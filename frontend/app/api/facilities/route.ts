import { NextResponse } from "next/server";

type DatabricksStatementResponse = {
  result?: {
    data_array?: unknown[][];
  };
};

const GOLD_TABLE = "pramaana.gold.facilities_scored";
const VECTOR_INDEX =
  process.env.DATABRICKS_VECTOR_INDEX || "pramaana.gold.facilities_scored_vs_index";
const INDIAN_STATES = [
  "Andhra Pradesh",
  "Arunachal Pradesh",
  "Assam",
  "Bihar",
  "Chandigarh",
  "Chhattisgarh",
  "Delhi",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Madhya Pradesh",
  "Maharashtra",
  "Manipur",
  "Meghalaya",
  "Mizoram",
  "Nagaland",
  "Odisha",
  "Punjab",
  "Rajasthan",
  "Sikkim",
  "Tamil Nadu",
  "Telangana",
  "Tripura",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
];

type SearchIntent = {
  semanticQuery: string;
  terms: string[];
  band?: "high" | "medium" | "low" | "suspicious";
  state?: string;
  riskIntent: boolean;
  contradictionIntent: boolean;
  webProofIntent: boolean;
};

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

function parseTrustScore(summary: string) {
  const match = summary.match(/scores\s+(\d+)\/100/i);
  return match ? Number(match[1]) : 0;
}

function parseStringArray(value: unknown): string[] {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map(String).filter(Boolean);
  }
  const text = String(value).trim();
  if (!text || text === "[]") {
    return [];
  }
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed.map(String).filter(Boolean);
    }
  } catch {
    // Spark SQL may return arrays as plain strings; fall through to cleanup.
  }
  return text
    .replace(/^\[/, "")
    .replace(/\]$/, "")
    .split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/)
    .map((item) => item.replace(/^"|"$/g, "").trim())
    .filter(Boolean);
}

function pickEvidence(citations: string[], terms: string[]) {
  const normalizedTerms = terms.map((term) => term.toLowerCase());
  const match = citations.find((citation) =>
    normalizedTerms.some((term) => citation.toLowerCase().includes(term)),
  );
  return cleanEvidence(match ?? citations[0] ?? "No citation span available for this row.");
}

