"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui";

/** What the Windows app reports back (desktop/main.js). */
interface UpdateResult {
  ok: boolean;
  code: "cancelled" | "rejected" | "busy" | "failed" | "updated";
  message?: string;
  detail?: string;
}

/** Provided by the Windows app (desktop/preload.js); absent in a normal browser. */
declare global {
  interface Window {
    scrapingHub?: {
      updateCredentials: () => Promise<UpdateResult>;
      currentUser: () => Promise<{ username: string; name: string } | null>;
      signOut: () => Promise<void>;
    };
  }
}

const noSubscribe = () => () => {};

/**
 * Swap in a new portal-credentials file without reinstalling — shown only
 * inside the Windows app. The app picks the file, checks it, refuses while a
 * run is in progress, and restarts the engine; the outcome is shown here.
 */
export default function UpdateCredentialsButton() {
  // Read on the client only, so the prerendered page (no button) hydrates cleanly.
  const desktop = useSyncExternalStore(noSubscribe, () => Boolean(window.scrapingHub), () => false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UpdateResult | null>(null);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    window.scrapingHub?.currentUser().then((u) => setName(u?.name ?? null));
  }, []);

  // A success note goes away on its own; a problem stays until dismissed.
  useEffect(() => {
    if (!result?.ok) return;
    const t = setTimeout(() => setResult(null), 10_000);
    return () => clearTimeout(t);
  }, [result]);

  if (!desktop) return null;

  const update = async () => {
    setBusy(true);
    setResult(null);
    try {
      const r = await window.scrapingHub!.updateCredentials();
      if (r.code !== "cancelled") setResult(r);
    } catch (e) {
      setResult({ ok: false, code: "failed", message: "Something went wrong and nothing was changed.", detail: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {name && (
        <span className="hidden items-center gap-2 text-xs text-ink-600 md:flex" data-testid="signed-in-as">
          <span className="max-w-[10rem] truncate font-medium text-ink-800">{name}</span>
          <button
            type="button"
            onClick={() => window.scrapingHub?.signOut()}
            className="rounded-md px-1.5 py-0.5 text-ink-500 underline-offset-2 transition hover:text-ink-900 hover:underline"
          >
            Sign out
          </button>
        </span>
      )}
      <Button
        size="sm"
        loading={busy}
        onClick={update}
        data-testid="update-credentials"
        title="Load a new credentials file after a portal password changes"
      >
        <span className="hidden sm:inline">{busy ? "Updating…" : "Update credentials"}</span>
        <span className="sm:hidden">Credentials</span>
      </Button>

      {result && (
        <div
          role={result.ok ? "status" : "alert"}
          data-testid="update-credentials-result"
          data-code={result.code}
          className={`fixed bottom-16 right-4 z-40 w-[22rem] max-w-[calc(100vw-2rem)] rounded-xl border p-4 shadow-lg ${
            result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium">{result.message}</p>
            <button
              type="button"
              onClick={() => setResult(null)}
              aria-label="Dismiss"
              className="shrink-0 rounded-md px-1.5 text-base leading-none opacity-60 transition hover:opacity-100"
            >
              ×
            </button>
          </div>
          {result.detail && <p className="mt-1.5 text-xs leading-relaxed opacity-90">{result.detail}</p>}
        </div>
      )}
    </>
  );
}
