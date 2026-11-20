import { approveAccount, removeAccount } from "@/app/actions";
import Avatar from "@/components/Avatar";
import ConfirmButton from "@/components/ConfirmButton";
import SubmitButton from "@/components/SubmitButton";
import TableSearch from "@/components/TableSearch";
import When from "@/components/When";
import { listPending } from "@/lib/accounts";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Pending Approvals" };

const th = "px-5 py-3 text-left text-xs font-semibold text-ink-500";
const td = "px-5 py-3.5 align-middle";

export default async function PendingPage() {
  await requireAdmin();
  const pending = await listPending();

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-[2rem] leading-tight text-ink-900">Pending Approvals</h1>
          <p className="mt-2 text-sm text-ink-500">
            {pending.length === 0 ? (
              "No requests waiting."
            ) : (
              <>
                <span className="tabular font-semibold text-ink-800">{pending.length}</span>{" "}
                {pending.length === 1 ? "request is" : "requests are"} waiting. Approved accounts can sign in straight away.
              </>
            )}
          </p>
        </div>
        {pending.length > 3 && <TableSearch target="pending" label="Search name or email" />}
      </header>

      <div className="mt-7 overflow-x-auto rounded-xl border border-ink-100 bg-white shadow-[0_1px_2px_rgba(11,31,58,0.04),0_8px_24px_-16px_rgba(11,31,58,0.12)]">
        {pending.length > 0 ? (
          <table id="pending" className="w-full min-w-[820px] text-sm">
            <thead className="border-b border-ink-100">
              <tr>
                <th className={th}>Person</th>
                <th className={th}>IP address</th>
                <th className={th}>Date requested</th>
                <th className={`${th} w-64 text-right`}>Approve / Decline</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {pending.map((p) => (
                <tr key={p.email} data-search={`${p.name} ${p.email}`.toLowerCase()} className="transition-colors duration-150 hover:bg-paper">
                  <td className={td}>
                    <div className="flex items-center gap-3">
                      <Avatar name={p.name} tone="quiet" />
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-ink-900">{p.name}</p>
                        <p className="truncate text-[13px] text-ink-500">{p.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className={`${td} tabular text-ink-600`}>{p.requested_ip ?? <span className="text-ink-300">—</span>}</td>
                  <td className={`${td} text-ink-600`}>
                    <When iso={new Date(p.requested_at).toISOString()} />
                  </td>
                  <td className={td}>
                    <div className="flex items-center justify-end gap-2">
                      <form action={removeAccount}>
                        <input type="hidden" name="email" value={p.email} />
                        <ConfirmButton label="Decline" confirmLabel="Confirm decline" tone="quiet" />
                      </form>
                      <form action={approveAccount}>
                        <input type="hidden" name="email" value={p.email} />
                        <SubmitButton busy="Approving…">Approve</SubmitButton>
                      </form>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-gold-50 text-gold-600 ring-1 ring-gold-100">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-5 w-5" aria-hidden>
                <path d="m4.5 10.5 3.5 3.5 7.5-8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <p className="mt-4 font-semibold text-ink-900">You&apos;re all caught up</p>
            <p className="mt-1 max-w-md text-sm text-ink-500">
              When someone uses Create account on the Windows app&apos;s sign-in screen, their request appears here with
              the IP it came from. A declined request is removed, and the person may ask again.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
