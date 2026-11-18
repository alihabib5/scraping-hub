"""COMMBUYS persistence: store the scraped bids in the DB and build the per-run
Excel (one sheet, every bid with its verdict) from it."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import excel_style
from app.db import SessionLocal
from app.scrapers.commbuys.evaluation import REJECT, REVIEW
from app.scrapers.commbuys.models import EXCEL_COLUMNS, CommbuysBid, CommbuysRun

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _upsert_run(session, run: dict[str, Any]) -> None:
    values = {
        "run_id": run["run_id"],
        "status": run.get("status"),
        "started_at": _parse_dt(run.get("started_at")),
        "finished_at": _parse_dt(run.get("finished_at")),
        "search": run.get("search"),
        "bids_found": run.get("bids_found", 0),
        "bids_passed": run.get("bids_passed", 0),
        "folder": run.get("folder"),
        "excel_path": run.get("excel_path"),
    }
    stmt = pg_insert(CommbuysRun).values(**values).on_conflict_do_update(
        index_elements=[CommbuysRun.run_id], set_={k: v for k, v in values.items() if k != "run_id"},
    )
    session.execute(stmt)


def save_run(run: dict[str, Any]) -> None:
    session = SessionLocal()
    try:
        _upsert_run(session, run)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_bids(run: dict[str, Any], records: list[dict[str, Any]]) -> int:
    """Upsert the run row and every exported bid in one transaction."""
    session = SessionLocal()
    try:
        _upsert_run(session, run)
        seen: set[str] = set()
        for record in records:
            if record["bid_number"] in seen:
                continue
            seen.add(record["bid_number"])
            values = {attr: (record.get(attr) or None) for attr, _ in EXCEL_COLUMNS}
            values.update(run_id=run["run_id"], raw_data=record.get("raw") or {})
            stmt = pg_insert(CommbuysBid).values(**values).on_conflict_do_update(
                constraint="uq_commbuys_run_bid",
                set_={k: v for k, v in values.items() if k not in ("run_id", "bid_number")},
            )
            session.execute(stmt)
        session.commit()
        logger.info("[run %s] stored %d COMMBUYS rows in DB", run.get("run_id"), len(seen))
        return len(seen)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_DECISION = [attr for attr, _ in EXCEL_COLUMNS].index("decision")
_TINT = {REJECT: "reject", REVIEW: "review"}  # PASS rows are left plain


def _write(records: list[dict[str, Any]], out_path: str | Path) -> int:
    """One sheet: every bid with its Decision (PASS / REJECT / MANUAL REVIEW) and
    reason; REJECT rows tinted red, MANUAL REVIEW rows yellow."""
    workbook, sheet = excel_style.new_workbook("COMMBUYS Bids")
    count = excel_style.write_table(
        sheet,
        [header for _, header in EXCEL_COLUMNS],
        ([r.get(attr) for attr, _ in EXCEL_COLUMNS] for r in records),
        row_style=lambda values: _TINT.get(values[_DECISION]),
    )
    workbook.save(str(out_path))
    return count


def generate_excel(run_id: str, out_path: str | Path) -> int:
    """Build this run's Excel from commbuys_bids. Returns the row count."""
    session = SessionLocal()
    try:
        bids = session.execute(
            select(CommbuysBid).where(CommbuysBid.run_id == run_id).order_by(CommbuysBid.id)
        ).scalars().all()
    finally:
        session.close()
    return _write([{attr: getattr(b, attr) for attr, _ in EXCEL_COLUMNS} for b in bids], out_path)


def generate_excel_from_records(records: list[dict[str, Any]], out_path: str | Path) -> int:
    """Build the Excel straight from in-memory records (DB-unavailable fallback)."""
    return _write(records, out_path)
