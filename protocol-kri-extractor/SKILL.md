---
name: protocol-kri-extractor
description: >
  Extracts Key Risk Indicators (KRIs) from clinical trial protocol PDFs and
  assembles them into a structured JSON file ready for CRA monitoring agents.
  Use this skill whenever the user wants to: parse a clinical protocol, extract
  rules or guidelines from a protocol PDF, generate KRIs, build a monitoring
  rule set, analyze a protocol document, or compare extracted rules against a
  golden set. Works on any Phase 2/3 trial regardless of sponsor or format
  (ALLOVIVE, Pfizer, Novartis, or any other). Always use this skill when a
  protocol PDF is provided and the user wants structured extraction of any kind.
---

# Protocol KRI Extractor

Extracts monitoring rules (KRIs) from any clinical trial protocol PDF.
Protocol-agnostic: no hardcoded section names, visit labels, or therapeutic areas.

### Target audience (foundational principle)

The extracted KRIs serve **operational and clinical trial professionals only**: sponsor ClinOps, CRAs, CROs, and CRCs. Every KRI must be something these roles would need to verify during site monitoring, subject management, or trial oversight. **Do NOT extract** rules meant purely for biostatisticians, data scientists, or regulatory statisticians (e.g., statistical model specifications, alpha spending, sample size calculations). If a rule is not actionable by a CRA/CRC/ClinOps professional, it does not belong in the KRI set.

### Verifiability requirement (foundational principle)

Every KRI must be **binary-verifiable by a system** — a clear YES/NO check with unambiguous, measurable criteria. Rules that depend on subjective human judgment ("clinically significant", "if appropriate", "per local regulations"), vague time expressions without numeric thresholds ("promptly", "reasonable time"), or effort-based language ("efforts were made") are **not verifiable** and must be separated into the NDEF (Non-Defined) domain. See Quality Rule 16 for the full detection criteria.

## Output schema

Every extracted KRI matches this structure:
```json
{
  "kri_id": "SOA-V1-001",
  "kri_name": "V1- IMP administration",
  "description": "What this KRI monitors and why it matters. For check-in KRIs: MUST state the protocol-specified visit window verbatim (e.g. 'Week 14 ± 3 days').",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V1- Verify that [specific actionable check with exact values, data source, timepoint, and binary condition]. See rule_for_llm writing guide below.",
  "protocol_reference": "Section X.X, Page N: \"verbatim quote ≤30 words\". Multiple sources allowed — see multi-reference rule below.",
  "additional_footnotes": "Footnote N: [verbatim text from protocol] — or null. See footnote rules below.",
  "non_verifiable_reason": "Only present for NDEF KRIs. Explains why the rule is non-verifiable, quoting the problematic phrase from rule_for_llm. — or omitted for all other domains."
}
```

### rule_for_llm writing guide (mandatory)

`rule_for_llm` is a **system instruction for an LLM agent** — not a human-readable summary. The agent will read this field and decide whether a subject is compliant or non-compliant. Write it as a precise, executable binary check.

Every `rule_for_llm` must answer all four of these questions:

1. **WHAT** — What specific data item, field, or fact must be checked?
   *(e.g., "LDL-C value from screening labs", "IMP administration date in eCRF", "SAE report submission timestamp")*

2. **WHERE / FROM WHAT SOURCE** — In which record or system is this data found?
   *(e.g., "in the subject's medication history", "in the eCRF visit date field", "in the lab report", "in the IP accountability log")*

3. **WHEN** — At what timepoint, visit, or relative to what event?
   *(e.g., "at Screening Visit", "within 24 hours of the event", "prior to first IMP dose", "at Visit 8 (Week 14)")*

4. **WHAT CONDITION makes it PASS (YES) or FAIL (NO)** — The binary decision rule, expressed with exact thresholds, comparators, or relationships.
   *(e.g., "is ≥ 70 mg/dL", "falls within ±3 days of the target date", "is absent from medical history", "was completed before IMP administration", "is documented as performed")*

**Examples of correct vs. incorrect `rule_for_llm`**:

