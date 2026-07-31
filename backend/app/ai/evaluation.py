"""Deterministic quality metrics for sanitized AI analysis fixtures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _hosts(item: dict) -> set[str]:
    value = item.get("affected_hosts") or ""
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def _similarity(expected: dict, actual: dict) -> float:
    title_score = SequenceMatcher(
        None,
        _normalize_title(expected.get("title", "")),
        _normalize_title(actual.get("title", "")),
    ).ratio()
    expected_hosts = _hosts(expected)
    actual_hosts = _hosts(actual)
    if expected_hosts and actual_hosts and expected_hosts & actual_hosts:
        title_score = min(1.0, title_score + 0.1)
    return title_score


@dataclass(frozen=True)
class EvaluationMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    severity_accuracy: float
    evidence_accuracy: float
    grounded_rate: float

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_findings(
    expected: list[dict],
    actual: list[dict],
    allowed_evidence_ids: set[str],
    *,
    similarity_threshold: float = 0.75,
) -> EvaluationMetrics:
    unmatched = set(range(len(actual)))
    matches: list[tuple[dict, dict]] = []
    for expected_item in expected:
        candidates = [
            (index, _similarity(expected_item, actual[index]))
            for index in unmatched
        ]
        if not candidates:
            continue
        best_index, best_score = max(candidates, key=lambda pair: pair[1])
        if best_score >= similarity_threshold:
            matches.append((expected_item, actual[best_index]))
            unmatched.remove(best_index)

    true_positives = len(matches)
    false_positives = len(actual) - true_positives
    false_negatives = len(expected) - true_positives
    precision = true_positives / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = true_positives / len(expected) if expected else 1.0
    severity_accuracy = (
        sum(expected_item.get("severity") == actual_item.get("severity") for expected_item, actual_item in matches)
        / true_positives
        if true_positives
        else (1.0 if not expected else 0.0)
    )
    evidence_accuracy = (
        sum(
            bool(set(expected_item.get("evidence_refs", [])) & set(actual_item.get("evidence_refs", [])))
            for expected_item, actual_item in matches
        )
        / true_positives
        if true_positives
        else (1.0 if not expected else 0.0)
    )
    grounded_rate = (
        sum(
            bool(item.get("evidence_refs"))
            and set(item["evidence_refs"]).issubset(allowed_evidence_ids)
            for item in actual
        )
        / len(actual)
        if actual
        else 1.0
    )
    return EvaluationMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=round(precision, 4),
        recall=round(recall, 4),
        severity_accuracy=round(severity_accuracy, 4),
        evidence_accuracy=round(evidence_accuracy, 4),
        grounded_rate=round(grounded_rate, 4),
    )


def meets_release_baseline(metrics: EvaluationMetrics) -> bool:
    return (
        metrics.precision >= 0.95
        and metrics.recall >= 0.90
        and metrics.severity_accuracy >= 0.90
        and metrics.evidence_accuracy == 1.0
        and metrics.grounded_rate == 1.0
    )
