// Scraping Hub desktop app: the window the team double-clicks.
//
// Installed layout (C:\Program Files\Scraping Hub — read-only):
//   Scraping Hub.exe          this Electron shell
//   server\                   the compiled API (scraping-hub-server.exe, no source)
//   console\                  the console as static files (client, SCRAPING_HUB_DESKTOP=1 build)
//   pgsql\                    PostgreSQL, run as the "ScrapingHubDB" service the installer set up
// Everything written goes to C:\ProgramData\Scraping Hub (database, archives, logs, settings),
// including credentials.shc: the encrypted portal logins the setup wizard asked for.
//
// On start: launch the server hidden, wait until it answers, show the console.
// On quit: stop the server and every Chrome it started.
// "Update credentials" (button in the console, via preload.js): swap in a new
// credentials.shc after the engine confirms it opens, then restart the engine.

const { app, BrowserWindow, dialog, ipcMain, net, protocol, session, shell } = require("electron");
const { spawn, execFile } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const PORT = 9001; // the console is built against http://127.0.0.1:9001
const API = `http://127.0.0.1:${PORT}`;
const INSTALL_DIR = app.isPackaged ? path.dirname(process.execPath) : path.resolve(__dirname, "..");
// Development only (npm start): SCRAPING_HUB_DATA_DIR keeps a test run out of ProgramData.
const DATA_DIR =
  (!app.isPackaged && process.env.SCRAPING_HUB_DATA_DIR) ||
  path.join(process.env.ProgramData || "C:\\ProgramData", "Scraping Hub");

// In development (npm start in desktop\) the pieces are found where the builds leave them.
const SERVER_EXE = app.isPackaged
  ? path.join(INSTALL_DIR, "server", "scraping-hub-server.exe")
  : path.join(INSTALL_DIR, "installer", "build", "hub_server.dist", "scraping-hub-server.exe");
const CONSOLE_DIR = app.isPackaged
  ? path.join(INSTALL_DIR, "console")
  : path.join(INSTALL_DIR, "client", "out-desktop");

let server = null;
let win = null;
// The signed-in employee, { username, name }, until the app closes. Null = sign-in screen.
let user = null;
// The account panel's session for that sign-in: checked in every few minutes, ended on sign-out / close.
const PING_MS = 5 * 60_000;
let pingTimer = null;
const SIGNIN_FILE = path.join(__dirname, "signin.html");
const SIGNIN_URL = pathToFileURL(SIGNIN_FILE).href;

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

if (!app.requestSingleInstanceLock()) {
  app.quit(); // already open: the first instance focuses its window instead
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(start);
}

/** app://hub/console/emma -> console\console\emma.html (Next's static export layout). */
function serveConsole() {
  protocol.handle("app", (request) => {
    if (!user) return new Response("Sign in first", { status: 403 }); // the console only after sign-in
    const rel = decodeURIComponent(new URL(request.url).pathname).replace(/^\/+/, "");
    const base = path.resolve(CONSOLE_DIR);
    const candidates = rel === "" ? ["index.html"] : [rel, `${rel}.html`, path.join(rel, "index.html")];
    for (const c of candidates) {
      const file = path.resolve(base, c);
      if (file.startsWith(base) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        return net.fetch(pathToFileURL(file).toString());
      }
    }
    return net.fetch(pathToFileURL(path.join(base, "404.html")).toString());
  });
}

let failed = false;

/** Tell the user in plain words what went wrong, then close. Only the first problem is shown. */
function fatal(title, message) {
  if (failed) return;
  failed = true;
  app.isQuitting = true;
  stopServer();
  console.error(`${title}: ${message}`);
  dialog.showErrorBox(title, message);
  app.quit();
}

/** Who is answering on the app's port: "hub" (an engine from an earlier session), "other" or "none". */
async function probePort() {
  try {
    const body = await (await net.fetch(`${API}/`)).json().catch(() => ({}));
    return body.service === "scraping-hub" ? "hub" : "other";
  } catch {
    return "none";
  }
}

