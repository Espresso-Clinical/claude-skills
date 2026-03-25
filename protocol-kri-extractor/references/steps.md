# Steps Reference — Protocol KRI Extractor

Detailed instructions and prompt templates for each pipeline step.
Claude uses these directly when running the pipeline.

---

## Shared constants

```python
DOMAIN_CATEGORIES = {
    "SOA":  "Schedule of Activities — visit schedule, procedure matrix, footnotes, visit windows",
    "ELIG": "Eligibility — inclusion criteria, exclusion criteria, randomization criteria",
    "SAF":  "Safety & Toxicity — AE/SAE reporting, stopping rules, toxicity management, safety monitoring",
    "END":  "Endpoints & Statistics — objectives, efficacy endpoints, analysis sets, statistical methods",
    "OPS":  "Operations & Compliance — IMP handling, blinding, records retention, regulatory, GCP compliance",
}

SYSTEM_PROMPT = """You are a clinical trial protocol expert and CRA (Clinical Research Associate).
You extract information from protocol documents with precision and faithfulness.
You always return valid JSON with no markdown fences, no prose, no extra text."""
```

---

## Step 1A — Protocol Manifest

**Purpose**: Read cover + TOC pages, produce `manifest.json`.

**PDF pages to read**: Cover pages (1–3) + TOC pages (search first 40 pages for a page with 5+ numbered section lines containing dots or page numbers).

**LLM prompt**:
```
Read the following pages from a clinical trial protocol and extract the manifest.

[PROTOCOL PAGES]
{pages_text}
[END]

Return a JSON object:
{
  "protocol_id": "exact protocol number from cover",
  "study_name": "short study name/acronym or null",
  "sponsor": "sponsor name",
  "compound": "investigational product name",
  "indication": "therapeutic indication in 5 words or fewer",
  "phase": "e.g. IIb, III",
  "therapeutic_area": "cardiovascular|oncology|immunology|neurology|musculoskeletal|other",
  "total_pages": N,
  "section_map": {
    "SOA":  [{"section_number": "3", "title": "Schedule of Activities", "pages_approx": [22, 26]}],
    "ELIG": [...],
    "SAF":  [...],
    "END":  [...],
    "OPS":  [...]
  }
}

Domain categories:
- SOA:  Schedule of Activities — visit schedule, procedure matrix, footnotes, visit windows
- ELIG: Eligibility — inclusion criteria, exclusion criteria, randomization criteria
- SAF:  Safety & Toxicity — AE/SAE reporting, stopping rules, toxicity management
- END:  Endpoints & Statistics — objectives, endpoints, analysis sets, statistical methods
- OPS:  Operations & Compliance — IMP handling, blinding, records, regulatory

Rules:
- Each section goes in at most one category (its PRIMARY domain)
- pages_approx: use [null, null] if page numbers not visible in TOC
- Return ONLY the JSON object
```

**Save output**: `{out_dir}/manifest.json`

---

## Step 1B-Camelot — Table Extraction (PRIMARY)

**Purpose**: Use Camelot (lattice mode) to extract the SoA table deterministically from the PDF. This is the **PRIMARY** source of truth for the SoA procedure × visit grid. Camelot reads the table's line geometry from the PDF and produces ~99% structural accuracy — deterministic, reproducible, and not affected by LLM variance.

**Dependencies**: `camelot-py[cv]`, `opencv-python-headless` (`pip install camelot-py[cv] opencv-python-headless --break-system-packages -q`)

**Implementation**:

```python
import sys
sys.path.insert(0, "/path/to/scripts")
from camelot_table_extractor import run_extraction

# Auto-detect SoA pages and extract
result = run_extraction(
    pdf_path="protocol.pdf",
    out_dir="{out_dir}/",
    pages=None  # Auto-detect, or specify e.g. "24" or "22,23,24"
)

# Result contains:
#   result["csv_path"]  -> {out_dir}/soa_table.csv
#   result["json_path"] -> {out_dir}/soa_table.json
#   result["parsed"]    -> structured dict with visits, procedures, matrix
```

**What Camelot produces**:
- `soa_table.csv` — the SoA matrix in CSV format (procedures as rows, visits as columns, X marks)
- `soa_table.json` — structured JSON with both visit-centric and procedure-centric views

**Multi-page table handling**: Many protocols split the SoA across 2-3 pages. The `merge_multipage_tables()` function automatically detects matching column structures and merges procedure rows.

**Known limitation**: Camelot may miss cells where the content is "X" plus footnote superscripts (e.g., "X¹⁰", "X¹³·¹⁴"). These appear as empty cells in Camelot's output. Use Vision fallback (Step 1B-Vision) to recover these.

**Save outputs**:
- `{out_dir}/soa_table.csv` — canonical CSV (use this for all downstream steps)
- `{out_dir}/soa_table.json` — structured JSON with visit-procedure mapping

---

## Step 1B-Vision — Vision-Based Table Extraction (FALLBACK)

**Purpose**: FALLBACK for cells where Camelot detects the table structure but misses cell content (especially footnote superscripts). Also used for protocols where Camelot's lattice mode fails (no clear table lines). Convert protocol PDF pages to high-resolution images and use Claude's multimodal vision to extract structured table data.

**Why this step exists**: pdfplumber extracts PDF text character-by-character without spatial context. When a SoA table row reads `X13 X14 X X X`, the LLM cannot tell which column each X belongs to. Vision-based extraction sees the table as a human does — with clear column boundaries — and correctly maps marks to their columns.

**Dependencies**: `pymupdf` (`pip install pymupdf --break-system-packages -q`)

**Implementation**:

```python
import fitz  # pymupdf
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from vision_table_extractor import extract_page_as_image, extract_soa_multipass

pdf_path = "protocol.pdf"
img_dir = "{out_dir}/page_images"
os.makedirs(img_dir, exist_ok=True)

doc = fitz.open(pdf_path)

# Normal pages: 300 DPI
zoom_normal = 300 / 72
mat_normal = fitz.Matrix(zoom_normal, zoom_normal)

for i in range(len(doc)):
    page = doc[i]
    pix = page.get_pixmap(matrix=mat_normal)
    pix.save(f"{img_dir}/page_{i+1:03d}.png")
doc.close()

# SoA/table pages: 450 DPI with multi-pass (full + left half + right half)
soa_pages = [p for section in manifest["section_map"]["SOA"] for p in range(section["pages_approx"][0], section["pages_approx"][1] + 1)]
multipass_images = extract_soa_multipass(pdf_path, soa_pages, "{out_dir}", dpi=450)
# This generates page_NNN.png (450 DPI full), page_NNN_left.png, page_NNN_right.png for each SoA page
```

**DPI Configuration**:
- **Normal pages**: 300 DPI (sufficient for text-heavy sections)
- **SoA/table pages**: 450 DPI (higher resolution captures small X marks in narrow columns)
- The 450 DPI upgrade specifically targets wide tables where narrow columns cause vision to miss marks

**Which pages to process with vision**: All pages identified as containing tables by pdfplumber's `find_tables()`, PLUS all pages in `manifest.section_map.SOA` range (including footnote pages).

**Multi-Pass Vision Extraction (CRITICAL for wide tables)**:

