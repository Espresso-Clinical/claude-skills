---
name: golden-set-binary-rule-distiller
description: Distills a clinical-trial Golden Set (KRI rules extracted from a protocol) into ONLY the binary, deviation-producing rules — and rewrites each surviving rule's "Rule for LLM" column into a clean, machine-readable 3-line SOURCE/CHECK/DEVIATION format with a Deviation Level column added. The Golden Set is treated as a hypothesis; the source protocol PDF is the only source of truth, and every decision must be cross-checked against the PDF. Use this skill whenever the user asks to "filter a golden set", "extract only binary rules", "keep only rules that produce deviations", "rewrite rule for LLM", "make rules machine-readable", "clean up KRIs", or provides a Golden Set xlsx plus a protocol PDF and wants the actionable rules separated from definitions/methodology/reporting. Also use when the user wants to add a Deviation Level (subject/site/trial) column to a KRI table.
---

# Golden Set Binary-Rule Distiller

## What this skill does

Takes two inputs:
1. A **Golden Set xlsx** — clinical-trial KRI rules (typically produced by the `protocol-kri-extractor` skill or hand-curated).
2. The **source protocol PDF** — the actual protocol from which the Golden Set was extracted.

Produces:
- `<protocol_id>_binary_filtered.xlsx` — the final distilled Golden Set: only rules that can produce a binary deviation from data, with the `Rule for LLM` column rewritten in a uniform machine-readable form and a new `Deviation Level` column.
- `dropped_rules_audit.xlsx` — every dropped rule with a one-line reason.
- (Optional) `panel_review.xlsx` — per-reviewer votes and rationales when multi-reviewer stages are run.

## Why this skill exists — the core insight

Golden Sets coming out of protocol extraction contain many rule types: binary checks, definitions, statistical methodology, reporting metrics, exploratory analyses, vague aspirations. Only a fraction of them can actually produce a **deviation** when data arrives — a yes/no flag based on a concrete data point. The skill's job is to keep that fraction and discard the rest, then make every surviving rule's "Rule for LLM" text crisp enough that a downstream LLM engine can execute it against trial data.

**The crucial discipline:** the source `Rule for LLM` text in the Golden Set is often loose, sometimes wrong, sometimes drifts from the protocol. So is the `Description`. Even the `Protocol Reference & Quote` column may be a truncated or mis-anchored snippet. The skill must **never trust the Golden Set's text as authoritative** — every keep/drop decision and every rewrite must be cross-checked against the actual protocol PDF at the cited reference. This is the rule that prevents fabrications.

## Required inputs from the user

Confirm both are present before starting:
- **Golden Set xlsx path** — must have columns `KRI ID`, `Category`, `KRI Name`, `Description`, `Rule for LLM`, `Protocol Reference & Quote`, `Severity`. Any number of sheets.
- **Source protocol PDF path** — the actual protocol document.

If the user provides only one of the two, ask for the other. The PDF is not optional — the skill cannot reliably do its job without it.

## Output layout

Use the convention `~/Downloads/extractor/<protocol_id>/<run_id>/binary_distill/`. Pick `<run_id>` as a zero-padded incrementing number (e.g., `run_001`, `run_002`) within the protocol directory, mirroring the protocol-kri-extractor convention.

## The pipeline — 4 stages

Stages 1 and 3 are mandatory. Stages 2 and 4 (panel reviews) are recommended but optional; ask the user how thorough a pass they want before starting.

### Stage 1 — Binary filter

For every rule in the Golden Set, decide whether it produces a binary deviation. Read `references/filter_criteria.md` for the full rubric (case A/B/C distinction and the keep/drop lists with examples). The short version:

**KEEP** if the rule has a measurable data anchor (a number, date, presence/absence, category) that the rule references — even if the threshold is fuzzy. The downstream LLM engine applies judgment at borderline cases.

**DROP** if the rule is primarily a pure endpoint or population definition, statistical methodology, a reporting metric, an exploratory analysis, a permissive option, a broad meta-compliance umbrella, a pure term definition, or a pure aspiration with no measurable target.

**Mandatory cross-check before every decision:** open the protocol PDF at the cited section/page, read the surrounding context (not just the snippet), and verify the rule's intent against the actual protocol text. If the cited reference doesn't actually support the rule, lean toward drop.

