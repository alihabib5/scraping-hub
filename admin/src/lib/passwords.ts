import { pbkdf2Sync, randomBytes, timingSafeEqual } from "node:crypto";

// The engine's own scheme (server/app/core/accounts.py), so a PC can check a cached account offline.
const ROUNDS = 200_000;

export function hashPassword(password: string, salt = randomBytes(16).toString("hex")) {
  const hash = pbkdf2Sync(password, Buffer.from(salt, "hex"), ROUNDS, 32, "sha256").toString("hex");
  return { salt, hash };
}

export function passwordMatches(password: string, salt: string, hash: string): boolean {
  const attempt = Buffer.from(hashPassword(password, salt).hash, "hex");
  const stored = Buffer.from(hash, "hex");
  return attempt.length === stored.length && timingSafeEqual(attempt, stored);
}