For SoA table pages, perform THREE vision passes per page:
1. **Full page** at 450 DPI — reads the complete table for overall structure
2. **Left half** (55% crop from left) at 450 DPI — higher effective resolution for left columns
3. **Right half** (55% crop from right) at 450 DPI — higher effective resolution for right columns

The 10% center overlap (55% + 55% = 110%) ensures columns near the middle appear in BOTH half-crops, enabling cross-validation.

For each pass, read the image using the Read tool and extract the procedure × visit grid independently. Then merge the three results using `merge_multipass_results()` from `vision_table_extractor.py`.

**Merge Strategy — Majority Voting with Region-Based Tie-Breaking**:
1. For each procedure × visit cell, collect votes from all 3 passes
2. If 2+ passes agree cell has X → mark as X (use the most detailed value with footnotes)
3. If 2+ passes agree cell is empty → mark as empty
4. If tie (1 yes, 2 no):
   - Left region columns (first 45%) → trust left-half pass
   - Right region columns (last 45%) → trust right-half pass
   - Center overlap columns (middle 10%) → trust full-page pass
5. All conflicts are logged in `{out_dir}/multipass_conflicts.json` for audit

**Save outputs**:
- `{out_dir}/multipass_conflicts.json` — all tie-break decisions with evidence
- `{out_dir}/vision_SOA_table_full.json` — full-page extraction result
- `{out_dir}/vision_SOA_table_left.json` — left-half extraction result
- `{out_dir}/vision_SOA_table_right.json` — right-half extraction result
- `{out_dir}/vision_SOA_table.json` — MERGED result (this is the PRIMARY source)

**Single-Pass Vision Extraction**:

For each pass (full, left, right), read the page image using the Read tool and visually identify:
1. Column headers (visit names: S-I, S-II, V1, V2, V3, V4, V5, V6, UNS)
2. Row labels (procedure names)
3. Cell contents (X marks, footnote superscripts, empty cells)

Build a structured mapping:
```json
{
  "source": "vision-based extraction from page images",
  "columns": ["S-I", "S-II", "V1", "V2", "V3", "V4", "V5", "V6", "UNS"],
  "procedures": {
    "Safety laboratory assessment": {
      "S-I": "X13", "V3": "X14", "V4": "X", "V5": "X", "V6": "X"
    },
    "Vital signs": {
      "S-I": "X9", "V1": "X10", "V2": "X10", "V3": "X10", "V4": "X", "V5": "X", "V6": "X", "UNS": "X"
    }
  }
}
```

**Vision extraction — Other tables**: Also extract any other structured tables found in the protocol:
- Eligibility criteria tables (Section 8)
- Lab panel tables (Section 13)
- AE severity/causality tables (Section 14)
- Concomitant therapy tables (Section 11)
- Statistical tables (Section 15)

**Save outputs**:
- `{out_dir}/page_images/` — all page PNG files (300 DPI normal, 450 DPI for SoA + left/right crops)
- `{out_dir}/vision_SOA_table.json` — MERGED multi-pass SoA grid (PRIMARY source)
- `{out_dir}/vision_SOA_table_full.json` — full-page extraction result
- `{out_dir}/vision_SOA_table_left.json` — left-half extraction result
- `{out_dir}/vision_SOA_table_right.json` — right-half extraction result
- `{out_dir}/multipass_conflicts.json` — all merge conflicts and resolution decisions
- `{out_dir}/vision_footnotes.json` — all SoA footnotes from vision
- `{out_dir}/vision_corrections.json` — any corrections vs pdfplumber text

**Fallback**: If pymupdf is not available or image extraction fails, proceed with pdfplumber text extraction only (Step 1B below) with extra caution on the Edge-Column Bias Check.

---

## Step 1B-ColDetect — Column Boundary Detection

**Purpose**: Use the PDF's vector line drawings (table grid lines) to detect exact column boundaries at pixel level. Then verify that each X mark from vision extraction falls within the correct column. This catches "column drift" — where superscript footnotes (X²²'²³) or merged cells shift text visually into an adjacent column.

**Dependencies**: `pymupdf` (already installed for vision step)

**Implementation**:

```python
# Run the column boundary detection script
python3 scripts/vision_table_extractor.py \
  --pdf protocol.pdf \
  --pages 22,23,24 \
  --out {out_dir}/
```

**Verification process**:

After running `vision_table_extractor.py`, load both the vision-extracted table (`vision_SOA_table.json`) and the column detection results (`column_detection.json`). For each procedure row:

1. Get the X mark positions from `extract_text_with_positions()` — these have exact x-coordinates
2. Get the column boundaries from `detect_table_lines()` — these have exact column edges
3. For each X mark, compute which column it falls in by checking `col_left ≤ text_center_x ≤ col_right`
4. Compare the column assignment to what the vision extraction reported
5. If they disagree, the column boundary detection is MORE RELIABLE (it uses the actual table grid lines)

**Critical correction pattern**: When a text item like "X²²'²³" has its center x-coordinate at position 520, and column boundaries are:
- V4: 480–540
- V5: 540–620

If the center is at 520, it's in V4. But if the center is at 545, it's in V5. The superscript "²²'²³" makes the text wider, which can shift the center rightward.

**Correction rules**:
- When column detection disagrees with vision extraction, produce a `vision_corrections.json` that lists every correction with evidence:
  ```json
  {
    "corrections": [
      {
        "procedure": "MRI modality",
        "vision_said": "V4",
        "column_detection_says": "V5",
        "text_center_x": 545,
        "column_V4_range": [480, 540],
        "column_V5_range": [540, 620],
        "verdict": "CORRECT_TO_V5",
        "confidence": "HIGH"
      }
    ]
  }
  ```
- Apply all HIGH confidence corrections to `vision_SOA_table.json` before passing it to the ontology builder

**Save outputs**:
- `{out_dir}/column_detection.json` — raw column boundaries and text positions
- `{out_dir}/vision_corrections.json` — corrections applied (updated with column evidence)

---

## Step 1B — SoA Ontology

**Purpose**: Read SoA table pages from manifest, produce `ontology.json`. When vision-extracted data is available (from Step 1B-Vision), use it as the PRIMARY source for the procedure × visit grid. Fall back to pdfplumber text only when vision data is unavailable.

**PDF pages to read**: All pages listed in `manifest.section_map.SOA[*].pages_approx` plus 2 buffer pages after the last one (for footnotes).

