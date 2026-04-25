# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 04: Trust Scorer (Silver → Gold)
# MAGIC
# MAGIC Joins Silver extracted + Silver validated → runs Agent 3 → writes Gold scored table.
# MAGIC Gold table is the final product: one row per facility with trust score + CI + citations.

# COMMAND ----------

# MAGIC %pip install --upgrade "pydantic>=2.5" "mlflow>=3.1.0" python-dotenv
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
GOLD_TABLE = "pramaana.gold.facilities_scored"

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
from src.agents.trust_scorer import score

# COMMAND ----------

extracted_pdf = spark.table(SILVER_EXTRACTED).toPandas()
validated_pdf = spark.table(SILVER_VALIDATED).toPandas()
print(f"Extracted: {len(extracted_pdf):,} | Validated: {len(validated_pdf):,}")

# Join on facility_id
merged = extracted_pdf.merge(validated_pdf, on="facility_id", suffixes=("_ext", "_val"))
print(f"Merged: {len(merged):,} rows")

# COMMAND ----------

def _clean(value):
    """Normalize pandas values before Pydantic validation."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def _list(value) -> list[str]:
    """Normalize Spark/Pandas array values before Pydantic validation."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    if value == "":
        return []
    return [str(value)]


def _nested_facility(row: dict) -> ExtractedFacility:
    """Rebuild nested ExtractedFacility from flattened extracted columns."""
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


def _validation_flags(row: dict) -> ValidationFlags:
    """Rebuild ValidationFlags from validated columns."""
    return ValidationFlags(
        facility_id=_clean(row.get("facility_id")),
        internal_contradictions=_list(row.get("internal_contradictions")),
        web_presence_score=float(_clean(row.get("web_presence_score")) or 0.0),
        tavily_results_count=int(_clean(row.get("tavily_results_count")) or 0),
        tavily_corroboration_evidence=_list(row.get("tavily_corroboration_evidence")),
        tavily_queries_used=_list(row.get("tavily_queries_used")),
        has_official_website=bool(_clean(row.get("has_official_website"))),
        social_presence_count=int(_clean(row.get("social_presence_count")) or 0),
        follower_count=int(_clean(row.get("follower_count")) or 0),
        pin_code_outlier_flags=_list(row.get("pin_code_outlier_flags")),
    )


def _fast_score(*args, **kwargs):
    """Bypass per-row child spans for 10k-row batch speed; parent span still traces the run."""
    return getattr(score, "__wrapped__", score)(*args, **kwargs)


scored_results = []
errors = []

with mlflow.start_span(name="phase4_scoring", span_type="CHAIN") as span:
    span.set_inputs({"rows": len(merged)})
    for i, row in enumerate(merged.to_dict(orient="records")):
        try:
            extracted = _nested_facility(row)
            flags = _validation_flags(row)
            trust_score = _fast_score(extracted, flags)
            scored_results.append(trust_score.model_dump())
        except Exception as e:
            errors.append({"facility_id": row.get("facility_id"), "error": str(e)})
            if len(errors) <= 5:
                print(f"[WARN] {row.get('facility_id')}: {e}")

        if (i + 1) % 500 == 0:
            print(f"Scored {i+1:,}/{len(merged):,} ({len(errors)} errors)")

    avg_score = sum(r["score"] for r in scored_results) / max(1, len(scored_results))
    span.set_outputs({
        "rows_scored": len(scored_results),
        "scoring_errors": len(errors),
        "avg_trust_score": round(avg_score, 2),
        "suspicious_count": sum(1 for r in scored_results if r["score_band"] == "suspicious"),
    })

print(f"Scoring complete: {len(scored_results):,} OK, {len(errors):,} errors, avg score={avg_score:.1f}")
if errors:
    raise RuntimeError(f"Scoring produced {len(errors)} errors; refusing to write partial Gold table.")

# COMMAND ----------

gold_df = spark.createDataFrame(pd.json_normalize(scored_results))
for array_col in ["reason_codes", "citation_spans"]:
    if array_col in gold_df.columns:
        gold_df = gold_df.withColumn(array_col, F.col(array_col).cast("array<string>"))

gold_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD_TABLE)
print(f"Written to {GOLD_TABLE}: {spark.table(GOLD_TABLE).count():,} rows")

# COMMAND ----------

# Quick distribution summary for the README/demo
display(spark.table(GOLD_TABLE).groupBy("score_band").count().orderBy("score_band"))

# COMMAND ----------

spark.sql("SELECT COUNT(*) FROM pramaana.gold.facilities_scored").show()
spark.sql("""
SELECT score_band, COUNT(*) AS n
FROM pramaana.gold.facilities_scored
GROUP BY score_band
ORDER BY score_band
""").show()
