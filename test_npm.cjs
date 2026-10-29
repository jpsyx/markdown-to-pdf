'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

test('packed CLI works locally and globally without install scripts or Mermaid', { timeout: 240000 }, () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'markdown npm test '));
  const env = { ...process.env, MARKDOWN_TO_PDF_CACHE_DIR: path.join(temp, 'python cache') };
  function run(command, args, options = {}) {
    const result = spawnSync(command, args, { cwd: temp, env, encoding: 'utf8', ...options });
    assert.equal(result.status, 0, `${command}: ${result.stdout}\n${result.stderr}`);
    return result;
  }
  try {
    const packResult = JSON.parse(run('npm', ['pack', '--json', '--pack-destination', temp], { cwd: __dirname }).stdout);
    const packed = Object.values(packResult)[0];
    const names = packed.files.map(file => file.path);
    assert.ok(names.includes('main.py'));
    assert.ok(names.includes('bin/markdown-to-pdf.cjs'));
    assert.ok(!names.some(name => /node_modules|\.venv|test_inline/.test(name)));
    const tarball = path.join(temp, packed.filename);
    fs.writeFileSync(path.join(temp, 'package.json'), JSON.stringify({ private: true, scripts: { pdf: 'markdown-to-pdf' } }));
    run('npm', ['install', '--save-dev', '--ignore-scripts', '--omit=optional', tarball]);
    const version = require('./package.json').version;
    assert.ok(run('npm', ['run', 'pdf', '--', '--version']).stdout.includes(version));
    fs.writeFileSync(path.join(temp, 'input with spaces.md'), '# CI release\n\nA **formatted** PDF.\n');
    run('npm', ['run', 'pdf', '--', 'input with spaces.md', '--out', 'local.pdf']);
    assert.equal(fs.readFileSync(path.join(temp, 'local.pdf')).subarray(0, 5).toString(), '%PDF-');
    const bin = path.join(temp, 'node_modules', '.bin', 'markdown-to-pdf');
    assert.equal(spawnSync(bin, [], { cwd: temp, env }).status, 2);
    // Reuse succeeds without pip or network access.
    run(bin, ['--help'], { env: { ...env, PIP_NO_INDEX: '1' } });
    const prefix = path.join(temp, 'global');
    run('npm', ['install', '-g', '--prefix', prefix, '--ignore-scripts', '--omit=optional', tarball]);
    run(path.join(prefix, 'bin', 'markdown-to-pdf'), ['input with spaces.md', '--out', 'global.pdf']);
    assert.equal(fs.readFileSync(path.join(temp, 'global.pdf')).subarray(0, 5).toString(), '%PDF-');
    const missing = spawnSync(bin, ['--version'], { cwd: temp, encoding: 'utf8', env: {
      ...env, MARKDOWN_TO_PDF_PYTHON: path.join(temp, 'missing-python') } });
    assert.equal(missing.status, 1);
    assert.match(missing.stderr, /Python 3.10\+ is required/);
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
});
