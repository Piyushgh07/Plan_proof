"""Create initial Plan Proof metadata schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_app_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("target_database", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_fingerprint", sa.String(128), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("calls", sa.BigInteger(), nullable=False),
        sa.Column("total_exec_time_ms", sa.Numeric(20, 3), nullable=False),
        sa.Column("mean_exec_time_ms", sa.Numeric(20, 3), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=True),
    )

    op.create_index(
        "ix_queries_query_fingerprint",
        "queries",
        ["query_fingerprint"],
    )

    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "query_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("queries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("proposal_sql", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
    )

    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verifier", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("baseline_cost", sa.Numeric(20, 3), nullable=True),
        sa.Column("candidate_cost", sa.Numeric(20, 3), nullable=True),
        sa.Column("baseline_latency_ms", sa.Numeric(20, 3), nullable=True),
        sa.Column("candidate_latency_ms", sa.Numeric(20, 3), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("verifications")
    op.drop_table("candidates")
    op.drop_index(
        "ix_queries_query_fingerprint",
        table_name="queries",
    )
    op.drop_table("queries")
    op.drop_table("analysis_runs")
