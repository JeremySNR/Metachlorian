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

// How to run the core: { cmd, prefix (args before ours), env }.
// Installed apps carry their own Python, core, web app and FFmpeg in resources (desktop/scripts/bundle.mjs);
// a source checkout falls back to an env override, the install.sh venv, the repo venv, then PATH.
function findCoreCommand(resourcesPath) {
  const win = process.platform === 'win32';
  const bundled = resourcesPath && path.join(resourcesPath, 'python', win ? 'python.exe' : path.join('bin', 'python3'));
  if (!process.env.METACHLORIAN_BIN && bundled && fs.existsSync(bundled)) {
    const ff = (tool) => path.join(resourcesPath, 'ffmpeg', tool + (win ? '.exe' : ''));
    return {
      cmd: bundled,
      prefix: ['-m', 'metachlorian'],
      env: {
        METACHLORIAN_APP_DIST: path.join(resourcesPath, 'app'),
        METACHLORIAN_FFMPEG: ff('ffmpeg'),
        METACHLORIAN_FFPROBE: ff('ffprobe'),
        // The bundle is read-only (and signed on macOS): never write bytecode or read the user's site-packages.
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONNOUSERSITE: '1',
        PYTHONHOME: '', PYTHONPATH: '',
      },
    };
  }
  const candidates = [];
  if (process.env.METACHLORIAN_BIN) candidates.push(process.env.METACHLORIAN_BIN);
  const exe = win ? path.join('Scripts', 'metachlorian.exe') : path.join('bin', 'metachlorian');
  candidates.push(path.join(os.homedir(), '.local', 'src', 'metachlorian', '.venv', exe));
  candidates.push(path.join(__dirname, '..', '..', 'core', '.venv', exe));
  const cmd = candidates.find((c) => c && fs.existsSync(c)) || 'metachlorian'; // rely on PATH
  return { cmd, prefix: [], env: {} };
}

function runCore(core, args) {
  const env = { ...process.env, ...core.env };
  for (const k of Object.keys(env)) if (env[k] === '') delete env[k];
  return spawn(core.cmd, [...core.prefix, ...args], { stdio: ['ignore', 'pipe', 'pipe'], env, windowsHide: true });
}

// First-run setup: download any missing analysis models, reporting progress.
// onEvent receives the JSON events of `metachlorian models fetch --json` (plan, start, progress, done, complete).
function ensureModels({ resourcesPath, dataDir, onEvent, onLog } = {}) {
  const core = findCoreCommand(resourcesPath);
  const args = dataDir ? ['--data', dataDir] : [];
  const child = runCore(core, [...args, 'models', 'fetch', '--json']);
  let buf = '';
  let failure = null;
  child.stdout.on('data', (d) => {
    buf += String(d);
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line) continue;
      try {
        const ev = JSON.parse(line);
        if (ev.event === 'error') failure = ev.message;
        onEvent && onEvent(ev);
      } catch { onLog && onLog(line + '\n'); }
    }
  });
  child.stderr.on('data', (d) => onLog && onLog(String(d)));
  return new Promise((resolve, reject) => {
    child.on('error', (e) => reject(new Error(`Could not start the Metachlorian engine (${core.cmd}): ${e.message}`)));
    child.on('exit', (code) => code === 0 ? resolve() : reject(new Error(failure || `Model setup stopped unexpectedly (exit ${code}).`)));
  });
}

async function startSoloCore({ resourcesPath, dataDir, onLog } = {}) {
  const port = await freePort(8765);
  const baseUrl = `http://127.0.0.1:${port}`;
  const existing = await health(baseUrl);
  if (existing) return { baseUrl, child: null, reused: true };
  const core = findCoreCommand(resourcesPath);
  const args = [];
  if (dataDir) args.push('--data', dataDir);
  args.push('serve', '--host', '127.0.0.1', '--port', String(port));
  const child = runCore(core, args);
  let spawnError = null;
  child.on('error', (e) => { spawnError = e; });
  child.stdout.on('data', (d) => onLog && onLog(String(d)));
  child.stderr.on('data', (d) => onLog && onLog(String(d)));
  const started = Date.now();
  // The first start after installing can be slow (antivirus scans every new file on Windows).
  while (Date.now() - started < 180_000) {
    if (spawnError) throw new Error(`Could not start the Metachlorian engine (${core.cmd}): ${spawnError.message}`);
    if (child.exitCode !== null) throw new Error(`The Metachlorian engine stopped while starting (exit ${child.exitCode}).`);
    if (await health(baseUrl)) return { baseUrl, child, reused: false };
    await new Promise((r) => setTimeout(r, 400));
  }
  child.kill();
  throw new Error('The Metachlorian engine did not start within 3 minutes.');
}

module.exports = { freePort, health, findCoreCommand, ensureModels, startSoloCore };
