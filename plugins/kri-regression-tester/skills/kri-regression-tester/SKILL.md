---
name: kri-regression-tester
description: >
  Regression testing for the protocol-kri-extractor skill. Detects when updates
  to the extractor skill would break or invalidate previously approved golden sets.
  Use this skill whenever: the user says "run regression", "regression test",
  "check regression", "did I break anything", or when starting a session where
  the extractor skill will be edited. Also use when the user wants to freeze/vault
  a completed golden set, or asks about the regression vault. Always run regression
  checks before and after editing the extractor skill to catch problems early.
---

# KRI Regression Tester

Ensures that updates to the `protocol-kri-extractor` skill never break previously
approved golden sets. Each approved golden set is frozen in a vault. When the
extractor skill changes, this skill validates every frozen golden set against the
updated rules and reports any conflicts at field-level granularity.

---

## Core Concept

The protocol-kri-extractor produces golden sets — the definitive, verified KRI
collections for clinical trial protocols. Once a golden set is approved by the user,
it is **frozen and immutable**. It represents ground truth.

The extractor skill evolves over time: rules get refined, domains get clarified,
quality checks get added. Every such change risks retroactively invalidating a
previously approved golden set. This skill catches that before it causes damage.

**What this skill does NOT do:**
- It does NOT re-run the extractor on old protocols
- It does NOT validate golden sets against the original protocol PDF
- It does NOT question the correctness of approved golden sets — they are truth

**What this skill DOES do:**
- Validates frozen golden sets against the **current** extractor skill rules
- Diffs the current skill against the skill snapshot from each golden set's approval time
- Reports exactly which changes cause which conflicts, at field-level granularity
- Suggests two remediation paths: fix the skill change, or update the golden set

---

## Vault Location & Structure

```
~/Documents/kri-regression-vault/
  <protocol_id>/
    metadata.json               # Approval metadata
    skill_snapshot/
      SKILL.md                  # Extractor skill at time of approval
    golden_set/
      extracted_kris.json       # THE golden set (primary artifact)
      Extracted_KRIs.xlsx       # Excel version
      raw_SOA.json              # Per-domain extractions
      raw_ELIG.json
      raw_SAF.json
      raw_END.json
      raw_OPS.json
      raw_NDEF.json
      manifest.json             # Protocol structure
      ontology.json             # SoA ontology
      soa_table.csv             # Canonical SoA matrix
      soa_table.json
      footnote_map.json         # Deterministic footnote mapping
      verify_report.json        # Verbatim verification results
      gaps_report.json          # Completeness report
      consistency_report.json   # Consistency report
      crossdomain_dedup_report.json  # Dedup decisions
```

### metadata.json

```json
{
  "protocol_id": "B1481038",
  "protocol_name": "ODYSSEY OUTCOMES",
  "frozen_at": "2026-04-10T14:30:00Z",
  "frozen_by": "user",
  "extractor_skill_version": "git commit hash or date",
  "total_kris": 247,
  "domain_counts": {
    "SOA": 142, "ELIG": 38, "SAF": 22,
    "END": 28, "OPS": 12, "NDEF": 5
  },
  "source_run_dir": "~/Downloads/extractor/B1481038/run_003/",
  "notes": "User's optional notes about this approval"
}
```

---

## Operation 1: Freeze a Golden Set

**Trigger:** User says "freeze this", "vault this", "save to vault", "approve and freeze",
or explicitly asks to preserve a golden set. Also triggered when the extractor skill
asks "Do you want to freeze this golden set?" at the end of a successful run.

### Steps

1. **Identify the source.** Ask the user which run directory to freeze, or detect it
   from the current conversation context (the most recent completed extraction run).

2. **Validate completeness.** Before freezing, verify the source directory has at minimum:
   - `extracted_kris.json` (required — this IS the golden set)
   - `Extracted_KRIs.xlsx`
   At least some of the intermediate artifacts (raw domain files, reports).
   If `extracted_kris.json` is missing, refuse to freeze — it's not a complete run.

3. **Confirm with user.** Show a summary:
   ```
   Ready to freeze:
   - Protocol: [protocol_id]
   - Source: [run directory path]
   - Total KRIs: [count]
   - Domains: SOA=[n], ELIG=[n], SAF=[n], END=[n], OPS=[n], NDEF=[n]
   - Artifacts found: [list]
   
   This will be permanently preserved in the regression vault.
   Confirm? (yes/no)
   ```

