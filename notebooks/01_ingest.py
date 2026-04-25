# Databricks notebook source
# MAGIC %md
# MAGIC # PRAMAANA — Notebook 01: Bronze Ingestion
# MAGIC
# MAGIC Reads the raw XLSX from Unity Catalog Volume → adds `facility_id` → writes Bronze Delta table.
# MAGIC Expected output: `pramaana.bronze.facilities_raw` with 10,000 rows.

# COMMAND ----------

import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

VOLUME_PATH = "/Volumes/pramaana/bronze/raw/VF_Hackathon_Dataset_India_Large.xlsx"
BRONZE_TABLE = "pramaana.bronze.facilities_raw"

# COMMAND ----------

# Read XLSX via pandas then convert to Spark (XLSX is not natively Spark-readable)
print(f"Reading XLSX from {VOLUME_PATH} ...")
pdf = pd.read_excel(VOLUME_PATH, engine="openpyxl")
print(f"Loaded {len(pdf):,} rows, {len(pdf.columns)} columns")
print(f"Columns: {list(pdf.columns)}")

# COMMAND ----------

# Synthesize facility_id: FAC000000 ... FAC009999
pdf.insert(0, "facility_id", [f"FAC{i:06d}" for i in range(len(pdf))])

# Normalize column names: strip whitespace
pdf.columns = [c.strip() for c in pdf.columns]

# COMMAND ----------

# Convert object columns to string to avoid Arrow conversion issues
for col in pdf.select_dtypes(include=['object']).columns:
    pdf[col] = pdf[col].astype(str)

# Convert to Spark DataFrame and write as Delta
sdf = spark.createDataFrame(pdf)
sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(BRONZE_TABLE)

# COMMAND ----------

# Verify
count = spark.table(BRONZE_TABLE).count()
print(f"Rows in {BRONZE_TABLE}: {count:,}")
assert count == len(pdf), f"Row count mismatch: Delta={count}, pandas={len(pdf)}"
print("Bronze ingestion COMPLETE.")
spark.table(BRONZE_TABLE).printSchema()
