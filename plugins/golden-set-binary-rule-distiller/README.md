# golden-set-binary-rule-distiller

A Claude Code skill that takes a clinical-trial **Golden Set xlsx** (with no usable `Rule for LLM` column) and the **source protocol PDF**, and produces a distilled set containing only the **binary, deviation-producing rules**, with each rule's `Rule for LLM` **authored from scratch** as a comprehensive, self-contained, machine-readable **YAML "Protocol rule"** (a data-agnostic clinical statement of the check) and a new `Deviation Level` column added. A rule is kept only if a binary, testable rule can be authored for it.

## When to invoke

The skill triggers on prompts like:
- "Filter my Golden Set to only the binary rules"
- "Keep only rules that can produce deviations"
- "Rewrite the Rule for LLM column to be machine-readable"
- "Make the KRI rules machine-checkable"
- "Add a Deviation Level column"
- Any time the user shares a Golden Set xlsx plus a protocol PDF and wants the actionable subset extracted.

## Inputs (both mandatory)

1. **Golden Set xlsx** — must include columns `KRI ID`, `Category`, `KRI Name`, `Description`, `Protocol Reference & Quote`, `Severity`. Any number of sheets. A `Rule for LLM` column is **not required** — the skill authors it; if present it's treated as a non-authoritative hint only.
2. **Source protocol PDF** — the actual protocol the Golden Set was extracted from. The skill cross-checks every decision against this PDF.

## Outputs

- `<protocol_id>_binary_distilled.xlsx` — final clean Golden Set with the freshly authored `Rule for LLM` column + new `Deviation Level` column.
- `dropped_rules_audit.xlsx` — every dropped rule with one-line reason.
- (Optional) `panel_review_stage2.xlsx` / `panel_review_stage4.xlsx` — per-reviewer votes from optional multi-reviewer stages.
- `changelog.xlsx` — every modification with action and reason (if Stage 4 fixes are applied).

Defaults to `~/Downloads/extractor/<protocol_id>/<run_id>/binary_distill/`.

## Pipeline (4 stages)

All multi-agent panels run on **Gemini 3.5 Flash (high thinking)** — never Claude sub-agents. Dropping is **keep-biased**: a rule is removed only if a panel *nominates* it AND a second panel *fails to defend* it; no single reviewer can drop a rule.

1. **Stage 1 — Drop nomination** — a Gemini panel (default 5) flags drop candidates against the binary test; **nothing is dropped yet** (any drop vote = candidate; keep is the default).
2. **Stage 2 — Drop defense** — a Gemini panel tries to *keep* each candidate. Equivalent rules (same footnote / procedure / "optional" clause) are clustered and ruled as one family; a family is dropped on a clear ≥ 4/5 confirm, restored if defended ≥ 3/5, and **every 3–2 near-tie is escalated to the user**. Discretionary/optional procedures ("may", "per Sponsor") are not defensible by "if performed it's checkable" → confirm-drop. An inverse-coverage pass then checks the whole drop list for systematic over-dropping.
3. **Stage 3 — Author Rule for LLM** — write every survivor from scratch as a YAML "Protocol rule" (slots: `intent` / `applies_to` / `evidence_expected` / `acceptance` / `deviation` / `provenance`; data-agnostic; **no footnote numbers**), folding in every checkable detail from columns + footnotes + PDF. Assign the `Deviation Level` column.
4. *(Recommended)* **Stage 4 — Quality panel** — a Gemini panel audits the authored rules; apply consensus fixes (dismiss flags that conflict with user-approved patterns).

## Core principle

The protocol PDF is the only source of truth. The Golden Set is treated as a hypothesis. The authored `Rule for LLM` must be **exhaustive of what the protocol authorizes** (every analyte, window, required-subset, and condition — because only this column drives the downstream deviation engine) and **silent on what it doesn't** — the skill never invents specifics (numeric tolerances, field lists, ranges, thresholds) the protocol doesn't state.

See `skills/golden-set-binary-rule-distiller/SKILL.md` for the full skill instructions, and the `references/` directory for the detailed filter rubric, authoring style guide, deviation-level rubric, and panel-review protocols.

## File layout

```
golden-set-binary-rule-distiller/
├── .claude-plugin/
│   └── plugin.json
├── README.md
├── references/
│   ├── filter_criteria.md       Keep/drop rubric, Case A/B/C, examples
│   ├── rewrite_format.md        YAML Protocol-rule style guide
│   ├── deviation_levels.md      Subject/site/trial guidance
│   └── panel_review.md          Multi-reviewer protocols
├── scripts/
│   ├── load_golden_set.py       Read xlsx → JSON
│   ├── extract_protocol_pages.py  Extract PDF page-range as text
│   ├── write_filtered_xlsx.py   Write final filtered xlsx
│   ├── write_audit_xlsx.py      Write drop audit / changelog xlsx
│   ├── write_panel_review_xlsx.py  Write panel-review consolidation
│   └── validate_rule_format.py  Verify YAML Protocol-rule format
└── skills/
    └── golden-set-binary-rule-distiller/
        └── SKILL.md             Main skill entry point
```
