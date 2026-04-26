"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

type Band = "high" | "medium" | "low" | "suspicious";

type Facility = {
  id: string;
  name: string;
  state: string;
  score: number;
  band: Band;
  capability: string;
  webHits: number;
  contradictions: number;
  outliers: number;
  summary: string;
  ciLow?: number;
  ciHigh?: number;
};

type ResultStatus = "ready" | "loading" | "live" | "fallback" | "error";

const DEMO_FACILITIES: Facility[] = [
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
    ciLow: 58,
    ciHigh: 90,
    summary:
      "Dr. Mudit Khurana Dialysis Centre scores 80/100 [HIGH]. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
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
    ciLow: 62,
    ciHigh: 91,
    summary:
      "Apollo Dialysis Clinic, S.S Hospitals scores 80/100 [HIGH]. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
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
    ciLow: 55,
    ciHigh: 88,
    summary:
      "I Care Diagnostic and Dialysis Center scores 78/100 [HIGH]. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
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
    ciLow: 48,
    ciHigh: 84,
    summary:
      "GR Dialysis Centre scores 73/100 [HIGH]. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
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
    ciLow: 50,
    ciHigh: 84,
    summary:
      "Hfrc Dialysis Center scores 73/100 [HIGH]. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
];

const STATES = [
  "all",
  "Bihar",
  "Jharkhand",
  "Maharashtra",
  "Rajasthan",
  "Tamil Nadu",
  "Telangana",
  "Uttar Pradesh",
];

const PROMPTS = [
  "high trust dialysis centers",
  "suspicious ICU claims",
  "oncology facilities with web proof",
  "emergency surgery contradictions",
];

const statePosition: Record<string, [number, number]> = {
  Rajasthan: [28, 34],
  "Uttar Pradesh": [58, 34],
  Bihar: [74, 38],
  Jharkhand: [72, 52],
  Maharashtra: [43, 64],
  Telangana: [59, 68],
  "Tamil Nadu": [66, 86],
};

const bandClass: Record<Band, string> = {
  high: "is-high",
  medium: "is-medium",
  low: "is-low",
  suspicious: "is-suspicious",
};

function getCi(facility: Facility) {
  return {
    low: facility.ciLow ?? Math.max(0, facility.score - 12),
    high: facility.ciHigh ?? Math.min(100, facility.score + 12),
  };
}

