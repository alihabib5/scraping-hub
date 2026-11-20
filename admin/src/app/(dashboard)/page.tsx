import { removeAccount } from "@/app/actions";
import Avatar from "@/components/Avatar";
import ConfirmButton from "@/components/ConfirmButton";
import SessionTime from "@/components/SessionTime";
import TableSearch from "@/components/TableSearch";
import When from "@/components/When";
import { listUsers } from "@/lib/accounts";
import { isActive } from "@/lib/sessions";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Users" };

const th = "px-5 py-3 text-left text-xs font-semibold text-ink-500";
const td = "px-5 py-3.5 align-middle";
const iso = (d: Date | null) => (d ? new Date(d).toISOString() : null);

export default async function UsersPage() {
  const admin = await requireAdmin();
  const users = await listUsers();
  const active = users.filter((u) => isActive(iso(u.last_seen_at), iso(u.ended_at), Date.now())).length;
  const never = users.filter((u) => !u.started_at).length;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[2rem] leading-tight text-ink-900">Users</h1>
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-500">
            <span><span className="tabular font-semibold text-ink-800">{users.length}</span> can sign in</span>
            <span aria-hidden className="text-ink-300">·</span>
            <span className="inline-flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-ink-300"}`} aria-hidden />
              <span className="tabular font-semibold text-ink-800">{active}</span> active now
            </span>
            {never > 0 && (
              <>
                <span aria-hidden className="text-ink-300">·</span>
                <span><span className="tabular font-semibold text-ink-800">{never}</span> not signed in yet</span>
              </>
            )}
          </p>
        </div>
        {users.length > 3 && <TableSearch target="users" label="Search name or email" />}
      </header>

      <div className="mt-7 overflow-x-auto rounded-xl border border-ink-100 bg-white shadow-[0_1px_2px_rgba(11,31,58,0.04),0_8px_24px_-16px_rgba(11,31,58,0.12)]">
        <table id="users" className="w-full min-w-[820px] text-sm">
          <thead className="border-b border-ink-100">
            <tr>
              <th className={th}>Person</th>
              <th className={th}>IP address</th>
              <th className={th}>Last sign-in</th>
              <th className={th}>Session time</th>
              <th className={`${th} w-44`}><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {users.map((u) => (
              <tr key={u.email} data-search={`${u.name} ${u.email}`.toLowerCase()} className="transition-colors duration-150 hover:bg-paper">
                <td className={td}>
                  <div className="flex items-center gap-3">
                    <Avatar name={u.name} tone={u.email === admin ? "gold" : "ink"} />
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-ink-900">
                        {u.name}
                        {u.email === admin && (
                          <span className="ml-2 rounded-full bg-gold-50 px-2 py-0.5 text-[11px] font-semibold text-gold-600 ring-1 ring-gold-100">You</span>
                        )}
                      </p>
                      <p className="truncate text-[13px] text-ink-500">{u.email}</p>
                    </div>
                  </div>
                </td>
                <td className={`${td} tabular text-ink-600`}>{u.ip ?? <span className="text-ink-300">—</span>}</td>
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
                      <ConfirmButton label="Remove" confirmLabel="Confirm remove" />
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="px-6 py-14 text-center">
            <p className="font-semibold text-ink-900">No one can sign in yet</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-ink-500">
              People ask for an account on the Windows app&apos;s Create account screen. Approve them under Pending
              Approvals and they appear here.
            </p>
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-ink-400">
        Removing someone stops them signing in on each PC the next time it is online.
      </p>
    </div>
  );
}
