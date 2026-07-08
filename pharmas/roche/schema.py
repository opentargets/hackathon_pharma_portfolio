"""Unified pipeline-record schema (docs/data-model.md)."""

from datetime import date
from enum import Enum

from pydantic import BaseModel


class Phase(str, Enum):
    PRECLINICAL = "Preclinical"
    PHASE_1 = "Phase 1"
    PHASE_1_2 = "Phase 1/2"
    PHASE_2 = "Phase 2"
    PHASE_2_3 = "Phase 2/3"
    PHASE_3 = "Phase 3"
    PREREGISTRATION = "Preregistration"
    REGISTERED = "Registered"
    DISCONTINUED = "Discontinued"


class PipelineRecord(BaseModel):
    company: str
    asset_name: str
    synonyms: list[str] | None = None
    mechanism_of_action: str | None = None
    therapeutic_area: str
    indication: str
    phase: Phase
    trial_id: str | None = None
    source_url: str
    extraction_date: date
    notes: str | None = None
    others: list[str] | None = None
