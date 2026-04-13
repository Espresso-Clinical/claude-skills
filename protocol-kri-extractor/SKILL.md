---
name: protocol-kri-extractor
description: >
  Extracts Key Risk Indicators (KRIs) from clinical trial protocol PDFs and
  produces the authoritative Golden Set — the definitive, verified, structured
  list of monitoring rules for a given protocol. Use this skill whenever the user
  wants to: parse a clinical protocol, extract rules or guidelines from a protocol
  PDF, generate KRIs, or build a monitoring rule set. Works on any Phase 2/3 trial
  regardless of sponsor or format (ALLOVIVE, Pfizer, Novartis, or any other).
  Always use this skill when a protocol PDF is provided and the user wants
  structured extraction of any kind.
---

# Protocol KRI Extractor

## Ultimate Goal

This skill **creates the Golden Set** — the authoritative, verified collection of KRIs for a given clinical trial protocol. The Golden Set is the primary deliverable. It is not a comparison tool, a validation tool, or a QC tool against a pre-existing set. The skill itself, working from the protocol PDF alone, produces the ground-truth KRI list that becomes the standard for that protocol.

The output (`golden_set.json` + `Extracted_KRIs.xlsx`) is the source of truth — not derived from any prior set and not judged against any prior set.

---

Extracts monitoring rules (KRIs) from any clinical trial protocol PDF.
Protocol-agnostic: no hardcoded section names, visit labels, or therapeutic areas.

---

## ⚠️ META-RULE — Skill Updates Are Additive Only (NEVER violate this)

Every refinement, update, or improvement to this skill is **additive**. It adds to what is already defined. It never removes, overwrites, or silently replaces previous rules.

- **Never delete** a rule that was not explicitly requested to be deleted
- **Never overwrite** a previous definition unless the user explicitly said "replace this"
- When in doubt: **add** the new rule alongside the old one, clearly labeled
- If a new rule contradicts an old rule, **surface the conflict** to the user — do not silently resolve it by deleting one side
- De-duplication, orphan scan, NDEF classification, verbatim verification, and all other steps documented here remain in force forever unless explicitly removed
- When presenting "new" ideas to the user, check first whether they are already documented here — do not re-propose things that already exist in the skill

This rule applies to Claude when editing this file, and to the skill pipeline itself when producing KRIs.

---

## Output schema

Every extracted KRI matches this structure:
```json
{
  "kri_id": "SOA-V1-001",
  "kri_name": "V1- IMP administration",
  "description": "What this KRI monitors and why it matters",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V1- Verify that [specific actionable check with exact values]",
  "protocol_reference": "Section X.X, p.N",
  "supporting_quote": "Verbatim text from the protocol page ≤30 words",
  "combined_ref": "Section X.X, p.N — \"Verbatim text from the protocol page\"",
  "additional_footnotes": "Footnote N: verbatim text — or null",
  "severity": "critical|major|minor"
}
```

**Field rules — read carefully:**
- `protocol_reference` — section label + page number only (e.g. `"Section 4.4.1, p.65"`). **No embedded quote inside this field.**
- `supporting_quote` — verbatim text ≤30 words copied exactly from the PDF page. **NEVER wrap in outer double quotes** — do not start or end with `"`. The `combined_ref` field adds its own quotes. No leading or trailing `"` character.
- `combined_ref` — always computed as: `f'{protocol_reference} — "{supporting_quote}"'` (em dash `—`, not hyphen `-`). This is the **single field** used in the Excel "Protocol Reference & Quote" column. Never split it into two columns.
- `additional_footnotes` — null if no relevant footnote, otherwise verbatim footnote text.
- `severity` — **critical**: primary endpoint, analysis population, primary analysis model, multiplicity control, interim analysis rules. **major**: secondary endpoints, biomarker endpoints, supplemental analysis methods, baseline definitions. **minor**: exploratory endpoints, HCRU endpoints, administrative governance rules.
- **SOA table/footnote page reference rule**: For SOA KRIs derived from the SoA table or its footnotes, `protocol_reference` must use the **full page range** covering the table AND all footnote pages (e.g., `"Schedule of Activities, Footnote 4, p.24-p.29"`). Do NOT cite individual pages within the table section. Do NOT add a "Section X.X" prefix if the SoA table has no section number — just use `"Schedule of Activities"`. Only SOA KRIs whose content comes from protocol TEXT outside the table (e.g., dosing instructions from Section 5.4) should have a specific section + page reference.
- **No fabricated section numbers for SOA table**: If the SoA table in the protocol has no section number (many protocols just have it as a standalone table), do not invent one. Use `"Schedule of Activities"` as the reference label.

