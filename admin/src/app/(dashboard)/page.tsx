import { removeAccount } from "@/app/actions";
import SessionTime from "@/components/SessionTime";
import When from "@/components/When";
import { listUsers } from "@/lib/accounts";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Users" };

const th = "px-4 py-3 text-left text-xs font-semibold text-ink-500";
const td = "px-4 py-3.5 align-middle";

export default async function UsersPage() {
  const admin = await requireAdmin();
  const users = await listUsers();
  const iso = (d: Date | null) => (d ? new Date(d).toISOString() : null);

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="font-display text-3xl text-ink-900">Users</h1>
        <p className="mt-1.5 text-sm text-ink-500">
          Everyone who can sign in to the Windows app, with their latest session. Removing someone stops them signing in
          on each PC the next time it is online.
        </p>
      </header>

      <div className="mt-8 overflow-x-auto rounded-xl border border-ink-100 bg-white">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="border-b border-ink-100 bg-ink-50/50">
            <tr>
              <th className={th}>Name</th>
              <th className={th}>Email</th>
              <th className={th}>IP address</th>
              <th className={th}>Last sign-in</th>
              <th className={th}>Session time</th>
              <th className={th}><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {users.map((u) => (
              <tr key={u.email} className="transition hover:bg-ink-50/40">
                <td className={`${td} font-medium text-ink-900`}>
                  {u.name}
                  {u.email === admin && <span className="ml-2 text-xs font-normal text-ink-400">you</span>}
                </td>
                <td className={`${td} text-ink-600`}>{u.email}</td>
                <td className={`${td} tabular text-ink-600`}>{u.ip ?? "—"}</td>
                <td className={`${td} text-ink-600`}>
                  {u.started_at ? <When iso={iso(u.started_at)} /> : <span className="text-ink-400">Not signed in yet</span>}
                </td>
                <td className={td}>
                  <SessionTime started={iso(u.started_at)} lastSeen={iso(u.last_seen_at)} ended={iso(u.ended_at)} />
                </td>
                <td className={`${td} text-right`}>
                  {u.email !== admin && (
                    <form action={removeAccount}>
                      <input type="hidden" name="email" value={u.email} />
                      <button className="rounded-md px-2.5 py-1.5 text-sm font-medium text-rose-700 transition hover:bg-rose-50">
                        Remove
                      </button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <p className="px-4 py-10 text-center text-sm text-ink-500">No approved accounts yet.</p>}
      </div>
    </div>
  );
}
