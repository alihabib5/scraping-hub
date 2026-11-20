import { approveAccount, removeAccount } from "@/app/actions";
import When from "@/components/When";
import { listPending } from "@/lib/accounts";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Pending Approvals" };

const th = "px-4 py-3 text-left text-xs font-semibold text-ink-500";
const td = "px-4 py-3.5 align-middle";

export default async function PendingPage() {
  await requireAdmin();
  const pending = await listPending();

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="font-display text-3xl text-ink-900">Pending Approvals</h1>
        <p className="mt-1.5 text-sm text-ink-500">
          Accounts requested on the Windows app&apos;s Create account screen. Approved accounts can sign in straight away;
          a declined request is removed and the person may ask again.
        </p>
      </header>

      <div className="mt-8 overflow-x-auto rounded-xl border border-ink-100 bg-white">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="border-b border-ink-100 bg-ink-50/50">
            <tr>
              <th className={th}>Name</th>
              <th className={th}>Email</th>
              <th className={th}>IP address</th>
              <th className={th}>Date requested</th>
              <th className={`${th} text-right`}>Approve / Decline</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {pending.map((p) => (
              <tr key={p.email} className="transition hover:bg-ink-50/40">
                <td className={`${td} font-medium text-ink-900`}>{p.name}</td>
                <td className={`${td} text-ink-600`}>{p.email}</td>
                <td className={`${td} tabular text-ink-600`}>{p.requested_ip ?? "—"}</td>
                <td className={`${td} text-ink-600`}>
                  <When iso={new Date(p.requested_at).toISOString()} />
                </td>
                <td className={td}>
                  <div className="flex justify-end gap-2">
                    <form action={removeAccount}>
                      <input type="hidden" name="email" value={p.email} />
                      <button className="rounded-md px-3 py-1.5 text-sm font-medium text-ink-600 transition hover:bg-ink-50 hover:text-ink-900">
                        Decline
                      </button>
                    </form>
                    <form action={approveAccount}>
                      <input type="hidden" name="email" value={p.email} />
                      <button className="rounded-md bg-ink-900 px-3.5 py-1.5 text-sm font-semibold text-white transition hover:bg-ink-800">
                        Approve
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {pending.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-ink-500">
            Nobody is waiting. New requests from the app appear here.
          </p>
        )}
      </div>
    </div>
  );
}
