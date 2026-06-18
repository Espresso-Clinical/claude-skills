---
name: golden-set-binary-rule-distiller
description: Distills a clinical-trial Golden Set (KRI rules extracted from a protocol) into ONLY the binary, deviation-producing rules — and AUTHORS each surviving rule's "Rule for LLM" from scratch as a comprehensive, self-contained, machine-readable YAML "Protocol rule" (a data-agnostic clinical statement of the check), with a Deviation Level column added. The incoming Golden Set has no usable "Rule for LLM" column; the skill generates it. A rule is kept only if a binary, unambiguously-testable Rule for LLM can be authored for it; if not, the rule is dropped in the binary filter. The authored Rule for LLM must fold in EVERY checkable detail from all of the rule's columns plus its footnotes/quotes (analyte lists, time/acceptability windows, required-subsets, conditional triggers, definitions of what passes vs. what deviates), because downstream only the Rule for LLM drives the deviation engine. The source protocol PDF is the only source of truth, and every decision must be cross-checked against the PDF. Use this skill whenever the user asks to "filter a golden set", "extract only binary rules", "keep only rules that produce deviations", "generate/author/rewrite rule for LLM", "make rules machine-readable", "clean up KRIs", or provides a Golden Set xlsx plus a protocol PDF and wants the actionable rules separated from definitions/methodology/reporting. Also use when the user wants to add a Deviation Level (subject/site/trial) column to a KRI table.
---

# Golden Set Binary-Rule Distiller

## What this skill does

Takes two inputs:
1. A **Golden Set xlsx** — clinical-trial KRI rules (typically produced by the `protocol-kri-extractor` skill or hand-curated). **It arrives with no usable `Rule for LLM` column** — that column is absent or empty. The skill authors it.
2. The **source protocol PDF** — the actual protocol from which the Golden Set was extracted.

Produces:
- `<protocol_id>_binary_distilled.xlsx` — the final distilled Golden Set: only rules for which a binary, testable rule could be authored, each with a freshly **authored** `Rule for LLM` in the YAML Protocol-rule form and a new `Deviation Level` column.
- `dropped_rules_audit.xlsx` — every dropped rule with a one-line reason.
- (Optional) `panel_review.xlsx` — per-reviewer votes and rationales when multi-reviewer stages are run.

## Why this skill exists — the core insight

Golden Sets coming out of protocol extraction contain many rule types: binary checks, definitions, statistical methodology, reporting metrics, exploratory analyses, vague aspirations. Only a fraction of them can actually produce a **deviation** when data arrives — a yes/no flag based on a concrete data point. The skill's job is to keep that fraction, discard the rest, and **author from scratch** a `Rule for LLM` for each survivor that is crisp and complete enough for a downstream LLM engine to execute against trial data.

**Scope — the skill changes nothing else.** The only outputs the skill creates are two new columns (the authored `Rule for LLM` and `Deviation Level`) and the removal of non-binary rules. Every existing column of every surviving rule (`KRI ID`, `Category`, `KRI Name`, `Description`, `Protocol Reference & Quote`, `Severity`, and anything else present) is carried through **verbatim, unchanged**. See Hard Constraint #1.

**The binary filter and the authoring are the same test.** For each rule, attempt to author a binary, unambiguously-testable `Rule for LLM`. If you can — keep the rule. If you cannot — because the rule has no measurable anchor, can't produce a deviation, or is a pure definition/methodology/aspiration — **drop it in the binary filter** and log why. "Can a binary rule be authored for this?" is exactly the keep/drop question.

**The authored `Rule for LLM` is the product.** Downstream, the deviation engine is driven by the `Rule for LLM`. It must therefore be the most informative, most comprehensive artifact possible: **every smallest checkable detail must appear in it.** Pull from every column the rule has — `KRI Name`, `Description`, `Category`, `Severity`, `Protocol Reference & Quote` — AND from the footnotes/quotes and the protocol PDF behind them. Concretely, the rule must capture things like: every analyte/parameter that must be present in a panel (e.g. each value in a biochemistry test), every time or acceptability window ("up to 4 days prior to the visit", "within 3 months prior to screening is acceptable"), every required-subset and AND/OR condition ("sodium, potassium, glucose, bilirubin, creatinine, and AST or ALT must be reviewed prior to first treatment"), and the protocol's own definition of what counts as compliant vs. what counts as a deviation. If a detail is checkable and the protocol authorizes it, it belongs in the rule. Nothing checkable may be left behind in a footnote or another column.

