"""Database models for Texas SmartBuy ESBD (Solicitations) scrape runs and bids."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TxSmartBuyRun(Base):
    """One row per ESBD scrape run."""

    __tablename__ = "txsmartbuy_runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The filters the run applied, as a readable summary.
    search: Mapped[str | None] = mapped_column(Text)
    bids_found: Mapped[int] = mapped_column(Integer, default=0)
    folder: Mapped[str | None] = mapped_column(Text)
    excel_path: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bids: Mapped[list["TxSmartBuyBid"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TxSmartBuyBid(Base):
    """One row of the ESBD "Export to CSV" file."""

    __tablename__ = "txsmartbuy_bids"
    __table_args__ = (UniqueConstraint("run_id", "solicitation_id", name="uq_txsmartbuy_run_solicitation"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("txsmartbuy_runs.run_id", ondelete="CASCADE"), index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    name: Mapped[str | None] = mapped_column(Text)
    solicitation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    due_date: Mapped[str | None] = mapped_column(String(32))
    due_time: Mapped[str | None] = mapped_column(String(32))
    agency_number: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(64))
    posting_date: Mapped[str | None] = mapped_column(String(32))
    created: Mapped[str | None] = mapped_column(String(64))
    last_modified: Mapped[str | None] = mapped_column(String(64))
    nigp_codes: Mapped[str | None] = mapped_column(Text)
    detail_url: Mapped[str | None] = mapped_column(Text)

    # The CSV row exactly as ESBD exported it.
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    run: Mapped["TxSmartBuyRun"] = relationship(back_populates="bids")


# The ESBD CSV's own columns, in its order, plus the solicitation's page.
EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("solicitation_id", "Solicitation ID"),
    ("due_date", "Due Date"),
    ("due_time", "Due Time"),
    ("agency_number", "Agency/Texas SmartBuy Member Number"),
    ("status", "Status"),
    ("posting_date", "Posting Date"),
    ("created", "Created"),
    ("last_modified", "Last Modified"),
    ("nigp_codes", "NIGP Codes"),
    ("detail_url", "Bid Link"),
]
