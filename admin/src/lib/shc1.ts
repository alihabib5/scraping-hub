// Scraping Hub's credentials file ("SHC1"), byte-compatible with
// (copied from the Encrypter project's landing/lib/shc1.ts; accounts.csv now takes email too)
// scraping-hub/server/app/core/credentials_file.py and installer/make_credentials.py:
// "SHC1" | nonce (16) | HMAC-SHA256 tag (32) | JSON body XOR HMAC-SHA256 keystream.

const enc = new TextEncoder();
const MAGIC = enc.encode("SHC1");

/** Per-machine settings the installer writes on each PC; never packed into the credentials file. */
export const NOT_INCLUDED = new Set([
  "DATABASE_URL",
  "DOWNLOAD_DIR",
  "ARCHIVE_DIR",
  "WORK_DIR",
  "NORTHDAKOTA_PROFILE_DIR",
  "PUBLIC_BASE_URL",
]);
export const ACCOUNTS_SETTING = "SCRAPING_HUB_ACCOUNTS";
// As server/app/core/accounts.py: an email, or a pre-email username.
const USERNAME = /^(?:[a-z0-9._-]{2,32}|[a-z0-9._%+-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})$/;
const PBKDF2_ROUNDS = 200_000;

const hex = (bytes: Uint8Array) => [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (h: string) => Uint8Array.from(h.match(/../g) ?? [], (x) => parseInt(x, 16));

/** KEY=VALUE lines the way python-dotenv's dotenv_values reads them (comments, `export`, quotes). */
export function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of text.replace(/^﻿/, "").split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice(7).trim();
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    const q = value[0];
    if ((q === '"' || q === "'") && value.lastIndexOf(q) > 0) {
      value = value.slice(1, value.lastIndexOf(q));
      if (q === '"') value = value.replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\\\/g, "\\");
    } else {
      value = value.replace(/\s+#.*$/, "").trim();
    }
    out[key] = value;
  }
  return out;
}

/** Settings make_credentials.py would pack: every non-empty key except the per-machine ones. */
export function credentialsFromEnv(env: Record<string, string>): { values: Record<string, string>; skipped: string[] } {
  const values: Record<string, string> = {};
  const skipped: string[] = [];
  for (const [k, v] of Object.entries(env)) {
    if (!v) continue;
    if (NOT_INCLUDED.has(k.toUpperCase())) skipped.push(k);
    else values[k] = v;
  }
  return { values, skipped };
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const src = text.replace(/^﻿/, "");
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"' && src[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim()));
}

async function hashPassword(password: string): Promise<{ salt: string; hash: string }> {
  const salt = hex(crypto.getRandomValues(new Uint8Array(16)));
  const base = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: fromHex(salt), iterations: PBKDF2_ROUNDS },
    base,
    256,
  );
  return { salt, hash: hex(new Uint8Array(bits)) };
}

/** Employee sign-ins from accounts.csv (email,name,password — or the older username column), hashed like accounts_from_csv(). */
export async function accountsFromCsv(text: string): Promise<Record<string, { name: string; salt: string; hash: string }>> {
  const [header, ...rows] = parseCsv(text);
  if (!header) throw new Error("accounts.csv is empty. It needs a header row: email,name,password");
  const col = (n: string) => header.findIndex((h) => h.trim().toLowerCase() === n);
  const iu = col("email") >= 0 ? col("email") : col("username");
  const [iname, ipw] = [col("name"), col("password")];
  if (iu < 0 || iname < 0 || ipw < 0) throw new Error("accounts.csv needs the columns email,name,password");
  const accounts: Record<string, { name: string; salt: string; hash: string }> = {};
  for (const [n, row] of rows.entries()) {
    const line = n + 2;
    const username = (row[iu] ?? "").trim().toLowerCase();
    const name = (row[iname] ?? "").trim();
    const password = row[ipw] ?? "";
    if (!USERNAME.test(username)) throw new Error(`accounts.csv line ${line}: needs an email address (or a username of 2-32 a-z 0-9 . _ -)`);
    if (username in accounts) throw new Error(`accounts.csv line ${line}: ${username} appears twice`);
    if (!name || password.length < 8) throw new Error(`accounts.csv line ${line}: needs a name and a password of 8+ characters`);
    accounts[username] = { name, ...(await hashPassword(password)) };
  }
  if (!Object.keys(accounts).length) throw new Error("accounts.csv has no sign-ins, so nobody could sign in to the app");
  return accounts;
}

async function hmacKey(raw: Uint8Array) {
  return crypto.subtle.importKey("raw", new Uint8Array(raw), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

export async function shc1Encrypt(values: Record<string, string>, rawKey: Uint8Array): Promise<Uint8Array> {
  if (rawKey.length !== 32) throw new Error("credentials.key must be exactly 32 bytes");
  const key = await hmacKey(rawKey);
  const nonce = crypto.getRandomValues(new Uint8Array(16));
  const plain = enc.encode(JSON.stringify(values));

  const body = new Uint8Array(plain.length);
  for (let counter = 0, off = 0; off < plain.length; counter++, off += 32) {
    const block = new Uint8Array(24);
    block.set(nonce);
    new DataView(block.buffer).setBigUint64(16, BigInt(counter));
    const ks = new Uint8Array(await crypto.subtle.sign("HMAC", key, block));
    for (let i = 0; i < 32 && off + i < plain.length; i++) body[off + i] = plain[off + i] ^ ks[i];
  }

  const signed = new Uint8Array(4 + 16 + body.length);
  signed.set(MAGIC);
  signed.set(nonce, 4);
  signed.set(body, 20);
  const tag = new Uint8Array(await crypto.subtle.sign("HMAC", key, signed));

  const out = new Uint8Array(52 + body.length);
  out.set(MAGIC);
  out.set(nonce, 4);
  out.set(tag, 20);
  out.set(body, 52);
  return out;
}
