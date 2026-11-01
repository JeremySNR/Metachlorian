// Metachlorian desktop shell.
// Solo mode: starts a local core on 127.0.0.1 and shows its web UI.
// Team mode: connects to a shared core (server or NAS) configured by URL.
'use strict';
const { app, BrowserWindow, ipcMain, shell, dialog, nativeImage } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { startSoloCore, ensureModels, health } = require('./core');

const settingsFile = () => path.join(app.getPath('userData'), 'settings.json');
function loadSettings() {
  try { return JSON.parse(fs.readFileSync(settingsFile(), 'utf8')); } catch { return { mode: 'solo', serverUrl: '' }; }
}
function saveSettings(s) {
  fs.mkdirSync(path.dirname(settingsFile()), { recursive: true });
  fs.writeFileSync(settingsFile(), JSON.stringify(s, null, 2));
}

let core = null;
let win = null;
let baseUrl = null;

async function connect() {
  const s = loadSettings();
  if (s.mode === 'team' && s.serverUrl) {
    const h = await health(s.serverUrl, 4000);
    if (!h) throw new Error(`Cannot reach the Metachlorian server at ${s.serverUrl}.`);
    return s.serverUrl;
  }
  const opts = { resourcesPath: process.resourcesPath, dataDir: process.env.METACHLORIAN_DATA, onLog: (l) => process.stdout.write(l) };
  // First launch downloads the analysis models (~1.9 GB, once); later launches find them and continue at once.
  if (!process.env.METACHLORIAN_SKIP_MODEL_SETUP) await ensureModels({ ...opts, onEvent: showSetupProgress });
  setStatus({ title: 'Starting Metachlorian…' });
  core = await startSoloCore(opts);
  return core.baseUrl;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 900, minHeight: 600,
    backgroundColor: '#141414',
    title: 'Metachlorian',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  // Only our core's origin may load in the window; everything else opens in the browser.
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => { if (!baseUrl || !url.startsWith(baseUrl)) { e.preventDefault(); shell.openExternal(url); } });
  return win;
}

// The window shows this page until the library is ready: starting up, first-run model download, or an error.
function startupPage() {
  const html = `<!doctype html><meta charset="utf-8"><title>Metachlorian</title>
  <style>
    body{background:#141414;color:#e8e8e8;font:15px/1.5 system-ui;display:grid;place-items:center;height:100vh;margin:0}
    main{width:min(520px,calc(100vw - 48px))} h1{font-weight:600;font-size:20px;margin:0 0 8px}
    p{color:#b4b4b4;margin:0 0 16px} .bar{height:6px;background:#2a2a2a;border-radius:3px;overflow:hidden}
    .bar i{display:block;height:100%;width:0;background:#e8e8e8;transition:width .3s} small{color:#8a8a8a}
    button{font:inherit;background:#e8e8e8;color:#141414;border:0;border-radius:6px;padding:8px 16px;cursor:pointer}
    [hidden]{display:none!important}
  </style>
  <main><h1 id="t">Starting Metachlorian…</h1><p id="d"></p>
  <div id="p" hidden><div class="bar"><i id="b"></i></div><small id="n"></small></div>
  <div id="e" hidden><p id="m"></p><button onclick="window.metachlorian.retry()">Try again</button></div></main>
  <script>window.setState=(s)=>{t.textContent=s.title||'';d.textContent=s.detail||'';d.hidden=!s.detail;
    p.hidden=s.progress==null;if(s.progress!=null){b.style.width=(s.progress*100).toFixed(1)+'%';n.textContent=s.note||''}
    e.hidden=!s.error;m.textContent=s.error||''}</script>`;
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}
let pageReady = null;
function setStatus(state) {
  if (!win || win.isDestroyed()) return;
  (pageReady || Promise.resolve()).then(() => win.webContents.executeJavaScript(`window.setState && window.setState(${JSON.stringify(state)})`).catch(() => {}));
}
const gb = (bytes) => (bytes / 1e9).toFixed(bytes < 1e9 ? 2 : 1) + ' GB';
let setup = null;
function showSetupProgress(ev) {
  if (ev.event === 'plan') {
    setup = { sizes: Object.fromEntries(ev.models.map((m) => [m.name, m.size_mb * 1e6])), done: {}, current: {} };
    setup.total = Object.values(setup.sizes).reduce((a, b) => a + b, 0);
    if (!ev.models.length) setup = null;
  }
  if (!setup) return;
  if (ev.event === 'progress') {
    if (ev.total) setup.sizes[ev.model] = ev.total;
    setup.current[ev.model] = ev.done;
  }
  if (ev.event === 'done') setup.done[ev.model] = true;
  const total = Object.values(setup.sizes).reduce((a, b) => a + b, 0);
  const got = Object.keys(setup.sizes).reduce((a, n) => a + (setup.done[n] ? setup.sizes[n] : setup.current[n] || 0), 0);
  // Test hook: screenshot the setup screen part-way through (METACHLORIAN_SETUP_SHOT=<png path>).
  if (process.env.METACHLORIAN_SETUP_SHOT && !setup.shot && total && got / total > 0.2) {
    setup.shot = true;
    setTimeout(() => win.webContents.capturePage().then((img) => fs.writeFileSync(process.env.METACHLORIAN_SETUP_SHOT, img.toPNG())), 500);
  }
  setStatus({
    title: 'Setting up Metachlorian',
    detail: 'Downloading the models that watch and listen to your footage. This happens once and everything then runs on this computer.',
    progress: total ? Math.min(1, got / total) : 0,
    note: `${gb(got)} of ${gb(total)}`,
  });
}

