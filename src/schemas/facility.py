"""PRAMAANA — Pydantic schema for the Virtue Foundation India 10k dataset.

LOCKED at hour 1. Mapped exactly to the 41 columns in
VF_Hackathon_Dataset_India_Large.xlsx.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ============================================================
# RAW INPUT — mirrors the XLSX columns we actually use
# ============================================================
class RawFacilityRow(BaseModel):
    """Subset of the 41 columns we feed to the Extractor Agent."""
    name: str
    description: Optional[str] = None
    specialties: Optional[str] = None
    procedure: Optional[str] = None
    equipment: Optional[str] = None
    capability: Optional[str] = None
    numberDoctors: Optional[float] = None  # XLSX often loads ints as floats
    capacity: Optional[float] = None
    facilityTypeId: Optional[str] = None
    address_city: Optional[str] = None
    address_stateOrRegion: Optional[str] = None
    address_zipOrPostcode: Optional[str] = None
    
    # Web/social signals — pre-computed in the dataset
    officialWebsite: Optional[str] = None
    facebookLink: Optional[str] = None
    linkedinLink: Optional[str] = None
    distinct_social_media_presence_count: Optional[float] = None
    engagement_metrics_n_followers: Optional[float] = None
    recency_of_page_update: Optional[str] = None
    
    # Geo
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ============================================================
# AGENT 1 OUTPUT — Structured extraction
# ============================================================
class StaffingClaim(BaseModel):
    has_full_time_doctor: Optional[bool] = None
    has_anesthesiologist: Optional[bool] = None
    has_nephrologist: Optional[bool] = None
    has_oncologist: Optional[bool] = None
    has_emergency_specialist: Optional[bool] = None
    has_neonatologist: Optional[bool] = None
    doctor_count_extracted: Optional[int] = None
    raw_evidence_span: Optional[str] = Field(
        None,
        description="Exact sentence from description/specialties/procedure that supports these staffing claims."
    )


class EquipmentClaim(BaseModel):
    has_icu: Optional[bool] = None
    icu_bed_count: Optional[int] = None
    has_dialysis_machine: Optional[bool] = None
    has_oxygen_supply: Optional[bool] = None
    has_neonatal_unit: Optional[bool] = None
    has_operating_theatre: Optional[bool] = None
    has_xray: Optional[bool] = None
    has_ct_scan: Optional[bool] = None
    has_mri: Optional[bool] = None
    raw_evidence_span: Optional[str] = None


class CapabilityClaim(BaseModel):
    performs_emergency_surgery: Optional[bool] = None
    performs_dialysis: Optional[bool] = None
    performs_oncology_treatment: Optional[bool] = None
    performs_neonatal_care: Optional[bool] = None
    performs_trauma_care: Optional[bool] = None
    performs_cardiac_care: Optional[bool] = None
    available_24_7: Optional[bool] = None
    raw_evidence_span: Optional[str] = None


class ExtractedFacility(BaseModel):
    facility_id: str  # we'll synthesize this from row index since dataset has no ID
    name: str
    state: Optional[str] = None
    city: Optional[str] = None
    pin_code: Optional[str] = None
    facility_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    staffing: StaffingClaim
    equipment: EquipmentClaim
    capabilities: CapabilityClaim
    
    extraction_model: str
    extraction_confidence: Literal["high", "medium", "low"] = "medium"


# ============================================================
# AGENT 2 OUTPUT — Triple validation
# ============================================================
class ValidationFlags(BaseModel):
    facility_id: str
    
    # 2A: Internal logical validator
    internal_contradictions: list[str] = Field(default_factory=list)
    
    # 2B: TAVILY KILLSHOT — live web corroboration
    web_presence_score: float = Field(0.0, ge=0.0, le=1.0)
    tavily_results_count: int = 0
    tavily_corroboration_evidence: list[str] = Field(default_factory=list)
    tavily_queries_used: list[str] = Field(default_factory=list)
    
    # 2B-bonus: dataset-native web signals (free win)
    has_official_website: bool = False
    social_presence_count: int = 0
    follower_count: int = 0
    
    # 2C: Statistical / population-level validator
    pin_code_outlier_flags: list[str] = Field(default_factory=list)


# ============================================================
# AGENT 3 OUTPUT — Trust Score (Gold layer)
# ============================================================
class TrustScore(BaseModel):
    facility_id: str
    name: str
    state: Optional[str]
    pin_code: Optional[str]
    
    score: int = Field(ge=0, le=100)
    confidence_interval_low: int
    confidence_interval_high: int
    
    reason_codes: list[str]  # e.g., ["NO_WEB_PRESENCE", "CLAIM_STAFF_MISMATCH"]
    human_summary: str = Field(max_length=500)
    citation_spans: list[str]
    
    # Surfaced for the UI
    score_band: Literal["high", "medium", "low", "suspicious"]