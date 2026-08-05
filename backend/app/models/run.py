import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RunStatus(StrEnum):
    """Where a run has got to."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(Base):
    """One audit of one repository.

    No API key is stored here, or anywhere else. A key arrives with the request,
    lives in memory for the length of the run, and is never written down.
    """

    __tablename__ = "runs"

    repository_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Stable key for grouping runs of the same repository, so Phase 5 can diff
    # one run against the previous one without parsing URLs.
    repository_slug: Mapped[str] = mapped_column(String(300), nullable=False)

    # Enum, not String: a plain String column hands back a str, so the
    # Mapped[RunStatus] annotation would be a lie and "is" comparisons against
    # the enum would quietly fail. native_enum=False stores it as a VARCHAR, so
    # adding a status later needs no database type change.
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=20), default=RunStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    # Numeric, not Float: this is money, and it is compared against a ceiling.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal(0))
    truncated: Mapped[bool] = mapped_column(default=False)

    findings: Mapped[list["FindingRow"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        # Phase 5 looks up a repository's previous run on every new one.
        Index("ix_runs_slug_created", "repository_slug", "created_at"),
    )


class FindingRow(Base):
    """One finding produced by one auditor during one run.

    Named FindingRow rather than Finding so it cannot be confused with the
    Pydantic Finding that auditors return: this one is what got stored, that one
    is what the model said.
    """

    __tablename__ = "findings"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    auditor: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line: Mapped[int | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[Run] = relationship(back_populates="findings")
