// Finding, starting and talking to a Metachlorian core.
'use strict';
const { spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

function freePort(preferred = 8765) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => {
      const s2 = net.createServer();
      s2.listen(0, '127.0.0.1', () => { const p = s2.address().port; s2.close(() => resolve(p)); });
    });
    srv.listen(preferred, '127.0.0.1', () => { const p = srv.address().port; srv.close(() => resolve(p)); });
  });
}

async function health(baseUrl, timeoutMs = 1500) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(new URL('/api/health', baseUrl), { signal: ctrl.signal });
    if (!r.ok) return null;
    const j = await r.json();
    return j && j.name === 'metachlorian' ? j : null;
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

// Where the `metachlorian` command lives: env override, bundled venv, user install, PATH.
function findCoreCommand(resourcesPath) {
  const candidates = [];
  if (process.env.METACHLORIAN_BIN) candidates.push(process.env.METACHLORIAN_BIN);
  const exe = process.platform === 'win32' ? path.join('Scripts', 'metachlorian.exe') : path.join('bin', 'metachlorian');
  if (resourcesPath) candidates.push(path.join(resourcesPath, 'python', exe));
  candidates.push(path.join(os.homedir(), '.local', 'src', 'metachlorian', '.venv', exe));
  candidates.push(path.join(__dirname, '..', '..', 'core', '.venv', exe));
  for (const c of candidates) if (c && fs.existsSync(c)) return c;
  return 'metachlorian'; // rely on PATH
}

async function startSoloCore({ resourcesPath, dataDir, onLog } = {}) {
  const port = await freePort(8765);
  const baseUrl = `http://127.0.0.1:${port}`;
  const existing = await health(baseUrl);
  if (existing) return { baseUrl, child: null, reused: true };
  const cmd = findCoreCommand(resourcesPath);
  const args = [];
  if (dataDir) args.push('--data', dataDir);
  args.push('serve', '--host', '127.0.0.1', '--port', String(port));
  const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env } });
  child.stdout.on('data', (d) => onLog && onLog(String(d)));
  child.stderr.on('data', (d) => onLog && onLog(String(d)));
  const started = Date.now();
  while (Date.now() - started < 60_000) {
    if (child.exitCode !== null) throw new Error(`The Metachlorian core exited (${child.exitCode}). Is it installed? Tried: ${cmd}`);
    if (await health(baseUrl)) return { baseUrl, child, reused: false };
    await new Promise((r) => setTimeout(r, 400));
  }
  child.kill();
  throw new Error('The Metachlorian core did not start within 60 seconds.');
}

module.exports = { freePort, health, findCoreCommand, startSoloCore };
