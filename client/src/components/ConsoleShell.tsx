"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import ActiveJobs from "@/components/ActiveJobs";
import ConsoleSidebar, { useSidebarCollapsed } from "@/components/ConsoleSidebar";
import PortalPanelHost from "@/components/PortalPanelHost";
import SessionEngine from "@/components/SessionEngine";
import UpdateCredentialsButton from "@/components/UpdateCredentialsButton";

import Copyright from "@/components/Copyright";
import Logo from "@/components/Logo";
import { LinkButton } from "@/components/ui";
import { apiDocsUrl, type Portal } from "@/lib/api";
import { isPortal, PORTALS } from "@/lib/portals";
import { useActivePortals } from "@/lib/sessions";

const SECTIONS = [
  { key: "", label: "Console" },
  { key: "history", label: "History" },
  { key: "exports", label: "Downloads" },
] as const;

/**
 * Chrome for every console route: global bar, source rail, footer.
 *
 * Both nav dimensions live in the URL (`/console/{portal}/{section}`), so the
 * shell derives its active state from the pathname rather than holding any.
 *
 * It also owns the two things that must outlive a page. `SessionEngine` watches
 * every run on every portal for as long as the console is open, and
 * `PortalPanelHost` keeps the portal panels themselves mounted across
 * navigation. Both live here because a layout survives the routes under it —
 * which is exactly what a scrape in flight needs and a page cannot give it.
 */
export default function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean); // ["console", portal, section?]
  const portal = (segments[1] ?? "") as Portal;
  const section = segments[2] ?? "";
  // Portals with a run in flight, so the rail can say so while you are looking
  // at another one — the point of the whole exercise is that a run you navigated
  // away from is still going.
  const live = useActivePortals();
  const [collapsed] = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const currentPortal = PORTALS.find((p) => p.key === portal);

  // Escape closes the drawer; it also closes if the window grows past the narrow layout.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    const wide = window.matchMedia("(min-width: 1024px)");
    const onWide = () => wide.matches && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    wide.addEventListener("change", onWide);
    return () => {
      window.removeEventListener("keydown", onKey);
      wide.removeEventListener("change", onWide);
    };
  }, [drawerOpen]);

  const href = (p: string, s: string) => `/console/${p}${s ? `/${s}` : ""}`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-ink-200/70 bg-paper/85 backdrop-blur">
        <div className="flex h-16 items-center gap-2 px-3 sm:gap-3 sm:px-6">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open data sources"
            className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-600 transition hover:bg-ink-50 hover:text-ink-900 lg:hidden"
          >
            <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
              <path d="M3.5 5.5h13M3.5 10h13M3.5 14.5h13" strokeLinecap="round" />
            </svg>
            {live.size > 0 && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-paper" />}
          </button>
          <Link href="/" className="flex shrink-0 items-center gap-2.5 rounded-lg transition hover:opacity-80">
            <Logo />
            <span className="hidden font-display text-base text-ink-900 lg:inline">Scraping Hub</span>
          </Link>
          {/* Narrow windows have no rail, so the header names the portal (it gives way first). */}
          {currentPortal && (
            <span className="min-w-0 truncate text-sm font-medium text-ink-600 lg:hidden">{currentPortal.label}</span>
          )}

          <span className="mx-1 hidden h-6 w-px shrink-0 bg-ink-200 sm:block" />

          <nav className="no-scrollbar flex shrink-0 items-center gap-1 overflow-x-auto" aria-label="Sections">
            {SECTIONS.map((s) => {
              const isActive = s.key === section;
              return (
                <Link
                  key={s.key || "console"}
                  href={href(portal, s.key)}
                  aria-current={isActive ? "page" : undefined}
                  className={`relative shrink-0 rounded-lg px-3 pb-2 pt-1.5 text-sm transition ${
                    isActive ? "font-semibold text-ink-900" : "font-medium text-ink-500 hover:bg-ink-50 hover:text-ink-900"
                  }`}
                >
                  {s.label}
                  {/* Sits inside the link's box: the nav is overflow-x-auto, which
                      forces overflow-y:auto, so anything hanging below it would
                      raise a stray vertical scrollbar. */}
                  {isActive && <span className="absolute inset-x-3 bottom-0.5 h-0.5 rounded-full bg-gold-500" />}
                </Link>
              );
            })}
          </nav>

          <span className="min-w-0 flex-1" />

          <div className="hidden items-center gap-2 rounded-full border border-ink-200 bg-white px-2.5 py-1 xl:flex">
            <span className="relative flex h-1.5 w-1.5">
              <span className="status-pulse absolute inline-flex h-full w-full rounded-full bg-emerald-400" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            <span className="whitespace-nowrap text-xs font-medium text-ink-600">{PORTALS.length} sources</span>
          </div>

          <UpdateCredentialsButton />

          <LinkButton href={apiDocsUrl()} target="_blank" rel="noopener noreferrer" size="sm">
            <span className="hidden lg:inline">API docs</span>
            <span className="sr-only lg:hidden">API docs</span>
            <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 lg:hidden" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <path d="M5 3.5h6.5L15 7v9.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-12a1 1 0 0 1 1-1Z" strokeLinejoin="round" />
              <path d="M11 3.5V7h4M6.75 10.5h6.5M6.75 13.5h4" strokeLinecap="round" />
            </svg>
          </LinkButton>
        </div>
      </header>

      {/* Watches every run on every portal, independent of what is mounted. */}
      <SessionEngine />

      <div className="flex min-h-0 flex-1">
        {/* Source rail (wide windows): collapses to icons */}
        <aside
          className={`sticky top-16 hidden h-[calc(100vh-4rem)] shrink-0 border-r border-ink-200/70 bg-white/60 transition-[width] duration-200 lg:block ${
            collapsed ? "w-[4.5rem]" : "w-64"
          }`}
        >
          <ConsoleSidebar portal={portal} hrefFor={(p) => href(p, section)} live={live} mode="rail" />
        </aside>

        {/* The same list as a slide-in drawer (narrow windows) */}
        {drawerOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Data sources">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setDrawerOpen(false)}
              className="absolute inset-0 bg-ink-900/30"
            />
            <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-paper shadow-xl">
              <ConsoleSidebar
                portal={portal}
                hrefFor={(p) => href(p, section)}
                live={live}
                mode="drawer"
                onNavigate={() => setDrawerOpen(false)}
                onClose={() => setDrawerOpen(false)}
              />
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-8 sm:py-8">
            {/* The portal panels are rendered here, by the layout, rather than
                by `[portal]/page.tsx` — that page renders nothing. A page is
                torn down on navigation; this is not, which is what lets a
                running scrape keep its view. The section pages (History,
                Downloads) still come through as children. */}
            <PortalPanelHost portal={isPortal(portal) ? portal : null} visible={section === ""} />
            {children}
          </main>

          {/* Every in-flight scrape, on every portal. Lives in the shell, not
              on a page, so moving between portals never loses sight of a run —
              the run belongs to the server, not to the page that started it. */}
          <ActiveJobs />

          <footer className="border-t border-ink-200/70 px-5 py-5 sm:px-8">
            <div className="mx-auto flex max-w-5xl flex-col gap-1">
              <p className="text-xs text-ink-400">
                Scraping Hub — automated bid collection for public procurement portals.
              </p>
              <Copyright />
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
