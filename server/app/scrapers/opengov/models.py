"""Database models for OpenGov Procurement scrape runs and the opportunities
read from the vendor Network's "Current Opportunities" table.

Only what the list shows is stored: opening each bid's detail page (for the
Project ID) triggers a CAPTCHA, so the detail pages are never visited.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OpenGovRun(Base):
    """One row per OpenGov scrape run."""

    __tablename__ = "opengov_runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bids_found: Mapped[int] = mapped_column(Integer, default=0)
    folder: Mapped[str | None] = mapped_column(Text)
    excel_path: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bids: Mapped[list["OpenGovBid"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class OpenGovBid(Base):
    """One row per opportunity in the Current Opportunities table."""

    __tablename__ = "opengov_bids"
    __table_args__ = (UniqueConstraint("run_id", "project_id", name="uq_opengov_run_project_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("opengov_runs.run_id", ondelete="CASCADE"), index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project_id: Mapped[str | None] = mapped_column(String(128), index=True)
    project_title: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(64))
    release_date: Mapped[str | None] = mapped_column(String(64))
    due_date: Mapped[str | None] = mapped_column(String(64))
    detail_url: Mapped[str | None] = mapped_column(Text)

    # Complete original scraped record: {field -> value}.
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    run: Mapped["OpenGovRun"] = relationship(back_populates="bids")


# Column order for the generated Excel, mapped to friendly headers.
EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("project_title", "Project Title"),
    ("organization", "Organization"),
    ("state", "State"),
    ("status", "Status"),
    ("release_date", "Release Date"),
    ("due_date", "Due Date"),
    ("days_remaining", "Days Remaining"),
    # Pass/Reject qualification, same logic as the PHL sheet. The verdict is
    # stored in `raw_data`; a niche-flagged title is shown as REJECT.
    ("decision", "Evaluation Status"),
    ("detail_url", "Bid Link"),
]

#: Columns that are not real DB columns on `OpenGovBid`.
DERIVED_COLUMNS = {"decision", "days_remaining"}