**LLM prompt** (when vision data is available, include it):
```
Read the Schedule of Activities table in the following protocol pages.
It is a matrix where rows are procedures and columns are visits.

[PROTOCOL PAGES]
{soa_pages_text}
[END]

[VISION-EXTRACTED TABLE — use this as PRIMARY source of truth for procedure × visit mapping]
{vision_soa_table_json_if_available}
[END VISION DATA]

Extract the complete SoA structure. Return JSON:
{
  "soa_section_title": "exact title",
  "marker_legend": {
    "X": "meaning (e.g. required, recorded in database)",
    "S": "meaning if present, else null"
  },
  "epochs": ["Screening", "Treatment", "Follow-up"],
  "visits": [
    {
      "visit_id": "V_S1",
      "original_label": "S-I",
      "epoch": "screening|treatment|follow_up|end_of_study|unscheduled",
      "day_reference": "Day -45 to 0",
      "window": "±3 days or null",
      "is_treatment_day": false
    }
  ],
  "procedures": [
    {
      "procedure_id": "PROC_VITALS",
      "canonical_name": "Vital signs",
      "original_label": "exact row label",
      "category": "physical_assessment|laboratory|intervention|questionnaire_pro|administrative|other",
      "required_at": ["V_S1", "V_V1"],
      "source_only_at": [],
      "footnote_numbers": ["9", "10"]
    }
  ],
  "footnotes": {
    "9": "full verbatim footnote text",
    "10": "full verbatim footnote text"
  },
  "cross_visit_rules": ["any timing/washout/sequencing rules in SoA section text"]
}

Rules:
- Do NOT invent visits or procedures — only what is in the table
- required_at / source_only_at must reference visit_id values you defined
- footnotes: include COMPLETE verbatim text — never truncate
- EDGE-COLUMN BIAS CHECK: PDF text extraction destroys column positioning. X marks
  near the first and last columns are most prone to misalignment. For each procedure:
  1. Count the total X marks you see in that row (including marks that wrapped to the
     next line or are separated by whitespace)
  2. Verify that count equals len(required_at) + len(source_only_at)
  3. If the count does NOT match, re-examine which columns the marks belong to —
     pay special attention to the FIRST column and LAST 2 columns
  4. If alignment is ambiguous (e.g. line-wrapped rows), use the procedure's footnotes
     to resolve: a footnote saying "at all visits" means every column gets an X
- Return ONLY the JSON
```

**Post-processing: Footnote Cross-Validation (Fix 1)**

After the LLM returns the ontology JSON, run a second LLM pass to cross-validate
`required_at` lists against footnote semantics. This catches column-alignment errors
from PDF text extraction where X marks lose positional anchoring.

**Footnote cross-validation prompt**:
```
You are a clinical trial protocol expert validating a Schedule of Activities ontology.

The ontology below was extracted from a PDF SoA table. PDF text extraction destroys
column alignment, so the `required_at` lists may have errors — especially for the
FIRST visit column and LAST 1-2 visit columns, which are most prone to edge-alignment
mistakes.

ONTOLOGY:
{ontology_json}

CROSS-VALIDATION RULES:
1. For each procedure, read its associated footnotes (from the footnotes dict).
   - If a footnote says "at all visits", "at all on-site visits", "at every visit",
     "each visit", or similar universal language → verify that required_at includes
     ALL visits (or all on-site visits excluding phone/remote visits).
   - If a footnote says "before [another procedure]" or "prior to [questionnaires]"
     → verify that required_at includes every visit where that other procedure occurs.
   - If a footnote describes a condition that logically applies at additional visits
     (e.g. "accountability" implies end-of-study reconciliation), flag those visits
     as potentially missing.

2. Count the total X/check marks you see per procedure row in the raw SoA text.
   Compare that count to len(required_at). If they don't match, the alignment is wrong.

3. For each procedure, check clinical logic:
   - Drug accountability/dispensation → must include End of Study visit (final return)
   - Pre-questionnaire scripts → must include every visit with questionnaire/PRO procedures
   - Informed consent → must include first screening visit at minimum
   - AE collection → must include all visits from first dose onward

Return JSON:
{
  "validation_status": "PASS|HAS_CORRECTIONS",
  "corrections": [
    {
      "procedure_id": "PROC_XXX",
      "canonical_name": "...",
      "issue": "description of what's wrong",
      "current_required_at": ["V_S2", "V_V1", ...],
      "corrected_required_at": ["V_S1", "V_S2", "V_V1", ...],
      "evidence": "Footnote N says '...' which implies visit V_S1 should be included"
    }
  ]
}
Return ONLY the JSON.
```

**Action**: If corrections are found, apply them to the ontology JSON before saving.
Log all corrections in `{out_dir}/ontology_corrections.json` for audit trail.

**Save output**: `{out_dir}/ontology.json`

---

## Step 2 — KRI Extraction (per category)

**Purpose**: Extract all KRIs for one domain category. Run 5 times (once per category).

**PDF pages to read**: Pages from `manifest.section_map[CATEGORY]` entries.

**KRI schema** (every KRI must match exactly):
```json
{
  "kri_id": "SOA-V1-001",
  "kri_name": "V1- IMP administration",
  "description": "1-2 sentences: what this monitors and why",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V1- Verify that [exact actionable check]",
  "protocol_reference": "Section 9.2, Page 52: \"verbatim quote ≤30 words\"",
  "additional_footnotes": "Footnote 10: verbatim text — or null"
}
```

**ID format by category**:
- SOA: `SOA-{VISIT_CODE}-{NNN}` e.g. `SOA-S1-001`, `SOA-V1-001`, `SOA-CROSS-001`
- ELIG: `ELIG-INC-{NNN}` and `ELIG-EXC-{NNN}`
- SAF: `SAF-AE-{NNN}`, `SAF-ALLERGY-{NNN}`, `SAF-PREG-{NNN}`, `SAF-RM-{NNN}`, `SAF-STOP-{NNN}`
- END: `END-PRI-{NNN}`, `END-KSEC-{NNN}`, `END-SEC-{NNN}`, `END-EXP-{NNN}`, `END-ASET-{NNN}`, `END-STAT-{NNN}`, `END-ICE-{NNN}`
- OPS: `OPS-IMP-{NNN}`, `OPS-BLIND-{NNN}`, `OPS-RECS-{NNN}`, `OPS-COMP-{NNN}`

### 6-Step SOA Extraction Process

The SOA extraction follows a strict 6-step process using the Camelot CSV as ground truth:

**Step SOA-1 — Visit Mapping**: Parse `soa_table.json` to extract all visits with their timing (week numbers). Establish canonical naming conventions (V0, V1, V2... V20, EDC_EOS). From this point forward, use ONLY these names in all KRIs.

**Step SOA-2 — Table Verification**: Compare the Camelot `soa_table.csv` against the PDF page image for verification. Flag any cells where Camelot shows empty but the image shows X (footnote superscript issue). Save the verified matrix.

**Step SOA-3 — Check-in KRIs**: For each visit, create ONE check-in KRI (SOA-CHECKIN-{VID}) verifying the subject attended within the protocol-specified timing window. Include: visit window (±days), fasting requirements, scheduling constraints.

**Step SOA-4 — Procedure KRIs**: For each visit, create:
- ONE procedure-list KRI (SOA-PROC-{VID}) listing ALL procedures required at that visit in the format: `V1 - procedure name`
- ONE KRI per procedure × visit cell (SOA-{VID}-{procedure}) with the specific check

**Step SOA-5 — Footnote Enrichment**: After table-based KRIs are complete, read all protocol footnotes and:
- Enrich each procedure KRI with relevant footnote details
- Create **cross-visit rule KRIs** (SOA-CROSS-*) for protocol-wide rules:
  - Fasting requirements (≥10h before blood draws, exceptions for CK/LFTs/pregnancy)
  - IP dosing window (1 day before to 4 days after scheduled date)
  - Lipid/ADA/PK/PCSK9 10-day post-dose rule
  - IP injection sequence (only after blood draws + physical exam)
  - Missed visit contact escalation (phone → email → text → letter → certified mail)
  - EDC retention team notification
  - EOS safety follow-up period (typically 28-40 days post-last-dose)
  - V5/baseline observation period for IP administration
  - Visit-specific special rules from footnotes

