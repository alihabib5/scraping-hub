"""Pass/Reject qualification for OpenGov bids.

Not reimplemented: this is the same logic the Philadelphia scraper runs. The
verdict comes from `philadelphia.evaluation.evaluate` (the shared Rule A/B/C
funnel from `sam.evaluation`, with MANUAL_REVIEW settled the same way), and the
niche flag from `philadelphia.flags` (the client's twenty excluded categories,
derived from SAM's `RULE_B`). One engine means a PURSUE here reads the same as a
PURSUE on the PHL sheet.

OpenGov's list has only a title (no description, no line items), so the title is
what both are judged on. Every bid is kept; the verdict is a column, never a filter.
"""

from __future__ import annotations

from typing import Any

from app.scrapers.philadelphia import evaluation as phl_evaluation
from app.scrapers.philadelphia import flags

#: Stored on the bid's `raw_data` (JSONB), so no schema change is needed.
VERDICT_FIELDS = ("decision", "reason", "rule", "requirement_type")


def _as_phl_record(record: dict[str, Any]) -> dict[str, Any]:
    title = str(record.get("project_title") or "")
    return {
        "bid_number": title[:60] or "unknown",
        "title": title,
        "description": title,
        "organization": record.get("organization"),
        "items": [],
    }


def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    """The matrix verdict for one scraped row. Never raises."""
    verdict = phl_evaluation.evaluate(_as_phl_record(record))
    return {k: verdict.get(k) for k in VERDICT_FIELDS}


def niche_flag(record: dict[str, Any]) -> tuple[str, str]:
    """`(Niche Flag, Niche Flag Reason)` — ("", "") for a bid in scope."""
    phl = _as_phl_record(record)
    return flags.status(phl), flags.reason(phl)
