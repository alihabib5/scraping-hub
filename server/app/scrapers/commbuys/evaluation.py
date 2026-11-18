"""PASS / REJECT / MANUAL REVIEW for COMMBUYS bids.

COMMBUYS and PHLContracts are the same platform (Periscope BSO), so a COMMBUYS
bid is read the way Philadelphia reads one — header table and line items — and
its text is put together by Philadelphia's own `build_full_text` (description,
the header fields that say what is bought, the line items). That text goes to the
shared Rule A/B/C funnel (`app.scrapers.sam.evaluation.evaluate`, the one SAM,
Philadelphia and Unison use, with the live kill-words).

Two Philadelphia steps are deliberately left out. Its line-item hint treats
quantified items as proof of a supply, but a COMMBUYS item is "1.0 EA" on almost
every bid — roof replacements, guard services, property sales — so here it
proved nothing and passed services as hardware (19 Nov, 94 live bids: 51 PASS,
most of them wrong). And its settling of the undecided rejects every service the
allowed list does not name, which without that evidence would also reject the
gloves and trucks. So an undecided bid stays MANUAL REVIEW for a person.
"""

from __future__ import annotations

import logging
from typing import Any

from app.scrapers.philadelphia.evaluation import build_full_text
from app.scrapers.sam.evaluation import evaluate as evaluate_bid

logger = logging.getLogger(__name__)

PASS, REJECT, REVIEW = "PASS", "REJECT", "MANUAL REVIEW"
_SHOWN = {"PURSUE": PASS, "REJECT": REJECT}  # anything else is for a person


def decide(record: dict[str, Any]) -> tuple[str, str]:
    """(PASS, REJECT or MANUAL REVIEW, the reason). Never raises."""
    if record.get("detail_error"):
        # Judged on its title alone an unread bid could pass unseen; a person checks it.
        return REVIEW, f"The bid's page could not be read ({record['detail_error']}) — check it on COMMBUYS."
    bid_id = record.get("bid_number") or "unknown"
    title = " ".join(str(record.get("description") or "").split())
    try:
        verdict = evaluate_bid(bid_id, build_full_text(record), title=title)
    except Exception as exc:  # noqa: BLE001 — a verdict must never sink a bid
        logger.exception("[commbuys eval] %s could not be evaluated", bid_id)
        return REVIEW, f"Could not be evaluated ({exc.__class__.__name__}) — check it by hand."
    return _SHOWN.get(verdict.get("decision"), REVIEW), verdict.get("reason") or ""


def apply(records: list[dict[str, Any]]) -> int:
    """Set `decision` / `decision_reason` on every record. Returns how many passed."""
    for record in records:
        record["decision"], record["decision_reason"] = decide(record)
    counts = {d: sum(r["decision"] == d for r in records) for d in (PASS, REJECT, REVIEW)}
    logger.info("[commbuys eval] %d bid(s): %d PASS, %d REJECT, %d MANUAL REVIEW",
                len(records), counts[PASS], counts[REJECT], counts[REVIEW])
    return counts[PASS]
