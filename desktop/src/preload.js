// The capability bridge the web UI checks for (window.metachlorian is undefined in a browser).
'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('metachlorian', {
  desktop: true,
  info: () => ipcRenderer.invoke('mc:info'),
  setServer: (mode, serverUrl) => ipcRenderer.invoke('mc:setServer', { mode, serverUrl }),
  startDrag: (files, icon) => ipcRenderer.send('mc:startDrag', { files, icon }),
  reveal: (filePath) => ipcRenderer.invoke('mc:reveal', filePath),
  openPath: (filePath) => ipcRenderer.invoke('mc:openPath', filePath),
  chooseFolder: () => ipcRenderer.invoke('mc:chooseFolder'),
  openInCutawan: (packagePath) => ipcRenderer.invoke('mc:openInCutawan', packagePath),
});
