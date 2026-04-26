# PRAMAANA

**"The trust-first reasoning layer for Indian healthcare. Every recommendation comes with a confidence interval, a citation, and a contradiction flag."**

Hack-Nation 5th Global AI Hackathon — Track: Databricks "Serving A Nation"

---

## Architecture

```
RAW XLSX (10,000 rows)
         |
         v
[Unity Catalog] pramaana.bronze.facilities_raw
         |
         v
[AGENT 1: EXTRACTOR]  Pydantic-structured LLM extraction from free text
  - Model: Databricks-served Llama via Agent Bricks
  - Output: ExtractedFacility (staffing + equipment + capability claims)
         |
         v
pramaana.silver.facilities_extracted
         |
   +-----+-----+-----+
   |           |     |
   v           v     v
[2A INTERNAL] [2B TAVILY] [2C STAT]
 Logic rules   Live web    Wilson-score
 checker       corroboration CI at PIN-code
                (KILLSHOT)   level
   |           |     |
   +-----+-----+-----+
         |
         v
pramaana.silver.facilities_validated
         |
         v
[AGENT 3: TRUST SCORER]  0-100 score + CI + reason codes + citations
         |
         v
pramaana.gold.facilities_scored
         |
         v
[Mosaic AI Vector Search Index]
         |
         v
[AGENT 4: REASONER]  Tool-calling orchestrator (MLflow traced)
         |
         v
[FastAPI on Databricks Model Serving]
         |
         v
[Next.js + Leaflet on Vercel]  India map with trust score overlays
```

---

## The Killshot (Agent 2B)

Agent 2B hits the **live Tavily Search API** per facility:

```
query = "{facility_name} {city} {state} {claimed_capability}"
```

- Zero Tavily results + zero social presence = hard evidence of a false claim
- Trust Score drops to `suspicious` band
- Contradiction flags are surfaced in the UI with citation spans
- No other team has live web corroboration baked into the scoring pipeline

---

## Demo Persona

**Priya**, district health officer in rural Bihar.

She has 30 minutes to decide where to allocate a mobile dialysis unit across 10,000 messy facility records she doesn't trust.

PRAMAANA shows her:
1. A map of Bihar filtered to `performs_dialysis = true`
2. Each pin colored by trust score band (green/yellow/red/black)
3. One click → full reasoning trace: what the LLM extracted, what Tavily found, what the CI says
4. A ranked list with `human_summary` + contradiction flags

---

## Judging Criteria Checklist

| Criterion | Weight | Our approach | Status |
|---|---|---|---|
| Discovery & Verification | 35% | Self-checking extraction + Wilson CIs + Tavily live corroboration | Phase 2-4 |
| IDP Innovation | 30% | Multi-step agentic loop, MLflow 3 traces on every span | Phase 2-5 |
| Social Impact & Utility | 25% | Priya demo: map + ranked list + actionable insight in 30 min | Phase 6 |
| UX & Transparency | 10% | Visible chain-of-thought, row-level citations, contradiction flags | Phase 6 |

---

## Required Sponsor Tech

| Technology | Usage |
|---|---|
| Databricks Free Edition + Unity Catalog | Bronze/Silver/Gold Delta tables |
| Agent Bricks (Databricks-served Llama) | Agent 1 primary LLM |
| Mosaic AI Vector Search | `/query` semantic facility search |
| MLflow 3 Tracing | Every agent step, every LLM call, every tool call |
| Pydantic v2 | `RawFacilityRow`, `ExtractedFacility`, `ValidationFlags`, `TrustScore` |

---

## Setup

```bash
git clone https://github.com/abdelaalimouid/pramaana.git
cd pramaana
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in DATABRICKS_HOST, DATABRICKS_TOKEN, TAVILY_API_KEY, MLFLOW_EXPERIMENT_NAME
```

### On Databricks

1. Upload `VF_Hackathon_Dataset_India_Large.xlsx` to `/Volumes/pramaana/bronze/raw/`
2. Run `notebooks/00_smoke_test.py` — verify MLflow traces appear
3. Run `notebooks/01_ingest.py` — verify `pramaana.bronze.facilities_raw` has 10,000 rows
4. Run `notebooks/02_extract.py` — Agent 1
5. Run `notebooks/03_validate.py` — Agents 2A + 2B + 2C
6. Run `notebooks/04_score.py` — Agent 3 → Gold table
7. Run `notebooks/05_vector_index.py` — Mosaic Vector Search

---

## Phase Plan

| Phase | Hours | Description |
|---|---|---|
| 1 | 0–2 | Ingestion & Governance (Bronze Delta) |
| 2 | 2–6 | Extractor Agent (LLM structured extraction) |
| 3 | 6–10 | Triple Validation (internal + Tavily + stat) |
| 4 | 10–12 | Trust Scoring (Gold table) |
| 5 | 12–15 | Vector Index + Reasoner orchestrator |
| 6 | 15–19 | Frontend (v0 → Cursor → Vercel) |
| 7 | 19–21 | Submission artifacts (Loom, README final) |
| 8 | 21–22 | Buffer |

Code freeze: Sunday 11:00 AM Casablanca (6:00 AM ET)
Submission deadline: Sunday 2:00 PM Casablanca (9:00 AM ET)

---

## Final Hackathon Results

PRAMAANA completed the full Databricks pipeline over the Virtue Foundation India
10k facility dataset:

| Layer | Output | Result |
|---|---:|---|
| Bronze raw facilities | `pramaana.bronze.facilities_raw` | 10,000 rows |
| Silver extracted claims | `pramaana.silver.facilities_extracted` | 10,000 rows |
| Silver validation flags | `pramaana.silver.facilities_validated` | 10,000 rows |
| Gold trust scores | `pramaana.gold.facilities_scored` | 10,000 rows |
| Tavily live web checks | high-signal facilities | 300 searches |
| Mosaic Vector Search | `pramaana.gold.facilities_scored_vs_index` | Online, 10,000 indexed rows |

Trust interpretation:

| Category | Count | Meaning |
|---|---:|---|
| High trust | 126 | Strongest candidates for action: high score with fewer unresolved verification concerns |
| Medium trust | 9,854 | Potentially useful facilities that should be verified before urgent referral |
| Low / suspicious score | 20 | Facilities below the medium score threshold |

Important: “medium” is not a clean bill of health. PRAMAANA also surfaces
medium-scored facilities with contradiction flags, missing specialist signals,
outlier warnings, or weak web corroboration. The dashboard’s suspicious queries
use those review signals, not only the final low-score count.


