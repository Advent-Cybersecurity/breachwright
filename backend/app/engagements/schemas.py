from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.engagements.models import EngagementStatus, Severity


class EngagementCreate(BaseModel):
    name: str
    client_name: str
    scope: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class EngagementUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[EngagementStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class EngagementResponse(BaseModel):
    id: str
    name: str
    client_name: str
    scope: Optional[str]
    status: EngagementStatus
    start_date: Optional[date]
    end_date: Optional[date]
    created_by: str
    finding_count: int = 0

    model_config = {"from_attributes": True}


class FindingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    severity: Severity = Severity.info
    cvss_score: Optional[float] = None
    affected_hosts: Optional[str] = None
    evidence: Optional[str] = None
    remediation: Optional[str] = None


class FindingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    cvss_score: Optional[float] = None
    affected_hosts: Optional[str] = None
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    retest_status: Optional[str] = None


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
    retest_status: Optional[str] = None

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
