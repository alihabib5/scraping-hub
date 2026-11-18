# Scraping Hub — Windows installer

Builds `ScrapingHub-Setup-<version>.exe`: a normal Windows setup wizard. The team
gets the app without any source code.

| Where | What |
| --- | --- |
| `C:\Program Files\Scraping Hub\` | the app: window (`Scraping Hub.exe`), compiled server, console, PostgreSQL. Read-only |
| `C:\ProgramData\Scraping Hub\` | everything it writes: `pgdata\` (database), `archives\`, `documents\`, `logs\`, `.env` (database address), `credentials.shc` |
| Start Menu, desktop | shortcuts; uninstall from *Settings → Apps* |
| Windows service `ScrapingHubDB` | the app's own PostgreSQL, port 5433, this PC only |

## What you hand out

1. `installer\output\ScrapingHub-Setup-1.0.0.exe`
2. `installer\output\rizviz-credentials.shc`, the encrypted portal logins

The wizard asks for the `.shc` file. If you run it from the command line, pass
`/CREDENTIALS="path\to\file.shc"` (add `/SILENT` for a no-questions install).

## Building

Run from the repo root. You need `server\.venv` with Nuitka, and Inno Setup 6.

```bat
server\.venv\Scripts\python.exe installer\build_server.py
cd client && set SCRAPING_HUB_DESKTOP=1&& set NEXT_PUBLIC_API_URL=http://127.0.0.1:9001&& npx next build && cd ..
cd desktop && npm run package && cd ..
server\.venv\Scripts\python.exe installer\stage.py
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\ScrapingHub.iss
server\.venv\Scripts\python.exe installer\make_credentials.py
```

`build_server.py` takes a while (Nuitka compiles everything to C). Two scripts
refuse to finish if anything that must not ship gets in:

- `build_server.py` fails on any `.py` file or readable login in the build.
- `stage.py` fails on any source file, `.env`, key or `.shc`.

## Credentials

- `make_credentials.py` reads `server\.env` and leaves out per-PC settings such
  as `DATABASE_URL`.

### Employee sign-in

Everyone signs in with their email when they open Scraping Hub, and each run
records who started it (shown as "by <email>" in History).

Accounts are managed online, in the account panel on Vercel (`admin/` in this
repo; its README covers setting it up):

- **Create account** on the app's sign-in screen sends a request (display name,
  email, password) to the panel. It cannot sign in until an administrator
  approves it there.
- **Sign in** asks the panel. Each PC remembers, as a password hash, the people
  who signed in on it, so a short internet outage doesn't lock them out.
- **Removing** someone in the panel stops them signing in on each PC the next
  time that PC is online.

The app finds the panel through two settings in `server/.env`, which
`make_credentials.py` packs into the `.shc` with the portal logins:

```
SCRAPING_HUB_ACCOUNTS_URL=https://<your-panel>.vercel.app
SCRAPING_HUB_API_KEY=<the same value as HUB_API_KEY in Vercel>
```

**Optional: issued accounts.** `installerccounts.csv` (gitignored; columns
`email,name,password`, passwords 8+ characters) adds accounts that sign in from
the credentials file itself, even when the panel is unreachable. Without the
panel settings, this file is required.

After changing either, run `make_credentials.py` again and send the new `.shc`;
on each PC use **Update credentials**, or run the setup again and choose the file.

### When a portal password changes

No rebuild and no reinstall:

1. Put the new password in `server\.env`. Quote values that contain symbols
   or spaces, for example `BIDNET_PASSWORD='new#pass'`.
2. Run `server\.venv\Scripts\python.exe installer\make_credentials.py` and send
   the new `installer\output\rizviz-credentials.shc` to the team.
3. On each PC, click **Update credentials** at the top of the console and choose
   that file.

The app then does the rest:

- It checks the file opens with this build's key, and refuses a wrong or damaged
  file without changing anything.
- It refuses while a run is in progress, so no run is cut off.
- It swaps the file in safely and keeps the old one as `credentials.shc.bak`.
- It restarts the engine and confirms how many settings it loaded.

Running the setup again and choosing the new file also works.

### The key

- **Back up `installer\credentials.key`.** It is created on first use and is not
  in git. The app holds only this key, never a password, and a `.shc` only opens
  in a build made with the same key.
- The limit: because the key ships inside the app, encryption stops anyone
  reading the passwords off the disk, but not a determined reverse-engineer.

## Updating the PCs

1. Raise `AppVersion` in `ScrapingHub.iss` (and `version` in `desktop\package.json`).
2. Build again and run the new setup on each PC. It upgrades in place and keeps
   the database, results and credentials. Leave the credentials page empty to
   keep the current file.

Never change the `AppId` in `ScrapingHub.iss`. It is how a new setup recognises
an existing install.

## Needs on each PC

- Windows 10/11, 64-bit, and an admin account once, to install.
- **Google Chrome.** The wizard warns if it is missing.
- Internet access. Selenium fetches a matching chromedriver on the first run.

## Troubleshooting

### A new PC fails to install or the engine stops

The wizard checks the engine on the PC at the end of the install and saves the
result. Collect these from the PC and send them along with the PC model:

- `C:\ProgramData\Scraping Hub\logs\setup-database.log`: every step of the
  database setup and PostgreSQL's own replies
- `C:\ProgramData\Scraping Hub\logs\self-check.log`: how far the engine got
  on that PC and what the chip is
- `C:\ProgramData\Scraping Hub\logs\server.log`: the engine's log

"Engine closed unexpectedly (code 3221225501)" means *illegal instruction*: the
PC's processor cannot run something in the build. The usual cause is an ARM
laptop (Snapdragon "Copilot+" PCs) running the x64 build through emulation; the
wizard warns on those. Check *Settings → System → About → System type*.


All logs are in `C:\ProgramData\Scraping Hub\logs\`:

- `server.log`: the engine
- `setup-database.log`: the database setup

To check that an install can do everything a run needs, run this in a Command Prompt:

```bat
"C:\Program Files\Scraping Hub\server\scraping-hub-server.exe" --self-check
```

It loads every scraper module, reads a PDF and a Word file, checks Excel,
starts a headless Chrome and opens the credentials file, one line each. It ends
with "Self-check passed", or names what is missing.

`installer\nuitka_plugin.py` does two things during the build:

- It blanks the docstrings (developer explanations) in Rizviz's own code, so
  they don't ship as readable text in the exe. Third-party libraries keep
  theirs, because some need them to run.
- It embeds PyMuPDF (PDF reading) as bytecode rather than compiling it to C.
  PyMuPDF is public open-source code, and its generated bindings are 185 MB of C
  that take hours to compile. All Rizviz code is compiled.
