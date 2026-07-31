"""Validation boundaries for structured data returned by AI providers.

AI responses are external input even when they come from a configured provider.
Keep provider quirks and unexpectedly large responses from reaching database
models or report generation.
"""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.engagements.schemas import FindingCreate


MAX_AI_RECORDS = 1000
MAX_ATTACK_PATH_STEPS_SIZE = 500_000


class AIFindingCandidate(FindingCreate):
    evidence_refs: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(default_factory=list, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("evidence_refs")
    @classmethod
    def evidence_refs_are_unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AttackPathStepCandidate(BaseModel):
    order: int = Field(ge=1, le=1000)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    finding_id: str | None = Field(default=None, max_length=36)
    finding_title: str | None = Field(default=None, max_length=500)

    model_config = {"str_strip_whitespace": True}


class AttackPathCandidate(BaseModel):
    name: str = Field(default="Unnamed Path", min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=200_000)
    steps: list[AttackPathStepCandidate] = Field(default_factory=list, max_length=1000)
    risk_level: Literal["critical", "high", "medium", "low"] | None = None
    target_hosts: str | None = Field(default=None, max_length=50_000)

    model_config = {"str_strip_whitespace": True}

    @field_validator("steps")
    @classmethod
    def steps_fit_storage_limit(
        cls, value: list[AttackPathStepCandidate]
    ) -> list[AttackPathStepCandidate]:
        serialized = [step.model_dump(mode="json") for step in value]
        if len(json.dumps(serialized).encode("utf-8")) > MAX_ATTACK_PATH_STEPS_SIZE:
            raise ValueError("steps exceed the 500 KB storage limit")
        return value


class ADPathNodeCandidate(BaseModel):
    name: str = Field(default="?", min_length=1, max_length=500)
    type: str = Field(default="unknown", min_length=1, max_length=50)
    technique: str = Field(default="", max_length=2000)

    model_config = {"str_strip_whitespace": True}


class ADAttackPathCandidate(BaseModel):
    name: str = Field(default="Unnamed Path", min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=200_000)
    risk_level: Literal["critical", "high", "medium", "low"] = "medium"
    path_nodes: list[ADPathNodeCandidate] = Field(default_factory=list, max_length=1000)
    remediation: str | None = Field(default=None, max_length=200_000)
    evidence_refs: list[
        Annotated[str, Field(min_length=1, max_length=200)]
    ] = Field(default_factory=list, max_length=1000)

    model_config = {"str_strip_whitespace": True}

    @field_validator("path_nodes")
    @classmethod
    def nodes_fit_storage_limit(
        cls,
        value: list[ADPathNodeCandidate],
    ) -> list[ADPathNodeCandidate]:
        serialized = [node.model_dump(mode="json") for node in value]
        if len(json.dumps(serialized).encode("utf-8")) > MAX_ATTACK_PATH_STEPS_SIZE:
            raise ValueError("path nodes exceed the 500 KB storage limit")
        return value


class GapCandidate(BaseModel):
    category: str = Field(min_length=1, max_length=500)
    item: str = Field(min_length=1, max_length=1000)
    severity: Literal["high", "medium", "low"]
    type: Literal["not_tested", "undertested"]
    reason: str = Field(min_length=1, max_length=20_000)
    recommendation: str = Field(min_length=1, max_length=20_000)
    methodology_ref: str = Field(default="", max_length=2000)
    supporting_refs: list[
        Annotated[str, Field(min_length=1, max_length=200)]
    ] = Field(default_factory=list, max_length=100)

    model_config = {"str_strip_whitespace": True}


class OutOfScopeCandidate(BaseModel):
    category: str = Field(min_length=1, max_length=500)
    item: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=20_000)
    supporting_refs: list[
        Annotated[str, Field(min_length=1, max_length=200)]
    ] = Field(default_factory=list, max_length=100)

    model_config = {"str_strip_whitespace": True}