## CRITICAL — Atomicity Principle (applies to ALL domains)

**Every KRI must be atomic.** A single KRI must represent exactly ONE verifiable check about ONE thing at ONE time point in ONE clinical context. Never combine multiple rules, multiple endpoints, multiple procedures, multiple time points, or multiple clinical settings into a single KRI.

Examples of atomicity violations (WRONG):
- "Verify LDL-C, Non-HDL-C, Apo B, and triglycerides percent change at Week 14" → Must be 4 separate KRIs, one per analyte
- "Verify vital signs and laboratory assessment at V3" → Must be 2 separate KRIs
- "Verify key secondary endpoints are composite of CV death, MI, stroke, and UA" → Must be one KRI per distinct composite endpoint definition

Examples of correct atomicity:
- "Verify that the percent change from baseline in LDL-C (direct measurement) is calculated at Week 14 (Visit 8)"
- "Verify that vital signs were measured at V3"
- "Verify that the key secondary endpoint is calculated as time from randomization to the first occurrence of a composite of CV death, non-fatal MI, and non-fatal stroke"

**This applies across all domains:** SOA (one procedure × one visit = one KRI), ELIG (one criterion or sub-criterion = one KRI), SAF (one reporting rule or one stopping rule = one KRI), END (one endpoint definition or one statistical method = one KRI), OPS (one operational rule = one KRI).

Six categories (universal across all trials — from ICH GCP):
- **SOA** — Schedule of Activities
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints, Statistics & Governance (see detailed sub-categories below)
- **OPS** — Operations & Compliance
- **NDEF** — Non-Definable: eligibility criteria or rules based on investigator clinical judgment that cannot be expressed as a binary verifiable rule. Rule format: `"NDEF — Non-verifiable: [reason why LLM cannot verify]"`. These are documented so auditors know the criterion exists but flagged as out-of-scope for automated monitoring.

---

## CRITICAL — Domain Boundary Rules (prevents cross-domain duplicates)

### Rule 1 — SOA owns all "procedure happened at visit" checks

If a KRI is essentially **"Verify that [procedure] was performed at [visit]"** — it belongs in **SOA only**. Never in SAF or OPS.

This means:
- Lab timing ("hepatitis B and C collected at Visit 1") → **SOA**, not SAF
- Visit window ("V0 to V1 maximum 30 days") → **SOA** check-in KRI, not OPS
- Contraception check at designated visits → **SOA** procedure KRI, not SAF
- IRT registration at every visit → **SOA** Contact IRT KRI, not OPS
- HbA1c collected at baseline/V11/EDC → **SOA** procedure KRI, not SAF
- Plasma biospecimen collection at V5/V11 → **SOA** procedure KRI, not SAF
- Lipid profile not collected at EDC/EOS → **SOA** footnote rule, not SAF
- EOS visit no sooner than 14 days after last dose → **SOA-CROSS**, not SAF

**Red-flag test**: If a KRI's `rule_for_llm` contains the phrase "per SOA", "per schedule", "per the SoA table", or "at [visit name]" and is describing THAT something was done — it belongs in SOA. Delete the SAF or OPS version.

### Rule 2 — SAF owns safety thresholds, reporting obligations, and clinical responses

SAF **only** contains KRIs that are about:
- (a) **Numeric safety thresholds and what to do when exceeded** (CK >5× ULN → stop IP; TG ≥600 mg/dL → unscheduled visit; AST/ALT ≥3× ULN → DILI workup)
- (b) **AE/SAE collection windows and reporting timelines** (report within 24h/48h; collect from first dose to 40 days post-last-dose)
- (c) **Stopping rules and IP discontinuation triggers**
- (d) **Emergency protocols and rescue medication** (specific drugs, doses, routes)
- (e) **Causality assessment requirements** (AE causality, pregnancy outcome follow-up)
- (f) **Dose modification rules** (IP frequency change triggers and consequences)

SAF does **NOT** contain:
- ✗ How to perform a measurement (position, technique, timing within a visit) → **OPS**
- ✗ Equipment standardization (same cuff, calibrated device, same arm) → **OPS**
- ✗ When/whether a procedure occurs at a specific visit → **SOA**
- ✗ Sample tube type or processing technique → **OPS**

