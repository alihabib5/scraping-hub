# Scraping Hub — account panel

The online side of the Windows app's sign-in. Hosted on Vercel, accounts kept in
Supabase (Postgres).

- **Dashboard** (sidebar):
  - **Users** (`/`): everyone who can sign in, with the IP, time and length of
    their latest session in the Windows app ("Active now" while it is open).
    Remove someone here.
  - **Pending Approvals** (`/pending`): accounts requested on the app's
    **Create account** screen, with the IP and date of the request; Approve or
    Decline.
  - **Encryptor** (`/encryptor`): makes the app's `credentials.shc` from a
    `.env`, the build's `credentials.key` and an optional `accounts.csv`, in the
    browser — nothing is uploaded. Byte-compatible with
    `server/app/core/credentials_file.py` (code from the Encrypter project).
- **API** (`/api/signup`, `/api/login`, `/api/session`): called by each installed app's engine
  (`server/app/core/accounts.py`). Every call must carry the app key
  (`X-Hub-Key`), so only an installed Scraping Hub can use it.

Passwords are stored as PBKDF2-SHA256 hashes (200,000 rounds) — the same scheme
as the engine, so a PC can check a remembered account while offline.

## Set up (once)

1. **Supabase.** Create a project. In **SQL Editor**, run `schema.sql`. (A database
   made from an older `schema.sql`: run `migrations/001_sessions.sql` instead — it
   adds the sign-up IP and the sessions table, and is safe to run twice.) Under
   **Connect → Connection string**, copy the *Transaction pooler* URI (port
   6543) and put the database password into it.
2. **Vercel.** New project → import this repository → **Root Directory:
   `admin`**. Add these environment variables before the first deploy:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Supabase connection string from step 1 |
   | `ADMIN_EMAILS` | who may use the panel, comma-separated: `sara@fedpoint.us,omar@fedpoint.us` |
   | `SESSION_SECRET` | a long random string (signs the admin sign-in cookie) |
   | `HUB_API_KEY` | a long random string; the apps send it to prove they are Scraping Hub |

   A random string, in PowerShell:
   `-join ((48..57)+(97..122) | Get-Random -Count 40 | % {[char]$_})`
3. **First administrator.** From this folder, with the Supabase connection
   string and a password of 8+ characters in the environment:

   ```powershell
   $env:DATABASE_URL = "<Supabase connection string>"
   $env:ADMIN_PASSWORD = "<their password>"
   npm install
   npm run add-admin -- sara@fedpoint.us "Sara Khan"
   ```

   They can now sign in to the panel, and to the Windows app. Further admins:
   list them in `ADMIN_EMAILS` (then redeploy) and either run `add-admin` for
   them or let them request an account in the app and approve it.
4. **The apps.** In `server/.env`, set `SCRAPING_HUB_ACCOUNTS_URL` to the
   deployment's address (`https://<project>.vercel.app`) and
   `SCRAPING_HUB_API_KEY` to the same value as `HUB_API_KEY`, then build a new
   credentials file (`installer/README.md`).

## Develop

`.env.local` in this folder holds the four settings above (gitignored). Then
`npm run dev` serves the panel on http://localhost:4100. `DATABASE_URL` may
point at a local Postgres; run `schema.sql` there first.

## Limits

- Removing an account takes effect on a PC the next time it is online: until
  then that PC still lets in someone who signed in there before.
- No rate limit on the sign-in endpoints yet; the app key keeps them to installed apps.
