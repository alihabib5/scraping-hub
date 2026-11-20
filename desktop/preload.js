// What the app's own pages may ask the desktop app to do. Exposed as
// window.scrapingHub, which exists only inside the app: in a normal browser the
// console sees no such object and hides the desktop-only controls.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scrapingHub", {
  updateCredentials: () => ipcRenderer.invoke("update-credentials"),
  signIn: (email, password) => ipcRenderer.invoke("sign-in", email, password),
  signUp: (name, email, password) => ipcRenderer.invoke("sign-up", name, email, password),
  signOut: () => ipcRenderer.invoke("sign-out"),
  currentUser: () => ipcRenderer.invoke("current-user"),
  accountCount: () => ipcRenderer.invoke("account-count"),
});
