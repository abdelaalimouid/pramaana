# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 04: Trust Scorer (Silver → Gold)
# MAGIC
# MAGIC Joins Silver extracted + Silver validated → runs Agent 3 → writes Gold scored table.
# MAGIC Gold table is the final product: one row per facility with trust score + CI + citations.

# COMMAND ----------

import os, json
import pandas as pd
import mlflow

SILVER_EXTRACTED = "pramaana.silver.facilities_extracted"
SILVER_VALIDATED = "pramaana.silver.facilities_validated"
GOLD_TABLE = "pramaana.gold.facilities_scored"

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

scored_results = []
errors = []

with mlflow.start_run(run_name="phase4_scoring"):
    for i, row in enumerate(merged.to_dict(orient="records")):
        try:
            extracted = ExtractedFacility(**{k.replace("_ext", ""): v for k, v in row.items() if "_val" not in k})
            flags = ValidationFlags(**{k.replace("_val", ""): v for k, v in row.items() if "_ext" not in k})
            trust_score = score(extracted, flags)
            scored_results.append(trust_score.model_dump())
        except Exception as e:
            errors.append({"facility_id": row.get("facility_id"), "error": str(e)})

        if (i + 1) % 500 == 0:
            print(f"Scored {i+1:,}/{len(merged):,}")

    avg_score = sum(r["score"] for r in scored_results) / max(1, len(scored_results))
    mlflow.log_metric("rows_scored", len(scored_results))
    mlflow.log_metric("scoring_errors", len(errors))
    mlflow.log_metric("avg_trust_score", round(avg_score, 2))
    mlflow.log_metric("suspicious_count", sum(1 for r in scored_results if r["score_band"] == "suspicious"))

print(f"Scoring complete: {len(scored_results):,} OK, avg score={avg_score:.1f}")

# COMMAND ----------

gold_df = spark.createDataFrame(pd.json_normalize(scored_results))
gold_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD_TABLE)
print(f"Written to {GOLD_TABLE}: {spark.table(GOLD_TABLE).count():,} rows")

# COMMAND ----------

# Quick distribution summary for the README/demo
display(spark.table(GOLD_TABLE).groupBy("score_band").count().orderBy("score_band"))
