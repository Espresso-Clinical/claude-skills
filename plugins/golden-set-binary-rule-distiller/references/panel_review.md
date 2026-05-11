# Panel review — Stages 2 and 4

Stages 2 (panel filter) and 4 (quality audit) use parallel reviewer agents to apply consensus pressure to the keep/drop and rewrite decisions. This file gives prompt templates, vote consolidation, and consensus thresholds.

## When to run panel reviews

- **Stage 2** runs after Stage 1 (filter). Reviewers re-evaluate the kept rules and flag any that should still be dropped. Run when the user wants more rigor than a single-pass filter.
- **Stage 4** runs after Stage 3 (rewrite). Reviewers audit the rewritten rules for clarity, protocol-faithfulness, and correctness of Deviation Level. Run when the user wants to verify the rewrite landed cleanly.

Both stages are optional. Default for both is "yes, run them" unless the user opts out.

## Mechanics

- Spawn N parallel reviewer agents (default 10, minimum 5).
- Each reviewer has access to the protocol PDF and the current state of the Golden Set.
- Each reviewer flags rules they think are problematic, with a short reason.
- Consolidate votes per rule: count how many reviewers flagged each rule.
- Apply changes at the consensus threshold (default ≥ 4 of 10 votes).

The consensus threshold matters. Singleton flags from one reviewer are noise — they reflect that reviewer's particular reading, not a defect in the rule. Real issues get flagged by multiple reviewers independently.

## Stage 2 — Panel filter prompt template

When spawning each Stage 2 reviewer, use a prompt of this shape:

```
You are reviewer #<N> of <total> doing an INDEPENDENT audit of a clinical-trial Golden Set's binary-rule filter.

CONTEXT
The Golden Set <protocol_id> has <X> rules across <Y> sheets. A prior filter pass classified each rule as binary-checkable or not. Your job is to find rules that should NOT have passed — rules that are actually descriptive, definitional, statistical, or otherwise NOT able to produce a clear binary deviation from data.

FILTER CRITERIA (a rule must satisfy ALL three to be kept):
1. Binary checkable — data either complies or doesn't.
2. Tied to trial data — subject-, site-, or trial-level data collected/reported during the trial.
3. Produces a clear deviation when violated — a specific anomaly can be flagged.

DROP if the rule is primarily:
- Pure endpoint definition
- Pure population definition (ITT/FAS/PP/Safety)
- Statistical methodology (MMRM, Kaplan-Meier, hierarchical testing)
- Reporting metrics ("% of subjects with X are reported")
- Exploratory analyses or correlations
- Permissive options ("sponsor may reduce enrollment...")
- Broad meta-compliance umbrellas (generic "follow GCP")
- Pure threshold/term definitions with no embedded action
- Subjective judgment with no objective data anchor

INSTRUCTIONS
- Read the protocol PDF at <protocol_pdf_path> and the kept-rule JSON at <kept_rules_json_path>.
- For each rule, cross-check against the protocol's actual text at the cited reference.
- Treat the source `Rule for LLM` column with limited trust — it is often malformed. Read all columns holistically.
- Be holistic and judicious. The prior pass already removed obvious non-checkable rules. Look for residual cases that slipped through.
- The ~330 SOA visit×procedure rules typically follow a uniform template; if the template is correct, flag the TEMPLATE issue once if you find one — don't list 330 instances.

OUTPUT
A markdown table:
| KRI ID | Sheet | Reason to Drop |

After the table, give a 1-2 sentence overall verdict on filter quality.

Be independent — do not anchor on any prior reviewer. Make your own judgment from the rule contents and the protocol.
```

## Stage 4 — Quality audit prompt template