Read ALL columns of the rule together (KRI ID, Category, KRI Name, Description, Rule for LLM, Protocol Reference & Quote, Severity). Treat the `Rule for LLM` column with **limited trust** — it is often the most malformed column in the source. The Description and Protocol Reference are usually more reliable, but still must be verified against the PDF.

For homogeneous rule families (e.g., SOA visit-procedure cells), it's fine to evaluate the template once and apply the decision across all instances of that template.

Write the filtered set and a corresponding `dropped_rules_audit.xlsx` listing every dropped rule with a one-line reason.

### Stage 2 — Multi-reviewer panel filter (optional)

If the user wants a more rigorous pass, spawn parallel reviewer agents (default 10) — each independently audits the Stage-1 kept rules and flags any that should still be dropped, with one-line reasons. Each reviewer must have access to the protocol PDF.

Consolidate votes per rule. Drop rules at the consensus threshold (default ≥ 4/10). Save all panel votes and rationales to `panel_review_stage2.xlsx`.

Read `references/panel_review.md` for prompts, vote-consolidation logic, and consensus-threshold guidance.

### Stage 3 — Rewrite `Rule for LLM` (with mandatory protocol cross-check)

For every kept rule, rewrite the `Rule for LLM` column into the agreed 3-line format:

```
SOURCE: <data the engine should pull, in plain natural language>
CHECK: <the precise compliance condition>
DEVIATION: <the exact condition that flags a deviation, including missing-data cases>
```

Three lines. No extra fields, no preambles, no postscripts.

**Before writing each rule, the agent MUST:**
1. Open the protocol PDF at the cited reference in the `Protocol Reference & Quote` column.
2. Read the surrounding context (the full paragraph/section, not just the quoted snippet).
3. Verify the rule's intent against the protocol's actual wording.
4. If the protocol doesn't actually support the rule's intent, flag it as a drop candidate instead of inventing.

**Hard rules for the rewrite (read `references/rewrite_format.md` for examples):**
- Short and sharp: one short sentence per line. No paragraphs.
- Natural language only — NO EDC/CRF field names, no schema references. "The subject's screening body weight" — never `vitals.weight_kg`.
- **NEVER invent numeric bounds, tolerances, field lists, ranges, or conditions not present in the protocol text.** If the protocol says "approximately 30 minutes", the rule says "approximately 30 minutes" — never "25-35 minutes". When the protocol is intentionally fuzzy, use phrasing like "substantially deviates per applicable sponsor SOP" and let the downstream LLM apply runtime judgment.
- Include missing-data as a deviation cause whenever the rule's intent is data presence ("…or measurement is missing").
- Preserve the protocol's fuzziness. Don't sharpen it. The downstream LLM engine handles edge cases at runtime — that's its job, not the skill's.

**Add the new `Deviation Level` column** with one of `subject`, `site`, `trial`. See `references/deviation_levels.md` for the assignment rubric and examples.

### Stage 4 — Quality audit (optional, single pass)

If the user wants to verify Stage 3 landed cleanly, spawn parallel reviewer agents (default 10). Each has access to the protocol PDF and audits every rewritten rule, flagging issues:
- `unclear`: SOURCE/CHECK/DEVIATION wording is vague or missing data the engine needs
- `inconsistent`: rule contradicts/drifts from the protocol text or other Golden Set columns
- `non-deviation`: DEVIATION doesn't describe a real anomaly; should not be in Golden Set
- `wrong-level`: Deviation Level mis-assigned
- `broken-template`: SOURCE/CHECK/DEVIATION structure missing/malformed
- `fabricated-specifics`: rule introduces numbers, tolerances, or fields not in the protocol

Consolidate flags per rule. Fix high-consensus issues (≥ 4/10). **Stop after one or at most two passes** — past that, returns diminish sharply; singleton reviewer opinions are not the same as real defects.

Save audit votes and rationales to `panel_review_stage4.xlsx`. Apply fixes to the filtered xlsx and document each change in a changelog xlsx.

Read `references/panel_review.md` for audit-prompt templates.

## Hard constraints across all stages

These constraints are not negotiable — they exist because violating them caused real rework on prior runs:

1. **Preserve all source columns exactly** other than `Rule for LLM` (rewritten in Stage 3) and the new `Deviation Level` column. Do not modify Category, KRI Name, Description, Protocol Reference & Quote, or Severity.

