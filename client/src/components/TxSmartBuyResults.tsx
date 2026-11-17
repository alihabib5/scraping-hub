"use client";

import { DataTable } from "@/components/ui";
import type { BidResult } from "@/lib/api";

/** Posted reads as live; everything else (awarded, closed, cancelled) as settled. */
function statusTone(status: string): string {
  return /posted/i.test(status) && !/cancel/i.test(status)
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : "border-ink-200 bg-ink-50 text-ink-600";
}

/** The first rows of the run's ESBD export (the full list is in the Excel). */
export default function TxSmartBuyResults({ bids }: { bids: BidResult[] }) {
  if (bids.length === 0) return null;

  return (
    <DataTable
      caption={`Results · ${bids.length} ${bids.length === 1 ? "solicitation" : "solicitations"}`}
      headers={[
        { label: "Solicitation ID" },
        { label: "Name" },
        { label: "Due" },
        { label: "Status" },
        { label: "Posted" },
        { label: "Agency #" },
      ]}
    >
      {bids.map((bid, i) => (
        <tr key={`${bid.solicitation_id ?? "row"}-${i}`} className="transition hover:bg-ink-50">
          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-medium text-ink-900">
            {bid.detail_url ? (
              <a href={bid.detail_url} target="_blank" rel="noreferrer" className="hover:text-red-600 hover:underline">
                {bid.solicitation_id}
              </a>
            ) : (bid.solicitation_id ?? "—")}
          </td>
          <td className="max-w-sm truncate px-4 py-3 text-ink-700" title={bid.name ?? ""}>{bid.name ?? "—"}</td>
          <td className="tabular whitespace-nowrap px-4 py-3 text-xs text-ink-600">
            {[bid.due_date, bid.due_time].filter(Boolean).join(" ") || "—"}
          </td>
          <td className="px-4 py-3">
            {bid.status ? (
              <span className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${statusTone(bid.status)}`}>
                {bid.status}
              </span>
            ) : (
              <span className="text-ink-400">—</span>
            )}
          </td>
          <td className="tabular whitespace-nowrap px-4 py-3 text-xs text-ink-600">{bid.posting_date ?? "—"}</td>
          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-600">{bid.agency_number ?? "—"}</td>
        </tr>
      ))}
    </DataTable>
  );
}
