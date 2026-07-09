"""Convert the Takeda pipeline PDF to the unified parquet schema.

Source: https://www.takeda.com/science/pipeline/ → DOWNLOAD THE PDF
PDF is the Q4 FY2025 (ending March 31, 2026) pipeline table.
Uses position-aware word extraction (pdfplumber extract_words) since the
table spans multiple fragmented rows per asset.
"""

import argparse
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
PDF_PATH = HERE / "qr2025_q4_Pipeline_table_en.pdf"
SOURCE_URL = "https://www.takeda.com/science/pipeline/"

DEV_CODE_RE = re.compile(r"^(TAK|SGN|HQP|ACI|IBI)[-\s]*(\d+(?:[.]\d+)?)")

# Column boundaries from x0 analysis:
# c0: 40-90    dev code / generic name / brand name
# c1: 120-160  type of drug (administration route)
# c2: 210-250  modality
# c3: 260-360  indications
# c4: 420-510  country/region + stage (region ~420-470, stage ~480-510)
COL_BOUNDS = [
    (0, 100),
    (100, 180),
    (180, 260),
    (260, 400),
    (400, 9999),
]

PAGE_TA_MAP = {
    3: "GI & Inflammation",
    4: "Neuroscience",
    5: "Oncology",
    6: "Other Rare Diseases",
    7: "Plasma-Derived Therapies",
}

FOOTNOTES: dict[str, str] = {}


