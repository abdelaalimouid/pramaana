"""PRAMAANA Agent 4 — Reasoner / orchestrator.

Judging criterion: IDP Innovation (30%) — multi-step agentic loop with visible reasoning traces.
Orchestrates: Extract → Validate (2A+2B+2C) → Score in a single traced run.
"""
import mlflow
from src.schemas.facility import RawFacilityRow, ValidationFlags, TrustScore
from src.agents import extractor, validator_internal, validator_tavily, validator_stat
from src.agents.trust_scorer import score as compute_score
from src.tracing import trace_agent_run


@trace_agent_run("reasoner")
def reason(
    row: RawFacilityRow,
    facility_id: str,
    pin_stats: dict,
) -> TrustScore:
    """Full single-facility pipeline: raw row → TrustScore with MLflow trace.

    pin_stats: pre-computed PIN-code statistics from validator_stat.build_pin_code_stats().
    """
    with mlflow.start_span(name="step1_extract", span_type="CHAIN"):
        extracted = extractor.extract(row, facility_id)

    with mlflow.start_span(name="step2a_internal_validate", span_type="CHAIN"):
        contradictions = validator_internal.validate(extracted)

    with mlflow.start_span(name="step2b_tavily_validate", span_type="CHAIN"):
        flags: ValidationFlags = validator_tavily.validate(extracted)

    with mlflow.start_span(name="step2c_stat_validate", span_type="CHAIN"):
        outlier_flags = validator_stat.validate(extracted, pin_stats)

    # Merge all validation signals into a single ValidationFlags
    flags.internal_contradictions = contradictions
    flags.pin_code_outlier_flags = outlier_flags

    with mlflow.start_span(name="step3_score", span_type="CHAIN"):
        trust_score = compute_score(extracted, flags)

    return trust_score
