"""Pass / Reject / Manual Review for COMMBUYS bids: the company's keyword matrix.

`app.scrapers.sam.evaluation.evaluate` is the one engine (Rule A/B/C funnel with
the live kill-word list edited in the console), the same one SAM, Philadelphia
and Unison use, so a PASS here means what it means on their sheets. Its verdicts
are shown as PASS (PURSUE), REJECT, or MANUAL REVIEW: a service the matrix does
not list either way is left for a person rather than guessed. COMMBUYS gives one
line of text per bid — its Description — so that is what is judged.
"""

from __future__ import annotations

import logging
from typing import Any

from app.scrapers.sam.evaluation import evaluate as evaluate_bid

logger = logging.getLogger(__name__)

PASS, REJECT, REVIEW = "PASS", "REJECT", "MANUAL REVIEW"
_SHOWN = {"PURSUE": PASS, "REJECT": REJECT}  # anything else is for a person


def decide(record: dict[str, Any]) -> tuple[str, str]:
    """(PASS, REJECT or MANUAL REVIEW, the reason). Never raises: a bid that cannot
    be judged goes to MANUAL REVIEW with the reason."""
    bid_id = record.get("bid_number") or "unknown"
    text = " ".join(str(record.get("description") or "").split())
    try:
        verdict = evaluate_bid(bid_id, text, title=text)
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