**Step SOA-6 — Self-Verification**: Cross-check that every X cell in the Camelot CSV has a corresponding KRI. Report: `N/N cells covered = 100%`. Flag any gaps.

### SOA prompt
```
Extract Schedule of Activities KRIs for the {EPOCH} epoch.
Protocol: {protocol_id}
Visits in scope: {visit_ids}

ONTOLOGY VISITS:
{visits_json}

ONTOLOGY FOOTNOTES:
{footnotes_json}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- One KRI per procedure × visit cell where the procedure is required
- rule_for_llm MUST start with visit prefix: "V1-", "S1-", "All visits-", etc.
- Visit check-in KRIs: include window (e.g. "within 90 ± 7 days")
- Treatment visits: vital signs measured TWICE (pre + post injection per footnote)
- Washout KRIs: say "by checking medication logs and visit timestamps"  
- Lab KRIs: include ALL specific analytes from the footnote — never "biochemistry panel" alone
- Vitals KRIs: use exact positioning wording from Section 13.2 / equivalent
- IMP admin KRIs: include exact dose, volume, route, person who administers, post-injection observation time
- Include ALL footnote details that apply to that procedure × visit
- Measurement specs: height/weight KRIs must include units (kg, cm) and preparation
  (e.g. "shoes removed", "after voiding") when the protocol specifies them
- Questionnaire recall periods: if a PRO instrument has a recall period (e.g. "past week",
  "last 2 weeks"), include it in rule_for_llm — check the appendix/instrument description
- Procedure sequencing: if footnotes specify procedure order or prerequisites (e.g.
  "WOMAC performed second, immediately after placebo script"), include sequencing in
  rule_for_llm
- Non-drug therapies: when protocol tracks "medications AND non-drug therapies",
  capture both explicitly — do not collapse into "medications" alone
- Stability windows: if concomitant therapy must be stable for N weeks/months prior,
  include the stability duration in the rule
- Visit window KRIs (MANDATORY — every visit and screening):
  For EVERY visit in the SoA table — including all screening visits (S-I, S-II, etc.),
  all treatment visits (V1, V2, V3, etc.), and all follow-up visits (V4, V5, V6/EOS, etc.)
  — create one dedicated "check-in / within-window" KRI. This KRI verifies that:
    1. The visit actually occurred
    2. The visit occurred within the protocol-specified timing window
  Use the day reference AND window tolerance from the ontology (e.g. "Day -45 to 0",
  "Day 14 ± 3 days", "Month 3 ± 7 days"). If the protocol specifies an allowed range
  or deviation window for the visit, embed it in rule_for_llm.
  Examples:
    - "S1- Verify that the Screening I visit occurred within the allowed window (Day -45 to Day 0)"
    - "S2- Verify that the Screening II visit occurred within [N] days after Screening I"
    - "V1- Verify that the Day 0 treatment visit occurred within the allowed window"
    - "V2- Verify that the Day 14 treatment visit occurred within 14 ± 3 days of Day 0"
    - "V4- Verify that the 3-month follow-up visit occurred within 90 ± 7 days of first treatment"
  If the SoA table or protocol text does not specify a window for a particular visit,
  still create the check-in KRI using whatever timing reference is available (e.g.
  "Day -45 to 0" for screening). Never skip a visit — if the protocol has it, it
  gets a window KRI.

Return ONLY a JSON array starting with [ and ending with ]
```

### ELIG prompt
```
Extract Eligibility KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- One KRI per criterion or per meaningful sub-criterion (e.g. 5a, 5b → two KRIs)
- Inclusion rule_for_llm: "Verify that [requirement] is documented/confirmed"
- Exclusion rule_for_llm: "Verify the absence of [condition]" (preferred phrasing)
- Include exact numeric thresholds, timeframes, clinical terms verbatim
- Lab thresholds: list each parameter and exact threshold value
- Multi-part exclusion criteria (e.g. criterion 14a through 14k): one KRI per letter
- Timing in criteria: if a criterion specifies a timeframe (e.g. "symptoms ≥ 3 months",
  "X-ray within 6 months"), embed the timeframe directly in rule_for_llm — not only
  in additional_footnotes
- Investigator framing: if a criterion is framed as "Investigator-assessed" or
  "in the Investigator's judgment", preserve that framing in the rule

Return ONLY a JSON array
```

### SAF prompt
```
Extract Safety & Toxicity KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- Cover: AE/SAE collection windows, reporting timelines (24h, 48h), allergic reaction 
  management (exact drug names + doses), stopping rules, DSMB triggers, rescue medication 
  dose caps, pregnancy reporting, AESI definitions, post-injection observation period
- Include exact drug names and doses for emergency treatment protocols
- Include exact reporting timeframes
- Distinguish: pre-IMP conditions = medical history (not AE)
- Boundary rules: what is collected when (e.g. only SAEs beyond 6 months)
- Concomitant medication timing: prohibited medications with specific washout/exclusion
  windows (e.g. "IA corticosteroids prohibited within 3 months") should each get their
  own KRI with the exact timing

Return ONLY a JSON array
```

### END prompt
```
Extract Endpoints & Statistics KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- Order: primary → key secondary → secondary → exploratory → ICEs → analysis sets → statistics
- One KRI per endpoint, per ICE type, per analysis set definition
- Analysis sets: use exact protocol definitions
  (e.g. ITT = ALL randomized, not just ≥1 dose)
- Statistical rules: ANCOVA covariates, gatekeeping sequence, alpha levels, 
  imputation strategy, interim analysis trigger criteria
- Baseline definitions: general (Day 0 pre-dose) AND endpoint-specific if different
- ADP-NRS calculation method if applicable

Return ONLY a JSON array
```

### OPS prompt
```
Extract Operations & Compliance KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- Cover: IMP storage conditions (exact temperatures), who handles IMP, who administers,
  blinding approach, unblinding documentation, record retention duration,
  eCRF requirements, participant withdrawal/replacement rules,
  regulatory approvals required, 21 CFR Part 11 compliance
- Include exact temperature ranges
- Include exact retention durations (years)
- Central analyses: cover all central review requirements — imaging (X-ray, MRI),
  lab, ECG — including verification that data was transmitted to the central facility
  and results were reviewed centrally
- Data governance: include Investigator approval/sign-off of eCRF data, delegation
  of authority logs, and any regulatory sign-off requirements
- Participant rights: include ICF copy provision to participant, re-consent rules,
  and any participant notification requirements

Return ONLY a JSON array
```

**Save output**: `{out_dir}/raw_{CATEGORY}.json`

---

## Step 3A — Completeness Check

**Purpose**: Verify every ontology procedure × visit has a KRI. Run once per category.

**For SOA**: Cross-reference `ontology.procedures[*].required_at` against extracted KRI names/visit prefixes.

