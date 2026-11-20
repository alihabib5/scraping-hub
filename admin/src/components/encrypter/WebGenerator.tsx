"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { b64url, decodeKey, encodeKey, fernetEncrypt, generateRawKey, hasWebCrypto, importRawKey } from "@/lib/fernet";
import { ACCOUNTS_SETTING, accountsFromCsv, credentialsFromEnv, parseDotenv, shc1Encrypt } from "@/lib/shc1";

// Copied from the Encrypter project (landing/components/WebGenerator.tsx). Changes for the account panel:
// accounts.csv is optional when the .env carries the panel settings, and it takes an email column.
const MAX_BYTES = 1024 * 1024;
const PANEL_SETTINGS = ["SCRAPING_HUB_ACCOUNTS_URL", "SCRAPING_HUB_API_KEY"];
const HWID_RE = /^[0-9a-f]{64}$/i;

type Format = "license" | "hub";
type Mode = "file" | "text";
type KeyMode = "new" | "mine";
type Download = { name: string; data: string | Uint8Array; label: string };
type Result = { headline: string; preview: string; downloads: Download[]; note: string; detail?: string };

function download({ name, data }: Download) {
  const url = URL.createObjectURL(new Blob([data as BlobPart], { type: "application/octet-stream" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** File picker row in the Windows-dialog style: read-only path box plus Browse. */
function FilePick({ file, placeholder, accept, label, onPick }: {
  file: File | null;
  placeholder: string;
  accept: string;
  label: string;
  onPick: (f: File | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="win-file">
      <input className="gen-path" readOnly value={file?.name ?? ""} placeholder={placeholder} aria-label={label} onClick={() => input.current?.click()} />
      <button type="button" className="gen-browse" onClick={() => input.current?.click()}>
        Browse...
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(e: ChangeEvent<HTMLInputElement>) => onPick(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

/**
 * The .SHC Key Generator, working in the browser. Nothing is uploaded: files are read and encrypted on this page.
 * Two outputs: an Encrypter license (Fernet, for security_loader.py) or Scraping Hub's credentials.shc (SHC1).
 */
export function WebGenerator() {
  const [format, setFormat] = useState<Format>("license");
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [keyMode, setKeyMode] = useState<KeyMode>("new");
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [accountsFile, setAccountsFile] = useState<File | null>(null);
  const [hwid, setHwid] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const hub = format === "hub";

  const reset = () => {
    setError(null);
    setResult(null);
  };

  function chooseFormat(next: Format) {
    setFormat(next);
    setKeyMode(next === "hub" ? "mine" : "new");
    setKeyFile(null);
    reset();
  }

  async function readPayload(): Promise<string | null> {
    if (mode === "file") {
      if (!file || !/\.(env|txt)$/i.test(file.name)) {
        setError("Please select a valid .env or .txt file.");
        return null;
      }
      if (file.size > MAX_BYTES) {
        setError("That file is over 1 MB. A config file should be a few lines; check you picked the right one.");
        return null;
      }
      const content = await file.text();
      if (!content.trim()) {
        setError("That file is empty. Add your key=value lines and try again.");
        return null;
      }
      return content;
    }
    if (!text.trim()) {
      setError("Please enter key data in the text box.");
      return null;
    }
    return text.trim();
  }

  async function makeLicense(payload: string): Promise<Result | null> {
    const lock = hwid.trim();
    if (lock) {
      if (!HWID_RE.test(lock)) {
        setError("The machine ID should be 64 hex characters (the SHA-256 printed by get_windows_hwid()). Leave it empty to skip the lock.");
        return null;
      }
      if (/^ALLOWED_HWID=/m.test(payload)) {
        setError("Your config already has an ALLOWED_HWID line. Remove it or clear the machine ID field.");
        return null;
      }
      payload = `${payload.replace(/\s*$/, "")}\nALLOWED_HWID=${lock.toLowerCase()}\n`;
    }

    let raw: Uint8Array;
    if (keyMode === "mine") {
      if (!keyFile) {
        setError("Choose your secret.key file, or switch to “Create a new key”.");
        return null;
      }
      try {
        raw = decodeKey(await keyFile.text());
      } catch {
        setError("That isn’t a valid secret.key. It should hold one 44-character Fernet key.");
        return null;
      }
    } else {
      raw = generateRawKey();
    }

    const token = b64url(await fernetEncrypt(await importRawKey(raw), payload));
    const lines = payload.split("\n").filter((l) => l.includes("=")).length;
    const downloads: Download[] = [{ name: "license.shc", data: token, label: "Download license.shc" }];
    if (keyMode === "new") downloads.push({ name: "secret.key", data: encodeKey(raw), label: "Download secret.key" });
    return {
      headline: `license.shc ready: ${lines} ${lines === 1 ? "setting" : "settings"}, ${token.length} bytes`,
      preview: token,
      downloads,
      note:
        keyMode === "new"
          ? "Save secret.key now. It was made on this page and isn’t stored anywhere, so it can’t be recovered. Your bot needs it to open the license."
          : "Encrypted with your existing key, so bots already using that secret.key can open this license.",
    };
  }

  async function makeHubCredentials(payload: string): Promise<Result | null> {
    const { values, skipped } = credentialsFromEnv(parseDotenv(payload));
    if (!Object.keys(values).length) {
      setError("No credentials found in that config. Each line should look like EMMA_PASSWORD=…");
      return null;
    }
    const missingPanel = PANEL_SETTINGS.filter((k) => !values[k]);
    if (!accountsFile && missingPanel.length) {
      setError(
        `Nobody could sign in with this file: it has no ${missingPanel.join(" or ")} for the account panel, and no accounts.csv. ` +
          "Add the panel settings to the config, or choose accounts.csv (email,name,password).",
      );
      return null;
    }

    let raw: Uint8Array;
    if (keyMode === "mine") {
      if (!keyFile) {
        setError("Choose the build’s credentials.key, or switch to “Create a new key” for a new build.");
        return null;
      }
      raw = new Uint8Array(await keyFile.arrayBuffer());
      if (raw.length !== 32) {
        setError(`That credentials.key is damaged (expected 32 bytes, found ${raw.length}).`);
        return null;
      }
    } else {
      raw = crypto.getRandomValues(new Uint8Array(32));
    }

    let accounts: Record<string, unknown> = {};
    if (accountsFile) {
      try {
        accounts = await accountsFromCsv(await accountsFile.text());
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "accounts.csv could not be read.");
        return null;
      }
    }
    const settings = Object.keys(values).sort();
    const packed = accountsFile ? { ...values, [ACCOUNTS_SETTING]: JSON.stringify(accounts) } : values;
    const data = await shc1Encrypt(packed, raw);
    const people = Object.keys(accounts).sort();

    const downloads: Download[] = [{ name: "credentials.shc", data, label: "Download credentials.shc" }];
    if (keyMode === "new") downloads.push({ name: "credentials.key", data: raw, label: "Download credentials.key" });
    return {
      headline: accountsFile
        ? `credentials.shc ready: ${settings.length + 1} settings, ${people.length} employee ${people.length === 1 ? "sign-in" : "sign-ins"}`
        : `credentials.shc ready: ${settings.length} settings; sign-in through the account panel`,
      preview: `SHC1 · ${data.length} bytes`,
      detail: `Settings: ${settings.join(", ")}.${people.length ? ` Sign-ins: ${people.join(", ")}.` : ""}${skipped.length ? ` Left out (set per PC by the installer): ${skipped.join(", ")}.` : ""}`,
      downloads,
      note:
        keyMode === "new"
          ? "This key is new, so only a build compiled with it can open this file. Put credentials.key in installer\\ and rebuild before handing out the setup."
          : "The setup wizard asks for this file on each PC. It opens only in builds made with this credentials.key.",
    };
  }

  async function generate() {
    reset();
    if (!hasWebCrypto()) {
      setError("This browser can’t encrypt here. Open the page over https, or use the desktop generator.");
      return;
    }
    const payload = await readPayload();
    if (payload === null) return;
    setBusy(true);
    try {
      const made = hub ? await makeHubCredentials(payload) : await makeLicense(payload);
      if (made) setResult(made);
    } catch (exc) {
      setError(`Failed to generate .shc file: ${exc instanceof Error ? exc.message : "unknown error"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="win gen" role="group" aria-labelledby="gen-title">
      <div className="win-title">
        <span id="gen-title">.SHC Key Generator Tool</span>
        <span className="win-tag">Runs in your browser</span>
      </div>

      <div className="win-body">
        <div className="gen-format" role="radiogroup" aria-label="What to make">
          <button type="button" role="radio" aria-checked={!hub} className={!hub ? "on" : ""} onClick={() => chooseFormat("license")}>
            Bot license
            <small>license.shc for security_loader.py</small>
          </button>
          <button type="button" role="radio" aria-checked={hub} className={hub ? "on" : ""} onClick={() => chooseFormat("hub")}>
            Scraping Hub
            <small>credentials.shc for the Windows app</small>
          </button>
        </div>

        <label className="gen-radio">
          <input type="radio" name="gen-mode" checked={mode === "file"} onChange={() => setMode("file")} />
          Option 1: Upload .env / .txt File
        </label>
        <FilePick
          file={file}
          placeholder="No file chosen"
          accept=".env,.txt,text/plain"
          label="Chosen file"
          onPick={(f) => {
            setFile(f);
            setMode("file");
            reset();
          }}
        />

        <label className="gen-radio">
          <input type="radio" name="gen-mode" checked={mode === "text"} onChange={() => setMode("text")} />
          Option 2: Paste Input Text
        </label>
        <textarea
          className="gen-text"
          rows={5}
          spellCheck={false}
          autoComplete="off"
          placeholder={hub ? "EMMA_USERNAME=…\nEMMA_PASSWORD=…\nBIDNET_USERNAME=…" : "BOT_USER=admin\nBOT_PASS=Secret123!\nPROXY=192.168.1.1:8080"}
          aria-label="Configuration lines"
          value={text}
          onFocus={() => setMode("text")}
          onChange={(e) => {
            setText(e.target.value);
            setResult(null);
          }}
        />

        {hub && (
          <fieldset className="gen-key">
            <legend>Employee sign-ins (optional with the account panel)</legend>
            <FilePick
              file={accountsFile}
              placeholder="Choose accounts.csv (email,name,password)"
              accept=".csv,text/csv"
              label="Chosen accounts file"
              onPick={(f) => {
                setAccountsFile(f);
                reset();
              }}
            />
          </fieldset>
        )}

        <fieldset className="gen-key">
          <legend>Encryption key</legend>
          {hub ? (
            <>
              <label className="gen-radio">
                <input type="radio" name="gen-key" checked={keyMode === "mine"} onChange={() => setKeyMode("mine")} />
                Use the build’s credentials.key
              </label>
              <label className="gen-radio">
                <input type="radio" name="gen-key" checked={keyMode === "new"} onChange={() => setKeyMode("new")} />
                Create a new key (for a new build)
              </label>
            </>
          ) : (
            <>
              <label className="gen-radio">
                <input type="radio" name="gen-key" checked={keyMode === "new"} onChange={() => setKeyMode("new")} />
                Create a new key
              </label>
              <label className="gen-radio">
                <input type="radio" name="gen-key" checked={keyMode === "mine"} onChange={() => setKeyMode("mine")} />
                Use my secret.key
              </label>
            </>
          )}
          {keyMode === "mine" && (
            <FilePick
              file={keyFile}
              placeholder={hub ? "Choose installer\\credentials.key" : "Choose secret.key"}
              accept={hub ? ".key" : ".key,text/plain"}
              label="Chosen key file"
              onPick={(f) => {
                setKeyFile(f);
                setResult(null);
              }}
            />
          )}
        </fieldset>

        {!hub && (
          <label className="gen-field">
            <span>Lock to one machine (optional)</span>
            <input
              className="gen-path mono"
              value={hwid}
              onChange={(e) => setHwid(e.target.value)}
              placeholder="64-character machine ID"
              spellCheck={false}
              autoComplete="off"
            />
          </label>
        )}

        {error && (
          <p className="gen-error" role="alert">
            {error}
          </p>
        )}

        <button type="button" className="win-gen" onClick={generate} disabled={busy}>
          {busy ? "Encrypting…" : hub ? "Generate credentials.shc" : "Generate .shc Key"}
        </button>

        {result && (
          <div className="gen-result" role="status">
            <p className="gen-result-head">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>{" "}
              {result.headline}
            </p>
            <code className="gen-token">{result.preview.length > 64 ? `${result.preview.slice(0, 64)}…` : result.preview}</code>
            {result.detail && <p className="gen-note">{result.detail}</p>}
            <div className="gen-downloads">
              {result.downloads.map((d) => (
                <button key={d.name} type="button" className="gen-dl" onClick={() => download(d)}>
                  {d.label}
                </button>
              ))}
            </div>
            <p className="gen-note">{result.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}