function startServer() {
  const logs = path.join(DATA_DIR, "logs");
  const logFile = path.join(logs, "server.log");
  if (!fs.existsSync(SERVER_EXE)) {
    fatal(
      "Scraping Hub is incomplete",
      `A part of Scraping Hub is missing:\n${SERVER_EXE}\n\n` +
        "Please reinstall Scraping Hub. If your antivirus removed this file, ask IT to allow it, then reinstall.",
    );
    return false;
  }
  fs.mkdirSync(logs, { recursive: true });
  const out = fs.openSync(logFile, "a");
  const proc = spawn(SERVER_EXE, [], {
    cwd: DATA_DIR,
    windowsHide: true,
    stdio: ["ignore", out, out],
    env: {
      ...process.env,
      SCRAPING_HUB_PORT: String(PORT),
      SCRAPING_HUB_DATA_DIR: DATA_DIR,
      ARCHIVE_DIR: path.join(DATA_DIR, "archives"),
      DOWNLOAD_DIR: path.join(DATA_DIR, "documents"),
      WORK_DIR: path.join(DATA_DIR, "work"),
      NORTHDAKOTA_PROFILE_DIR: path.join(DATA_DIR, "chrome_profiles", "northdakota"),
      PUBLIC_BASE_URL: API,
    },
  });
  server = proc;
  // Events from an engine that has since been replaced or stopped on purpose
  // (a restart, quitting) are not news.
  proc.on("error", (err) => {
    if (server !== proc) return;
    server = null;
    fatal(
      "Scraping Hub could not start",
      `The Scraping Hub engine could not be started (${err.code || err.message}).\n\n` +
        "Please reinstall Scraping Hub. If your antivirus blocked it, ask IT to allow it.",
    );
  });
  proc.on("exit", (code) => {
    if (server !== proc) return;
    server = null;
    if (!app.isQuitting) {
      fatal(
        "Scraping Hub stopped",
        `The Scraping Hub engine closed unexpectedly (code ${code}).\n\n` +
          `Please close and reopen Scraping Hub. If it keeps happening, send IT this file:\n${logFile}`,
      );
    }
  });
  return true;
}

