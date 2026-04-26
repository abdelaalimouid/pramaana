import Link from "next/link";

const cards = [
  {
    title: "Discover",
    text: "Extract ICU, dialysis, oncology, neonatal, and emergency capabilities from noisy facility descriptions.",
  },
  {
    title: "Verify",
    text: "Cross-check claims with contradictions, live Tavily web evidence, and local statistical context.",
  },
  {
    title: "Prioritize",
    text: "Rank facilities by trust score, confidence interval, reason codes, and citations for field action.",
  },
];

const pipeline = ["Bronze", "Extraction", "Validation", "Gold", "Search"];

export default function Home() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav">
        <div className="wordmark">PRAMAANA</div>
        <Link href="/dashboard" className="nav-link">
          Open dashboard
        </Link>
      </nav>

      <section className="landing-hero">
        <p className="landing-kicker">Agentic Healthcare Intelligence</p>
        <h1>Verify healthcare capability before lives depend on it.</h1>
        <p className="landing-lede">
          PRAMAANA turns 10,000 unstructured Indian facility records into a
          ranked, traceable intelligence layer for district health decisions.
        </p>
        <div className="landing-actions">
          <Link href="/dashboard" className="primary-link">
            Open Intelligence Dashboard
          </Link>
          <a href="#how" className="secondary-link">
            See how it works
          </a>
        </div>
      </section>

      <section className="landing-metrics" aria-label="Pipeline metrics">
        <div>
          <strong>10,000</strong>
          <span>Gold-scored facilities</span>
        </div>
        <div>
          <strong>300</strong>
          <span>Tavily web checks</span>
        </div>
        <div>
          <strong>126</strong>
          <span>High-trust facilities</span>
        </div>
        <div>
          <strong>Online</strong>
          <span>Mosaic Vector Search</span>
        </div>
      </section>

      <section className="value-grid">
        {cards.map((card) => (
          <article key={card.title}>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </article>
        ))}
      </section>

      <section className="pipeline-strip" id="how">
        {pipeline.map((step, index) => (
          <div key={step} className="pipeline-item">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{step}</strong>
          </div>
        ))}
      </section>

      <section className="landing-proof">
        <div>
          <p className="landing-kicker">Demo persona</p>
          <h2>Priya has 30 minutes to allocate a mobile dialysis unit.</h2>
        </div>
        <p>
          The dashboard lets her ask natural-language questions, search the
          live Mosaic Vector Search index, inspect confidence intervals, and
          fall back to verified Gold-table results if any serving layer is slow.
        </p>
      </section>
    </main>
  );
}