| ❌ Too vague | ✅ Correct |
|---|---|
| `"V1 — Verify IMP was administered correctly"` | `"V1 — Verify that the IMP injection date/time (eCRF IMP administration field) falls within the protocol-specified dosing window: 1 day before to 4 days after the target visit date. YES if within window, NO if outside."` |
| `"Verify subject met eligibility"` | `"ELIG-INC — Verify that the subject's LDL-C value documented in the screening lab report is ≥ 70 mg/dL. Timepoint: Screening. Source: lab report. YES if ≥ 70 mg/dL, NO if < 70 mg/dL or missing."` |
| `"SAE must be reported promptly"` | `"SAF-AE — Verify that each SAE was reported to the sponsor within 24 hours of the investigator's first documented awareness. Source: SAE report submission timestamp vs. investigator awareness date in eCRF. YES if ≤ 24h, NO if > 24h."` |
| `"Verify fasting was observed"` | `"SOA-CROSS — Verify that the subject fasted for ≥ 10 hours before blood draw visits (V1, V2, V3, V5, V7, V9) as documented in the eCRF fasting field. Exceptions: CK, LFTs, and pregnancy tests do not require fasting. YES if fasting ≥ 10h documented or procedure is an excepted type, NO if fasting < 10h or field is empty for a required visit."` |

**Do NOT write** `rule_for_llm` as a plain English description of the KRI. It must read as an instruction the system can act on.

### Footnote rules (mandatory)

**Rule F1 — Always verbatim**: `additional_footnotes` must always be copied word-for-word exactly as written in the protocol. No paraphrasing, no summarizing, no rewording. Copy typos, punctuation, and formatting exactly.

**Rule F2 — Short footnotes: copy in full**: If the footnote is of reasonable length and covers one topic, copy the entire footnote verbatim.

**Rule F3 — Long/multi-topic footnotes: extract only the relevant passage**: If a footnote is long and covers multiple unrelated topics (e.g., visit windows, informed consent, fasting rules, and dosing windows all in one footnote), identify the sentence(s) or clause(s) directly relevant to THIS specific KRI's procedure × visit and quote only those — verbatim. If the relevant content is mid-sentence within a longer sentence that also covers irrelevant material, quote the full sentence. Never truncate mid-sentence.

**Rule F4 — Footnote location**: Footnotes can appear anywhere in the SoA section:
- As superscripts in the procedure name column (most common)
- As superscripts on the X marks within cells (e.g. "X¹⁰")
- In the visit column header row
- In a separate footnote legend below the table
All are equally valid. A KRI inherits the footnotes from its procedure row AND from its specific cell (if the X mark itself carries a superscript).

**Rule F5 — Check-in KRI window in description**: Every check-in KRI `description` field MUST state the protocol-specified timing window for that visit. If the window is defined in the table itself, use that. If defined in a footnote, extract the exact relevant sentence from that footnote and state it clearly in the description. Example: *"Verifies that Visit 8 (Week 14) occurred within the allowed window of ±3 days. Protocol: 'Visits 8 (the Week 14 visit), 11 (the Week 52 visit), both which will have visit window of ±3 days'."*

Six categories (universal across all trials — from ICH GCP, not protocol-specific):
- **SOA** — Schedule of Activities
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints & Statistics
- **OPS** — Operations & Compliance
- **NDEF** — Non-Defined KRIs (non-verifiable rules)

---

## How to run

### Step 0 — Setup (first time only)
```bash
pip install pdfplumber pymupdf camelot-py[cv] opencv-python-headless openpyxl --break-system-packages -q
```

### Input required
- Protocol PDF file path
- Output directory (will be created)
- Optional: golden set JSON path (for step 4B comparison)

### Full pipeline command
```bash
python /path/to/scripts/run_pipeline.py \
  --pdf /path/to/protocol.pdf \
  --out /path/to/output/ \
  [--golden /path/to/golden_set.json]
```

Or run steps individually — see **Step-by-step** below.

---

## Step-by-step

Read `references/steps.md` for the detailed prompt templates and logic for each step.

### Phase 1 — Discover

**Step 1A — Manifest**: Read cover pages + TOC. Map every section to SOA/ELIG/SAF/END/OPS.

**Step 1B-Camelot — Table Extraction (PRIMARY)**: Use Camelot (lattice mode) via `scripts/camelot_table_extractor.py` to extract the SoA table into `soa_table.csv` and `soa_table.json`. This is the **PRIMARY** source of truth for the SoA procedure × visit grid. Camelot reads table line geometry from the PDF and gives ~99% structural accuracy — deterministic, reproducible, and not affected by LLM variance. Handles multi-page tables automatically. The CSV and JSON outputs become the canonical SoA data for all downstream steps.