export default function Dashboard() {
  const [query, setQuery] = useState("dialysis");
  const [state, setState] = useState("all");
  const [minScore, setMinScore] = useState(45);
  const [status, setStatus] = useState<ResultStatus>("ready");
  const [source, setSource] = useState("Mosaic Vector Search ready");
  const [results, setResults] = useState<Facility[]>(DEMO_FACILITIES);
  const [selectedId, setSelectedId] = useState(DEMO_FACILITIES[0].id);

  const selected = useMemo(
    () => results.find((facility) => facility.id === selectedId) ?? results[0],
    [results, selectedId],
  );

  async function askPramaana() {
    setStatus("loading");
    setSource("Searching Mosaic Vector Search...");
    try {
      const params = new URLSearchParams({
        q: query,
        state,
        minScore: String(minScore),
      });
      const response = await fetch(`/api/facilities?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error ?? "Search failed");
      }
      setResults(payload.facilities);
      setSelectedId(payload.facilities[0]?.id ?? "");
      setStatus("live");
      setSource(
        payload.source === "mosaic-vector-search"
          ? "Live: Mosaic Vector Search"
          : "Live: Databricks SQL fallback",
      );
    } catch (error) {
      setStatus("error");
      setSource(error instanceof Error ? error.message : "Search failed");
    }
  }

  function loadDemo() {
    setQuery("dialysis");
    setState("all");
    setMinScore(45);
    setResults(DEMO_FACILITIES);
    setSelectedId(DEMO_FACILITIES[0].id);
    setStatus("fallback");
    setSource("Static demo loaded from verified Gold output");
  }

  function applyPrompt(prompt: string) {
    setQuery(prompt);
    if (prompt.includes("suspicious") || prompt.includes("low trust")) {
      setMinScore(0);
    } else {
      setMinScore(45);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="app-header">
        <Link href="/" className="app-brand">
          PRAMAANA
        </Link>
        <div className="app-status">
          <span className="status-dot" />
          Vector index online · 10,000 rows
        </div>
      </header>

      <section className="app-grid">
        <aside className="query-card">
          <p className="section-label">Ask PRAMAANA</p>
          <h1>Search verified healthcare capability.</h1>
          <p>
            Natural-language search uses Mosaic Vector Search first, with
            Databricks SQL as the fallback.
          </p>

          <div className="prompt-row">
            {PROMPTS.map((prompt) => (
              <button key={prompt} onClick={() => applyPrompt(prompt)}>
                {prompt}
              </button>
            ))}
          </div>

          <label className="form-field">
            Question
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={3}
              placeholder="Find high-trust dialysis centers near Bihar"
            />
          </label>

          <div className="form-pair">
            <label className="form-field">
              State
              <select value={state} onChange={(event) => setState(event.target.value)}>
                {STATES.map((item) => (
                  <option key={item} value={item}>
                    {item === "all" ? "All states" : item}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Minimum score
              <input
                type="number"
                min={0}
                max={100}
                value={minScore}
                onChange={(event) => setMinScore(Number(event.target.value))}
              />
            </label>
          </div>

          <div className="action-row">
            <button className="primary-action" onClick={askPramaana} disabled={status === "loading"}>
              {status === "loading" ? "Searching..." : "Search live index"}
            </button>
            <button className="secondary-action" onClick={loadDemo}>
              Static demo
            </button>
          </div>

          <p className={`source-note ${status === "error" ? "is-error" : ""}`}>{source}</p>

          <div className="metrics-list">
            <div>
              <strong>10,000</strong>
              <span>Gold scored</span>
            </div>
            <div>
              <strong>300</strong>
              <span>Tavily checked</span>
            </div>
            <div>
              <strong>126</strong>
              <span>High trust</span>
            </div>
          </div>
        </aside>

        <section className="map-card-clean">
          <div className="section-heading">
            <div>
              <p className="section-label">Capability Map</p>
              <h2>{results.length} matched facilities</h2>
            </div>
            <span className={`source-badge source-${status}`}>{status === "live" ? "Live" : "Demo"}</span>
          </div>

          <div className="map-canvas">
            <div className="india-outline" />
            {results.map((facility, index) => {
              const position = statePosition[facility.state] ?? [50 + index * 4, 50 + index * 3];
              return (
                <button
                  key={facility.id}
                  className={`map-marker ${bandClass[facility.band]} ${selected?.id === facility.id ? "is-selected" : ""}`}
                  style={{ left: `${position[0]}%`, top: `${position[1]}%` }}
                  onClick={() => setSelectedId(facility.id)}
                  aria-label={facility.name}
                />
              );
            })}
          </div>

          <div className="map-legend-clean">
            <span><i className="legend-dot is-high" /> High</span>
            <span><i className="legend-dot is-medium" /> Medium</span>
            <span><i className="legend-dot is-low" /> Low</span>
          </div>
        </section>

        <section className="results-card-clean">
          <div className="section-heading">
            <div>
              <p className="section-label">Ranked Results</p>
              <h2>Recommended facilities</h2>
            </div>
          </div>

          <div className="result-list-clean">
            {results.map((facility, index) => (
              <button
                key={facility.id}
                className={`result-row-clean ${selected?.id === facility.id ? "is-active" : ""}`}
                onClick={() => setSelectedId(facility.id)}
              >
                <span className="result-rank">{String(index + 1).padStart(2, "0")}</span>
                <span className="result-main">
                  <strong>{facility.name}</strong>
                  <small>{facility.state} · {facility.webHits} web hits · {facility.contradictions} contradictions</small>
                </span>
                <span className={`score-chip ${bandClass[facility.band]}`}>{facility.score}</span>
              </button>
            ))}
          </div>
        </section>

        <aside className="evidence-card-clean">
          <p className="section-label">Evidence</p>
          {selected ? (
            <>
              <h2>{selected.name}</h2>
              <p>{selected.summary}</p>
              <div className="ci-card">
                <span>Confidence interval</span>
                <div className="ci-line">
                  <i
                    style={{
                      left: `${getCi(selected).low}%`,
                      width: `${getCi(selected).high - getCi(selected).low}%`,
                    }}
                  />
                  <b style={{ left: `${selected.score}%` }} />
                </div>
                <small>
                  {getCi(selected).low} to {getCi(selected).high}, score {selected.score}
                </small>
              </div>
              <div className="evidence-grid-small">
                <div><strong>{selected.webHits}</strong><span>Web hits</span></div>
                <div><strong>{selected.contradictions}</strong><span>Contradictions</span></div>
                <div><strong>{selected.outliers}</strong><span>Outliers</span></div>
              </div>
            </>
          ) : (
            <p>No facility selected.</p>
          )}
        </aside>
      </section>
    </main>
  );
}
