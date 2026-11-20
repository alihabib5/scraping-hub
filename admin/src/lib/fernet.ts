// Copied from the Encrypter project (landing/lib/fernet.ts): the bot license format, Fernet in WebCrypto.
// Fernet in the browser via WebCrypto, byte-compatible with Python's cryptography.Fernet:
// 0x80 | timestamp (8, big-endian) | IV (16) | AES-128-CBC ciphertext (PKCS7) | HMAC-SHA256 (32)

export type FernetKey = { sign: CryptoKey; aes: CryptoKey };

const enc = new TextEncoder();
const dec = new TextDecoder();

export const SAMPLE_ENV =
  "BOT_USER=agent_rivera\nBOT_PASS=Sunset-4417!\nTARGET_URL=https://portal.example.com/login\nPROXY=10.0.4.12:3128\nHEADLESS=true\n";
export const THIS_PC = "4C4C4544-0042-3510-8051-B4C04F4E3732";
export const OTHER_PC = "03000200-0400-0500-0006-000700080009";

export const hasWebCrypto = (): boolean =>
  typeof window !== "undefined" && !!window.crypto?.subtle;

export function b64url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_");
}

export async function sha256hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** 32 random bytes: first 16 sign (HMAC), last 16 encrypt (AES), as in cryptography.Fernet. */
export const generateRawKey = (): Uint8Array => crypto.getRandomValues(new Uint8Array(32));

export async function importRawKey(raw: Uint8Array): Promise<FernetKey> {
  return {
    sign: await crypto.subtle.importKey("raw", raw.slice(0, 16), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]),
    aes: await crypto.subtle.importKey("raw", raw.slice(16), { name: "AES-CBC" }, false, ["encrypt", "decrypt"]),
  };
}

export const newKey = async (): Promise<FernetKey> => importRawKey(generateRawKey());

/** The secret.key file format: URL-safe base64 of the 32 raw bytes, padded (44 chars), like Fernet.generate_key(). */
export const encodeKey = (raw: Uint8Array): string => b64url(raw);

/** Parse a secret.key file's contents; throws when it is not a 32-byte URL-safe base64 Fernet key. */
export function decodeKey(text: string): Uint8Array {
  const clean = text.trim();
  if (!/^[A-Za-z0-9_-]{43}=?$/.test(clean)) throw new Error("Not a Fernet key");
  const padded = clean.length === 43 ? clean + "=" : clean;
  const bin = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const raw = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("Not a Fernet key");
  return raw;
}

export async function fernetEncrypt(key: FernetKey, text: string): Promise<Uint8Array> {
  const iv = crypto.getRandomValues(new Uint8Array(16));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-CBC", iv }, key.aes, enc.encode(text)));
  const body = new Uint8Array(25 + ct.length);
  body[0] = 0x80;
  new DataView(body.buffer).setBigUint64(1, BigInt(Math.floor(Date.now() / 1000)));
  body.set(iv, 9);
  body.set(ct, 25);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key.sign, body));
  const token = new Uint8Array(body.length + 32);
  token.set(body);
  token.set(mac, body.length);
  return token;
}

export async function fernetDecrypt(key: FernetKey, token: Uint8Array): Promise<string> {
  const body = token.slice(0, -32);
  const mac = token.slice(-32);
  if (token[0] !== 0x80 || !(await crypto.subtle.verify("HMAC", key.sign, mac, body))) {
    throw new Error("InvalidToken");
  }
  const pt = await crypto.subtle.decrypt({ name: "AES-CBC", iv: body.slice(9, 25) }, key.aes, body.slice(25));
  return dec.decode(pt);
}

export function parseEnv(text: string): Record<string, string> {
  return Object.fromEntries(
    text
      .split("\n")
      .filter((line) => line.includes("="))
      .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
  );
}

export const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
