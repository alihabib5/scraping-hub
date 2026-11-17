"""Texas SmartBuy ESBD persistence: read the portal's CSV export, store it in the
DB, and build the per-run Excel from the DB (openpyxl)."""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import excel_style
from app.db import SessionLocal
from app.scrapers.txsmartbuy.models import EXCEL_COLUMNS, TxSmartBuyBid, TxSmartBuyRun

logger = logging.getLogger(__name__)

DETAIL_URL = "https://www.txsmartbuy.gov/esbd/{}"
# ESBD's CSV header -> our field. Read by name, so a column reorder can't scramble rows.
CSV_FIELDS = {header: attr for attr, header in EXCEL_COLUMNS if attr != "detail_url"}
CSV_LIMIT = 20_000  # ESBD: "CSV export is limited to 20,000 results."


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    """The export's rows as records, each with its solicitation's page link."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"ESBD export is missing columns: {', '.join(sorted(missing))}")
        records = []
        for row in reader:
            record = {attr: (row.get(header) or "").strip() for header, attr in CSV_FIELDS.items()}
            if not record["solicitation_id"]:
                continue
            record["detail_url"] = DETAIL_URL.format(quote(record["solicitation_id"]))
            record["raw"] = dict(row)
            records.append(record)
    return records


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
        "folder": run.get("folder"),
        "excel_path": run.get("excel_path"),
    }
    stmt = pg_insert(TxSmartBuyRun).values(**values).on_conflict_do_update(
        index_elements=[TxSmartBuyRun.run_id], set_={k: v for k, v in values.items() if k != "run_id"},
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
    """Upsert the run row and every exported solicitation in one transaction."""
    session = SessionLocal()
    try:
        _upsert_run(session, run)
        seen: set[str] = set()
        for record in records:
            if record["solicitation_id"] in seen:
                continue
            seen.add(record["solicitation_id"])
            values = {attr: (record.get(attr) or None) for attr, _ in EXCEL_COLUMNS}
            values.update(run_id=run["run_id"], raw_data=record.get("raw") or {})
            stmt = pg_insert(TxSmartBuyBid).values(**values).on_conflict_do_update(
                constraint="uq_txsmartbuy_run_solicitation",
                set_={k: v for k, v in values.items() if k not in ("run_id", "solicitation_id")},
            )
            session.execute(stmt)
        session.commit()
        logger.info("[run %s] stored %d ESBD rows in DB", run.get("run_id"), len(seen))
        return len(seen)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _write(rows, out_path: str | Path) -> int:
    workbook, sheet = excel_style.new_workbook("ESBD Solicitations")
    count = excel_style.write_table(sheet, [header for _, header in EXCEL_COLUMNS], rows)
    workbook.save(str(out_path))
    return count


def generate_excel(run_id: str, out_path: str | Path) -> int:
    """Build this run's Excel from txsmartbuy_bids. Returns the row count."""
    session = SessionLocal()
    try:
        bids = session.execute(
            select(TxSmartBuyBid).where(TxSmartBuyBid.run_id == run_id).order_by(TxSmartBuyBid.id)
        ).scalars().all()
    finally:
        session.close()
    return _write(([getattr(b, attr) for attr, _ in EXCEL_COLUMNS] for b in bids), out_path)


def generate_excel_from_records(records: list[dict[str, Any]], out_path: str | Path) -> int:
    """Build the Excel straight from in-memory records (DB-unavailable fallback)."""
    return _write(([r.get(attr) for attr, _ in EXCEL_COLUMNS] for r in records), out_path)
