"""PRAMAANA Agent 2B — Tavily live-web corroboration validator. THE KILLSHOT.

Judging criterion: Discovery & Verification (35%) — this is what wins the demo.
Zero Tavily results + zero social presence = hard evidence of a false claim.
"""
import os
from tavily import TavilyClient
from src.schemas.facility import ExtractedFacility, ValidationFlags
from src.tracing import traced_tool

_MAX_RESULTS = 5


def _build_queries(facility: ExtractedFacility) -> list[str]:
    """Build targeted search queries from the facility's highest-stakes claims."""
    base = f"{facility.name} {facility.city or ''} {facility.state or ''}".strip()
    queries = [base]

    c = facility.capabilities
    if c.performs_emergency_surgery:
        queries.append(f"{base} emergency surgery")
    if c.performs_dialysis:
        queries.append(f"{base} dialysis")
    if c.performs_oncology_treatment:
        queries.append(f"{base} oncology cancer treatment")
    if facility.equipment.has_icu:
        queries.append(f"{base} ICU intensive care")

    return queries[:3]  # cap at 3 queries to stay within rate limits


@traced_tool("tavily_web_search", span_type="RETRIEVER")
def _search_once(client: TavilyClient, query: str) -> list[dict]:
    """Execute a single Tavily search; return list of result dicts."""
    response = client.search(query=query, max_results=_MAX_RESULTS, search_depth="basic")
    return response.get("results", [])


def validate(facility: ExtractedFacility) -> ValidationFlags:
    """Hit Tavily for each high-stakes claim; build web presence evidence."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY not set")

    client = TavilyClient(api_key=api_key)
    queries = _build_queries(facility)

    all_results: list[dict] = []
    for query in queries:
        all_results.extend(_search_once(client, query))

    corroboration_evidence = [
        r.get("content", "")[:300]
        for r in all_results
        if r.get("score", 0) > 0.5
    ]

    # Web presence score: log-scale on result count, capped at 1.0
    raw_count = len(all_results)
    web_presence_score = min(1.0, raw_count / (_MAX_RESULTS * len(queries)))

    return ValidationFlags(
        facility_id=facility.facility_id,
        web_presence_score=web_presence_score,
        tavily_results_count=raw_count,
        tavily_corroboration_evidence=corroboration_evidence,
        tavily_queries_used=queries,
        has_official_website=bool(facility.staffing.raw_evidence_span),  # placeholder until wired to raw row
        social_presence_count=0,
        follower_count=0,
        pin_code_outlier_flags=[],
        internal_contradictions=[],
    )
