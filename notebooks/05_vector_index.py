# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 05: Mosaic AI Vector Search Index
# MAGIC
# MAGIC Builds a Mosaic AI Vector Search index over the Gold table's `human_summary` + `citation_spans`.
# MAGIC This powers the `/query` endpoint (natural-language facility search for the Priya demo).

# COMMAND ----------

import os
from databricks.sdk import WorkspaceClient
from databricks.vector_search.client import VectorSearchClient

GOLD_TABLE = "pramaana.gold.facilities_scored"
VECTOR_INDEX_NAME = "pramaana.gold.facilities_scored_vs_index"
ENDPOINT_NAME = "pramaana_vs_endpoint"
EMBEDDING_MODEL = "databricks-bge-large-en"  # built-in Databricks embedding model

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
        endpoint_type="STANDARD",
    )
    print(f"Created VS endpoint: {ENDPOINT_NAME}")
except Exception as e:
    print(f"Endpoint already exists or error: {e}")

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
results = index.similarity_search(
    query_text="dialysis facility Bihar",
    columns=["facility_id", "name", "state", "score", "score_band", "human_summary"],
    num_results=5,
)
print("Sample query results:")
for r in results.get("result", {}).get("data_array", []):
    print(r)
