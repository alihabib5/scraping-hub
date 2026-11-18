from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.core import jobs, run_manager
from app.core.filenames import timestamp
from app.db import get_session
from app.scrapers.commbuys import filters
from app.scrapers.commbuys.models import EXCEL_COLUMNS, CommbuysBid
from app.scrapers.commbuys.scraper import execute_run

router = APIRouter(prefix="/commbuys", tags=["commbuys"])


class ScrapeRequest(BaseModel):
    """The Available Date range (YYYY-MM-DD, inclusive). Both blank: every open bid."""

    available_from: str = ""
    available_to: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip() if isinstance(v, str) or v is None else v

    @field_validator("available_from", "available_to")
    @classmethod
    def _date(cls, v):
        filters.parse_iso(v)  # raises on anything that is not YYYY-MM-DD
        return v


@router.get("/filters")
def filter_options() -> dict:
    """Whether the console can start a run (the credentials are in server/.env)."""
    return {"credentials_set": bool(settings.commbuys_username and settings.commbuys_password)}


@router.post("/scrape")
def start_scrape(request: ScrapeRequest, live_preview: bool = False) -> dict:
    if not (settings.commbuys_username and settings.commbuys_password):
        raise HTTPException(status_code=400, detail="COMMBUYS_USERNAME / COMMBUYS_PASSWORD are not set in server/.env.")
    criteria = request.model_dump()
    if criteria["available_from"] and criteria["available_to"] and criteria["available_from"] > criteria["available_to"]:
        raise HTTPException(status_code=422, detail="Available Date From is after Available Date To.")
    search = filters.summary(criteria)
    label = timestamp()
    folder = run_manager.make_run_folder(f"COMMBUYS ({label})")
    run = run_manager.create_run(
        "commbuys",
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
    return {"runs": run_manager.list_runs(scraper="commbuys")}


@router.get("/bids")
def list_bids(
    run_id: str | None = Query(None, description="Filter by scrape run"),
    query: str = Query("", description="Search bid # / description / organization"),
    decision: str = Query("", description="PASS or REJECT"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """COMMBUYS bids stored in the database, most recent first."""
    stmt = select(CommbuysBid).order_by(CommbuysBid.scraped_at.desc(), CommbuysBid.id.desc())
    if run_id:
        stmt = stmt.where(CommbuysBid.run_id == run_id)
    if decision:
        stmt = stmt.where(CommbuysBid.decision == decision.upper())
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(CommbuysBid.bid_number.ilike(like), CommbuysBid.description.ilike(like),
                              CommbuysBid.organization.ilike(like)))
    try:
        rows = session.execute(stmt.limit(limit).offset(offset)).scalars().all()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable — check DATABASE_URL in server/.env") from exc
    return {"bids": [{attr: getattr(b, attr) for attr, _ in EXCEL_COLUMNS} | {"id": b.id, "run_id": b.run_id} for b in rows],
            "count": len(rows)}