**Example of the error to avoid**: The protocol describes BP methodology and vital signs positioning in its "Safety Assessments" section. Those rules are in the safety section but are not about safety thresholds — they belong in OPS. Do not use "found in safety section of protocol" as the criterion for SAF.

### Rule 3 — OPS owns technique, methodology, and standardization

OPS contains:
- **How to perform assessments**: measurement position (sitting, arm supported), measurement duration (30 seconds), equipment type (same calibrated cuff)
- **Longitudinal standardization**: same arm throughout study, same scale, same position
- **Sample handling**: tube type, processing steps, shipping conditions
- **IP storage, handling, dispensing, accountability**
- **Documentation and records**: CRF corrections, consent documentation, delegation logs
- **Regulatory compliance**: IRB approvals, inspection notifications, record retention

### Rule 4 — NDEF for investigator-judgment rules that an LLM cannot verify

NDEF includes any rule where compliance depends on real-time clinical judgment by the investigator, such as:
- Emergency unblinding decisions (investigator determines medical necessity)
- Causality determinations for immediate-notification AE rules ("immediately notify if clinically significant" — the determination of "clinically significant" is judgment-based)
- Any exclusion criterion framed as "in the investigator's opinion" that has no objective measurable proxy

---

## CRITICAL — Cross-Domain De-duplication (mandatory after all domains extracted)

After Step 4A assembly, run a **cross-domain dedup pass** before finalizing:

**Step 4A-Dedup — Cross-Domain Duplicate Detection**

1. For each KRI in SAF and OPS, check: does a SOA KRI already cover this same clinical check?
   - If a SAF KRI checks "that [lab] was collected at [visit]" and a SOA KRI for that procedure × visit exists → **delete the SAF KRI** (SOA owns it)
   - If an OPS KRI checks "visit window for V[N]" and a SOA-CHECKIN-V[N] KRI exists → **delete the OPS KRI** (SOA owns it)
   - If an OPS KRI checks "IRT registered at every visit" and SOA Contact IRT KRIs exist → **delete the OPS KRI**

2. Within each domain, check for semantic duplicates: two KRIs with different IDs but the same essential `rule_for_llm` → keep the one with the richer description, delete the other.

3. **Ownership hierarchy** (when same rule appears in multiple domains, this domain wins):

   | Rule type | Owner | Delete from |
   |---|---|---|
   | Procedure happened at visit | SOA | SAF, OPS |
   | Visit timing / window | SOA | OPS |
   | Safety threshold + response | SAF | OPS |
   | Measurement technique | OPS | SAF |
   | Scheduling coordination rule (e.g. postpone test X with test Y) | SOA-CROSS | SAF, OPS |

4. Log all deletions in `{out_dir}/crossdomain_dedup_report.json` with: deleted KRI ID, duplicate of KRI ID, reason.

---

### END Domain — Three Mandatory Sub-Categories

The END domain must produce KRIs in three sub-categories. All use `category_id: "END"` and `category_label: "Endpoints & Statistics"`.

**Sub-category 1 — Endpoint Definitions (ID prefix: `END-`)**
One KRI per protocol-defined endpoint. Every endpoint listed in the protocol's objectives section gets its own KRI:
- **Primary endpoint**: exact composite definition, time-from-randomization, adjudication requirement. Severity: critical.
- **Each key secondary endpoint separately**: even if they share a section header, each distinct composite or individual endpoint is a separate KRI. Severity: critical.
- **Each other secondary/clinical endpoint separately**: CV death, any MI, fatal MI, non-fatal MI, any stroke, fatal stroke, non-fatal stroke, hospitalization for UA, hospitalization for CHF, any coronary revascularization, CABG, PCI, any arterial revascularization, all-cause death — each one a separate KRI. Severity: major.
- **Each biomarker endpoint separately**: LDL-C percent change Week 14, LDL-C nominal change Week 14, LDL-C percent change last available, Non-HDL-C, Total cholesterol, VLDL-C, RLP-C, Apo B, Lp(a), Triglycerides, HDL-C, Apo A-I, hs-CRP — each analyte × each measurement type = one KRI. Severity: major.
- **Each HCRU endpoint separately**: all-cause hospitalizations, CV hospitalizations, ER visits, physician office visits, outpatient rehab visits, 30-day readmissions — each one a separate KRI. Severity: minor.

