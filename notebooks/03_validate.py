# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 03: Triple Validation (2A Internal + 2B Tavily + 2C Stat)
# MAGIC
# MAGIC Reads Silver extracted → runs all three validators → writes Silver validated table.
# MAGIC The Tavily validator is the KILLSHOT: live web corroboration per facility.

# COMMAND ----------

# MAGIC %pip install --upgrade "pydantic>=2.5" "mlflow>=3.1.0" "tavily-python>=0.5" python-dotenv
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import math
import os
import sys
import pandas as pd
import mlflow
from dotenv import load_dotenv
from packaging.version import Version
from pyspark.sql import functions as F

SILVER_EXTRACTED = "pramaana.silver.facilities_extracted"
SILVER_VALIDATED = "pramaana.silver.facilities_validated"
BRONZE_TABLE = "pramaana.bronze.facilities_raw"

load_dotenv()

if Version(mlflow.__version__) < Version("3.1.0") or not hasattr(mlflow, "start_span"):
    raise RuntimeError("MLflow tracing requires mlflow>=3.1.0 with start_span().")

REPO_PATH = os.environ.get("PRAMAANA_REPO_PATH", "/Workspace/Repos/abdelaalimouid/pramaana")
if REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)
print(f"Using repo path: {REPO_PATH}")

experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

from src.schemas.facility import ExtractedFacility, ValidationFlags
from src.agents import validator_internal, validator_tavily, validator_stat

# COMMAND ----------

extracted_pdf = spark.table(SILVER_EXTRACTED).toPandas()
print(f"Loaded {len(extracted_pdf):,} extracted facilities")

# ── Also load the Bronze row for web-signal columns ───────────────────────────
bronze_pdf = spark.table(BRONZE_TABLE).select(
    "facility_id", "officialWebsite", "distinct_social_media_presence_count",
    "engagement_metrics_n_followers",
).toPandas()
web_signals = bronze_pdf.set_index("facility_id").to_dict(orient="index")
print(f"Web signals loaded for {len(web_signals):,} facilities")

# COMMAND ----------

def _web(facility_id: str, key: str, default):
    val = web_signals.get(facility_id, {}).get(key, default)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return val


