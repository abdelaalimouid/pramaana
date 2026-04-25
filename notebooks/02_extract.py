# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 02: Extractor Agent
# MAGIC
# MAGIC Reads Bronze → runs Agent 1 (LLM extraction) → writes Silver extracted table.
# MAGIC - Concurrent execution via ThreadPoolExecutor (tune WORKERS to your endpoint's rate limit)
# MAGIC - Checkpoints every CHECKPOINT_EVERY rows so a crash doesn't lose all progress
# MAGIC - NaN values from pandas are converted to None before passing to Pydantic

# COMMAND ----------

# MAGIC %pip install --upgrade "pydantic>=2.5" "mlflow>=3.1.0" "httpx>=0.27" python-dotenv
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
os.environ["PRAMAANA_FULL_EXTRACT"] = "1"
os.environ["PRAMAANA_EXTRACT_WORKERS"] = "1"
os.environ["DATABRICKS_LLM_ENDPOINT"] = "databricks-meta-llama-3-3-70b-instruct"

# COMMAND ----------

import os
import json
import math
import warnings
import pandas as pd
import mlflow
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from packaging.version import Version
from pyspark.sql import functions as F

load_dotenv()

print(f"MLflow version: {mlflow.__version__}")
if Version(mlflow.__version__) < Version("3.1.0") or not hasattr(mlflow, "start_span"):
    raise RuntimeError(
        "STOP: MLflow tracing is not active in this Python kernel. "
        "Run the first %pip cell, let dbutils.library.restartPython() restart, "
        "then run this notebook from the top again."
    )

BRONZE_TABLE        = "pramaana.bronze.facilities_raw"
SILVER_TABLE        = "pramaana.silver.facilities_extracted"
CHECKPOINT_TABLE    = "pramaana.silver.facilities_extracted_ckpt"
FULL_RUN            = os.environ.get("PRAMAANA_FULL_EXTRACT", "0") == "1"
DRY_RUN_LIMIT       = int(os.environ.get("PRAMAANA_EXTRACT_LIMIT", "25"))
WORKERS             = int(os.environ.get("PRAMAANA_EXTRACT_WORKERS", "2"))
CHECKPOINT_EVERY    = 500   # write partial results to Delta this often
LOG_EVERY           = 25    # print progress this often

if not FULL_RUN:
    SILVER_TABLE = "pramaana.silver.facilities_extracted_smoke"
    CHECKPOINT_TABLE = "pramaana.silver.facilities_extracted_smoke_ckpt"
    CHECKPOINT_EVERY = min(CHECKPOINT_EVERY, DRY_RUN_LIMIT)

print(f"FULL_RUN={FULL_RUN} | DRY_RUN_LIMIT={DRY_RUN_LIMIT} | WORKERS={WORKERS}")
print(f"Output table: {SILVER_TABLE}")
if FULL_RUN:
    print("FULL RUN ENABLED: this will process all remaining Bronze rows.")
else:
    print("SMOKE RUN ENABLED: this will process only the first DRY_RUN_LIMIT rows.")
    spark.sql(f"DROP TABLE IF EXISTS {CHECKPOINT_TABLE}")
    spark.sql(f"DROP TABLE IF EXISTS {SILVER_TABLE}")
    print(f"Reset smoke tables: {CHECKPOINT_TABLE}, {SILVER_TABLE}")

experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

import sys
REPO_PATH = os.environ.get("PRAMAANA_REPO_PATH", "/Workspace/Repos/abdelaalimouid/pramaana")
if REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)
print(f"Using repo path: {REPO_PATH}")

from src.schemas.facility import RawFacilityRow
from src.agents.extractor import extract

# COMMAND ----------

# ── Load Bronze ──────────────────────────────────────────────────────────────
bronze_df = spark.table(BRONZE_TABLE).toPandas()
print(f"Loaded {len(bronze_df):,} rows from {BRONZE_TABLE}")

# ── Check for already-processed rows (resume after crash) ─────────────────────
try:
    done_ids = set(spark.table(CHECKPOINT_TABLE).select("facility_id").toPandas()["facility_id"].tolist())
    print(f"Resuming: {len(done_ids):,} rows already processed, skipping them")
except Exception:
    print(f"No checkpoint table found yet: {CHECKPOINT_TABLE}")
    done_ids = set()

todo_df = bronze_df[~bronze_df["facility_id"].isin(done_ids)].reset_index(drop=True)
if not FULL_RUN:
    todo_df = todo_df.head(DRY_RUN_LIMIT).reset_index(drop=True)
print(f"Rows to process: {len(todo_df):,}")

# COMMAND ----------

# ── NaN → None helper ────────────────────────────────────────────────────────
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

_FLOAT_OUTPUT_FIELDS = [
    "latitude",
    "longitude",
]

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