**The crucial discipline:** the `Description` may be loose, and the `Protocol Reference & Quote` column may be a truncated or mis-anchored snippet. The skill must **never trust the Golden Set's text as authoritative** — every keep/drop decision and every authored rule must be cross-checked against the actual protocol PDF at the cited reference. This is the rule that prevents both fabrication (inventing what the protocol doesn't say) and omission (dropping what the protocol does say).

## Required inputs from the user

Confirm both are present before starting:
- **Golden Set xlsx path** — must have columns `KRI ID`, `Category`, `KRI Name`, `Description`, `Protocol Reference & Quote`, `Severity`. Any number of sheets. A `Rule for LLM` column is **not required** — the skill authors it. If one is present on input, treat it as a non-authoritative hint only; do not carry its text forward unverified.
- **Source protocol PDF path** — the actual protocol document.

If the user provides only one of the two, ask for the other. The PDF is not optional — the skill cannot reliably do its job without it.

## Output layout

Use the convention `~/Downloads/extractor/<protocol_id>/<run_id>/binary_distill/`. Pick `<run_id>` as a zero-padded incrementing number (e.g., `run_001`, `run_002`) within the protocol directory, mirroring the protocol-kri-extractor convention.

## The pipeline — 4 stages

The filter is split into **Stage 1 (nominate)** and **Stage 2 (defend)**; **Stage 3 (author)** is the core; **Stage 4 (quality panel)** verifies the authoring. Stages 1 and 3 are mandatory. Stages 2 and 4 are strongly recommended — they are the safety nets — confirm with the user how thorough a pass they want.

### Panel engine — skill-wide rule (read before running any stage)

**Every multi-agent panel in this skill runs on Gemini 3.5 Flash at high thinking — never Claude sub-agents.** This covers Stage 1 nomination, Stage 2 defense, the inverse-coverage check, and Stage 4. The Claude `Agent` tool cannot route to Gemini, so call Gemini via the wrapper:

```
import sys; sys.path.insert(0, os.path.expanduser("~/.claude/skills-repo/plugins/soa-kri-extractor/scripts"))
from gemini_extract import call_gemini
call_gemini(prompt, system_prompt=..., temperature=..., task="judge")   # task="judge" = high thinking budget
```

Run the reviewers in parallel threads with a temperature spread (e.g. 0.1–0.3) for independence. Model + API key are in `~/.claude/secrets/protocol-kri-extractor.json` (model = `gemini-3.5-flash`). Requires PyYAML (`pip install pyyaml`).

### Dropping discipline — the governing principle of Stages 1–2

Dropping a rule is the only destructive, irreversible action the filter takes, so it is the hardest thing to do. **Keep is the default.** A rule is removed only if a panel *nominates* it for drop AND a second panel *fails to defend* it. **No single agent can drop a rule.** Borderline rules fall toward keep or are escalated to the user — never silently dropped.

### Stage 1 — Drop nomination (multi-agent panel; nothing is finalized here)

A panel of independent Gemini reviewers (default 5) each classifies **every** rule keep/drop against the binary test (read `references/filter_criteria.md`): *can a binary, unambiguously-testable `Rule for LLM` be authored?* KEEP if there is a measurable data anchor (number, date, presence/absence, category) even if fuzzy; nominate for DROP only if it is primarily a pure definition, statistical methodology, reporting metric, exploratory analysis, permissive option, broad meta-compliance umbrella, or pure aspiration. Each reviewer cross-checks the protocol PDF at the cited reference (+ footnotes).

Consolidate the votes into three buckets — **Stage 1 finalizes nothing; it only triages:**
- **Unanimous keep** → kept and locked (skips Stage 2).
- **Any drop vote** → becomes a **drop *candidate*** carried to Stage 2, tagged with its drop-vote count and the reviewers' reasons.
- For homogeneous SOA visit×procedure templates, evaluate the template once and apply across instances.

Save the nomination votes to `stage1_nominations.json`. **Stage 1 cannot remove a rule on its own** — there is no "dropped" list yet.

### Stage 2 — Drop confirmation by adversarial defense (multi-agent panel; the recovery stage)

For **each drop candidate from Stage 1**, a fresh panel of independent Gemini reviewers (default 5) gets the OPPOSITE task: **steelman keeping the rule** — find any protocol-grounded reason it *is* binary/checkable (a measurable anchor, a footnote that makes it testable, a rubric basis such as a valid trial-level governance KRI) — and only then vote confirm-drop vs. restore.