**Step 1B-Vision — Vision Fallback (SECONDARY)**: For cells where Camelot detects the lattice structure but the cell content contains footnote superscripts (e.g., "X¹⁰", "X¹³·¹⁴") that Camelot may read as empty, use Claude Vision at 450 DPI as fallback. Also use multi-pass vision (full + left 55% crop + right 55% crop at 450 DPI) with majority voting for wide tables (>12 columns) to recover any cells Camelot missed. Save conflicts in `multipass_conflicts.json`.

**Step 1B-ColDetect — Column Boundary Detection**: After extraction, run `scripts/vision_table_extractor.py` column detection to verify column boundaries match the Camelot-extracted structure. Flag any discrepancies.

**Step 1B — Ontology**: Build the SoA ontology from the Camelot-extracted table data (verified by vision fallback where needed). Run **Footnote Cross-Validation** as a safety net.

### Phase 2 — Extract (ALL 5 domains in parallel)

All five domains start simultaneously. SOA uses a structured 6-step process anchored on the Camelot table; ELIG/SAF/END/OPS each use a 3-pass extraction process.

**SOA — 6-step structured process**:
1. **Visit mapping**: Pull all visits and their timing from the Camelot CSV. Establish naming conventions (V0, V1, V2... EDC_EOS). From this point forward, use ONLY these canonical names.
2. **Table verification**: Compare the Camelot CSV against the PDF image for verification. Flag any discrepancies. Save `soa_table.csv` and `soa_table.json` as the tracking artifacts.
3. **Check-in KRIs**: For each visit, create ONE check-in KRI verifying the subject attended within the protocol-specified timing window.
4. **Procedure KRIs**: For each visit, create ONE KRI listing ALL procedures required at that visit (in the format: `V1 - procedure name`). Also create one KRI per procedure × visit cell.
5. **Footnote enrichment**: After the table-based KRIs are complete, read all footnotes from the protocol and enrich each KRI with relevant footnote details. Also create **cross-visit rule KRIs** for protocol-wide rules (fasting requirements, dosing windows, 10-day lipid rule, IP administration sequence, missed visit escalation, EDC retention, safety follow-up periods, etc.).
6. **Self-verification**: Cross-check that every X cell in the Camelot CSV has a corresponding KRI. Report: `N/N cells covered = 100%`.

**SOA ordering convention** (mandatory — preserved in final assembly):
The SOA KRI list must be ordered as follows:
1. **Check-in KRIs** — one per visit, in chronological visit order (V0, V1, V2, ... V20, EDC_EOS)
2. **Procedure bundle KRIs** — one per visit, same chronological order
3. **Procedure × Visit KRIs** — grouped **by procedure** (not by visit). Within each procedure group, visits appear in chronological order. The procedure groups follow the row order of the SOA table (e.g., Informed Consent → Contact IRT → Medical History → ... → HCRU Assessment).
4. **Cross-visit / footnote rules** — at the end (SOA-ALL-xxx), for protocol-wide rules not tied to a single procedure × visit cell.

This ordering ensures a CRA can review all visits for one procedure together, rather than jumping between procedures for each visit. The assembly step must preserve this insertion order for SOA (never re-sort SOA KRIs alphabetically by kri_id).

**ELIG / SAF / END / OPS — 3-pass extraction process** (runs in parallel across all 4 domains):

- **Pass A — Primary extraction**: Extract KRIs from sections tagged to this domain in the manifest (`section_map`). Apply full atomization rules: each KRI must represent exactly ONE independently verifiable binary condition (a YES/NO check a CRA can perform without needing to verify anything else simultaneously). Compound conditions must be split. **Target audience filter applies during extraction** — do not extract rules that are not actionable by CRAs/CRCs/ClinOps (see Quality Rule 15). For END specifically: skip pure statistical methodology (model specs, alpha calculations, power analyses, imputation methods) and only extract operationally relevant endpoint rules (what to measure, when, how, response criteria, data collection requirements).
- **Pass B — Cross-sectional sweep**: Read the ENTIRE protocol text (all sections, footnotes, appendices of the same protocol). Find any rule, requirement, or statement relevant to this domain that was NOT already captured in Pass A — including rules buried in sections formally belonging to other domains, in method descriptions, in footnotes, or scattered throughout the document. Extract only net-new KRIs.
- **Pass C — Atomic decomposition**: Review the combined Pass A + B KRI list. Identify any remaining KRI whose `rule_for_llm` contains more than one independently verifiable condition. Split each into atomic KRIs. Output the final domain KRI list.