```
You are reviewer #<N> of <total> doing an INDEPENDENT audit of the rewritten `Rule for LLM` column.

CONTEXT
The Golden Set <protocol_id> has <X> rules with each `Rule for LLM` rewritten in this format:
  SOURCE: <data the engine should pull, in plain language>
  CHECK: <the precise compliance condition>
  DEVIATION: <the exact condition that flags a deviation>
A `Deviation Level` column (subject / site / trial) was also added.

YOUR JUDGMENT TASK — for every rule, decide whether the rewrite is:
(a) Sharp, simple, machine-readable.
(b) Internally consistent with the other columns (KRI Name, Description, Protocol Reference & Quote) AND with the protocol PDF.
(c) Capable of producing a real binary deviation.
(d) Tagged with the right Deviation Level.

FLAG CATEGORIES
- "unclear": SOURCE/CHECK/DEVIATION wording is vague or missing data.
- "inconsistent": rule contradicts/drifts from the protocol text or other Golden Set columns.
- "non-deviation": DEVIATION doesn't describe a real anomaly.
- "wrong-level": Deviation Level mis-assigned.
- "broken-template": SOURCE/CHECK/DEVIATION structure missing/malformed.
- "fabricated-specifics": rule introduces numbers, tolerances, or fields not present in the protocol PDF.

INSTRUCTIONS
- Read the protocol PDF at <protocol_pdf_path>.
- For every rule, open the protocol at the cited reference and verify the rewrite against the actual protocol text.
- The "fabricated-specifics" flag is especially important — flag any rule whose CHECK or DEVIATION introduces specifics the protocol does not authorize (invented tolerances, invented field lists, invented thresholds).
- The ~330 SOA visit×procedure rules follow a uniform template; if the template is correct, all instances pass — flag the TEMPLATE issue once if you find one, don't list 330 instances.

OUTPUT
A markdown table (cap at ~25 most material flags):
| KRI ID | Flag | Issue (1 line) | Suggested fix (1 line) |

After the table, give a 1-2 sentence overall verdict on whether the rewrite is production-ready.

Be independent. Verify each rule on its merits against the protocol.
```

## Vote consolidation

After all reviewers complete:

1. Aggregate flags per (KRI ID, sheet, flag-category) tuple.
2. Count how many reviewers flagged each item.
3. Sort by vote count, descending.
4. Apply changes per the consensus threshold:
   - **Default threshold: ≥ 4 of 10 votes** (= ≥ 40% panel consensus).
   - Higher = more conservative (fewer changes, more confidence per change).
   - Lower = more aggressive (more changes, more noise risk).
5. Singleton flags (1 vote) are not acted on automatically. They get logged in the panel review xlsx for the user's awareness, but they don't drive changes.

## Output to panel_review.xlsx

Save the consolidated panel review to a workbook with these sheets:

- **Summary** — vote-tier table: how many items at each vote level (10/10, 9/10, …, 1/10), with a per-tier recommendation.
- **Reviewer Counts** — how many flags each reviewer raised.
- **Consolidated Flags** — one row per flagged item, columns for KRI ID, sheet, vote count, primary flag category, each reviewer's vote and reason (or blank if they didn't flag).

Color-code the consolidated-flags rows by vote tier (e.g., dark green for unanimous, light green for ≥ 7, yellow for ≥ 5, orange for ≥ 3, gray for ≤ 2).

## Diminishing returns — stop early

The first panel pass catches the real issues. The second pass catches a few more. By the third pass you're chasing singleton opinions and over-correcting. **Default: one panel pass per stage. Cap at two.**

A useful signal: if the high-consensus (≥ 7/10) flag count drops by more than 50% between iterations, you've extracted the real issues. The long tail of 1-3 vote singletons is noise from the diversity of reviewer perspectives, not real defects.

## Recovering from a bad iteration

A common failure mode: trying to fix every flag by inventing specificity in the rule text (e.g., adding a tolerance number to make a fuzzy rule "more binary"). This sharpens the rule beyond what the protocol authorizes, and the next panel pass flags it as "fabricated-specifics".

If this happens, walk back the fabrications in a surgical pass:
- Remove invented numeric tolerances and restore the protocol's wording verbatim (use "substantially deviates per applicable sponsor SOP" for fuzzy targets).
- Remove invented field lists and restore the protocol's clause structure.
- Remove engine-implementation guidance from rule bodies.

A walk-back pass is short and safe — it adds no new inventions. Document each walk-back in the changelog.