def _clean(value):
    """Normalize pandas values before Pydantic validation."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def _nested_facility(row: dict) -> ExtractedFacility:
    """Rebuild nested ExtractedFacility from flattened Delta columns."""
    payload = {
        "facility_id": _clean(row.get("facility_id")),
        "name": _clean(row.get("name")),
        "state": _clean(row.get("state")),
        "city": _clean(row.get("city")),
        "pin_code": _clean(row.get("pin_code")),
        "facility_type": _clean(row.get("facility_type")),
        "latitude": _clean(row.get("latitude")),
        "longitude": _clean(row.get("longitude")),
        "staffing": {
            "has_full_time_doctor": _clean(row.get("staffing.has_full_time_doctor")),
            "has_anesthesiologist": _clean(row.get("staffing.has_anesthesiologist")),
            "has_nephrologist": _clean(row.get("staffing.has_nephrologist")),
            "has_oncologist": _clean(row.get("staffing.has_oncologist")),
            "has_emergency_specialist": _clean(row.get("staffing.has_emergency_specialist")),
            "has_neonatologist": _clean(row.get("staffing.has_neonatologist")),
            "doctor_count_extracted": _clean(row.get("staffing.doctor_count_extracted")),
            "raw_evidence_span": _clean(row.get("staffing.raw_evidence_span")),
        },
        "equipment": {
            "has_icu": _clean(row.get("equipment.has_icu")),
            "icu_bed_count": _clean(row.get("equipment.icu_bed_count")),
            "has_dialysis_machine": _clean(row.get("equipment.has_dialysis_machine")),
            "has_oxygen_supply": _clean(row.get("equipment.has_oxygen_supply")),
            "has_neonatal_unit": _clean(row.get("equipment.has_neonatal_unit")),
            "has_operating_theatre": _clean(row.get("equipment.has_operating_theatre")),
            "has_xray": _clean(row.get("equipment.has_xray")),
            "has_ct_scan": _clean(row.get("equipment.has_ct_scan")),
            "has_mri": _clean(row.get("equipment.has_mri")),
            "raw_evidence_span": _clean(row.get("equipment.raw_evidence_span")),
        },
        "capabilities": {
            "performs_emergency_surgery": _clean(row.get("capabilities.performs_emergency_surgery")),
            "performs_dialysis": _clean(row.get("capabilities.performs_dialysis")),
            "performs_oncology_treatment": _clean(row.get("capabilities.performs_oncology_treatment")),
            "performs_neonatal_care": _clean(row.get("capabilities.performs_neonatal_care")),
            "performs_trauma_care": _clean(row.get("capabilities.performs_trauma_care")),
            "performs_cardiac_care": _clean(row.get("capabilities.performs_cardiac_care")),
            "available_24_7": _clean(row.get("capabilities.available_24_7")),
            "raw_evidence_span": _clean(row.get("capabilities.raw_evidence_span")),
        },
        "extraction_model": _clean(row.get("extraction_model")),
        "extraction_confidence": _clean(row.get("extraction_confidence")) or "medium",
    }
    return ExtractedFacility(**payload)


def _fast_validate(fn, *args, **kwargs):
    """Bypass per-row child spans for 10k-row batch speed; parent span still traces the run."""
    return getattr(fn, "__wrapped__", fn)(*args, **kwargs)

# COMMAND ----------

# Pre-compute PIN-code stats for Agent 2C (done once over the full set)
facilities = [_nested_facility(r) for r in extracted_pdf.to_dict(orient="records")]
pin_stats = validator_stat.build_pin_code_stats(facilities)
print(f"PIN-code stats computed for {len(pin_stats)} PIN codes")

# COMMAND ----------

validated_results = []
errors = []
tavily_limit = int(os.environ.get("PRAMAANA_TAVILY_LIMIT", "300"))
tavily_used = 0
tavily_enabled = bool(os.environ.get("TAVILY_API_KEY"))
if not tavily_enabled:
    print("TAVILY_API_KEY not set; Phase 3 will use dataset web signals only.")
else:
    print(f"Tavily enabled for up to {tavily_limit:,} high-signal facilities.")

with mlflow.start_span(name="phase3_validation", span_type="CHAIN") as span:
    span.set_inputs({"rows": len(facilities), "tavily_limit": tavily_limit, "tavily_enabled": tavily_enabled})
    for i, facility in enumerate(facilities):
        try:
            # 2A: internal logical contradictions
            contradictions = _fast_validate(validator_internal.validate, facility)

            has_official_website = bool(_web(facility.facility_id, "officialWebsite", None))
            social_presence_count = int(_web(facility.facility_id, "distinct_social_media_presence_count", 0) or 0)
            follower_count = int(_web(facility.facility_id, "engagement_metrics_n_followers", 0) or 0)

            should_tavily = (
                tavily_enabled
                and tavily_used < tavily_limit
                and (
                    facility.extraction_model != "rules_v1"
                    or facility.extraction_confidence == "high"
                    or facility.equipment.has_icu
                    or facility.capabilities.performs_dialysis
                    or facility.capabilities.performs_emergency_surgery
                )
            )

            if should_tavily:
                # 2B: Tavily live web corroboration (THE KILLSHOT)
                flags: ValidationFlags = validator_tavily.validate(
                    facility,
                    has_official_website=has_official_website,
                    social_presence_count=social_presence_count,
                    follower_count=follower_count,
                )
                tavily_used += 1
            else:
                dataset_score = min(1.0, (int(has_official_website) * 0.5 + min(social_presence_count, 5) * 0.1))
                flags = ValidationFlags(
                    facility_id=facility.facility_id,
                    web_presence_score=round(0.4 * dataset_score, 4),
                    tavily_results_count=0,
                    tavily_corroboration_evidence=[],
                    tavily_queries_used=[],
                    has_official_website=has_official_website,
                    social_presence_count=social_presence_count,
                    follower_count=follower_count,
                )

            # 2C: statistical outlier check
            outlier_flags = _fast_validate(validator_stat.validate, facility, pin_stats)

            # Merge
            flags.internal_contradictions = contradictions
            flags.pin_code_outlier_flags = outlier_flags

            validated_results.append(flags.model_dump())

        except Exception as e:
            errors.append({"facility_id": facility.facility_id, "error": str(e)})
            if len(errors) <= 5:
                print(f"[WARN] {facility.facility_id}: {e}")

        if (i + 1) % 100 == 0:
            print(f"Validated {i+1:,}/{len(facilities):,} ({len(errors)} errors, {tavily_used} Tavily)")

    span.set_outputs({
        "rows_validated": len(validated_results),
        "validation_errors": len(errors),
        "tavily_used": tavily_used,
        "total_contradictions": sum(len(r["internal_contradictions"]) for r in validated_results),
        "total_web_zero": sum(1 for r in validated_results if r["tavily_results_count"] == 0),
    })

print(f"Validation complete: {len(validated_results):,} OK, {len(errors):,} errors, {tavily_used} Tavily searches")

# COMMAND ----------

val_df = spark.createDataFrame(pd.json_normalize(validated_results))
val_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_VALIDATED)
print(f"Written to {SILVER_VALIDATED}: {spark.table(SILVER_VALIDATED).count():,} rows")
