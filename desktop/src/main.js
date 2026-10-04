// Metachlorian desktop shell.
// Solo mode: starts a local core on 127.0.0.1 and shows its web UI.
// Team mode: connects to a shared core (server or NAS) configured by URL.
'use strict';
const { app, BrowserWindow, ipcMain, shell, dialog, nativeImage } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { startSoloCore, health } = require('./core');

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
  core = await startSoloCore({ resourcesPath: process.resourcesPath, dataDir: process.env.METACHLORIAN_DATA, onLog: (l) => process.stdout.write(l) });
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

function startupPage(message) {
  const html = `<!doctype html><meta charset="utf-8"><title>Metachlorian</title>
  <body style="background:#141414;color:#e8e8e8;font:15px system-ui;display:grid;place-items:center;height:100vh;margin:0">
  <div style="max-width:520px"><h1 style="font-weight:600;font-size:20px">Metachlorian</h1><p>${message}</p></div></body>`;
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}

// ---------------------------------------------------------------- bridge
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

app.whenReady().then(async () => {
  createWindow();
  win.loadURL(startupPage('Starting the library…'));
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
    win.loadURL(startupPage(String(err.message || err) + '<br><br>Install the core with <code>scripts/install.sh</code>, or switch to a team server in settings.'));
  }
});

app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { if (core && core.child) core.child.kill(); });
