# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 02: Extractor Agent
# MAGIC
# MAGIC Reads Bronze → runs Agent 1 (LLM extraction) → writes Silver extracted table.
# MAGIC - Concurrent execution via ThreadPoolExecutor (tune WORKERS to your endpoint's rate limit)
# MAGIC - Checkpoints every CHECKPOINT_EVERY rows so a crash doesn't lose all progress
# MAGIC - NaN values from pandas are converted to None before passing to Pydantic

# COMMAND ----------

# %pip install openai tavily-python pydantic>=2.5 mlflow>=3.0.0
# dbutils.library.restartPython()

# COMMAND ----------

import os
import json
import math
import warnings
import pandas as pd
import mlflow
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

BRONZE_TABLE        = "pramaana.bronze.facilities_raw"
SILVER_TABLE        = "pramaana.silver.facilities_extracted"
CHECKPOINT_TABLE    = "pramaana.silver.facilities_extracted_ckpt"
WORKERS             = 8     # concurrent LLM calls — raise if endpoint allows it
CHECKPOINT_EVERY    = 500   # write partial results to Delta this often
LOG_EVERY           = 100   # print progress this often

experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

import sys
sys.path.insert(0, "/Workspace/Repos/abdelaalimouid/pramaana")  # adjust to your repo path

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
    done_ids = set()

todo_df = bronze_df[~bronze_df["facility_id"].isin(done_ids)].reset_index(drop=True)
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

def _row_to_raw(row_dict: dict, idx: int) -> tuple[str, RawFacilityRow]:
    """Convert a Bronze row dict to (facility_id, RawFacilityRow), coercing NaN → None."""
    facility_id = row_dict.get("facility_id") or f"FAC{idx:06d}"
    clean = {}
    for field in _RAW_FIELDS:
        val = row_dict.get(field)
        # pandas uses float NaN for missing values in mixed-type columns
        if val is not None and isinstance(val, float) and math.isnan(val):
            val = None
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

with mlflow.start_run(run_name="phase2_extraction"):
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
                ckpt_df = spark.createDataFrame(pd.json_normalize(results))
                ckpt_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(CHECKPOINT_TABLE)
                print(f"  [CHECKPOINT] flushed {len(results)} rows to {CHECKPOINT_TABLE}")
                results.clear()

    # Final flush
    if results:
        ckpt_df = spark.createDataFrame(pd.json_normalize(results))
        ckpt_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(CHECKPOINT_TABLE)
        print(f"  [CHECKPOINT] final flush of {len(results)} rows")
        results.clear()

    mlflow.log_metric("rows_extracted", completed - len(errors))
    mlflow.log_metric("extraction_errors", len(errors))
    mlflow.log_metric("error_rate_pct", round(100 * len(errors) / max(1, total), 2))

print(f"\nExtraction complete: {completed - len(errors):,} OK, {len(errors):,} errors")

# COMMAND ----------

# ── Deduplicate checkpoint → write final Silver table ────────────────────────
silver_df = (
    spark.table(CHECKPOINT_TABLE)
    .dropDuplicates(["facility_id"])
    .filter("_error IS NULL OR _error = ''")
)
silver_df = silver_df.drop("_error") if "_error" in silver_df.columns else silver_df

silver_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_TABLE)

count = spark.table(SILVER_TABLE).count()
print(f"Written to {SILVER_TABLE}: {count:,} rows")
assert count >= total * 0.95, f"Too many failures: only {count} of {total} rows extracted"

# COMMAND ----------

# ── Quick sanity checks ───────────────────────────────────────────────────────
display(spark.table(SILVER_TABLE).select(
    "facility_id", "name", "state", "extraction_confidence",
    "equipment.has_icu", "capabilities.performs_dialysis",
    "staffing.raw_evidence_span",
).limit(10))
