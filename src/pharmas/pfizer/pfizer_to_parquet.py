"""Convert Pfizer Q1 2026 pipeline PDF to the unified parquet schema.

Source: https://www.pfizer.com/science/drug-product-pipeline
PDF: quarterly pipeline update (Q1 2026, as of May 5, 2026)
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
PDF_PATH = HERE / "Q1_2026_Pipeline_Update.pdf"
SOURCE_URL = "https://www.pfizer.com/science/drug-product-pipeline"
EXTRACTION_DATE = date(2026, 7, 8)

PHASE_MAP = {
    "Phase 1": Phase.PHASE_1,
    "Phase 2": Phase.PHASE_2,
    "Phase 3": Phase.PHASE_3,
    "Registration": Phase.PREREGISTRATION,
}

PAGE_TO_AREA = {
    4: "Inflammation & Immunology",
    5: "Inflammation & Immunology",
    6: "Internal Medicine",
    7: "Internal Medicine",
    8: "Oncology",
    9: "Oncology",
    10: "Oncology",
    11: "Oncology",
    12: "Oncology",
    13: "Vaccines",
}

TRADEMARK_RE = re.compile(r"[®™]")
BIOLOGIC_RE = re.compile(r"\s*\(Biologic\)")
NEWLINE_RE = re.compile(r"\n\s*")


def clean_name(text: str) -> str:
    text = TRADEMARK_RE.sub("", text or "")
    text = NEWLINE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lstrip("►").strip()
    return text


def normalize_cell(text: str | None) -> str:
    if not text:
        return ""
    text = NEWLINE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_modality(indication: str, page_idx: int) -> tuple[str, str | None]:
    modality = None
    m = BIOLOGIC_RE.search(indication)
    if m:
        modality = "Biologic"
        indication = indication[: m.start()] + indication[m.end() :]
    elif page_idx in PAGE_TO_AREA and PAGE_TO_AREA[page_idx] == "Vaccines":
        modality = "Vaccine"
    elif page_idx in PAGE_TO_AREA and PAGE_TO_AREA[page_idx] != "Vaccines":
        modalities_found = re.findall(r"\(Small\s+Molecule\)", indication, re.IGNORECASE)
        if modalities_found:
            modality = "Small Molecule"
            for mf in modalities_found:
                indication = indication.replace(mf, "")
    if modality == "Biologic" and page_idx in PAGE_TO_AREA and PAGE_TO_AREA[page_idx] == "Vaccines":
        pass
    if not modality and page_idx in PAGE_TO_AREA:
        if PAGE_TO_AREA[page_idx] != "Vaccines":
            modality = "Small Molecule"
    return re.sub(r"\s+", " ", indication).strip(), modality


def parse_rows_from_page(page, page_idx: int) -> list[dict]:
    """Extract table rows from a PDF page."""
    rows = []
    tables = page.extract_tables()
    data_table = None
    for t in tables:
        if len(t) > 1 and len(t[0]) >= 5:
            data_table = t
            break

    if data_table is None:
        return []

    header = [normalize_cell(h) for h in data_table[0]]
    expected_header = ["Compound Name", "Mechanism of Action", "Indication", "Phase of Development", "Submission Type"]
    if any(e in h for h, e in zip(header, expected_header)):
        for row in data_table[1:]:
            if len(row) < 5:
                continue
            compound = normalize_cell(row[0])
            moa = normalize_cell(row[1])
            indication = normalize_cell(row[2])
            phase_text = normalize_cell(row[3])
            submission = normalize_cell(row[4])
            if not compound and not indication:
                continue
            if not phase_text:
                continue
            rows.append({
                "compound": compound,
                "moa": moa,
                "indication": indication,
                "phase": phase_text,
                "submission": submission,
            })
    return rows


def parse_vaccines_page(page) -> list[dict]:
    words = page.extract_words(keep_blank_chars=True, x_tolerance=3)

    def col_for_x(x):
        if x < 120:
            return "compound"
        elif 120 <= x < 365:
            return "moa"
        elif 365 <= x < 740:
            return "indication"
        elif 740 <= x < 820:
            return "phase"
        elif x >= 820:
            return "submission"
        return None

    wdata = [(w["x0"], w["top"], col_for_x(w["x0"]), w["text"]) for w in words]
    wdata = [(x0, top, col, t) for x0, top, col, t in wdata if col is not None]

    PHASES = {"Phase 1", "Phase 2", "Phase 3", "Registration"}

    wdata.sort(key=lambda x: (x[1], x[0]))

    row_groups = []
    current_group = {}
    current_top = None
    for x0, top, col, text in wdata:
        if current_top is None:
            current_top = top
        if top - current_top > 2.5:
            if current_group:
                row_groups.append((current_top, current_group))
            current_group = {}
            current_top = top
        if col not in current_group:
            current_group[col] = []
        current_group[col].append(text)
    if current_group:
        row_groups.append((current_top, current_group))

    content_groups = [(t, g) for t, g in row_groups if t >= 100 and t < 450]

    anchor_indices = []
    for idx, (top_key, g) in enumerate(content_groups):
        if "phase" in g and "submission" in g:
            pt = " ".join(g["phase"])
            st = " ".join(g["submission"])
            if pt in PHASES and st in ("New Molecular Entity", "Product Enhancement"):
                anchor_indices.append(idx)

    anchors = []
    for ai in anchor_indices:
        top_key, g = content_groups[ai]
        compound = " ".join(g.get("compound", []))
        moa = " ".join(g.get("moa", []))
        indication = " ".join(g.get("indication", []))
        anchors.append({
            "key": top_key,
            "group_idx": ai,
            "compound": compound,
            "moa": moa,
            "indication": indication,
            "phase": " ".join(g["phase"]),
            "submission": " ".join(g["submission"]),
        })

    non_anchor_groups = {}
    for gi, (top_key, g) in enumerate(content_groups):
        is_anchor = gi in anchor_indices
        if not is_anchor:
            non_anchor_groups[gi] = (top_key, g)

    enriched = []
    for i, anchor in enumerate(anchors):
        curr_idx = anchor["group_idx"]
        curr_top = anchor["key"]

        moa_parts = []
        ind_parts = []

        if anchor["moa"]:
            moa_parts.append(anchor["moa"])
        if anchor["indication"]:
            ind_parts.append(anchor["indication"])

        for ngi, (ntop, ng) in non_anchor_groups.items():
            prev_anchor_top = anchors[i - 1]["key"] if i > 0 else -999
            next_anchor_top = anchors[i + 1]["key"] if i + 1 < len(anchors) else 9999
            if abs(ntop - curr_top) <= abs(ntop - prev_anchor_top) and abs(ntop - curr_top) <= abs(ntop - next_anchor_top):
                if "moa" in ng:
                    moa_parts.append(" ".join(ng["moa"]))
                if "indication" in ng:
                    ind_parts.append(" ".join(ng["indication"]))

        compound = anchor["compound"].lstrip("►").strip()
        if compound:
            enriched.append({
                "compound": compound,
                "moa": " ".join(moa_parts).strip() or None,
                "indication": " ".join(ind_parts).strip(),
                "phase": anchor["phase"],
                "submission": anchor["submission"],
            })

    return enriched


def build_records() -> list[PipelineRecord]:
    records = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_idx in range(4, 15):
            area = PAGE_TO_AREA.get(page_idx)
            if area is None:
                continue

            page = pdf.pages[page_idx]

            if page_idx == 13:
                page_rows = parse_vaccines_page(page)
            else:
                page_rows = parse_rows_from_page(page, page_idx)

            if not page_rows:
                continue

            for row in page_rows:
                compound = clean_name(row["compound"])
                if not compound:
                    continue
                moa = clean_name(row["moa"]) or None
                indication = normalize_cell(row["indication"])
                phase_text = normalize_cell(row["phase"])
                submission = normalize_cell(row["submission"])

                modality = None
                indication, modality = extract_modality(indication, page_idx)

                indication = re.sub(r"\s+", " ", indication).strip()

                phase = PHASE_MAP.get(phase_text)
                if phase is None:
                    continue

                others = []
                if submission:
                    others.append(f"Submission Type: {submission}")
                if modality:
                    others.append(f"Modality: {modality}")

                records.append(
                    PipelineRecord(
                        company="Pfizer",
                        asset_name=compound,
                        mechanism_of_action=moa,
                        therapeutic_area=area,
                        indication=indication,
                        phase=phase,
                        modality=modality,
                        source_url=SOURCE_URL,
                        extraction_date=EXTRACTION_DATE,
                        others=others or None,
                    )
                )

    return records


def main() -> None:
    records = build_records()
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    out_path = HERE / "pfizer_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")

    print(f"Phase breakdown:")
    for phase, count in df["phase"].value_counts().sort_index().items():
        print(f"  {phase}: {count}")
    print(f"  Total: {len(df)}")


if __name__ == "__main__":
    main()