**LLM prompt (SOA)**:
```
Check completeness of SOA KRI extraction.
Protocol: {protocol_id}

EXPECTED COVERAGE (from ontology):
{procedures_with_required_at}

EXTRACTED SOA KRIs:
{kri_name_and_rule_list}

For each procedure, check whether a KRI exists for each visit in required_at.
A KRI covers a procedure×visit if its visit prefix (e.g. V1-, S1-) matches
and the name/rule refers to that procedure.

Return JSON:
{
  "total_expected": N,
  "total_covered": N,
  "coverage_pct": 0-100,
  "gaps": [
    {
      "procedure": "canonical_name",
      "missing_at": ["V_V4", "V_V5"],
      "severity": "CRITICAL|MODERATE|MINOR",
      "note": "brief reason"
    }
  ]
}

Severity: CRITICAL = intervention/lab/consent at treatment visit, MODERATE = assessment at follow-up, MINOR = administrative
```

**For ELIG/SAF/END/OPS**: Simpler coverage check — does each subsection have ≥1 KRI?

**Action**: If CRITICAL gaps found → re-run Step 2 for the affected pages only, merge results.

### Step 3A+ — Clinical Completeness Heuristics (Fix 3)

After the ontology-based completeness check, run an additional heuristic pass that catches
gaps the ontology itself may have missed (e.g., due to PDF table parsing errors in Step 1B).
These heuristics are protocol-agnostic and based on universal clinical trial logic.

**Heuristic prompt**:
```
You are a clinical trial protocol expert performing a completeness audit.
Review the extracted KRI set against clinical logic heuristics — these catch gaps
that the ontology may have missed due to PDF parsing errors.

EXTRACTED SOA KRIs:
{soa_kri_names_and_rules}

ONTOLOGY VISITS:
{visits_json}

ONTOLOGY PROCEDURES:
{procedures_json}

ONTOLOGY FOOTNOTES:
{footnotes_json}

Apply ALL of the following heuristics. For each, check whether the extracted KRIs
satisfy the requirement. If not, flag the gap.

HEURISTIC 1 — DRUG/MEDICATION ACCOUNTABILITY AT END-OF-STUDY:
If any procedure related to "medication accountability", "drug accountability",
"IMP accountability", "medication return", or "rescue medication accountability"
exists at treatment or follow-up visits, it MUST also exist at:
  a) The End-of-Study (EOS) visit — final reconciliation is standard GCP practice
  b) Any Unscheduled visit type — medication changes can occur at any contact
Check: is there a KRI for this procedure at the EOS visit? At UNS?

HEURISTIC 2 — PRE-QUESTIONNAIRE PROCEDURES AT ALL PRO VISITS:
If a procedure is described in any footnote as occurring "before questionnaires",
"prior to completion of questionnaires", "at all visits", "at all on-site visits",
or similar universal language, it MUST exist at EVERY visit that has any
questionnaire/PRO procedure (WOMAC, PGA, EQ-5D, NRS, PHQ-9, WPI, etc.).
Check: list all visits with questionnaire KRIs. Does the pre-questionnaire
procedure have a KRI at each of those visits?

HEURISTIC 3 — INFORMED CONSENT AT FIRST CONTACT:
If an informed consent procedure exists, it MUST include the very first
screening visit (not only later visits).
Check: does an ICF/consent KRI exist at the first screening visit?

HEURISTIC 4 — AE COLLECTION FROM FIRST DOSE:
If AE/adverse event collection KRIs exist, they must cover all visits from
first treatment dose through the protocol-defined reporting window.
Check: is there an AE KRI at every visit from first treatment through EOS?

HEURISTIC 5 — CONCOMITANT MEDICATIONS AT ALL VISITS:
Concomitant medication recording is typically required at every visit.
Check: does a concomitant medication KRI exist at every visit?

HEURISTIC 6 — SCREENING PROCEDURE SYMMETRY:
If a procedure exists at a later screening visit but not the first (or vice versa),
flag it for review — unless the protocol explicitly states the procedure is only
at one screening visit.

HEURISTIC 7 — VITAL SIGNS AT TREATMENT VISITS:
If vital signs are measured at treatment visits, check whether both pre-treatment
and post-treatment measurements are captured (common requirement for IMP infusions/
injections with observation periods).

HEURISTIC 8 — EDGE-COLUMN FOOTNOTE RECONCILIATION:
For procedures in the first column (V0/Pre) or last column (EDC/EOS), cross-check
against footnotes. If a footnote explicitly says a procedure occurs "at EDC/EOS"
or "at end of study" but the Camelot CSV shows it only at V0 (or vice versa),
flag the discrepancy. Also check: if a footnote says "will NOT be collected at EDC"
but the CSV shows X at EDC, flag for removal.
This catches edge-column swaps where table extraction misattributes marks near
the left/right edges of wide tables.

HEURISTIC 9 — EPOCH BOUNDARY PLAUSIBILITY CHECK:
For each procedure, check if it has isolated marks in a different epoch than its
primary cluster. For example, if a procedure has marks at V5-V20 (treatment)
but also a single mark at V0 (pre-screening), flag it for review.
A single isolated mark in a distant epoch is suspicious — verify it against the
Camelot CSV and protocol text. Exception: procedures clinically expected at
screening (labs, ICF, eligibility, medical history).

HEURISTIC 10 — CONTIGUOUS COVERAGE GAP DETECTION (run via Python, then validate with LLM):
Before running the LLM heuristic prompt above, run the Python-based gap detector:
```python
from vision_table_extractor import detect_contiguous_gaps
import json

with open(f"{out_dir}/ontology.json") as f:
    ontology = json.load(f)

gap_findings = detect_contiguous_gaps(ontology)
# Save for audit
with open(f"{out_dir}/contiguous_gap_findings.json", "w") as f:
    json.dump(gap_findings, f, indent=2)
```

For each procedure flagged by Heuristic 10:
1. The Python function identifies procedures with 5+ visit marks that have suspicious
   "holes" in their visit sequence (>15% of the range is missing).
2. For each flagged procedure, RE-READ the SoA table page images at the specific
   column positions of the missing visits. Use the right-half crop images for right-side
   columns and left-half crops for left-side columns — these have higher effective resolution.
3. If the re-read confirms X marks exist at the missing visits, add them to the ontology's
   `required_at` list for that procedure.
4. Log all corrections in `{out_dir}/contiguous_gap_corrections.json`.

This heuristic specifically catches the pattern where vision extraction misses X marks
in intermediate columns of wide tables (e.g., a procedure present at V5-V20 but vision
only captures V5, V8, V11, V14, V17, V20 — missing the ones in between). Clinical
procedures rarely skip arbitrary visits in a contiguous range.

Return JSON:
{
  "heuristics_applied": 10,
  "heuristics_passed": N,
  "gaps_found": [
    {
      "heuristic": "DRUG_ACCOUNTABILITY_AT_EOS",
      "heuristic_number": 1,
      "procedure": "Rescue medication accountability",
      "missing_at_visits": ["V_V6", "V_UNS"],
      "severity": "CRITICAL|MODERATE|MINOR",
      "evidence": "Procedure exists at V1-V5 but not V6/UNS. GCP requires final
                    reconciliation at study end.",
      "recommendation": "Add KRI for rescue medication accountability at V6 and UNS"
    }
  ]
}
Return ONLY the JSON.
```

