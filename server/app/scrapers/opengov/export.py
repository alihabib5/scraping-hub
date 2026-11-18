"""OpenGov persistence: store scraped opportunities in the DB and build the
per-run Excel sheet from the DB (shared `excel_style`, like every other portal).

Data path: scrape -> opengov_bids -> generated Excel. One transaction upserts
the run row and every bid.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import excel_style
from app.db import SessionLocal
from app.scrapers.opengov import evaluation
from app.scrapers.opengov.models import DERIVED_COLUMNS, EXCEL_COLUMNS, OpenGovBid, OpenGovRun

logger = logging.getLogger(__name__)

_BID_FIELDS = {attr for attr, _ in EXCEL_COLUMNS} - DERIVED_COLUMNS
SHEET_NAME = "OpenGov Opportunities"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _run_values(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "status": run.get("status"),
        "started_at": _parse_dt(run.get("started_at")),
        "finished_at": _parse_dt(run.get("finished_at")),
        "bids_found": run.get("bids_found", 0),
        "folder": run.get("folder"),
        "excel_path": run.get("excel_path"),
    }


def _upsert_run(session, run: dict[str, Any]) -> None:
    values = _run_values(run)
    stmt = pg_insert(OpenGovRun).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[OpenGovRun.run_id],
        set_={k: v for k, v in values.items() if k != "run_id"},
    )
    session.execute(stmt)


def save_run(run: dict[str, Any]) -> None:
    """Upsert the run-level row in opengov_runs (its own transaction)."""
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
    """Upsert a run's opportunities into opengov_bids in one transaction.

    Rolls back and re-raises on any error so the caller can fall back to an
    Excel-from-records. Returns the number of rows stored.
    """
    session = SessionLocal()
    try:
        _upsert_run(session, run)

        stored = 0
        for record in records:
            values: dict[str, Any] = {f: record.get(f) or None for f in _BID_FIELDS}
            values["run_id"] = run["run_id"]
            values["raw_data"] = {k: v for k, v in record.items() if isinstance(v, (str, int, float, bool, type(None)))}
            session.add(OpenGovBid(**values))
            stored += 1

        session.commit()
        logger.info("[run %s] stored %d bid rows in DB", run.get("run_id"), stored)
        return stored
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _cell(source: Any, attr: str) -> Any:
    """One cell, from a DB row (verdict in `raw_data`) or a scraped record."""
    if isinstance(source, dict):
        record = source
    else:
        record = {**(source.raw_data or {}), "project_title": source.project_title,
                  "organization": source.organization}
    if attr == "decision":
        # An excluded niche is a REJECT whatever the funnel said (as on PHL's sheet).
        if evaluation.niche_flag(record)[0]:
            return "REJECT"
        return record.get("decision")
    if attr == "detail_url" and not isinstance(source, dict):
        return source.detail_url
    return record.get(attr)


def _row_style(values: list[Any]) -> str | None:
    """Same tinting as PHL: red = REJECT (incl. niche-flagged), yellow = needs review."""
    index = {attr: i for i, (attr, _) in enumerate(EXCEL_COLUMNS)}
    decision = str(values[index["decision"]] or "").strip().upper()
    if "REJECT" in decision:
        return "reject"
    if "REVIEW" in decision or "PENDING" in decision:
        return "review"
    return None


def _write(rows: list[Any], out_path: str | Path) -> int:
    workbook, sheet = excel_style.new_workbook(SHEET_NAME)
    count = excel_style.write_table(
        sheet,
        [header for _, header in EXCEL_COLUMNS],
        ([_cell(row, attr) for attr, _ in EXCEL_COLUMNS] for row in rows),
        row_style=_row_style,
    )
    workbook.save(str(out_path))
    return count


def generate_excel(run_id: str, out_path: str | Path) -> int:
    """Build this run's Excel sheet from opengov_bids. Returns the row count."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(OpenGovBid).where(OpenGovBid.run_id == run_id).order_by(OpenGovBid.id)
        ).scalars().all()
    finally:
        session.close()

    count = _write(rows, out_path)
    logger.info("[run %s] wrote %d rows to %s", run_id, count, out_path)
    return count


def generate_excel_from_records(records: list[dict[str, Any]], out_path: str | Path) -> int:
    """Build the Excel straight from in-memory records (DB-unavailable fallback)."""
    return _write(records, out_path)
