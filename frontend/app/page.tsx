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

const facilities = [
  {
    id: "FAC000864",
    name: "Apollo Dialysis Clinic, S.S Hospitals",
    state: "Rajasthan",
    score: 80,
    band: "high",
    summary:
      "Apollo Dialysis Clinic, S.S Hospitals scores 80/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC003957",
    name: "Dr. Mudit Khurana Dialysis Centre",
    state: "Uttar Pradesh",
    score: 80,
    band: "high",
    summary:
      "Dr. Mudit Khurana Dialysis Centre scores 80/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005570",
    name: "I Care Diagnostic and Dialysis Center",
    state: "Maharashtra",
    score: 78,
    band: "high",
    summary:
      "I Care Diagnostic and Dialysis Center scores 78/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005372",
    name: "Hfrc Dialysis Center",
    state: "Maharashtra",
    score: 73,
    band: "high",
    summary:
      "Hfrc Dialysis Center scores 73/100. Web hits: 10. Contradictions: 0. Outlier flags: 0.",
  },
  {
    id: "FAC005135",
    name: "GR Dialysis Centre",
    state: "Tamil Nadu",
    score: 73,
    band: "high",
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
            <a href="#results" className="button primary">
              See Priya&apos;s dialysis shortlist
            </a>
            <a href="#evidence" className="button secondary">
              Audit the reasoning
            </a>
          </div>
        </div>

        <div className="command-card" aria-label="Demo query">
          <div className="card-topline">
            <span>District officer query</span>
            <span className="live-dot">SQL fallback live</span>
          </div>
          <code>
            SELECT name, state, score
            <br />
            FROM pramaana.gold.facilities_scored
            <br />
            WHERE human_summary LIKE &apos;%dialysis%&apos;
            <br />
            ORDER BY score DESC LIMIT 5;
          </code>
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
        </div>

        <div className="facility-list">
          {facilities.map((facility, index) => (
            <article key={facility.id} className="facility-card">
              <div className="rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="facility-main">
                <div>
                  <p className="facility-id">{facility.id}</p>
                  <h3>{facility.name}</h3>
                  <span>{facility.state}</span>
                </div>
                <p>{facility.summary}</p>
              </div>
              <div className="score-pill">
                <strong>{facility.score}</strong>
                <span>{facility.band}</span>
              </div>
            </article>
          ))}
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