2. **Do not change KRI IDs.** Source-file bugs (duplicate IDs, typos, malformed names) are preserved unless the user **explicitly authorizes** a fix. If duplicates exist in the source, surface them in the audit log and ask.

3. **Do not dedupe cross-sheet logical duplicates** (e.g., the same protocol provision encoded once in ELIG and once in OPS) unless the user explicitly authorizes the dedupe. Surface duplicates in the audit log.

4. **Audit log is mandatory** — every drop and every modification must be captured in the audit/changelog xlsx with a one-line reason.

5. **Protocol PDF is the only source of truth.** The Golden Set's text is a starting hypothesis. Never invent specifics the protocol doesn't authorize. The single most common failure mode of past runs was sharpening fuzzy protocol language by inventing tolerances ("25-35 min" instead of "approximately 30 min"); don't do this.

## Default behaviors and user-customization points

Before starting, briefly confirm with the user:
- **Number of reviewer agents per panel stage** (default 10).
- **Consensus threshold for drops/fixes** (default ≥ 4 of 10 votes).
- **Run Stage 2?** (default yes — recommended).
- **Run Stage 4?** (default yes — recommended).
- **Number of audit passes** (default 1; cap at 2).

Then proceed without further confirmation unless something material changes.

## Lessons baked into this skill (so we don't repeat past mistakes)

- **Stay protocol-faithful.** Never invent numeric tolerances to make a rule "more binary". A rule with "approximately X" is still binary — the LLM engine handles judgment at runtime.
- **Treat the source `Rule for LLM` column with limited trust.** It is often the most malformed column in the input. Cross-check against the Description, the Protocol Reference & Quote, and (most importantly) the actual protocol PDF.
- **Per-AE timeliness/completeness rules are subject-level**, not site-level. Other CRF data-quality rules tied to a per-subject event are also subject-level. Site-level is for site-wide assets (storage logs, IRB approval, monitoring logs) and trial-level is for cumulative trial state (pause triggers, DMC cadence, enrollment caps).
- **Cross-sheet duplicates of the same protocol provision** get flagged but only deduped on user authorization.
- **One panel-review pass is usually enough.** Diminishing returns past that; the long tail of singleton reviewer opinions is noise, not defects.

## Operating workflow

1. Confirm both inputs (Golden Set xlsx + protocol PDF). Confirm output directory.
2. Confirm default behaviors (panel sizes, thresholds, whether to run Stages 2/4).
3. Run Stage 1 (filter). Produce the first filtered xlsx and audit log.
4. (Optional) Run Stage 2 (panel filter). Update the filtered xlsx and audit log.
5. Run Stage 3 (rewrite Rule for LLM + add Deviation Level). Produce the rewritten xlsx.
6. (Optional) Run Stage 4 (quality audit + fixes). Produce the final xlsx and audit log.
7. Summarize: how many rules entered, how many remain, where the audit logs are, key drop categories.

## Reference files (load as needed)

- `references/filter_criteria.md` — Full keep/drop rubric. Case A/B/C distinction. Examples.
- `references/rewrite_format.md` — SOURCE/CHECK/DEVIATION style guide with before/after examples. The "no invented thresholds" rule with worked examples.
- `references/deviation_levels.md` — Subject/site/trial assignment rubric with examples.
- `references/panel_review.md` — Multi-reviewer protocols, prompt templates, vote consolidation.

## Helper scripts (in `scripts/`)

These exist to handle deterministic plumbing — file I/O, xlsx formatting, format validation. The classification and rewriting logic stays with the agent.

- `scripts/load_golden_set.py` — Load and validate the Golden Set xlsx. Emits JSON.
- `scripts/extract_protocol_pages.py` — Extract a specific page-range from the protocol PDF for cross-check.
- `scripts/write_filtered_xlsx.py` — Write the final filtered xlsx with proper formatting, preserved columns, and the new `Deviation Level` column.
- `scripts/write_audit_xlsx.py` — Write the audit/changelog xlsx.
- `scripts/validate_rule_format.py` — Sanity-check every rule's `Rule for LLM` column for the SOURCE/CHECK/DEVIATION 3-line format.

Run them via `python -m scripts.<name>` from the plugin root, or call directly with `python /path/to/script.py`.