**Action**: For each gap found:
1. Re-read the relevant protocol pages to confirm the procedure should exist at that visit
2. If confirmed, generate the missing KRI(s) using the Step 2 SOA prompt for that visit
3. Add generated KRIs to `raw_SOA.json`
4. Log all heuristic-generated KRIs in `{out_dir}/heuristic_additions.json` for audit trail

**Save output**: `{out_dir}/gaps_report.json` (append heuristic results to ontology gaps)

---

## Step 3B — Accuracy Check

**Purpose**: Sample 20 KRIs (4 per category), re-read their source pages, verify faithfulness.

**How to sample**: Take the first 4 KRIs from each `raw_{CAT}.json` that have a parseable page number in `protocol_reference`.

**For each batch of 5 KRIs**, read their cited PDF pages, then:

**LLM prompt**:
```
Verify accuracy of these KRIs against the protocol text.

KRIs TO VERIFY:
{kri_list_with_rule_and_reference}

PROTOCOL SOURCE PAGES:
{page_texts}

For each KRI verify:
1. Is rule_for_llm faithful to the protocol?
2. Are all values correct (thresholds, drug names, doses, timing)?
3. Is protocol_reference section/page accurate?
4. Are any critical details missing?

Return JSON array:
[
  {
    "kri_id": "...",
    "verdict": "CORRECT|IMPRECISE|WRONG",
    "issue": "specific problem or null",
    "corrected_rule": "corrected text if IMPRECISE/WRONG, else null",
    "protocol_evidence": "verbatim quote ≤20 words proving verdict"
  }
]
```

**Threshold**: ≥85% CORRECT → pass. Otherwise fix WRONG/IMPRECISE items and re-verify.

**Save output**: `{out_dir}/accuracy_report.json`

---

## Step 3C — Consistency Check

**Purpose**: Group SOA KRIs by procedure family, check same procedure is consistent across visits.

**Grouping**: Strip visit prefix (`V1- `, `S2- `, etc.) from `kri_name` to get bare procedure name. Group all KRIs with same bare name. Only check families with 3+ members.

**For each family**, read cited PDF pages, then:

**LLM prompt**:
```
Check internal consistency for the "{procedure_name}" procedure across these visits.

KRIs:
{kri_list}

PROTOCOL PAGES:
{relevant_page_text}

Identify inconsistencies where a detail present at some visits is absent from others
without a visit-specific reason — e.g.:
- "without shoes" for weight
- "supine" for vitals  
- "including CRP/hsCRP" for labs
- "by checking medication logs" for washout
- specific drug names in safety procedures

Mark differences as intentional only if the protocol explicitly states different
requirements per visit (e.g. vitals twice on treatment days, once on follow-up).

Return JSON:
{
  "family": "{procedure_name}",
  "overall_status": "CONSISTENT|HAS_INCONSISTENCIES",
  "inconsistencies": [
    {
      "description": "what the inconsistency is",
      "affected_kri_ids": ["..."],
      "reference_kri_ids": ["..."],
      "could_be_intentional": false,
      "protocol_quote": "verbatim ≤20 words",
      "recommendation": "what affected KRIs should say"
    }
  ]
}
```

**Action**: Flag inconsistencies for user review. Do not auto-fix.

**Save output**: `{out_dir}/consistency_report.json`

---

## Step 4A — Assembly (Python, no LLM)

Run this Python code to merge all category files:

```python
import json, re, os

CATEGORY_LABELS = {
    "SOA": "Schedule of Activities", "ELIG": "Eligibility",
    "SAF": "Safety & Toxicity", "END": "Endpoints & Statistics",
    "OPS": "Operations & Compliance"
}

def assemble(out_dir, manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    all_kris, categories_meta = [], []
    
    for cat in ["SOA", "ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(out_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            continue
        with open(raw_path) as f:
            data = json.load(f)
        kris = data.get("kris", [])
        
        # Normalize + deduplicate
        seen, cleaned = set(), []
        for i, k in enumerate(kris, 1):
            rule = (k.get("rule_for_llm") or "").strip().lower()
            if rule and rule in seen: continue
            if rule: seen.add(rule)
            if not k.get("rule_for_llm") and not k.get("kri_name"): continue
            k["category_id"] = cat
            k["category_label"] = CATEGORY_LABELS[cat]
            cleaned.append(k)
        
        all_kris.extend(cleaned)
        categories_meta.append({
            "id": cat, "label": CATEGORY_LABELS[cat],
            "kri_count": len(cleaned),
            "kri_ids": [k["kri_id"] for k in cleaned]
        })
    
    output = {
        "_meta": {
            "version": "1.0.0",
            "protocol": manifest.get("protocol_id", "UNKNOWN"),
            "sponsor": manifest.get("sponsor", ""),
            "extracted_by": "protocol-kri-extractor",
            "total_kris": len(all_kris),
            "total_categories": len(categories_meta)
        },
        "categories": categories_meta,
        "kris": all_kris
    }
    
    out_path = os.path.join(out_dir, "extracted_kris.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    return out_path
```

### Excel output (always generate alongside JSON)

After assembling `extracted_kris.json`, also generate `Extracted_KRIs.xlsx` using openpyxl.
The Excel workbook must have **5 sheets** matching the golden set format:

| Sheet name | Category | Columns |
|---|---|---|
| SOA | Schedule of Activities | KRI Name, Description, category, Rule to Check- for LLM, Referance, Additional Footnotes |
| ELIGIBILITY | Eligibility | KRI Name, Description, category, Referance, Rule to Check- for LLM |
| SAF&TOX | Safety & Toxicity | KRI Name, Description, category, Referance, Rule to Check- for LLM |
| END&STAT | Endpoints & Statistics | KRI Name, Description, Category, Referance, Rule to Check for LLM |
| OPE&COM | Operations & Compliance | KRI Name, Description, Category, Referance, Rule to Check for LLM |

**Note**: SOA has 6 columns (includes "Additional Footnotes"), all others have 5.
The column ORDER matters — SOA puts "Rule" before "Referance", other sheets put "Referance" before "Rule".

Formatting:
- Blue header row with white bold text, frozen at row 1
- Text wrapping enabled on all cells
- Column widths: ~35 for name, ~50 for description, ~20 for category, ~55 for rule, ~45 for reference

Map KRI fields to columns:
- "KRI Name" ← `kri_name` (or `kri_id` if name is missing)
- "Description" ← `description`
- "category" ← category label (e.g. "Schedule of Activities")
- "Rule to Check- for LLM" ← `rule_for_llm`
- "Referance" ← `protocol_reference`
- "Additional Footnotes" ← `additional_footnotes` (SOA only, null → empty)

