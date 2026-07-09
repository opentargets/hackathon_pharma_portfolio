"""Map Boehringer Ingelheim's pipeline PDF onto the shared PipelineRecord schema.

Source (confirmed with user, see log.md and GitHub issue #15): the live
webpage (`WEBPAGE_SOURCE_URL`) is hard-blocked by an Incapsula WAF for every
tool-driven fetch path tried (curl, WebFetch, scrapling, chrome-devtools-mcp
-- all share the sandbox's fixed egress IP, see log.md). The user downloaded
BI's own PDF directly (`2026_May_Clinical_Pipeline.pdf`, "as of May 2026" --
newer than the Oct-2025 Wayback snapshot gathered as an earlier fallback,
which is kept in `wayback_parsed.json`/`wayback_pipeline_20260218.html` for
reference but is NOT used here since the PDF is more current and reachable).

The PDF is a 3-column-per-page grid of cards (Registration / Phase 3 /
Phase 2 / Phase 1). Each card is four font-tagged text runs in a fixed
order -- therapeutic area (bold heading font), indication (medium font,
absent for every Phase 1 card in this PDF), mechanism of action (regular
font), and asset name (italic font, absent for undisclosed early compounds).
Column assignment is done by x-gap clustering per text line (a word's own
x0 can drift past the next column's nominal start when a line wraps wide,
so nearest-anchor assignment misfires; gap-clustering first, then anchoring
by each cluster's own left edge, does not).
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

from schema import Phase, PipelineRecord

HERE = Path(__file__).parent
PDF_PATH = HERE / "2026_May_Clinical_Pipeline.pdf"
WEBPAGE_SOURCE_URL = (
    "https://www.boehringer-ingelheim.com/science-innovation/"
    "human-health-innovation/clinical-pipeline"
)
PDF_SOURCE_URL = (
    "https://www.boehringer-ingelheim.com/science-innovation/"
    "human-health-innovation/clinical-pipeline/pdf/human-pharma-clinical-pipeline"
)
EXTRACTION_DATE = date(2026, 7, 9)

COL_ANCHORS = [154, 293, 432]

FONT_ROLE = {
    "BoehringerForwardHead-Md": "ta",
    "BoehringerForwardText-Md": "indication",
    "BoehringerForwardText-It": "asset",
    "BoehringerForwardText": "moa",
}

PHASE_MAP = {
    "Registration": Phase.PREREGISTRATION,  # confirmed with user, matches
    # Novo Nordisk's "filed" precedent
    "Phase 3": Phase.PHASE_3,
    "Phase 2": Phase.PHASE_2,
    "Phase 1": Phase.PHASE_1,
}

# BI names each asset "INN (BI code)" (e.g. "Zongertinib (BI 1810631)") or,
# for combos, "INN (BI code)/OtherInn" -- the code is split out into
# `synonyms` and the INN kept as `asset_name` (confirmed with user, matches
# the Merck KGaA precedent of INN-primary naming). Bare "BI ######" with no
# INN (undisclosed-name compounds still in early testing) has no parens to
# split, so it's kept as-is.
PAREN_CODE_RE = re.compile(r"\(\s*(BI\s*\d+)\s*\)")


def split_asset(asset_text):
    codes = PAREN_CODE_RE.findall(asset_text)
    name = PAREN_CODE_RE.sub("", asset_text)
    name = re.sub(r"\s*/\s*", "/", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name, (codes or None)


def role_of(fontname):
    return FONT_ROLE.get(fontname.split("+")[-1])


def nearest_col(x0):
    return min(range(len(COL_ANCHORS)), key=lambda i: abs(COL_ANCHORS[i] - x0))


def line_clusters(words):
    """Split one physical line's words (sorted by x0) into column clusters
    by horizontal gap -- a wrapped line's overflow words stay close to their
    own column's preceding word, while a genuine new column starts with a
    big jump."""
    clusters, cur, prev_x1 = [], [], None
    for w in words:
        if prev_x1 is not None and w["x0"] - prev_x1 > 15:
            clusters.append(cur)
            cur = []
        cur.append(w)
        prev_x1 = w["x1"]
    if cur:
        clusters.append(cur)
    return clusters


def parse_page(page, phase_ranges):
    words = page.extract_words(extra_attrs=["fontname"])
    words = [w for w in words if 95 < w["top"] < 700 and w["x0"] >= 100]
    by_line = {}
    for w in words:
        by_line.setdefault(round(w["top"]), []).append(w)

    per_col_slots = {0: [], 1: [], 2: []}
    for top in sorted(by_line):
        line_words = sorted(by_line[top], key=lambda w: w["x0"])
        for cluster in line_clusters(line_words):
            slots = per_col_slots[nearest_col(cluster[0]["x0"])]
            for w in cluster:
                role = role_of(w["fontname"])
                if role is None:
                    continue
                if (role == "ta" and slots and slots[-1]["_stage"] != "ta") or not slots:
                    slots.append(
                        {"top": top, "ta": "", "indication": "", "moa": "", "asset": "", "_stage": None}
                    )
                slot = slots[-1]
                slot[role] = (slot[role] + " " + w["text"]).strip()
                slot["_stage"] = role

    cards = []
    for slots in per_col_slots.values():
        for s in slots:
            s.pop("_stage", None)
            for lo, hi, name in phase_ranges:
                if lo <= s["top"] < hi:
                    s["phase_section"] = name
                    break
            cards.append(s)
    return cards


def load_cards():
    with pdfplumber.open(PDF_PATH) as pdf:
        cards = []
        cards += parse_page(pdf.pages[1], [(0, 180, "Registration"), (180, 700, "Phase 3")])
        cards += parse_page(pdf.pages[2], [(0, 700, "Phase 2")])
        cards += parse_page(pdf.pages[3], [(0, 700, "Phase 1")])
    return cards


def build_records():
    records = []
    for c in load_cards():
        ta = c["ta"].strip()
        indication = c["indication"].strip()
        moa = c["moa"].strip() or None
        asset = c["asset"].strip()

        # Undisclosed compounds (no code name in source) and every Phase 1
        # card (indication is never given at that phase in this PDF) fall
        # back per the user-confirmed mapping: asset_name -> MoA label when
        # no name is disclosed; indication -> therapeutic_area when absent.
        if asset:
            asset_name, synonyms = split_asset(asset)
        else:
            asset_name, synonyms = moa, None
        indication = indication or ta

        records.append(
            PipelineRecord(
                company="Boehringer Ingelheim",
                asset_name=asset_name,
                synonyms=synonyms,
                mechanism_of_action=moa,
                therapeutic_area=ta,
                indication=indication,
                phase=PHASE_MAP[c["phase_section"]],
                trial_id=None,
                source_url=PDF_SOURCE_URL,
                extraction_date=EXTRACTION_DATE,
                modality=None,
                notes=None,
            )
        )
    return records


def main():
    records = build_records()
    df = pd.DataFrame([r.model_dump() for r in records])
    df["phase"] = df["phase"].apply(lambda p: p.value if isinstance(p, Phase) else p)
    out_path = HERE / "boehringer_ingelheim_pipeline.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} records to {out_path}")


if __name__ == "__main__":
    main()