**Sub-category 2 — Statistical Methods (ID prefix: `STAT-`)**
One KRI per analysis method specified in the protocol's statistical section:
- **Primary analysis model**: test type (log rank), stratification factors, exact two-sided alpha after adjustments. Severity: critical.
- **Hazard ratio estimation model**: Cox proportional hazards, covariates, stratification factors, confidence interval, convergence fallback. Severity: critical.
- **Multiplicity control**: gatekeeping procedure, fixed sequence testing, alpha allocation, experimentwise Type 1 error control. Severity: critical.
- **Missing data handling**: imputation method (e.g. multiple imputations for informative censoring), which subjects (e.g. withdrew consent before cutoff), conservative approach (e.g. imputation from placebo only). Severity: major.
- **Supplemental analyses**: recurrent events method (e.g. Wei-Lin-Weissfeld), adherent subject analysis with exact criteria (treatment duration, LDL-C threshold, additional covariates). Severity: major.
- **Biomarker analysis model**: MMRM with all fixed effects listed, covariance structure, estimation method (REML). Severity: major.
- **Data transformations**: which analytes are log-transformed, zero-value replacement. Severity: major.
- **Baseline definitions**: exact calculation method (e.g. mean of last two non-missing values prior to randomization). Severity: major.

**Sub-category 3 — Governance (ID prefix: `GOV-`)**
One KRI per trial governance rule:
- **Analysis population definitions**: Full Analysis Set (FAS) exact inclusion criteria, Safety Analysis Set (SAS) exact inclusion criteria, any other analysis sets. Severity: critical.
- **Interim analysis trigger**: exact event count thresholds, which endpoints must be met, percentage requirements. Severity: critical.
- **Alpha spending**: method name (e.g. Heybittle-Peto), exact alpha value, adjustment to final analysis alpha. Severity: critical.
- **Study end/completion definition**: event count target, time-based criterion, whichever-occurs-later logic. Severity: major.

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

**Step 1A — Manifest**: Read cover pages + TOC. Map every section to SOA/ELIG/SAF/END/OPS/NDEF.

**Step 1B-Camelot — Table Extraction (PRIMARY)**: Use Camelot (lattice mode) via `scripts/camelot_table_extractor.py` to extract the SoA table into `soa_table.csv` and `soa_table.json`. This is the **PRIMARY** source of truth for the SoA procedure × visit grid. Camelot reads table line geometry from the PDF and gives ~99% structural accuracy — deterministic, reproducible, and not affected by LLM variance. Handles multi-page tables automatically. The CSV and JSON outputs become the canonical SoA data for all downstream steps.

**Step 1B-Vision — Vision Fallback (SECONDARY)**: For cells where Camelot detects the lattice structure but the cell content contains footnote superscripts (e.g., "X¹⁰", "X¹³·¹⁴") that Camelot may read as empty, use Claude Vision at 450 DPI as fallback. Also use multi-pass vision (full + left 55% crop + right 55% crop at 450 DPI) with majority voting for wide tables (>12 columns) to recover any cells Camelot missed. Save conflicts in `multipass_conflicts.json`.

**Step 1B-ColDetect — Column Boundary Detection**: After extraction, run `scripts/vision_table_extractor.py` column detection to verify column boundaries match the Camelot-extracted structure. Flag any discrepancies.

**Step 1B — Ontology**: Build the SoA ontology from the Camelot-extracted table data (verified by vision fallback where needed). Run **Footnote Cross-Validation** as a safety net.

**Step 1C — Deterministic Footnote Mapping (MANDATORY)**: Run `scripts/footnote_mapper.py` to build a fully deterministic map of which footnotes belong to which procedure × visit cells. This uses PDF character geometry (font size detection for superscripts) and Camelot cell text parsing — **zero LLM calls**. The output `footnote_map.json` becomes the single source of truth for all footnote associations in SOA KRI generation. The LLM never guesses which footnotes apply — it receives the pre-computed map.

### Phase 2 — Extract (6-Step SOA Process)

The SOA extraction follows a strict 6-step process:

