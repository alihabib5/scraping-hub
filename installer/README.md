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

1. `installer\output\ScrapingHub-Setup-<version>.exe` (currently 1.0.2)
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

### Sign-in alerts

Every successful sign-in on any PC sends an email to the addresses in
`SIGNIN_ALERT_EMAILS` (comma-separated, in `server/.env`, packed into the `.shc`).
It lists the name and email, the time (that PC's local time and UTC), the public IP
(as the account panel saw it), the local IP, the computer name, the Windows user,
the Windows version, the app version, and how the sign-in was checked: the account
panel, the PC's remembered accounts while offline, or an issued account.

- It goes through the same mail server as the run emails: **Gmail** (`SMTP_*`
  in `server/.env`; free, about 500 emails a day), or AWS SES (`AWS_SES_*`) when
  `SMTP_HOST` is blank.
- Gmail setup: turn on 2-Step Verification on the sending Google account, then
  go to *Google Account → Security → App passwords* and create one. Put the Gmail
  address in `SMTP_USERNAME` and the 16-letter app password in `SMTP_PASSWORD`.
  The normal Gmail password does not work here. Changing the Google password
  cancels the app password, so make a new one and send out a new `.shc`.
- It is sent in the background: a slow or failed email never delays a sign-in.
- An offline sign-in has no public IP, and is emailed only if the PC can still
  reach SES. If it can't, the sign-in is still recorded in `server.log`.
- Wrong passwords send nothing.

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
- **Never hand out `credentials.key`, `server\.env` or this repo.** The team gets
  only the setup `.exe` and the `.shc`. `stage.py` refuses to ship any `.key`,
  `.env` or `.shc`.
- **Locked to each PC.** The `.shc` the wizard copies into
  `C:\ProgramData\Scraping Hub\` (never Program Files) is rewritten the first
  time the app opens it: the same file wrapped with Windows DPAPI in machine
  scope, with the app key as extra entropy (`SHM1` instead of `SHC1`). It opens
  only on that PC and only with this build. Copying ProgramData to another
  computer gets nothing usable. The setup wizard's final check does this, so
  the locking happens during the install.
- The portable `.shc` you send out still opens with any install of this build,
  so treat it like a password. Send it privately, not in a shared folder or a
  group chat.
- The limit: because the key ships inside the app, encryption stops anyone
  reading the passwords off the disk or carrying them to another PC, but not a
  determined reverse-engineer working on a PC where it is installed.

## Updating the PCs

1. Raise `AppVersion` in `ScrapingHub.iss` (and `version` in `desktop\package.json`).
2. Build again and run the new setup on each PC. It upgrades in place and keeps
   the database, results and credentials. Leave the credentials page empty to
   keep the current file.

Never change the `AppId` in `ScrapingHub.iss`. It is how a new setup recognises
an existing install.

## System requirements

| | Minimum | Recommended |
| --- | --- | --- |
| Windows | Windows 10 (22H2), 64-bit | Windows 11, 64-bit |
| Processor | x64, 4 cores (Intel Core i3 8th gen / AMD Ryzen 3 or newer) | x64, 6+ cores (Intel Core i5 10th gen / AMD Ryzen 5 or newer) |
| Memory (RAM) | 8 GB | 16 GB |
| Free disk space | 10 GB (the app is about 1 GB; the rest is for the database and downloaded bid documents) | 50 GB on an SSD |
| Screen | 1366 × 768 | 1920 × 1080 |
| Internet | Stable broadband | Wired or strong Wi-Fi, 20 Mbps or more |
| Other | An admin account once, to install. Google Chrome: the setup installs it if missing (needs internet during setup) | Same, and the PC left awake during long runs |

Not supported: ARM laptops (Snapdragon "Copilot+" PCs; the wizard warns),
32-bit Windows, Windows 7/8, macOS.

Why these numbers: each portal run drives its own Chrome, and the big sweeps
(EUNA BONFIRE, MyFlorida) visit 100+ agencies in one session. Below 8 GB, Chrome
runs out of memory on those, which is how the RideMetro "inconsistent counts"
showed up. More cores and RAM let several portals run at once.

## What the person installing sees

1. Run the setup, accept, and choose the `.shc` credentials file.
2. **No Chrome on the PC?** After *Install* is clicked, the wizard downloads
   Google's own business installer for Chrome (64-bit MSI, about 170 MB, from
   `dl.google.com`) with a progress bar, then installs it silently for every
   user. Chrome keeps itself updated after that. The setup does not carry
   Chrome, so it stays small and always gets the current version. Without
   internet the install carries on, and at the end it asks for Chrome to be
   installed.
3. The wizard installs the app, prepares the database (retrying once on its
   own), then checks that everything works.
4. Open **Scraping Hub** from the desktop and sign in. If Chrome is still
   missing (for example, someone uninstalled it), the app says so at start-up
   with a **Get Chrome** button, before any run can fail.

Nobody is ever asked to find a log. When something fails, the wizard or the app
puts **`Scraping Hub support.zip`** on the Desktop (the app's error box has a
**Save support file** button), and the person sends that one file to Rizviz
support. `server.log` starts over past 5 MB, keeping one previous file.

## Troubleshooting

### A new PC fails to install or the engine stops

Ask for the `Scraping Hub support.zip` from the PC's Desktop. It holds the
whole `logs` folder:

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
