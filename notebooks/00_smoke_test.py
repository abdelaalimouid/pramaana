# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 00: MLflow Tracing Smoke Test
# MAGIC
# MAGIC Verifies that MLflow 3 tracing plumbing works end-to-end on this workspace.
# MAGIC No LLM calls. Just create a dummy span and confirm it appears in the Experiments UI.

# COMMAND ----------

import os
import mlflow

# Must be set explicitly on serverless — auto-detection reads unavailable Spark configs
mlflow.set_tracking_uri("databricks")

def _resolve_experiment_name() -> str:
    if os.environ.get("MLFLOW_EXPERIMENT_NAME"):
        return os.environ["MLFLOW_EXPERIMENT_NAME"]
    current_user = spark.sql("SELECT current_user()").collect()[0][0]
    return f"/Users/{current_user}/pramaana"

experiment_name = _resolve_experiment_name()
mlflow.set_experiment(experiment_name)
print(f"Experiment: {experiment_name}")

# COMMAND ----------

with mlflow.start_run(run_name="smoke_test") as run:
    with mlflow.start_span(name="dummy_extraction", span_type="TOOL") as span:
        span.set_inputs({"facility_id": "FAC000001", "text": "Has ICU and dialysis unit"})
        result = {"has_icu": True, "has_dialysis_machine": True}
        span.set_outputs({"result": result})

    mlflow.log_param("smoke_test", True)
    mlflow.log_metric("dummy_score", 75)
    print(f"Run ID: {run.info.run_id}")
    print("MLflow tracing OK — check the Experiments UI to see the trace.")

# COMMAND ----------

# Verify the run is accessible
client = mlflow.tracking.MlflowClient()
run_data = client.get_run(run.info.run_id)
print(f"Run status: {run_data.info.status}")
print(f"Params: {run_data.data.params}")
print(f"Metrics: {run_data.data.metrics}")
print("Smoke test PASSED.")
