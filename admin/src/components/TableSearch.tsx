"use client";

import { useEffect, useState } from "react";

/**
 * Filters the rows of the table `target` as you type, matching each row's
 * data-search text (name and email). The rows stay server-rendered; this only
 * hides the ones that don't match, and says so when none do.
 */
export default function TableSearch({ target, label }: { target: string; label: string }) {
  const [query, setQuery] = useState("");
  const [none, setNone] = useState(false);

  useEffect(() => {
    const rows = document.querySelectorAll<HTMLElement>(`#${target} tbody tr[data-search]`);
    const q = query.trim().toLowerCase();
    let shown = 0;
    rows.forEach((row) => {
      const match = !q || (row.dataset.search ?? "").includes(q);
      row.hidden = !match;
      if (match) shown++;
    });
    setNone(rows.length > 0 && shown === 0);
  }, [query, target]);

  return (
    <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
      <label className="relative block w-full sm:w-72">
        <span className="sr-only">{label}</span>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400">
          <circle cx="9" cy="9" r="5.5" />
          <path d="m13.2 13.2 3.3 3.3" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={label}
          className="w-full rounded-lg border border-ink-200 bg-white py-2 pl-9 pr-3 text-sm text-ink-900 placeholder:text-ink-400 transition hover:border-ink-300 focus:border-gold-500 focus:shadow-[0_0_0_3px_rgba(185,135,60,0.2)] focus:outline-none"
        />
      </label>
      {none && <p className="text-xs text-ink-500" role="status">Nobody matches “{query.trim()}”.</p>}
    </div>
  );
}