def _clean(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip()


def _load_footnotes() -> None:
    global FOOTNOTES
    pdf = pdfplumber.open(PDF_PATH)
    fn_parts = []
    for pi in [3, 4, 5, 6, 7]:
        text = pdf.pages[pi].extract_text()
        for line in text.split("\n"):
            if re.match(r"^\*\d", line.strip()):
                fn_parts.append(line.strip())
    pdf.close()
    combined = " ".join(fn_parts)
    for m in re.finditer(r"(\*\d+)\s+(.*?)(?=\s*\*\d|\Z)", combined):
        FOOTNOTES[m.group(1)] = m.group(2).strip().rstrip(".") + "."


def _is_dev_code(text: str) -> bool:
    return bool(text and DEV_CODE_RE.match(text.strip()))


def _extract_dev_code(text: str) -> str:
    m = DEV_CODE_RE.match(text.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def _find_stage(text: str) -> str | None:
    for kw in ["Approved", "Filed", "P-III", "P-II", "P-I"]:
        if kw in text:
            return kw
    return None


def _map_phase(label: str | None) -> Phase | None:
    if not label:
        return None
    if label.startswith("P-III"):
        return Phase.PHASE_3
    if label.startswith("P-II"):
        return Phase.PHASE_2
    if label.startswith("P-I"):
        return Phase.PHASE_1
    if label == "Filed":
        return Phase.PREREGISTRATION
    if label == "Approved":
        return Phase.REGISTERED
    return None


def _assign_col(w: dict) -> int | None:
    x = (w["x0"] + w["x1"]) / 2
    for ci, (lo, hi) in enumerate(COL_BOUNDS):
        if lo <= x < hi:
            return ci
    return None


def _extract_generic(text: str) -> str | None:
    m = re.search(r"<([^>]+)>", text)
    return m.group(1) if m else None


def extract_assets(page_idx: int, words: list[dict]) -> list[dict]:
    ta = PAGE_TA_MAP.get(page_idx, "Unknown")

    y_tol = 6
    rows_y: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        rows_y[round(w["top"] / y_tol) * y_tol].append(w)

    raw_rows: list[list[str]] = []
    for y in sorted(rows_y):
        wlist = sorted(rows_y[y], key=lambda w: w["x0"])
        cols = [""] * 5
        for w in wlist:
            ci = _assign_col(w)
            if ci is not None:
                cols[ci] = (cols[ci] + " " + w["text"]).strip()
        raw_rows.append(cols)

    skip_patterns = [
        "Development code", "Brand name",
        "Neuroscience Pipeline", "Oncology Pipeline",
        "Other Rare Diseases Pipeline", "Plasma-Derived Therapies Pipeline",
        "Partnership with",
    ]
    header_col_keywords = ["Modality", "Indications / additional", "Type of Drug",
                           "(administration route)", "Country/", "Region", "Stage", "(country/region)"]
    def _is_header_row(r):
        for p in skip_patterns:
            if p in r[0]:
                return True
        if r[0].startswith("*"):
            return True
        for c in r:
            for hk in header_col_keywords:
                if hk in c:
                    return True
        return False

    data_rows = [r for r in raw_rows if not _is_header_row(r)]

    # Group into blocks by dev code
    blocks: list[list[list[str]]] = []
    pre_code_rows: list[list[str]] = []
    for r in data_rows:
        if _is_dev_code(r[0]):
            # Attach buffered pre-code rows to this block
            if pre_code_rows:
                pre_code_rows.append(r)
                blocks.append(pre_code_rows)
                pre_code_rows = []
            else:
                blocks.append([r])
        elif blocks:
            blocks[-1].append(r)
        else:
            pre_code_rows.append(r)

    assets = []

    for block in blocks:
        # Accumulate metadata (generic, brands, drug type, modality) from the block
        gen = None
        brands: list[str] = []
        c1_parts: list[str] = []
        c2_parts: list[str] = []
        dc = ""
        full_c0 = ""

        for r in block:
            c0 = _clean(r[0])
            c1 = _clean(r[1])
            c2 = _clean(r[2])
            c3 = _clean(r[3])
            c4 = _clean(r[4])

            if _is_dev_code(c0):
                dc = _extract_dev_code(c0)
                full_c0 = c0
                gn = _extract_generic(c0)
                if gn:
                    gen = gn
                if c1:
                    c1_parts.append(c1)
                if c2:
                    c2_parts.append(c2)
            else:
                gn = _extract_generic(c0)
                if gn and not gen:
                    gen = gn
                if c0 and not gn:
                    cb = c0.strip().strip("()").strip()
                    if cb and not any(cb.startswith(x) for x in
                                       ["U.S.", "EU", "Japan", "China", "Global"]):
                        if cb not in brands:
                            brands.append(cb)
                if c1:
                    c1_parts.append(c1)
                if c2:
                    c2_parts.append(c2)

        mechanism = _clean(" ".join(c1_parts))
        modality = _clean(" ".join(c2_parts))

        if not dc:
            continue

        # Collect all (indication, stage) pairs from the block.
        # Each stage row gets c3 from rows in its span (between previous and next stage).
        row_indications = [_clean(r[3]) for r in block]
        row_stages = [_clean(r[4]) for r in block]
        n = len(block)

        # Find stage row positions
        stage_idx = [i for i in range(n) if row_stages[i] and _find_stage(row_stages[i])]

        # For each stage row, collect c3 from its span (prev_stage to next_stage)
        # Include same-row c3 even if the row has a stage; exclude c3 from OTHER stage rows.
        span_indications: dict[int, str] = {}
        for si in stage_idx:
            lo = (stage_idx[max(0, stage_idx.index(si) - 1)] + 1
                  if stage_idx.index(si) > 0 else 0)
            hi = (stage_idx[stage_idx.index(si) + 1]
                  if stage_idx.index(si) + 1 < len(stage_idx) else n)
            parts: list[str] = []
            for j in range(lo, hi):
                rc3 = row_indications[j]
                rc4 = row_stages[j]
                if not rc3 or rc3 == "-":
                    continue
                if j != si and rc4 and _find_stage(rc4):
                    continue
                parts.append(rc3)
            span_indications[si] = _clean(" ".join(parts))

        # Fill empty spans with the nearest non-empty span
        filled = set()
        empty_span = [si for si, txt in span_indications.items() if not txt]
        non_empty = [si for si, txt in span_indications.items() if txt]
        for si in empty_span:
            best = None
            best_dist = n
            for nei in non_empty:
                d = abs(nei - si)
                if d < best_dist:
                    best_dist = d
                    best = nei
            if best is not None:
                span_indications[si] = span_indications[best]
                filled.add(si)

        # Merge adjacent spans where the next span starts with the current one's text
        sorted_si = sorted(span_indications.keys())
        for a, b in zip(sorted_si, sorted_si[1:]):
            txt_a = span_indications[a]
            txt_b = span_indications[b]
            if txt_a and txt_b and txt_b.startswith(txt_a) and len(txt_b) > len(txt_a):
                span_indications[a] = txt_b
            elif txt_a and txt_b and txt_a.startswith(txt_b) and len(txt_a) > len(txt_b):
                span_indications[b] = txt_a

        ind_stage_pairs: list[tuple[str, str, str]] = []

        for i in range(n):
            c4 = row_stages[i]
            if not (c4 and _find_stage(c4)):
                continue
            ind = span_indications.get(i, "")

            stage_pairs_c4 = _find_all_stages(c4)
            for region_text, skw, stage_full in stage_pairs_c4:
                if skw:
                    ind_stage_pairs.append((ind, region_text, stage_full))

        # Build default indication from ALL non-stage c3 text in the block
        # This merges fragmented indication text (e.g. "Pediatric on-demand and surgery
        # treatment of" + "von Willebrand disease" → full string)
        all_ind_parts: list[str] = []
        for r in block:
            c3 = _clean(r[3])
            c4 = _clean(r[4])
            if c3 and not _find_stage(c4):
                # Skip standalone "-" (not an indication, just a placeholder)
                if c3 == "-":
                    continue
                all_ind_parts.append(c3)
        default_indication = _clean(" ".join(all_ind_parts))
        # Remove placeholder dashes from the middle too
        default_indication = re.sub(r"\s*-\s*", " ", default_indication).strip()

        # Extract synonyms
        c0_all = " ".join(_clean(r[0]) for r in block if r[0])
        c0_all_clean = re.sub(r"<[^>]+>", "", c0_all).strip()
        for p in c0_all_clean.split():
            p = p.strip().strip("()").strip()
            if not p:
                continue
            if _is_dev_code(p) or _extract_generic(p):
                continue
            if any(p.startswith(x) for x in ["U.S.", "EU", "Japan", "China", "Global"]):
                continue
            if p not in brands:
                brands.append(p)

        synonyms = []
        if gen and gen.lower() != dc.lower():
            synonyms.append(gen)
        for b in brands:
            b = b.strip()
            if b and b.lower() != dc.lower() and b not in synonyms:
                synonyms.append(b)
        if not synonyms:
            synonyms = None

        fn_nums = re.findall(r"\*\d+", full_c0)
        notes_parts = [FOOTNOTES.get(fn, "") for fn in fn_nums if FOOTNOTES.get(fn)]
        notes_str = " ".join(notes_parts) if notes_parts else None

        # Clean up: empty or "-" indications → keep as "-"
        for pi, (ind_text, region_text, stage_full) in enumerate(ind_stage_pairs):
            if not ind_text or ind_text == "-":
                ind_stage_pairs[pi] = ("-", region_text, stage_full)

        for ind_text, region_text, stage_full in ind_stage_pairs:
            skw = _find_stage(stage_full)
            if not skw:
                continue
            phase = _map_phase(skw)
            if not phase:
                continue

            assets.append({
                "dev_code": dc,
                "generic_name": gen,
                "synonyms": synonyms,
                "mechanism_of_action": mechanism if mechanism else None,
                "modality": modality if modality else None,
                "therapeutic_area": ta,
                "indication": ind_text,
                "region": region_text,
                "phase": phase,
                "stage_text": stage_full.strip(),
                "notes": notes_str,
            })

    return assets


def _find_all_stages(text: str) -> list[tuple[str, str, str]]:
    """Parse text like 'Japan Filed (Mar 2026) U.S. P-III' into [(region, kw, full), ...]."""
    results = []
    remaining = text.strip()
    while remaining:
        best = None
        best_idx = len(remaining)
        for kw in ["Approved", "Filed", "P-III", "P-II", "P-I"]:
            idx = remaining.find(kw)
            if idx != -1 and idx < best_idx:
                best = kw
                best_idx = idx
        if best is None:
            break
        region = remaining[:best_idx].strip().rstrip(",").strip()
        # Find where this stage entry ends — at the next region keyword or end
        # Region keywords that start the next entry
        next_regions = ["Japan", "U.S.", "EU", "China", "Global"]
        rest = remaining[best_idx:]
        end_pos = len(rest)
        for nr in next_regions:
            nr_pos = rest.find(" " + nr)
            if nr_pos != -1 and nr_pos < end_pos:
                end_pos = nr_pos
        stage_full = rest[:end_pos].strip()
        remaining = rest[end_pos:].strip()
        results.append((region, best, stage_full))
    return results


def convert(pdf_path: Path, extraction_date: date) -> list[PipelineRecord]:
    _load_footnotes()
    pdf = pdfplumber.open(pdf_path)

    all_assets = []
    for pi in PAGE_TA_MAP:
        page = pdf.pages[pi]
        words = page.extract_words(keep_blank_chars=True, x_tolerance=3)
        all_assets.extend(extract_assets(pi, words))

    pdf.close()

    # Deduplicate: same asset + indication + phase
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []
    for a in all_assets:
        key = (a["dev_code"], a.get("indication", ""), str(a["phase"].value))
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    # Remove fragment entries: if two entries have same asset+phase and one
    # indication is a substring of the other, keep the longer one
    filtered: list[dict] = []
    for i, a in enumerate(deduped):
        is_fragment = False
        code = a["dev_code"]
        ind = a.get("indication", "")
        ph = a["phase"]
        for j, b in enumerate(deduped):
            if i == j:
                continue
            if b["dev_code"] != code or b["phase"] != ph:
                continue
            b_ind = b.get("indication", "")
            if b_ind and ind and ind != b_ind and len(ind) < len(b_ind) and ind in b_ind:
                is_fragment = True
                break
        if not is_fragment:
            filtered.append(a)

    records = []
    for a in filtered:
        records.append(
            PipelineRecord(
                company="Takeda",
                asset_name=a["dev_code"],
                synonyms=a.get("synonyms"),
                mechanism_of_action=a.get("mechanism_of_action"),
                therapeutic_area=a.get("therapeutic_area"),
                indication=a.get("indication", ""),
                phase=a["phase"],
                trial_id=None,
                source_url=SOURCE_URL,
                extraction_date=extraction_date,
                notes=a.get("notes"),
                modality=a.get("modality"),
            )
        )

    return records


def _verify(records: list[PipelineRecord]) -> None:
    print(f"Total records: {len(records)}")
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    uniq = sorted(df["asset_name"].unique())
    print(f"\nUnique assets: {len(uniq)}")
    for name in uniq:
        subset = df[df["asset_name"] == name]
        for _, r in subset.iterrows():
            ind = (r["indication"] or "")[:60]
            print(f"  {name:25s} | {ind:60s} | {r['phase']:15s} | {r['therapeutic_area'] or '':30s}")
    print(f"\nPhase:")
    print(df["phase"].value_counts().to_string())
    print(f"\nTA:")
    print(df["therapeutic_area"].value_counts().to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=PDF_PATH, type=Path)
    parser.add_argument("--out", default=HERE / "takeda_pipeline.parquet", type=Path)
    parser.add_argument("--extraction-date", default="2026-07-09", type=date.fromisoformat)
    args = parser.parse_args()

    records = convert(args.pdf, args.extraction_date)
    _verify(records)
    df = pd.DataFrame([r.model_dump(mode="json") for r in records])
    df.to_parquet(args.out, index=False)
    print(f"\nWrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
