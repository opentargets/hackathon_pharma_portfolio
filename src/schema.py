"""Pipeline record schema.

Field-level documentation is maintained in docs/data-model.md.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    model_config = {"extra": "allow"}

    company: str = Field(
        description="Parent company name (e.g. 'Pfizer', 'Novartis')",
    )
    asset_name: str = Field(
        description="Compound or candidate name (INN, code name, or brand name)",
    )
    synonyms: Optional[list[str]] = Field(
        default=None,
        description="Alternative names for the asset (INN, brand name, code names, etc.)",
    )
    mechanism_of_action: Optional[str] = Field(
        default=None,
        description="Molecular target or MoA (e.g. 'PD-1 inhibitor', 'EGFR TKI'). Omitted if not disclosed.",
    )
    therapeutic_area: Optional[str] = Field(
        default=None,
        description="Broad disease area (e.g. 'Oncology', 'Cardiovascular', 'Immunology'). Mapped to a controlled vocabulary.",
    )
    indication: str = Field(
        description="Specific disease or condition (e.g. 'Metastatic non-small cell lung cancer')",
    )
    phase: Phase = Field(
        description="Normalised development phase from the Phase enum",
    )
    trial_id: Optional[str] = Field(
        default=None,
        description="ClinicalTrials.gov identifier (NCT number) when available from the source",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Direct URL to the pipeline page or PDF from which this record was extracted",
    )
    extraction_date: Optional[date] = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD) when the source was fetched and parsed",
    )
    modality: Optional[str] = Field(
        default=None,
        description="Compound or vaccine modality (e.g. 'Biologic', 'Small Molecule', 'Vaccine')",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-text annotation — e.g. 'Discontinued 2026-Q1', 'Partnered with X', 'Combination therapy'",
    )
