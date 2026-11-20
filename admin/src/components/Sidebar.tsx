"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { signOut } from "@/app/actions";

const icon = "h-[18px] w-[18px] shrink-0";
const ICONS = {
  users: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className={icon} aria-hidden>
      <circle cx="7.5" cy="7" r="3" />
      <path d="M2.5 16.5c.6-2.8 2.6-4.5 5-4.5s4.4 1.7 5 4.5" strokeLinecap="round" />
      <path d="M13 4.2a3 3 0 0 1 0 5.6M14.5 12.3c1.6.5 2.7 2 3 4.2" strokeLinecap="round" />
    </svg>
  ),
  pending: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className={icon} aria-hidden>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4.2l2.8 1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  encryptor: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className={icon} aria-hidden>
      <rect x="4" y="8.5" width="12" height="8.5" rx="1.75" />
      <path d="M6.75 8.5V6.25a3.25 3.25 0 0 1 6.5 0V8.5" />
      <path d="M10 11.75v2" strokeLinecap="round" />
    </svg>
  ),
};

const NAV = [
  { href: "/", label: "Users", icon: ICONS.users },
  { href: "/pending", label: "Pending Approvals", icon: ICONS.pending },
  { href: "/encryptor", label: "Encryptor", icon: ICONS.encryptor },
] as const;

/** The dashboard's sidebar; on a narrow screen it becomes a bar across the top. */
export default function Sidebar({ admin, name, pending }: { admin: string; name: string; pending: number }) {
  const path = usePathname();
  return (
    <aside className="flex shrink-0 flex-col border-b border-ink-100 bg-white md:sticky md:top-0 md:h-screen md:w-64 md:border-b-0 md:border-r">
      <div className="flex items-center gap-3 px-5 pb-4 pt-5 md:pb-6 md:pt-7">
        <svg width="32" height="32" viewBox="0 0 40 40" aria-hidden className="shrink-0">
          <rect width="40" height="40" rx="10" fill="#0b1f3a" />
          <path d="M11 14.5h18M11 20h12M11 25.5h15" stroke="#faf8f3" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="28.5" cy="25.5" r="2.6" fill="#b9873c" />
        </svg>
        <div className="min-w-0">
          <p className="font-display text-[17px] leading-tight text-ink-900">Scraping Hub</p>
          <p className="text-xs text-ink-500">Administration</p>
        </div>
        <form action={signOut} className="ml-auto md:hidden">
          <button className="rounded-md px-2 py-1 text-sm font-medium text-ink-600 transition hover:text-ink-900">Sign out</button>
        </form>
      </div>

      <nav aria-label="Dashboard" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible md:pb-0">
        {NAV.map((item) => {
          const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                active ? "bg-ink-50 font-semibold text-ink-900" : "font-medium text-ink-600 hover:bg-ink-50/60 hover:text-ink-900"
              }`}
            >
              <span className={active ? "text-gold-600" : "text-ink-400"}>{item.icon}</span>
              <span className="whitespace-nowrap">{item.label}</span>
              {item.href === "/pending" && pending > 0 && (
                <span className="tabular ml-auto rounded-full bg-gold-500 px-2 py-0.5 text-[11px] font-semibold leading-none text-white">
                  {pending}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="hidden border-t border-ink-100 px-5 py-4 md:block">
        <p className="text-xs font-medium text-ink-400">Signed in as</p>
        <p className="mt-0.5 truncate text-sm font-semibold text-ink-900">{name}</p>
        <p className="truncate text-xs text-ink-500" title={admin}>{admin}</p>
        <form action={signOut} className="mt-3">
          <button className="rounded-md text-sm font-medium text-ink-600 underline-offset-4 transition hover:text-ink-900 hover:underline">
            Sign out
          </button>
        </form>
      </div>
    </aside>
  );
}
