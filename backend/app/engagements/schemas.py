from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from datetime import date, datetime
from app.engagements.models import EngagementStatus, Severity


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client_name: str = Field(min_length=1, max_length=255)
    scope: Optional[str] = Field(default=None, max_length=50000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    template_key: Optional[Literal["web", "api", "external", "internal", "active_directory", "cloud"]] = None

    model_config = {"str_strip_whitespace": True}

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        return self


class EngagementUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    client_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    scope: Optional[str] = Field(default=None, max_length=50000)
    status: Optional[EngagementStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    model_config = {"str_strip_whitespace": True}


class EngagementResponse(BaseModel):
    id: str
    name: str
    client_name: str
    scope: Optional[str]
    status: EngagementStatus
    start_date: Optional[date]
    end_date: Optional[date]
    template_key: Optional[str] = None
    created_by: str
    finding_count: int = 0

    model_config = {"from_attributes": True}


class FindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=200000)
    severity: Severity = Severity.info
    cvss_score: Optional[float] = Field(default=None, ge=0, le=10)
    affected_hosts: Optional[str] = Field(default=None, max_length=50000)
    evidence: Optional[str] = Field(default=None, max_length=200000)
    remediation: Optional[str] = Field(default=None, max_length=200000)
    retest_status: Optional[Literal["open", "remediated", "retest_needed", "accepted_risk"]] = None
    retest_due_date: Optional[date] = None

    model_config = {"str_strip_whitespace": True}


class FindingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=200000)
    severity: Optional[Severity] = None
    cvss_score: Optional[float] = Field(default=None, ge=0, le=10)
    affected_hosts: Optional[str] = Field(default=None, max_length=50000)
    evidence: Optional[str] = Field(default=None, max_length=200000)
    remediation: Optional[str] = Field(default=None, max_length=200000)
    retest_status: Optional[
        Literal["open", "remediated", "retest_needed", "accepted_risk"]
    ] = None
    retest_due_date: Optional[date] = None

    model_config = {"str_strip_whitespace": True}


class FindingResponse(BaseModel):
    id: str
    engagement_id: str
    title: str
    description: Optional[str]
    severity: Severity
    cvss_score: Optional[float]
    affected_hosts: Optional[str]
    evidence: Optional[str]
    remediation: Optional[str]
    source: str
    evidence_refs: Optional[list[dict]] = None
    ai_confidence: Optional[float] = None
    ai_inference: bool = False
    retest_status: Optional[str] = None
    retest_due_date: Optional[date] = None

    model_config = {"from_attributes": True}


class AttackPathResponse(BaseModel):
    id: str
    engagement_id: str
    name: str
    description: Optional[str]
    steps: Optional[list]
    risk_level: Optional[str]
    narrative: Optional[str] = None
    mitre_techniques: Optional[list] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: str
    engagement_id: str
    title: str
    format: str
    template_used: Optional[str]
    file_path: Optional[str]
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
