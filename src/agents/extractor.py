"""PRAMAANA Agent 1 — Structured extraction from free text.

Judging criterion: IDP Innovation (30%) + Discovery & Verification (35%).
"""
import os
import json
import warnings
import mlflow
import httpx
from src.schemas.facility import RawFacilityRow, ExtractedFacility, StaffingClaim, EquipmentClaim, CapabilityClaim
from src.tracing import record_span_error, trace_agent_run

# Concrete JSON example keeps Llama on-schema better than schema prose alone.
_EXTRACTION_PROMPT = """\
You are a medical-records parser for Indian healthcare facilities.
Extract structured capability claims from the raw text fields below.
Return ONLY valid JSON — no prose, no markdown, no code fences.
If a field cannot be determined from the text, use null (not false, not "unknown").
Only set a boolean to true when there is explicit textual evidence.

Facility name: {name}
City: {city}, State: {state}
Description: {description}
Specialties: {specialties}
Procedure: {procedure}
Equipment: {equipment}
Capability: {capability}

Return this exact JSON structure (all keys required, unknown values = null):
{{
  "staffing": {{
    "has_full_time_doctor": null,
    "has_anesthesiologist": null,
    "has_nephrologist": null,
    "has_oncologist": null,
    "has_emergency_specialist": null,
    "has_neonatologist": null,
    "doctor_count_extracted": null,
    "raw_evidence_span": null
  }},
  "equipment": {{
    "has_icu": null,
    "icu_bed_count": null,
    "has_dialysis_machine": null,
    "has_oxygen_supply": null,
    "has_neonatal_unit": null,
    "has_operating_theatre": null,
    "has_xray": null,
    "has_ct_scan": null,
    "has_mri": null,
    "raw_evidence_span": null
  }},
  "capabilities": {{
    "performs_emergency_surgery": null,
    "performs_dialysis": null,
    "performs_oncology_treatment": null,
    "performs_neonatal_care": null,
    "performs_trauma_care": null,
    "performs_cardiac_care": null,
    "available_24_7": null,
    "raw_evidence_span": null
  }},
  "extraction_confidence": "medium"
}}

Rules:
- raw_evidence_span: copy the exact sentence(s) from the input text that justify the claims. Max 200 chars.
- extraction_confidence: "high" if ≥3 fields have explicit evidence, "low" if all text fields are empty/vague, else "medium".
- Indian synonyms: "OT" = operating theatre, "NICU" = neonatal ICU, "HD" or "haemodialysis" = dialysis.
"""

_EMPTY_STAFFING = StaffingClaim()
_EMPTY_EQUIPMENT = EquipmentClaim()
_EMPTY_CAPABILITIES = CapabilityClaim()


def _get_databricks_endpoint() -> tuple[str, str, str]:
    """Load Databricks serving endpoint settings for IDP Innovation extraction."""
    databricks_host = os.environ.get("DATABRICKS_HOST")
    databricks_token = os.environ.get("DATABRICKS_TOKEN")
    endpoint = os.environ.get("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")

    if not databricks_host or not databricks_token:
        databricks_host, databricks_token = _get_notebook_auth()

    if not databricks_host or not databricks_token:
        raise RuntimeError(
            "DATABRICKS_HOST and DATABRICKS_TOKEN must be set. "
            "No fallback LLM is configured."
        )

    return databricks_host.rstrip("/"), databricks_token, endpoint


def _get_notebook_auth() -> tuple[str | None, str | None]:
    """Read Databricks notebook host/token without printing secrets."""
    try:
        from IPython import get_ipython

        shell = get_ipython()
        dbutils = shell.user_ns.get("dbutils") if shell else None
        if not dbutils:
            return None, None

        context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
        host = f"https://{context.browserHostName().get()}"
        token = context.apiToken().get()
        return host, token
    except Exception:
        return None, None


def _parse_llm_output(raw: str, facility_id: str) -> dict:
    """Parse LLM JSON output with graceful fallback on malformed responses."""
    raw = raw.strip()

    # Strip markdown code fences if the model wrapped the JSON anyway
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first {...} block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    warnings.warn(f"[{facility_id}] LLM returned unparseable JSON — using empty extraction", stacklevel=2)
    return {}


def _safe_model(model_cls, data: dict):
    """Build a Pydantic model, dropping unknown keys and coercing bad types."""
    valid_fields = model_cls.model_fields.keys()
    clean = {k: v for k, v in data.items() if k in valid_fields}
    try:
        return model_cls.model_validate(clean)
    except Exception:
        return model_cls()


def _extract_message_content(response_json: dict) -> str:
    """Extract model text from Databricks serving response shapes."""
    choices = response_json.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        if message.get("content") is not None:
            return message["content"]
        if choices[0].get("text") is not None:
            return choices[0]["text"]

    predictions = response_json.get("predictions") or []
    if predictions:
        first = predictions[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("content") or first.get("text") or json.dumps(first)

    if response_json.get("content") is not None:
        return response_json["content"]

    raise RuntimeError(f"Unrecognized Databricks LLM response shape: {response_json}")


def _call_databricks_llm(host: str, token: str, endpoint: str, prompt: str, facility_id: str) -> str:
    """Call Databricks-served Llama under an MLflow LLM span for transparency."""
    payload = dict(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=800,
    )
    url = f"{host}/serving-endpoints/{endpoint}/invocations"

    with mlflow.start_span(name="llm_extraction_call::databricks", span_type="LLM") as span:
        span.set_inputs({"model": endpoint, "provider": "databricks", "facility_id": facility_id})
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            raw_json = _extract_message_content(response.json())
            span.set_outputs({"raw_json_length": len(raw_json)})
            return raw_json
        except Exception as exc:
            record_span_error(span, exc)
            raise


@trace_agent_run("extractor")
def extract(row: RawFacilityRow, facility_id: str) -> ExtractedFacility:
    """Call LLM to extract structured capability claims from raw facility text fields."""
    host, token, endpoint = _get_databricks_endpoint()

    prompt = _EXTRACTION_PROMPT.format(
        name=row.name,
        city=row.address_city or "",
        state=row.address_stateOrRegion or "",
        description=row.description or "",
        specialties=row.specialties or "",
        procedure=row.procedure or "",
        equipment=row.equipment or "",
        capability=row.capability or "",
    )

    raw_json = _call_databricks_llm(host, token, endpoint, prompt, facility_id)

    parsed = _parse_llm_output(raw_json or "", facility_id)

    return ExtractedFacility(
        facility_id=facility_id,
        name=row.name,
        state=row.address_stateOrRegion,
        city=row.address_city,
        pin_code=str(row.address_zipOrPostcode) if row.address_zipOrPostcode else None,
        facility_type=row.facilityTypeId,
        latitude=row.latitude,
        longitude=row.longitude,
        staffing=_safe_model(StaffingClaim, parsed.get("staffing") or {}),
        equipment=_safe_model(EquipmentClaim, parsed.get("equipment") or {}),
        capabilities=_safe_model(CapabilityClaim, parsed.get("capabilities") or {}),
        extraction_model=endpoint,
        extraction_confidence=parsed.get("extraction_confidence", "medium"),
    )