**Discretionary ≠ binary — defense guardrail (do not rescue optional procedures).** A procedure the protocol leaves to discretion — "may be performed", "optionally", "in a subset", "per Sponsor instruction", "per investigator judgment" — is **NOT** made binary by arguing "if it is performed, its presence is checkable." Discretion is not a protocol-mandated trigger, so non-performance cannot be a deviation → these **confirm-drop**. A conditional rule is only defensible when **both** hold: (i) the trigger is a protocol-**defined, recorded** clinical condition (e.g. "if total bilirubin is abnormal", "women of childbearing potential"), AND (ii) the protocol **requires** the action when the trigger holds. "Sponsor/investigator may decide" fails (i) — drop it.

**Family consistency — decide equivalent rules as ONE unit (do not let a 1-vote margin split them).** Before consolidating votes, **cluster the candidates that share the same protocol basis** — the same footnote, the same procedure repeated across visits, the same "optional per Sponsor" clause (e.g. all synovial-fluid-collection rules; all physical-performance-test rules). Decide each family with a **single verdict** applied to every instance: pool the family's votes (or take the modal verdict) rather than ruling instance-by-instance. Near-identical rules must never end up split (some dropped, some kept) on noise.

**Keep-biased decision (asymmetric thresholds), applied per family:**
- **Drop** only on a clear confirm-majority: **≥ 4/5 confirm** (or, after pooling a family, a clear ≥⅔ confirm share). A bare 3–2 is **not** decisive.
- **Restore to keep** if the defense reaches **≥ 3/5**, or confirm ≤ 1.
- **Escalate to the user** every genuine near-tie (3–2 either way) and every family the panel can't clearly resolve — never auto-decide a knife-edge vote. Keep is the default whenever unsure.

This is what makes the filter reversible: Stage 1 only accuses; Stage 2 defends and **can give rules back**. Read `references/panel_review.md` for the nomination/defense prompts, thresholds, and consolidation.

**Inverse-coverage check (final guard against over-dropping):** after Stage 2, one more Gemini pass reviews the *entire finalized drop list at once* and asks "were any of these wrongly removed — was a whole class of rule (e.g. trial-level governance) systematically dropped?" Anything it flags is restored or escalated to the user. Then write `dropped_rules_audit.xlsx` (every drop + stage + reason + vote counts).

### Stage 3 — Author `Rule for LLM` from scratch (with mandatory protocol cross-check)

For every kept rule, **author** the `Rule for LLM` from scratch as a **YAML "Protocol rule"** — a data-agnostic clinical statement of the check, built from the rule's columns + footnotes + the protocol PDF. There is no source `Rule for LLM` to clean up.

The rule is serialized as **YAML** in the single `Rule for LLM` cell, with these slots:

```yaml
intent: one-line plain-English purpose
applies_to: the clinical denominator — WHO/WHAT must satisfy this (e.g. "enrolled subjects", "every SAE", "every activated site")
evidence_expected: the clinical artifact the protocol says must exist (the thing, not where it is stored)
acceptance:            # open set of sub-slots — use only the ones the rule needs
  timing: ...          # window / acceptability window
  required: ...        # mandatory items
  preferred: ...       # non-mandatory but preferred
  conditional: ...     # conditional trigger / exception
  pass: ...            # the plain pass condition (criteria-style rules)
  override: ...        # a documented waiver that satisfies the rule
deviation: the violation in clinical terms, derived from applies_to + acceptance
provenance: terse pointer only — section + page (NO footnote numbers; not the verbatim quote)
```

This is the **protocol layer only** — it names NO tables, columns, codes, joins, or EDC/CRF fields. Resolving the rule to real data is a downstream tool's job, deliberately outside this format.

**Before writing each rule, the agent MUST:**
1. Open the protocol PDF at the cited reference, read the surrounding context (the full paragraph/section), **and every footnote attached to the rule's row/cell**.
2. Verify the rule's intent against the protocol's actual wording. If the protocol doesn't support it, flag it as a drop candidate instead of inventing.

**Hard rules for authoring (read `references/rewrite_format.md` for the full guide + worked examples):**

