import { approveAccount, removeAccount, signOut } from "@/app/actions";
import { listAccounts, type Account } from "@/lib/accounts";
import { requireAdmin } from "@/lib/session";

export const dynamic = "force-dynamic";

const when = (d: Date | null) =>
  d ? new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";

function Row({ account, admin, children }: { account: Account; admin: string; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-4 py-3.5">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink-900">
          {account.name}
          {account.email === admin && <span className="ml-2 text-xs font-normal text-ink-400">you</span>}
        </p>
        <p className="truncate text-sm text-ink-500">{account.email}</p>
      </div>
      {children}
    </li>
  );
}

const ghost = "rounded-md px-3 py-1.5 text-sm font-medium text-ink-600 transition hover:bg-ink-50 hover:text-ink-900";

export default async function AccountsPage() {
  const admin = await requireAdmin();
  const accounts = await listAccounts();
  const pending = accounts.filter((a) => a.status === "pending");
  const approved = accounts.filter((a) => a.status === "approved");

  return (
    <main className="mx-auto max-w-3xl px-4 pb-16 pt-10 sm:px-6">
      <header className="flex items-end justify-between gap-4 border-b border-ink-100 pb-5">
        <div>
          <p className="text-sm font-medium text-ink-600">Scraping Hub</p>
          <h1 className="font-display mt-1 text-3xl text-ink-900">Accounts</h1>
        </div>
        <form action={signOut} className="flex items-center gap-3 text-sm text-ink-500">
          <span className="hidden sm:inline">{admin}</span>
          <button className={ghost}>Sign out</button>
        </form>
      </header>

      <section className="mt-8" aria-labelledby="waiting">
        <h2 id="waiting" className="flex items-baseline gap-2 text-base font-semibold text-ink-900">
          Waiting for approval
          <span className="tabular text-sm font-normal text-ink-500">{pending.length}</span>
        </h2>
        {pending.length === 0 ? (
          <p className="mt-3 text-sm text-ink-500">
            Nobody is waiting. Requests made on the app&apos;s Create account screen appear here.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-ink-100">
            {pending.map((a) => (
              <Row key={a.email} account={a} admin={admin}>
                <span className="tabular hidden text-sm text-ink-400 sm:inline">{when(a.requested_at)}</span>
                <form action={removeAccount}>
                  <input type="hidden" name="email" value={a.email} />
                  <button className={ghost}>Reject</button>
                </form>
                <form action={approveAccount}>
                  <input type="hidden" name="email" value={a.email} />
                  <button className="rounded-md bg-ink-900 px-3.5 py-1.5 text-sm font-semibold text-white transition hover:bg-ink-800">
                    Approve
                  </button>
                </form>
              </Row>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-12" aria-labelledby="approved">
        <h2 id="approved" className="flex items-baseline gap-2 text-base font-semibold text-ink-900">
          Can sign in
          <span className="tabular text-sm font-normal text-ink-500">{approved.length}</span>
        </h2>
        <p className="mt-1 text-sm text-ink-500">
          Removing someone stops them signing in on each PC the next time it is online.
        </p>
        <ul className="mt-2 divide-y divide-ink-100">
          {approved.map((a) => (
            <Row key={a.email} account={a} admin={admin}>
              <span className="tabular hidden text-sm text-ink-400 sm:inline">
                {a.decided_by ? `Approved ${when(a.decided_at)}` : ""}
              </span>
              {a.email !== admin && (
                <form action={removeAccount}>
                  <input type="hidden" name="email" value={a.email} />
                  <button className="rounded-md px-3 py-1.5 text-sm font-medium text-rose-700 transition hover:bg-rose-50">
                    Remove
                  </button>
                </form>
              )}
            </Row>
          ))}
        </ul>
      </section>
    </main>
  );
}
