// The app checks in every 5 minutes; past twice that with no sign-out, the session is taken as closed.
export const STALE_MS = 12 * 60_000;

/** Open and still checking in: the one rule both the row and the page's "active now" count use. */
export function isActive(lastSeen: string | null, ended: string | null, now: number): boolean {
  return !ended && !!lastSeen && now - Date.parse(lastSeen) < STALE_MS;
}