4. **Copy artifacts.** Create the vault directory and copy all available artifacts.
   Run `scripts/freeze.py` to handle the copy and generate metadata:
   ```bash
   python <skill-path>/scripts/freeze.py \
     --source <run_directory> \
     --vault ~/Documents/kri-regression-vault \
     --protocol-id <protocol_id> \
     --protocol-name "<protocol_name>" \
     --skill-path <path-to-current-extractor-SKILL.md>
   ```

5. **Snapshot the extractor skill.** Copy the CURRENT version of the extractor
   SKILL.md into `skill_snapshot/SKILL.md`. This is the version that produced and
   was validated against this golden set.

6. **Confirm success.** Tell the user the golden set is frozen and show the vault path.

---

## Operation 2: Run Regression Test

**Trigger:** User says "run regression", "regression test", "check regression",
"did I break anything", "is everything still good". Also should be run as a ritual
at the start of every session where the extractor skill will be edited.

### Overview

The regression test has two layers:
1. **Programmatic checks** — fast, deterministic validation of schema, formats, and
   structural rules (run via `scripts/regression_check.py`)
2. **Semantic analysis** — LLM-powered comparison of skill rule changes against
   golden set content to catch meaning-level conflicts

Both layers run for EVERY frozen protocol in the vault.

### Step 1: Gather Context

1. Read the current extractor skill:
   `~/.claude/skills-repo/protocol-kri-extractor/SKILL.md`

2. List all frozen protocols in the vault:
   `~/Documents/kri-regression-vault/*/metadata.json`

3. For each frozen protocol, read its `skill_snapshot/SKILL.md`

### Step 2: Diff the Skill Versions

For each frozen protocol, compare the **current** extractor SKILL.md against the
**frozen** SKILL.md snapshot. Identify every change:

- Added rules (new quality rules, new domain boundaries, new schema fields)
- Modified rules (changed definitions, tightened criteria, altered severity mappings)
- Removed rules (deleted requirements)
- Structural changes (renamed fields, changed schema, altered output format)

Categorize each change as:
- **Additive**: New field, new column, new artifact, new quality rule that checks
  something not previously checked. These won't exist in old golden sets — that's
  expected, not a regression.
- **Semantic**: Changed meaning of existing rules, tightened/loosened criteria,
  moved domain boundaries, altered severity definitions, changed extraction logic.
  These CAN break frozen golden sets.
- **Structural**: Renamed fields, changed JSON schema, altered Excel format.
  These WILL break frozen golden sets if the old format no longer matches.

### Step 3: Programmatic Checks

Run `scripts/regression_check.py` for deterministic validation:

```bash
python <skill-path>/scripts/regression_check.py \
  --vault ~/Documents/kri-regression-vault \
  --skill <path-to-current-extractor-SKILL.md>
```

This script checks every frozen golden set against the current skill's rules:

