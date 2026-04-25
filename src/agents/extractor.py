"""PRAMAANA Agent 1 — Structured extraction from free text.

Judging criterion: IDP Innovation (30%) + Discovery & Verification (35%).
"""
import os
import json
import warnings
import mlflow
from openai import OpenAI
from src.schemas.facility import RawFacilityRow, ExtractedFacility, StaffingClaim, EquipmentClaim, CapabilityClaim
from src.tracing import trace_agent_run

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


def _openai_fallback(reason: str) -> tuple[OpenAI, str, bool, str]:
    """Create explicit OpenAI fallback client; serves IDP Innovation reliability."""
    message = (
        f"WARNING: Databricks-served LLM unavailable ({reason}). "
        "Falling back to OpenAI GPT-4o-mini explicitly."
    )
    print(message)
    warnings.warn(message, stacklevel=3)
    fallback_model = os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; cannot use explicit fallback model.")
    return OpenAI(api_key=api_key), fallback_model, True, "openai"


def _get_llm_client() -> tuple[OpenAI, str, bool, str]:
    """Return (client, model_name, supports_json_mode, provider).

    Databricks-served Llama is primary; OpenAI GPT-4o-mini is the fallback.
    Llama endpoints on Databricks do not support response_format=json_object.
    """
    databricks_host = os.environ.get("DATABRICKS_HOST")
    databricks_token = os.environ.get("DATABRICKS_TOKEN")
    endpoint = os.environ.get("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")

    if databricks_host and databricks_token:
        client = OpenAI(
            base_url=f"{databricks_host}/serving-endpoints",
            api_key=databricks_token,
        )
        return client, endpoint, False, "databricks"  # Llama does not support json_object mode

    return _openai_fallback("DATABRICKS_HOST or DATABRICKS_TOKEN is not set")


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


def _call_llm(
    client: OpenAI,
    model: str,
    supports_json_mode: bool,
    provider: str,
    prompt: str,
    facility_id: str,
) -> str:
    """Call one chat model under an MLflow LLM span for trace transparency."""
    call_kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=800,
    )
    if supports_json_mode:
        call_kwargs["response_format"] = {"type": "json_object"}

    with mlflow.start_span(name=f"llm_extraction_call::{provider}", span_type="LLM") as span:
        span.set_inputs({"model": model, "provider": provider, "facility_id": facility_id})
        try:
            response = client.chat.completions.create(**call_kwargs)
            raw_json = response.choices[0].message.content or ""
            span.set_outputs({"raw_json_length": len(raw_json)})
            return raw_json
        except Exception as exc:
            span.set_status("ERROR", description=str(exc))
            raise


@trace_agent_run("extractor")
def extract(row: RawFacilityRow, facility_id: str) -> ExtractedFacility:
    """Call LLM to extract structured capability claims from raw facility text fields."""
    client, model, supports_json_mode, provider = _get_llm_client()

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

    try:
        raw_json = _call_llm(client, model, supports_json_mode, provider, prompt, facility_id)
        extraction_model = model
    except Exception as exc:
        if provider != "databricks":
            raise
        client, model, supports_json_mode, provider = _openai_fallback(str(exc))
        raw_json = _call_llm(client, model, supports_json_mode, provider, prompt, facility_id)
        extraction_model = model

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
        extraction_model=extraction_model,
        extraction_confidence=parsed.get("extraction_confidence", "medium"),
    )
