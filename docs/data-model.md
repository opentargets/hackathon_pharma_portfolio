# Data Model — Normalised Pipeline Schema

Every extracted pipeline entry is mapped to the following unified schema, regardless of the source format (PDF, JSON, HTML, narrative).

> ⚠️ We use Pydantic for data model definitions

## Fields

This is the **base model**; the full data model may include additional metadata fields from each source.

| Field | Type | Required | Description |
|---|---|---|---|
| `company` | `str` | Yes | Parent company name (e.g. `"Pfizer"`, `"Novartis"`) |
| `asset_name` | `str` | Yes | Compound or candidate name (INN, code name, or brand name) |
| `mechanism_of_action` | `str` | No | Molecular target or MoA (e.g. `"PD-1 inhibitor"`, `"EGFR TKI"`). Omitted if not disclosed. |
| `therapeutic_area` | `str` | Yes | Broad disease area (e.g. `"Oncology"`, `"Cardiovascular"`, `"Immunology"`). Mapped to a controlled vocabulary. |
| `indication` | `str` | Yes | Specific disease or condition (e.g. `"Metastatic non-small cell lung cancer"`) |
| `phase` | `str` | Yes | Normalised development phase from the controlled enum below |
| `trial_id` | `str` | No | ClinicalTrials.gov identifier (NCT number) when available from the source |
| `source_url` | `str` | Yes | Direct URL to the pipeline page or PDF from which this record was extracted |
| `extraction_date` | `date` | Yes | ISO 8601 date (YYYY-MM-DD) when the source was fetched and parsed |
| `notes` | `str` | No | Free-text annotation — e.g. "Discontinued 2026-Q1", "Partnered with X", "Combination therapy" |

## Phase Enum

Values are normalised to a controlled set to handle inconsistencies across companies:

| Normalised Value | Aliases (source-specific) |
|---|---|
| `Preclinical` | Discovery, Research, Pre-IND |
| `Phase 1` | Phase I, First-in-human, POC |
| `Phase 1/2` | Phase I/II, Phase 1b/2 |
| `Phase 2` | Phase II, Proof of Concept |
| `Phase 2/3` | Phase II/III |
| `Phase 3` | Phase III, Pivotal |
| `Preregistration` | NDA filed, BLA filed, Submitted, Under Review |
| `Registered` | Approved, Marketed, Launched |
| `Discontinued` | Terminated, No longer active, Suspended |

Ideally, you want to use our already harmonised set of phase terms: https://github.com/opentargets/clinical_mining/blob/main/src/clinical_mining/schemas.py#L53


## Edge Cases & Conventions

- **Combination therapies**: record as a single entry with both asset names in `asset_name` (e.g. `"Drug A + Drug B"`) and note in `notes`.
- **Multiple indications per asset**: one row per (company, asset, indication) tuple.
- **Missing MoA**: leave `null` rather than inferring.
- **NCT IDs**: only populate when the source explicitly provides them. Do not backfill from ClinicalTrials.gov lookups (deferred to a downstream enrichment step).
- **Extraction date**: use the date the raw source file was fetched, not the pipeline publication date.
