# Panel review — Stages 1 (nominate), 2 (defend), and 4 (quality)

**All panels run on Gemini 3.5 Flash at high thinking — never Claude sub-agents.** Call `gemini_extract.call_gemini(prompt, system_prompt=..., temperature=..., task="judge")` (task="judge" = high thinking budget) in parallel threads with a temperature spread (0.1–0.3) for independence. See SKILL.md "Panel engine" for the import. This file gives the prompt templates, vote consolidation, and thresholds.

## The filter is keep-biased: nominate, then defend

Dropping a rule is irreversible, so it takes TWO panels agreeing across TWO opposite tasks:
- **Stage 1 (nominate)** casts a wide net — each reviewer flags drop candidates. A rule becomes a *candidate* on **any** drop vote. **Nothing is dropped here.**
- **Stage 2 (defend)** is adversarial in the other direction — for each candidate, reviewers try to KEEP it. A candidate is dropped only if the defense fails; otherwise it is **restored** or **escalated to the user**.
- An **inverse-coverage** pass then reviews the whole finalized drop list for systematic over-dropping.

**Keep is always the default. Borderline → keep or escalate, never a silent drop.** No single reviewer can drop a rule.

## Mechanics

- Run N independent Gemini reviewers (default 5) in parallel, temperature-spread.
- Each reviewer sees the protocol PDF (cited pages + footnotes) + the relevant rules.
- Consolidate votes per rule/candidate; apply the stage's keep-biased threshold (below).
- Singleton opinions are noise; multi-reviewer agreement is signal.

## Stage 1 — Drop-nomination prompt

```
You are reviewer #<N> of <total> independently screening a clinical-trial Golden Set for rules that CANNOT be turned into a binary, deviation-producing rule.

KEEPABLE: a binary check can be authored — the rule has a measurable data anchor (number, date, presence/absence, category), even if the threshold is fuzzy ("approximately").
NOMINATE FOR DROP only if the rule is primarily: a pure endpoint/population definition, statistical methodology, a reporting metric, an exploratory analysis/correlation, a permissive option ("may"), a broad meta-compliance umbrella ("follow GCP"), a pure term/threshold definition with no embedded action, a pure aspiration, or purely subjective investigator judgment with no objective anchor.

KEEP IS THE SAFE DEFAULT — when unsure, do not nominate. You are flagging only the clearly non-binary.

INPUTS: rules at <rules_path>; protocol PDF at <pdf> (read cited pages + footnotes).
SOA visit×procedure rules are templated — treat as one template, flag a template issue once, don't enumerate.

OUTPUT: ONLY strict JSON — rules you nominate to DROP:
[{"kri_id":"...","drop_reason":"<=15 words"}]
Return [] if none.
```
Consolidate: any rule with ≥ 1 drop nomination → **candidate** (carry its nomination count + reasons). Unanimous-keep rules are locked and skip Stage 2.

## Stage 2 — Drop-defense prompt (adversarial; the recovery stage)