**Output**: `raw_{CATEGORY}.json` per domain (SOA, ELIG, SAF, END, OPS, and after NDEF filtering: NDEF).

---

### Phase 2.5 — Deduplicate

Runs once, after all 5 domains have completed Phase 2.

**Step D1 — Within-domain deduplication** (4 parallel LLM calls, one per non-SOA domain):
- Input: Pass C output for each domain
- Task: identify clusters of KRIs that check the same underlying clinical condition (even if worded differently). For each cluster, keep the single most complete and specific version. Mark duplicates as removed.
- Two KRIs are duplicates if a CRA would consult the same protocol source and verify the same requirement — not just if they use similar words.
- Output: deduplicated `raw_{CATEGORY}.json` (overwrites Pass C output)

**Step D2 — Cross-domain deduplication** (1 LLM call, all 5 deduplicated lists):
- Input: all 5 deduped domain lists
- Task: find KRIs across different domains that check the same underlying clinical requirement. For each cross-domain duplicate pair/group, assign the KRI to the single most appropriate domain and remove it from the other(s).
- Output: 5 clean domain lists with no inter-domain semantic duplicates (NDEF filtering happens later in Phase 3.5). Save `dedup_report.json` documenting every removal and its reason.

---

### Phase 2.7 — Coverage Audit (Orphan Detection)

Ensures no verifiable protocol rule is left unassigned to any domain.

**Step E1 — Build coverage index**: From all 5 domain KRI lists, extract every section number referenced in `protocol_reference` fields. Build a set of "covered sections." Compare against ALL sections in the TOC (from manifest + full protocol parse).

**Step E2 — Gap classification**: For each TOC section with zero KRI coverage, read its text and classify: `HAS_RULES` (contains at least one verifiable clinical requirement) | `NARRATIVE_ONLY` (background, rationale, introductory text — OK to have no KRIs) | `REFERENCE_ONLY` (cross-references or appendix headers). Only `HAS_RULES` sections proceed to E3.

**Step E3 — Orphan extraction**: For each `HAS_RULES` uncovered section, run a targeted extraction pass with full protocol context. Prompt explicitly shows the existing KRI list and says: "Extract only net-new rules not already covered." Output: `raw_ORPHANS.json`.

**Step E4 — Orphan integration**: Semantic dedup of orphans against all existing KRIs (in case of overlap). Assign each remaining orphan to its most appropriate domain. Merge orphans into the corresponding domain KRI lists. Log all assignments in `orphan_report.json`.

### Phase 3 — Validate (3 independent passes + heuristics)
**Step 3A — Completeness**: Every Camelot CSV cell with "X" must have a KRI.
**Step 3A+ — Clinical Heuristics**: 10 protocol-agnostic heuristics:
- H1-H7: Drug accountability at EOS, pre-questionnaire procedures, ICF at first contact, AE from first dose, concomitant meds at all visits, screening symmetry, vital signs dual measurement.
- **H8 — Edge-Column Footnote Reconciliation**: For procedures in the first/last column, cross-check against footnotes. If a footnote says "at EDC/EOS" but ontology shows V0 (or vice versa), correct it.
- **H9 — Epoch Boundary Plausibility Check**: If a procedure has marks in treatment epoch (V5-V20) but also a single isolated mark in screening (V0/V1), flag it for review. Single marks in a distant epoch are suspicious.
- **H10 — Contiguous Coverage Gap Detection**: For procedures with 5+ visits, check for suspicious holes (>15% gap ratio). Re-verify gaps against the Camelot CSV. Use `detect_contiguous_gaps()` from `scripts/vision_table_extractor.py`.
**Step 3B — Accuracy**: 20 random KRIs re-verified against source pages. Threshold ≥85%.
**Step 3C — Consistency**: Same procedure across visits must have consistent details.

### Phase 3.5 — NDEF Filtering (Non-Verifiable KRI Detection)

