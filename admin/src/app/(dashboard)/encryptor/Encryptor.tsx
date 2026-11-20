"use client";

import { useState } from "react";

import { ACCOUNTS_SETTING, accountsFromCsv, credentialsFromEnv, parseDotenv, shc1Encrypt } from "@/lib/shc1";

const PANEL_SETTINGS = ["SCRAPING_HUB_ACCOUNTS_URL", "SCRAPING_HUB_API_KEY"];

interface EnvFile {
  name: string;
  values: Record<string, string>;
  skipped: string[];
}

function FilePick({ id, label, hint, accept, file, onPick }: {
  id: string;
  label: string;
  hint: string;
  accept: string;
  file: string | null;
  onPick: (f: File) => void;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-ink-100 px-5 py-5 sm:flex-row sm:items-center sm:gap-6">
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="text-sm font-semibold text-ink-900">{label}</label>
        <p className="mt-0.5 text-sm text-ink-500">{hint}</p>
      </div>
      <div className="flex items-center gap-3">
        {file && <span className="max-w-[14rem] truncate text-sm text-ink-600" title={file}>{file}</span>}
        <label className="cursor-pointer rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-sm font-semibold text-ink-800 transition hover:border-ink-300 hover:bg-ink-50 focus-within:ring-2 focus-within:ring-gold-500">
          {file ? "Change" : "Choose file"}
          <input
            id={id}
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onPick(f);
              e.target.value = ""; // the same file can be picked again after an edit
            }}
          />
        </label>
      </div>
    </div>
  );
}

/** Makes the installed app's credentials.shc in this browser: nothing is uploaded anywhere. */
export default function Encryptor() {
  const [env, setEnv] = useState<EnvFile | null>(null);
  const [key, setKey] = useState<{ name: string; bytes: Uint8Array } | null>(null);
  const [csv, setCsv] = useState<{ name: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const missingPanel = env ? PANEL_SETTINGS.filter((k) => !env.values[k]) : [];

  const pickEnv = async (f: File) => {
    setError(null);
    setMade(null);
    const { values, skipped } = credentialsFromEnv(parseDotenv(await f.text()));
    if (!Object.keys(values).length) {
      setEnv(null);
      setError(`${f.name} has no settings to pack. Choose the server's .env file.`);
      return;
    }
    setEnv({ name: f.name, values, skipped });
  };

  const pickKey = async (f: File) => {
    setError(null);
    setMade(null);
    const bytes = new Uint8Array(await f.arrayBuffer());
    if (bytes.length !== 32) {
      setKey(null);
      setError(`${f.name} is not a credentials key (it must be exactly 32 bytes; this one is ${bytes.length}).`);
      return;
    }
    setKey({ name: f.name, bytes });
  };

  const generate = async () => {
    if (!env || !key) return;
    setBusy(true);
    setError(null);
    setMade(null);
    try {
      const values = { ...env.values };
      if (csv) values[ACCOUNTS_SETTING] = JSON.stringify(await accountsFromCsv(csv.text));
      else if (missingPanel.length) {
        throw new Error(
          "Nobody could sign in with this file: it has no account panel settings and no accounts.csv. " +
            `Add ${missingPanel.join(" and ")} to the .env, or choose an accounts.csv.`,
        );
      }
      const data = await shc1Encrypt(values, key.bytes);
      const url = URL.createObjectURL(new Blob([new Uint8Array(data)], { type: "application/octet-stream" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "credentials.shc";
      a.click();
      URL.revokeObjectURL(url);
      setMade(`credentials.shc downloaded: ${Object.keys(values).length} settings${csv ? ", including the accounts from " + csv.name : ""}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-8 max-w-3xl">
      <div className="overflow-hidden rounded-xl border border-ink-100 bg-white">
        <FilePick
          id="env"
          label="1. Settings (.env)"
          hint="The server's .env with the portal logins. Per-PC settings such as DATABASE_URL are left out, as the installer sets those."
          accept=".env,.txt,text/plain"
          file={env?.name ?? null}
          onPick={pickEnv}
        />
        <FilePick
          id="key"
          label="2. Build key (credentials.key)"
          hint="installer\credentials.key from the build the team installed. A file made with any other key will not open."
          accept=".key,application/octet-stream"
          file={key?.name ?? null}
          onPick={pickKey}
        />
        <FilePick
          id="csv"
          label="3. Accounts (accounts.csv), optional"
          hint="email,name,password rows that can sign in even when the account panel is unreachable."
          accept=".csv,text/csv"
          file={csv?.name ?? null}
          onPick={async (f) => {
            setError(null);
            setMade(null);
            setCsv({ name: f.name, text: await f.text() });
          }}
        />

        {env && (
          <div className="border-b border-ink-100 bg-ink-50/40 px-5 py-4 text-sm">
            <p className="text-ink-700">
              <span className="tabular font-semibold text-ink-900">{Object.keys(env.values).length}</span> settings will be packed
              {env.skipped.length > 0 && (
                <span className="text-ink-500"> · left out (set per PC): {env.skipped.join(", ")}</span>
              )}
            </p>
            {missingPanel.length > 0 && (
              <p className="mt-2 text-amber-800">
                {missingPanel.join(" and ")} {missingPanel.length > 1 ? "are" : "is"} not in this .env, so the app will not
                reach this panel to sign people in{csv ? "; only the accounts in accounts.csv will work" : ""}.
              </p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-3 px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-500">Everything stays in this browser: the files and passwords are never sent anywhere.</p>
          <button
            type="button"
            onClick={generate}
            disabled={!env || !key || busy}
            className="shrink-0 rounded-lg bg-ink-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Encrypting…" : "Make credentials.shc"}
          </button>
        </div>
      </div>

      {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>}
      {made && <p role="status" className="mt-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{made} Send it to the team; on each PC use Update credentials.</p>}
    </div>
  );
}
