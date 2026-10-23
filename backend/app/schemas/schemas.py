"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.rules import (BLOOD_GROUPS, CANDIDATE_STATUSES, COMPONENTS, GENDERS, REQUEST_STATUSES, URGENCIES)

BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
Component = Literal["Whole Blood", "Packed Red Cells", "Platelets", "Plasma"]
Gender = Literal["Female", "Male", "Other", "Prefer not to say"]
Urgency = Literal["Critical", "Urgent", "Routine"]
RequestStatus = Literal["open", "under_review", "awaiting_confirmation", "partially_fulfilled", "fulfilled", "cancelled"]
CandidateType = Literal["blood_bank", "donor"]
EventType = Literal["STOCK_UNAVAILABLE", "DONOR_DECLINED", "DONOR_NO_RESPONSE", "DATA_STALE",
                    "SELECT_FOR_REVIEW", "CONFIRM_AVAILABILITY", "REINSTATE_CANDIDATE", "COORDINATOR_NOTE"]
StrictAge = Annotated[int, Field(strict=True, ge=0, le=120)]
StrictUnits = Annotated[int, Field(strict=True, ge=1, le=20)]


# ---------------------------------------------------------------- requests
class RequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    patient_name: str = Field(min_length=2, max_length=100)
    patient_age: StrictAge
    patient_gender: Gender
    patient_blood_group: BloodGroup
    component: Component
    units_required: StrictUnits
    hospital_name: str = Field(min_length=2, max_length=120)
    hospital_location: str = Field(min_length=2, max_length=120)
    hospital_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    hospital_longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    urgency: Urgency

    @field_validator("patient_name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not all(ch.isalpha() or ch in " .'-" for ch in v) or sum(ch.isalpha() for ch in v) < 2:
            raise ValueError("Use letters, spaces, full stops, apostrophes or hyphens only.")
        return v

    @model_validator(mode="after")
    def _coords_together(self):
        if (self.hospital_latitude is None) != (self.hospital_longitude is None):
            raise ValueError("Provide both hospital latitude and longitude, or neither.")
        return self


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_name: str
    patient_age: int
    patient_gender: str
    patient_blood_group: str
    component: str
    units_required: int
    hospital_name: str
    hospital_location: str
    hospital_latitude: Optional[float] = None
    hospital_longitude: Optional[float] = None
    urgency: str
    status: str
    created_at: datetime
    updated_at: datetime
    is_demo_data: bool = True


class StatusUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: RequestStatus
    reason: Optional[str] = Field(default=None, max_length=300)
    simulated_confirmation: bool = False


class EventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    event_type: EventType
    candidate_type: Optional[CandidateType] = None
    candidate_id: Optional[str] = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9\-_]+$")
    reason: Optional[str] = Field(default=None, max_length=300)


# --------------------------------------------------------------- candidates
class CandidateResult(BaseModel):
    """One option in a ranking. Keys must match ranking.CANDIDATE_FIELDS."""
    rank: Optional[int] = None
    candidate_type: str
    candidate_id: str
    display_name: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    blood_group: str
    component: Optional[str] = None
    units_available: Optional[int] = None
    review_status: str
    verification_label: str
    freshness: str
    age_hours: Optional[float] = None
    last_updated: Optional[str] = None
    data_source: str = ""
    distance_km: Optional[float] = None
    distance_note: str
    match_level: str
    match_rule: str
    factors: List[str]
    explanation: str
    reduced_priority_reasons: List[str]
    exclusion_reasons: List[str]
    exclusion_category: Optional[str] = None
    priority_tier: Optional[int] = None


class SnapshotOut(BaseModel):
    version: int
    trigger: str
    created_at: datetime
    summary: Dict[str, Any]
    ranked: List[CandidateResult]
    excluded: List[CandidateResult]
    changes: List[str]


class SnapshotSummary(BaseModel):
    version: int
    trigger: str
    created_at: datetime
    ranked_count: int
    excluded_count: int
    top_candidate_id: Optional[str] = None
    top_candidate_name: Optional[str] = None
    changes: List[str]


class RecommendationsOut(BaseModel):
    request_id: str
    current: SnapshotOut
    history: List[SnapshotSummary]
    is_demo_data: bool = True


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    request_id: str
    event_type: str
    timestamp: datetime
    candidate_type: Optional[str] = None
    candidate_id: Optional[str] = None
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    reason: str
    is_simulation: bool


class EventResultOut(BaseModel):
    event: AuditEventOut
    request: RequestOut
    recommendations: RecommendationsOut


# ------------------------------------------------------------------ records
class FreshnessFields(BaseModel):
    freshness: str
    age_hours: Optional[float] = None
    freshness_note: str
    verification_label: str
    distance_km: Optional[float] = None
    distance_note: str


class BloodBankOut(FreshnessFields):
    id: str
    name: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    blood_group: str
    component: str
    units_available: int
    availability_status: str
    last_updated: Optional[str] = None
    data_source: str
    is_simulated: bool = True


class DonorOut(FreshnessFields):
    id: str
    display_name: str
    blood_group: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    consent_status: str
    availability_status: str
    response_status: str
    last_updated: Optional[str] = None
    data_source: str
    is_simulated: bool = True


class LocationOut(BaseModel):
    location_id: str
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class HealthOut(BaseModel):
    status: str
    service: str
    database: str
    demo_data: bool
    time: datetime


class DashboardOut(BaseModel):
    requests_total: int
    requests_active: int
    requests_urgent_active: int
    by_status: Dict[str, int]
    blood_banks: Dict[str, int]
    donors: Dict[str, int]
    recent_activity: List[AuditEventOut]
    recent_requests: List[RequestOut]
    is_demo_data: bool = True


class MetaOut(BaseModel):
    blood_groups: List[str]
    components: List[str]
    genders: List[str]
    urgencies: List[str]
    request_statuses: List[str]
    candidate_statuses: List[str]
    request_transitions: Dict[str, List[str]]
    candidate_transitions: Dict[str, List[str]]
    event_types: Dict[str, str]
    freshness_recent_hours: float
    freshness_legend: Dict[str, str]
    match_rules: Dict[str, str]
    disclaimer: str