async function waitForServer(timeoutMs = 90_000) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until && !failed) {
    try {
      if ((await net.fetch(`${API}/`)).ok) return true;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function stopServer() {
  if (!server) return;
  // /T takes the whole tree: the server plus every chromedriver and Chrome it started.
  execFile("taskkill", ["/PID", String(server.pid), "/T", "/F"], { windowsHide: true }, () => {});
  server = null;
}

// -- Update credentials ------------------------------------------------------

const run = (file, args) =>
  new Promise((resolve) =>
    execFile(file, args, { windowsHide: true, timeout: 60_000 }, (err, stdout) =>
      resolve({ ok: !err, out: String(stdout || "").trim() }),
    ),
  );

/** Ask the engine whether `file` opens with this build's key: { ok, detail }. */
async function checkCredentials(file) {
  const { ok, out } = await run(SERVER_EXE, ["--check-credentials", file]);
  const detail = out.replace(/^(OK|FAIL) - /, "") || "the engine could not check it";
  return { ok: ok && out.startsWith("OK"), detail };
}

/** Runs not yet finished (running, queued or paused). A restart would cut them off. */
async function activeRuns() {
  try {
    const body = await (await net.fetch(`${API}/runs?active=true`)).json();
    return (body.jobs || []).length;
  } catch {
    return 0; // engine not answering: nothing to cut off
  }
}

/** Restart the engine so it reads the new credentials file. */
async function restartServer() {
  const old = server;
  server = null; // the old engine's exit is expected, not an error
  if (old) {
    await run("taskkill", ["/PID", String(old.pid), "/T", "/F"]);
  } else {
    // An engine we did not start (left over from an earlier session): by name.
    await run("taskkill", ["/IM", "scraping-hub-server.exe", "/T", "/F"]);
  }
  for (let i = 0; i < 40 && (await probePort()) !== "none"; i++) {
    await new Promise((r) => setTimeout(r, 250));
  }
  return startServer() && (await waitForServer());
}

/**
 * Swap in a new credentials file. Returns what happened for the console to
 * show: { ok, code, message, detail }. Nothing changes unless `ok`.
 *   cancelled | rejected | busy | failed | updated
 * SCRAPING_HUB_PICK_FILE skips the file picker (used by the automated tests;
 * the file still has to pass every check).
 */
async function updateCredentials() {
  let chosen = process.env.SCRAPING_HUB_PICK_FILE;
  if (!chosen) {
    const pick = await dialog.showOpenDialog(win, {
      title: "Choose the new credentials file",
      filters: [{ name: "Scraping Hub credentials", extensions: ["shc"] }],
      properties: ["openFile"],
    });
    if (pick.canceled || pick.filePaths.length === 0) return { ok: false, code: "cancelled" };
    chosen = pick.filePaths[0];
  }

  const check = await checkCredentials(chosen);
  if (!check.ok) {
    return {
      ok: false,
      code: "rejected",
      message: "That file can't be used, so nothing was changed.",
      detail: `${check.detail}. Choose the .shc file you were sent for this version of Scraping Hub.`,
    };
  }

  const busy = await activeRuns();
  if (busy > 0) {
    return {
      ok: false,
      code: "busy",
      message: `${busy} run${busy === 1 ? " is" : "s are"} still in progress, so nothing was changed.`,
      detail: "Let them finish, or stop them, then choose Update credentials again.",
    };
  }

  // Copy beside the target first, then swap it in with a rename, so the
  // installed file is never half-written. The previous file is kept as .bak.
  const target = path.join(DATA_DIR, "credentials.shc");
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.copyFileSync(chosen, `${target}.new`);
  const hadPrevious = fs.existsSync(target);
  if (hadPrevious) fs.copyFileSync(target, `${target}.bak`);
  fs.renameSync(`${target}.new`, target);

  if (!(await restartServer())) {
    fatal(
      "Scraping Hub could not restart",
      "The new credentials were saved, but the engine did not start again.\n\n" +
        "Please close and reopen Scraping Hub. If it still fails, send IT this file:\n" +
        path.join(DATA_DIR, "logs", "server.log"),
    );
    return { ok: false, code: "failed" };
  }
  return {
    ok: true,
    code: "updated",
    message: "Credentials updated. The new portal logins are in use.",
    detail: `${check.detail} loaded.` + (hadPrevious ? " The previous file was kept as credentials.shc.bak." : ""),
  };
}

let updating = false;
const fromApp = (event) => {
  const url = event.senderFrame?.url || "";
  return url.startsWith("app://hub") || url === SIGNIN_URL;
};

ipcMain.handle("update-credentials", async (event) => {
  // Only our own pages may ask, and one update at a time.
  if (!fromApp(event)) return { ok: false, code: "cancelled" };
  if (updating) return { ok: false, code: "busy", message: "An update is already in progress." };
  updating = true;
  try {
    return await updateCredentials();
  } catch (err) {
    console.error("update-credentials failed:", err);
    return { ok: false, code: "failed", message: "Something went wrong and nothing was changed.", detail: String(err.message || err) };
  } finally {
    updating = false;
  }
});

async function start() {
  serveConsole();

  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 650,
    title: "Scraping Hub",
    backgroundColor: "#faf8f3",
    autoHideMenuBar: true,
    show: false,
    webPreferences: { contextIsolation: true, sandbox: true, preload: path.join(__dirname, "preload.js") },
  });
  win.setMenu(null);
  win.once("ready-to-show", () => win.show());
  // Why a window went away, in the app's own output (seen when run from a terminal).
  win.webContents.on("render-process-gone", (_e, d) => console.error("console renderer gone:", d.reason, d.exitCode));
  win.on("closed", () => console.error("window closed"));
  app.on("child-process-gone", (_e, d) => console.error("child process gone:", d.type, d.reason, d.exitCode));

  // Bid links and anything else outside the app open in the normal browser.
  // The app's own pages and the local API (Excel / ZIP downloads) stay here.
  const internal = (url) => url.startsWith("app://hub") || url.startsWith(API);
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!internal(url)) {
      event.preventDefault();
      if (/^https?:/.test(url)) shell.openExternal(url);
    }
  });

  await win.loadFile(path.join(__dirname, "loading.html"));
  const onPort = await probePort();
  if (onPort === "other") {
    fatal(
      "Scraping Hub could not start",
      `Another program is using port ${PORT}, which Scraping Hub needs.\n\n` +
        "Please restart the computer and try again. If it keeps happening, tell IT.",
    );
    return;
  }
  // "hub": an engine left running by an earlier session (e.g. after a crash) — use it.
  if (onPort === "none" && !startServer()) return;
  if (!(await waitForServer())) {
    fatal(
      "Scraping Hub could not start",
      "The Scraping Hub engine did not start within 90 seconds.\n\n" +
        "Please restart the computer and try again. If it still fails, send IT this file:\n" +
        path.join(DATA_DIR, "logs", "server.log"),
    );
    return;
  }
  // Every request to the engine carries who is signed in, so runs record it.
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls: [`${API}/*`] }, (details, callback) => {
    if (user) details.requestHeaders["X-Hub-User"] = user.username;
    callback({ requestHeaders: details.requestHeaders });
  });
  await win.loadFile(SIGNIN_FILE);
}

