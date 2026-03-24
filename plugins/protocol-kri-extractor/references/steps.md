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

## Step 1B — SoA Ontology

**Purpose**: Read SoA table pages from manifest, produce `ontology.json`.

**PDF pages to read**: All pages listed in `manifest.section_map.SOA[*].pages_approx` plus 2 buffer pages after the last one (for footnotes).

**LLM prompt**:
```
Read the Schedule of Activities table in the following protocol pages.
It is a matrix where rows are procedures and columns are visits.

[PROTOCOL PAGES]
{soa_pages_text}
[END]

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
- Return ONLY the JSON
```

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

**Save output**: `{out_dir}/gaps_report.json`

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

---

## Step 4B — Golden Set Comparison (optional)

Only run if a golden set JSON is provided.

**Batch size**: 15 pairs per LLM call.
**Pass 1**: 1:1 ID matching, then semantic judge.
**Pass 2**: For SUBSET cases, check if sibling extracted KRIs together cover the golden.

**Judge prompt** (include at top of every batch call):
```
You are a clinical trial monitoring expert comparing CRA verification rules.

SCORING RUBRIC:
- EQUIVALENT: Same intent, same scope, same data. Phrasing is irrelevant.
  "Verify absence of X" = "Verify participant does not have X" = EQUIVALENT
- SUBSET: Same requirement but extracted is less specific — missing a data source,
  threshold, drug name, or condition detail
- SUPERSET: Same requirement but extracted adds specificity beyond the golden
- DIVERGENT: Different requirement, different visit scope, or different rule entirely

FEW-SHOT EXAMPLES:
[PAIR] INC1
  GOLDEN:    Verify age ≥ 64 years at screening.
  EXTRACTED: Verify participant is ≥ 64 years old at first screening visit.
  VERDICT: EQUIVALENT

[PAIR] SOA-V4-075
  GOLDEN:    V4- Verify by checking medication logs the participant maintained 48-hour washout.
  EXTRACTED: V4- Verify that a ≥48-hour washout was observed before pain assessments.
  VERDICT: SUBSET — missing "by checking medication logs"

[PAIR] OPS1
  GOLDEN:    Verify IMP storage logs document ≤ -150°C.
  EXTRACTED: Verify IMP storage logs document ≤ -150°C (or -80°C short-term) in secure area.
  VERDICT: SUPERSET — adds short-term condition and access control

NOW EVALUATE {N} PAIRS. Return ONLY a JSON array of exactly {N} objects:
[{"kri_id": "...", "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT", "reason": "one sentence"}]
```

**Scoring**: `(EQUIVALENT + SUPERSET + 0.5×SUBSET) / total_golden × 100`
- ≥80 → PASS | 60–79 → ITERATE | <60 → REWORK

**Save output**: `{out_dir}/comparison_report.json`
