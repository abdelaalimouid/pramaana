# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 02b: Hybrid Extractor
# MAGIC
# MAGIC Builds full 10k Silver extraction coverage by combining:
# MAGIC - LLM-extracted checkpoint rows from `02_extract.py`
# MAGIC - deterministic rules extraction for every Bronze row

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

load_dotenv()

if Version(mlflow.__version__) < Version("3.1.0") or not hasattr(mlflow, "start_span"):
    raise RuntimeError("MLflow tracing requires mlflow>=3.1.0 with start_span().")

BRONZE_TABLE = "pramaana.bronze.facilities_raw"
LLM_CHECKPOINT_TABLE = "pramaana.silver.facilities_extracted_ckpt"
SILVER_TABLE = "pramaana.silver.facilities_extracted"

REPO_PATH = os.environ.get("PRAMAANA_REPO_PATH", "/Workspace/Repos/abdelaalimouid/pramaana")
if REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)
print(f"Using repo path: {REPO_PATH}")

mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana"))

# COMMAND ----------

from src.schemas.facility import RawFacilityRow
from src.agents.extractor_rules import extract_rules

# COMMAND ----------

_RAW_FIELDS = [
    "name", "description", "specialties", "procedure", "equipment", "capability",
    "numberDoctors", "capacity", "facilityTypeId",
    "address_city", "address_stateOrRegion", "address_zipOrPostcode",
    "officialWebsite", "facebookLink", "linkedinLink",
    "distinct_social_media_presence_count", "engagement_metrics_n_followers",
    "recency_of_page_update", "latitude", "longitude",
]

_BOOLEAN_OUTPUT_FIELDS = [
    "staffing.has_full_time_doctor",
    "staffing.has_anesthesiologist",
    "staffing.has_nephrologist",
    "staffing.has_oncologist",
    "staffing.has_emergency_specialist",
    "staffing.has_neonatologist",
    "equipment.has_icu",
    "equipment.has_dialysis_machine",
    "equipment.has_oxygen_supply",
    "equipment.has_neonatal_unit",
    "equipment.has_operating_theatre",
    "equipment.has_xray",
    "equipment.has_ct_scan",
    "equipment.has_mri",
    "capabilities.performs_emergency_surgery",
    "capabilities.performs_dialysis",
    "capabilities.performs_oncology_treatment",
    "capabilities.performs_neonatal_care",
    "capabilities.performs_trauma_care",
    "capabilities.performs_cardiac_care",
    "capabilities.available_24_7",
]

_INTEGER_OUTPUT_FIELDS = [
    "staffing.doctor_count_extracted",
    "equipment.icu_bed_count",
]

_FLOAT_OUTPUT_FIELDS = ["latitude", "longitude"]

_STRING_OUTPUT_FIELDS = [
    "facility_id",
    "name",
    "state",
    "city",
    "pin_code",
    "facility_type",
    "extraction_model",
    "extraction_confidence",
    "staffing.raw_evidence_span",
    "equipment.raw_evidence_span",
    "capabilities.raw_evidence_span",
]


def _clean_value(value):
    """Normalize pandas missing/timestamp values before Pydantic validation."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _row_to_raw(row_dict: dict, idx: int) -> tuple[str, RawFacilityRow]:
    """Convert Bronze row dict into RawFacilityRow for deterministic extraction."""
    facility_id = row_dict.get("facility_id") or f"FAC{idx:06d}"
    clean = {field: _clean_value(row_dict.get(field)) for field in _RAW_FIELDS}
    return facility_id, RawFacilityRow(**clean)


def _cast_output_df(sdf):
    """Cast flattened extraction output to stable Delta-compatible column types."""
    for field in _STRING_OUTPUT_FIELDS:
        if field not in sdf.columns:
            sdf = sdf.withColumn(field, F.lit(None).cast("string"))
        else:
            sdf = sdf.withColumn(field, F.col(f"`{field}`").cast("string"))

    for field in _BOOLEAN_OUTPUT_FIELDS:
        if field not in sdf.columns:
            sdf = sdf.withColumn(field, F.lit(None).cast("boolean"))
        else:
            sdf = sdf.withColumn(field, F.col(f"`{field}`").cast("boolean"))

    for field in _INTEGER_OUTPUT_FIELDS:
        if field not in sdf.columns:
            sdf = sdf.withColumn(field, F.lit(None).cast("int"))
        else:
            sdf = sdf.withColumn(field, F.col(f"`{field}`").cast("int"))

    for field in _FLOAT_OUTPUT_FIELDS:
        if field not in sdf.columns:
            sdf = sdf.withColumn(field, F.lit(None).cast("double"))
        else:
            sdf = sdf.withColumn(field, F.col(f"`{field}`").cast("double"))

    ordered = _STRING_OUTPUT_FIELDS + _FLOAT_OUTPUT_FIELDS + _BOOLEAN_OUTPUT_FIELDS + _INTEGER_OUTPUT_FIELDS
    return sdf.select(*[F.col(f"`{field}`") for field in ordered])


# COMMAND ----------

bronze_pdf = spark.table(BRONZE_TABLE).toPandas()
print(f"Loaded Bronze rows: {len(bronze_pdf):,}")

rule_rows = []
with mlflow.start_span(name="phase2b_rules_extract_all", span_type="CHAIN") as span:
    span.set_inputs({"bronze_rows": len(bronze_pdf)})
    for idx, row_dict in enumerate(bronze_pdf.to_dict(orient="records")):
        facility_id, raw = _row_to_raw(row_dict, idx)
        rule_rows.append(extract_rules(raw, facility_id).model_dump())
        if (idx + 1) % 1000 == 0:
            print(f"Rules extracted {idx + 1:,}/{len(bronze_pdf):,}")
    span.set_outputs({"rule_rows": len(rule_rows)})

rules_df = _cast_output_df(spark.createDataFrame(pd.json_normalize(rule_rows)))
print(f"Rule extraction rows: {rules_df.count():,}")

# COMMAND ----------

try:
    llm_df = _cast_output_df(spark.table(LLM_CHECKPOINT_TABLE).dropDuplicates(["facility_id"]))
    llm_count = llm_df.count()
    print(f"LLM checkpoint rows: {llm_count:,}")
except Exception as exc:
    print(f"No LLM checkpoint table found; using rules only. Detail: {exc}")
    llm_df = None
    llm_count = 0

# COMMAND ----------

if llm_df is not None and llm_count > 0:
    rule_only_df = rules_df.join(llm_df.select("facility_id"), on="facility_id", how="left_anti")
    final_df = llm_df.unionByName(rule_only_df)
    print(f"Hybrid final = {llm_count:,} LLM rows + {rule_only_df.count():,} rule rows")
else:
    final_df = rules_df
    print("Hybrid final = rules only")

final_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_TABLE)

count = spark.table(SILVER_TABLE).count()
print(f"Written to {SILVER_TABLE}: {count:,} rows")
assert count == len(bronze_pdf), f"Expected {len(bronze_pdf)} rows, got {count}"

# COMMAND ----------

summary = spark.table(SILVER_TABLE).groupBy("extraction_model", "extraction_confidence").count()
display(summary.orderBy("extraction_model", "extraction_confidence"))

sample_pdf = spark.table(SILVER_TABLE).limit(10).toPandas()
display(sample_pdf[[
    "facility_id",
    "name",
    "state",
    "extraction_model",
    "extraction_confidence",
    "equipment.has_icu",
    "capabilities.performs_dialysis",
    "staffing.raw_evidence_span",
]])