class GapAnalysisCandidate(BaseModel):
    engagement_type: list[
        Annotated[str, Field(min_length=1, max_length=50)]
    ] = Field(default_factory=list, max_length=20)
    scope_summary: str = Field(default="", max_length=20_000)
    gaps: list[GapCandidate] = Field(default_factory=list, max_length=1000)
    out_of_scope_items: list[OutOfScopeCandidate] = Field(
        default_factory=list,
        max_length=1000,
    )
    coverage_score: float = Field(ge=0, le=100)
    summary: str = Field(default="", max_length=20_000)

    model_config = {"str_strip_whitespace": True}


class MITRETechniqueCandidate(BaseModel):
    technique_id: str = Field(min_length=1, max_length=50)
    technique_name: str = Field(min_length=1, max_length=500)
    step: int | None = Field(default=None, ge=1, le=1000)


class PathNarrativeCandidate(BaseModel):
    narrative: str = Field(min_length=1, max_length=500_000)
    executive_summary: str = Field(default="", max_length=50_000)
    mitre_techniques: list[MITRETechniqueCandidate] = Field(default_factory=list, max_length=1000)
    impact_rating: Literal["critical", "high", "medium", "low"]
    estimated_time: str = Field(default="", max_length=5000)
    prerequisites: str = Field(default="", max_length=20_000)
    citations: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=1000
    )

    model_config = {"str_strip_whitespace": True}


class FullNarrativeCandidate(BaseModel):
    full_narrative: str = Field(min_length=1, max_length=1_000_000)
    executive_summary: str = Field(default="", max_length=50_000)
    key_risks: list[Annotated[str, Field(min_length=1, max_length=20_000)]] = Field(
        default_factory=list, max_length=1000
    )
    mitre_techniques: list[MITRETechniqueCandidate] = Field(default_factory=list, max_length=1000)
    overall_risk: Literal["critical", "high", "medium", "low"]
    citations: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=5000
    )

    model_config = {"str_strip_whitespace": True}


def _validate_list(raw: object, model: type[BaseModel], label: str) -> list[BaseModel]:
    if not isinstance(raw, list):
        raise ValueError(f"AI returned {label} in an invalid format")
    if len(raw) > MAX_AI_RECORDS:
        raise ValueError(f"AI returned more than {MAX_AI_RECORDS} {label}")

    validated = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"AI returned invalid {label} record {index + 1}")
        try:
            validated.append(model.model_validate(item))
        except ValidationError as exc:
            message = exc.errors()[0]["msg"]
            raise ValueError(
                f"AI returned invalid {label} record {index + 1}: {message}"
            ) from exc
    return validated


def validate_ai_findings(raw: object) -> list[AIFindingCandidate]:
    return _validate_list(raw, AIFindingCandidate, "finding")


def validate_ai_attack_paths(raw: object) -> list[AttackPathCandidate]:
    return _validate_list(raw, AttackPathCandidate, "attack path")


def validate_ai_ad_paths(raw: object) -> list[ADAttackPathCandidate]:
    return _validate_list(raw, ADAttackPathCandidate, "Active Directory path")


def validate_gap_analysis(raw: object) -> GapAnalysisCandidate:
    if not isinstance(raw, dict):
        raise ValueError("AI returned gap analysis in an invalid format")
    try:
        return GapAnalysisCandidate.model_validate(raw)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        raise ValueError(f"AI returned invalid gap analysis: {message}") from exc


def validate_path_narrative(raw: object) -> PathNarrativeCandidate:
    if not isinstance(raw, dict):
        raise ValueError("AI returned path narrative in an invalid format")
    try:
        return PathNarrativeCandidate.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"AI returned invalid path narrative: {exc.errors()[0]['msg']}"
        ) from exc


def validate_full_narrative(raw: object) -> FullNarrativeCandidate:
    if not isinstance(raw, dict):
        raise ValueError("AI returned engagement narrative in an invalid format")
    try:
        return FullNarrativeCandidate.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(
            f"AI returned invalid engagement narrative: {exc.errors()[0]['msg']}"
        ) from exc