1. **Visit mapping**: Pull all visits and their timing from the Camelot CSV. Establish naming conventions (V0, V1, V2... EDC_EOS). From this point forward, use ONLY these canonical names.
2. **Table verification**: Compare the Camelot CSV against the PDF image for verification. Flag any discrepancies. Save `soa_table.csv` and `soa_table.json` as the tracking artifacts.
3. **Check-in KRIs**: For each visit, create ONE check-in KRI verifying the subject attended within the protocol-specified timing window.
4. **Procedure KRIs**: For each visit, create ONE KRI listing ALL procedures required at that visit (in the format: `V1 - procedure name`). Also create one KRI per procedure × visit cell.
5. **Footnote enrichment**: After the table-based KRIs are complete, read all footnotes from the protocol and enrich each KRI with relevant footnote details. Also create **cross-visit rule KRIs** for protocol-wide rules (fasting requirements, dosing windows, 10-day lipid rule, IP administration sequence, missed visit escalation, EDC retention, safety follow-up periods, etc.).
6. **Self-verification**: Cross-check that every X cell in the Camelot CSV has a corresponding KRI. Report: `N/N cells covered = 100%`.

For non-SOA categories, extraction uses one LLM call per category producing `raw_{CAT}.json`:
- ELIG: one KRI per criterion/sub-criterion; criteria based on pure investigator judgment → NDEF
- SAF: every reporting timeline, stopping rule, emergency protocol
- END: **three sub-categories** — (1) one KRI per endpoint definition (primary, each key secondary, each other secondary individually, each biomarker analyte × measurement type, each HCRU metric), (2) one KRI per statistical method (primary model, hazard ratio model, multiplicity control, missing data, supplemental analyses, biomarker model, transformations, baseline definitions), (3) one KRI per governance rule (analysis populations, interim analysis triggers, alpha spending, study end definition)
- OPS: IMP handling, blinding, records, compliance

### Phase 3 — Validate (3 passes + heuristics + mandatory full verification)

**Step 3A — Completeness**: Every Camelot CSV cell with "X" must have a KRI.

**Step 3A+ — Clinical Heuristics**: 10 protocol-agnostic heuristics:
- H1-H7: Drug accountability at EOS, pre-questionnaire procedures, ICF at first contact, AE from first dose, concomitant meds at all visits, screening symmetry, vital signs dual measurement.
- **H8 — Edge-Column Footnote Reconciliation**: For procedures in the first/last column, cross-check against footnotes. If a footnote says "at EDC/EOS" but ontology shows V0 (or vice versa), correct it.
- **H9 — Epoch Boundary Plausibility Check**: If a procedure has marks in treatment epoch (V5-V20) but also a single isolated mark in screening (V0/V1), flag it for review. Single marks in a distant epoch are suspicious.
- **H10 — Contiguous Coverage Gap Detection**: For procedures with 5+ visits, check for suspicious holes (>15% gap ratio). Re-verify gaps against the Camelot CSV. Use `detect_contiguous_gaps()` from `scripts/vision_table_extractor.py`.

**Step 3B — Clinical Quality Review**: Sample 20 KRIs (4 per category), re-read their source pages, verify clinical faithfulness and factual completeness. Threshold ≥85% CORRECT. This step checks whether the **content** of rules is clinically accurate — it does NOT substitute for Step 3D quote verification.

**Step 3C — Consistency**: Same procedure across visits must have consistent details.

**Step 3D — Full Verbatim Verification (MANDATORY BLOCKING GATE)**: Run `scripts/step3d_verify.py` against the PDF to verify every single KRI's `supporting_quote` is a verbatim substring of the cited page text. **The pipeline cannot advance to Step 4A until this step reports 100% pass.** See details below.

### Phase 4 — Assemble + Compare
**Step 4A — Assembly**: Run `scripts/step4a_assemble.py` to merge all category files → `extracted_kris.json` + `Extracted_KRIs.xlsx`. The Excel workbook has one sheet per domain (SOA, ELIG, SAF, END, OPS, NDEF) plus a Summary sheet. **Exact column structure — no deviations:**

| Column | Field | Width |
|--------|-------|-------|
| KRI ID | `kri_id` | 16 |
| Category | `category_label` | 28 |
| KRI Name | `kri_name` | 34 |
| Description | `description` | 52 |
| Rule for LLM | `rule_for_llm` | 60 |
| Protocol Reference & Quote | `combined_ref` | 90 |
| Severity | `severity` | 12 |

No "Domain" column. No separate "Protocol Reference" column. No separate "Supporting Quote" column. The `combined_ref` field is the single source for the reference column.

