"""Convert Boehringer Ingelheim pipeline PDF to the unified parquet schema.

Field-mapping decisions are recorded in src/pharmas/boehringer_ingelheim/log.md.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
SOURCE_URL = "https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline"

PHASE_MAP = {
    "Preregistration": Phase.PREREGISTRATION,
    "Phase 3": Phase.PHASE_3,
    "Phase 2": Phase.PHASE_2,
    "Phase 1": Phase.PHASE_1,
}

RAW_RECORDS = [
    # ── Registration (Preregistration) ──
    {"phase": "Preregistration", "ta": "Oncology", "indication": "Non-small cell lung cancer", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Preregistration", "ta": "Respiratory", "indication": "Idiopathic pulmonary fibrosis", "moa": "PDE4B inhibitor", "asset": "BI 1015550", "synonyms": ["Nerandomilast"]},
    {"phase": "Preregistration", "ta": "Respiratory", "indication": "Progressive pulmonary fibrosis", "moa": "PDE4B inhibitor", "asset": "BI 1015550", "synonyms": ["Nerandomilast"]},

    # ── Phase 3 ──
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Focal segmental glomerulosclerosis", "moa": "TRPC6 inhibitor", "asset": "BI 764198", "synonyms": ["Apecotrep"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Metabolic dysfunction-associated steatohepatitis", "moa": "GCGR/GLP1 agonist", "asset": "BI 456906", "synonyms": ["Survodutide"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Obesity", "moa": "GCGR/GLP1 agonist", "asset": "BI 456906", "synonyms": ["Survodutide"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Acute ischemic stroke >4.5 h", "moa": "Fibrinolytic", "asset": "Tenecteplase", "synonyms": None},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Cardiovascular risk reduction", "moa": "Aldosterone synthase inhibitor / SGLT2 inhibitor", "asset": "BI 690517 / Empagliflozin", "synonyms": ["Vicadrostat"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Chronic kidney disease", "moa": "Aldosterone synthase inhibitor / SGLT2 inhibitor", "asset": "BI 690517 / Empagliflozin", "synonyms": ["Vicadrostat"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Heart failure with preserved ejection fraction", "moa": "Aldosterone synthase inhibitor / SGLT2 inhibitor", "asset": "BI 690517 / Empagliflozin", "synonyms": ["Vicadrostat"]},
    {"phase": "Phase 3", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Heart failure with reduced ejection fraction", "moa": "Aldosterone synthase inhibitor / SGLT2 inhibitor", "asset": "BI 690517 / Empagliflozin", "synonyms": ["Vicadrostat"]},
    {"phase": "Phase 3", "ta": "Oncology", "indication": "Small cell lung cancer", "moa": "DLL3/CD3 T-cell engager", "asset": "BI 764532", "synonyms": ["Obrixtamig"]},
    {"phase": "Phase 3", "ta": "Oncology", "indication": "Adjuvant non-small cell lung cancer", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Phase 3", "ta": "Respiratory", "indication": "Bronchiectasis", "moa": "DPP1/CatC inhibitor", "asset": "BI 1291583", "synonyms": ["Verducatib"]},

    # ── Phase 2 ──
    {"phase": "Phase 2", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Proteinuric kidney diseases", "moa": "TRPC6 inhibitor", "asset": "BI 764198", "synonyms": ["Apecotrep"]},
    {"phase": "Phase 2", "ta": "Eye Health", "indication": "Diabetic retinopathy", "moa": "Sema3A antibody", "asset": "BI 764524", "synonyms": None},
    {"phase": "Phase 2", "ta": "Eye Health", "indication": "Geographic atrophy", "moa": "Antibody fragment", "asset": "BI 771716", "synonyms": None},
    {"phase": "Phase 2", "ta": "Eye Health", "indication": "Geographic atrophy", "moa": "Phospholipid modulator", "asset": "BI 1584862", "synonyms": None},
    {"phase": "Phase 2", "ta": "Eye Health", "indication": "Diabetic macular edema", "moa": "Oral vascular modulator", "asset": "BI 1815368", "synonyms": None},
    {"phase": "Phase 2", "ta": "Immunology", "indication": "Systemic sclerosis", "moa": "PDE4B inhibitor", "asset": "BI 1015550", "synonyms": ["Nerandomilast"]},
    {"phase": "Phase 2", "ta": "Immunology", "indication": "Inflammatory bowel disease", "moa": "TREM-1 antagonist", "asset": "BI 3032950", "synonyms": None},
    {"phase": "Phase 2", "ta": "Immunology", "indication": "Systemic lupus erythematosus", "moa": "Immunomodulator", "asset": "BI 3000202", "synonyms": None},
    {"phase": "Phase 2", "ta": "Oncology", "indication": "Extra-pulmonary neuroendocrine carcinoma", "moa": "DLL3/CD3 T-cell engager", "asset": "BI 764532", "synonyms": ["Obrixtamig"]},
    {"phase": "Phase 2", "ta": "Oncology", "indication": "Advanced cancers with HER2 alterations", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Phase 2", "ta": "Oncology", "indication": "Breast cancer", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Phase 2", "ta": "Oncology", "indication": "Gastric cancer", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Phase 2", "ta": "Respiratory", "indication": "Idiopathic pulmonary fibrosis", "moa": "IL-11 antibody", "asset": "BI 765423", "synonyms": None},
    {"phase": "Phase 2", "ta": "Respiratory", "indication": "Idiopathic / progressive pulmonary fibrosis", "moa": "Lysophospholipase inhibitor", "asset": "BI 1819479", "synonyms": None},

    # ── Phase 1 ──
    {"phase": "Phase 1", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Undisclosed", "moa": "Anti-fibrotic agent", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Undisclosed", "moa": "Anti-fibrotic agent", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Undisclosed", "moa": "Glutamate receptor modulator", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Undisclosed", "moa": "Immunomodulator", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Cardiovascular-Renal-Metabolic", "indication": "Undisclosed", "moa": "Triple agonist peptide", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Immunology", "indication": "Undisclosed", "moa": "Anti-inflammatory agent", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Immunology", "indication": "Undisclosed", "moa": "Immunomodulator", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Immunology", "indication": "Undisclosed", "moa": "PD-1 antibody", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Mental Health", "indication": "Undisclosed", "moa": "Acyltransferase inhibitor", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Mental Health", "indication": "Undisclosed", "moa": "Glutamate receptor modulator", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Mental Health", "indication": "Undisclosed", "moa": "Receptor agonist", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "PD-1 antibody", "asset": "Ezabenlimab", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "DLL3/CD3 T-cell engager", "asset": "BI 764532", "synonyms": ["Obrixtamig"]},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "HER2 TKI", "asset": "BI 1810631", "synonyms": ["Zongertinib"]},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "B7-H6/CD3 T-cell engager", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "CD137/FAP agonist", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "Immunological fusion protein", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "Modified yersinia", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "SIRP\u03b1 antagonist", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "STING agonist (2nd generation)", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "Targeted cancer immunotherapy", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "T-cell engager", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Oncology", "indication": "Undisclosed", "moa": "VSV-GP", "asset": "Undisclosed", "synonyms": None},
    {"phase": "Phase 1", "ta": "Respiratory", "indication": "Undisclosed", "moa": "Anti-fibrotic agent", "asset": "Undisclosed", "synonyms": None},
]


def convert(extraction_date: date) -> list[PipelineRecord]:
    records = []
    for r in RAW_RECORDS:
        phase = PHASE_MAP[r["phase"]]
        records.append(
            PipelineRecord(
                company="Boehringer Ingelheim",
                asset_name=r["asset"],
                synonyms=r["synonyms"],
                mechanism_of_action=r["moa"],
                therapeutic_area=r["ta"],
                indication=r["indication"],
                phase=phase,
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=None,
                modality=None,
            )
        )
    return records


def main() -> None:
    extraction_date = date(2026, 7, 9)
    records = convert(extraction_date)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    out_path = HERE / "boehringer_ingelheim_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()
