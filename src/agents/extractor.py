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

_EXTRACTION_PROMPT = """\
You are a medical-records parser. Extract structured healthcare capability claims from the raw text fields below.
Return ONLY valid JSON matching the schema. If a field cannot be determined, use null.

Facility name: {name}
City: {city}, State: {state}
Description: {description}
Specialties: {specialties}
Procedure: {procedure}
Equipment: {equipment}
Capability: {capability}

Output JSON with keys: staffing, equipment, capabilities, extraction_confidence.
staffing keys: has_full_time_doctor, has_anesthesiologist, has_nephrologist, has_oncologist,
               has_emergency_specialist, has_neonatologist, doctor_count_extracted, raw_evidence_span
equipment keys: has_icu, icu_bed_count, has_dialysis_machine, has_oxygen_supply, has_neonatal_unit,
                has_operating_theatre, has_xray, has_ct_scan, has_mri, raw_evidence_span
capabilities keys: performs_emergency_surgery, performs_dialysis, performs_oncology_treatment,
                   performs_neonatal_care, performs_trauma_care, performs_cardiac_care,
                   available_24_7, raw_evidence_span
extraction_confidence: "high" | "medium" | "low"
"""


def _get_llm_client() -> tuple[OpenAI, str]:
    """Return (client, model_name) — Databricks-served Llama primary, OpenAI fallback."""
    databricks_host = os.environ.get("DATABRICKS_HOST")
    databricks_token = os.environ.get("DATABRICKS_TOKEN")
    endpoint = os.environ.get("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")

    if databricks_host and databricks_token:
        client = OpenAI(
            base_url=f"{databricks_host}/serving-endpoints",
            api_key=databricks_token,
        )
        return client, endpoint

    warnings.warn("DATABRICKS_HOST/TOKEN not set — falling back to OpenAI GPT-4o-mini", stacklevel=2)
    fallback_model = os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"]), fallback_model


@trace_agent_run("extractor")
def extract(row: RawFacilityRow, facility_id: str) -> ExtractedFacility:
    """Call LLM to extract structured capability claims from raw facility text fields."""
    client, model = _get_llm_client()

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

    with mlflow.start_span(name="llm_extraction_call", span_type="LLM") as span:
        span.set_inputs({"model": model, "facility_id": facility_id})
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw_json = response.choices[0].message.content
        span.set_outputs({"raw_json_length": len(raw_json)})

    parsed = json.loads(raw_json)

    return ExtractedFacility(
        facility_id=facility_id,
        name=row.name,
        state=row.address_stateOrRegion,
        city=row.address_city,
        pin_code=str(row.address_zipOrPostcode) if row.address_zipOrPostcode else None,
        facility_type=row.facilityTypeId,
        latitude=row.latitude,
        longitude=row.longitude,
        staffing=StaffingClaim(**parsed.get("staffing", {})),
        equipment=EquipmentClaim(**parsed.get("equipment", {})),
        capabilities=CapabilityClaim(**parsed.get("capabilities", {})),
        extraction_model=model,
        extraction_confidence=parsed.get("extraction_confidence", "medium"),
    )