def _results_to_spark_df(rows: list[dict]):
    """Create a Spark DataFrame with stable types for flattened Pydantic output."""
    pdf = pd.json_normalize(rows)
    sdf = spark.createDataFrame(pdf)

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

    return sdf

def _row_to_raw(row_dict: dict, idx: int) -> tuple[str, RawFacilityRow]:
    """Convert a Bronze row dict to (facility_id, RawFacilityRow), coercing NaN → None."""
    facility_id = row_dict.get("facility_id") or f"FAC{idx:06d}"
    clean = {}
    for field in _RAW_FIELDS:
        val = row_dict.get(field)
        # pandas uses NaN/NaT for missing values in mixed-type columns
        if val is None or pd.isna(val):
            val = None
        elif isinstance(val, pd.Timestamp):
            val = val.isoformat()
        clean[field] = val
    return facility_id, RawFacilityRow(**clean)


# ── Worker function ──────────────────────────────────────────────────────────
def _process_one(args: tuple) -> dict | None:
    idx, row_dict = args
    facility_id, raw = _row_to_raw(row_dict, idx)
    try:
        extracted = extract(raw, facility_id)
        return extracted.model_dump()
    except Exception as exc:
        warnings.warn(f"[{facility_id}] extraction failed: {exc}")
        return {"facility_id": facility_id, "_error": str(exc)}


# COMMAND ----------

# ── Main extraction loop with checkpointing ──────────────────────────────────
results      = []
errors       = []
rows_list    = list(todo_df.to_dict(orient="records"))
total        = len(rows_list)

with mlflow.start_span(name="phase2_extraction_batch", span_type="CHAIN") as batch_span:
    batch_span.set_inputs({
        "total": total,
        "full_run": FULL_RUN,
        "workers": WORKERS,
        "output_table": SILVER_TABLE,
    })
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_process_one, (i, row)): i
            for i, row in enumerate(rows_list)
        }

        completed = 0
        for future in as_completed(futures):
            result = future.result()
            completed += 1

            if result is None:
                pass
            elif "_error" in result:
                errors.append(result)
            else:
                results.append(result)

            # Progress logging
            if completed % LOG_EVERY == 0:
                print(f"  {completed:,}/{total:,} done  |  {len(errors)} errors")

            # Checkpoint: flush results to Delta and clear the buffer
            if completed % CHECKPOINT_EVERY == 0 and results:
                ckpt_df = _results_to_spark_df(results)
                ckpt_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(CHECKPOINT_TABLE)
                print(f"  [CHECKPOINT] flushed {len(results)} rows to {CHECKPOINT_TABLE}")
                results.clear()

    # Final flush
    if results:
        ckpt_df = _results_to_spark_df(results)
        ckpt_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(CHECKPOINT_TABLE)
        print(f"  [CHECKPOINT] final flush of {len(results)} rows")
        results.clear()

    batch_span.set_outputs({
        "rows_extracted": completed - len(errors),
        "extraction_errors": len(errors),
        "error_rate_pct": round(100 * len(errors) / max(1, total), 2),
    })

print(f"\nExtraction complete: {completed - len(errors):,} OK, {len(errors):,} errors")
if completed == len(errors):
    print("All extraction attempts failed. First 5 errors:")
    for err in errors[:5]:
        print(err)
    raise RuntimeError("Smoke extraction produced 0 successful rows; not reading checkpoint table.")

# COMMAND ----------

spark.sql("SELECT COUNT(*) FROM pramaana.silver.facilities_extracted_ckpt").show()

# COMMAND ----------

# ── Deduplicate checkpoint → write final Silver table ────────────────────────
silver_df = (
    spark.table(CHECKPOINT_TABLE)
    .dropDuplicates(["facility_id"])
)
if "_error" in silver_df.columns:
    silver_df = silver_df.filter("_error IS NULL OR _error = ''").drop("_error")

silver_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_TABLE)

count = spark.table(SILVER_TABLE).count()
print(f"Written to {SILVER_TABLE}: {count:,} rows")
assert count >= total * 0.95, f"Too many failures: only {count} of {total} rows extracted"

# COMMAND ----------

# ── Quick sanity checks ───────────────────────────────────────────────────────
# Spark Connect/Photon can mis-handle flattened dotted column names; pandas is safer here.
sample_pdf = spark.table(SILVER_TABLE).limit(10).toPandas()
display(sample_pdf[[
    "facility_id",
    "name",
    "state",
    "extraction_confidence",
    "equipment.has_icu",
    "capabilities.performs_dialysis",
    "staffing.raw_evidence_span",
]])

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE pramaana.silver.facilities_extracted AS
SELECT * FROM pramaana.silver.facilities_extracted_ckpt
""")
