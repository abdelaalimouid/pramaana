# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 00: MLflow Tracing Smoke Test
# MAGIC
# MAGIC Verifies that MLflow 3 tracing plumbing works end-to-end on this workspace.
# MAGIC No LLM calls. Just create a dummy span and confirm it appears in the Experiments UI.

# COMMAND ----------

# MAGIC %pip install --upgrade "mlflow>=3.1.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import mlflow
from packaging.version import Version

# In Databricks notebooks MLflow is pre-configured — do NOT call set_tracking_uri()
# It internally reads spark.mlflow.modelRegistryUri which is unavailable on serverless.
current_user = spark.sql("SELECT current_user()").collect()[0][0]
experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", f"/Users/{current_user}/pramaana")
mlflow.set_experiment(experiment_name)
print(f"Experiment: {experiment_name}")
print(f"MLflow version: {mlflow.__version__}")

if Version(mlflow.__version__) < Version("3.1.0") or not hasattr(mlflow, "start_span"):
    raise RuntimeError(
        "MLflow tracing is required for judging, but this runtime does not expose "
        "mlflow.start_span(). Re-run the first %pip install cell and restart Python."
    )

# COMMAND ----------

with mlflow.start_span(name="dummy_extraction", span_type="TOOL") as span:
    span.set_inputs({"facility_id": "FAC000001", "text": "Has ICU and dialysis unit"})
    result = {"has_icu": True, "has_dialysis_machine": True}
    span.set_outputs({"result": result})

print("MLflow tracing OK — check the Experiments UI to see the trace.")

# COMMAND ----------

print("Smoke test PASSED.")
