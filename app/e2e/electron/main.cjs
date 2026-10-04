// Minimal Electron host for the preview-latency check: loads the web UI from the
// core (same as the desktop shell does) so H.264 proxies can actually decode.
const { app, BrowserWindow } = require('electron')

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1440, height: 900, show: true, backgroundColor: '#141414', webPreferences: { contextIsolation: true, sandbox: true } })
  win.loadURL(`${process.env.BASE_URL || 'http://127.0.0.1:8770'}/search?q=${encodeURIComponent('street at night')}`)
})
app.on('window-all-closed', () => app.quit())