```python
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

def generate_excel(out_dir, all_kris_by_category):
    """Generate Extracted_KRIs.xlsx matching golden set format."""
    SHEETS = [
        ("SOA", "Schedule of Activities", True),
        ("ELIGIBILITY", "Eligibility", False),
        ("SAF&TOX", "Safety & Toxicity", False),
        ("END&STAT", "Endpoints & Statistics", False),
        ("OPE&COM", "Operations & Compliance", False),
    ]
    CAT_MAP = {"SOA": "SOA", "ELIGIBILITY": "ELIG", "SAF&TOX": "SAF",
               "END&STAT": "END", "OPE&COM": "OPS"}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    hdr_font = Font(bold=True, size=11, color="FFFFFF")
    hdr_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    wrap = Alignment(wrap_text=True, vertical="top")
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                    top=Side(style='thin'), bottom=Side(style='thin'))

    for sheet_name, cat_label, has_footnotes in SHEETS:
        ws = wb.create_sheet(sheet_name)
        cat_key = CAT_MAP[sheet_name]
        kris = all_kris_by_category.get(cat_key, [])

        if has_footnotes:
            headers = ["KRI Name", "Description", "category",
                       "Rule to Check- for LLM", "Referance ", "Additional Footnotes"]
        else:
            headers = ["KRI Name", "Description", "category",
                       "Referance ", "Rule to Check- for LLM"]

        for col, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=col, value=h)
            c.font = hdr_font; c.fill = hdr_fill; c.alignment = wrap; c.border = border

        for i, kri in enumerate(kris, 2):
            name = kri.get("kri_name", kri.get("kri_id", ""))
            desc = kri.get("description", "")
            rule = kri.get("rule_for_llm", "")
            ref = kri.get("protocol_reference", "")
            fn = kri.get("additional_footnotes") or ""

            if has_footnotes:
                row = [name, desc, cat_label, rule, ref, fn]
            else:
                row = [name, desc, cat_label, ref, rule]

            for col, val in enumerate(row, 1):
                c = ws.cell(row=i, column=col, value=str(val) if val else "")
                c.alignment = wrap; c.border = border

        widths = [35, 50, 20, 55, 45, 40] if has_footnotes else [35, 50, 20, 45, 55]
        for col, w in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w
        ws.freeze_panes = "A2"

    xlsx_path = os.path.join(out_dir, "Extracted_KRIs.xlsx")
    wb.save(xlsx_path)
    return xlsx_path
```

---

## Step 4B — Golden Set Prompt

After Step 4A assembly completes, **always ask the user**:

> "Do you have a golden set (reference KRI file) to compare against? If so, please provide the file path or upload it."

Wait for the user's response. If they provide a golden set path or file, proceed to Step 4C.
If they say no, the pipeline is complete.

**Accepted golden set formats**:
- JSON file with a `kris` array (same schema as `extracted_kris.json`)
- JSON file that IS a flat array of KRI objects
- JSON file with category-level keys (e.g. `{"SOA": [...], "ELIG": [...]}`)

Normalize the golden set into a flat list of KRI objects before proceeding.

**Save normalized golden set**: `{out_dir}/golden_set_normalized.json`

---

## Step 4C — Golden Set Comparison

Run category-by-category comparison. For each of the 5 categories, run 3 phases in sequence.
Use parallel subagents to process multiple categories simultaneously when possible.

### Phase 1 — Semantic Matching

For each category, match extracted KRIs to golden KRIs based on semantic similarity
of the `rule_for_llm` and `kri_name` fields — not ID matching (IDs may differ between sets).

**Matching prompt** (per category, batch up to 20 golden KRIs at a time):
```
You are a clinical trial protocol expert matching CRA verification rules.

GOLDEN KRIs ({CATEGORY}):
{golden_kris_json}

EXTRACTED KRIs ({CATEGORY}):
{extracted_kris_json}

For each GOLDEN KRI, find the best-matching EXTRACTED KRI(s) based on what the rule
verifies — the same clinical requirement, same visit scope, same data check.
Matching is by meaning, not by ID or phrasing.

Rules:
- A golden KRI may match 1 extracted KRI (1:1) or multiple (1:many if the extracted
  set split the golden rule into finer-grained KRIs)
- An extracted KRI may match multiple golden KRIs (many:1 if the extracted set merged
  golden rules)
- Some golden KRIs may have NO match (missing from extraction)
- Some extracted KRIs may have NO golden match (extra in extraction)

Return JSON:
{
  "matches": [
    {
      "golden_kri_id": "...",
      "golden_rule": "the rule_for_llm text",
      "matched_extracted_ids": ["id1", "id2"] or [],
      "match_type": "1:1|1:many|many:1|unmatched"
    }
  ],
  "unmatched_extracted": ["extracted_id1", "extracted_id2"]
}
```

### Phase 2 — Semantic Judging

For each matched pair (or group), evaluate semantic equivalence.

