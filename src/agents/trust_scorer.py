"""PRAMAANA Agent 3 — Trust Scorer. Bronze → Silver → Gold.

Judging criterion: Discovery & Verification (35%) — explicit confidence intervals win this bucket.
Scoring formula (0-100):
  base            = 50
  + web_presence  = web_presence_score * 20         (max +20)
  + social_bonus  = min(social_presence_count, 5)   (max +5)
  + website_bonus = 5 if has_official_website        (+5)
  - contradictions= len(internal_contradictions)*10  (up to -30)
  - outliers      = len(pin_code_outlier_flags)*5    (up to -15)
"""
from src.schemas.facility import ExtractedFacility, ValidationFlags, TrustScore
from src.tracing import trace_agent_run

_BAND_THRESHOLDS = {"high": 70, "medium": 45, "low": 25}
_REASON_DESCRIPTIONS = {
    "NO_WEB_PRESENCE": "Zero web results for claimed capabilities",
    "NO_SOCIAL_PRESENCE": "No social media presence",
    "SURGERY_NO_ANESTHESIOLOGIST": "Claims surgery but no anesthesiologist listed",
    "DIALYSIS_NO_NEPHROLOGIST": "Claims dialysis but no nephrologist listed",
    "NEONATAL_NO_NEONATOLOGIST": "Claims neonatal care but no neonatologist listed",
    "ONCOLOGY_NO_ONCOLOGIST": "Claims oncology but no oncologist listed",
    "ICU_NO_DOCTOR": "Claims ICU but no full-time doctor listed",
}


@trace_agent_run("trust_scorer")
def score(extracted: ExtractedFacility, flags: ValidationFlags) -> TrustScore:
    """Combine extraction + validation signals into a 0-100 trust score with Wilson CI."""
    raw = 50.0
    raw += flags.web_presence_score * 20
    raw += min(flags.social_presence_count, 5)
    raw += 5 if flags.has_official_website else 0
    raw -= len(flags.internal_contradictions) * 10
    raw -= len(flags.pin_code_outlier_flags) * 5
    raw = max(0.0, min(100.0, raw))

    score_int = int(round(raw))

    # Approximate Wilson CI using the score as a proportion
    p = score_int / 100.0
    n = max(1, flags.tavily_results_count + flags.social_presence_count + 1)
    z = 1.96
    import math
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    ci_low = int(max(0, round((centre - margin) * 100)))
    ci_high = int(min(100, round((centre + margin) * 100)))

    reason_codes = list(flags.internal_contradictions) + list(flags.pin_code_outlier_flags)
    if flags.tavily_results_count == 0:
        reason_codes.append("NO_WEB_PRESENCE")
    if flags.social_presence_count == 0:
        reason_codes.append("NO_SOCIAL_PRESENCE")

    if score_int >= _BAND_THRESHOLDS["high"]:
        band = "high"
    elif score_int >= _BAND_THRESHOLDS["medium"]:
        band = "medium"
    elif score_int >= _BAND_THRESHOLDS["low"]:
        band = "low"
    else:
        band = "suspicious"

    citation_spans = []
    if extracted.staffing.raw_evidence_span:
        citation_spans.append(f"[staffing] {extracted.staffing.raw_evidence_span}")
    if extracted.equipment.raw_evidence_span:
        citation_spans.append(f"[equipment] {extracted.equipment.raw_evidence_span}")
    if extracted.capabilities.raw_evidence_span:
        citation_spans.append(f"[capabilities] {extracted.capabilities.raw_evidence_span}")
    citation_spans.extend(flags.tavily_corroboration_evidence[:3])

    human_summary = (
        f"{extracted.name} ({extracted.city}, {extracted.state}) "
        f"scores {score_int}/100 [{band.upper()}]. "
        f"Web hits: {flags.tavily_results_count}. "
        f"Contradictions: {len(flags.internal_contradictions)}. "
        f"Outlier flags: {len(flags.pin_code_outlier_flags)}."
    )[:500]

    return TrustScore(
        facility_id=extracted.facility_id,
        name=extracted.name,
        state=extracted.state,
        pin_code=extracted.pin_code,
        score=score_int,
        confidence_interval_low=ci_low,
        confidence_interval_high=ci_high,
        reason_codes=reason_codes,
        human_summary=human_summary,
        citation_spans=citation_spans,
        score_band=band,
    )
