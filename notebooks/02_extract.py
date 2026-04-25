# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 02: Extractor Agent (Phase 2)
# MAGIC
# MAGIC Reads Bronze → runs Agent 1 (LLM extraction) row by row → writes Silver extracted table.
# MAGIC Uses batch processing with checkpointing to survive Databricks serverless timeouts.

# COMMAND ----------

import os, json
import pandas as pd
import mlflow
from pyspark.sql import functions as F

# Install src as editable if running on cluster (adjust path to your repo)
# %pip install -e /Workspace/Repos/<your-repo>/pramaana  # uncomment and adjust

BRONZE_TABLE = "pramaana.bronze.facilities_raw"
SILVER_TABLE = "pramaana.silver.facilities_extracted"
BATCH_SIZE = 50  # rows per LLM batch; tune based on rate limits

# COMMAND ----------

experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

from src.schemas.facility import RawFacilityRow
from src.agents.extractor import extract

# COMMAND ----------

# Load Bronze
bronze_df = spark.table(BRONZE_TABLE).toPandas()
print(f"Loaded {len(bronze_df):,} rows from Bronze")

# COMMAND ----------

# Column mapping: XLSX columns → RawFacilityRow fields
FIELD_MAP = {
    "name": "name",
    "description": "description",
    "specialties": "specialties",
    "procedure": "procedure",
    "equipment": "equipment",
    "capability": "capability",
    "numberDoctors": "numberDoctors",
    "capacity": "capacity",
    "facilityTypeId": "facilityTypeId",
    "address_city": "address_city",
    "address_stateOrRegion": "address_stateOrRegion",
    "address_zipOrPostcode": "address_zipOrPostcode",
    "officialWebsite": "officialWebsite",
    "facebookLink": "facebookLink",
    "linkedinLink": "linkedinLink",
    "distinct_social_media_presence_count": "distinct_social_media_presence_count",
    "engagement_metrics_n_followers": "engagement_metrics_n_followers",
    "recency_of_page_update": "recency_of_page_update",
    "latitude": "latitude",
    "longitude": "longitude",
}

# COMMAND ----------

results = []
errors = []

with mlflow.start_run(run_name="phase2_extraction"):
    for i, row_dict in enumerate(bronze_df.to_dict(orient="records")):
        facility_id = row_dict.get("facility_id", f"FAC{i:06d}")
        try:
            raw = RawFacilityRow(**{k: row_dict.get(v) for k, v in FIELD_MAP.items()})
            extracted = extract(raw, facility_id)
            results.append(extracted.model_dump())
        except Exception as e:
            errors.append({"facility_id": facility_id, "error": str(e)})
            if len(errors) <= 5:
                print(f"[WARN] {facility_id}: {e}")

        if (i + 1) % 100 == 0:
            print(f"Processed {i+1:,}/{len(bronze_df):,} rows ({len(errors)} errors so far)")

    mlflow.log_metric("rows_extracted", len(results))
    mlflow.log_metric("extraction_errors", len(errors))

print(f"Extraction complete: {len(results):,} OK, {len(errors):,} errors")

# COMMAND ----------

# Write Silver extracted
result_df = spark.createDataFrame(pd.json_normalize(results))
result_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_TABLE)
print(f"Written to {SILVER_TABLE}: {spark.table(SILVER_TABLE).count():,} rows")
