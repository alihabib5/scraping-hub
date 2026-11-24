import { sql } from "@/lib/db";
import { hashPassword, passwordMatches } from "@/lib/passwords";

export const MIN_PASSWORD = 8; // as the engine and installer/make_credentials.py require
const EMAIL = /^[a-z0-9._%+-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export interface PendingAccount {
  email: string;
  name: string;
  requested_at: Date;
  requested_ip: string | null;
}

/** An approved account with its latest session in the Windows app, if any. */
export interface User {
  email: string;
  name: string;
  decided_at: Date | null;
  ip: string | null;
  started_at: Date | null;
  last_seen_at: Date | null;
  ended_at: Date | null;
}

export class Refused extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const normalEmail = (email: unknown) => String(email ?? "").trim().toLowerCase();

/** The caller's public address as Vercel saw it (the first hop of x-forwarded-for). */
export function clientIp(request: Request): string | null {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || request.headers.get("x-real-ip") || null;
}

/** A new sign-up, pending until an admin approves it. */
export async function requestAccount(name: unknown, email: unknown, password: unknown, ip: string | null): Promise<string> {
  const display = String(name ?? "").split(/\s+/).filter(Boolean).join(" ");
  const key = normalEmail(email);
  const secret = String(password ?? "");
  if (display.length < 2 || display.length > 60) throw new Refused(422, "Enter a display name of 2 to 60 characters.");
  if (!EMAIL.test(key)) throw new Refused(422, "Enter a valid email address.");
  if (secret.length < MIN_PASSWORD) throw new Refused(422, `Use a password of at least ${MIN_PASSWORD} characters.`);
  const { salt, hash } = hashPassword(secret);
  const made = await sql`
    insert into hub_accounts (email, name, salt, hash, requested_ip) values (${key}, ${display}, ${salt}, ${hash}, ${ip})
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

/** A sign-in in the Windows app: its session id, for the app's check-ins and sign-out. */
export async function startSession(email: string, ip: string | null): Promise<string> {
  const [row] = await sql<{ id: string }[]>`insert into hub_sessions (email, ip) values (${normalEmail(email)}, ${ip}) returning id`;
  return row.id;
}

/** The app checking in ("ping") or signing out / closing ("end"). An unknown or ended session is ignored. */
export async function touchSession(id: unknown, end: boolean): Promise<boolean> {
  const key = String(id ?? "").toLowerCase();
  if (!UUID.test(key)) return false;
  const done = end
    ? await sql`update hub_sessions set last_seen_at = now(), ended_at = now() where id = ${key} and ended_at is null returning id`
    : await sql`update hub_sessions set last_seen_at = now() where id = ${key} and ended_at is null returning id`;
  return done.length > 0;
}

export function listPending() {
  return sql<PendingAccount[]>`
    select email, name, requested_at, requested_ip from hub_accounts
    where status = 'pending' order by requested_at desc`;
}

export function countPending() {
  return sql<{ n: number }[]>`select count(*)::int as n from hub_accounts where status = 'pending'`.then((r) => r[0].n);
}

export function listUsers() {
  return sql<User[]>`
    select a.email, a.name, a.decided_at, s.ip, s.started_at, s.last_seen_at, s.ended_at
    from hub_accounts a
    left join lateral (
      select ip, started_at, last_seen_at, ended_at from hub_sessions
      where email = a.email order by started_at desc limit 1
    ) s on true
    where a.status = 'approved'
    order by s.started_at desc nulls last, a.name`;
}

export async function approve(email: string, admin: string) {
  await sql`update hub_accounts set status = 'approved', decided_by = ${admin}, decided_at = now()
            where email = ${normalEmail(email)} and status = 'pending'`;
}

/** Decline a request or remove an account; either way the email may ask again. Its sessions go with it. */
export async function remove(email: string) {
  await sql`delete from hub_accounts where email = ${normalEmail(email)}`;
}

export async function accountName(email: string): Promise<string> {
  const [row] = await sql<{ name: string }[]>`select name from hub_accounts where email = ${normalEmail(email)}`;
  return row?.name ?? email;
}

/** One sign-in in the Windows app, with who it was. */
export interface SessionRow {
  id: string;
  email: string;
  name: string;
  ip: string | null;
  started_at: Date;
  last_seen_at: Date;
  ended_at: Date | null;
}

export const SESSIONS_PER_PAGE = 50;

/** Every session, newest first; `email` narrows it to one person. A removed account's sessions go with it. */
export function listSessions(email: string | null, page: number) {
  const who = email ? normalEmail(email) : null;
  return sql<SessionRow[]>`
    select s.id, s.email, a.name, s.ip, s.started_at, s.last_seen_at, s.ended_at
    from hub_sessions s join hub_accounts a on a.email = s.email
    where (${who}::text is null or s.email = ${who})
    order by s.started_at desc
    limit ${SESSIONS_PER_PAGE + 1} offset ${Math.max(0, page - 1) * SESSIONS_PER_PAGE}`;
}

/** Totals for the page's status line: all sessions, and those started in the last 7 days. */
export function sessionCounts(email: string | null) {
  const who = email ? normalEmail(email) : null;
  return sql<{ total: number; week: number }[]>`
    select count(*)::int as total, count(*) filter (where started_at > now() - interval '7 days')::int as week
    from hub_sessions where (${who}::text is null or email = ${who})`.then((r) => r[0]);
}