Runs after validation, before assembly. Scans ALL KRIs across all 5 operational domains for rules that are not binary-verifiable by a system (see Quality Rule 16 for the full pattern list). Each non-verifiable KRI is:
- **Reclassified** (not duplicated) — removed from its original domain and moved to NDEF
- Tagged with `category_id: "NDEF"`, `category_label: "Non-Defined KRIs"`
- Given a `non_verifiable_reason` field quoting the specific problematic phrase
- Its original `kri_id` is preserved

Output: `raw_NDEF.json` containing all reclassified KRIs. The original domain `raw_*.json` files are updated to exclude the reclassified KRIs. This step does NOT change the total KRI count — it only moves KRIs between domains.

### Phase 4 — Assemble + Compare
**Step 4A — Assembly**: Run `scripts/step4a_assemble.py` to merge all category files (including `raw_NDEF.json`) → `extracted_kris.json` + `Extracted_KRIs.xlsx` (Excel workbook with 6 sheets: SOA, ELIGIBILITY, SAF&TOX, END&STAT, OPS&COM, and NON-DEFINED — blue headers, frozen row 1, wrapped text). The NON-DEFINED sheet includes an extra column: "Non-Verifiable Reason". Sheet assignment uses the `kri_id` prefix for operational domains (SOA/ELIG/SAF/END/OPS) and `category_id == "NDEF"` for the Non-Defined sheet. **Critical**: SOA KRIs must preserve their original insertion order (procedure-grouped, see SOA ordering convention above). Do NOT sort SOA by kri_id alphabetically — this would break the procedure-first grouping into an incorrect visit-first grouping. Other domains may be sorted by kri_id.
**Step 4B — Golden Set Prompt**: After assembly, ask the user if a golden set is available.
**Step 4C — Golden Set Comparison**: Category-by-category LLM comparison with protocol evidence for every difference.
**Step 4D — Comparison Verification**: After Step 4C, run a reconciliation pass. For each "MISSING" verdict, search the extracted KRIs for any KRI whose rule_for_llm contains the same key terms (procedure name + visit prefix). If found, reclassify as EQUIVALENT or SUBSET (false negative in comparison). Also for each "DIVERGENT" verdict, re-read both rules and confirm they truly check different clinical requirements — not just differently worded versions of the same check. Output a `comparison_verified.json` with corrections.

---

## Output artifacts

Each pipeline run produces these files in the output directory:

| File | Description | Source |
|------|-------------|--------|
| `manifest.json` | Protocol metadata and section map | Step 1A |
| `soa_table.csv` | **Canonical SoA matrix** (Camelot) | Step 1B-Camelot |
| `soa_table.json` | SoA matrix + visit-procedure mapping (Camelot) | Step 1B-Camelot |
| `ontology.json` | SoA ontology (visits, procedures, footnotes) | Step 1B |
| `raw_SOA.json` | SOA KRIs (check-in + procedure + cross-visit) | Phase 2 |
| `raw_ELIG.json` | Eligibility KRIs (deduped) | Phase 2.5 |
| `raw_SAF.json` | Safety KRIs (deduped) | Phase 2.5 |
| `raw_END.json` | Endpoint KRIs (deduped) | Phase 2.5 |
| `raw_OPS.json` | Operations KRIs (deduped) | Phase 2.5 |
| `raw_NDEF.json` | Non-Defined KRIs (non-verifiable rules reclassified from all domains) | Phase 3.5 |
| `dedup_report.json` | Log of all within-domain and cross-domain deduplication decisions | Phase 2.5 |
| `raw_ORPHANS.json` | Rules found in uncovered protocol sections | Phase 2.7 |
| `orphan_report.json` | Domain assignment log for each orphan KRI | Phase 2.7 |
| `extracted_kris.json` | All KRIs assembled (all 6 domains, deduplicated, NDEF-filtered) | Step 4A |
| `Extracted_KRIs.xlsx` | Excel workbook (6 sheets: SOA, ELIGIBILITY, SAF&TOX, END&STAT, OPS&COM, NON-DEFINED) | Step 4A |
| `gaps_report.json` | Completeness + heuristic results | Step 3A/3A+ |
| `accuracy_report.json` | 20-KRI accuracy sample | Step 3B |
| `consistency_report.json` | Procedure family consistency | Step 3C |
| `comparison_report.json` | Golden set comparison (if provided) | Step 4C |