**Step 4B — Golden Set Prompt**: After assembly, ask the user if a golden set is available.
**Step 4C — Golden Set Comparison**: Category-by-category LLM comparison with protocol evidence for every difference.
**Step 4D — Comparison Verification**: After Step 4C, run a reconciliation pass. For each "MISSING" verdict, search the extracted KRIs for any KRI whose rule_for_llm contains the same key terms (procedure name + visit prefix). If found, reclassify as EQUIVALENT or SUBSET (false negative in comparison). Also for each "DIVERGENT" verdict, re-read both rules and confirm they truly check different clinical requirements — not just differently worded versions of the same check. Output a `comparison_verified.json` with corrections.

---

## Step 3D — Full Verbatim Verification (details)

Run `scripts/step3d_verify.py --pdf /path/to/protocol.pdf --json /path/to/extracted_kris.json`.

**How it works:**
```python
import pdfplumber, re, json, shutil, pathlib

def norm(t):
    return re.sub(r'\s+', ' ', t).strip()

def verify_all(pdf_path, json_path):
    with open(json_path) as f:
        data = json.load(f)
    kris = data.get('kris', data) if isinstance(data, dict) else data

    # Cache all pages in one PDF open
    page_cache = {}
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        for pg in range(1, n+1):
            page_cache[pg] = pdf.pages[pg-1].extract_text() or ''

    results = {'pass': [], 'fail': [], 'auto_corrected': []}

    for k in kris:
        kid = k['kri_id']
        q   = k.get('supporting_quote', '')
        ref = k.get('protocol_reference', '')

        # Strip any outer quotes that slipped through (should not exist, but safety net)
        if q.startswith('"') and q.endswith('"') and len(q) > 1:
            q = q[1:-1]
        if q.startswith('"'):
            q = q.lstrip('"')

        # Extract cited page(s) — handle ranges like p.24-p.29
        m_range = re.search(r'p\.(\d+)-p\.(\d+)', ref)
        m_single = re.search(r'p\.(\d+)', ref)
        if m_range:
            pg_start, pg_end = int(m_range.group(1)), int(m_range.group(2))
        elif m_single:
            pg_start = pg_end = int(m_single.group(1))
        else:
            results['fail'].append({'kri_id': kid, 'reason': 'NO_PAGE_IN_REF'})
            continue

        # Search cited page range ± 2 pages
        found_pg = None
        for p2 in range(max(1, pg_start-2), min(n, pg_end+2)+1):
            if norm(q) in norm(page_cache.get(p2, '')):
                found_pg = p2
                break

        if found_pg is None:
            results['fail'].append({'kri_id': kid, 'cited_pg': cited_pg, 'quote': q[:80]})
        elif found_pg != cited_pg:
            # Auto-correct the page reference
            new_ref = re.sub(r'\bp\.' + str(cited_pg) + r'\b', f'p.{found_pg}', ref)
            k['protocol_reference'] = new_ref
            k['combined_ref'] = f'{new_ref} — "{q}"'
            k['supporting_quote'] = q
            results['auto_corrected'].append({'kri_id': kid, 'old_pg': cited_pg, 'new_pg': found_pg})
            results['pass'].append(kid)
        else:
            k['supporting_quote'] = q  # ensure stripped version is saved
            k['combined_ref'] = f'{ref} — "{q}"'
            results['pass'].append(kid)

    # Save corrected JSON (with backup)
    backup = pathlib.Path(json_path).with_suffix('.pre_verify.json')
    shutil.copy(json_path, backup)
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    total = len(kris)
    print(f"PASS: {len(results['pass'])}/{total}")
    print(f"AUTO-CORRECTED: {len(results['auto_corrected'])}")
    print(f"FAIL: {len(results['fail'])}")
    if results['fail']:
        print("\\nFailing KRIs (must fix manually before Step 4A):")
        for f in results['fail']:
            print(f"  {f}")
    return results
```

**Known PDF quirks to handle:**
- pdfplumber drops spaces in some PDFs (e.g., "Everyeffort" instead of "Every effort"). If `norm(q)` fails, try shortening the quote to a segment that doesn't cross a word-boundary drop.
- Curly apostrophes in PDFs: `\u2019` (`'`) vs straight `\u0027` (`'`). The quote must match the PDF's actual character.
- Two-column table pages: pdfplumber interleaves column text line-by-line. Test quotes on these pages carefully.

**Pipeline gate**: If `results['fail']` is non-empty after Step 3D, **stop the pipeline**. Fix each failing KRI manually (correct the page reference or the quote), then re-run Step 3D until 0 failures. Only then proceed to Step 4A.

---

## Output artifacts

Each pipeline run produces these files in the output directory:

