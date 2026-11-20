import { sql } from "@/lib/db";
import { hashPassword, passwordMatches } from "@/lib/passwords";

export const MIN_PASSWORD = 8; // as the engine and installer/make_credentials.py require
const EMAIL = /^[a-z0-9._%+-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$/;

export interface Account {
  email: string;
  name: string;
  status: "pending" | "approved";
  requested_at: Date;
  decided_by: string | null;
  decided_at: Date | null;
}

export class Refused extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const normalEmail = (email: unknown) => String(email ?? "").trim().toLowerCase();

/** A new sign-up, pending until an admin approves it. */
export async function requestAccount(name: unknown, email: unknown, password: unknown): Promise<string> {
  const display = String(name ?? "").split(/\s+/).filter(Boolean).join(" ");
  const key = normalEmail(email);
  const secret = String(password ?? "");
  if (display.length < 2 || display.length > 60) throw new Refused(422, "Enter a display name of 2 to 60 characters.");
  if (!EMAIL.test(key)) throw new Refused(422, "Enter a valid email address.");
  if (secret.length < MIN_PASSWORD) throw new Refused(422, `Use a password of at least ${MIN_PASSWORD} characters.`);
  const { salt, hash } = hashPassword(secret);
  const made = await sql`
    insert into hub_accounts (email, name, salt, hash) values (${key}, ${display}, ${salt}, ${hash})
    on conflict (email) do nothing returning email`;
  if (made.length === 0) throw new Refused(409, "An account with this email already exists or is waiting for approval.");
  return key;
}

/** "approved" with the name, "pending" (right password, not yet approved), or null. */
export async function checkSignIn(email: unknown, password: unknown) {
  const [row] = await sql<{ name: string; salt: string; hash: string; status: string }[]>`
    select name, salt, hash, status from hub_accounts where email = ${normalEmail(email)}`;
  if (!row || !passwordMatches(String(password ?? ""), row.salt, row.hash)) return null;
  return row.status === "approved" ? { status: "approved" as const, name: row.name } : { status: "pending" as const };
}

export function listAccounts() {
  return sql<Account[]>`
    select email, name, status, requested_at, decided_by, decided_at from hub_accounts
    order by status desc, requested_at desc`;
}

export async function approve(email: string, admin: string) {
  await sql`update hub_accounts set status = 'approved', decided_by = ${admin}, decided_at = now()
            where email = ${normalEmail(email)} and status = 'pending'`;
}

/** Reject a request or remove an account; either way the email may ask again. */
export async function remove(email: string) {
  await sql`delete from hub_accounts where email = ${normalEmail(email)}`;
}
