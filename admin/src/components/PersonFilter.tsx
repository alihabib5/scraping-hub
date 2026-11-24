"use client";

import { useRouter } from "next/navigation";

/** Pick whose sessions to show; "Everyone" clears the filter. Changes the URL, so the view can be shared or bookmarked. */
export default function PersonFilter({ people, current }: { people: { email: string; name: string }[]; current: string | null }) {
  const router = useRouter();
  return (
    <label className="flex flex-col gap-1.5 sm:items-end">
      <span className="sr-only">Show sessions for</span>
      <select
        value={current ?? ""}
        onChange={(e) => router.push(e.target.value ? `/sessions?email=${encodeURIComponent(e.target.value)}` : "/sessions")}
        className="w-full rounded-lg border border-ink-200 bg-white py-2 pl-3 pr-8 text-sm text-ink-900 transition hover:border-ink-300 focus:border-gold-500 focus:shadow-[0_0_0_3px_rgba(185,135,60,0.2)] focus:outline-none sm:w-72"
      >
        <option value="">Everyone</option>
        {people.map((p) => (
          <option key={p.email} value={p.email}>
            {p.name} ({p.email})
          </option>
        ))}
      </select>
    </label>
  );
}