---

## Quality rules (apply to every KRI)

1. **Faithfulness**: Use exact drug names, doses, thresholds, timing windows from the protocol. Never generalize ("emergency treatment" → name the drugs).
2. **Data source**: Washout KRIs must say "by checking medication logs and visit timestamps".
3. **Lab panels**: Include all analytes from the protocol footnote — never just "biochemistry panel".
4. **Vitals position**: Use the exact position wording the protocol uses (e.g. "supine position").
5. **Visit prefix**: Every SOA `rule_for_llm` starts with visit code: `V1-`, `S2-`, `All visits-`.
6. **Analysis sets**: Use the protocol's exact definition — ITT ≠ mITT ≠ FAS.
7. **No hallucination**: Every KRI must cite a real section + page. If unsure, omit.
8. **Measurement detail**: Physical assessments must include units, positioning, and preparation when the protocol specifies them (e.g. "weight in kilograms, shoes removed").
9. **Visit window check-in KRI (MANDATORY)**: Every single visit in the SoA table MUST have a dedicated "check-in / within-window" KRI as its FIRST KRI. This includes all screening visits, treatment visits, follow-up visits, and unscheduled visits. The KRI verifies the visit occurred AND fell within the protocol-specified timing window (day reference ± tolerance). The `description` field MUST state the exact protocol-specified window verbatim. Never skip any visit.
10. **Table is truth**: The SoA table (via Camelot CSV) is the single source of truth for which procedures occur at which visits. Footnotes can ADD context (enrichment) but cannot OVERRIDE the table's X marks. If a footnote says "annually" but the table shows X at V10/V13/V16/V19, use the table's visits, not the footnote's interpretation.
11. **Footnotes verbatim**: `additional_footnotes` is always exact protocol text — never a summary or paraphrase. For short/single-topic footnotes: copy in full. For long/multi-topic footnotes: copy only the sentence(s) relevant to this specific KRI, but never truncate mid-sentence. See Footnote Rules F1–F5 above.
12. **rule_for_llm is a system instruction**: The `rule_for_llm` field must be written as a precise, binary, executable check for an LLM agent — specifying WHAT data to check, WHERE it comes from, WHEN (timepoint/visit), and WHAT binary condition determines pass/fail. Never write it as a prose description of the KRI. See rule_for_llm writing guide above.
13. **SOA cross-visit scope accuracy**: When creating KRIs for rules that apply to multiple visits (from footnotes, cross-sectional sweep, or other protocol sections), name and describe the KRI to reflect the EXACT scope stated in the source. Do NOT label a KRI as "All Visits" if the rule applies only to a subset of visits — state the exact visits or visit types (e.g. "Dosing Visits V1, V2, V3, V5" or "Visits with blood draws"). If a cross-visit rule has multiple source references in the protocol, list ALL of them in `protocol_reference` with their exact citations.
14. **Multiple protocol references**: If a KRI's rule is supported by more than one location in the protocol (e.g. stated in a footnote AND cross-referenced in the procedure section), include all references. Format: `"Section X.X, Page N: \"quote\"; Footnote Y, Page M: \"quote\""`. Never collapse multiple sources into one or omit secondary references.
15. **Target audience filter**: The extracted KRIs serve operational and clinical trial professionals: sponsor ClinOps, CRAs, CROs, and CRCs. KRIs must be actionable by these roles. Do NOT extract KRIs for:
    - Pure statistical methodology (alpha calculations, Type I error rates, significance levels, multiplicity adjustments)
    - Sample size / power calculations
    - Statistical analysis methods (ANCOVA, MMRM, regression methodology details)
    - Proportion/percentage calculation formulas
    - Sensitivity analysis methodology
    - Missing data imputation methodology
    - Subgroup analysis statistical methodology
    - Confidence interval calculation methods

    DO extract endpoint KRIs that ARE operationally relevant:
    - Primary/secondary endpoint definitions (what to measure, when, how)
    - Endpoint collection procedures and timing
    - Response criteria definitions that affect clinical decisions
    - Discontinuation/withdrawal rules tied to endpoint thresholds
    - Data collection requirements, eCRF completion rules, query resolution timelines

    In the END domain, only include rules that a CRA, CRC, or ClinOps professional would need to verify during monitoring or site management. Anything meant purely for biostatisticians analyzing the trial data should be excluded.
