# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 05: Mosaic AI Vector Search Index
# MAGIC
# MAGIC Builds a Mosaic AI Vector Search index over the Gold table's `human_summary` + `citation_spans`.
# MAGIC This powers the `/query` endpoint (natural-language facility search for the Priya demo).

# COMMAND ----------

# MAGIC %pip install --upgrade databricks-vectorsearch databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import EndpointType
from databricks.vector_search.client import VectorSearchClient

GOLD_TABLE = "pramaana.gold.facilities_scored"
VECTOR_INDEX_NAME = "pramaana.gold.facilities_scored_vs_index"
ENDPOINT_NAME = "pramaana_vs_endpoint"
EMBEDDING_MODEL = "databricks-bge-large-en"  # built-in Databricks embedding model

# COMMAND ----------

gold_count = spark.table(GOLD_TABLE).count()
print(f"Gold rows available for vector indexing: {gold_count:,}")
assert gold_count == 10_000, f"Expected 10,000 Gold rows, got {gold_count}"

display(spark.table(GOLD_TABLE).select(
    "facility_id", "name", "state", "score", "score_band", "human_summary"
).limit(5))

# COMMAND ----------

# Ensure the Gold table has a Change Data Feed enabled (required for Managed VS index)
spark.sql(f"""
    ALTER TABLE {GOLD_TABLE}
    SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")
print(f"Change Data Feed enabled on {GOLD_TABLE}")

# COMMAND ----------

# Create Vector Search endpoint (skip if already exists)
w = WorkspaceClient()
try:
    endpoint = w.vector_search_endpoints.create_endpoint(
        name=ENDPOINT_NAME,
        endpoint_type=EndpointType.STANDARD,
    )
    print(f"Created VS endpoint: {ENDPOINT_NAME}")
except Exception as e:
    print(f"Endpoint already exists or error: {e}")

# COMMAND ----------

for attempt in range(12):
    try:
        endpoint = w.vector_search_endpoints.get_endpoint(ENDPOINT_NAME)
        print(f"Vector Search endpoint found: {ENDPOINT_NAME}")
        break
    except Exception as exc:
        print(f"Waiting for Vector Search endpoint ({attempt + 1}/12): {exc}")
        time.sleep(10)
else:
    raise RuntimeError(
        f"Vector Search endpoint {ENDPOINT_NAME} was not found. "
        "Create it manually in Databricks Vector Search UI, then rerun from this cell."
    )

# COMMAND ----------

# Create the managed delta sync index
vs_client = VectorSearchClient()

try:
    index = vs_client.create_delta_sync_index(
        endpoint_name=ENDPOINT_NAME,
        index_name=VECTOR_INDEX_NAME,
        source_table_name=GOLD_TABLE,
        pipeline_type="TRIGGERED",
        primary_key="facility_id",
        embedding_source_column="human_summary",
        embedding_model_endpoint_name=EMBEDDING_MODEL,
    )
    print(f"Vector index created: {VECTOR_INDEX_NAME}")
except Exception as e:
    print(f"Index already exists or error: {e}")

# COMMAND ----------

# Trigger initial sync
index = vs_client.get_index(endpoint_name=ENDPOINT_NAME, index_name=VECTOR_INDEX_NAME)
index.sync()
print("Index sync triggered. Check endpoint status in the Databricks UI.")

# COMMAND ----------

# Smoke test: query the index
try:
    results = index.similarity_search(
        query_text="dialysis facility Bihar",
        columns=["facility_id", "name", "state", "score", "score_band", "human_summary"],
        num_results=5,
    )
    print("Sample vector query results:")
    for r in results.get("result", {}).get("data_array", []):
        print(r)
except Exception as exc:
    print(f"Vector index not queryable yet: {exc}")
    print("Fallback SQL demo query:")
    display(spark.sql(f"""
        SELECT facility_id, name, state, score, score_band, human_summary
        FROM {GOLD_TABLE}
        WHERE lower(human_summary) LIKE '%dialysis%'
          AND score >= 45
        ORDER BY score DESC
        LIMIT 5
    """))