function cleanEvidence(value: string) {
  return value
    .replace(/\s+\["[\s\S]*$/, "")
    .replace(/\s+\[[A-Za-z][\s\S]*$/, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
}

function deriveIntent(rawQuery: string): SearchIntent {
  const q = rawQuery.toLowerCase().replace(/[-_]/g, " ");
  const terms = new Set<string>();
  const state = INDIAN_STATES.find((item) => q.includes(item.toLowerCase()));

  if (q.includes("dialysis") || q.includes("renal")) {
    terms.add("dialysis");
  }
  if (q.includes("icu") || q.includes("intensive") || q.includes("critical")) {
    terms.add("icu");
    terms.add("intensive care");
  }
  if (q.includes("oncology") || q.includes("cancer") || q.includes("chemo")) {
    terms.add("oncology");
    terms.add("cancer");
  }
  if (q.includes("surgery") || q.includes("surgical") || q.includes("operation")) {
    terms.add("surgery");
  }
  if (q.includes("emergency") || q.includes("trauma")) {
    terms.add("emergency");
    terms.add("trauma");
  }
  if (q.includes("neonatal") || q.includes("nicu")) {
    terms.add("neonatal");
    terms.add("nicu");
  }

  let band: SearchIntent["band"];
  if (q.includes("high trust") || q.includes("verified") || q.includes("reliable")) {
    band = "high";
  } else if (q.includes("medium trust")) {
    band = "medium";
  } else if (q.includes("low trust")) {
    band = "low";
  } else if (q.includes("suspicious")) {
    band = "suspicious";
  }

  const riskIntent =
    q.includes("suspicious") ||
    q.includes("fabricated") ||
    q.includes("false") ||
    q.includes("untrusted") ||
    q.includes("low trust");
  const contradictionIntent = q.includes("contradiction") || q.includes("conflict");
  const webProofIntent =
    q.includes("web proof") ||
    q.includes("web evidence") ||
    q.includes("corroborated") ||
    q.includes("tavily");

  if (terms.size === 0) {
    q.split(/\s+/)
      .filter((word) => word.length > 3)
      .filter(
        (word) =>
          ![
            "trust",
            "claims",
            "with",
            "show",
            "find",
            "facilities",
            "facility",
            "centers",
            "centre",
            "near",
          ].includes(word),
      )
      .slice(0, 4)
      .forEach((word) => terms.add(word));
  }

  return {
    semanticQuery: Array.from(terms).join(" ") || rawQuery,
    terms: Array.from(terms),
    band,
    state,
    riskIntent,
    contradictionIntent,
    webProofIntent,
  };
}

function rowToFacility(row: unknown[], query: string, terms: string[]) {
  const summary = String(row[5] ?? "");
  const reasonCodes = parseStringArray(row[8]);
  const citationSpans = parseStringArray(row[9]);
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
    ciLow: Number(row[6] ?? 0) || undefined,
    ciHigh: Number(row[7] ?? 0) || undefined,
    reasonCodes,
    citationSpans,
    matchedEvidence: pickEvidence(citationSpans, terms),
    matchedTerms: terms,
  };
}

function vectorRowToFacility(row: unknown[], query: string, terms: string[]) {
  const summary = String(row[4] ?? "");
  const reasonCodes = parseStringArray(row[7]);
  const citationSpans = parseStringArray(row[8]);
  return {
    id: String(row[0] ?? ""),
    name: String(row[1] ?? ""),
    state: String(row[2] ?? ""),
    score: parseTrustScore(summary),
    band: String(row[3] ?? "medium").toLowerCase(),
    capability: query,
    webHits: parseCount(summary, "Web hits"),
    contradictions: parseCount(summary, "Contradictions"),
    outliers: parseCount(summary, "Outlier flags"),
    summary,
    ciLow: Number(row[5] ?? 0) || undefined,
    ciHigh: Number(row[6] ?? 0) || undefined,
    reasonCodes,
    citationSpans,
    matchedEvidence: pickEvidence(citationSpans, terms),
    matchedTerms: terms,
  };
}

async function queryVectorSearch(
  host: string,
  token: string,
  query: string,
  state: string,
  minScore: number,
  intent: SearchIntent,
) {
  const response = await fetch(
    `${host}/api/2.0/vector-search/indexes/${encodeURIComponent(VECTOR_INDEX)}/query`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query_text: intent.semanticQuery,
        columns: [
          "facility_id",
          "name",
          "state",
          "score_band",
          "human_summary",
          "confidence_interval_low",
          "confidence_interval_high",
          "reason_codes",
          "citation_spans",
        ],
        num_results: 30,
      }),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(await response.text());
  }

  const payload = (await response.json()) as DatabricksStatementResponse;
  return (payload.result?.data_array ?? [])
    .map((row) => vectorRowToFacility(row, query, intent.terms))
    .filter((facility) => {
      const stateMatches = state === "all" || facility.state === state;
      const scoreMatches = facility.score >= minScore;
      const bandMatches =
        !intent.band ||
        facility.band === intent.band ||
        (intent.riskIntent && ["low", "suspicious"].includes(facility.band));
      const contradictionMatches = !intent.contradictionIntent || facility.contradictions > 0;
      const webMatches = !intent.webProofIntent || facility.webHits > 0;
      return stateMatches && scoreMatches && bandMatches && contradictionMatches && webMatches;
    })
    .slice(0, 10);
}

async function queryGoldSql(
  host: string,
  token: string,
  warehouseId: string,
  query: string,
  state: string,
  minScore: number,
  intent: SearchIntent,
) {
  const stateClause = state === "all" ? "" : `AND state = '${state}'`;
  const textBlob = `
    lower(concat_ws(' ',
      coalesce(name, ''),
      coalesce(human_summary, ''),
      coalesce(cast(reason_codes as string), ''),
      coalesce(cast(citation_spans as string), '')
    ))
  `;
  const termClause =
    intent.terms.length === 0
      ? "1 = 1"
      : intent.terms
          .map((term) => `${textBlob} LIKE lower('%${sqlString(term)}%')`)
          .join(" OR ");
  const bandClause = intent.band
    ? intent.riskIntent
      ? "AND score_band IN ('low', 'suspicious')"
      : `AND score_band = '${intent.band}'`
    : "";
  const riskClause = intent.riskIntent
    ? "AND (score_band IN ('low', 'suspicious') OR size(reason_codes) > 0 OR human_summary NOT LIKE '%Web hits: 10%')"
    : "";
  const contradictionClause = intent.contradictionIntent
    ? "AND human_summary NOT LIKE '%Contradictions: 0%'"
    : "";
  const webProofClause = intent.webProofIntent ? "AND human_summary LIKE '%Web hits: 10%'" : "";
  const statement = `
    SELECT
      facility_id,
      name,
      state,
      score,
      score_band,
      human_summary,
      confidence_interval_low,
      confidence_interval_high,
      reason_codes,
      citation_spans
    FROM ${GOLD_TABLE}
    WHERE score >= ${minScore}
      ${stateClause}
      AND (${termClause})
      ${bandClause}
      ${riskClause}
      ${contradictionClause}
      ${webProofClause}
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
    throw new Error(await response.text());
  }

  const payload = (await response.json()) as DatabricksStatementResponse;
  return (payload.result?.data_array ?? []).map((row) => rowToFacility(row, query, intent.terms));
}

export async function GET(request: Request) {
  const host = process.env.DATABRICKS_HOST?.replace(/\/$/, "");
  const token = process.env.DATABRICKS_TOKEN;
  const warehouseId = process.env.DATABRICKS_WAREHOUSE_ID;

  if (!host || !token) {
    return NextResponse.json(
      {
        error:
          "Databricks is not configured. Set DATABRICKS_HOST and DATABRICKS_TOKEN.",
      },
      { status: 503 },
    );
  }

  const { searchParams } = new URL(request.url);
  const query = sqlString(searchParams.get("q") || "dialysis");
  const minScore = clampScore(searchParams.get("minScore"));
  const intent = deriveIntent(query);
  const requestedState = sqlString(searchParams.get("state") || "all");
  const state =
    requestedState === "all" && intent.state ? sqlString(intent.state) : requestedState;

  try {
    const facilities = await queryVectorSearch(host, token, query, state, minScore, intent);
    if (facilities.length > 0) {
      return NextResponse.json({
        source: "mosaic-vector-search",
        facilities,
      });
    }
    throw new Error("Vector Search returned no rows after filters.");
  } catch (vectorError) {
    if (!warehouseId) {
      return NextResponse.json(
        {
          error:
            "Vector Search failed and DATABRICKS_WAREHOUSE_ID is missing for SQL fallback.",
          detail: vectorError instanceof Error ? vectorError.message : String(vectorError),
        },
        { status: 503 },
      );
    }

    try {
      const facilities = await queryGoldSql(host, token, warehouseId, query, state, minScore, intent);
      return NextResponse.json({
        source: "databricks-sql-intent",
        warning: vectorError instanceof Error ? vectorError.message : String(vectorError),
        facilities,
      });
    } catch (sqlError) {
      return NextResponse.json(
        {
          error: `Vector Search and SQL fallback both failed.`,
          vectorError: vectorError instanceof Error ? vectorError.message : String(vectorError),
          sqlError: sqlError instanceof Error ? sqlError.message : String(sqlError),
        },
        { status: 502 },
      );
    }
  }
}
