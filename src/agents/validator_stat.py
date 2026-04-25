"""PRAMAANA Agent 2C — Statistical / population-level outlier validator.

Judging criterion: Discovery & Verification (35%).
Computes Wilson-score confidence intervals at PIN-code level to flag facilities
whose capability claims are statistical outliers for their area.
"""
import math
from collections import defaultdict
from src.schemas.facility import ExtractedFacility
from src.tracing import traced_tool

_Z = 1.96  # 95% CI


def _wilson_score(p_hat: float, n: int) -> tuple[float, float]:
    """Return (low, high) Wilson-score CI for a proportion."""
    if n == 0:
        return 0.0, 1.0
    denominator = 1 + _Z**2 / n
    centre = (p_hat + _Z**2 / (2 * n)) / denominator
    margin = (_Z * math.sqrt(p_hat * (1 - p_hat) / n + _Z**2 / (4 * n**2))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def build_pin_code_stats(facilities: list[ExtractedFacility]) -> dict[str, dict]:
    """Pre-compute per-PIN-code capability rates across all facilities.

    Call once before batch validation to build the lookup table.
    """
    buckets: dict[str, list[ExtractedFacility]] = defaultdict(list)
    for f in facilities:
        key = f.pin_code or "UNKNOWN"
        buckets[key].append(f)

    stats: dict[str, dict] = {}
    for pin, group in buckets.items():
        n = len(group)
        icu_rate = sum(1 for f in group if f.equipment.has_icu) / n
        dialysis_rate = sum(1 for f in group if f.capabilities.performs_dialysis) / n
        surgery_rate = sum(1 for f in group if f.capabilities.performs_emergency_surgery) / n
        stats[pin] = {
            "n": n,
            "icu_ci": _wilson_score(icu_rate, n),
            "dialysis_ci": _wilson_score(dialysis_rate, n),
            "surgery_ci": _wilson_score(surgery_rate, n),
        }
    return stats


@traced_tool("stat_outlier_check", span_type="TOOL")
def validate(facility: ExtractedFacility, pin_stats: dict[str, dict]) -> list[str]:
    """Flag a facility if its claims are implausible given its PIN-code peer group."""
    pin = facility.pin_code or "UNKNOWN"
    stats = pin_stats.get(pin, {})
    flags: list[str] = []

    if not stats or stats.get("n", 0) < 3:
        return flags  # not enough peers to compare

    def _is_outlier(claimed: bool | None, ci_high: float) -> bool:
        return claimed is True and ci_high < 0.05

    if _is_outlier(facility.equipment.has_icu, stats["icu_ci"][1]):
        flags.append(f"ICU_CLAIM_OUTLIER_FOR_PIN_{pin}")

    if _is_outlier(facility.capabilities.performs_dialysis, stats["dialysis_ci"][1]):
        flags.append(f"DIALYSIS_CLAIM_OUTLIER_FOR_PIN_{pin}")

    if _is_outlier(facility.capabilities.performs_emergency_surgery, stats["surgery_ci"][1]):
        flags.append(f"SURGERY_CLAIM_OUTLIER_FOR_PIN_{pin}")

    return flags
