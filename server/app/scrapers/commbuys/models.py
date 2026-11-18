"""Database models for COMMBUYS (Massachusetts) Bid Solicitation runs and bids."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CommbuysRun(Base):
    """One row per COMMBUYS scrape run."""

    __tablename__ = "commbuys_runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The filters the run applied, as a readable summary.
    search: Mapped[str | None] = mapped_column(Text)
    bids_found: Mapped[int] = mapped_column(Integer, default=0)
    bids_passed: Mapped[int] = mapped_column(Integer, default=0)
    folder: Mapped[str | None] = mapped_column(Text)
    excel_path: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bids: Mapped[list["CommbuysBid"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class CommbuysBid(Base):
    """One open bid from COMMBUYS's bid list, with its Pass / Reject verdict."""

    __tablename__ = "commbuys_bids"
    __table_args__ = (UniqueConstraint("run_id", "bid_number", name="uq_commbuys_run_bid"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("commbuys_runs.run_id", ondelete="CASCADE"), index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bid_number: Mapped[str | None] = mapped_column(String(128), index=True)
    organization: Mapped[str | None] = mapped_column(Text)
    alternate_id: Mapped[str | None] = mapped_column(String(128))
    buyer: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    purchase_method: Mapped[str | None] = mapped_column(String(128))
    opening_date: Mapped[str | None] = mapped_column(String(64))
    # From the bid's public page; the open-bids list does not show it.
    available_date: Mapped[str | None] = mapped_column(String(64))
    detail_url: Mapped[str | None] = mapped_column(Text)
    # PASS or REJECT, from the shared evaluation matrix (see evaluation.py).
    decision: Mapped[str | None] = mapped_column(String(16), index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text)

    # The list row exactly as COMMBUYS showed it.
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    run: Mapped["CommbuysRun"] = relationship(back_populates="bids")


# The open-bids list's columns (less its Q & A / Quotes / Bid Holder links), the
# Available Date read from each bid's page, the page itself, and the verdict.
EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("bid_number", "Bid #"),
    ("organization", "Organization"),
    ("alternate_id", "Alternate Id"),
    ("buyer", "Buyer"),
    ("description", "Description"),
    ("purchase_method", "Purchase Method"),
    ("opening_date", "Bid Opening Date"),
    ("available_date", "Available Date"),
    ("detail_url", "Bid Link"),
    ("decision", "Decision"),
    ("decision_reason", "Reason"),
]
