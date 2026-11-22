"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import PortalIcon from "@/components/PortalIcon";
import { type Portal } from "@/lib/api";
import { PORTALS } from "@/lib/portals";

const COLLAPSED_KEY = "scraping-hub.sidebar.collapsed";
const listeners = new Set<() => void>();

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

/** The rail's collapsed state, remembered on this PC (a convenience: a fresh profile just starts expanded). */
export function useSidebarCollapsed(): [boolean, (v: boolean) => void] {
  const collapsed = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    readCollapsed,
    () => false,
  );
  const set = (v: boolean) => {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, v ? "1" : "0");
    } catch {
      // storage blocked: the toggle still works for this session via the listeners below
    }
    listeners.forEach((l) => l());
  };
  return [collapsed, set];
}

type User = { username: string; name: string };

/** Who is signed in to the Windows app; null in a normal browser or before sign-in. */
function useSignedInUser(): User | null {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    window.scrapingHub
      ?.currentUser()
      .then((u) => setUser(u ?? null))
      .catch(() => setUser(null));
  }, []);
  return user;
}

function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path d="M4 4v12" strokeLinecap="round" />
      <path d={collapsed ? "M9 6l4 4-4 4" : "M14 6l-4 4 4 4"} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M8 4H5.5A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" strokeLinecap="round" />
      <path d="M12 6.5 15.5 10 12 13.5M15.5 10H8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * The data-source list, Safri-style: a rail that collapses to icons on wide
 * windows, the same content in a slide-in drawer on narrow ones, and the
 * signed-in person with Sign out at the foot.
 */
export default function ConsoleSidebar({
  portal,
  hrefFor,
  live,
  mode,
  onNavigate,
  onClose,
}: {
  portal: Portal | "";
  hrefFor: (portal: string) => string;
  live: Set<string>;
  mode: "rail" | "drawer";
  onNavigate?: () => void;
  onClose?: () => void;
}) {
  const [stored, setCollapsed] = useSidebarCollapsed();
  const collapsed = mode === "rail" && stored;
  const user = useSignedInUser();

  return (
    <div className="flex h-full flex-col">
      <div className={`flex items-center border-b border-ink-200/70 py-3 ${collapsed ? "justify-center px-2" : "justify-between px-4"}`}>
        {!collapsed && <p className="eyebrow text-ink-400">Data sources</p>}
        {mode === "rail" ? (
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 transition hover:bg-ink-50 hover:text-ink-900 focus-visible:outline-2 focus-visible:outline-gold-500"
          >
            <CollapseIcon collapsed={collapsed} />
          </button>
        ) : (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-lg leading-none text-ink-500 transition hover:bg-ink-50 hover:text-ink-900"
          >
            ×
          </button>
        )}
      </div>

      <nav className={`flex-1 overflow-y-auto ${collapsed ? "no-scrollbar px-2 py-3" : "p-3"}`} aria-label="Data sources">
        <ul className="space-y-1">
          {PORTALS.map((p) => {
            const isActive = p.key === portal;
            return (
              <li key={p.key}>
                <Link
                  href={hrefFor(p.key)}
                  onClick={onNavigate}
                  aria-current={isActive ? "page" : undefined}
                  aria-label={collapsed ? p.label : undefined}
                  title={collapsed ? `${p.label} — ${p.tagline}` : undefined}
                  className={`group relative flex w-full items-center rounded-lg transition ${
                    collapsed ? "justify-center p-1.5" : "gap-3 px-3 py-2.5"
                  } ${isActive ? "bg-white shadow-sm shadow-ink-900/[0.04] ring-1 ring-ink-200/70" : "hover:bg-white/70"}`}
                >
                  {isActive && <span className="absolute left-0 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-gold-500" />}
                  <span
                    className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ring-1 transition ${
                      isActive ? p.accent.tile : "bg-ink-50 text-ink-400 ring-ink-100 group-hover:text-ink-600"
                    }`}
                  >
                    <PortalIcon name={p.icon} />
                    {collapsed && live.has(p.key) && (
                      <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                    )}
                  </span>
                  {!collapsed && (
                    <>
                      <span className="min-w-0 flex-1">
                        <span className={`block truncate text-sm ${isActive ? "font-semibold text-ink-900" : "font-medium text-ink-700"}`}>
                          {p.label}
                        </span>
                        <span className="block truncate text-xs text-ink-500">{p.tagline}</span>
                      </span>
                      {live.has(p.key) && (
                        <span className="relative flex h-2 w-2 shrink-0" title="Scraping now">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                        </span>
                      )}
                    </>
                  )}
                  {live.has(p.key) && <span className="sr-only">Scraping now</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {user && (
        <div
          data-testid="signed-in-as"
          className={`flex items-center border-t border-ink-200/70 py-3 ${collapsed ? "flex-col gap-2 px-2" : "gap-3 px-4"}`}
        >
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-900 text-sm font-semibold text-white"
            title={collapsed ? `${user.name} — ${user.username}` : undefined}
            aria-hidden
          >
            {(user.name || user.username).trim().charAt(0).toUpperCase()}
          </span>
          {!collapsed && (
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-ink-900">{user.name}</span>
              <span className="block truncate text-xs text-ink-500">{user.username}</span>
            </span>
          )}
          <button
            type="button"
            onClick={() => window.scrapingHub?.signOut()}
            aria-label="Sign out"
            title="Sign out"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-ink-500 transition hover:bg-ink-50 hover:text-ink-900"
          >
            <SignOutIcon />
          </button>
        </div>
      )}
    </div>
  );
}