| File | Description | Source |
|------|-------------|--------|
| `manifest.json` | Protocol metadata and section map | Step 1A |
| `soa_table.csv` | **Canonical SoA matrix** (Camelot) | Step 1B-Camelot |
| `soa_table.json` | SoA matrix + visit-procedure mapping (Camelot) | Step 1B-Camelot |
| `ontology.json` | SoA ontology (visits, procedures, footnotes) | Step 1B |
| `footnote_map.json` | **Deterministic footnote-to-cell mapping** (single source of truth) | Step 1C |
| `raw_SOA.json` | SOA KRIs (check-in + procedure + cross-visit) | Step 2 |
| `raw_ELIG.json` | Eligibility KRIs | Step 2 |
| `raw_SAF.json` | Safety KRIs | Step 2 |
| `raw_END.json` | Endpoint KRIs | Step 2 |
| `raw_OPS.json` | Operations KRIs | Step 2 |
| `raw_NDEF.json` | Non-Definable KRIs | Step 2 |
| `extracted_kris.json` | All KRIs assembled | Step 4A |
| `Extracted_KRIs.xlsx` | Excel workbook (6 domain sheets + Summary) | Step 4A |
| `gaps_report.json` | Completeness + heuristic results | Step 3A/3A+ |
| `accuracy_report.json` | 20-KRI clinical quality sample | Step 3B |
| `consistency_report.json` | Procedure family consistency | Step 3C |
| `verify_report.json` | Full verbatim verification results | Step 3D |
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
9. **Visit window check-in KRI (MANDATORY)**: Every single visit in the SoA table MUST have a dedicated "check-in / within-window" KRI as its FIRST KRI. This includes all screening visits, treatment visits, follow-up visits, and unscheduled visits. The KRI verifies the visit occurred AND fell within the protocol-specified timing window (day reference ± tolerance). Never skip any visit.
10. **Table is truth**: The SoA table (via Camelot CSV) is the single source of truth for which procedures occur at which visits. Footnotes can ADD context (enrichment) but cannot OVERRIDE the table's X marks. If a footnote says "annually" but the table shows X at V10/V13/V16/V19, use the table's visits, not the footnote's interpretation.
11. **No outer quotes in supporting_quote**: The `supporting_quote` field must never begin or end with a `"` character. The `combined_ref` field adds its own surrounding quotes.
12. **No duplicate page numbers**: Never produce `"p.27, p.27"` or `"Page 27, p.27"`. Exactly one page reference per KRI.
13. **No footnote number prefix in quotes**: Raw PDF has `"13 Urinalysis..."` — the `13` is a label, not content. Strip it. Quote starts with the text: `"Urinalysis: Dipstick..."`.
14. **Script safety — always save**: Every script that modifies JSON must: (a) create a backup, (b) `json.dump(..., ensure_ascii=False)`, (c) print confirmation with record count.
15. **Footnote associations are deterministic**: They come from `footnote_map.json` (Step 1C), NEVER from LLM inference. If the map says Vital Signs = Footnote 4, the KRI cites Footnote 4. Period.

### SOA Domain — Reference and Quote Rules (MANDATORY, NO EXCEPTIONS)

The SOA domain has strict rules because it must be 100% deterministic:

**A. Three types of SOA KRIs and their reference format:**

| Type | Reference format | `supporting_quote` source |
|------|-----------------|--------------------------|
| Table procedure WITH footnote | `Schedule of Activities, Footnote N, p.X-p.Y` | Verbatim excerpt from Footnote N's text (from `footnote_map.json`) |
| Table procedure WITHOUT footnote | `Schedule of Activities, p.X-p.Y` | Text from the SoA table page itself (procedure name or visit label) |
| Non-table KRI (from body text) | `Section N.N, p.Z` | Verbatim text from the cited protocol section |

Where `p.X-p.Y` is the full page range covering the SoA table AND all its footnote pages (e.g., `p.24-p.29`).

**B. What goes WRONG if these rules are violated (never do these):**
- Do NOT fabricate a "Section X.X" for the SoA table if it has no section number in the protocol
- Do NOT cite individual footnote pages (e.g., `p.27`) — always use the full range (`p.24-p.29`)
- Do NOT put a quote from one footnote when the reference says a different footnote number
- Do NOT include the footnote number inside the quote text (e.g., `"13 Urinalysis..."` → wrong; `"Urinalysis..."` → correct)
- Do NOT use quotes from protocol amendment pages (p.1-10), body text pages, or any page outside the SoA table range for table-derived KRIs
- Do NOT omit the Footnote number from the reference when the procedure has one in the deterministic map

