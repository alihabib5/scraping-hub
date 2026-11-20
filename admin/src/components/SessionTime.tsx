"use client";

import { useSyncExternalStore } from "react";

const noSubscribe = () => () => {};
// The app checks in every 5 minutes; past twice that with no sign-out, the session is taken as closed.
const STALE_MS = 12 * 60_000;

function span(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes < 1) return "under a minute";
  const h = Math.floor(minutes / 60);
  return h ? `${h} h ${minutes % 60} m` : `${minutes} m`;
}

/** How long the latest session lasted, "Active now", or for a PC that vanished, how long until its last check-in. */
export default function SessionTime({ started, lastSeen, ended }: { started: string | null; lastSeen: string | null; ended: string | null }) {
  const now = useSyncExternalStore(noSubscribe, () => Math.floor(Date.now() / 60_000) * 60_000, () => 0);
  if (!started) return <span className="text-ink-400">—</span>;
  const t0 = Date.parse(started);
  if (ended) return <span className="tabular text-ink-700">{span(Date.parse(ended) - t0)}</span>;
  const seen = lastSeen ? Date.parse(lastSeen) : t0;
  if (now && now - seen < STALE_MS) {
    return (
      <span className="inline-flex items-center gap-2 whitespace-nowrap text-emerald-700">
        <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
        Active now · {span(now - t0)}
      </span>
    );
  }
  return (
    <span className="tabular text-ink-700" title="The app stopped checking in without signing out (closed abruptly or went offline).">
      {span(seen - t0)} <span className="text-ink-400">· no sign-out</span>
    </span>
  );
}
