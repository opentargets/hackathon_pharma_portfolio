# AstraZeneca extraction log

Source: https://www.astrazeneca.com/our-therapy-areas/pipeline.html
(Tier 1: server-rendered static HTML, no JS needed. PDF also available at the
annual report URL but the webpage is more current — 29 April 2026 vs 10 Feb 2026 —
and adds fields like Molecule size, Filing status, Status change.)

## Page structure

The pipeline is a fully server-rendered HTML page. Five therapeutic area
sections (Oncology, CVRM, R&I, Rare Disease, Infectious Disease) each contain
phase-grouped (Phase I / II / III / LCM Projects) compound lists. A sixth
"Removed since last quarter" termination section lists ~13 recently-removed
projects.

Each compound block contains:
- Name (compound code, generic name, or brand name, sometimes with trial/protocol
  suffix)
- Short indication (em tag, the trigger description)
- Phase label in the popup title
- Mechanism of action
- Area under investigation (full indication)
- Molecule size (Small / Large / Combination molecule)
- Optional: Additional information, Status change, First Major Market Filing
  Status

Total: 186 active entries + 13 discontinued = 199 rows.

## Field mapping decisions (confirmed with user on 2026-07-08)

| Schema field | Source | Notes |
|---|---|---|
| `asset_name` | Compound code or generic name | Trial/protocol suffixes stripped (e.g. "SERENA-6", "DESTINY-Breast05", "eVOLVE-HNSCC", etc.) |
| `synonyms` | Known brand↔generic pairs | e.g. Imfinzi→durvalumab, Tagrisso→osimertinib, saruparib→AZD5305, etc. |
| `mechanism_of_action` | "Mechanism:" field | Direct |
| `therapeutic_area` | Section data-label | Oncology, Cardiovascular, Renal and Metabolism, Respiratory & Immunology, Rare Disease, Infectious Disease. Discontinued entries have None (unknown original TA). |
| `indication` | "Area under investigation:" field | Direct |
| `phase` | Phase heading (I/II/III) | LCM Projects → Phase 3 (approved drugs in new indications). Removed since last quarter → Discontinued |
| `modality` | "Molecule size:" field | Small molecule→Small Molecule, Large molecule→Biologic, Combination molecule→Combination |
| `notes` | Termination section entries | "Removed since last quarter" for discontinued entries |
| Extra fields | Additional information, Status change, First Major Market Filing Status | Skipped per user request |

## Data quality flags

1. **ALXN2230 has mechanism "0"** — appears to be a placeholder for undisclosed
   mechanism. Set to None in output.

2. **13 entries in "Removed since last quarter" section** — no phase label,
   therapeutic_area, or mechanism available. Included with
   `phase=Discontinued, notes="Removed since last quarter"`. These include:
   Datroway, Enhertu, Imfinzi combos, AZD1705, AZD6912, volrustomig, ALXN2420,
   atuliflapon, Breztri/Trixeo, Orpathys + Imfinzi, Ultomiris.

3. **Infectious Disease section has only 4 active entries** (Kavigale SUPERNOVA
   and a few others) — notably small compared to other sections.

4. **Some compounds appear in multiple TAs** (e.g., AZD0120 in both Oncology and
   R&I; surovatamig in Oncology and R&I) — these are legitimate cross-TA entries
   for the same drug.

5. **Source HTML pipeline_page.html** — saved from the live page at extraction
   time. If the page is updated, section positions may shift and the hardcoded
   byte positions in the converter will need to be updated (fallback dynamic
   discovery should handle most changes).

## Cross-check (2026-07-08)

User provided manual copy/paste of Phase I Oncology entries and R&I LCM Projects
from the live webpage. Results confirmed correct:

- **Phase I Oncology (9 entries)**: AZD0240 through AZD4512 — all names and
  indications match exactly.
- **R&I LCM (8 entries)**: Breztri/Trixeo, Fasenra, Saphnelo entries — all names
  and indications match exactly.
- **Bug found and fixed**: The trial suffix stripper was doing a single pass,
  so "Breztri/Trixeo (PT010) KALOS LOGOS" was only partially stripped to
  "Breztri/Trixeo (PT010) KALOS". Fixed by making the stripping iterative.
  Re-ran and verified the output is now correct.

No other inconsistencies found. Output verified.
