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
  "protocol_reference": "Section X.X, Page N: \"verbatim quote ≤30 words\"",
  "additional_footnotes": "Footnote N: verbatim text — or null"
}
```

Five categories (universal across all trials — from ICH GCP, not protocol-specific):
- **SOA** — Schedule of Activities
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints & Statistics
- **OPS** — Operations & Compliance

---

## How to run

### Step 0 — Setup (first time only)
```bash
pip install pdfplumber --break-system-packages -q
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
**Step 1B — Ontology**: Read SoA table. Extract visits, procedures, footnotes verbatim.

### Phase 2 — Extract
**Step 2 — KRI extraction**: One LLM call per category. Produces `raw_{CAT}.json` files.
- SOA: one KRI per procedure × visit cell + cross-visit rules
- ELIG: one KRI per criterion/sub-criterion
- SAF: every reporting timeline, stopping rule, emergency protocol
- END: every endpoint, analysis set, statistical rule
- OPS: IMP handling, blinding, records, compliance

### Phase 3 — Validate (3 independent passes)
**Step 3A — Completeness**: Every ontology procedure × visit cell must have a KRI.
**Step 3B — Accuracy**: 20 random KRIs re-verified against source pages. Threshold ≥85%.
**Step 3C — Consistency**: Same procedure across visits must have consistent details.

### Phase 4 — Assemble + Compare
**Step 4A — Assembly**: Merge all category files → `extracted_kris.json` (Python, no LLM).
**Step 4B — Comparison** (optional): LLM judge vs golden set. Batch 15, 4 verdicts.

---

## Quality rules (apply to every KRI)

1. **Faithfulness**: Use exact drug names, doses, thresholds, timing windows from the protocol. Never generalize ("emergency treatment" → name the drugs).
2. **Data source**: Washout KRIs must say "by checking medication logs and visit timestamps".
3. **Lab panels**: Include all analytes from the protocol footnote — never just "biochemistry panel".
4. **Vitals position**: Use the exact position wording the protocol uses (e.g. "supine position").
5. **Visit prefix**: Every SOA `rule_for_llm` starts with visit code: `V1-`, `S2-`, `All visits-`.
6. **Analysis sets**: Use the protocol's exact definition — ITT ≠ mITT ≠ FAS.
7. **No hallucination**: Every KRI must cite a real section + page. If unsure, omit.

---

## Comparing against a golden set

When a golden set is provided, run Step 4B. This uses an LLM judge (batch 15 pairs per call)
with 4 verdicts:
- **EQUIVALENT** — same intent, same scope, phrasing irrelevant
- **SUBSET** — same requirement but extracted is less specific
- **SUPERSET** — same requirement but extracted adds detail beyond golden
- **DIVERGENT** — different requirement entirely

Pass 2 handles split rules: if one golden KRI was split into two extracted KRIs,
the sibling check counts them as a combined match.

Score = (EQUIVALENT + SUPERSET + 0.5×SUBSET) / total_golden × 100
- ≥80 → PASS
- 60–79 → ITERATE
- <60 → REWORK

---

## Reference files

- `references/steps.md` — detailed LLM prompt templates for each step
- `references/kri_examples.md` — annotated KRI examples per category

## Scripts

All scripts are in the `scripts/` directory:

- `scripts/run.py` — full pipeline orchestrator
- `scripts/step1a_manifest.py` — cover/TOC → manifest.json
- `scripts/step1b_ontology.py` — SoA table → ontology.json
- `scripts/step2_extract.py` — KRI extraction per category
- `scripts/step3a_completeness.py` — completeness validation
- `scripts/step3b_accuracy.py` — accuracy sampling check
- `scripts/step3c_consistency.py` — cross-visit consistency
- `scripts/step4a_assemble.py` — merge to final JSON (no LLM)
- `scripts/step4b_compare.py` — golden set comparison
- `scripts/compare_versions.py` — compare two extraction versions
