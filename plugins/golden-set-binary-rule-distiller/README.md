# golden-set-binary-rule-distiller

A Claude Code skill that takes a clinical-trial **Golden Set xlsx** and the **source protocol PDF**, and produces a distilled set containing only the **binary, deviation-producing rules**, with each rule's `Rule for LLM` column rewritten into a uniform machine-readable form and a new `Deviation Level` column added.

## When to invoke

The skill triggers on prompts like:
- "Filter my Golden Set to only the binary rules"
- "Keep only rules that can produce deviations"
- "Rewrite the Rule for LLM column to be machine-readable"
- "Make the KRI rules machine-checkable"
- "Add a Deviation Level column"
- Any time the user shares a Golden Set xlsx plus a protocol PDF and wants the actionable subset extracted.

## Inputs (both mandatory)

1. **Golden Set xlsx** — must include columns `KRI ID`, `Category`, `KRI Name`, `Description`, `Rule for LLM`, `Protocol Reference & Quote`, `Severity`. Any number of sheets.
2. **Source protocol PDF** — the actual protocol the Golden Set was extracted from. The skill cross-checks every decision against this PDF.

## Outputs

- `<protocol_id>_binary_filtered.xlsx` — final clean Golden Set with rewritten `Rule for LLM` column + new `Deviation Level` column.
- `dropped_rules_audit.xlsx` — every dropped rule with one-line reason.
- (Optional) `panel_review_stage2.xlsx` / `panel_review_stage4.xlsx` — per-reviewer votes from optional multi-reviewer stages.
- `changelog.xlsx` — every modification with action and reason (if Stage 4 fixes are applied).

Defaults to `~/Downloads/extractor/<protocol_id>/<run_id>/binary_distill/`.

## Pipeline (4 stages)

1. **Binary filter** — classify each rule keep/drop against three criteria, with mandatory protocol-PDF cross-check.
2. *(Optional)* **Multi-reviewer panel filter** — N parallel reviewers re-audit; drop on consensus (default ≥ 4/10).
3. **Rewrite Rule for LLM** — convert every kept rule into the 3-line `SOURCE / CHECK / DEVIATION` format with mandatory protocol-PDF cross-check before each rewrite. Add the `Deviation Level` column.
4. *(Optional)* **Quality audit** — N parallel reviewers audit the rewritten rules; apply consensus fixes.

## Core principle

The protocol PDF is the only source of truth. The Golden Set is treated as a hypothesis. The skill never invents specifics (numeric tolerances, field lists, ranges, thresholds) that the protocol doesn't authorize.

See `skills/golden-set-binary-rule-distiller/SKILL.md` for the full skill instructions, and the `references/` directory for the detailed filter rubric, rewrite style guide, deviation-level rubric, and panel-review protocols.

## File layout

```
golden-set-binary-rule-distiller/
├── .claude-plugin/
│   └── plugin.json
├── README.md
├── references/
│   ├── filter_criteria.md       Keep/drop rubric, Case A/B/C, examples
│   ├── rewrite_format.md        SOURCE/CHECK/DEVIATION style guide
│   ├── deviation_levels.md      Subject/site/trial guidance
│   └── panel_review.md          Multi-reviewer protocols
├── scripts/
│   ├── load_golden_set.py       Read xlsx → JSON
│   ├── extract_protocol_pages.py  Extract PDF page-range as text
│   ├── write_filtered_xlsx.py   Write final filtered xlsx
│   ├── write_audit_xlsx.py      Write drop audit / changelog xlsx
│   ├── write_panel_review_xlsx.py  Write panel-review consolidation
│   └── validate_rule_format.py  Verify SOURCE/CHECK/DEVIATION format
└── skills/
    └── golden-set-binary-rule-distiller/
        └── SKILL.md             Main skill entry point
```