**C. The `supporting_quote` for a footnoted SOA KRI is an excerpt from the footnote text in `footnote_map.json`.** It must be a verbatim substring of that footnote's text, verified by pdfplumber on the SoA footnote pages. It must NOT come from any other source.

**D. Topic-specific quotes for multi-topic footnotes (CRITICAL):**
Some footnotes are long and cover multiple distinct topics (e.g., Footnote 1 in SPIRE covers fasting, informed consent, pre-screening, visit scheduling, dosing windows, lipid testing rules — all in one footnote). When a KRI is about ONE specific topic within a multi-topic footnote:
- The `supporting_quote` MUST quote the **specific sentence(s) about that KRI's topic**, NOT the first 25 words of the footnote
- Example: KRI "IP After Blood Draws" must quote "subjects should self-inject IP only after blood samples have been collected" — NOT the fasting sentence that starts the footnote
- If a KRI's topic comes from a DIFFERENT footnote than its procedure's default, cite the correct footnote (e.g., "IP After Blood Draws" is in Footnote 20, not Footnote 1, even though the IP dispensing procedure maps to Footnote 20)
- NEVER give all KRIs under the same footnote the same generic excerpt. Each KRI quotes the part relevant to its specific check.

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

## Multi-Model Extraction (Gemini + Claude Competition)

The skill uses **competing models** for domain extraction to eliminate same-model bias:

**Architecture per domain:**
```
5 Claude agents (via Claude Code subagents)     ─┐
                                                  ├─→ Adjudication (Claude) → final KRIs
5 Gemini agents (via scripts/gemini_extract.py)  ─┘
```

**Why multi-model matters:**
- Same-model agents share biases — when 5 Claudes agree on a wrong answer, adjudication can't catch it
- Cross-model disagreement (Claude says X, Gemini says Y) is 3x more informative
- Cross-model consensus (both agree) is near-certainty
- Gemini has the lowest hallucination rate (~0.7%) and native PDF support

**How to run Gemini agents:**
```python
import sys
sys.path.insert(0, "/path/to/scripts")
from gemini_extract import run_gemini_extraction, save_gemini_results

# Same prompt used for Claude agents
results = run_gemini_extraction(
    domain="END",
    extraction_prompt=prompt_text,
    n_agents=5,
)
save_gemini_results(results, out_dir, "END")
```

**Adjudication — consensus-based, per domain:**

| Agent consensus | Action |
|---|---|
| **7–10 agents** found it | Auto-approve into golden set |
| **4–6 agents** found it | Verify against protocol, then present decision table to user. User approves/rejects each. |
| **1–3 agents** found it | Auto-delete |

Decision table shown to user for 4–6 tier KRIs includes: KRI ID, KRI Name, agent count with breakdown (e.g., "5/10 (3C + 2G)"), verified status, reference & quote, and a decision column.

**Process is sequential per domain**: SOA → ELIG → SAF → END → OPS. Each domain completes its 10-agent extraction → merge → consensus tiers → user decision table → de-duplication BEFORE the next domain begins.

**API key storage:**
Keys are stored in `~/.claude/secrets/protocol-kri-extractor.json` (never in the skill directory, never pushed to git). The file is `chmod 600` (owner-only). See `scripts/gemini_extract.py` for the loading mechanism.

```json
// ~/.claude/secrets/protocol-kri-extractor.json
{
  "gemini": { "api_key": "AIza...", "model": "gemini-2.5-pro-preview-05-06" },
  "openai": { "api_key": "", "model": "gpt-4o" },
  "xai":    { "api_key": "", "model": "grok-3" }
}
```

Only Gemini is required. OpenAI and xAI are optional — the skill gracefully falls back to Claude-only mode if their keys are empty.

---

## Reference files

- `references/steps.md` — detailed LLM prompt templates for each step
- `references/kri_examples.md` — annotated KRI examples per category
- `scripts/camelot_table_extractor.py` — Camelot-based table extraction (PRIMARY for SoA)
- `scripts/vision_table_extractor.py` — Vision-based extraction + multi-pass + Heuristic 10
- `scripts/gemini_extract.py` — Gemini API extraction agents (multi-model competition)
- `scripts/step3d_verify.py` — Full verbatim pdfplumber verification (blocking gate)
- `scripts/step4a_assemble.py` — Assembly + Excel generation (no LLM needed)
