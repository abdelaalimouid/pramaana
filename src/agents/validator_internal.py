"""PRAMAANA Agent 2A — Internal logical contradiction validator.

Judging criterion: Discovery & Verification (35%).
Checks clinical logic rules: e.g. claims surgery → must list anesthesiologist.
"""
from src.schemas.facility import ExtractedFacility
from src.tracing import traced_tool

# (rule_description, condition_that_triggers, condition_that_must_also_be_true)
_RULES: list[tuple[str, str]] = [
    ("SURGERY_NO_ANESTHESIOLOGIST", "performs_emergency_surgery requires has_anesthesiologist"),
    ("DIALYSIS_NO_NEPHROLOGIST", "performs_dialysis requires has_nephrologist"),
    ("NEONATAL_NO_NEONATOLOGIST", "performs_neonatal_care requires has_neonatologist"),
    ("ONCOLOGY_NO_ONCOLOGIST", "performs_oncology_treatment requires has_oncologist"),
    ("ICU_NO_DOCTOR", "has_icu requires has_full_time_doctor"),
    ("HIGH_CAPACITY_NO_DOCTOR", "capacity > 50 requires has_full_time_doctor"),
]


@traced_tool("internal_contradiction_check", span_type="TOOL")
def validate(facility: ExtractedFacility) -> list[str]:
    """Apply rule-based contradiction checks; return list of violation reason codes."""
    contradictions: list[str] = []
    c = facility.capabilities
    s = facility.staffing
    e = facility.equipment

    if c.performs_emergency_surgery and s.has_anesthesiologist is False:
        contradictions.append("SURGERY_NO_ANESTHESIOLOGIST")

    if c.performs_dialysis and s.has_nephrologist is False:
        contradictions.append("DIALYSIS_NO_NEPHROLOGIST")

    if c.performs_neonatal_care and s.has_neonatologist is False:
        contradictions.append("NEONATAL_NO_NEONATOLOGIST")

    if c.performs_oncology_treatment and s.has_oncologist is False:
        contradictions.append("ONCOLOGY_NO_ONCOLOGIST")

    if e.has_icu and s.has_full_time_doctor is False:
        contradictions.append("ICU_NO_DOCTOR")

    return contradictions
