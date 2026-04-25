# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 03: Triple Validation (2A Internal + 2B Tavily + 2C Stat)
# MAGIC
# MAGIC Reads Silver extracted → runs all three validators → writes Silver validated table.
# MAGIC The Tavily validator is the KILLSHOT: live web corroboration per facility.

# COMMAND ----------

import os, json
import pandas as pd
import mlflow
from pyspark.sql import functions as F

SILVER_EXTRACTED = "pramaana.silver.facilities_extracted"
SILVER_VALIDATED = "pramaana.silver.facilities_validated"

experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

from src.schemas.facility import ExtractedFacility, ValidationFlags
from src.agents import validator_internal, validator_tavily, validator_stat

# COMMAND ----------

extracted_pdf = spark.table(SILVER_EXTRACTED).toPandas()
print(f"Loaded {len(extracted_pdf):,} extracted facilities")

# COMMAND ----------

# Pre-compute PIN-code stats for Agent 2C (done once over the full set)
facilities = [ExtractedFacility(**r) for r in extracted_pdf.to_dict(orient="records")]
pin_stats = validator_stat.build_pin_code_stats(facilities)
print(f"PIN-code stats computed for {len(pin_stats)} PIN codes")

# COMMAND ----------

validated_results = []
errors = []

with mlflow.start_run(run_name="phase3_validation"):
    for i, facility in enumerate(facilities):
        try:
            # 2A: internal logical contradictions
            contradictions = validator_internal.validate(facility)

            # 2B: Tavily live web corroboration (THE KILLSHOT)
            flags: ValidationFlags = validator_tavily.validate(facility)

            # 2C: statistical outlier check
            outlier_flags = validator_stat.validate(facility, pin_stats)

            # Merge
            flags.internal_contradictions = contradictions
            flags.pin_code_outlier_flags = outlier_flags

            validated_results.append(flags.model_dump())

        except Exception as e:
            errors.append({"facility_id": facility.facility_id, "error": str(e)})
            if len(errors) <= 5:
                print(f"[WARN] {facility.facility_id}: {e}")

        if (i + 1) % 100 == 0:
            print(f"Validated {i+1:,}/{len(facilities):,} ({len(errors)} errors)")

    mlflow.log_metric("rows_validated", len(validated_results))
    mlflow.log_metric("validation_errors", len(errors))
    mlflow.log_metric("total_contradictions", sum(len(r["internal_contradictions"]) for r in validated_results))
    mlflow.log_metric("total_web_zero", sum(1 for r in validated_results if r["tavily_results_count"] == 0))

print(f"Validation complete: {len(validated_results):,} OK, {len(errors):,} errors")

# COMMAND ----------

val_df = spark.createDataFrame(pd.json_normalize(validated_results))
val_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(SILVER_VALIDATED)
print(f"Written to {SILVER_VALIDATED}: {spark.table(SILVER_VALIDATED).count():,} rows")
