import { NextResponse } from "next/server";

type DatabricksStatementResponse = {
  result?: {
    data_array?: unknown[][];
  };
};

const GOLD_TABLE = "pramaana.gold.facilities_scored";

function sqlString(value: string) {
  return value.replaceAll("'", "''").slice(0, 120);
}

function clampScore(value: string | null) {
  const parsed = Number(value ?? 45);
  if (Number.isNaN(parsed)) {
    return 45;
  }
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function parseCount(summary: string, label: string) {
  const match = summary.match(new RegExp(`${label}:\\s*(\\d+)`, "i"));
  return match ? Number(match[1]) : 0;
}

export async function GET(request: Request) {
  const host = process.env.DATABRICKS_HOST?.replace(/\/$/, "");
  const token = process.env.DATABRICKS_TOKEN;
  const warehouseId = process.env.DATABRICKS_WAREHOUSE_ID;

  if (!host || !token || !warehouseId) {
    return NextResponse.json(
      {
        error:
          "Databricks SQL is not configured. Set DATABRICKS_HOST, DATABRICKS_TOKEN, and DATABRICKS_WAREHOUSE_ID.",
      },
      { status: 503 },
    );
  }

  const { searchParams } = new URL(request.url);
  const query = sqlString(searchParams.get("q") || "dialysis");
  const state = sqlString(searchParams.get("state") || "all");
  const minScore = clampScore(searchParams.get("minScore"));

  const stateClause = state === "all" ? "" : `AND state = '${state}'`;
  const statement = `
    SELECT facility_id, name, state, score, score_band, human_summary
    FROM ${GOLD_TABLE}
    WHERE score >= ${minScore}
      ${stateClause}
      AND (
        lower(human_summary) LIKE lower('%${query}%')
        OR lower(name) LIKE lower('%${query}%')
      )
    ORDER BY score DESC
    LIMIT 10
  `;

  const response = await fetch(`${host}/api/2.0/sql/statements`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      warehouse_id: warehouseId,
      statement,
      wait_timeout: "30s",
      disposition: "INLINE",
      format: "JSON_ARRAY",
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    return NextResponse.json(
      { error: `Databricks SQL query failed: ${detail}` },
      { status: response.status },
    );
  }

  const payload = (await response.json()) as DatabricksStatementResponse;
  const rows = payload.result?.data_array ?? [];
  const facilities = rows.map((row) => {
    const summary = String(row[5] ?? "");
    return {
      id: String(row[0] ?? ""),
      name: String(row[1] ?? ""),
      state: String(row[2] ?? ""),
      score: Number(row[3] ?? 0),
      band: String(row[4] ?? "medium").toLowerCase(),
      capability: query,
      webHits: parseCount(summary, "Web hits"),
      contradictions: parseCount(summary, "Contradictions"),
      outliers: parseCount(summary, "Outlier flags"),
      summary,
    };
  });

  return NextResponse.json({
    source: "databricks-sql",
    facilities,
  });
}
