import { createHmac, timingSafeEqual } from "node:crypto";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { adminEmails, env } from "@/lib/env";

const COOKIE = "hub_admin";
const HOURS = 8;

function sign(value: string): string {
  return createHmac("sha256", env("SESSION_SECRET")).update(value).digest("hex");
}

export async function startSession(email: string) {
  const value = `${email}|${Date.now() + HOURS * 3_600_000}`;
  (await cookies()).set(COOKIE, `${value}|${sign(value)}`, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: HOURS * 3600,
  });
}

export async function endSession() {
  (await cookies()).delete(COOKIE);
}

/** The signed-in admin's email, or null. Re-checks ADMIN_EMAILS, so removing someone there ends their session. */
export async function currentAdmin(): Promise<string | null> {
  const raw = (await cookies()).get(COOKIE)?.value ?? "";
  const cut = raw.lastIndexOf("|");
  if (cut < 0) return null;
  const value = raw.slice(0, cut);
  const given = Buffer.from(raw.slice(cut + 1), "hex");
  const expected = Buffer.from(sign(value), "hex");
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;
  const [email, expires] = value.split("|");
  return Number(expires) > Date.now() && adminEmails().has(email) ? email : null;
}

/** For pages and actions: the admin, or off to the sign-in page. */
export async function requireAdmin(): Promise<string> {
  const admin = await currentAdmin();
  if (!admin) redirect("/login");
  return admin;
}
