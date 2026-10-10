import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="created"
    )
    target_database: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    queries: Mapped[list["QueryRecord"]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )


class QueryRecord(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    query_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    calls: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_exec_time_ms: Mapped[Decimal] = mapped_column(
        Numeric(20, 3), nullable=False, default=0
    )
    mean_exec_time_ms: Mapped[Decimal] = mapped_column(
        Numeric(20, 3), nullable=False, default=0
    )
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="queries")
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    query: Mapped["QueryRecord"] = relationship(back_populates="candidates")
    verifications: Mapped[list["Verification"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    verifier: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 3), nullable=True
    )
    candidate_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 3), nullable=True
    )
    baseline_latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 3), nullable=True
    )
    candidate_latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 3), nullable=True
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="verifications")
