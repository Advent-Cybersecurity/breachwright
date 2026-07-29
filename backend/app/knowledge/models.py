"""Cross-Engagement Intelligence — Knowledge Base Models.

Tracks finding types across all engagements, enabling trend analysis,
pattern detection, and AI-driven recommendations.

Each unique finding type (e.g. "SMB Signing Disabled") gets a KnowledgeEntry.
Each time that finding appears in an engagement, a FindingLink connects them.
This lets us answer: "Where else have we seen this?", "What's trending?",
and "Based on this environment, what else should we test?"
"""
import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Text, DateTime, Float, Integer, ForeignKey,
    Enum as SAEnum, JSON, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class FindingCategory(str, enum.Enum):
    network = "network"
    web = "web"
    authentication = "authentication"
    authorization = "authorization"
    cryptography = "cryptography"
    configuration = "configuration"
    active_directory = "active_directory"
    cloud = "cloud"
    wireless = "wireless"
    social_engineering = "social_engineering"
    physical = "physical"
    other = "other"


class KnowledgeEntry(Base, TimestampMixin):
    """A canonical finding type that appears across engagements.

    Think of this as the "template" for a finding — the idealized version
    that gets refined as we see more instances. The canonical_title,
    description, and remediation improve over time via AI refinement.
    """
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Stable fingerprint for matching — derived from normalized title + category
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[FindingCategory] = mapped_column(
        SAEnum(FindingCategory), default=FindingCategory.other
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    default_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    default_cvss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Standards references
    cwe_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mitre_attack_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Aggregate stats (updated on each link)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_client_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Relationships
    finding_links: Mapped[list["FindingKnowledgeLink"]] = relationship(
        back_populates="knowledge_entry", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_knowledge_category_severity", "category", "default_severity"),
    )


class FindingKnowledgeLink(Base):
    """Links a specific finding instance to its knowledge base entry.

    Denormalizes engagement_id and client_name for fast cross-engagement
    queries without requiring joins through findings → engagements.
    """
    __tablename__ = "finding_knowledge_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    knowledge_entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_entries.id", ondelete="CASCADE"), index=True
    )
    # Denormalized for query performance
    engagement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    knowledge_entry: Mapped["KnowledgeEntry"] = relationship(
        back_populates="finding_links"
    )

    __table_args__ = (
        Index("ix_fkl_knowledge_client", "knowledge_entry_id", "client_name"),
        Index("ix_fkl_engagement", "engagement_id"),
    )