**Judge prompt** (batch up to 15 pairs per call):
```
You are a clinical trial monitoring expert comparing CRA verification rules.

JUDGING PHILOSOPHY — TWO TIERS:
This comparison uses TWO separate criteria for judging:

TIER 1 — SEMANTIC COVERAGE (lenient):
  Does the extracted KRI check the SAME clinical requirement as the golden KRI?
  If yes, differences in phrasing, sentence structure, word choice, or level of
  detail in HOW the rule is expressed do NOT matter. Focus on WHAT is being
  verified, not HOW the sentence is worded.
  Examples that are EQUIVALENT under semantic coverage:
  - "Verify absence of X" vs "Verify participant does not have X"
  - "Confirm weight was recorded" vs "Verify body weight measurement was performed"
  - "Check consent was obtained" vs "Verify ICF signed and dated before procedures"
  - "Verify vitals were taken" vs "Verify vital signs (BP, HR, temp) were measured"
    (if both refer to the same visit and same clinical check)

TIER 2 — FACTUAL PRECISION (strict):
  When EITHER rule (golden or extracted) contains specific factual details from the
  protocol, those details MUST be accurate and present. Factual details include:
  - Numeric values: thresholds, doses, ages, lab ranges (e.g. "≥64 years", "≤-150°C")
  - Visit windows: timing tolerances (e.g. "±3 days", "Day -45 to 0")
  - Drug/compound names: exact names, not generic descriptions (e.g. "diphenhydramine
    50 mg IV" not "antihistamine")
  - Specific time periods: washout durations (e.g. "≥48 hours", "within 3 months")
  - Named instruments/scales: (e.g. "WOMAC Total", "PHQ-9", "KL grade")
  - Named procedures with specific method: (e.g. "ultrasound-guided", "central read")
  If these factual details match or are both absent → no penalty.
  If one has them and the other omits them → mark as SUBSET or SUPERSET.
  If both have them but they DIFFER → mark as DIVERGENT.

SCORING RUBRIC (applying both tiers):
- EQUIVALENT: Same clinical requirement (Tier 1 pass). Any factual details present
  in both rules are consistent (Tier 2 pass). Wording differences are irrelevant.
  A rule that says more about context or rationale but checks the same thing = EQUIVALENT.
- SUBSET: Same clinical requirement (Tier 1 pass) but extracted OMITS a specific
  factual detail (drug name, dose, threshold, timing, method) that the golden includes
  and that comes from the protocol. Only flag as SUBSET if the missing detail would
  change what a CRA actually checks in practice.
- SUPERSET: Same clinical requirement (Tier 1 pass) but extracted ADDS a specific
  factual detail beyond the golden that comes from the protocol.
- DIVERGENT: Different clinical requirement (Tier 1 fail), OR same requirement but
  factual details contradict each other (e.g. "±3 days" vs "±7 days").

IMPORTANT — DO NOT mark as SUBSET for:
  - Different phrasing that means the same thing
  - Different sentence structure or ordering
  - One rule being more verbose or descriptive than the other
  - One rule including explanatory context the other omits
  - Minor differences in how the same data source is referenced
  These are ALL considered EQUIVALENT if the clinical check is the same.

FEW-SHOT EXAMPLES:
[PAIR] INC1
  GOLDEN:    Verify age ≥ 64 years at screening.
  EXTRACTED: Verify participant is ≥ 64 years old at first screening visit.
  VERDICT: EQUIVALENT — same check, same threshold, phrasing irrelevant

[PAIR] WEIGHT
  GOLDEN:    V4- Verify weight measured in kilograms, shoes removed.
  EXTRACTED: V4- Verify weight was recorded.
  VERDICT: SUBSET — missing factual details "in kilograms" and "shoes removed"

[PAIR] CONSENT
  GOLDEN:    S1- Verify ICF signed before procedures.
  EXTRACTED: S1- Verify informed consent form is signed and dated by participant
             before any study-specific procedures, with copy provided to participant.
  VERDICT: SUPERSET — adds "dated", "copy provided" factual details

[PAIR] SOA-V4-075
  GOLDEN:    V4- Verify by checking medication logs the participant maintained 48-hour washout.
  EXTRACTED: V4- Verify that a ≥48-hour washout was observed before pain assessments.
  VERDICT: EQUIVALENT — same clinical check (48-hour washout at V4). "By checking
           medication logs" is a data-source detail, not a different requirement. Both
           rules would cause a CRA to verify the same thing.

[PAIR] OPS1
  GOLDEN:    Verify IMP storage logs document ≤ -150°C.
  EXTRACTED: Verify IMP storage logs document ≤ -150°C (or -80°C short-term) in secure area.
  VERDICT: SUPERSET — adds short-term condition and access control

[PAIR] WINDOW
  GOLDEN:    V2- Verify visit occurred within Day 14 ± 3 days.
  EXTRACTED: V2- Verify visit occurred within Day 14 ± 7 days.
  VERDICT: DIVERGENT — factual detail (window tolerance) contradicts

NOW EVALUATE {N} PAIRS. For each pair return:
{
  "golden_kri_id": "...",
  "extracted_kri_id": "...",
  "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT",
  "reason": "one sentence explaining why, referencing Tier 1 and Tier 2",
  "key_difference": "the specific factual detail missing/added/changed, or null if EQUIVALENT"
}

Return ONLY a JSON array of exactly {N} objects.
```

### Phase 3 — Protocol Evidence for Differences

This is the critical new step. For every non-EQUIVALENT pair, go back to the protocol PDF
and find what the protocol actually says. This creates the 3-column comparison the user needs.

**For each non-EQUIVALENT pair**:
1. Parse the `protocol_reference` from both the extracted and golden KRI
2. Read those PDF pages (and any additional pages referenced in footnotes)
3. Determine which version (extracted or golden) is more faithful to the protocol

**Evidence prompt** (batch up to 10 differences per call):
```
You are a clinical trial protocol expert. For each difference below, determine what the
protocol actually says and which version (extracted or golden) is more faithful.

PROTOCOL TEXT:
{relevant_pages_text}

DIFFERENCES TO RESOLVE:
{differences_list_with_extracted_and_golden_rules}

For each difference, return:
{
  "golden_kri_id": "...",
  "extracted_kri_id": "...",
  "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT",
  "extracted_rule": "the extracted rule_for_llm",
  "golden_rule": "the golden rule_for_llm",
  "protocol_says": "What the protocol actually states — include section number, page,
                     and a verbatim quote (≤30 words). If information comes from multiple
                     places, cite all of them.",
  "protocol_references": [
    "Section X.X, Page N: \"verbatim quote\"",
    "Footnote N, Page M: \"verbatim quote\""
  ],
  "more_faithful": "extracted|golden|neither",
  "explanation": "1-2 sentences explaining who is right and what is missing/wrong/added"
}

Return ONLY a JSON array.
```

### Phase 4 — Coverage Gaps

After all categories are judged:
- List golden KRIs with NO extracted match → "Missing from extraction"
- List extracted KRIs with NO golden match → "Extra in extraction"

For each gap, read the relevant protocol pages and note whether the KRI is supported
by the protocol text (i.e., is the golden KRI a real requirement? Is the extra extracted
KRI a valid rule from the protocol?).

### Assembling the comparison report

Merge all per-category results into a single `comparison_report.json`:

```json
{
  "_meta": {
    "protocol_id": "...",
    "golden_set_path": "...",
    "extracted_total": N,
    "golden_total": N,
    "comparison_date": "ISO date"
  },
  "score": {
    "formula": "(EQUIVALENT + SUPERSET + 0.5*SUBSET) / total_golden * 100",
    "value": 85.3,
    "verdict": "PASS|ITERATE|REWORK",
    "thresholds": {"pass": 80, "iterate": 60}
  },
  "summary_by_category": [
    {
      "category": "SOA",
      "golden_count": N,
      "extracted_count": N,
      "equivalent": N,
      "subset": N,
      "superset": N,
      "divergent": N,
      "missing_from_extracted": N,
      "extra_in_extracted": N
    }
  ],
  "differences": [
    {
      "category": "SOA",
      "golden_kri_id": "...",
      "extracted_kri_id": "...",
      "verdict": "SUBSET",
      "extracted_rule": "...",
      "golden_rule": "...",
      "protocol_says": "...",
      "protocol_references": ["Section X, Page N: \"quote\""],
      "more_faithful": "golden",
      "explanation": "Extracted rule omits the data source..."
    }
  ],
  "missing_from_extracted": [
    {
      "golden_kri_id": "...",
      "golden_rule": "...",
      "category": "...",
      "protocol_supported": true,
      "protocol_reference": "Section X, Page N"
    }
  ],
  "extra_in_extracted": [
    {
      "extracted_kri_id": "...",
      "extracted_rule": "...",
      "category": "...",
      "protocol_supported": true,
      "protocol_reference": "Section X, Page N"
    }
  ]
}
```

**Scoring**: `(EQUIVALENT + SUPERSET + 0.5×SUBSET) / total_golden × 100`
- ≥80 → **PASS**
- 60–79 → **ITERATE** (re-extract categories with most SUBSET/DIVERGENT)
- <60 → **REWORK** (re-run full pipeline)

**Save output**: `{out_dir}/comparison_report.json`

### Presenting the report to the user

After saving the JSON, present a human-readable summary:

1. **Overall score** and PASS/ITERATE/REWORK verdict
2. **Per-category table** with verdict counts
3. **Top differences** — show the 3-column view (extracted | golden | protocol says)
   for the most impactful differences (DIVERGENT first, then SUBSET)
4. **Coverage gaps** — missing and extra KRIs with protocol support status
5. **Recommendations** — which categories or specific KRIs to fix if score < 80
