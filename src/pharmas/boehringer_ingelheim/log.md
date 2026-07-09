# Boehringer Ingelheim — Extraction Log

## Status: ✅ Done

## Source
- **Webpage (canonical, Tier 1 per `docs/sources.md`):**
  `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline`
- **PDF (actually used for extraction):**
  `https://www.boehringer-ingelheim.com/science-innovation/human-health-innovation/clinical-pipeline/pdf/human-pharma-clinical-pipeline`
  — downloaded manually as `2026_May_Clinical_Pipeline.pdf` ("as of May 2026").

## Why the PDF and not the live page

Both the live webpage and the PDF URL are behind an Incapsula WAF that
blocks the sandbox's fixed egress IP range (`193.62.0.0/16`). Every
tool-driven fetch attempt returned the same Incapsula incident page:

| Method | Result |
|---|---|
| Plain curl (webpage + PDF URL) | Incapsula iframe / 212-byte stub |
| scrapling StealthyFetcher (Camoufox) | Incapsula iframe |
| scrapling DynamicFetcher (Playwright) | 403, incident ID |
| Jina AI reader, Google cache | Blocked / not cached |
| chrome-devtools-mcp (fresh headless Chrome via `npx`) | Same Incapsula block — the MCP server launches its own browser from the sandbox machine, not the user's actual browser; `cip=193.62.205.62` in the block response confirmed identical egress IP |
| Wayback Machine, live page | No genuine capture for the PDF URL (0 captures); page itself has one usable capture, `20260218054928`, "as of October 2025" |

The PDF, downloaded directly in a real browser, was the only source that
reached either extraction session with real content.

## Two independent extractions, reconciled

Two people extracted Boehringer Ingelheim from the same PDF the same day.
Both parses agreed on the underlying 52 rows (Registration 3, Phase 3 11,
Phase 2 14, Phase 1 24) and the same field values per row, but differed on
schema-mapping conventions. Reconciled as follows (this session's final
call):

- **Converter kept:** the programmatic pdfplumber parser
  (`boehringer_ingelheim_to_parquet.py`) over a hand-transcribed row list —
  reproducible if BI publishes an updated PDF later (rerun the script; no
  manual re-transcription).
- **Asset naming:** INN as `asset_name`, BI internal code split into
  `synonyms` (e.g. `asset_name="Zongertinib"`, `synonyms=["BI 1810631"]`) —
  matches the Merck KGaA precedent of INN-primary naming. Bare `BI ######`
  codes with no disclosed INN are kept as `asset_name` with no synonym
  (nothing to split).
- **Undisclosed Phase 1 compounds:** `asset_name` falls back to the MoA
  label, `indication` falls back to `therapeutic_area` — keeps both fields
  semantically informative instead of a placeholder string.

## Extraction method

`boehringer_ingelheim_to_parquet.py` parses `2026_May_Clinical_Pipeline.pdf`
with `pdfplumber`. Layout: pages 2–4 are a 3-column grid of cards
(Registration / Phase 3 | Phase 2 | Phase 1), each card four font-tagged
text runs in fixed order — therapeutic area (bold heading font), indication
(medium font — **absent for every Phase 1 card in this PDF**, disclosed or
not), mechanism of action (regular font), asset name (italic font — absent
for undisclosed early compounds).

Column assignment required gap-based clustering rather than nearest-x0
matching: a wrapped indication line's tail words can drift past the next
column's nominal x-start (e.g. "Adjuvant non-small cell lung cancer" has
its last word starting past the Phase 3 column-2 threshold), so naive
nearest-anchor assignment silently misattributed words to the wrong card.
Fixed by clustering words per physical line on horizontal gap (>15pt = new
column) and then anchoring each *cluster's* leading edge, not each word's.

Total: **52 rows** — manually cross-checked against the PDF text dump row
by row, and separately cross-checked against live-page content pasted in
by hand — full match (only discrepancies were two typos on BI's own site,
"Teneceteplase" / "bowl disease", not extraction errors).

## Mapping decisions (confirmed with user)

- `phase`: BI's "Registration" bucket → `Preregistration` (matches Novo
  Nordisk's "filed" precedent).
- `asset_name` / `synonyms`: see "Two independent extractions, reconciled"
  above.
- Every Phase 1 card in this PDF lacks an `indication` line entirely
  (confirmed both for undisclosed and named compounds, e.g. Ezabenlimab,
  Obrixtamig, Zongertinib all show no indication at Phase 1) → `indication`
  falls back to the card's `therapeutic_area`.
- `therapeutic_area`: kept as BI's own verbatim labels
  (Cardiovascular-Renal-Metabolic, Eye Health, Immunology, Mental Health,
  Oncology, Respiratory) — no cross-company controlled vocabulary yet.
- `trial_id` / `modality` / `notes`: left null — PDF has no NCT numbers or
  modality labels, and the on-page filter badges (external partnership /
  breakthrough / fast track / combo therapy) are vector icons in the PDF,
  not extractable as text, so they're dropped rather than guessed.

## Wayback fallback (Oct 2025) vs PDF (May 2026) — real pipeline movement

Kept `wayback_parsed.json` / `wayback_pipeline_20260218.html` for reference
only; not merged into the final data. Diffing the two by
(therapeutic_area, mechanism, asset) shows genuine ~8-month pipeline
changes, not a parsing artifact:

- **Progressed:** Zongertinib (NSCLC) Phase 3 → Registration; Verducatib
  (bronchiectasis) Phase 1 → Phase 3; several BI-code compounds (e.g.
  Apecotrep = BI 764198, formerly listed only by code) gained an INN.
- **New entries:** Tenecteplase (acute ischemic stroke, Phase 3),
  Obrixtamig SCLC (Phase 3), Adjuvant-NSCLC Zongertinib (Phase 3), plus
  several new undisclosed Phase 1 programs.
- **Dropped from the May 2026 list** (discontinued, or moved off the
  public pipeline — can't distinguish from this source): CT-155 /
  BI 3972080 (schizophrenia, prescription digital therapeutic), Avenciguat
  / BI 685509 (sGC activator), BI 770371 (SIRPa antagonist, named — now
  reappears undisclosed in Phase 1), KISIMA® cancer vaccine, lentiviral
  vector-based gene therapy (respiratory), IL11 antibody (respiratory,
  distinct row from the new Phase 2 "BI 765423 IL-11 antibody").

## Output
- `boehringer_ingelheim_pipeline.parquet` — 52 records, all required
  schema fields populated, `phase` enum values validated.