async function start() {
  pageReady = win.loadURL(startupPage()).catch(() => {});
  try {
    baseUrl = await connect();
    await win.loadURL(baseUrl);
    if (process.env.METACHLORIAN_DESKTOP_SMOKE) {
      // Headless check: wait for the UI to render, save a screenshot, report the bridge, exit.
      await new Promise((r) => setTimeout(r, Number(process.env.METACHLORIAN_SMOKE_WAIT || 6000)));
      const img = await win.webContents.capturePage();
      fs.writeFileSync(process.env.METACHLORIAN_DESKTOP_SMOKE, img.toPNG());
      const bridge = await win.webContents.executeJavaScript('typeof window.metachlorian === "object" && window.metachlorian.desktop === true');
      process.stdout.write(JSON.stringify({ smoke: 'ok', baseUrl, bridge }) + '\n');
      app.quit();
    }
  } catch (err) {
    const team = loadSettings().mode === 'team';
    setStatus({
      title: team ? 'Can\'t reach your team server' : (setup ? 'Setup couldn\'t finish' : 'Metachlorian couldn\'t start'),
      detail: team ? 'Check the server is running and this computer is on the same network.'
        : setup ? 'Check your internet connection, then try again. Anything already downloaded is kept.' : '',
      error: String(err.message || err),
    });
    if (process.env.METACHLORIAN_DESKTOP_SMOKE) { process.stdout.write(JSON.stringify({ smoke: 'failed', error: String(err.message || err) }) + '\n'); app.exit(1); }
  }
}

// ---------------------------------------------------------------- bridge
ipcMain.handle('mc:retry', () => { if (!baseUrl) start(); return true; });
ipcMain.handle('mc:info', () => ({ desktop: true, platform: process.platform, mode: loadSettings().mode, baseUrl, version: app.getVersion() }));
ipcMain.handle('mc:setServer', async (_e, { mode, serverUrl }) => {
  if (mode === 'team') {
    const h = await health(serverUrl, 4000);
    if (!h) return { ok: false, error: `No Metachlorian server answered at ${serverUrl}` };
  }
  saveSettings({ ...loadSettings(), mode, serverUrl: serverUrl || '' });
  app.relaunch();
  app.exit(0);
  return { ok: true };
});
ipcMain.handle('mc:reveal', (_e, filePath) => { if (filePath && fs.existsSync(filePath)) shell.showItemInFolder(filePath); return true; });
ipcMain.handle('mc:openPath', (_e, filePath) => shell.openPath(filePath));
ipcMain.handle('mc:chooseFolder', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openDirectory'] });
  return r.canceled ? null : r.filePaths[0];
});
// Native drag-out of real files (exported clips) into editing software or Cutawan.
ipcMain.on('mc:startDrag', (e, { files, icon }) => {
  const list = (files || []).filter((f) => typeof f === 'string' && fs.existsSync(f));
  if (!list.length) return;
  let img = icon && fs.existsSync(icon) ? nativeImage.createFromPath(icon).resize({ width: 96 }) : nativeImage.createEmpty();
  if (img.isEmpty()) img = nativeImage.createFromDataURL('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBApkbN4IAAAAASUVORK5CYII=');
  e.sender.startDrag(list.length === 1 ? { file: list[0], icon: img } : { files: list, icon: img });
});
// Hand a package to Cutawan (if installed) with its documented CLI.
ipcMain.handle('mc:openInCutawan', async (_e, packagePath) => {
  const { spawn } = require('node:child_process');
  const candidates = process.platform === 'darwin' ? ['/Applications/Cutawan.app/Contents/MacOS/Cutawan'] :
    process.platform === 'win32' ? [path.join(process.env.LOCALAPPDATA || '', 'Programs', 'cutawan', 'Cutawan.exe')] : ['cutawan'];
  for (const c of candidates) {
    try {
      const child = spawn(c, ['--import-package', packagePath], { detached: true, stdio: 'ignore' });
      child.unref();
      return { ok: true };
    } catch { /* try the next one */ }
  }
  return { ok: false, error: 'Cutawan was not found. Install it from https://github.com/JeremySNR/cutawan/releases' };
});

app.whenReady().then(() => {
  createWindow();
  start();
});

app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { if (core && core.child) core.child.kill(); });
