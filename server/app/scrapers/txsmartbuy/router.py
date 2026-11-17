from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import jobs, run_manager
from app.core.filenames import timestamp
from app.db import get_session
from app.scrapers.txsmartbuy import filters
from app.scrapers.txsmartbuy.models import EXCEL_COLUMNS, TxSmartBuyBid
from app.scrapers.txsmartbuy.scraper import execute_run

router = APIRouter(prefix="/txsmartbuy", tags=["txsmartbuy"])


class ScrapeRequest(BaseModel):
    """ESBD's Solicitations filters. All optional: empty searches everything."""

    agency: str = ""
    agency_number: str = ""
    status: str = ""
    class_item_codes: str = ""
    keyword: str = ""
    solicitation_id: str = ""
    date_range: str = "custom"
    start_date: str = ""  # YYYY-MM-DD; only used with date_range "custom"
    end_date: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip() if isinstance(v, str) or v is None else v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in filters.STATUSES:
            raise ValueError(f"status must be one of {sorted(filters.STATUSES)}")
        return v

    @field_validator("date_range")
    @classmethod
    def _date_range(cls, v):
        if v not in filters.DATE_RANGES:
            raise ValueError(f"date_range must be one of {sorted(filters.DATE_RANGES)}")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def _date(cls, v):
        filters.portal_date(v)  # raises on anything that is not YYYY-MM-DD
        return v


@router.get("/filters")
def filter_options() -> dict:
    """What the console's filter form offers, mirroring ESBD's own dropdowns."""
    return {
        "agencies": filters.agencies(),
        "statuses": [{"value": k, "label": v} for k, v in filters.STATUSES.items()],
        "date_ranges": [{"value": k, "label": v} for k, v in filters.DATE_RANGES.items()],
    }


@router.post("/scrape")
def start_scrape(request: ScrapeRequest, live_preview: bool = False) -> dict:
    criteria = request.model_dump()
    if criteria["start_date"] and criteria["end_date"] and criteria["start_date"] > criteria["end_date"]:
        raise HTTPException(status_code=422, detail="Start date is after end date.")
    search = filters.summary(criteria)
    label = timestamp()
    folder = run_manager.make_run_folder(f"TxSmartBuy ({label})")
    run = run_manager.create_run(
        "txsmartbuy",
        folder,
        {"label": label, "search": search, "criteria": criteria, "excel_exported": False, "live_preview": live_preview},
    )
    jobs.submit(run["run_id"], execute_run, run["run_id"], criteria)
    return {"run_id": run["run_id"], "search": search, "folder": run["folder"]}


@router.get("/scrape/status/{run_id}")
def scrape_status(run_id: str) -> dict:
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return run


@router.get("/scrape/runs")
def scrape_runs() -> dict:
    return {"runs": run_manager.list_runs(scraper="txsmartbuy")}


@router.get("/bids")
def list_bids(
    run_id: str | None = Query(None, description="Filter by scrape run"),
    query: str = Query("", description="Search name / solicitation ID / NIGP codes"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """ESBD solicitations stored in the database, most recent first."""
    stmt = select(TxSmartBuyBid).order_by(TxSmartBuyBid.scraped_at.desc(), TxSmartBuyBid.id.desc())
    if run_id:
        stmt = stmt.where(TxSmartBuyBid.run_id == run_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(TxSmartBuyBid.name.ilike(like), TxSmartBuyBid.solicitation_id.ilike(like),
                              TxSmartBuyBid.nigp_codes.ilike(like)))
    try:
        rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable — check DATABASE_URL in server/.env") from exc
    return {"bids": [{attr: getattr(b, attr) for attr, _ in EXCEL_COLUMNS} | {"id": b.id, "run_id": b.run_id} for b in rows],
            "count": len(rows)}
