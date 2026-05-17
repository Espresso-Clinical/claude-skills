---
name: protocol-kri-extractor
description: >
  Extracts Key Risk Indicators (KRIs) from clinical trial protocol PDFs across
  the ELIG, SAF, END, and OPS domains, and produces the authoritative Golden Set
  for those domains — the definitive, verified, structured list of monitoring
  rules for a given protocol. Use this skill whenever the user wants to: parse a
  clinical protocol for ELIG / SAF / END / OPS KRIs, extract eligibility / safety /
  endpoint / operational rules from a protocol PDF, or build a non-SOA monitoring
  rule set. Schedule-of-Activities (SOA) extraction is OUT OF SCOPE for this
  skill — it is handled by the separate `soa-kri-extractor` skill. Works on any
  Phase 2/3 trial regardless of sponsor or format.
---

# Protocol KRI Extractor

## Ultimate Goal

This skill **creates the Golden Set for the ELIG, SAF, END, and OPS domains** — the authoritative, verified collection of non-SOA KRIs for a given clinical trial protocol. The Golden Set is the primary deliverable. It is not a comparison tool, a validation tool, or a QC tool against a pre-existing set. The skill itself, working from the protocol PDF alone, produces the ground-truth KRI list for these 4 domains.

The output (`golden_set.json` + `Extracted_KRIs.xlsx`) is the source of truth — not derived from any prior set and not judged against any prior set.

**Scope boundary**: Schedule-of-Activities (SOA) extraction is handled by the separate `soa-kri-extractor` skill. This skill explicitly excludes SOA content (the SoA table, its footnotes, procedure-at-visit rules, visit windows, cross-visit timing, visit-schedule narrative). The SOA Golden Set is produced by `soa-kri-extractor`; the ELIG/SAF/END/OPS Golden Set is produced here. The two are merged downstream of both skills.

---

Extracts monitoring rules (KRIs) from any clinical trial protocol PDF for the ELIG, SAF, END, and OPS domains.
Protocol-agnostic: no hardcoded section names, visit labels, or therapeutic areas.

---

## ⚠️ META-RULE — Skill Updates Are Additive Only (NEVER violate this)

Every refinement, update, or improvement to this skill is **additive**. It adds to what is already defined. It never removes, overwrites, or silently replaces previous rules.

### Absolute no-removal rule

**No step, no definition, no instruction, no rule in this skill is ever removed, omitted, skipped, or silently replaced.** Every step, every rule, every definition, and every instruction documented here (in `SKILL.md`, in `references/steps.md`, and in the scripts) is **MANDATORY** — not optional, not "for efficiency", not "when time permits", not "when relevant". Nothing is a suggestion. Nothing is skippable. Nothing is a substitute for something else.

The ONLY way something gets removed, changed, weakened, or replaced is if the user has **explicitly said so** ("delete this", "replace X with Y", "this is no longer needed"). Even then, the change must be made as an explicit, documented edit — never as a silent drop and never as a side effect of another change.

Every update the user uploads to this skill is ONLY an **addition**, **refinement**, **clarification**, or **adjustment**. It is NEVER a substitute for something that already exists and NEVER causes something else to break — unless the user has explicitly said so.

- **Never delete** a rule that was not explicitly requested to be deleted
- **Never overwrite** a previous definition unless the user explicitly said "replace this"
- **Never skip, defer, or reorder** any step for speed, efficiency, brevity, cost, or convenience — if it is documented here, it runs in full
- **Never "summarize", "consolidate", or "simplify"** rules into shorter versions that drop details, soften gating, or lose scope
- **Never weaken mandatory language** ("MUST", "BLOCKING", "mandatory") into optional language ("should", "recommended", "when possible")
- When in doubt: **add** the new rule alongside the old one, clearly labeled
- If a new rule contradicts an old rule, **surface the conflict** to the user — do not silently resolve it by deleting one side
- De-duplication, protocol-wide orphan scan, verbatim verification, full accuracy judging, Compliance Monitor, and all other steps documented here remain in force forever unless explicitly removed
- When presenting "new" ideas to the user, check first whether they are already documented here — do not re-propose things that already exist in the skill

### What counts as "silent removal" (forbidden)

A step, rule, or definition is considered "silently removed" if ANY of these happen without an explicit user instruction:

- It is deleted from `SKILL.md`, `references/steps.md`, or any script
- It is rewritten in a way that drops its requirements or softens its gating
- Its mandatory language is weakened to optional language
- It is moved to a different location and loses visibility
- Its gating (blocking gate, phase gate, consensus threshold, pass threshold) is relaxed
- Its scope is narrowed (e.g. "all KRIs" becomes "a sample of KRIs", "every page" becomes "cited pages")
- It is replaced by a reference to a different step that does not do the same thing
- It is marked as "deferred", "optional", "if time permits", or "future work"

Any of these is a **meta-rule violation**. If any reviewer, user, or future Claude instance notices a discrepancy between what the user specified in conversation and what is actually in the skill files — the discrepancy must be surfaced immediately and repaired by **restoring the missing content**, not by rationalizing the gap, not by claiming the absence is intentional, and not by proposing a lesser substitute.

### Audit obligation

Before any skill execution and before any skill edit, the agent MUST audit the skill files against known prior user instructions. If anything is missing, stop and restore it before proceeding with the current task.

This rule applies to Claude when editing this file, and to the skill pipeline itself when producing KRIs.

---

## ⚠️ MANDATORY — Compliance Monitor Agent (runs throughout entire pipeline)

Every execution of this skill MUST launch a **Compliance Monitor Agent** at the very start — before any other step begins. This agent runs **in parallel** with the entire pipeline from start to finish. It is not optional. It cannot be skipped.

### Purpose

The Compliance Monitor Agent is a babysitter agent that ensures the main pipeline agent and all sub-agents follow every instruction in this skill exactly as written. It monitors, verifies, and enforces compliance with the skill's workflow, rules, and output requirements.

### When to launch

Launch the Compliance Monitor Agent **immediately** when the skill is activated on a protocol — before Step 0 begins. It runs in the background throughout the entire pipeline and is consulted at each phase gate.

### What the Compliance Monitor Agent does

**1. Step Completion Verification (after each step)**
After each pipeline step completes, the monitor verifies:
- The step was actually executed (not skipped)
- All required intermediate artifacts for that step were produced and saved to disk
- The artifacts match the expected schema/format defined in this skill
- No instructions from this skill relevant to that step were ignored

**2. Mandatory Artifact Checklist**
The monitor maintains and checks this artifact checklist throughout execution:

| Step | Required Artifact(s) | Verified? |
|------|---------------------|-----------|
| 1A | `manifest.json` (ELIG/SAF/END/OPS section map only — no SOA mapping) | |
| 2 (per domain) | `raw_{DOMAIN}.json` for each of ELIG/SAF/END/OPS, `{DOMAIN}_adjudication.json` | |
| 2 (multi-model) | 5 Claude agent outputs + 5 Gemini agent outputs per domain | |
| 2 (consensus) | Tier 1 auto-approved, Tier 2 decision table shown to user, Tier 3 → promotion pipeline (`{domain}_tier3_filtered.json`) | |
| 2 (per-domain checkpoint) | `{domain}_manual_review_decisions.json` — user acceptance/rejection record for all T2 + promoted T3 KRIs | |
| 2.5 (obligation inventory) | `{domain}_obligation_inventory.json` — all obligation sentences found, with KRI coverage check | |
| **3.5** | **`orphan_scan_report.json` (primary section sweep + secondary page sweep + consolidation + cross-check + classification + user decisions + promoted orphans appended to `raw_{DOMAIN}.json`). SOA-flavored candidates dropped with reason `out_of_scope_soa`.** | |
| 3A | `gaps_report.json` (obligation-inventory coverage) + H4 SAF heuristic | |
| **3B** | **`accuracy_report_full.json` (100% KRI coverage, 5-judge cross-model panel, 0 FAIL, 0 unresolved FLAG — blocking)** | |
| 3C | `consistency_report.json` | |
| 3D | `verify_report.json` — must show 100% pass | |
| 4A | `extracted_kris.json`, `Extracted_KRIs.xlsx` (4 domain sheets: ELIG, SAF, END, OPS + Summary) | |
| 4A-Dedup | `dedup_report.json` (contains `cross_domain` — including any SOA-flavored deletions, `intra_domain`, and `kept_despite_similarity` sections) | |

