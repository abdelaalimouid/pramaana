"use client";

import { useMemo, useState } from "react";

const stats = [
  { label: "Bronze records", value: "10,000", detail: "raw Indian facility rows" },
  { label: "Silver extracted", value: "10,000", detail: "LLM + rules capability claims" },
  { label: "Tavily checks", value: "300", detail: "live web corroboration searches" },
  { label: "Gold scored", value: "10,000", detail: "trust scores with citations" },
];

const scoreBands = [
  { label: "High trust", value: 126, color: "var(--green)" },
  { label: "Medium trust", value: 9854, color: "var(--amber)" },
  { label: "Low trust", value: 20, color: "var(--red)" },
];

type Facility = {
  id: string;
  name: string;
  state: string;
  score: number;
  band: "high" | "medium" | "low";
  capability: string;
  webHits: number;
  contradictions: number;
  outliers: number;
  summary: string;
};

type ResultStatus = "ready" | "loading" | "live" | "fallback" | "error";

const staticDemoQuery = {
  capability: "dialysis",
  state: "all",
  minScore: 45,
};

const facilities: Facility[] = [
  {
    id: "FAC000864",
    name: "Apollo Dialysis Clinic, S.S Hospitals",
    state: "Rajasthan",
    score: 80,
    band: "high",
    capability: "dialysis",
    webHits: 10,
    contradictions: 0,
    outliers: 0,
    summary:
      "Apollo Dialysis Clinic, S.S Hospitals scores 80/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC003957",
    name: "Dr. Mudit Khurana Dialysis Centre",
    state: "Uttar Pradesh",
    score: 80,
    band: "high",
    capability: "dialysis",
    webHits: 10,
    contradictions: 0,
    outliers: 0,
    summary:
      "Dr. Mudit Khurana Dialysis Centre scores 80/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005570",
    name: "I Care Diagnostic and Dialysis Center",
    state: "Maharashtra",
    score: 78,
    band: "high",
    capability: "dialysis",
    webHits: 10,
    contradictions: 0,
    outliers: 0,
    summary:
      "I Care Diagnostic and Dialysis Center scores 78/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005372",
    name: "Hfrc Dialysis Center",
    state: "Maharashtra",
    score: 73,
    band: "high",
    capability: "dialysis",
    webHits: 10,
    contradictions: 0,
    outliers: 0,
    summary:
      "Hfrc Dialysis Center scores 73/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005135",
    name: "GR Dialysis Centre",
    state: "Tamil Nadu",
    score: 73,
    band: "high",
    capability: "dialysis",
    webHits: 10,
    contradictions: 0,
    outliers: 0,
    summary:
      "GR Dialysis Centre scores 73/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
];

const pipeline = [
  "Bronze: 10,000 messy facility rows landed in Unity Catalog",
  "Agent 1: 500 LLM rows + 9,500 deterministic coverage rows",
  "Agents 2A/2B/2C: contradiction checks, Tavily web proof, PIN-code statistics",
  "Agent 3: trust score, Wilson-style confidence interval, reason codes",
  "Agent 4: Mosaic Vector Search index created and syncing in Databricks",
];

export default function Home() {
  const [query, setQuery] = useState(staticDemoQuery.capability);
  const [state, setState] = useState(staticDemoQuery.state);
  const [minScore, setMinScore] = useState(staticDemoQuery.minScore);
  const [status, setStatus] = useState<ResultStatus>("ready");
  const [liveResults, setLiveResults] = useState<Facility[] | null>(null);
  const [message, setMessage] = useState(
    "Ready to query the agent-produced Gold table.",
  );

  const availableStates = useMemo(
    () => ["all", ...Array.from(new Set(facilities.map((facility) => facility.state))).sort()],
    [],
  );

  const cachedResults = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return facilities
      .filter((facility) => {
        const matchesQuery =
          !normalizedQuery ||
          facility.name.toLowerCase().includes(normalizedQuery) ||
          facility.capability.toLowerCase().includes(normalizedQuery) ||
          facility.summary.toLowerCase().includes(normalizedQuery);
        const matchesState = state === "all" || facility.state === state;
        return matchesQuery && matchesState && facility.score >= minScore;
      })
      .sort((a, b) => b.score - a.score);
  }, [query, state, minScore]);

  const results = status === "live" && liveResults ? liveResults : cachedResults;

  const runDynamicSearch = async () => {
    setStatus("loading");
    setMessage("Querying pramaana.gold.facilities_scored through Databricks SQL...");
    try {
      const params = new URLSearchParams({
        q: query,
        state,
        minScore: String(minScore),
      });
      const response = await fetch(`/api/facilities?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Databricks query failed");
      }
      setLiveResults(payload.facilities);
      setStatus("live");
      setMessage(
        `Live Databricks SQL returned ${payload.facilities.length} Gold rows.`,
      );
    } catch (error) {
      setStatus("error");
      setLiveResults(null);
      setMessage(
        error instanceof Error
          ? error.message
          : "Dynamic query failed. Use the static demo fallback.",
      );
    }
  };

  const loadStaticDemo = () => {
    setQuery(staticDemoQuery.capability);
    setState(staticDemoQuery.state);
    setMinScore(staticDemoQuery.minScore);
    setLiveResults(null);
    setStatus("fallback");
    setMessage("Static Priya dialysis shortlist loaded from the verified Gold output.");
  };

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">PRAMAANA / Agentic Healthcare Intelligence</p>
          <h1>Find the lifesaving facilities hidden inside unreliable records.</h1>
          <p className="lede">
            A trust-first reasoning layer for Indian healthcare: every facility
            recommendation carries a score, confidence interval, citation span,
            contradiction flag, and live web corroboration signal.
          </p>
          <div className="hero-actions">
            <button className="button primary" onClick={runDynamicSearch}>
              {status === "loading" ? "Querying..." : "Run dynamic search"}
            </button>
            <button className="button secondary" onClick={loadStaticDemo}>
              Load static demo
            </button>
            <a href="#evidence" className="button secondary">
              Audit the reasoning
            </a>
          </div>
        </div>

        <div className="command-card" aria-label="Demo query">
          <div className="card-topline">
            <span>District officer query</span>
            <span className="live-dot">
              {status === "live"
                ? "live Gold table"
                : status === "fallback"
                  ? "static fallback"
                  : status === "error"
                    ? "fallback available"
                    : "dynamic ready"}
            </span>
          </div>
          <div className="query-panel">
            <label>
              Capability or facility
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="dialysis, ICU, oncology..."
              />
            </label>
            <label>
              State
              <select value={state} onChange={(event) => setState(event.target.value)}>
                {availableStates.map((item) => (
                  <option key={item} value={item}>
                    {item === "all" ? "All states" : item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Minimum trust score
              <input
                type="number"
                min="0"
                max="100"
                value={minScore}
                onChange={(event) => setMinScore(Number(event.target.value))}
              />
            </label>
            <button className="button light" onClick={runDynamicSearch}>
              {status === "loading" ? "Querying Gold..." : "Query Gold table"}
            </button>
            <button className="button ghost" onClick={loadStaticDemo}>
              Use static example
            </button>
          </div>
          <div className="map-plate">
            <span className="pin pin-a" />
            <span className="pin pin-b" />
            <span className="pin pin-c" />
            <span className="pin pin-d" />
            <span className="pin pin-e" />
            <p>10,000 facilities scored across India</p>
          </div>
        </div>
      </section>

      <section className="stats-grid" aria-label="Pipeline metrics">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </section>

      <section className="split-section">
        <div className="panel">
          <p className="eyebrow">Trust distribution</p>
          <h2>Gold table is complete.</h2>
          <p>
            PRAMAANA scored every row, then surfaced the facilities worth acting
            on first. The system is conservative: only 126 facilities reached
            high trust.
          </p>
          <div className="band-list">
            {scoreBands.map((band) => (
              <div key={band.label} className="band-row">
                <span style={{ backgroundColor: band.color }} />
                <p>{band.label}</p>
                <strong>{band.value.toLocaleString()}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="panel dark" id="evidence">
          <p className="eyebrow">Why judges should care</p>
          <h2>Not a chatbot. An audit trail.</h2>
          <ul className="evidence-list">
            {pipeline.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="results-section" id="results">
        <div>
          <p className="eyebrow">Priya demo</p>
          <h2>Where should a mobile dialysis unit go first?</h2>
          <p>
            Ranked facilities from the Gold Delta table. Each result combines
            extracted capability, Tavily corroboration, contradiction checks,
            and statistical outlier detection.
          </p>
          <div className="query-status">
            <strong>{results.length}</strong>
            <span>
              {status === "live"
                ? "live Gold rows returned"
                : status === "fallback"
                  ? "static demo results loaded"
                  : status === "error"
                    ? "cached rows shown after query error"
                    : "matching cached demo rows"}
            </span>
          </div>
          <p className={`status-note ${status === "error" ? "is-error" : ""}`}>
            {message}
          </p>
        </div>

        <div className="facility-list">
          {results.map((facility, index) => (
            <article key={facility.id} className="facility-card">
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="facility-main">
                <div>
                  <p className="facility-id">{facility.id}</p>
                  <h3>{facility.name}</h3>
                  <span>{facility.state}</span>
                </div>
                <p>{facility.summary}</p>
                <div className="evidence-chips">
                  <span>{facility.webHits} web hits</span>
                  <span>{facility.contradictions} contradictions</span>
                  <span>{facility.outliers} outliers</span>
                </div>
              </div>
              <div className="score-pill">
                <strong>{facility.score}</strong>
                <span>{facility.band}</span>
              </div>
            </article>
          ))}
          {results.length === 0 && (
            <article className="empty-state">
              <h3>No matching cached demo rows.</h3>
              <p>
                Use “Load static demo” to restore the verified dialysis example,
                or check the Databricks SQL warehouse credentials for live mode.
              </p>
            </article>
          )}
        </div>
      </section>

      <section className="closing-panel">
        <p className="eyebrow">Submission line</p>
        <h2>
          PRAMAANA turns a spreadsheet nobody trusts into a ranked, traceable
          healthcare intelligence layer.
        </h2>
        <p>
          Built on Databricks Unity Catalog, MLflow tracing, Pydantic schemas,
          Tavily validation, Delta Gold scoring, and Mosaic Vector Search index
          provisioning.
        </p>
      </section>
    </main>
  );
}
