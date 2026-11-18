"use client";

import type { BidResult } from "@/lib/api";
import { DataTable } from "@/components/ui";

function decisionTone(decision: string): string {
  switch (decision.toUpperCase()) {
    case "PURSUE":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "REJECT":
      return "border-rose-200 bg-rose-50 text-rose-700";
    case "MANUAL_REVIEW":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-ink-200 bg-ink-50 text-ink-600";
  }
}

/** The opportunities a run has captured so far. */
export default function OpenGovResults({ bids }: { bids: BidResult[] }) {
  if (bids.length === 0) return null;

  return (
    <DataTable
      caption={`Results · ${bids.length} ${bids.length === 1 ? "opportunity" : "opportunities"}`}
      headers={[
        { label: "Decision" },
        { label: "Project Title" },
        { label: "Organization" },
        { label: "State" },
        { label: "Status" },
        { label: "Released" },
        { label: "Due" },
      ]}
    >
      {bids.map((bid, index) => (
        <tr key={`${bid.title ?? "bid"}-${index}`} className="transition hover:bg-ink-50">
          <td className="px-4 py-3">
            {(() => {
              // Red when the matrix says REJECT or the title names an excluded niche (as on the PHL sheet).
              const decision = bid.niche_flag ? "REJECT" : (bid.decision ?? "PENDING");
              const why = bid.niche_flag_reason || bid.reason || "";
              return (
                <span
                  className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${decisionTone(decision)}`}
                  title={why}
                >
                  {decision.replace("_", " ")}
                </span>
              );
            })()}
          </td>
          <td className="max-w-md truncate px-4 py-3 text-ink-700" title={bid.title ?? ""}>
            {bid.detail_url ? (
              <a href={bid.detail_url} target="_blank" rel="noreferrer" className="hover:underline">
                {bid.title ?? "—"}
              </a>
            ) : (
              (bid.title ?? "—")
            )}
          </td>
          <td className="max-w-xs truncate px-4 py-3 text-ink-600" title={bid.organization ?? ""}>
            {bid.organization ?? "—"}
          </td>
          <td className="whitespace-nowrap px-4 py-3 text-ink-600">{bid.state ?? "—"}</td>
          <td className="whitespace-nowrap px-4 py-3 text-ink-600">{bid.status ?? "—"}</td>
          <td className="whitespace-nowrap px-4 py-3 text-ink-600">{bid.release_date ?? "—"}</td>
          <td className="whitespace-nowrap px-4 py-3 text-ink-600">{bid.due_date ?? "—"}</td>
        </tr>
      ))}
    </DataTable>
  );
}
