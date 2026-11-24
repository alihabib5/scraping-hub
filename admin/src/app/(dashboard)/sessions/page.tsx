import Link from "next/link";

import Avatar from "@/components/Avatar";
import PersonFilter from "@/components/PersonFilter";
import SessionTime from "@/components/SessionTime";
import When from "@/components/When";
import { listSessions, listUsers, normalEmail, sessionCounts, SESSIONS_PER_PAGE } from "@/lib/accounts";
import { isActive } from "@/lib/sessions";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Session History" };

const th = "px-5 py-3 text-left text-xs font-semibold text-ink-500";
const td = "px-5 py-3.5 align-middle";
const iso = (d: Date | null) => (d ? new Date(d).toISOString() : null);
const pager = "rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-sm font-semibold text-ink-800 transition hover:border-ink-300 hover:bg-ink-50";

export default async function SessionsPage({ searchParams }: { searchParams: Promise<{ email?: string; page?: string }> }) {
  const admin = await requireAdmin();
  const params = await searchParams;
  const email = params.email ? normalEmail(params.email) : null;
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const [rows, counts, users] = await Promise.all([listSessions(email, page), sessionCounts(email), listUsers()]);
  const hasOlder = rows.length > SESSIONS_PER_PAGE;
  const sessions = rows.slice(0, SESSIONS_PER_PAGE);
  const now = Date.now();
  const open = sessions.filter((s) => isActive(iso(s.last_seen_at), iso(s.ended_at), now)).length;
  const person = email ? users.find((u) => u.email === email) : null;
  const href = (p: number) => `/sessions?${new URLSearchParams({ ...(email ? { email } : {}), ...(p > 1 ? { page: String(p) } : {}) })}`;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[2rem] leading-tight text-ink-900">Session History</h1>
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-500">
            {person && <span className="font-semibold text-ink-800">{person.name} ·</span>}
            <span><span className="tabular font-semibold text-ink-800">{counts.total}</span> {counts.total === 1 ? "session" : "sessions"}</span>
            <span aria-hidden className="text-ink-300">·</span>
            <span><span className="tabular font-semibold text-ink-800">{counts.week}</span> in the last 7 days</span>
            {page === 1 && (
              <>
                <span aria-hidden className="text-ink-300">·</span>
                <span className="inline-flex items-center gap-1.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${open ? "bg-emerald-500" : "bg-ink-300"}`} aria-hidden />
                  <span className="tabular font-semibold text-ink-800">{open}</span> open now
                </span>
              </>
            )}
          </p>
        </div>
        <PersonFilter people={users.map((u) => ({ email: u.email, name: u.name }))} current={email} />
      </header>

      <div className="mt-7 overflow-x-auto rounded-xl border border-ink-100 bg-white shadow-[0_1px_2px_rgba(11,31,58,0.04),0_8px_24px_-16px_rgba(11,31,58,0.12)]">
        {sessions.length > 0 ? (
          <table className="w-full min-w-[860px] text-sm">
            <thead className="border-b border-ink-100">
              <tr>
                <th className={th}>Person</th>
                <th className={th}>IP address</th>
                <th className={th}>Signed in</th>
                <th className={th}>Signed out</th>
                <th className={th}>Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {sessions.map((s) => {
                const live = isActive(iso(s.last_seen_at), iso(s.ended_at), now);
                return (
                  <tr key={s.id} className="transition-colors duration-150 hover:bg-paper">
                    <td className={td}>
                      <div className="flex items-center gap-3">
                        <Avatar name={s.name} tone={s.email === admin ? "gold" : "ink"} />
                        <div className="min-w-0">
                          <Link
                            href={`/sessions?email=${encodeURIComponent(s.email)}`}
                            className="block truncate font-semibold text-ink-900 underline-offset-4 hover:underline"
                            title={`Only ${s.name}'s sessions`}
                          >
                            {s.name}
                          </Link>
                          <p className="truncate text-[13px] text-ink-500">{s.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className={`${td} tabular text-ink-600`}>{s.ip ?? <span className="text-ink-300">—</span>}</td>
                    <td className={`${td} text-ink-600`}><When iso={iso(s.started_at)} /></td>
                    <td className={`${td} text-ink-600`}>
                      {s.ended_at ? (
                        <When iso={iso(s.ended_at)} />
                      ) : live ? (
                        <span className="text-emerald-700">Still signed in</span>
                      ) : (
                        <span className="text-ink-400" title="The app stopped checking in without signing out (closed abruptly or went offline).">
                          No sign-out
                        </span>
                      )}
                    </td>
                    <td className={td}>
                      <SessionTime started={iso(s.started_at)} lastSeen={iso(s.last_seen_at)} ended={iso(s.ended_at)} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <p className="font-semibold text-ink-900">{person ? `${person.name} has not signed in yet` : "No sessions yet"}</p>
            <p className="mt-1 max-w-md text-sm text-ink-500">
              Each sign-in to the Windows app appears here with its IP, when it started and ended, and how long it lasted.
            </p>
          </div>
        )}
      </div>

      {(page > 1 || hasOlder) && (
        <nav aria-label="Pages" className="mt-4 flex items-center justify-between">
          {page > 1 ? <Link href={href(page - 1)} className={pager}>Newer</Link> : <span />}
          <span className="tabular text-xs text-ink-500">Page {page}</span>
          {hasOlder ? <Link href={href(page + 1)} className={pager}>Older</Link> : <span />}
        </nav>
      )}
      <p className="mt-3 text-xs text-ink-400">Removing a user also removes their session history.</p>
    </div>
  );
}