// -- Sign-in ---------------------------------------------------------------

ipcMain.handle("sign-in", async (event, username, password) => {
  if (!fromApp(event)) return { ok: false, message: "Not allowed." };
  try {
    const res = await net.fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: String(username || ""), password: String(password || "") }),
    });
    if (res.status === 401) return { ok: false, message: "That email and password don't match an account." };
    if (!res.ok) {
      // 403 = waiting for approval, 503 = account server unreachable: the engine words both for the person.
      const detail = (await res.json().catch(() => ({}))).detail;
      return { ok: false, message: typeof detail === "string" ? detail : `Sign-in failed (engine answered ${res.status}).` };
    }
    user = await res.json();
    clearInterval(pingTimer);
    pingTimer = setInterval(() => net.fetch(`${API}/auth/ping`, { method: "POST" }).catch(() => {}), PING_MS);
  } catch {
    return { ok: false, message: "The Scraping Hub engine is not answering. Close and reopen Scraping Hub." };
  }
  await win.loadURL("app://hub/");
  return { ok: true };
});

ipcMain.handle("sign-up", async (event, name, email, password) => {
  if (!fromApp(event)) return { ok: false, message: "Not allowed." };
  try {
    const res = await net.fetch(`${API}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: String(name || ""), email: String(email || ""), password: String(password || "") }),
    });
    if (res.ok) return { ok: true };
    const detail = (await res.json().catch(() => ({}))).detail;
    // 409/422 carry a sentence for the person; FastAPI's own validation errors are a list.
    return { ok: false, message: typeof detail === "string" ? detail : `Sign-up failed (engine answered ${res.status}).` };
  } catch {
    return { ok: false, message: "The Scraping Hub engine is not answering. Close and reopen Scraping Hub." };
  }
});

/** Tell the account panel the session is over. Best effort, never longer than 3 s: closing must not hang on it. */
async function endPanelSession() {
  clearInterval(pingTimer);
  pingTimer = null;
  if (!user) return;
  const done = net.fetch(`${API}/auth/logout`, { method: "POST" }).catch(() => {});
  await Promise.race([done, new Promise((resolve) => setTimeout(resolve, 3000))]);
}

ipcMain.handle("sign-out", async (event) => {
  if (!fromApp(event)) return;
  await endPanelSession();
  user = null;
  await win.loadFile(SIGNIN_FILE);
});

ipcMain.handle("current-user", (event) => (fromApp(event) ? user : null));

ipcMain.handle("account-count", async (event) => {
  if (!fromApp(event)) return 0;
  try {
    const status = await (await net.fetch(`${API}/auth/status`)).json();
    return status.accounts || (status.panel ? 1 : 0); // with the account server, anyone may sign in or sign up
  } catch {
    return 0;
  }
});

app.on("before-quit", (event) => {
  if (user && !failed) {
    // End the panel session while the engine is still up, then quit for real.
    event.preventDefault();
    endPanelSession().finally(() => {
      user = null;
      app.quit();
    });
    return;
  }
  app.isQuitting = true;
  stopServer();
});
app.on("window-all-closed", () => app.quit());