16. **Non-verifiable KRI detection (NDEF domain)**: After extraction and deduplication, scan ALL KRIs across all domains for rules that are NOT binary-verifiable by a system. A KRI is non-verifiable if its `rule_for_llm` meets any of these criteria:
    - References subjective judgment ("clinical judgment", "investigator discretion", "medical opinion", "as needed", "if appropriate", "as deemed necessary")
    - Uses vague/unmeasurable time expressions ("reasonable time", "promptly", "as soon as possible", "timely manner") WITHOUT specific numeric thresholds
    - Uses effort-based language ("efforts were made", "attempt to", "try to", "encourage")
    - References unmeasurable conditions ("adequate", "sufficient", "appropriate", "significant", "excessive", "reasonable")
    - Depends on external undefined criteria ("per local regulations", "per institutional policy", "per standard practice") where the specific requirement varies by site
    - Contains conditional logic that can't be system-checked ("if clinically indicated", "if medically necessary", "based on clinical assessment")

    Non-verifiable KRIs are moved to a 6th domain called **NDEF** (Non-Defined KRIs):
    - `category_id`: "NDEF"
    - `category_label`: "Non-Defined KRIs"
    - Each NDEF KRI gets an additional field: `non_verifiable_reason` — a specific explanation of why the rule is non-verifiable, quoting the problematic phrase from the `rule_for_llm`.
    - The original `kri_id` is preserved (not renamed).

---

## Comparing against a golden set

After Step 4A assembly completes, **always ask the user**:
> "Do you have a golden set to compare against? You can provide a file path or upload it."

If the user provides a golden set, run Step 4C (see `references/steps.md` for full details).

### How comparison works

**Phase 1 — Matching**: For each category (SOA, ELIG, SAF, END, OPS, NDEF) separately, match extracted KRIs to golden KRIs using semantic similarity (not just ID matching). Handle 1:many and many:1 splits.

**Phase 2 — Two-tier semantic judging**: LLM evaluates each pair using two criteria:

**Tier 1 — Semantic coverage (lenient)**: Does the extracted KRI check the SAME clinical requirement? If yes, differences in phrasing, sentence structure, verbosity, or explanatory context are IRRELEVANT. Focus on WHAT is verified, not HOW the sentence reads.

**Tier 2 — Factual precision (strict)**: When either rule contains specific protocol facts — numeric thresholds, visit windows (±days), drug names & doses, named instruments/scales, washout durations, specific methods (e.g. "ultrasound-guided") — those facts MUST be accurate and present. Wording around them doesn't matter, but the facts themselves do.

Verdicts:
- **EQUIVALENT** — same clinical check (Tier 1 pass), factual details consistent or both absent (Tier 2 pass). Phrasing/wording differences are irrelevant.
- **SUBSET** — same check but extracted OMITS a specific factual detail that the golden includes.
- **SUPERSET** — same check but extracted ADDS factual detail from the protocol beyond what golden includes.
- **DIVERGENT** — different clinical requirement (Tier 1 fail), OR factual details contradict each other.

**Phase 3 — Protocol evidence**: For every non-EQUIVALENT pair, read the cited protocol pages and show a 3-column comparison.

**Phase 4 — Coverage gaps**: Identify golden KRIs with no extracted match and extracted KRIs with no golden match.

### Comparison report structure

The final `comparison_report.json` contains:
- **Score**: `(EQUIVALENT + SUPERSET + 0.5*SUBSET) / total_golden * 100`
  - >=80 → PASS | 60-79 → ITERATE | <60 → REWORK
- **Per-category breakdown** with counts per verdict
- **Differences table**: every non-EQUIVALENT pair with extracted rule, golden rule, protocol evidence
- **Missing from extracted**: golden KRIs with no match
- **Extra in extracted**: extracted KRIs with no golden match

---

## Reference files

- `references/steps.md` — detailed LLM prompt templates for each step
- `references/kri_examples.md` — annotated KRI examples per category
- `scripts/camelot_table_extractor.py` — Camelot-based table extraction (PRIMARY for SoA)
- `scripts/vision_table_extractor.py` — Vision-based extraction + multi-pass + Heuristic 10
- `scripts/step4a_assemble.py` — Assembly + Excel generation (no LLM needed)
