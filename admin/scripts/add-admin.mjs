// Create (or reset) an approved account, so the first administrator can sign in to the panel.
//
//   set DATABASE_URL=<Supabase connection string>
//   set ADMIN_PASSWORD=<their password>
//   npm run add-admin -- sara@fedpoint.us "Sara Khan"
//
// Also add the email to ADMIN_EMAILS in Vercel. The password is read from the
// environment, never the command line, so it does not land in shell history.
import { pbkdf2Sync, randomBytes } from "node:crypto";

import postgres from "postgres";

const [email, name] = [process.argv[2]?.trim().toLowerCase(), process.argv[3]?.trim()];
const password = process.env.ADMIN_PASSWORD ?? "";
if (!email || !name || !process.env.DATABASE_URL) {
  console.error('Usage: npm run add-admin -- <email> "<name>"   (with DATABASE_URL and ADMIN_PASSWORD set)');
  process.exit(1);
}
if (password.length < 8) {
  console.error("ADMIN_PASSWORD must be at least 8 characters.");
  process.exit(1);
}

const salt = randomBytes(16).toString("hex");
const hash = pbkdf2Sync(password, Buffer.from(salt, "hex"), 200_000, 32, "sha256").toString("hex"); // as src/lib/passwords.ts
const local = /@(localhost|127\.0\.0\.1)[:/]/.test(process.env.DATABASE_URL);
const sql = postgres(process.env.DATABASE_URL, { ssl: local ? false : "require", prepare: false });
await sql`
  insert into hub_accounts (email, name, salt, hash, status, decided_by, decided_at)
  values (${email}, ${name}, ${salt}, ${hash}, 'approved', 'add-admin', now())
  on conflict (email) do update set name = excluded.name, salt = excluded.salt, hash = excluded.hash,
    status = 'approved', decided_by = 'add-admin', decided_at = now()`;
await sql.end();
console.log(`${email} can sign in. Make sure it is listed in ADMIN_EMAILS.`);
