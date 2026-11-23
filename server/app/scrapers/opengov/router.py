"""OpenGov Procurement API.

Signs in as a vendor, opens Network, reads the Current Opportunities table, stores the rows, and rebuilds the run's Excel from the DB.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import jobs, run_manager
from app.core.filenames import timestamp
from app.db import get_session
from app.scrapers.myflorida import dates
from app.scrapers.opengov.models import EXCEL_COLUMNS, OpenGovBid
from app.scrapers.opengov.scraper import describe_window, execute_run

router = APIRouter(prefix="/opengov", tags=["opengov"])


class ScrapeRequest(BaseModel):
    # Release Date range, ISO yyyy-mm-dd (or the portal's m/d/yyyy). Both ends are
    # inclusive. Both blank: every current opportunity. from_date alone runs
    # through today; to_date alone has no lower bound.
    from_date: str = ""
    to_date: str = ""


def parse_release_window(from_date: str, to_date: str) -> dates.PostingDateRange:
    """The requested Release Date range, or a 400 the console can show as-is."""
    try:
        window = dates.parse(from_date, to_date)
    except dates.DateRangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if window.start and not window.end:
        # "Since the 10th" means up to now. Fixed here, at the start of the run,
        # so the window the run record shows is the one it actually used.
        window = dates.PostingDateRange(window.start, date.today())
        if window.end < window.start:
            raise HTTPException(
                status_code=400,
                detail=f"From date ({window.start.isoformat()}) is in the future — "
                "no bid can have been released yet.",
            )
    return window


@router.post("/scrape")
def start_scrape(request: ScrapeRequest | None = None, live_preview: bool = False) -> dict:
    request = request or ScrapeRequest()
    window = parse_release_window(request.from_date, request.to_date)
    date_from, date_to = window.isoformat()
    search = describe_window(window) or "all current opportunities"

    label = timestamp()  # e.g. 2026-07-30 14-30-05
    folder = run_manager.make_run_folder(f"OpenGov_Bids ({label})")
    run = run_manager.create_run(
        "opengov",
        folder,
        {
            "label": label,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "excel_exported": False,
            "live_preview": live_preview,
        },
    )
    jobs.submit(run["run_id"], execute_run, run["run_id"], window)
    return {"run_id": run["run_id"], "search": search, "folder": run["folder"],
            "date_from": date_from, "date_to": date_to}


@router.get("/scrape/status/{run_id}")
def scrape_status(run_id: str) -> dict:
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return run


@router.get("/scrape/runs")
def scrape_runs() -> dict:
    return {"runs": run_manager.list_runs(scraper="opengov")}


def _bid_to_dict(bid: OpenGovBid) -> dict:
    raw = bid.raw_data or {}
    data = {attr: getattr(bid, attr, None) or raw.get(attr) for attr, _ in EXCEL_COLUMNS}
    data.update(id=bid.id, run_id=bid.run_id)
    return data


@router.get("/bids")
def list_bids(
    run_id: str | None = Query(None, description="Filter by scrape run"),
    query: str = Query("", description="Search title / organization / status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """Return OpenGov opportunities stored in the database, most recent first."""
    stmt = select(OpenGovBid).order_by(OpenGovBid.scraped_at.desc(), OpenGovBid.id.desc())
    if run_id:
        stmt = stmt.where(OpenGovBid.run_id == run_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                OpenGovBid.project_title.ilike(like),
                OpenGovBid.organization.ilike(like),
                OpenGovBid.status.ilike(like),
            )
        )
    try:
        rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
    except OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — check DATABASE_URL in server/.env",
        ) from exc
    return {"bids": [_bid_to_dict(b) for b in rows], "count": len(rows)}
