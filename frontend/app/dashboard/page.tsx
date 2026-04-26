"use client";

import { useEffect, useMemo, useState } from "react";
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
  reasonCodes?: string[];
  reviewNotes?: string[];
  citationSpans?: string[];
  matchedEvidence?: string;
  matchedTerms?: string[];
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
    reasonCodes: [],
    reviewNotes: [],
    citationSpans: ["[capabilities] dialysis centre with corroborated web presence"],
    matchedEvidence: "Dialysis centre with corroborated web presence",
    matchedTerms: ["dialysis"],
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
    reasonCodes: [],
    reviewNotes: [],
    citationSpans: ["[capabilities] dialysis clinic with corroborated web presence"],
    matchedEvidence: "Dialysis clinic with corroborated web presence",
    matchedTerms: ["dialysis"],
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
    reasonCodes: [],
    reviewNotes: [],
    citationSpans: ["[capabilities] diagnostic and dialysis center"],
    matchedEvidence: "Diagnostic and dialysis center",
    matchedTerms: ["dialysis"],
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
    reasonCodes: [],
    reviewNotes: [],
    citationSpans: ["[capabilities] dialysis centre"],
    matchedEvidence: "Dialysis centre",
    matchedTerms: ["dialysis"],
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
    reasonCodes: [],
    reviewNotes: [],
    citationSpans: ["[capabilities] dialysis center"],
    matchedEvidence: "Dialysis center",
    matchedTerms: ["dialysis"],
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
  Rajasthan: [126, 138],
  "Uttar Pradesh": [218, 138],
  Bihar: [274, 156],
  Jharkhand: [264, 196],
  Maharashtra: [166, 266],
  Telangana: [220, 296],
  Karnataka: [190, 346],
  Gujarat: [92, 190],
  Haryana: [165, 102],
  "Madhya Pradesh": [180, 210],
  Delhi: [178, 118],
  "West Bengal": [302, 190],
  "Tamil Nadu": [238, 392],
};

const INDIA_PATH =
  "M163 18c23-8 63 4 79 18 14 12 32 12 51 25 13 9 22 23 35 33-8 16-7 27 4 43 13 19 24 53 12 83-13 33-30 67-51 94-22 29-43 48-60 71-13 18-16 42-27 60-18-16-29-43-43-71-19-39-42-75-60-113-15-31-31-61-43-91-12-28-35-54-31-84 3-30 34-51 65-60 14-4 27-8 42-13Z";
const INDIA_NE_PATH = "M286 50c20 6 45 14 61 30-9 10-23 13-36 9-17-5-28-18-38-31l13-8Z";

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
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

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
            <svg className="india-map-svg" viewBox="0 0 380 460" aria-label="India capability map">
              <defs>
                <radialGradient id="indiaGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#0f6b55" stopOpacity="0.14" />
                  <stop offset="100%" stopColor="#0f6b55" stopOpacity="0" />
                </radialGradient>
              </defs>
              <ellipse cx="190" cy="235" rx="172" ry="205" fill="url(#indiaGlow)" />
              {[90, 150, 210, 270, 330, 390].map((y) => (
                <line key={`h-${y}`} x1="44" y1={y} x2="350" y2={y} className="india-grid-line" />
              ))}
              {[80, 130, 180, 230, 280, 330].map((x) => (
                <line key={`v-${x}`} x1={x} y1="30" x2={x} y2="430" className="india-grid-line" />
              ))}
              <path d={INDIA_PATH} className="india-shape" />
              <path d={INDIA_NE_PATH} className="india-shape india-shape-ne" />
              <circle cx="274" cy="156" r="31" className="focus-ring" />
              <text x="274" y="113" className="map-label">
                Bihar focus
              </text>

              {results.map((facility, index) => {
                const [x, y] = statePosition[facility.state] ?? [145 + index * 16, 180 + index * 18];
                const selectedMarker = selected?.id === facility.id;
                return (
                  <g key={facility.id} className="marker-group">
                    <circle
                      cx={x}
                      cy={y}
                      r={selectedMarker ? 15 : 11}
                      className={`marker-halo ${bandClass[facility.band]}`}
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r={selectedMarker ? 7 : 5}
                      className={`marker-core ${bandClass[facility.band]}`}
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r="18"
                      className="marker-hit"
                      onClick={() => setSelectedId(facility.id)}
                    />
                  </g>
                );
              })}
            </svg>

            {selected && (
              <div className="map-callout">
                <span>{selected.state}</span>
                <strong>{selected.name}</strong>
                <p>{selected.score}/100 trust score</p>
              </div>
            )}
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
                  {mounted && <em>{facility.matchedEvidence ?? "No citation span available."}</em>}
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
              <div className="why-card">
                <span>Evidence found</span>
                <p>{selected.matchedEvidence ?? "No citation span available."}</p>
                {!!selected.matchedTerms?.length && (
                  <div className="term-row">
                    {selected.matchedTerms.map((term) => (
                      <small key={term}>{term}</small>
                    ))}
                  </div>
                )}
              </div>
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
              <div className="reason-card">
                <span>Review notes</span>
                {selected.reviewNotes?.length ? (
                  <div className="term-row">
                    {selected.reviewNotes.map((note) => (
                      <small key={note}>{note}</small>
                    ))}
                  </div>
                ) : (
                  <p>No issues were flagged for this facility.</p>
                )}
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
