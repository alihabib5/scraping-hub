"use client";

import { DataTable } from "@/components/ui";
import type { BidResult } from "@/lib/api";

function decisionTone(decision: string): string {
  if (decision === "PASS") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (decision === "REJECT") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700"; // MANUAL REVIEW
}

/** The first rows of the run (the full list, with every verdict, is in the Excel). */
export default function CommbuysResults({ bids }: { bids: BidResult[] }) {
  if (bids.length === 0) return null;
  const passed = bids.filter((b) => b.decision === "PASS").length;

  return (
    <DataTable
      caption={`Results · ${bids.length} ${bids.length === 1 ? "bid" : "bids"} · ${passed} pass`}
      headers={[
        { label: "Bid #" },
        { label: "Description" },
        { label: "Organization" },
        { label: "Available" },
        { label: "Opening" },
        { label: "Decision" },
      ]}
    >
      {bids.map((bid, i) => (
        <tr key={`${bid.bid_number ?? "row"}-${i}`} className="transition hover:bg-ink-50">
          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-medium text-ink-900">
            {bid.detail_url ? (
              <a href={bid.detail_url} target="_blank" rel="noreferrer" className="hover:text-sky-600 hover:underline">
                {bid.bid_number}
              </a>
            ) : (bid.bid_number ?? "—")}
          </td>
          <td className="max-w-sm truncate px-4 py-3 text-ink-700" title={bid.description ?? ""}>{bid.description || "—"}</td>
          <td className="max-w-xs truncate px-4 py-3 text-ink-600" title={bid.organization ?? ""}>{bid.organization || "—"}</td>
          <td className="tabular whitespace-nowrap px-4 py-3 text-xs text-ink-600">{bid.available_date || "—"}</td>
          <td className="tabular whitespace-nowrap px-4 py-3 text-xs text-ink-600">{bid.opening_date || "—"}</td>
          <td className="px-4 py-3">
            {bid.decision ? (
              <span
                className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${decisionTone(bid.decision)}`}
                title={bid.decision_reason ?? ""}
              >
                {bid.decision}
              </span>
            ) : (
              <span className="text-ink-400">—</span>
            )}
          </td>
        </tr>
      ))}
    </DataTable>
  );
}
