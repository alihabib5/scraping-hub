"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { signOut } from "@/app/actions";
import Avatar from "@/components/Avatar";
import Mark from "@/components/Mark";

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
  history: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className={icon} aria-hidden>
      <path d="M3.5 10a6.5 6.5 0 1 0 1.9-4.6" strokeLinecap="round" />
      <path d="M3.25 3.5v3h3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 6.75v3.5l2.25 1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  encryptor: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className={icon} aria-hidden>
      <rect x="4" y="8.5" width="12" height="8.5" rx="1.75" />
      <path d="M6.75 8.5V6.25a3.25 3.25 0 0 1 6.5 0V8.5" />
      <path d="M10 11.75v2" strokeLinecap="round" />
    </svg>
  ),
  signOut: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4" aria-hidden>
      <path d="M8 4H5.5A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" strokeLinecap="round" />
      <path d="M12 6.5 15.5 10 12 13.5M15.5 10H8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

const NAV = [
  { href: "/", label: "Users", icon: ICONS.users },
  { href: "/pending", label: "Pending Approvals", icon: ICONS.pending },
  { href: "/sessions", label: "Session History", icon: ICONS.history },
  { href: "/encryptor", label: "Encryptor", icon: ICONS.encryptor },
] as const;

/** The dashboard's navy rail; on a narrow screen it becomes a bar across the top. */
export default function Sidebar({ admin, name, pending }: { admin: string; name: string; pending: number }) {
  const path = usePathname();
  return (
    <aside className="flex shrink-0 flex-col bg-ink-900 text-ink-100 md:sticky md:top-0 md:h-screen md:w-[17rem]">
      <div className="flex items-center gap-3 px-5 pb-4 pt-5 md:px-6 md:pb-8 md:pt-7">
        <Mark size={34} onDark />
        <div className="min-w-0">
          <p className="font-display text-[18px] leading-tight text-white">Scraping Hub</p>
          <p className="text-xs text-ink-300">Account administration</p>
        </div>
        <form action={signOut} className="ml-auto md:hidden">
          <button className="rounded-md px-2 py-1 text-sm font-medium text-ink-200 transition hover:text-white">Sign out</button>
        </form>
      </div>

      <nav aria-label="Dashboard" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible md:px-4 md:pb-0">
        {NAV.map((item) => {
          const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`group flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition duration-200 ${
                active ? "bg-white/[0.08] font-semibold text-white" : "font-medium text-ink-200 hover:bg-white/[0.05] hover:text-white"
              }`}
            >
              <span className={active ? "text-gold-400" : "text-ink-300 transition group-hover:text-ink-100"}>{item.icon}</span>
              <span className="whitespace-nowrap">{item.label}</span>
              {item.href === "/pending" && pending > 0 && (
                <span className="tabular ml-auto rounded-full bg-gold-500 px-2 py-0.5 text-[11px] font-semibold leading-4 text-ink-900">
                  {pending}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mx-4 mb-4 hidden items-center gap-3 rounded-xl bg-white/[0.05] p-3 md:flex">
        <Avatar name={name} tone="gold" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{name}</p>
          <p className="truncate text-xs text-ink-300" title={admin}>{admin}</p>
        </div>
        <form action={signOut}>
          <button
            title="Sign out"
            aria-label="Sign out"
            className="rounded-md p-1.5 text-ink-300 transition hover:bg-white/[0.08] hover:text-white"
          >
            {ICONS.signOut}
          </button>
        </form>
      </div>
    </aside>
  );
}
