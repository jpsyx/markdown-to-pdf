'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const version = fs.readFileSync(path.join(root, 'main.py'), 'utf8').match(/^__version__ = "([^"]+)"/m)[1];
const file = path.join(root, 'package.json');
const pkg = JSON.parse(fs.readFileSync(file, 'utf8'));
pkg.version = version;
fs.writeFileSync(file, JSON.stringify(pkg, null, 2) + '\n');
const lockFile = path.join(root, 'package-lock.json');
if (fs.existsSync(lockFile)) {
  const lock = JSON.parse(fs.readFileSync(lockFile, 'utf8'));
  lock.version = version;
  lock.packages[''].version = version;
  fs.writeFileSync(lockFile, JSON.stringify(lock, null, 2) + '\n');
}
