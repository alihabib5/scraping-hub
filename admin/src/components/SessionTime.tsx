"use client";

import { useSyncExternalStore } from "react";

import { isActive } from "@/lib/sessions";

const noSubscribe = () => () => {};

function span(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes < 1) return "under a minute";
  const h = Math.floor(minutes / 60);
  return h ? `${h} h ${minutes % 60} m` : `${minutes} m`;
}

/** How long the latest session lasted, "Active now", or for a PC that vanished, how long until its last check-in. */
export default function SessionTime({ started, lastSeen, ended }: { started: string | null; lastSeen: string | null; ended: string | null }) {
  const now = useSyncExternalStore(noSubscribe, () => Math.floor(Date.now() / 60_000) * 60_000, () => 0);
  if (!started) return <span className="text-ink-300">—</span>;
  const t0 = Date.parse(started);
  if (ended) return <span className="tabular text-ink-700">{span(Date.parse(ended) - t0)}</span>;
  if (now && isActive(lastSeen, ended, now)) {
    return (
      <span className="inline-flex items-center gap-2 whitespace-nowrap rounded-full bg-emerald-50 px-2.5 py-1 text-[13px] font-medium text-emerald-800 ring-1 ring-emerald-100">
        <span className="relative flex h-2 w-2" aria-hidden>
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
        Active · {span(now - t0)}
      </span>
    );
  }
  const seen = lastSeen ? Date.parse(lastSeen) : t0;
  return (
    <span className="tabular whitespace-nowrap text-ink-700" title="The app stopped checking in without signing out (closed abruptly or went offline).">
      {span(seen - t0)} <span className="text-ink-400">· no sign-out</span>
    </span>
  );
}