- **Comprehensiveness — harvest from every column AND every footnote.** The authored rule is the ONLY artifact the deviation engine runs on, so every checkable detail must live inside it. Fold in: analyte/parameter lists (each value in a panel), time & acceptability windows ("up to 4 days prior", "available 3 months prior is acceptable"), mandatory subsets and AND/OR logic ("sodium … and AST or ALT"), conditional triggers ("only if total bilirubin is abnormal", "for women of childbearing potential"), and the protocol's pass-vs-deviation definition. Never leave a checkable detail sitting only in a footnote or another column.
- **Clarity — plain clinical language, no meta-commentary.** Every slot must read as a clear clinical statement. Do NOT write self-referential caveats like "presence and dating only — does NOT require every component" or tags like "[footnote 12 definition]". If individual items are not mandatory, simply don't list them under `required` and let the `deviation` line carry the actual check — its silence on the items already means they aren't required. Both the engine and a human must read the rule without decoding jargon.
- **No footnote numbers anywhere in the rule.** Carry the footnote's *content* into the slots, but never the citation — no "footnote 14", no "[footnote 14]", in any slot **including `provenance`**. The rule does not care which footnote number a detail came from; the numbered citation already lives, untouched, in the `Protocol Reference & Quote` column.
- **`applies_to` is a clinical denominator, never a data filter.** "enrolled subjects", "every SAE", "every activated site". Never adjectives like "active" or "expected to attend". For **eligibility criteria**, the denominator is **"enrolled subjects"** — the criterion is assessed at screening, but the deviation is *enrolling an ineligible subject* (a screen failure is not a deviation). Never use "randomized" unless the provision is specifically about the randomized phase (e.g. this trial's run-in phase is not randomized).
- **`evidence_expected` names a clinical artifact**, never restates the criterion. Write "the subject's prior IP / interventional-trial exposure history for the 60 days before first treatment" — not "the eligibility determination for exclusion #22".
- **No filler.** Drop subject-state preambles and restated visit labels. Keep every clinical parameter, value, window, and condition.
- **NEVER invent** numeric bounds, tolerances, field lists, or conditions not in the protocol. Comprehensiveness means including everything the protocol *does* authorize — never inventing what it doesn't. Preserve the protocol's fuzziness ("approximately 30 minutes" stays fuzzy; use "substantially deviates per applicable sponsor SOP" rather than an invented tolerance).
- **Author to the protocol, not the source columns.** If the `Description` conflicts with the protocol (e.g. a templated "±3-day window" where the SoA says "Day -29 to 0"), author to the protocol and surface the discrepancy in the audit log — do NOT change the Description (immutability).
- **Presence-only vs required-subset (labs).** A *screening* lab is usually presence-only: list its components inside `evidence_expected` as a description, give the window in `acceptance.timing`, and make the `deviation` "no result performed/dated in the window" — do NOT add a `required` item list. A *pre-treatment* lab that a footnote makes mandatory (e.g. "the following must be reviewed prior to first treatment: …") DOES get a `required` subset and a `preferred` full panel.
- **Visit-anchored timing — name the visit, not its window.** For a procedure scheduled at a specific visit, `acceptance.timing` names the visit ("performed at the V3 visit", "for the Screening visit") and keeps the procedure's own footnote window — but never restates the visit's calendar window ("Day 12-16", "Day -29 to 0"), which is owned by the visit's dedicated check-in rule.

**Assign the `Deviation Level` column** (`subject` / `site` / `trial`). This is **assigned by the skill** for every rule — verify and overwrite any inherited value; do not assume the input is correct. See `references/deviation_levels.md` for the rubric.

### Stage 4 — Quality audit (optional, single pass)

If the user wants to verify Stage 3 landed cleanly, run a Gemini panel (default 5 reviewers, high thinking — see "Panel engine" above; never Claude sub-agents). Each reviewer has the source row + the protocol PDF and audits every authored rule, flagging issues:
- `omitted-detail`: a checkable detail in the protocol/footnotes/columns (an analyte, a time or acceptability window, a required-subset, an AND/OR condition, a conditional trigger, a pass/deviation definition) is missing from the rule's slots. This is the most important flag — the rule must be exhaustive.
- `jargon`: a slot contains meta-commentary, self-referential caveats, or a footnote number (e.g. "presence and dating only — does NOT require every component", "[footnote 12]", "Footnote 14") instead of a plain clinical statement — should be rewritten plainly with no footnote numbers.
- `filler`: rule carries boilerplate that adds length without adding a check (e.g. "active subject expected to attend…", restated visit labels) — should be trimmed.
- `visit-window-in-timing`: a visit-anchored procedure's `acceptance.timing` restates the visit's calendar window ("Day 12-16", "Day -29 to 0") instead of naming the visit — the window belongs to the dedicated visit check-in rule (the procedure's own footnote window is fine).
- `bad-denominator`: `applies_to` is a data filter or wrong population (e.g. "randomized" for an eligibility criterion, "active subject") instead of a clinical denominator.
- `restated-criterion`: `evidence_expected` restates the criterion instead of naming a clinical artifact.
- `unclear`: a slot is vague or missing data the engine needs
- `inconsistent`: rule contradicts/drifts from the protocol text or other Golden Set columns
- `non-deviation`: the `deviation` slot doesn't describe a real anomaly; should not be in Golden Set
- `wrong-level`: Deviation Level mis-assigned
- `broken-template`: YAML malformed, or a required slot (intent / applies_to / evidence_expected / acceptance / deviation / provenance) missing
- `fabricated-specifics`: rule introduces numbers, tolerances, or fields not in the protocol

Consolidate flags per rule. Fix high-consensus issues (default ≥ majority, e.g. ≥ 2/3 or ≥ 3/5). **Stop after one or at most two passes** — past that, returns diminish sharply; singleton reviewer opinions are not the same as real defects. When a panel flag conflicts with a user-approved pattern (e.g. a denominator the user already signed off on), keep the user's decision and dismiss the flag as noise — surface it rather than auto-applying.

Save audit votes and rationales to `panel_review_stage4.xlsx`. Apply fixes to the filtered xlsx and document each change in a changelog xlsx.

Read `references/panel_review.md` for audit-prompt templates.

## Hard constraints across all stages

These constraints are not negotiable — they exist because violating them caused real rework on prior runs:

1. **The skill does exactly two things, and nothing else.** (a) It **adds two new columns** — the authored `Rule for LLM` and the `Deviation Level` (subject/site/trial). (b) It **removes non-binary rules** (the binary filter). That is the complete list of changes the skill is permitted to make.

   **Every existing column is preserved verbatim. No exceptions.** `KRI ID`, `Category`, `KRI Name`, `Description`, `Protocol Reference & Quote`, `Severity` — and any other column already present in the input — are copied through byte-for-byte for every surviving rule. Do not reword, reformat, re-case, trim, re-cite, "improve", or otherwise touch a single existing cell. The skill never edits the rules' existing properties; it only authors the new `Rule for LLM`, assigns `Deviation Level`, and drops rules that aren't binary. If you believe an existing column is wrong, surface it in the audit log — do not change it.

2. **Do not change KRI IDs.** Source-file bugs (duplicate IDs, typos, malformed names) are preserved unless the user **explicitly authorizes** a fix. If duplicates exist in the source, surface them in the audit log and ask.

3. **Do not dedupe cross-sheet logical duplicates** (e.g., the same protocol provision encoded once in ELIG and once in OPS) unless the user explicitly authorizes the dedupe. Surface duplicates in the audit log.

4. **Audit log is mandatory** — every drop and every modification must be captured in the audit/changelog xlsx with a one-line reason.

5. **Protocol PDF is the only source of truth.** The Golden Set's text is a starting hypothesis. Never invent specifics the protocol doesn't authorize. The single most common failure mode of past runs was sharpening fuzzy protocol language by inventing tolerances ("25-35 min" instead of "approximately 30 min"); don't do this.

## Default behaviors and user-customization points

Before starting, briefly confirm with the user:
- **Panel engine is fixed:** all panels are Gemini 3.5 Flash, high thinking (not configurable — see "Panel engine").
- **Reviewers per panel** (default 5).
- **Stage 1 nomination:** a rule becomes a drop *candidate* on **any** drop vote (keep-biased).
- **Stage 2 (per family):** drop on a clear confirm-majority (≥ 4/5, or ≥⅔ pooled); restore if defend ≥ 3/5 or confirm ≤ 1; **escalate every 3–2 near-tie**. Equivalent rules (same footnote / procedure / "optional" clause) get ONE pooled verdict. Discretionary/optional procedures are not defensible → confirm-drop.
- **Stage 4 fix threshold** (default ≥ majority).
- **Run Stage 2?** (default yes — strongly recommended; it is the recovery stage).
- **Run Stage 4?** (default yes — recommended).

Then proceed without further confirmation unless something material changes.

## Lessons baked into this skill (so we don't repeat past mistakes)

- **Stay protocol-faithful in both directions.** Never invent numeric tolerances to make a rule "more binary" (a rule with "approximately X" is still binary — the LLM engine handles judgment at runtime), and never omit a checkable detail the protocol *does* state. The authored rule must be exhaustive of what the protocol authorizes and silent on what it doesn't.
- **The authored `Rule for LLM` is the deliverable the engine runs on.** Every analyte, window, required-subset, and condition that lives in a footnote or another column must be folded into it. The single failure this redesign exists to prevent: a footnote acceptability window (e.g. "lab may be drawn up to 4 days prior to the visit") being left as a quote in the Reference column and never entering the rule's `acceptance`/`deviation` logic.
- **Author the source columns as hypotheses.** The `Description` and `Protocol Reference & Quote` are starting points, not authority. Cross-check against the actual protocol PDF, which is the only authority.
- **Timeliness / reporting-deadline rules are kept, not dropped as "process."** "Report/enter within N hours/days of an event" is a binary date-difference check; author it against the closest recorded dates (a date proxy) and name the proxy in `evidence_expected`. Only a true CSR reporting metric ("% of subjects summarised") is dropped.
- **Per-AE timeliness/completeness rules are subject-level**, not site-level. Other CRF data-quality rules tied to a per-subject event are also subject-level. Site-level is for site-wide assets (storage logs, IRB approval, monitoring logs) and trial-level is for cumulative trial state (pause triggers, DMC cadence, enrollment caps).
- **Cross-sheet duplicates of the same protocol provision** get flagged but only deduped on user authorization.
- **Decide equivalent rules as a family; never split them on a 1-vote margin.** A real failure: near-identical "optional per Sponsor" rules (synovial-fluid collection vs physical-performance tests) got opposite verdicts because the defense panel split 3–2 one way and 2–3 the other. Cluster by shared protocol basis and rule the family once; escalate genuine 3–2 ties.
- **Discretionary ≠ binary.** "May / optionally / in a subset / per Sponsor instruction" is not rescued by "if performed, presence is checkable" — discretion isn't a protocol-mandated trigger, so non-performance isn't a deviation. Only a protocol-*defined, recorded* trigger with a *required* action is keepable.
- **One panel-review pass is usually enough.** Diminishing returns past that; the long tail of singleton reviewer opinions is noise, not defects.

## Operating workflow

1. Confirm both inputs (Golden Set xlsx + protocol PDF). Confirm output directory.
2. Confirm default behaviors (reviewers per panel, thresholds, whether to run Stages 2/4). Panel engine is fixed to Gemini 3.5 Flash high thinking.
3. Run Stage 1 — **nomination** (Gemini panel). Produce `stage1_nominations.json` (keeps + drop candidates). Nothing dropped yet.
4. Run Stage 2 — **defense** (Gemini panel) over the drop candidates: confirm-drop / restore / escalate-to-user, keep-biased. Then the **inverse-coverage** Gemini pass over the finalized drop list. Produce the finalized keep set + `dropped_rules_audit.xlsx`.
5. Run Stage 3 — author the YAML `Rule for LLM` for every survivor + assign `Deviation Level`. Validate. (Strip any footnote numbers.)
6. (Recommended) Run Stage 4 — Gemini quality panel + apply consensus fixes (dismiss flags that conflict with user-approved patterns).
7. Assemble the final `<id>_binary_distilled.xlsx` (survivors; other columns verbatim) + dropped-rules table + changelog. Summarize: entered / kept / dropped, where the files are, key drop categories, and anything escalated for the user's call.

## Reference files (load as needed)

- `references/filter_criteria.md` — Full keep/drop rubric. Case A/B/C distinction. Examples.
- `references/rewrite_format.md` — YAML Protocol-rule style guide: the slots, the authoring rules (comprehensiveness, clarity, denominators, no-invent), and worked examples across all five domains.
- `references/deviation_levels.md` — Subject/site/trial assignment rubric with examples.
- `references/panel_review.md` — Multi-reviewer protocols, prompt templates, vote consolidation.

## Helper scripts (in `scripts/`)

These exist to handle deterministic plumbing — file I/O, xlsx formatting, format validation. The classification and authoring logic stays with the agent.

- `scripts/load_golden_set.py` — Load and validate the Golden Set xlsx. Emits JSON.
- `scripts/extract_protocol_pages.py` — Extract a specific page-range from the protocol PDF for cross-check.
- `scripts/write_filtered_xlsx.py` — Write the final filtered xlsx with proper formatting, preserved columns, and the new `Deviation Level` column.
- `scripts/write_audit_xlsx.py` — Write the audit/changelog xlsx.
- `scripts/validate_rule_format.py` — Sanity-check every rule's `Rule for LLM` column: valid YAML with all required Protocol-rule slots present, plus a populated `Deviation Level`.

Run them via `python -m scripts.<name>` from the plugin root, or call directly with `python /path/to/script.py`.
