"""PRAMAANA FastAPI — Model Serving endpoint.

Judging criterion: Social Impact & Utility (25%) — demo surface for Priya persona.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.schemas.facility import RawFacilityRow, TrustScore
from src.tracing import _init_experiment

_init_experiment()

app = FastAPI(title="PRAMAANA", version="0.1.0")


class ScoreRequest(BaseModel):
    facility_id: str
    row: RawFacilityRow
    pin_stats: dict = {}


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "service": "pramaana"}


@app.post("/score", response_model=TrustScore)
def score_facility(request: ScoreRequest) -> TrustScore:
    """Run the full Extract→Validate→Score pipeline for a single facility."""
    from src.agents.reasoner import reason
    try:
        result = reason(request.row, request.facility_id, request.pin_stats)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/query")
def query_facilities(
    state: str | None = None,
    capability: str | None = None,
    min_score: int = 0,
    limit: int = 20,
) -> dict:
    """Vector-search endpoint — wired to Mosaic Vector Search in Phase 5."""
    # TODO Phase 5: replace stub with Databricks Vector Search SDK call
    return {
        "results": [],
        "message": "Vector search not yet wired — Phase 5 pending",
        "filters": {"state": state, "capability": capability, "min_score": min_score},
    }