**Schema checks:**
- All required fields present in every KRI
- Field names match the current schema exactly
- No unexpected fields (unless from an older format — flag, don't fail)

**Format checks:**
- `kri_id` follows the current ID pattern (e.g., `SOA-V1-001`, `ELIG-INC-001`)
- `severity` values are in the current allowed set (`critical`, `major`, `minor`)
- `category_id` values are in the current domain list
- `combined_ref` format matches current rules
- `supporting_quote` doesn't start/end with `"` (Quality Rule 11)
- No duplicate page numbers in `protocol_reference` (Quality Rule 12)

**Domain boundary checks:**
- For each KRI, verify its `category_id` is correct according to current domain
  boundary rules (Rule 1: SOA owns procedure-at-visit, Rule 2: SAF owns thresholds,
  Rule 3: OPS owns methodology)
- Flag any KRI that would belong in a different domain under current rules

**Quality rule checks:**
- Validate each KRI against all numbered quality rules in the current skill
- For each rule, check every applicable KRI

**Atomicity checks:**
- Flag KRIs that mention multiple procedures, multiple visits, multiple endpoints
  in a single `rule_for_llm` (potential atomicity violations under current rules)

**NDEF classification checks:**
- Scan `rule_for_llm` for NDEF trigger phrases defined in the current skill
  ("clinically significant", "investigator discretion", "as appropriate", etc.)
- Flag non-NDEF KRIs that contain these phrases

The script outputs `regression_report.json` with every finding, organized by
protocol, domain, and KRI, with field-level detail.

### Step 4: Semantic Analysis

After the programmatic checks, perform LLM-powered analysis for things that
can't be caught by pattern matching:

1. **Read each skill change** identified in Step 2 that was categorized as "semantic."

2. **For each semantic change, scan every frozen golden set:**
   - Does any KRI's content contradict this new/modified rule?
   - Would any KRI need to be rewritten to comply with the updated rule?
   - Does the change alter the meaning or intent of any existing KRI?

3. **Cross-reference with git history** (if available):
   ```bash
   cd ~/.claude/skills-repo && git log --oneline -20 protocol-kri-extractor/SKILL.md
   ```
   Map each identified conflict to a specific commit or set of changes.

4. **Cross-reference with conversation context:** If currently in a session where
   skill edits were made, identify which specific edits (from the conversation)
   caused each conflict.

### Step 5: Report

Present findings in conversation, organized for clarity:

**If no regressions found:**
```
Regression test PASSED for all [N] frozen protocols.
- [Protocol A]: [X] KRIs checked — all clear
- [Protocol B]: [Y] KRIs checked — all clear
[summary of skill changes detected and why they don't conflict]
```

**If regressions found:**
For each regression, report:

1. **What broke:**
   - Protocol: [protocol_id]
   - Domain: [category_id]
   - KRI: [kri_id] — [kri_name]
   - Field: [field_name]
   - Current value: [what the golden set has]
   - Problem: [why this violates the updated skill]

2. **What caused it:**
   - Skill change: [quote the specific rule that changed]
   - Diff: [show the before/after from the skill snapshots]
   - Git commit: [if available, which commit introduced this]
   - Conversation edit: [if applicable, which edit in this session]

3. **Suggested remediation (two options):**
   - **Option A — Revert/adjust the skill change:** [specific suggestion for how
     to modify the new rule so it doesn't conflict with the golden set]
   - **Option B — Update the golden set:** [specific suggestion for what to change
     in the frozen golden set, and confirmation that the user must approve this]

### Step 6: Handle Additive Changes

For changes categorized as "additive" (new fields, new columns, new artifacts):

```
Additive change detected:
- The current skill now requires field "[new_field]"
- This field does NOT exist in the following frozen golden sets:
  - Protocol A ([X] KRIs affected)
  - Protocol B ([Y] KRIs affected)

This is expected — the field was added after these golden sets were approved.
Would you like me to update the frozen golden sets to include this field?
```

If the user says yes, guide them through updating each affected golden set
(or offer to do it programmatically if the field can be computed).

---

## Operation 3: Update a Frozen Golden Set

**Trigger:** User explicitly asks to update a frozen golden set, or approves an
update suggested during regression testing.

### Rules

- **NEVER update silently.** Every change to a frozen golden set must be explicitly
  confirmed by the user.
- **Log every change.** Append to `<protocol_id>/update_log.json`:
  ```json
  {
    "updates": [
      {
        "timestamp": "2026-04-13T10:00:00Z",
        "reason": "Added 'domain' field per skill update",
        "kris_affected": ["SOA-V1-001", "SOA-V1-002", ...],
        "field": "domain",
        "change_type": "field_added",
        "approved_by": "user"
      }
    ]
  }
  ```
- **Re-snapshot the skill.** After updating a golden set, copy the current
  extractor SKILL.md into `skill_snapshot/SKILL.md` (the golden set now aligns
  with the current skill).
- **Update metadata.** Bump the `frozen_at` timestamp and update domain counts
  if any KRIs were reclassified.

---

## Important Principles

1. **Golden sets are truth.** Never question the correctness of a frozen golden set.
   The regression test checks alignment with the skill, not correctness of the KRIs.

2. **Field-level granularity.** Every finding must specify the exact protocol, domain,
   KRI ID, and field affected. "SOA domain has problems" is not acceptable — name
   every KRI and every field.

3. **Two-way remediation.** Always suggest both directions: fix the skill or fix the
   golden set. Let the user decide.

4. **Additive vs. semantic.** Distinguish clearly between "this field didn't exist yet"
   (expected, offer to backfill) and "this rule now contradicts the golden set"
   (regression, must be resolved).

5. **No silent changes.** Every vault modification must be user-confirmed and logged.

6. **Track causation.** Don't just report WHAT broke — report WHY. Diff the skill
   versions, check git history, trace to specific edits.