```
You are reviewer #<N> of <total>. The rules below were NOMINATED by another panel to drop as "not binary". Your job is the OPPOSITE: for each, genuinely try to DEFEND keeping it.

For each candidate decide:
- "defend": there IS a protocol-grounded way to author a binary, deviation-producing rule — a measurable anchor, a footnote that makes it testable, OR a legitimate trial-level / site-level governance KRI (interim/enrollment trigger, cohort gating, DSMB approval, randomization stratification, IRB approval, IP accountability, etc.). State the basis.
- "confirm": after genuinely trying, there is no objective, checkable anchor — it is truly definitional / permissive / subjective.

GUARDRAIL — discretionary is NOT binary: a procedure the protocol leaves to discretion ("may", "optionally", "in a subset", "per Sponsor instruction", "per investigator judgment") is NOT defensible by arguing "if performed, presence is checkable" — discretion is not a protocol-mandated trigger, so non-performance is not a deviation → "confirm". Only "defend" a conditional rule when the trigger is a protocol-DEFINED, recorded clinical condition (e.g. "if total bilirubin abnormal", "women of childbearing potential") AND the protocol REQUIRES the action when it holds.

BIAS TOWARD "defend" for genuine data-checks, but apply the guardrail above strictly. Only "confirm" if you cannot find any protocol basis to keep it.

INPUTS: candidates at <candidates_path>; protocol PDF at <pdf> (read cited pages + footnotes).

OUTPUT: ONLY strict JSON:
[{"kri_id":"...","verdict":"defend"|"confirm","basis":"<=20 words"}]
```
Consolidate **per family** (keep-biased). First **cluster candidates that share the same protocol basis** — same footnote, same procedure repeated across visits, same "optional per Sponsor" clause (e.g. all synovial-fluid rules; all physical-performance-test rules) — and give each family ONE verdict applied to every instance (pool the family's votes; never split near-identical rules on a 1-vote margin). Then:
- **Drop** on a clear confirm-majority: **≥ 4/5 confirm** (or ≥ ⅔ of pooled family votes). A bare 3–2 is NOT decisive.
- **Restore** if defend ≥ 3/5 (or confirm ≤ 1).
- **Escalate to the user** every 3–2 near-tie and every family the panel can't clearly resolve. Never auto-decide a knife-edge vote; keep is the default.

## Inverse-coverage pass (single Gemini call, after Stage 2)

```
Below is the FULL list of rules a filter finalized as DROPPED, each with its reason. Review them as a SET. Identify any rule — or any whole CLASS of rule — that was wrongly removed, especially legitimate trial-level / site-level governance KRIs or anything with a real protocol-grounded data check.

OUTPUT: ONLY strict JSON — rules to restore or escalate:
[{"kri_id":"...","why_keep":"<=20 words"}]
Return [] if the drop list is clean.
```
Anything returned is **restored or escalated to the user** before authoring begins.

## Stage 4 — Quality audit prompt template

```
You are reviewer #<N> of <total> doing an INDEPENDENT audit of the authored `Rule for LLM` column.

CONTEXT
The Golden Set <protocol_id> has <X> rules with each `Rule for LLM` authored from scratch as a YAML "Protocol rule" — a data-agnostic clinical statement, with slots:
  intent: <one-line purpose>
  applies_to: <clinical denominator — e.g. "enrolled subjects", "every SAE", "every activated site">
  evidence_expected: <the clinical artifact that must exist; never a table/column>
  acceptance: <open set of sub-slots: timing / required / preferred / conditional / pass / override>
  deviation: <the violation in clinical terms>
  provenance: <terse section + page; NO footnote numbers>
A `Deviation Level` column (subject / site / trial) was also assigned.

YOUR JUDGMENT TASK — for every rule, decide whether the authored rule is:
(a) EXHAUSTIVE — every checkable detail in the protocol/footnotes/columns (analytes, time & acceptability windows, required-subsets, AND/OR logic, conditional triggers, pass/deviation definitions) is present. This is the priority check.
(b) CLEAR — plain clinical language in every slot; no meta-commentary ("presence and dating only — does NOT require X"), NO footnote numbers anywhere ("[footnote 14]", "Footnote 13", even in provenance), no filler ("active subject expected to attend…").
(c) Well-formed — valid YAML, all six top-level slots present; `applies_to` is a clinical denominator (not "randomized"/"active"/a data filter); `evidence_expected` names an artifact (not a restated criterion); no table/column/code names anywhere.
(d) Internally consistent with the other columns AND the protocol PDF, produces a real binary deviation, and has the right Deviation Level.

FLAG CATEGORIES
- "omitted-detail": a checkable detail present in the protocol/footnotes/columns is missing from the rule's slots (e.g. an acceptability window left only in the quote, an analyte dropped, an OR collapsed to AND). THE MOST IMPORTANT FLAG.
- "jargon": meta-commentary, self-referential tags, or a footnote number ("[footnote 12]", "Footnote 14") in a slot instead of a plain clinical statement.
- "filler": boilerplate that adds length without a check; should be trimmed.
- "bad-denominator": `applies_to` is a data filter or wrong population ("randomized" for an eligibility criterion, "active subject").
- "restated-criterion": `evidence_expected` restates the criterion instead of naming a clinical artifact.
- "names-data": rule names a table/column/code/join (belongs downstream, not in the Protocol rule).
- "unclear": a slot is vague or missing data the engine needs.
- "inconsistent": rule contradicts/drifts from the protocol text or other Golden Set columns.
- "non-deviation": the `deviation` slot doesn't describe a real anomaly.
- "wrong-level": Deviation Level mis-assigned.
- "broken-template": YAML malformed or a required slot missing.
- "fabricated-specifics": rule introduces numbers, tolerances, or fields not present in the protocol PDF.

INSTRUCTIONS
- Read the protocol PDF at <protocol_pdf_path>.
- For every rule, open the protocol at the cited reference — AND read every footnote attached to it — and verify the authored rule against the actual protocol text.
- "omitted-detail" is the priority flag: compare the footnotes/quotes against the rule and flag anything checkable that the protocol states but the rule does not encode.
- "fabricated-specifics" is its mirror: flag any rule whose `acceptance`/`deviation` introduces specifics the protocol does not authorize (invented tolerances, field lists, thresholds).
- The ~330 SOA visit×procedure rules follow a uniform template; if the template is correct, all instances pass — flag the TEMPLATE issue once if you find one, don't list 330 instances.

OUTPUT
A markdown table (cap at ~25 most material flags):
| KRI ID | Flag | Issue (1 line) | Suggested fix (1 line) |

After the table, give a 1-2 sentence overall verdict on whether the authored rules are production-ready.

Be independent. Verify each rule on its merits against the protocol.
```

## Vote consolidation

After all reviewers complete:

1. Aggregate flags per (KRI ID, sheet, flag-category) tuple.
2. Count how many reviewers flagged each item.
3. Sort by vote count, descending.
4. Apply changes per the stage's threshold:
   - **Stage 1 (nominate):** any drop vote → candidate (keep-biased; the bar to *survive* is in Stage 2, not here).
   - **Stage 2 (defend, drops):** cluster equivalent candidates into families and rule per family; drop on a clear ≥ 4/5 (or ≥⅔ pooled) confirm; restore if defend ≥ 3/5; **escalate every 3–2 near-tie**. Discretionary/optional procedures → confirm-drop (not defensible).
   - **Stage 4 (fixes):** default ≥ majority (≥ 3/5 or ≥ 2/3). Higher = more conservative; lower = noisier.
5. Singleton flags (1 vote) are not acted on automatically. They get logged for the user's awareness, but they don't drive changes. A panel flag that conflicts with a user-approved pattern is dismissed as noise (surface it, don't auto-apply).

## Output to panel_review.xlsx

Save the consolidated panel review to a workbook with these sheets:

- **Summary** — vote-tier table: how many items at each vote level (for a 5-panel: 5/5, 4/5, …, 1/5), with a per-tier recommendation.
- **Reviewer Counts** — how many flags each reviewer raised.
- **Consolidated Flags** — one row per flagged item, columns for KRI ID, sheet, vote count, primary flag category, each reviewer's vote and reason (or blank if they didn't flag).

Color-code the consolidated-flags rows by vote tier (e.g., dark green for unanimous, lighter green for a clear majority, orange for a bare majority, gray for singletons).

## Diminishing returns — stop early

The first panel pass catches the real issues. The second pass catches a few more. By the third pass you're chasing singleton opinions and over-correcting. **Default: one panel pass per stage. Cap at two.**

A useful signal: if the high-consensus (clear-majority) flag count drops by more than 50% between iterations, you've extracted the real issues. The long tail of singleton (1-vote) flags is noise from the diversity of reviewer perspectives, not real defects.

## Recovering from a bad iteration

A common failure mode: trying to fix every flag by inventing specificity in the rule text (e.g., adding a tolerance number to make a fuzzy rule "more binary"). This sharpens the rule beyond what the protocol authorizes, and the next panel pass flags it as "fabricated-specifics".

If this happens, walk back the fabrications in a surgical pass:
- Remove invented numeric tolerances and restore the protocol's wording verbatim (use "substantially deviates per applicable sponsor SOP" for fuzzy targets).
- Remove invented field lists and restore the protocol's clause structure.
- Remove engine-implementation guidance from rule bodies.

A walk-back pass is short and safe — it adds no new inventions. Document each walk-back in the changelog.