**3. Multi-Model Extraction Enforcement**
For Step 2, the monitor MUST verify:
- Exactly 5 Claude sub-agents were launched per domain
- Exactly 5 Gemini agents were launched per domain (via `gemini_extract.py`)
- All 10 agent outputs were collected and merged
- Consensus tiers were correctly applied:
  - 7-10 agents (T1) → auto-approved (verify these went into the domain's KRI set)
  - 4-6 agents (T2) → Step 2.6 auto-judgment (6-judge neutral panel) produced a per-KRI pre-decision. `{domain}_autojudgment_report.json` and `{domain}_manual_review_decisions.json` exist with full layer-by-layer results. In `--auto-approve-unanimous` mode (default ON), flagged items default to rejected and surface at end-of-run in `flagged_review_decisions.json` (Step 4A-FlaggedReview). In `--interactive` mode, every flagged row has an explicit user decision.
  - 1-3 agents (T3) → Tier 3 promotion pipeline (T3-1 Coverage / T3-2 Verbatim / T3-2.5 Atomicity / T3-3 Panel / T3-4 Aggregate) handled by Step 2.6. NOT auto-deleted. Verify `{domain}_tier3_filtered.json` exists with per-KRI dispositions.
- The domain processing order was sequential: ELIG → SAF → END → OPS
- Each domain completed fully (Step 2.6 produced its decision table, flagged items either resolved in `--interactive` mode OR defaulted to rejected in auto-approve mode) before the next domain began
- Every extractor prompt included the "Out of scope — SOA" methodology block (see `references/steps.md`)

**4. Blocking Gate Enforcement**
The monitor enforces all blocking gates:
- Step 3D must report 100% pass before Step 4A can begin
- If Step 3D has failures, the pipeline must stop and fix them before proceeding
- The user must be asked about golden set comparison at Step 4B

**5. Rule Compliance Spot-Checks**
The monitor periodically spot-checks KRIs against the quality rules in this skill:
- Atomicity: each KRI is one verifiable check about one thing
- Domain boundaries: SAF owns thresholds + reporting, OPS owns methodology, ELIG owns inclusion/exclusion criteria, END owns endpoints + governance; "procedure at visit" is OUT OF SCOPE (soa-kri-extractor)
- Field format: `supporting_quote` has no outer quotes, `combined_ref` uses em dash, no duplicate page numbers
- No SOA-flavored KRIs survived dedup — every "procedure at visit" / visit-window / cross-visit-timing KRI must be either skipped at extraction or deleted at dedup with reason `out_of_scope_soa`

**6. Reporting**
At each phase gate (end of Phase 1, end of Phase 2, end of Phase 3, end of Phase 4), the Compliance Monitor reports to the user:
```
COMPLIANCE CHECK — Phase N complete
✓ Steps completed: [list]
✓ Artifacts verified: [list]
✗ Issues found: [list, or "None"]
⚠ Warnings: [list, or "None"]
```

If any issue is found, the pipeline MUST stop until the issue is resolved.

### How to launch

```
Agent tool call:
  description: "Compliance Monitor Agent"
  prompt: [full compliance monitoring instructions + skill content]
  run_in_background: true
```

The monitor agent receives the full SKILL.md content and the output directory path. It periodically checks artifact files and is consulted via SendMessage at each phase gate.

### Non-negotiable rules for the Compliance Monitor

- It cannot be skipped, disabled, or deferred
- It cannot be "merged" into the main agent's responsibilities — it must be a separate, independent agent
- Its compliance checks are blocking — if it reports an issue, the pipeline stops
- It has read access to all output artifacts to verify their existence and correctness
- The main pipeline agent must send it a message at each phase gate and wait for its compliance report before proceeding

---

## Output schema

Every extracted KRI matches this structure:
```json
{
  "kri_id": "ELIG-INC-001",
  "kri_name": "Inclusion: confirmed diagnosis of X",
  "description": "What this KRI monitors and why it matters",
  "category_id": "ELIG",
  "category_label": "Eligibility",
  "rule_for_llm": "Verify that [specific actionable check with exact values]",
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
- `severity` — **critical**: primary endpoint, analysis population, interim analysis rules. **major**: secondary endpoints, biomarker endpoints. **minor**: exploratory endpoints, HCRU endpoints, administrative governance rules.

## CRITICAL — Atomicity Principle (applies to ALL in-scope domains)

**Every KRI must be atomic.** A single KRI must represent exactly ONE verifiable check about ONE thing at ONE time point in ONE clinical context. Never combine multiple rules, multiple endpoints, multiple criteria, multiple time points, or multiple clinical settings into a single KRI.

Examples of atomicity violations (WRONG):
- "Verify LDL-C, Non-HDL-C, Apo B, and triglycerides percent change at Week 14" → Must be 4 separate KRIs, one per analyte
- "Verify key secondary endpoints are composite of CV death, MI, stroke, and UA" → Must be one KRI per distinct composite endpoint definition
- "Verify HBsAg, HCV antibody, and HIV are all negative at screening" → Must be 3 separate KRIs

Examples of correct atomicity:
- "Verify that the percent change from baseline in LDL-C (direct measurement) is calculated at Week 14"
- "Verify that the key secondary endpoint is calculated as time from randomization to the first occurrence of a composite of CV death, non-fatal MI, and non-fatal stroke"
- "Verify that the subject has a negative HBsAg test at screening"

**This applies across the 4 in-scope domains:** ELIG (one criterion or sub-criterion = one KRI), SAF (one reporting rule or one stopping rule = one KRI), END (one endpoint definition or one governance rule = one KRI), OPS (one operational rule = one KRI).

### Atomization of compound clauses (refinement — apply carefully)

A single protocol criterion may contain multiple sub-conditions without explicit sub-letters (a/b/c). Before splitting, two preconditions MUST both hold:

**Precondition 1 — "Can this sub-condition actually fail?"** A sub-condition only becomes its own KRI if some real subject data can make it FALSE. If every subject passes by definition, it is not a verifiable check — do not extract it.
- Example: *"Males or females ≥18 to <85 years of age"* — "Males or females" covers all humans; no data can make it FALSE. Do NOT create a sex KRI. Only the age bounds are verifiable content here.

**Precondition 2 — Is this an ENUMERATION or ILLUSTRATIVE EXAMPLES?**
- **Illustrative examples → ONE KRI.** Wording like *"any X (such as A, B, C)"*, *"X including Y"*, *"X, e.g., A, B"*. The umbrella term X is the real criterion; A/B/C are examples showing what qualifies as X. Keep as one KRI; **put the examples into the `description` field** so monitoring staff see them. Splitting would wrongly narrow monitoring to only the named examples and miss anything else that qualifies as X.
  - Example: *"any medication (such as biological response modifiers, active immunomodulating treatment for cancer, systemic steroids) that causes immunosuppression"* → ONE KRI. `rule_for_llm` checks "any immunosuppressive medication"; `description` lists the named examples for clarity.
- **True enumeration → SPLIT.** An explicit list where each item is a distinct independently testable condition, with no umbrella term signalling "these are examples of something broader".
  - Example: *"positive test for HBsAg, a positive antibody test for hepatitis C, or positive test for HIV"* → 3 KRIs (each a distinct lab test on a distinct data field).

**When both preconditions hold, apply splitting for:**

- **True OR enumerations of distinct verifiable conditions** — each disjunct becomes its own KRI.
  Example: *"History of documented NASH, a positive test for HBsAg, a positive antibody test for hepatitis C, or any other known or suspected underlying liver disease"* → 4 KRIs (NASH diagnosis, HBsAg test, HCV antibody test, other liver disease).
- **AND clauses with independently verifiable parts on distinct fields** — each conjunct becomes its own KRI.
  Example: *"adequate circulation demonstrated AND no revascularization procedure anticipated before Week 16"* → 2 KRIs (distinct data fields).
- **Unlabeled list items that each name a distinct intervention/test/exposure** — each becomes its own KRI.
  Example: *"Treated with hyperbaric oxygen therapy or a cellular and/or tissue product (CTP) within 30 days"* → 2 KRIs (HBOT and CTP are distinct interventions with distinct records).
- **Combined lab thresholds with distinct analytes** — each analyte becomes its own KRI.
  Example: *"ALT or AST >3×ULN and/or bilirubin >1.5×ULN"* → 3 KRIs (ALT, AST, bilirubin are three separate lab values).

**Do NOT split when:**

- **Single-field range checks** — a numeric range like *"≥1 cm² and ≤40 cm²"* is evaluated against ONE data field (`surface_area_cm2`). Write ONE KRI that checks the value is within the range. A single field cannot fail only one bound at the data level — it's a single comparison. Exception: if the range uses two distinct measurements (e.g., *"systolic ≤140 AND diastolic ≤90"*), split — two fields, two KRIs.
- **Precondition 1 fails** — splitting would create a KRI that always passes.
- **Precondition 2 identifies the list as illustrative examples** — keep combined, examples go in the description.

**Verifiability test (final check when ambiguous):** for each proposed sub-KRI ask (a) Is there real subject data that would make this sub-KRI fail? (b) Does this sub-KRI read a different data field/record than the other sub-KRIs? Both must be YES to justify splitting. When in doubt, keep combined — over-splitting creates noise in consensus tiers that obscures real disagreement.

**Important — consistency across all agents and domains:** this rule applies identically to Claude sub-agents and Gemini agents, and across ELIG / SAF / END / OPS. The goal is consistent atomic granularity regardless of which agent produced the KRI.

Four in-scope categories (drawn from ICH GCP):
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints, Statistics & Governance (see detailed sub-categories below)
- **OPS** — Operations & Compliance

Out of scope for this skill (handled by the separate `soa-kri-extractor` skill):
- **SOA** — Schedule of Activities, including the SoA table, its footnotes, "procedure × visit" rules, visit-window check-ins, cross-visit timing rules, and visit-schedule narrative.

---

## CRITICAL — Domain Boundary Rules (prevents cross-domain duplicates)

### Rule 1 — "Procedure happened at visit" rules are OUT OF SCOPE (owned by the separate `soa-kri-extractor` skill)

If a KRI is essentially **"Verify that [procedure] was performed at [visit]"** — it belongs to the separate `soa-kri-extractor` skill, NOT to this skill. Do not extract it here. If a SAF or OPS extractor produces such a KRI by mistake, the cross-domain dedup pass (Step 4A-Dedup) must delete it with reason `"SOA-flavored — handled by soa-kri-extractor."`

This includes (non-exhaustive — every "X at visit Y" pattern qualifies):
- Lab timing ("hepatitis B and C collected at Visit 1") — out of scope
- Visit window ("V0 to V1 maximum 30 days") — out of scope
- Contraception check at designated visits — out of scope
- IRT registration at every visit — out of scope
- HbA1c collected at baseline/V11/EDC — out of scope
- Plasma biospecimen collection at V5/V11 — out of scope
- Lipid profile not collected at EDC/EOS — out of scope
- EOS visit no sooner than 14 days after last dose — out of scope
- Anything else of the form "[procedure] is performed at [visit]" or "visit X must occur within [window]"

**Red-flag test**: If a KRI's `rule_for_llm` contains the phrase "per SOA", "per schedule", "per the SoA table", "at [visit name]" (describing that something was done), "within ±N days of visit", or anchors a rule to a specific visit code — it is SOA-flavored and out of scope for this skill. Drop it during extraction; if it slips through, delete it during dedup.

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
- ✗ When/whether a procedure occurs at a specific visit → **out of scope (soa-kri-extractor)**
- ✗ Sample tube type or processing technique → **OPS**
- ✗ GCP documentation of protocol deviations without a clinical response trigger → **OPS**

**SAF/OPS boundary for deviations**: SAF owns deviations that trigger a clinical safety response. GCP documentation of protocol deviations without a clinical response trigger belongs in OPS.

**Example of the error to avoid**: The protocol describes BP methodology and vital signs positioning in its "Safety Assessments" section. Those rules are in the safety section but are not about safety thresholds — they belong in OPS. Do not use "found in safety section of protocol" as the criterion for SAF.

### Rule 3 — OPS owns technique, methodology, and standardization

OPS contains:
- **How to perform assessments**: measurement position (sitting, arm supported), measurement duration (30 seconds), equipment type (same calibrated cuff)
- **Longitudinal standardization**: same arm throughout study, same scale, same position
- **Sample handling**: tube type, processing steps, shipping conditions
- **IP storage, handling, dispensing, accountability**
- **Documentation and records**: CRF corrections, consent documentation, delegation logs
- **Regulatory compliance**: IRB approvals, inspection notifications, record retention
- **Protocol deviation documentation**: GCP-required logging, categorization, reporting, and submission of protocol deviations to sponsor and regulatory authority. One KRI per distinct deviation reporting obligation.

**OPS/SAF boundary for protocol deviations**: OPS owns protocol deviation as a GCP compliance document — logging, categorization, and reporting. If a deviation triggers a clinical safety response (e.g., deviation from a stopping rule requiring clinical action), that KRI belongs in SAF.

---

## CRITICAL — De-duplication (cross-domain AND intra-domain, mandatory after all domains extracted)

After Step 4A assembly, run the **dedup pass** before finalizing. Dedup operates in TWO fully-active sub-passes: **cross-domain** (between different domains) and **intra-domain** (within each domain). Both sub-passes are mandatory, both run on every extraction, and neither may be skipped.

### PRINCIPLE — Atomization is NOT duplication (read this before running dedup)

**The ultimate goal of this skill is to produce KRIs that are maximally atomic.** Each KRI must represent exactly ONE verifiable check about ONE thing, at ONE time point, in ONE clinical context, so that a machine can deterministically verify it in a simple YES/NO way. If a compound rule from the protocol has been split into N atomic KRIs, **those N KRIs are the correct output — they are NOT duplicates and must NEVER be merged back into one**.

Dedup exists to remove true duplicates only. It does NOT exist to compress atomization splits, to consolidate related KRIs, or to reduce KRI count.

**Definition of a TRUE DUPLICATE (only these qualify for deletion):**
- Same clinical check
- Same specific values (same threshold, same drug, same dose, same timing window, same analyte, same population scope)
- Same time point or visit
- Same clinical context
- Essentially interchangeable `rule_for_llm` — not just "similar in topic", not just "in the same area"

**NOT duplicates — MUST both be kept, NEVER delete:**
- Two KRIs that check different atomic aspects of the same clinical area
  - Example: "LDL-C percent change at Week 14" and "LDL-C nominal change at Week 14" are **different** KRIs, not duplicates
- Two KRIs that check different analytes in the same panel
  - Example: Apo B and LDL-C in the same lipid panel are separate KRIs
- Two KRIs that check the same procedure in different clinical settings
  - Example: fasting lipid vs non-fasting lipid — both kept
- Two KRIs that check different sub-criteria of the same eligibility criterion
  - Example: one inclusion criterion with 4 sub-bullets → 4 KRIs, all kept
- Two KRIs that check different endpoints within the same composite definition
  - Example: composite endpoint "CV death, MI, stroke" → 3 KRIs for the individual components PLUS 1 KRI for the composite definition = 4 KRIs, all kept

**Default when in doubt: KEEP BOTH.** Deletion is only justified when a duplicate is unambiguous. A false merge is worse than a false retention — a retained duplicate is visible in the Excel output and can be caught by human review, while a silently deleted atomic KRI is gone forever and the protocol coverage is permanently broken.

### Step 4A-Dedup — Two-pass Detection

**Sub-pass A — Cross-Domain Duplicate Detection (between ELIG / SAF / END / OPS)**

1. **SOA-flavored safety net (MANDATORY first check)**: For each KRI across all 4 in-scope domains, check whether the rule is essentially "procedure happened at visit", "visit X within ±N days", or any other "[procedure] at [visit]" pattern (see Domain Boundary Rule 1). If yes → **delete the KRI** with reason `"SOA-flavored — handled by soa-kri-extractor"`. This is the final safety net for any SOA-flavored rule that slipped past the extractor-prompt-level exclusion methodology. Log every such deletion in `dedup_report.json.cross_domain` under `rule_type: "out_of_scope_soa"`.

2. For each remaining KRI, check for cross-domain true duplicates per the ownership hierarchy below. Apply **Ownership hierarchy** (when the same atomic rule appears in multiple in-scope domains, this domain wins):

   | Rule type | Owner | Delete from |
   |---|---|---|
   | Safety threshold + response | SAF | OPS |
   | Measurement technique | OPS | SAF |
   | Endpoint or governance definition | END | SAF, OPS |
   | Eligibility criterion | ELIG | SAF, OPS |

3. **Cross-domain dedup only fires on TRUE DUPLICATES.** If two KRIs in different domains overlap in topic but check different atomic things (e.g., SAF "CK >5× ULN triggers IP stop" vs OPS "CK measurement technique"), **both are kept**. The ownership hierarchy resolves ownership only when the atomic check is identical, not when the topic is shared.

**Sub-pass B — Intra-Domain Duplicate Detection (fully active, not secondary)**

1. Within each domain, scan for duplicates using the TRUE DUPLICATE definition above. Matching uses **semantic equivalence** (not literal string match) — two KRIs whose only difference is wording, ordering, or paraphrasing of the same specific values are recognized as the same atomic check. Conservative threshold: only flag as duplicate when the two KRIs check the same subject, with the same condition and same threshold values, in the same context. When in doubt, KEEP BOTH and log under `kept_despite_similarity`.
2. Two KRIs with different IDs but semantically interchangeable `rule_for_llm`, same specific values, same time point, same context → keep the one with the richer description (more specific values, more cited context), delete the other.
3. **Never merge on "similar" or "related".** Atomization splits must be preserved — the presence of related KRIs is not evidence of duplication.
4. **Never merge atomic sub-checks into one KRI.** If the dedup pass encounters what looks like a duplicate but the two KRIs are actually atomic splits of a compound rule, STOP and keep both.
5. **Logging**: every intra-domain deletion candidate must be logged with its full `rule_for_llm`, the KRI it duplicates, the values compared, and the reason for deletion — so a human reviewer can verify the deletion was correct.

### Output artifact

Log all deletions (cross-domain AND intra-domain) in `{out_dir}/dedup_report.json` with:
```json
{
  "cross_domain": [
    {"deleted_kri_id": "...", "duplicate_of": "...", "reason": "...", "rule_type": "..."}
  ],
  "intra_domain": [
    {"domain": "...", "deleted_kri_id": "...", "duplicate_of": "...", "reason": "...", "values_compared": {...}}
  ],
  "kept_despite_similarity": [
    {"kri_id_a": "...", "kri_id_b": "...", "reason_kept": "atomization split / different time point / different analyte / etc."}
  ]
}
```

The `kept_despite_similarity` section is mandatory — it records cases where two KRIs looked similar but dedup correctly kept both. This is the audit trail that protects atomization against future over-aggressive dedup passes.

**Backward compatibility note**: The prior output file name `crossdomain_dedup_report.json` is deprecated in favor of `dedup_report.json`. Both names may be written during transition, but the canonical name is `dedup_report.json`.

---

### Cross-Section Merge Guard (MANDATORY — No Exceptions)

Two KRIs from **different numbered protocol subsections** (e.g., §8.7 and §8.14.1) MUST NEVER be merged during de-duplication, even if they appear topically similar, use similar language, or relate to the same subject area.

**The rule**: If `kri_a.protocol_reference` and `kri_b.protocol_reference` resolve to different numbered section identifiers (e.g., "Section 8.7" ≠ "Section 8.14.1"), the de-duplication agent is PROHIBITED from marking them as duplicates. Each section contains an independent protocol obligation and may encode a distinct, atomically verifiable rule.

**Rationale**: A dose-reduction trigger in §5.4.1.1 and a visit frequency consequence in §6.4.5 may both relate to LDL-C, but they are different obligations — merging them silently destroys one verifiable rule. Similarly, a hospitalization definition in §8.7 and a hospitalization reporting timeline in §8.14 are different rules.

**Implementation**:
- Before proposing any merge, the de-duplication agent MUST check whether `section_a != section_b`.
- If sections differ → the KRIs cannot be merged. They must appear as a `kept_despite_similarity` entry in `dedup_report.json` with reason: "Different protocol sections — merge prohibited by Cross-Section Merge Guard."
- The guard applies to both intra-domain and cross-domain de-duplication passes.
- A same-subsection merge (e.g., two KRIs both citing §8.14.1) is still subject to normal de-duplication rules.

---

### END Domain — Two Mandatory Sub-Categories

The END domain must produce KRIs in two sub-categories. All use `category_id: "END"` and `category_label: "Endpoints & Statistics"`.

**Sub-category 1 — Endpoint Definitions (ID prefix: `END-`)**
One KRI per protocol-defined endpoint. Every endpoint listed in the protocol's objectives section gets its own KRI:
- **Primary endpoint**: exact composite definition, time-from-randomization, adjudication requirement. Severity: critical.
- **Each key secondary endpoint separately**: even if they share a section header, each distinct composite or individual endpoint is a separate KRI. Severity: critical.
- **Each other secondary/clinical endpoint separately**: CV death, any MI, fatal MI, non-fatal MI, any stroke, fatal stroke, non-fatal stroke, hospitalization for UA, hospitalization for CHF, any coronary revascularization, CABG, PCI, any arterial revascularization, all-cause death — each one a separate KRI. Severity: major.
- **Each biomarker endpoint separately**: LDL-C percent change Week 14, LDL-C nominal change Week 14, LDL-C percent change last available, Non-HDL-C, Total cholesterol, VLDL-C, RLP-C, Apo B, Lp(a), Triglycerides, HDL-C, Apo A-I, hs-CRP — each analyte × each measurement type = one KRI. Severity: major.
- **Each HCRU endpoint separately**: all-cause hospitalizations, CV hospitalizations, ER visits, physician office visits, outpatient rehab visits, 30-day readmissions — each one a separate KRI. Severity: minor.

**Sub-category 2 — Governance (ID prefix: `GOV-`)**
One KRI per trial governance rule:
- **Analysis population definitions**: Full Analysis Set (FAS) exact inclusion criteria, Safety Analysis Set (SAS) exact inclusion criteria, any other analysis sets. Severity: critical.
- **Interim analysis trigger**: exact event count thresholds, which endpoints must be met, percentage requirements. Severity: critical.
- **Alpha spending**: method name (e.g. Heybittle-Peto), exact alpha value, adjustment to final analysis alpha. Severity: critical.
- **Study end/completion definition**: event count target, time-based criterion, whichever-occurs-later logic. Severity: major.
- **Data locks**: protocol-defined data lock date, data cut-off procedures, and lock criteria. One KRI per distinct lock event type. Severity: major.

---

## How to run

### Step 0 — Setup (first time only)
```bash
pip install pdfplumber pymupdf openpyxl --break-system-packages -q
```

### Input required
- Protocol PDF file path
- Output directory (will be created)
- Optional: golden set JSON path (for step 4B comparison)

**Canonical run directory**: `~/Downloads/extractor/<protocol_id>/<run_id>/` — e.g., `~/Downloads/extractor/B1481038/run_011/`. Every run uses its own directory. Pass this as the `--out` argument to `run.py`.

### Full pipeline command (DETERMINISTIC — canonical entry point)

**`bypassPermissions` permanent default**: `bypassPermissions` must be set as a permanent default for all pipeline runs — no approval prompts should interrupt extraction. Set this in the Claude Code session before invoking `run.py`.

`scripts/run.py` is the **single canonical entry point** for the pipeline. It executes every documented step in the exact order defined in this file and enforces the three blocking gates (Step 3.5 orphan scan, Step 3B full accuracy judging, Step 3D verbatim verification). No step can be silently skipped, reordered, or softened.

```bash
python /path/to/scripts/run.py \
  --pdf /path/to/protocol.pdf \
  --out /path/to/output/ \
  [--golden /path/to/golden_set.json]
```

Other modes:
```bash
# Resume from a specific step (useful after resolving a blocking gate)
python run.py --pdf ... --out ... --from 3.5
python run.py --pdf ... --out ... --from 3b

# Run only a specific step
python run.py --pdf ... --out ... --only 3b

# See full step order and blocking gates
python run.py --help
```

**Step order enforced by `run.py`** (matches this document exactly):
`1a → 2 → 2.6 → 3.5 → 3a → 3b → 3c → 3d → 4a → 4a-dedup → 4a-flagged → 4b`

**Blocking gates** (pipeline stops with exit 1 if any fail):
- **Step 3.5** — all USER_DECISION orphan candidates must be resolved
- **Step 3B** — 0 FAIL and 0 unresolved FLAG across all KRIs (100% coverage)
- **Step 3D** — 100% verbatim pass

**Complete protocol coverage guarantee**: Step 3.5 (full protocol sweep — section-by-section + page-by-page for unclaimed pages) combined with Step 3D (verbatim quote verification on every KRI's cited page) guarantees no protocol page is unread and no supporting quote goes unverified.

Any attempt to run individual step scripts outside of `run.py` (for debugging) is permitted, but the pipeline for production runs MUST go through `run.py` so that step order and blocking gates are enforced.

Or run steps individually for debugging — see **Step-by-step** below.

---

## Step-by-step

Read `references/steps.md` for the detailed prompt templates and logic for each step.

### Phase 1 — Discover

**Step 1A — Manifest**: Read cover pages + TOC. Map every protocol section to one of the 4 in-scope domains (ELIG, SAF, END, OPS). Schedule-of-Activities sections (the SoA table, its footnote pages, and any narrative section primarily devoted to visit schedule or "procedure at visit" rules) are left **unmapped** — they are out of scope for this skill and handled by the separate `soa-kri-extractor` skill. The manifest is the single source of truth for which pages each downstream extractor and the orphan scan are allowed to read.

### Phase 2 — Extract (4-domain multi-model panel)

> **Scope reminder — SOA is out of scope for this skill.** Schedule-of-Activities content (the SoA table, its footnotes, "procedure × visit" rules, visit-window check-ins, cross-visit timing rules, visit-schedule narrative) is handled by the separate `soa-kri-extractor` skill. Every extractor prompt in this Phase 2 carries the explicit "Out of scope — SOA" methodology block defined in `references/steps.md`. If an agent encounters SOA-flavored content in its domain section, it must skip it — do not emit a KRI for it.

Extraction for the 4 in-scope domains (ELIG, SAF, END, OPS) uses a **10-agent multi-model panel** (5 Claude Sonnet + 5 Gemini 2.5 Pro agents running in parallel). Consensus determines tier: **Tier 1** = 7–10 agents agree (auto-approved into Golden Set), **Tier 2** = 4–6 agents agree (**Step 2.6 auto-judgment** produces the per-KRI pre-decision), **Tier 3** = 1–3 agents (enters Tier 3 promotion pipeline, terminating in Step 2.6 auto-judgment). Step 2.6 replaces the prior manual decision-table pause with an automated 4-layer engine (verification gate, atomicity check, dedup/coverage, 6-judge neutral panel, aggregate). With `--auto-approve-unanimous` ON (default), the pipeline runs end-to-end without blocking; flagged items default to rejected and surface at end-of-run in **Step 4A-FlaggedReview** for cross-domain user review and optional re-inclusion. Per-domain content rules:
- ELIG: one KRI per criterion/sub-criterion. Extract every criterion regardless of whether the wording is qualitative or quantitative — write `rule_for_llm` as faithfully as the protocol allows, but do not skip a criterion because it uses qualitative wording.
- SAF: every reporting timeline, stopping rule, emergency protocol
- END: **two sub-categories** — (1) one KRI per endpoint definition (primary, each key secondary, each other secondary individually, each biomarker analyte × measurement type, each HCRU metric), (2) one KRI per governance rule (analysis populations, interim analysis triggers, alpha spending, study end definition, data locks)
- OPS: IMP handling, blinding, records, compliance

---

### Step 2.5 — Section Obligation Inventory (MANDATORY, runs after each domain extraction)

After completing the 10-agent extraction for a domain (and before proceeding to Phase 3), run a **Section Obligation Inventory** for that domain's assigned protocol sections. This step catches obligations that all agents missed.

**Process:**

1. **Scan every sentence** in the domain's protocol sections for obligation markers:
   - Hard obligations: "must", "shall", "is required to", "is prohibited"
   - Temporal obligations: "within [N] hours/days/weeks", "no later than", "at least [N] days before"
   - Submission obligations: "submitted to", "reported to", "notified", "communicated to"
   - Definitional boundaries: "is defined as", "does not include", "is not [X] when", "excludes"
   - Dose/threshold triggers: "if [condition], then [action]", "≤ [value]", "≥ [value]"

2. **For each obligation sentence found**, check whether it is covered by an existing KRI's `supporting_quote` (via substring match after normalization).

3. **Uncovered obligation sentences** → automatically promoted to **Tier 3** for processing through the Tier 3 Promotion Pipeline (see above). They enter Step T3-1 (Coverage Filter) immediately.

4. **Artifact**: Save the full inventory — all obligation sentences, their coverage status (covered/uncovered), and the covering KRI ID if applicable — to `{domain}_obligation_inventory.json`.

**Key principle**: This step is a mandatory safety net, not a replacement for the 10-agent extraction. Its purpose is to ensure that every sentence in the protocol that encodes a verifiable obligation has at least one KRI candidate in the system, even if the original agents had low confidence.

**Artifact**: `{domain}_obligation_inventory.json`

---

### Phase 3 — Validate (orphan scan + completeness + H4 heuristic + full accuracy judging + consistency + mandatory full verbatim verification)

**Step 3.5 — Protocol-Wide Orphan Scan (MANDATORY BLOCKING GATE, runs FIRST in Phase 3)**: Scan the ENTIRE protocol — section-by-section (primary) and page-by-page for any page not claimed by the section map (secondary sweep) — to find rule-like statements, obligations, thresholds, prohibitions, requirements, criteria, timings, or methods that were NOT captured by any domain extractor in Phase 2. Uses a **6-agent panel (3 Claude + 3 Gemini)** with high-recall candidate detection and consensus-based promotion. Promoted orphan KRIs are appended to the corresponding `raw_{DOMAIN}.json` file (one of the 4 in-scope domains: ELIG/SAF/END/OPS) so they flow through the rest of Phase 3 validation like any other KRI. **SOA-flavored candidates** (procedure-at-visit, visit-window, cross-visit-timing, SoA table content, SoA footnotes) **are dropped during candidate consolidation** with reason `"out_of_scope_soa"` — logged in the report for audit, but never promoted to a KRI in this skill. **The pipeline cannot advance to Step 3A until the orphan scan is complete and all user decisions are made.** See full spec below.

**Step 3A — Completeness**: Every obligation sentence in each domain's `{domain}_obligation_inventory.json` (from Step 2.5) must have at least one KRI whose `supporting_quote` covers it. SOA-flavored obligations are skipped from this check — they are not in scope. Output: `gaps_report.json`.

**Step 3A+ — H4 SAF Heuristic — Adverse-Event Collection Window**: Single protocol-agnostic heuristic retained from the prior 10-heuristic set. Verifies that there is a SAF KRI defining the AE collection window starting at first IP dose (e.g., "AEs collected from first IP administration through 30 days post-last-dose"). If no such KRI exists in `raw_SAF.json`, promote a candidate via the orphan-scan pathway. This is the only retained heuristic — the prior H1, H2, H3, H5, H6, H7, H8, H9, H10 were SOA-flavored (visit × procedure relationships, SoA-table geometry) and were removed when SOA extraction moved to `soa-kri-extractor`. Implementation: inside `step3a_completeness.py`.

**Step 3B — Full KRI Accuracy Judging (MANDATORY BLOCKING GATE, 100% coverage, multi-judge panel)**: Every single KRI (100% of the extracted set across all in-scope domains, including orphan KRIs promoted in Step 3.5) is verified by a **5-judge cross-model panel**: 3 Claude Sonnet judges + 2 Gemini 2.5 Pro judges. Each judge independently verifies six checks — Faithfulness (C1), Specific Values (C2), Reference Accuracy (C3), Completeness (C4), Scope Accuracy (C5), and Atomicity (C6) — against the full text of the cited page(s) ±1 page of context. Consensus adjudication determines the final verdict; any FAIL is blocking; FLAGs escalate to user decision; IMPRECISE KRIs are auto-corrected only when ≥3 judges agree on the correction, then re-verified. **The pipeline cannot advance to Step 3C until Step 3B emits a pass report with 0 FAIL and 0 unresolved FLAG.** This step checks whether the **content** of rules is clinically accurate — it does NOT substitute for Step 3D quote verification. **This step replaces the prior 20-KRI sampling approach** — sampling is no longer permitted under any circumstances. See full spec below.

**Step 3C — Consistency**: Same clinical concept across multiple KRIs (e.g., a threshold value mentioned in both SAF and OPS) must have consistent values, units, and references. Output: `consistency_report.json`.

**Step 3D — Full Verbatim Verification (MANDATORY BLOCKING GATE)**: Run `scripts/step3d_verify.py` against the PDF to verify every single KRI's `supporting_quote` is a verbatim substring of the cited page text. **The pipeline cannot advance to Step 4A until this step reports 100% pass.** A `supporting_quote` that cannot be found verbatim in the cited page is a **fabricated quote** — a hard pipeline failure. Not a warning, not a soft flag. The pipeline stops immediately. The KRI must be corrected before proceeding. No exceptions. See details below.

### Phase 4 — Assemble + Compare
**Step 4A — Assembly**: Run `scripts/step4a_assemble.py` to merge all category files → `extracted_kris.json` + `Extracted_KRIs.xlsx`. The Excel workbook has one sheet per in-scope domain (ELIG, SAF, END, OPS — 4 sheets) plus a Summary sheet. **Exact column structure — no deviations:**

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

**Post-Assembly pass (MANDATORY, before the Final summary):**
1. **Step 4A-Dedup** — run the dedup pass (see "CRITICAL — De-duplication" above). Includes the SOA-flavored safety-net check (Sub-pass A clause 1) that deletes any "procedure at visit" KRI that slipped past the extractor-prompt-level exclusion.

The dedup pass operates on the assembled output (`extracted_kris.json` + the `raw_{DOMAIN}.json` files) and rewrites them in place.

**Final summary (mandatory)**: At the end of every completed run — after the post-assembly dedup pass — print and log a domain-by-domain KRI count: total per in-scope domain (ELIG, SAF, END, OPS) and grand total. Confirm the assembled `extracted_kris.json` is the approved (non-SOA) Golden Set for this protocol.

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

## Step 3.5 — Protocol-Wide Orphan Scan (full spec)

**Step 3.5 is MANDATORY and BLOCKING.** It runs as the FIRST step of Phase 3, immediately after Phase 2 completes (all `raw_*.json` files written) and before Step 3A. It cannot be skipped, deferred, or disabled for any reason.

### Purpose

After Phase 2's domain extractors have run, the extracted KRI set reflects what the ELIG / SAF / END / OPS extractors each found within their own domain focus. But real protocols contain rule-like content that can fall between domain prompts — content in appendices, boxed notes, un-numbered sections, text that crosses domain boundaries, or content phrased in a way that no single domain extractor's prompt keyed on. Step 3.5 is the safety net that catches every such rule before dedup runs.

This step is the **protocol-wide orphan scan**. It also re-applies the SOA-exclusion methodology: SOA-flavored candidates are dropped (reason `out_of_scope_soa`), never promoted.

### Input

- Full protocol PDF
- `manifest.json` (section map)
- All `raw_{DOMAIN}.json` files (ELIG, SAF, END, OPS)

### Architecture — 6-agent panel (3 Claude + 3 Gemini)

Cross-model, same principle as Phase 2 extraction:

| Agents | Model |
|---|---|
| A_C1, A_C2, A_C3 | Claude Sonnet 4 |
| A_G1, A_G2, A_G3 | Gemini 2.5 Pro |

Orphan scanning is a **recall problem** — the cost of missing an orphan is higher than the cost of flagging a non-orphan. Therefore the candidate-detection stage is high-recall (any agent flagging something makes it a candidate), and the promotion stage is consensus-based.

### Phase 1 — Primary section sweep (section-by-section)

For each section in `manifest.json` (across all 4 domains in the section map):

1. Load the full text of the section's page range via pdfplumber
2. Load the list of all existing KRIs whose `protocol_reference` cites any page in that range (compact form: `kri_id` + `rule_for_llm`)
3. Dispatch the section text + existing-KRI list to each of the 6 agents independently, in parallel
4. Each agent returns a JSON list of candidate orphan rule-like statements found in that section that are NOT covered by any listed KRI
5. Each candidate includes: `candidate_text` (the rule-like statement verbatim), `page`, `surrounding_context` (≤50 words), `proposed_domain` (agent's initial guess)

**Why section-by-section is primary**: sections have semantic coherence. A rule introduced at the top of a section often has its threshold 3 paragraphs later, and splitting across arbitrary page boundaries loses the connection. Section boundaries preserve meaning. Using the `manifest.json` section map means this sweep uses the existing routing structure rather than imposing a new one.

**Zero-KRI section emphasis (MANDATORY)**: if a section has **zero** existing KRIs citing any of its pages (`len(existing_kris_citing_section) == 0`), the scan treats it as a **zero-KRI section** and dispatches an emphasized prompt variant that instructs the agents to apply maximum recall — since no existing KRI covers the section, every rule-like statement it contains is very likely an orphan. The agents are told not to self-filter, not to assume any statement is "too minor", and to flag every obligation, threshold, prohibition, requirement, procedure, criterion, timing, method, stopping rule, reporting rule, or governance rule present. Empty array is acceptable ONLY if the section genuinely contains no rule-like content (e.g. title page, references, signature block). This emphasis closes the gap where Phase 2 produced no KRIs for a section and the orphan scan was the last safety net. Per-section coverage (existing KRI count, zero-KRI flag, candidates flagged) is recorded in `orphan_scan_report.json` under `primary_sweep.section_coverage_audit` for audit. *Terminology note: "zero-KRI sections" here is distinct from Step 2.5's "uncovered obligations" — that is a per-domain obligation-level audit; this is a cross-domain section-level scan emphasis.*

### Phase 2 — Secondary page sweep (page-by-page, orphan pages only)

1. Compute the set of PDF pages that are **NOT claimed by any section** in `manifest.json`. These are orphan pages: appendices without section numbers, un-numbered boxes, amendment addenda, margin text, pages between sections.
2. For each orphan page:
   - Load the page text
   - Load the (usually small) list of any existing KRIs citing that page
   - Dispatch to the same 6-agent panel using the same per-agent prompt
3. Each agent returns candidate orphans the same way as Phase 1

**Why page-by-page for orphan pages**: these pages are exactly where rules hide. They aren't in the section map, so the primary sweep cannot cover them. Page-level granularity here is the exhaustive backstop.

### Phase 3 — Candidate consolidation

1. Union all candidates from both sweeps
2. For each candidate, count how many of the 6 agents independently identified it (match on semantic similarity, not exact string — the adjudication judge decides similarity)
3. Apply promotion tiers:

| Agent count | Tier | Action |
|---|---|---|
| **≥4 of 6** | HIGH CONFIDENCE | Auto-promote to classification (Phase 5) |
| **2–3 of 6** | USER DECISION | Escalate to user decision table with full context. Pipeline pauses until user responds. |
| **1 of 6** | LOW CONFIDENCE | **NOT silently dropped.** Logged in `orphan_scan_report.json` under `low_confidence_candidates` with full context, so the user can audit what was filtered out. |

### Phase 4 — Cross-check against existing KRIs

For each promoted candidate (from HIGH CONFIDENCE and user-approved USER DECISION tiers):

1. An **adjudication judge** (separate Claude call) receives the candidate + ALL existing KRIs across ALL domains (not just the section's)
2. The judge answers: "Is this candidate ALREADY covered by any existing KRI, anywhere in the extracted set, under the TRUE DUPLICATE definition from the dedup section?"
3. If **yes** → drop the candidate, log as `{"candidate": ..., "covered_by_kri": "<kri_id>", "reason": "..."}` in `orphan_scan_report.json`
4. If **no** → proceed to Phase 5

This cross-check is what prevents orphan scan from re-creating KRIs that already exist under a different wording. It does NOT compress atomic splits (see "Atomization is not duplication" above) — it only drops candidates that are genuinely already covered.

### Phase 5 — Domain classification & KRI generation

For each candidate that survives cross-check:

1. Classify into ELIG / SAF / END / OPS using the Domain Boundary Rules (SKILL.md Rules 1–3). If the candidate is SOA-flavored (procedure-at-visit, visit-window, cross-visit timing, SoA-table content, SoA footnote content), DROP it from the orphan-scan output with reason `"out_of_scope_soa"` — do NOT classify it into any domain in this skill. It is handled by the separate `soa-kri-extractor` skill.
2. Generate a full KRI record:
   - `kri_id`: prefixed `ORPH-{DOMAIN}-{NNN}` so orphan KRIs are identifiable in downstream audits
   - `kri_name`: short name derived from the candidate text
   - `description`: one-sentence description of what this KRI monitors
   - `rule_for_llm`: atomic rule text following all atomicity and faithfulness rules
   - `protocol_reference`: section label + page number
   - `supporting_quote`: verbatim ≤30 words from the source page (no outer quotes)
   - `combined_ref`: computed as `f'{protocol_reference} — "{supporting_quote}"'`
   - `additional_footnotes`: if applicable, verbatim footnote text
   - `severity`: critical / major / minor per the standard severity rules
3. Append the orphan KRI to the corresponding `raw_{DOMAIN}.json` file so it flows through the rest of Phase 3 (Step 3A completeness, Step 3A+ H4 SAF heuristic, Step 3B full accuracy judging, Step 3C consistency, Step 3D verbatim verification) exactly like a Phase 2 KRI.

### Phase 6 — Gating

- **Blocking**: Step 3A cannot start until:
  - Both sweeps completed
  - Consolidation produced tier counts
  - All USER DECISION items resolved (user has responded to each)
  - Cross-check completed
  - All HIGH CONFIDENCE and approved USER DECISION orphans classified and appended to `raw_{DOMAIN}.json`
  - `orphan_scan_report.json` written
- The Compliance Monitor verifies the orphan scan ran in full and the report exists with all required sections before allowing Phase 3 to continue
- Any attempt to skip Step 3.5 is a meta-rule violation and must stop the pipeline

### Output — `orphan_scan_report.json`

```json
{
  "_meta": {
    "step": "3.5",
    "sections_scanned": 34,
    "orphan_pages_scanned": 7,
    "total_agents": 6,
    "agent_breakdown": {"claude": 3, "gemini": 3},
    "total_tokens": {"claude": ..., "gemini": ...}
  },
  "primary_sweep": {
    "sections": [{"section_number": "...", "pages": [...], "candidates_found": N}],
    "total_candidates": 47
  },
  "secondary_sweep": {
    "orphan_pages": [...],
    "total_candidates": 12
  },
  "consolidation": {
    "total_candidates": 59,
    "high_confidence": 23,
    "user_decision": 14,
    "low_confidence": 22
  },
  "low_confidence_candidates": [ {"candidate_text": "...", "page": N, "agent_id": "...", "surrounding_context": "..."} ],
  "user_decisions": [ {"candidate_text": "...", "agent_count": 3, "user_decision": "approve|reject", "user_note": "..."} ],
  "cross_check": {
    "dropped_as_covered": 9,
    "dropped_list": [ {"candidate_text": "...", "covered_by_kri": "...", "reason": "..."} ],
    "promoted_to_classification": 28
  },
  "classification": {
    "by_domain": {"ELIG": 1, "SAF": 16, "END": 2, "OPS": 5},
    "dropped_as_out_of_scope_soa": 4
  },
  "promoted_orphans": [ { /* full KRI records */ } ]
}
```

---

## Step 3B — Full KRI Accuracy Judging (full spec)

**Step 3B is MANDATORY and BLOCKING.** It runs at 100% KRI coverage across all domains, including orphan KRIs promoted in Step 3.5. Sampling is NEVER permitted under any circumstances — not for cost, not for speed, not for convenience. If 100% judging is expensive, that is the cost of correctness.

### Purpose

Step 3B verifies the **clinical content** of every KRI against the protocol. It is distinct from Step 3D (verbatim substring verification) in that 3B checks whether the rule *means* what the protocol says, while 3D checks whether the quote *appears* where the KRI says it does. Both are mandatory and neither replaces the other.

Step 3B also closes the "wrong page citation" loophole: Step 3D's substring check can pass even when a KRI cites a page whose content is about a different clinical topic than the KRI. Check C3 (Reference Accuracy) in the 3B panel catches exactly this.

**Replaces** the prior 20-KRI / 4-per-category sampling approach. The old sampling implementation is superseded because it failed to provide coverage guarantees. Sampling must never be re-introduced under any framing.

### Panel composition — 5 judges per KRI, cross-model

| Judges | Model |
|---|---|
| C1, C2, C3 | Claude Sonnet 4 (3 independent judges) |
| G1, G2 | Gemini 2.5 Pro (2 independent judges) |

The 3-Claude / 2-Gemini ratio (vs. 5+5 in Phase 2 extraction) is intentional. Judging is a simpler task than extraction — it is fully grounded with the exact page text — so fewer agents per model suffice, and it keeps 100% coverage cost-tractable. Cross-model is non-negotiable to prevent same-model confirmation bias.

### Per-KRI input to each judge

Each judge receives, for the KRI being verified:

- The KRI record: `kri_id`, `kri_name`, `description`, `rule_for_llm`, `protocol_reference`, `supporting_quote`, `additional_footnotes`, `severity`, `category_id`
- The **full text of the cited page(s) + 1 page of context before and after**, loaded via pdfplumber

### The 6 checks (C1–C6) each judge runs independently

| Check | What it verifies |
|---|---|
| **C1 — Faithfulness** | Does `rule_for_llm` say what the protocol says, nothing more and nothing less? No additions, no omissions, no softening, no generalization |
| **C2 — Specific values** | Every concrete value in the rule (threshold, drug name, dose, timing window, analyte, visit number, day count, percentage, unit) matches the protocol exactly |
| **C3 — Reference accuracy** | The cited `protocol_reference` (section + page) is actually ABOUT the clinical topic of this KRI. This is NOT a substring check — it is a semantic check. If the KRI is about "LDL-C percent change at Week 14" but the cited page is about infusion reactions, C3 FAILS even if the quote happens to appear on that page. |
| **C4 — Completeness** | No critical detail the protocol specifies for this rule is missing. If the protocol says "measure in sitting position with arm supported after 5 minutes of rest" and the KRI says "measure in sitting position", C4 returns IMPRECISE with the missing detail identified |
| **C5 — Scope accuracy** | Visit scope, population scope, time-point scope all match protocol intent. If the KRI says "at V3" but the protocol specifies "at V3 and V5", C5 FAILS |
| **C6 — Atomicity** | The KRI encodes exactly ONE binary obligation about ONE subject with at most one condition. Compound KRIs that bundle multiple analytes (e.g., `LDL-C, Apo B, and TG at Week 14`), multiple sub-criteria, or multiple obligations in one `rule_for_llm` FAIL C6. Auto-correction = split into N atomic KRIs and re-judge each split. (Underlying rule: § "CRITICAL — Atomicity Principle"; § Quote anchoring quality rule.) |

### Per-judge verdict format

```json
{
  "judge_id": "C1",
  "model": "claude-sonnet-4",
  "kri_id": "SAF-003",
  "verdict": "CORRECT | IMPRECISE | WRONG",
  "failing_checks": ["C2", "C4"],
  "issue": "specific problem description, null if CORRECT",
  "corrected_rule": "corrected rule_for_llm text, null if CORRECT",
  "protocol_evidence": "verbatim ≤25-word quote from the cited page that proves the verdict"
}
```

Verdicts:
- **CORRECT** — all 6 checks pass
- **IMPRECISE** — right intent, all checks semantically pass, but C2 or C4 flagged a missing detail (e.g., missing CRP from a lab list, missing "supine" from vitals positioning). Auto-correctable.
- **WRONG** — any of C1, C3, C5, or C6 failed, OR C2/C4 failed with incorrect values (not just missing). Blocking. C6 failures are auto-correctable by atomic split (split the compound KRI into N atomic KRIs and re-judge each), but the original compound KRI does not pass.

### Consensus adjudication per KRI

After all 5 judges return verdicts, combine into a final per-KRI verdict:

| Vote distribution | Final verdict | Action |
|---|---|---|
| **5/5 CORRECT** | PASS | Auto-accept, no change |
| **4/5 CORRECT + 1 non-CORRECT** | PASS (with dissent) | Auto-accept, log the dissenting judge's issue in the report for audit |
| **3/5 CORRECT + 2 non-CORRECT** | FLAG | Escalate to user decision table. Pipeline pauses until user responds. No auto-accept. |
| **≤2/5 CORRECT** | FAIL | **BLOCKING.** Attempt auto-correction (see below); if correction is not possible or disagreed, the KRI must be manually fixed or re-extracted |

### Auto-correction protocol

When a KRI has an IMPRECISE verdict or a FAIL with judge-proposed corrections:

1. Collect all `corrected_rule` values from all judges (CORRECT judges contribute null)
2. If **≥3 judges independently propose a correction AND the proposed corrections are semantically equivalent** (adjudication judge decides equivalence) → merge the corrections into a single canonical correction
3. Apply the correction to the KRI in the corresponding `raw_{DOMAIN}.json`
4. **Re-run the 5-judge panel on the corrected KRI** — this re-verification is mandatory; a correction is never applied without re-verification
5. If the corrected KRI now returns ≥4/5 CORRECT → PASS, log the correction in the report
6. If not → escalate to user

If <3 judges agree on a correction → escalate to user decision table. The user is shown the original KRI, all 5 judge verdicts, the proposed corrections, and asked which (if any) to apply.

### Gating

Step 3B emits a pass report ONLY when:

- **0 FAIL** remaining (all blocking failures resolved by correction + re-verification or manual fix)
- **0 unresolved FLAG** (all user decisions submitted)
- Every IMPRECISE either auto-corrected + re-verified at ≥4/5 CORRECT, or explicitly user-accepted

The pipeline cannot advance to Step 3C until Step 3B emits the pass report. This matches the Step 3D blocking-gate pattern.

### Batching and cost control

100% coverage is expensive by default. The following optimizations make it tractable without sacrificing coverage:

- **Group KRIs by cited page range**: one pdfplumber page-text load serves every KRI that cites that page → page text is loaded once per run, not once per KRI
- **Batch up to 8 KRIs per LLM call** when they share the same cited page context. The judge call receives the page text once + 8 KRIs in a single call, returning 8 verdicts
- **Parallelize across domains**: ELIG / SAF / END / OPS judged in parallel (4 workers)
- **5 judges per KRI run in parallel, not sequentially** — the 5 judge calls for one KRI (or one batch) are dispatched concurrently
- **Page text cache**: in-memory dict keyed by page number, populated lazily, reused across all batches in the run
- **Gemini agents** are called via `scripts/gemini_extract.py` with judge mode (not extract mode)

These optimizations DO NOT reduce coverage. Coverage remains 100%. They only reduce redundant work.

### Output — `accuracy_report_full.json`

```json
{
  "_meta": {
    "step": "3B",
    "total_kris_judged": 312,
    "coverage": "100%",
    "pass_count": 298,
    "flag_count": 9,
    "fail_count": 5,
    "auto_corrections_applied": 14,
    "auto_corrections_re_verified": 14,
    "user_decisions_pending": 0,
    "tokens_used": {"claude": 1240000, "gemini": 890000},
    "pass_gate": true
  },
  "per_kri": [
    {
      "kri_id": "SAF-003",
      "final_verdict": "PASS",
      "consensus": "4/5 CORRECT",
      "judge_verdicts": [
        {"judge_id": "C1", "verdict": "CORRECT", ...},
        {"judge_id": "C2", "verdict": "CORRECT", ...},
        {"judge_id": "C3", "verdict": "CORRECT", ...},
        {"judge_id": "G1", "verdict": "IMPRECISE", "failing_checks": ["C4"], "issue": "missing 'supine' qualifier", ...},
        {"judge_id": "G2", "verdict": "CORRECT", ...}
      ],
      "dissent": {"judge_id": "G1", "issue": "missing 'supine' qualifier"},
      "correction_applied": null,
      "user_decision": null
    }
  ],
  "blocking_issues": [],
  "auto_correction_log": [ ... ],
  "user_decisions": [ ... ]
}
```

### Relationship to Step 3D

Step 3B and Step 3D are complementary, NOT overlapping. Both run, both are blocking, neither replaces the other:

| | Step 3B | Step 3D |
|---|---|---|
| **What it checks** | Clinical content: does the rule mean what the protocol says? | Traceability: is the quote a verbatim substring of the cited page? |
| **Coverage** | 100% | 100% |
| **Method** | 5-judge cross-model panel, semantic check of 6 dimensions (C1–C6) | Deterministic pdfplumber substring match |
| **Catches** | Wrong thresholds, wrong visit scope, wrong page topic, missing details, misinterpretation, compound (non-atomic) KRIs, footnote-number/quote misalignment | Fabricated quotes, wrong page numbers, typos that break exact match |
| **Blocking gate** | Yes — before 3C | Yes — before 4A |

The combination of 3B C2+C3 + 3D gives full protection against wrong page citations: 3D catches text fabrication, 3B C3 catches "the quote exists on the page but the page is about a different topic", 3B C2 catches wrong specific values. Nothing escapes.

---

## Output artifacts

Each pipeline run produces these files in the output directory:

| File | Description | Source |
|------|-------------|--------|
| `manifest.json` | Protocol metadata + section map (ELIG/SAF/END/OPS — SOA pages left unmapped, out of scope) | Step 1A |
| `raw_ELIG.json` | Eligibility KRIs | Step 2 |
| `raw_SAF.json` | Safety KRIs | Step 2 |
| `raw_END.json` | Endpoint + governance KRIs | Step 2 |
| `raw_OPS.json` | Operations KRIs | Step 2 |
| `{domain}_obligation_inventory.json` | Per-domain section obligation inventory + coverage check | Step 2.5 |
| `{domain}_autojudgment_report.json` | Per-KRI Step 2.6 layer-by-layer audit | Step 2.6 |
| `{domain}_manual_review_decisions.json` | Sectioned decision table (per domain) | Step 2.6 |
| `{domain}_tier3_filtered.json` | Tier 3 promotion pipeline dispositions | Step 2.6 |
| `orphan_scan_report.json` | **Protocol-wide orphan scan results (primary section sweep + secondary page sweep + consolidation + cross-check + classification + user decisions + promoted orphan KRIs). SOA-flavored candidates dropped with reason `out_of_scope_soa`.** | **Step 3.5** |
| `gaps_report.json` | Obligation-inventory coverage + H4 SAF heuristic result | Step 3A/3A+ |
| `accuracy_report_full.json` | **100% KRI accuracy judging — 5-judge cross-model panel verdicts, consensus results, auto-corrections, user decisions, blocking gate status** | **Step 3B** |
| `consistency_report.json` | Cross-KRI consistency check | Step 3C |
| `verify_report.json` | Full verbatim verification results | Step 3D |
| `extracted_kris.json` | All KRIs assembled (4 in-scope domains, including promoted orphans from Step 3.5) | Step 4A |
| `Extracted_KRIs.xlsx` | Excel workbook (4 domain sheets: ELIG, SAF, END, OPS + Summary) | Step 4A |
| `dedup_report.json` | **Dedup results — cross-domain (including SOA-flavored deletions) + intra-domain deletions + `kept_despite_similarity` audit trail** | **Step 4A-Dedup** |
| `flagged_review_decisions.json` | End-of-run cross-domain flagged-review consolidated table | Step 4A-FlaggedReview |
| `comparison_report.json` | Golden set comparison (if provided) | Step 4C |

---

## Quality rules (apply to every KRI)

1. **Faithfulness**: Use exact drug names, doses, thresholds, timing windows from the protocol. Never generalize ("emergency treatment" → name the drugs).
2. **Data source**: Washout KRIs must say "by checking medication logs and visit timestamps".
3. **Lab panels**: Include all analytes from the protocol footnote — never just "biochemistry panel".
4. **Vitals position**: Use the exact position wording the protocol uses (e.g. "supine position").
5. **Analysis sets**: Use the protocol's exact definition — ITT ≠ mITT ≠ FAS.
6. **No hallucination**: Every KRI must cite a real section + page. If unsure, omit.
7. **Measurement detail**: Physical assessments must include units, positioning, and preparation when the protocol specifies them (e.g. "weight in kilograms, shoes removed").
8. **No outer quotes in supporting_quote**: The `supporting_quote` field must never begin or end with a `"` character. The `combined_ref` field adds its own surrounding quotes.
9. **No duplicate page numbers**: Never produce `"p.27, p.27"` or `"Page 27, p.27"`. Exactly one page reference per KRI.
10. **No footnote number prefix in quotes**: Raw PDF has `"13 Urinalysis..."` — the `13` is a label, not content. Strip it. Quote starts with the text: `"Urinalysis: Dipstick..."`.
11. **Script safety — always save**: Every script that modifies JSON must: (a) create a backup, (b) `json.dump(..., ensure_ascii=False)`, (c) print confirmation with record count.
12. **Quote anchoring — one obligation per quote**: The `supporting_quote` must be the **shortest possible verbatim segment** from the protocol that anchors exactly ONE verifiable obligation. Never bundle multiple independent obligations into a single `supporting_quote`. If a sentence contains two independently verifiable rules (e.g., a dose definition AND a reporting timeline), split them into two KRIs with separate quotes. A quote that covers multiple obligations will be flagged during Step 3B accuracy judging for atomicity split. Long quotes (>200 characters) covering multiple clauses are automatically suspect — trim to the clause(s) that matter for this specific KRI's check.
13. **Discard traceability — empty reason is a pipeline error**: Every discarded KRI (at any stage: Tier 3 pipeline, de-duplication, domain validation) MUST have a non-empty `reason` field in its discard record. The reason must either: (a) name the covering KRI ID (e.g., "Covered by SAF-AE-004 — same obligation, same section"), OR (b) clearly explain why the cited text does not constitute a valid, atomically verifiable obligation, OR (c) flag it as out of scope (e.g., `"SOA-flavored — handled by soa-kri-extractor"`). An empty, null, or placeholder reason (e.g., "N/A", "see above") is a pipeline error that blocks the run. The Compliance Monitor must verify that all discard records across all artifacts (`{domain}_tier3_filtered.json`, `dedup_report.json`, validation logs) have non-empty reasons before allowing Phase 4 assembly.
14. **Definitional rules are KRIs**: Protocol sentences that define inclusion/exclusion boundaries for clinical concepts are valid KRIs. A sentence of the form "X is defined as...", "X does not include Y when...", or "X is not considered Y unless..." encodes a verifiable rule — a site can deviate by applying the wrong definition. Extract one KRI per definitional sentence. Domain assignment: SAF for adverse event/safety definitions; OPS for operational definitions; ELIG for eligibility criteria definitions. Do NOT skip definitional rules on the assumption that they are "just context" — they are independently verifiable and sites do misapply them.
15. **`rule_for_llm` must be binary and machine-readable**: The `rule_for_llm` field must be binary, unambiguous, and machine-readable — written as a precise, checkable instruction for an LLM system. It must specify exactly WHAT to check, WHEN to check it, HOW to verify compliance, and in relation to WHAT protocol requirement. It must produce a clear YES/NO answer when applied to a data record. It must NOT be narrative prose, a paraphrase of the protocol, or a vague description of intent. Examples of violations: "Ensure the procedure was performed correctly" (not binary), "Check the endpoint definition" (not specific), "The study drug was administered" (not an instruction). When the protocol uses qualitative language (e.g., "in the investigator's opinion", "as soon as possible"), write the rule_for_llm as faithfully as the protocol allows — preserve the qualitative wording verbatim rather than inventing a quantitative threshold the protocol does not state. Downstream filtering of qualitative / non-binary rules happens outside the boundaries of this skill.

## Comparing against a golden set

After Step 4A assembly completes, **always ask the user**:
> "Do you have a golden set to compare against? You can provide a file path or upload it."

If the user provides a golden set, run Step 4C (see `references/steps.md` for full details).

### How comparison works

**Phase 1 — Matching**: For each in-scope category (ELIG, SAF, END, OPS) separately, match extracted KRIs to golden KRIs using semantic similarity (not just ID matching). Handle 1:many and many:1 splits. If the supplied golden set contains SOA entries, they are loaded into a side channel and reported as "out of scope for this skill — see soa-kri-extractor"; they do not count against this skill's score.

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

**How to run Gemini agents (multi-turn with native PDF ingestion — PREFERRED for Phase 2):**

Gemini agents use **multi-turn focused sub-area extraction with native PDF ingestion**. This matches Claude agents' iteration capability (via the Agent tool) and was validated to achieve Claude parity in KRI count on all 4 domains: ELIG 46 (vs Claude 43), SAF 37 (vs 32), END 42 (vs 40), OPS 75 (vs 70).

Each Gemini agent opens a chat session with the PDF uploaded, then runs domain-specific sub-area turns sequentially (e.g., for OPS: IP handling → Blinding → Randomization → Procedures → Docs → Appendices). The focused turns force exhaustive extraction within each sub-area rather than a single broad pass where the model self-limits.

```python
import sys
sys.path.insert(0, "/path/to/scripts")
from gemini_extract import run_gemini_extraction_multi_turn, save_gemini_results

# Uses SUB_AREA_TURNS[domain] template from gemini_extract.py by default.
# See references/steps.md for the exact per-domain sub-area turn definitions.
results = run_gemini_extraction_multi_turn(
    domain="END",              # "ELIG", "SAF", "END", or "OPS"
    pdf_path="/path/to/protocol.pdf",
    n_agents=5,
)
save_gemini_results(results, out_dir, "END")
```

**Scope**: The multi-turn method is used for Phase 2 domain extraction of ELIG, SAF, END, OPS. Claude sub-agents are unchanged (they already iterate via the Agent tool). SOA extraction is out of scope for this skill — handled by the separate `soa-kri-extractor` skill.

**Backward compatibility**: The original `run_gemini_extraction()` (single-shot, text prompt, no PDF) is kept for other uses — e.g., Step 3B accuracy judging, Step 3.5 orphan scan — where single-shot is appropriate.

**Adjudication — consensus-based, per domain:**

| Agent consensus | Action |
|---|---|
| **7–10 agents** found it | Auto-approve into golden set |
| **4–6 agents** found it | Verify against protocol, then present decision table to user. User approves/rejects each. |
| **1–3 agents** found it | Auto-delete |

Decision table shown to user for 4–6 tier KRIs includes: KRI ID, KRI Name, agent count with breakdown (e.g., "5/10 (3C + 2G)"), verified status, reference & quote, and a decision column.

**Process is sequential per domain**: ELIG → SAF → END → OPS. Each domain completes its 10-agent extraction → merge → consensus tiers → Step 2.5 Section Obligation Inventory → Step 2.6 auto-judgment (handles T2 + T3-promoted, produces the decision table) BEFORE the next domain begins. In `--auto-approve-unanimous` mode (default), Step 2.6 completes without blocking; flagged items default to rejected and surface at end-of-run in Step 4A-FlaggedReview.

---

### Tier 3 Promotion Pipeline (ADDITIVE — replaces silent auto-delete, extended 3→5 steps)

KRIs found by only 1–3 agents (Tier 3) are NOT silently discarded. They enter a 5-step promotion pipeline that terminates in Step 2.6 auto-judgment (same 6-judge panel that handles T2). The rule "every discarded KRI must have a non-empty `reason`" (Quality Rule 13) applies to every step.

**Step T3-1 — Coverage Filter** (deterministic): Check whether the Tier 3 KRI's rule is already covered verbatim by an approved Tier 1 KRI (same section + same obligation). If fully covered → discard with reason "Covered by [KRI_ID]". If not → advance to T3-2. Implemented as Step 2.6 Layer 2.

**Step T3-2 — Verbatim Verification** (deterministic): Verify the `supporting_quote` is a verbatim substring of the cited page (Step 3D-style pdfplumber check), the `rule_for_llm` is binary/machine-readable, and the `protocol_reference` resolves to a real page. Any fail → discard with explicit documented reason. Implemented as Step 2.6 Layer 1.

**Step T3-2.5 — Atomicity Check (NEW)** (deterministic): Apply the atomization-of-compound-clauses refinement from SKILL.md (preconditions "can it actually fail?" and "enumeration vs illustrative examples"). Rejects always-true clauses (e.g., "Males or females"), illustrative-example splits, and pure definitions without a verifiable action. Advances candidate if atomic. Implemented as Step 2.6 Layer 1.5.

**Step T3-3 — 6-Judge Panel** (LLM): Dispatch to the same 6-judge neutral panel (3 Claude + 3 Gemini) used for T2 candidates. Each judge votes accept / reject / conditional with a ≤25-word reason. Implemented as Step 2.6 Layer 3.

**Step T3-4 — Aggregate Decision**: Apply Step 2.6 Layer 4 aggregate logic. ≥5 accept (≤1 reject) → auto-approve into Golden Set. ≥5 reject (≤1 accept) → auto-reject. Anything else → flag (see flagged-items handling in the "Step 2.6 Auto-Judgment" section below).

**Artifact**: Save all Tier 3 KRIs and their disposition (promoted / rejected / flagged + reason + stage) to `{domain}_tier3_filtered.json`.

**CRITICAL**: A Tier 3 KRI MUST NEVER be discarded with an empty `reason` field. The reason must name the covering KRI ID (if covered at T3-1) or the specific layer that rejected it with a concrete cause.

---

### Step 2.6 — Auto-Judgment for T2 + T3-Promoted KRIs (MANDATORY, replaces manual decision table)

Runs per-domain, AFTER Step 2.5 Section Obligation Inventory and BEFORE Phase 3. Converts the prior manual Phase-2 decision-table gate into an automated pre-decision step so the pipeline can run end-to-end overnight without blocking on per-domain user review.

**Distinction from other judging steps (critical — avoids confusion):**
- Step 2.6 decides **INCLUSION in the Golden Set** — runs per-domain during Phase 2 on T2 + T3-promoted candidates only.
- **Step 3B** decides **CORRECTNESS** of every KRI — runs after Phase 2 completion, 100% coverage, 5-judge panel (3 Claude + 2 Gemini). Different panel, different purpose. **Step 2.6 does NOT replace Step 3B.**
- **Step 3.5** orphan scan discovers **MISSED rules** — 6-agent panel, Phase 3. Different purpose.

**4-layer engine per candidate** (implemented in `scripts/step2_6_autojudgment.py`):

| Layer | What it checks | Type | Failure → |
|---|---|---|---|
| Layer 1 — Verification gate | Verbatim `supporting_quote` substring + binary `rule_for_llm` + reference sanity | Deterministic | auto-reject |
| Layer 1.5 — Atomicity | Always-true / illustrative-examples / pure-definition violations (atomization refinement) | Deterministic | auto-reject |
| Layer 2 — Coverage/dedup | Already covered by an approved T1 KRI? | Deterministic | auto-reject |
| Layer 3 — 6-judge neutral panel | 3 Claude + 3 Gemini independently vote accept / reject / conditional on this KRI | LLM | Layer 4 aggregates |
| Layer 4 — Aggregate | ≥5 accept + ≤1 reject → auto_approve. ≥5 reject + ≤1 accept → auto_reject. Anything else → flag. | Deterministic | flag goes to decision table |

**Judge prompt**: all 6 judges share the same CRA-framed prompt (consistent with the 10-agent extraction panel). No personas. See `scripts/autojudgment_prompts.py`.

**Gate behavior — `--auto-approve-unanimous` (default ON)**:
- Pipeline runs to completion without blocking per-domain on flagged items.
- Flagged items default to REJECTED at Phase 4 (conservative Golden Set).
- Flagged items are preserved verbatim in each domain's `{domain}_manual_review_decisions.json.sections.flagged_for_review` AND surfaced together in the end-of-run consolidated **Step 4A-FlaggedReview** table (`flagged_review_decisions.json`) so the user reviews all 4 domains' flagged items in one pass.
- The user can re-include any flagged KRI by setting `user_override: "include"` in `flagged_review_decisions.json` and re-running `python run.py --from 4a` to regenerate the Golden Set.

**Gate behavior — `--interactive`**:
- Pipeline pauses per-domain on flagged items. User must Accept / Reject / Edit every flagged row before advancing to the next domain. Matches the prior "Per-Domain Manual Review Checkpoint" blocking behavior.

**Relationship to the prior MANDATORY BLOCKING GATE**: in `--interactive` mode the gate behaves exactly as before (blocks at Phase 2 for that domain until user decides every row). In `--auto-approve-unanimous` mode the gate **shifts forward to Phase 4** — it still blocks the Golden Set from assembly if `flagged_review_decisions.json` indicates the user has pending overrides to apply. The gate is never silently removed; its enforcement point is mode-dependent.

**Scope of `--auto-approve-unanimous`**: affects Step 2.6 ONLY. Step 3.5 orphan scan USER_DECISION items and Step 3B accuracy FLAG items retain their own independent pause behavior — neither is affected by this flag.

**Decision-table columns** (unchanged display format, now produced by Step 2.6):

| Column | Content |
|---|---|
| KRI ID | Proposed ID (e.g., `SAF-AE-007`) |
| Tier | `T1` / `T2` / `T3` |
| KRI Name | Short descriptive name |
| Description | 1–2 sentence description |
| Agents | Count (e.g., `5/10`) |
| Protocol Ref | Section + page |
| Supporting Quote | Verbatim excerpt |
| Auto-decision | `auto_approve` / `auto_reject` / `flag` |
| Reason | One-sentence synthesis from the layer that produced the decision |
| Panel summary | `{accept}A/{reject}R/{conditional}C/{error}E` (e.g., `5A/1R/0C/0E`) |
| Decision source | `auto` or `user_override` |
| User override | `include` / `exclude` / null |

**Artifact**: `{domain}_autojudgment_report.json` (full layer-by-layer audit) + `{domain}_manual_review_decisions.json` (sectioned decision table). Both written per domain.

**Quality Rule 13 compliance**: every auto-rejected KRI has a non-empty `reason` identifying the specific layer that rejected it.

---

### Step 4A-FlaggedReview — End-of-Run Cross-Domain Flagged Review (runs after Step 4A-Dedup)

Collects every flagged KRI from all 4 domains' Step 2.6 autojudgment outputs and produces a single consolidated table (`flagged_review_decisions.json`) with FULL KRI columns so the user can scan all flagged items in one pass, not per-domain.

- **Input**: all `{domain}_manual_review_decisions.json.sections.flagged_for_review` rows.
- **Default action at Phase 4**: flagged items are **rejected** (not included in the Golden Set). They are preserved in the artifact for review.
- **User re-inclusion workflow**:
  1. Review `flagged_review_decisions.json`.
  2. Set `user_override: "include"` on any row you want back in the Golden Set.
  3. Run `python scripts/step4a_flagged_review.py --out /path/ --apply-overrides` (this re-adds included KRIs to their source domain's `raw_{DOMAIN}.json`).
  4. Re-run `python run.py --pdf ... --out ... --from 4a` to regenerate the Golden Set.

This decouples overnight pipeline completion from user review. The user reviews once at the end across all domains, not five times during the run.

---

### Interactive Review Table — Protocol View Integration

The per-domain decision table is rendered as an **interactive HTML page** in the Preview application (`mcp__Claude_Preview__*`). Each row includes a **"View in Protocol"** button with the following behavior:

1. **Opens** the protocol PDF text (via pdfplumber extraction of the cited page ± 1 page), or switches to an already-open view.
2. **Highlights** the exact `supporting_quote` text using `<mark>` HTML tags with a yellow background, scrolling the view to the match.
3. The highlighted view appears in a side panel next to the decision table so the user can read the protocol context and make their decision without leaving the table.

**Accept / Reject / Edit buttons** are live:
- **Accept**: Marks the KRI as accepted; it will enter the domain KRI set.
- **Reject**: Marks the KRI as rejected; it will be excluded (logged with reason in `{domain}_manual_review_decisions.json`).
- **Edit**: Opens an inline editor for any field (name, description, quote, reference). After editing, the user clicks Accept to finalize. Edits are stored verbatim.

The table displays immediately at the end of each domain's tier adjudication — **do not wait** for the next domain or phase before displaying it. If no T2 or T3-PROMOTED KRIs exist for a domain, display a brief confirmation: "Domain [X]: 0 KRIs require manual review — all approved automatically at Tier 1."

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

## Freezing a Golden Set (Regression Vault)

After a full extraction run is complete, validated (Step 3D passes at 100%), assembled (Step 4A), and the user has reviewed and approved the golden set — **ask the user if they want to freeze it in the regression vault.**

The regression vault preserves approved golden sets so that future skill updates can be checked for regressions. Each frozen golden set is immutable and represents ground truth for that protocol.

**When to ask:** After Step 4A assembly is complete and the user has confirmed they are satisfied with the results. Say something like:

> "The golden set for [protocol] is complete and validated. Would you like to freeze it in the regression vault? This preserves it so we can detect if future skill updates break anything."

**If the user says yes**, use the `kri-regression-tester` skill's freeze operation. Specifically, run:

```bash
python ~/.claude/skills-repo/plugins/kri-regression-tester/scripts/freeze.py \
  --source <run_directory> \
  --vault ~/Documents/kri-regression-vault \
  --protocol-id <protocol_id> \
  --protocol-name "<protocol_name>" \
  --skill-path ~/.claude/skills-repo/plugins/protocol-kri-extractor/skills/protocol-kri-extractor/SKILL.md
```

This copies all artifacts (extracted_kris.json, Extracted_KRIs.xlsx, raw domain files, manifest, ontology, footnote map, verification reports, etc.) into `~/Documents/kri-regression-vault/<protocol_id>/` alongside a snapshot of the current SKILL.md.

**If the user says no**, move on. The golden set remains in its run directory but is not vault-protected.

**At the start of any session where this skill will be edited**, run the regression test first to establish a clean baseline. Use the `kri-regression-tester` skill for this.

---

## Reference files

- `references/steps.md` — detailed LLM prompt templates for each step (each domain extractor prompt carries the "Out of scope — SOA" methodology block)
- `references/kri_examples.md` — annotated KRI examples per in-scope category (ELIG, SAF, END, OPS)
- `scripts/run.py` — single canonical pipeline entry point
- `scripts/step1a_manifest.py` — Step 1A manifest builder (ELIG/SAF/END/OPS section map)
- `scripts/step2_extract.py` — Step 2 KRI extraction (per-domain, 10-agent multi-model panel) with SOA-exclusion methodology in every prompt
- `scripts/gemini_extract.py` — Gemini API extraction agents (multi-model competition)
- `scripts/step2_6_autojudgment.py` — Step 2.6 auto-judgment (4-layer engine)
- `scripts/autojudgment_prompts.py` — neutral CRA-framed judge prompts
- `scripts/step3_5_orphan_scan.py` — Protocol-wide orphan scan (6-agent panel, section + page sweeps, SOA-flavored candidates dropped as `out_of_scope_soa`, blocking gate)
- `scripts/step3a_completeness.py` — Obligation-inventory completeness check + H4 SAF heuristic
- `scripts/step3b_accuracy.py` — Full KRI accuracy judging at 100% coverage (5-judge cross-model panel, blocking gate)
- `scripts/step3c_consistency.py` — Cross-KRI consistency check
- `scripts/step3d_verify.py` — Full verbatim pdfplumber verification (blocking gate)
- `scripts/step4a_assemble.py` — Assembly + Excel generation (4 in-scope domain sheets + Summary)
- `scripts/step4a_dedup.py` — Cross-domain + intra-domain dedup, includes the SOA-flavored safety-net deletion clause
- `scripts/step4a_flagged_review.py` — End-of-run cross-domain flagged-review consolidator
- `scripts/step4b_compare.py` — Optional golden-set comparison
