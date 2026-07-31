import uuid
import enum
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, String, Text, Date, DateTime, ForeignKey, Numeric, Integer, Enum as SAEnum, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class EngagementStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    archived = "archived"


class Severity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Engagement(Base, TimestampMixin):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[EngagementStatus] = mapped_column(
        SAEnum(EngagementStatus), default=EngagementStatus.active
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    template_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="engagement",
        lazy="raise",
    )


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(String(36), ForeignKey("engagements.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.info)
    cvss_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    affected_hosts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    evidence_refs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    ai_inference: Mapped[bool] = mapped_column(Boolean, default=False)
    retest_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # open, remediated, retest_needed, accepted_risk
    retest_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))

    engagement: Mapped["Engagement"] = relationship(back_populates="findings")


class FindingHistory(Base):
    """Immutable local audit trail for meaningful finding changes."""

    __tablename__ = "finding_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIFindingDraft(Base, TimestampMixin):
    """Evidence-grounded AI proposal that requires an explicit local review."""

    __tablename__ = "ai_finding_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    target_finding_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(20), default="create", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.info)
    cvss_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    affected_hosts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AttackPath(Base, TimestampMixin):
    __tablename__ = "attack_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(String(36), ForeignKey("engagements.id"))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mitre_techniques: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(String(36), ForeignKey("engagements.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str] = mapped_column(String(10), default="pdf")
    template_used: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))


class ScanUpload(Base, TimestampMixin):
    __tablename__ = "scan_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(String(36), ForeignKey("engagements.id"))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(50), default="nmap")
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))


class ScanSnapshot(Base):
    """A versioned, immutable interpretation of an explicit scan set."""

    __tablename__ = "scan_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_scan_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), default="structured-v1", nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanObservation(Base):
    """Normalized scanner fact used for deterministic snapshot comparison."""

    __tablename__ = "scan_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scan_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    host: Mapped[str] = mapped_column(String(500), nullable=False)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evidence_ref: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class EvidenceAttachment(Base):
    __tablename__ = "evidence_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("findings.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
