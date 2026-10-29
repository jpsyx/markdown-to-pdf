#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync, spawn } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const requirements = path.join(root, 'requirements.txt');
const pythonOverride = process.env.MARKDOWN_TO_PDF_PYTHON;
const key = crypto.createHash('sha256').update(root).update(fs.readFileSync(requirements))
  .update(pythonOverride || '').digest('hex').slice(0, 20);
const cache = path.resolve(process.env.MARKDOWN_TO_PDF_CACHE_DIR ||
  path.join(os.homedir(), '.cache', 'markdown-to-pdf', 'npm'));
const venv = path.join(cache, key);
const python = path.join(venv, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const lock = `${venv}.lock`;
const marker = path.join(venv, '.ready');

function ready() {
  return fs.existsSync(marker) && spawnSync(python, ['-c', 'import reportlab, pygments'],
    { stdio: 'ignore' }).status === 0;
}

function run(command, args, fix) {
  const result = spawnSync(command, args, { stdio: ['inherit', 2, 2] });
  if (result.error || result.status !== 0) throw new Error(fix);
}

async function provision() {
  if (ready()) return;
  fs.mkdirSync(cache, { recursive: true });
  const deadline = Date.now() + 120000;
  while (true) {
    try { fs.mkdirSync(lock); break; }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      if (ready()) return;
      if (Date.now() > deadline) throw new Error(
        `Timed out waiting for Python setup. If no other conversion is running, remove ${lock} and retry.`);
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }
  try {
    if (ready()) return;
    const candidates = pythonOverride ? [[pythonOverride]] :
      (process.platform === 'win32' ? [['py', '-3'], ['python3'], ['python']] : [['python3']]);
    const selected = candidates.find(([command, ...args]) => spawnSync(command,
      [...args, '-c', 'import sys; sys.exit(sys.version_info < (3, 10))'],
      { stdio: 'ignore' }).status === 0);
    if (!selected) throw new Error('Python 3.10+ is required. Install it from https://www.python.org/downloads/ or set MARKDOWN_TO_PDF_PYTHON to its executable.');
    fs.rmSync(venv, { recursive: true, force: true });
    console.error('markdown-to-pdf: preparing private Python environment...');
    const [command, ...args] = selected;
    run(command, [...args, '-m', 'venv', venv],
      'Could not create Python environment. On Debian/Ubuntu, install python3-venv (sudo apt install python3-venv), then retry.');
    run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirements],
      'Could not install Python dependencies. Check network access and pip configuration, then retry.');
    run(python, ['-c', 'import reportlab, pygments'], 'Python dependencies are unavailable. Retry setup.');
    fs.writeFileSync(marker, 'ready\n');
  } finally {
    fs.rmdirSync(lock);
  }
}

async function main() {
  await provision();
  // npm may hoist Mermaid outside this package. Resolve it through Node, then
  // expose its CLI to Python's existing PATH-based renderer discovery.
  const env = { ...process.env };
  const bins = (require.resolve.paths('@mermaid-js/mermaid-cli') || [])
    .map(directory => path.join(directory, '.bin'));
  env.PATH = [...bins, env.PATH || ''].join(path.delimiter);
  const child = spawn(python, [path.join(root, 'main.py'), ...process.argv.slice(2)],
    { stdio: 'inherit', env });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
  child.on('error', error => { console.error(`markdown-to-pdf: ${error.message}`); process.exitCode = 1; });
  child.on('exit', (code, signal) => {
    if (signal) {
      process.removeAllListeners(signal);
      process.kill(process.pid, signal);
    }
    else process.exitCode = code;
  });
}
main().catch(error => { console.error(`markdown-to-pdf: ${error.message}`); process.exitCode = 1; });
