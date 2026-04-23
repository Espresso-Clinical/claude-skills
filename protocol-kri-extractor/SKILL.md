---
name: protocol-kri-extractor
description: >
  Extracts Key Risk Indicators (KRIs) from clinical trial protocol PDFs and
  produces the authoritative Golden Set — the definitive, verified, structured
  list of monitoring rules for a given protocol. Use this skill whenever the user
  wants to: parse a clinical protocol, extract rules or guidelines from a protocol
  PDF, generate KRIs, or build a monitoring rule set. Works on any Phase 2/3 trial
  regardless of sponsor or format (ALLOVIVE, Pfizer, Novartis, or any other).
  Always use this skill when a protocol PDF is provided and the user wants
  structured extraction of any kind.
---

# Protocol KRI Extractor

## Ultimate Goal

This skill **creates the Golden Set** — the authoritative, verified collection of KRIs for a given clinical trial protocol. The Golden Set is the primary deliverable. It is not a comparison tool, a validation tool, or a QC tool against a pre-existing set. The skill itself, working from the protocol PDF alone, produces the ground-truth KRI list that becomes the standard for that protocol.

The output (`golden_set.json` + `Extracted_KRIs.xlsx`) is the source of truth — not derived from any prior set and not judged against any prior set.

---

Extracts monitoring rules (KRIs) from any clinical trial protocol PDF.
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
- De-duplication, orphan scan (both footnote-level AND protocol-wide), NDEF classification, verbatim verification, full accuracy judging, Compliance Monitor, and all other steps documented here remain in force forever unless explicitly removed
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
| 1A | `manifest.json` | |
| 1B-Camelot | `soa_table.csv`, `soa_table.json` | |
| 1B-Vision | `page_images/`, `vision_SOA_table.json`, `multipass_conflicts.json` | |
| 1B-ColDetect | `column_detection.json`, `vision_corrections.json` | |
| 1B-Ontology | `ontology.json` | |
| 1C | `footnote_map.json` (with footnote-level orphan validation block) | |
| 2 (per domain) | `raw_{DOMAIN}.json`, `{DOMAIN}_adjudication.json` | |
| 2 (multi-model) | 5 Claude agent outputs + 5 Gemini agent outputs per domain | |
| 2 (consensus) | Tier 1 auto-approved, Tier 2 decision table shown to user, Tier 3 → promotion pipeline (`{domain}_tier3_filtered.json`) | |
| 2 (per-domain checkpoint) | `{domain}_manual_review_decisions.json` — user acceptance/rejection record for all T2 + promoted T3 KRIs | |
| 2.5 (obligation inventory) | `{domain}_obligation_inventory.json` — all obligation sentences found, with KRI coverage check | |
| **3.5** | **`orphan_scan_report.json` (primary section sweep + secondary page sweep + consolidation + cross-check + classification + user decisions + promoted orphans appended to `raw_{DOMAIN}.json`)** | |
| 3A | `gaps_report.json` | |
| 3A+ | Heuristics H1-H10 results | |
| **3B** | **`accuracy_report_full.json` (100% KRI coverage, 5-judge cross-model panel, 0 FAIL, 0 unresolved FLAG — blocking)** | |
| 3C | `consistency_report.json` | |
| 3D | `verify_report.json` — must show 100% pass | |
| 4A | `extracted_kris.json`, `Extracted_KRIs.xlsx` | |
| 4A-Dedup | `dedup_report.json` (contains `cross_domain`, `intra_domain`, and `kept_despite_similarity` sections) | |

**3. Multi-Model Extraction Enforcement**
For Step 2, the monitor MUST verify:
- Exactly 5 Claude sub-agents were launched per domain
- Exactly 5 Gemini agents were launched per domain (via `gemini_extract.py`)
- All 10 agent outputs were collected and merged
- Consensus tiers were correctly applied:
  - 7-10 agents (T1) → auto-approved (verify these went into the domain's KRI set)
  - 4-6 agents (T2) → Step 2.6 auto-judgment (6-judge neutral panel) produced a per-KRI pre-decision. `{domain}_autojudgment_report.json` and `{domain}_manual_review_decisions.json` exist with full layer-by-layer results. In `--auto-approve-unanimous` mode (default ON), flagged items default to rejected and surface at end-of-run in `flagged_review_decisions.json` (Step 4A-FlaggedReview). In `--interactive` mode, every flagged row has an explicit user decision.
  - 1-3 agents (T3) → Tier 3 promotion pipeline (T3-1 Coverage / T3-2 Verbatim / T3-2.5 Atomicity / T3-3 Panel / T3-4 Aggregate) handled by Step 2.6. NOT auto-deleted. Verify `{domain}_tier3_filtered.json` exists with per-KRI dispositions.
- The domain processing order was sequential: SOA → ELIG → SAF → END → OPS
- Each domain completed fully (Step 2.6 produced its decision table, flagged items either resolved in `--interactive` mode OR defaulted to rejected in auto-approve mode) before the next domain began

**4. Blocking Gate Enforcement**
The monitor enforces all blocking gates:
- Step 3D must report 100% pass before Step 4A can begin
- If Step 3D has failures, the pipeline must stop and fix them before proceeding
- The user must be asked about golden set comparison at Step 4B

**5. Rule Compliance Spot-Checks**
The monitor periodically spot-checks KRIs against the quality rules in this skill:
- Atomicity: each KRI is one verifiable check about one thing
- Domain boundaries: SOA owns "procedure at visit", SAF owns thresholds, OPS owns methodology
- Field format: `supporting_quote` has no outer quotes, `combined_ref` uses em dash, no duplicate page numbers
- SOA reference rules: correct page range, footnote numbers match `footnote_map.json`

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
  "kri_id": "SOA-V1-001",
  "kri_name": "V1- IMP administration",
  "description": "What this KRI monitors and why it matters",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V1- Verify that [specific actionable check with exact values]",
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
- **SOA table/footnote page reference rule**: For SOA KRIs derived from the SoA table or its footnotes, `protocol_reference` must use the **full page range** covering the table AND all footnote pages (e.g., `"Schedule of Activities, Footnote 4, p.24-p.29"`). Do NOT cite individual pages within the table section. Do NOT add a "Section X.X" prefix if the SoA table has no section number — just use `"Schedule of Activities"`. Only SOA KRIs whose content comes from protocol TEXT outside the table (e.g., dosing instructions from Section 5.4) should have a specific section + page reference.
- **No fabricated section numbers for SOA table**: If the SoA table in the protocol has no section number (many protocols just have it as a standalone table), do not invent one. Use `"Schedule of Activities"` as the reference label.

## CRITICAL — Atomicity Principle (applies to ALL domains)

**Every KRI must be atomic.** A single KRI must represent exactly ONE verifiable check about ONE thing at ONE time point in ONE clinical context. Never combine multiple rules, multiple endpoints, multiple procedures, multiple time points, or multiple clinical settings into a single KRI.

Examples of atomicity violations (WRONG):
- "Verify LDL-C, Non-HDL-C, Apo B, and triglycerides percent change at Week 14" → Must be 4 separate KRIs, one per analyte
- "Verify vital signs and laboratory assessment at V3" → Must be 2 separate KRIs
- "Verify key secondary endpoints are composite of CV death, MI, stroke, and UA" → Must be one KRI per distinct composite endpoint definition

Examples of correct atomicity:
- "Verify that the percent change from baseline in LDL-C (direct measurement) is calculated at Week 14 (Visit 8)"
- "Verify that vital signs were measured at V3"
- "Verify that the key secondary endpoint is calculated as time from randomization to the first occurrence of a composite of CV death, non-fatal MI, and non-fatal stroke"

**This applies across all domains:** SOA (one procedure × one visit = one KRI), ELIG (one criterion or sub-criterion = one KRI), SAF (one reporting rule or one stopping rule = one KRI), END (one endpoint definition or one governance rule = one KRI), OPS (one operational rule = one KRI).

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

**Important — consistency across all agents and domains:** this rule applies identically to Claude sub-agents and Gemini agents, and across SOA / ELIG / SAF / END / OPS. The goal is consistent atomic granularity regardless of which agent produced the KRI.

Six categories (universal across all trials — from ICH GCP):
- **SOA** — Schedule of Activities
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints, Statistics & Governance (see detailed sub-categories below)
- **OPS** — Operations & Compliance
- **NDEF** — Non-Definable: the final-output classification for KRIs whose rule cannot be verified by a machine in an unambiguous, deterministic way. **NDEF is NOT an extraction target.** Phase 2 extractors place every rule into one of the 5 real domains (SOA/ELIG/SAF/END/OPS). The NDEF category is populated later by the **NDEF Sweep** (Step 4A-NDEF), which runs after Phase 2 extraction, the orphan scan, Step 4A assembly, and dedup — it reviews every extracted KRI and *moves* any whose rule cannot be checked deterministically out of its source domain and into NDEF. A KRI qualifies as non-definable if its rule cannot produce a clear YES/NO answer when applied to subject data — this includes investigator clinical judgment ("in the opinion of", "if clinically significant"), undefined time windows ("as soon as possible", "in a timely manner", "promptly"), undefined effort or quantity ("reasonable effort", "adequate", "sufficient"), subjective thresholds, or any other non-binary wording. Rule format for NDEF entries: `"NDEF — Non-verifiable: [reason why LLM cannot verify]"`. NDEF KRIs are documented so auditors know the obligation exists but flagged as out-of-scope for automated monitoring. **NDEF KRIs use the same column format as all other domains: KRI ID, KRI Name, Category, Description, Rule for LLM, Protocol Reference & Quote. NDEF is not a reduced-format domain.**

---

## CRITICAL — Domain Boundary Rules (prevents cross-domain duplicates)

### Rule 1 — SOA owns all "procedure happened at visit" checks

If a KRI is essentially **"Verify that [procedure] was performed at [visit]"** — it belongs in **SOA only**. Never in SAF or OPS.

This means:
- Lab timing ("hepatitis B and C collected at Visit 1") → **SOA**, not SAF
- Visit window ("V0 to V1 maximum 30 days") → **SOA** check-in KRI, not OPS
- Contraception check at designated visits → **SOA** procedure KRI, not SAF
- IRT registration at every visit → **SOA** Contact IRT KRI, not OPS
- HbA1c collected at baseline/V11/EDC → **SOA** procedure KRI, not SAF
- Plasma biospecimen collection at V5/V11 → **SOA** procedure KRI, not SAF
- Lipid profile not collected at EDC/EOS → **SOA** footnote rule, not SAF
- EOS visit no sooner than 14 days after last dose → **SOA-CROSS**, not SAF

**Red-flag test**: If a KRI's `rule_for_llm` contains the phrase "per SOA", "per schedule", "per the SoA table", or "at [visit name]" and is describing THAT something was done — it belongs in SOA. Delete the SAF or OPS version.

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
- ✗ When/whether a procedure occurs at a specific visit → **SOA**
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

### Rule 4 — NDEF is a post-extraction classification, not an extraction target

NDEF is **not** a domain that Phase 2 extractors populate. During extraction, every rule goes into one of the 5 real domains (SOA/ELIG/SAF/END/OPS) using Rules 1–3. NDEF is populated later by the **NDEF Sweep** (Step 4A-NDEF), which runs after Phase 2 extraction, the orphan scan, Step 4A assembly, and dedup. The sweep applies the criteria below to every extracted KRI and **moves** matching KRIs out of their source domain into NDEF.

A KRI is **non-definable** — and therefore belongs in NDEF — if its rule cannot produce a deterministic, unambiguous YES/NO answer when applied to a subject's data. This is a broad definition and includes (but is not limited to):

- **Investigator judgment** — wording like "in the investigator's opinion", "if clinically significant", "clinically relevant", "per clinical judgment". Examples: emergency unblinding decisions (investigator determines medical necessity); causality determinations framed as "immediately notify if clinically significant"; exclusion criteria framed as "in the investigator's opinion" with no objective measurable proxy.
- **Undefined time windows** — "as soon as possible", "in a timely manner", "promptly", "without undue delay", "reasonable time" — no concrete numeric window the data can be compared against.
- **Undefined effort, quantity, or completeness** — "reasonable effort", "adequate", "sufficient", "appropriate", "best effort" — no concrete threshold.
- **Subjective thresholds** — any criterion whose threshold is a qualitative judgment rather than a measurable value.
- **Any other non-binary wording** — if the rule cannot be rewritten as a concrete check against a data field with a deterministic YES/NO answer, it is non-definable.

Phase 2 extractors do NOT attempt to classify KRIs as NDEF. They extract every rule (including judgment-based and vague ones) into the real domain the rule belongs to. The sweep then performs reclassification in one consistent pass using a judge panel — this produces more consistent NDEF boundaries than having each domain extractor make its own call. See "CRITICAL — NDEF Sweep" below for the full spec.

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
- Two KRIs that check the same rule at different visits
  - Example: V1 check-in window vs V2 check-in window — both kept
- Two KRIs that check different analytes in the same panel
  - Example: Apo B and LDL-C in the same lipid panel are separate KRIs
- Two KRIs that check the same procedure in different clinical settings
  - Example: fasting lipid vs non-fasting lipid — both kept
- Two KRIs that check different sub-criteria of the same eligibility criterion
  - Example: one inclusion criterion with 4 sub-bullets → 4 KRIs, all kept
- Two KRIs that check different endpoints within the same composite definition
  - Example: composite endpoint "CV death, MI, stroke" → 3 KRIs for the individual components PLUS 1 KRI for the composite definition = 4 KRIs, all kept
- Two KRIs where one checks the act (procedure performed) and the other checks the technique (how it was performed)
  - Example: SOA KRI "V3 — Blood pressure measured" and OPS KRI "Blood pressure measured in sitting position after 5-min rest" — different things, both kept

**Default when in doubt: KEEP BOTH.** Deletion is only justified when a duplicate is unambiguous. A false merge is worse than a false retention — a retained duplicate is visible in the Excel output and can be caught by human review, while a silently deleted atomic KRI is gone forever and the protocol coverage is permanently broken.

### Step 4A-Dedup — Two-pass Detection

**Sub-pass A — Cross-Domain Duplicate Detection**

1. For each KRI in SAF and OPS, check: does a SOA KRI already cover this same clinical check (under the TRUE DUPLICATE definition above)?
   - If a SAF KRI checks "that [lab] was collected at [visit]" and a SOA KRI for that procedure × visit exists → **delete the SAF KRI** (SOA owns it)
   - If an OPS KRI checks "visit window for V[N]" and a SOA-CHECKIN-V[N] KRI exists → **delete the OPS KRI** (SOA owns it)
   - If an OPS KRI checks "IRT registered at every visit" and SOA Contact IRT KRIs exist → **delete the OPS KRI**

2. **Ownership hierarchy** (when the same atomic rule appears in multiple domains, this domain wins):

   | Rule type | Owner | Delete from |
   |---|---|---|
   | Procedure happened at visit | SOA | SAF, OPS |
   | Visit timing / window | SOA | OPS |
   | Safety threshold + response | SAF | OPS |
   | Measurement technique | OPS | SAF |
   | Scheduling coordination rule (e.g. postpone test X with test Y) | SOA-CROSS | SAF, OPS |

3. **Cross-domain dedup only fires on TRUE DUPLICATES.** If two KRIs in different domains overlap in topic but check different atomic things (e.g., SAF "CK >5× ULN triggers IP stop" vs OPS "CK measurement technique"), **both are kept**. The ownership hierarchy resolves ownership only when the atomic check is identical, not when the topic is shared.

**Sub-pass B — Intra-Domain Duplicate Detection (fully active, not secondary)**

1. Within each domain, scan for **exact** duplicates using the TRUE DUPLICATE definition above.
2. Two KRIs with different IDs but essentially interchangeable `rule_for_llm`, same specific values, same time point, same context → keep the one with the richer description (more specific values, more footnote context), delete the other.
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

## CRITICAL — NDEF Sweep (Step 4A-NDEF, MANDATORY, runs AFTER dedup)

The NDEF Sweep is the single place where KRIs are reclassified into NDEF. It runs once per extraction, after Step 4A assembly and after Step 4A-Dedup, and before the Final summary. It is mandatory — no run may finalize without it.

**What it does**: reviews every KRI in the assembled set across the 5 real domains (SOA/ELIG/SAF/END/OPS) and **moves** any KRI whose rule is not machine-checkable into NDEF. This is a MOVE, not a copy — the source domain no longer contains the KRI after the sweep.

**Why it is centralized here (not done by the extractors)**: Phase 2 agents see only their own domain and would each make their own NDEF judgment, producing inconsistent boundaries (e.g., ELIG agent flags a judgment-based criterion as NDEF, SAF agent leaves a similar one in SAF). A single post-assembly pass with a judge panel applies one consistent standard across the whole set.

### What qualifies as non-definable (binding definition — same criteria as Rule 4)

A KRI is non-definable if its `rule_for_llm` cannot produce a deterministic YES/NO answer when applied to concrete subject data. This includes:

- **Investigator judgment**: "in the investigator's opinion", "if clinically significant", "clinically relevant", "per clinical judgment", emergency unblinding decisions.
- **Undefined time windows**: "as soon as possible", "in a timely manner", "promptly", "without undue delay", "reasonable time".
- **Undefined effort, quantity, or completeness**: "reasonable effort", "adequate", "sufficient", "appropriate", "best effort".
- **Subjective thresholds**: thresholds expressed as qualitative judgments rather than measurable values.
- **Any other non-binary wording**: any rule that cannot be rewritten as a concrete check against a data field with a deterministic YES/NO answer.

A KRI stays in its source domain if it has a concrete check — even if it is complex — such as a numeric threshold, a specific time window (e.g., "within 24 hours", "≤30 days"), a named data field, or a countable event.

### How the sweep works

**Input**: the assembled `extracted_kris.json` plus the 5 `raw_{DOMAIN}.json` files, after dedup.

**Process**: a 6-agent judge panel (3 Claude + 3 Gemini) reviews each KRI independently and votes `DEFINABLE` / `NON_DEFINABLE` with a one-sentence reason. Consensus tiers are the same as other panels in this skill:

| Vote distribution | Action |
|---|---|
| **5–6 agents vote NON_DEFINABLE** | Auto-move to NDEF (no user review). |
| **3–4 agents vote NON_DEFINABLE** | Present to user in a decision table with agent vote breakdown and quoted reasons; user decides per-KRI. |
| **0–2 agents vote NON_DEFINABLE** | Keep in source domain. |

Each moved KRI:
- Has its `category_id` changed to `"NDEF"` and `category_label` to `"Non-Definable"`.
- Gets a new `kri_id` in the `NDEF-###` sequence (keeping `original_kri_id` in a sidecar field for audit).
- Has `rule_for_llm` rewritten to the fixed NDEF format: `"NDEF — Non-verifiable: [reason why LLM cannot verify]"` (reason comes from the panel consensus).
- Gets an `original_domain` field set to the source domain, for the audit trail.
- Keeps its original `protocol_reference`, `supporting_quote`, `combined_ref`, `description` unchanged — the rule's source in the protocol does not move.

**Output**:
- `raw_NDEF.json` — all newly-classified NDEF entries.
- `ndef_sweep_report.json` — per-KRI vote breakdown, reasons, and user decisions (audit trail).
- Updated `raw_{SOURCE_DOMAIN}.json` files with the moved KRIs removed.
- Updated `extracted_kris.json` reflecting the final classification.

**Atomicity / dedup interaction**: the sweep operates AFTER dedup, so atomization splits and cross-domain dedup decisions are already resolved. The sweep does not merge, split, or delete KRIs — it only moves them between domains.

**Idempotence**: running the sweep twice on the same assembled set produces the same output (no second-round movements, unless user decisions on the T3 tier change).

### What the sweep does NOT do

- It does NOT extract new KRIs. Phase 2 and the orphan scan are the only sources of KRIs.
- It does NOT merge or split KRIs. Dedup and atomization handle those concerns.
- It does NOT delete KRIs. Every KRI stays in the assembled output — it either remains in its source domain or is moved to NDEF.
- It does NOT re-run if a user rejects a proposed move — the KRI stays in its source domain and the decision is logged.

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
pip install pdfplumber pymupdf camelot-py[cv] opencv-python-headless openpyxl --break-system-packages -q
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
`1a → 1b-camelot → 1b → 1c → 2 → 3.5 → 3a → 3b → 3c → 3d → 4a → 4a-dedup → 4b`

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

**Step 1A — Manifest**: Read cover pages + TOC. Map every section to SOA/ELIG/SAF/END/OPS. (NDEF is not an extraction target — it is populated post-assembly by the NDEF Sweep. See Rule 4.)

**Step 1B-Camelot — Table Extraction (PRIMARY)**: Use Camelot (lattice mode) via `scripts/camelot_table_extractor.py` to extract the SoA table into `soa_table.csv` and `soa_table.json`. This is the **PRIMARY** source of truth for the SoA procedure × visit grid. Camelot reads table line geometry from the PDF and gives ~99% structural accuracy — deterministic, reproducible, and not affected by LLM variance. Handles multi-page tables automatically. The CSV and JSON outputs become the canonical SoA data for all downstream steps.

**Step 1B-Vision — Vision Fallback (SECONDARY)**: For cells where Camelot detects the lattice structure but the cell content contains footnote superscripts that Camelot may read as empty, use Claude Vision at 450 DPI as fallback. The camelot extractor correctly handles compound and dot-separated footnote superscripts in table cells — e.g., `X10`, `X13,14`, `X13·14` — parsing both the X mark and all associated footnote numbers. No footnote association is missed due to superscript formatting. Also use multi-pass vision (full + left 55% crop + right 55% crop at 450 DPI) with majority voting for wide tables (>12 columns) to recover any cells Camelot missed. Save conflicts in `multipass_conflicts.json`.

**Step 1B-ColDetect — Column Boundary Detection**: After extraction, run `scripts/vision_table_extractor.py` column detection to verify column boundaries match the Camelot-extracted structure. Flag any discrepancies.

**Step 1B — Ontology**: Build the SoA ontology from the Camelot-extracted table data (verified by vision fallback where needed). Run **Footnote Cross-Validation** as a safety net.

**Step 1C — Deterministic Footnote Mapping (MANDATORY)**: Run `scripts/footnote_mapper.py` to build a fully deterministic map of which footnotes belong to which procedure × visit cells. This uses PDF character geometry (font size detection for superscripts) and Camelot cell text parsing — **zero LLM calls**. The output `footnote_map.json` becomes the single source of truth for all footnote associations in SOA KRI generation. The LLM never guesses which footnotes apply — it receives the pre-computed map.

### Phase 2 — Extract (6-Step SOA Process)

The SOA extraction follows a strict 6-step process:

1. **Visit mapping**: Pull all visits and their timing from the Camelot CSV. Establish naming conventions (V0, V1, V2... EDC_EOS). From this point forward, use ONLY these canonical names.
2. **Table verification**: Compare the Camelot CSV against the PDF image for verification. Flag any discrepancies. Save `soa_table.csv` and `soa_table.json` as the tracking artifacts.
3. **Check-in KRIs**: For each visit, create ONE check-in KRI verifying the subject attended within the protocol-specified timing window. The protocol-specified timing window must be sourced from wherever the protocol defines it — table header, footnote, dedicated timing section, or protocol amendment. Do not assume or generalize from another visit's window.
4. **Procedure KRIs**: For each visit, create ONE KRI listing ALL procedures required at that visit (in the format: `V1 - procedure name`). Also create one KRI per procedure × visit cell.
5. **Footnote enrichment**: After the table-based KRIs are complete, read all footnotes from the protocol and enrich each KRI with relevant footnote details. Also create **cross-visit rule KRIs** for protocol-wide rules (fasting requirements, dosing windows, 10-day lipid rule, IP administration sequence, missed visit escalation, EDC retention, safety follow-up periods, etc.).
6. **Self-verification**: Cross-check that every X cell in the Camelot CSV has a corresponding KRI. Report: `N/N cells covered = 100%`.

For the 5 text-extracted domains (ELIG, SAF, END, OPS, and **SOA-text**), extraction uses a **10-agent multi-model panel** (5 Claude Sonnet + 5 Gemini 2.5 Pro agents running in parallel). Consensus determines tier: **Tier 1** = 7–10 agents agree (auto-approved into Golden Set), **Tier 2** = 4–6 agents agree (**Step 2.6 auto-judgment** produces the per-KRI pre-decision), **Tier 3** = 1–3 agents (enters Tier 3 promotion pipeline, terminating in Step 2.6 auto-judgment). Step 2.6 replaces the prior manual decision-table pause with an automated 4-layer engine (verification gate, atomicity check, dedup/coverage, 6-judge neutral panel, aggregate). With `--auto-approve-unanimous` ON (default), the pipeline runs end-to-end without blocking; flagged items default to rejected and surface at end-of-run in **Step 4A-FlaggedReview** for cross-domain user review and optional re-inclusion. Per-domain content rules:
- ELIG: one KRI per criterion/sub-criterion. Extract every criterion into ELIG regardless of whether it is objectively verifiable — judgment-based or vaguely-worded criteria are reclassified to NDEF later by the NDEF Sweep (Step 4A-NDEF), not by the extractor.
- SAF: every reporting timeline, stopping rule, emergency protocol
- END: **two sub-categories** — (1) one KRI per endpoint definition (primary, each key secondary, each other secondary individually, each biomarker analyte × measurement type, each HCRU metric), (2) one KRI per governance rule (analysis populations, interim analysis triggers, alpha spending, study end definition, data locks)
- OPS: IMP handling, blinding, records, compliance
- **SOA-text** (additive layer): protocol-wide / cross-visit / narrative-only SOA rules that are NOT in the SoA table — drug-timing separations, study-wide duration caps, cross-visit procedure methodology, long-term follow-up obligations, global visit windows, sample/volume caps. Output merges into `raw_SOA.json` alongside Phase 1 output. Guardrails in every SOA-text agent prompt forbid re-extracting table cells or footnote cell-rules (those come from Phase 1). See "SOA-text Phase 2 extraction" subsection below for the full spec.

### SOA-text Phase 2 extraction (additive — does NOT replace Phase 1 SOA)

Phase 1 extracts SOA from the **SoA table** using a deterministic Camelot + footnote-mapping process, plus step-5 cross-visit rules derived from footnotes. That process remains the authoritative source for:
- Every "procedure × visit" cell-level KRI (one X in the table = one KRI).
- Every footnote-anchored rule that attaches to specific cells.
- The cross-visit rule KRIs produced by Phase 1 step 5 from footnotes and known protocol-wide rules.

Empirically, Phase 1 step 5 misses some protocol-wide SOA rules that live in the protocol narrative rather than the SoA table or its footnotes — e.g., drug-timing separations ("administer phage ≥2 h before antibiotic"), total study-duration caps ("≤56 weeks"), "all visits must occur regardless of healing status", long-term follow-up obligations at W26/W52, global visit-window tolerances, cumulative blood-volume caps. The SOA-text Phase 2 layer exists to catch these.

**Scope rules (apply to every SOA-text agent prompt — MANDATORY)**:
1. Do **NOT** extract "procedure X at visit Y" KRIs — those come from the Camelot table in Phase 1.
2. Do **NOT** extract footnote rules that attach to specific table cells — the deterministic footnote mapper already covers those.
3. Only emit KRIs that are protocol-wide, cross-visit, or narrative-only. If a rule appears in the SoA table or its footnotes, skip it.
4. Respect Rule 1 (SOA ownership) — "procedure happened at visit" KRIs already belong to Phase 1 SOA; do not duplicate them here.
5. Use prefix `SOA-TEXT-NNN` for narrative-only rules. Use `SOA-CROSS-NNN` for cross-visit / protocol-wide rules (same prefix Phase 1 step 5 already uses for its cross-visit output).

**Sub-area turn templates** (defined in `scripts/gemini_extract.py::SUB_AREA_TURNS["SOA"]`; mirrored for Claude sub-agents):

1. Drug administration timing & separations — §5/§7 narrative (drug-to-drug gaps, infusion durations, order-of-administration).
2. Study-wide duration & schedule meta-rules — §3/§4 narrative (total duration caps, "all visits must occur", screening→randomization windows).
3. Cross-visit procedure methodology — §6 narrative (rules applying identically across all visits of a procedure — technique, equipment, sample handling).
4. Long-term follow-up obligations — §9/§10 narrative (vital status, SAE collection at LTFU, ulcer-recurrence windows).
5. Global visit windows & tolerances — visit-schedule narrative (±3/±7 day windows applying uniformly, grace periods, missed-visit rules).
6. Sample & volume caps — cumulative/study-wide caps on blood volume, tissue samples, imaging doses.

**Output merging**: SOA-text KRIs are appended to `raw_SOA.json` alongside Phase 1 output. Overlap with Phase 1 step 5 cross-visit rules is expected by design — the existing cross-domain + intra-domain dedup passes (Step 4A-Dedup) resolve it using the same logic applied to any cross-origin duplicate. No new dedup logic is required.

**Tier logic**: identical to ELIG/SAF/END/OPS — 10-agent panel, T1 7–10 auto-approved, T2 4–6 user decision, T3 1–3 promotion pipeline. Reuses the existing tier infrastructure.

**Scope boundary vs. OPS**: if a rule is purely about *how* a procedure is performed (technique, equipment, position), that's OPS — not SOA-text. SOA-text only captures rules about *when/where/how-often* procedures occur across visits, and cross-visit coordination. Per-visit technique details remain in OPS.

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

### Phase 3 — Validate (orphan scan + completeness + heuristics + full accuracy judging + consistency + mandatory full verbatim verification)

**Step 3.5 — Protocol-Wide Orphan Scan (MANDATORY BLOCKING GATE, runs FIRST in Phase 3)**: Scan the ENTIRE protocol — section-by-section (primary) and page-by-page for any page not claimed by the section map (secondary sweep) — to find rule-like statements, obligations, thresholds, prohibitions, requirements, schedules, procedures, criteria, timings, or methods that were NOT captured by any domain extractor in Phase 2. Uses a **6-agent panel (3 Claude + 3 Gemini)** with high-recall candidate detection and consensus-based promotion. Promoted orphan KRIs are appended to the corresponding `raw_{DOMAIN}.json` file (one of the 5 real domains: SOA/ELIG/SAF/END/OPS) so they flow through the rest of Phase 3 validation like any other KRI. Orphans that appear non-definable are still appended to their parent domain — the NDEF Sweep (Step 4A-NDEF) handles reclassification post-assembly, not the orphan scan. **The pipeline cannot advance to Step 3A until the orphan scan is complete and all user decisions are made.** See full spec below.

**Step 3A — Completeness**: Every Camelot CSV cell with "X" must have a KRI.

**Step 3A+ — Clinical Heuristics**: 10 protocol-agnostic heuristics:
- H1-H7: Drug accountability at EOS, pre-questionnaire procedures, ICF at first contact, AE from first dose, concomitant meds at all visits, screening symmetry, vital signs dual measurement.
- **H8 — Edge-Column Footnote Reconciliation**: For procedures in the first/last column, cross-check against footnotes. If a footnote says "at EDC/EOS" but ontology shows V0 (or vice versa), correct it.
- **H9 — Epoch Boundary Plausibility Check**: If a procedure has marks in treatment epoch (V5-V20) but also a single isolated mark in screening (V0/V1), flag it for review. Single marks in a distant epoch are suspicious.
- **H10 — Contiguous Coverage Gap Detection**: For procedures with 5+ visits, check for suspicious holes (>15% gap ratio). Re-verify gaps against the Camelot CSV. Use `detect_contiguous_gaps()` from `scripts/vision_table_extractor.py`.

**Step 3B — Full KRI Accuracy Judging (MANDATORY BLOCKING GATE, 100% coverage, multi-judge panel)**: Every single KRI (100% of the extracted set across all domains, including orphan KRIs promoted in Step 3.5) is verified by a **5-judge cross-model panel**: 3 Claude Sonnet judges + 2 Gemini 2.5 Pro judges. Each judge independently verifies five checks — Faithfulness (C1), Specific Values (C2), Reference Accuracy (C3), Completeness (C4), and Scope Accuracy (C5) — against the full text of the cited page(s) ±1 page of context. Consensus adjudication determines the final verdict; any FAIL is blocking; FLAGs escalate to user decision; IMPRECISE KRIs are auto-corrected only when ≥3 judges agree on the correction, then re-verified. **The pipeline cannot advance to Step 3C until Step 3B emits a pass report with 0 FAIL and 0 unresolved FLAG.** This step checks whether the **content** of rules is clinically accurate — it does NOT substitute for Step 3D quote verification. **This step replaces the prior 20-KRI sampling approach** — sampling is no longer permitted under any circumstances. See full spec below.

**Step 3C — Consistency**: Same procedure across visits must have consistent details.

**Step 3D — Full Verbatim Verification (MANDATORY BLOCKING GATE)**: Run `scripts/step3d_verify.py` against the PDF to verify every single KRI's `supporting_quote` is a verbatim substring of the cited page text. **The pipeline cannot advance to Step 4A until this step reports 100% pass.** A `supporting_quote` that cannot be found verbatim in the cited page is a **fabricated quote** — a hard pipeline failure. Not a warning, not a soft flag. The pipeline stops immediately. The KRI must be corrected before proceeding. No exceptions. See details below.

### Phase 4 — Assemble + Compare
**Step 4A — Assembly**: Run `scripts/step4a_assemble.py` to merge all category files → `extracted_kris.json` + `Extracted_KRIs.xlsx`. The Excel workbook has one sheet per domain (SOA, ELIG, SAF, END, OPS, NDEF) plus a Summary sheet. **Exact column structure — no deviations:**

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

**Post-Assembly passes (MANDATORY, in this order, before the Final summary):**
1. **Step 4A-Dedup** — run the dedup pass (see "CRITICAL — De-duplication" above).
2. **Step 4A-NDEF** — run the **NDEF Sweep** (`scripts/step4a_ndef_sweep.py`). This reviews every KRI across the 5 real domains and MOVES any whose rule is not deterministically machine-checkable into NDEF. See "CRITICAL — NDEF Sweep" below for the full spec.

Both passes operate on the assembled output (`extracted_kris.json` + the `raw_{DOMAIN}.json` files) and rewrite them in place. NDEF Sweep creates `raw_NDEF.json` if it doesn't already exist.

**Final summary (mandatory)**: At the end of every completed run — after both post-assembly passes — print and log a domain-by-domain KRI count: total per domain (SOA, ELIG, SAF, END, OPS, NDEF) and grand total. Confirm the assembled `extracted_kris.json` is the approved Golden Set for this protocol.

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

After Phase 2's domain extractors have run, the extracted KRI set reflects what the SOA / ELIG / SAF / END / OPS extractors each found within their own domain focus. But real protocols contain rule-like content that can fall between domain prompts — content in appendices, boxed notes, un-numbered sections, text that crosses domain boundaries, or content phrased in a way that no single domain extractor's prompt keyed on. Step 3.5 is the safety net that catches every such rule before dedup runs.

This step is the **protocol-wide orphan scan**. It is distinct from (and additional to) the Step 1C footnote-level orphan validation inside `footnote_map.json`. Both orphan mechanisms run, both are mandatory, and neither replaces the other.

### Input

- Full protocol PDF
- `manifest.json` (section map)
- All `raw_{DOMAIN}.json` files (SOA, ELIG, SAF, END, OPS, NDEF)

### Architecture — 6-agent panel (3 Claude + 3 Gemini)

Cross-model, same principle as Phase 2 extraction:

| Agents | Model |
|---|---|
| A_C1, A_C2, A_C3 | Claude Sonnet 4 |
| A_G1, A_G2, A_G3 | Gemini 2.5 Pro |

Orphan scanning is a **recall problem** — the cost of missing an orphan is higher than the cost of flagging a non-orphan. Therefore the candidate-detection stage is high-recall (any agent flagging something makes it a candidate), and the promotion stage is consensus-based.

### Phase 1 — Primary section sweep (section-by-section)

For each section in `manifest.json` (across all 5 domains in the section map):

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

1. Classify into SOA / ELIG / SAF / END / OPS using the Domain Boundary Rules (SKILL.md Rules 1–3). NDEF is out of scope here — reclassification to NDEF happens later in the NDEF Sweep (Step 4A-NDEF).
2. Generate a full KRI record:
   - `kri_id`: prefixed `ORPH-{DOMAIN}-{NNN}` so orphan KRIs are identifiable in downstream audits
   - `kri_name`: short name derived from the candidate text
   - `description`: one-sentence description of what this KRI monitors
   - `rule_for_llm`: atomic rule text following all atomicity and faithfulness rules
   - `protocol_reference`: section label + page number (or `Schedule of Activities` for SoA-derived orphans)
   - `supporting_quote`: verbatim ≤30 words from the source page (no outer quotes)
   - `combined_ref`: computed as `f'{protocol_reference} — "{supporting_quote}"'`
   - `additional_footnotes`: if applicable, from `footnote_map.json`
   - `severity`: critical / major / minor per the standard severity rules
3. Append the orphan KRI to the corresponding `raw_{DOMAIN}.json` file so it flows through the rest of Phase 3 (Step 3A completeness, Step 3A+ heuristics, Step 3B full accuracy judging, Step 3C consistency, Step 3D verbatim verification) exactly like a Phase 2 KRI.

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
    "by_domain": {"SOA": 3, "ELIG": 1, "SAF": 16, "END": 2, "OPS": 5, "NDEF": 1}
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
- For SOA KRIs with a footnote reference: the full footnote text from `footnote_map.json`

### The 5 checks (C1–C5) each judge runs independently

| Check | What it verifies |
|---|---|
| **C1 — Faithfulness** | Does `rule_for_llm` say what the protocol says, nothing more and nothing less? No additions, no omissions, no softening, no generalization |
| **C2 — Specific values** | Every concrete value in the rule (threshold, drug name, dose, timing window, analyte, visit number, day count, percentage, unit) matches the protocol exactly |
| **C3 — Reference accuracy** | The cited `protocol_reference` (section + page) is actually ABOUT the clinical topic of this KRI. This is NOT a substring check — it is a semantic check. If the KRI is about "LDL-C percent change at Week 14" but the cited page is about infusion reactions, C3 FAILS even if the quote happens to appear on that page. |
| **C4 — Completeness** | No critical detail the protocol specifies for this rule is missing. If the protocol says "measure in sitting position with arm supported after 5 minutes of rest" and the KRI says "measure in sitting position", C4 returns IMPRECISE with the missing detail identified |
| **C5 — Scope accuracy** | Visit scope, population scope, time-point scope all match protocol intent. If the KRI says "at V3" but the protocol specifies "at V3 and V5", C5 FAILS |

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
- **CORRECT** — all 5 checks pass
- **IMPRECISE** — right intent, all checks semantically pass, but C2 or C4 flagged a missing detail (e.g., missing CRP from a lab list, missing "supine" from vitals positioning). Auto-correctable.
- **WRONG** — any of C1, C3, or C5 failed, OR C2/C4 failed with incorrect values (not just missing). Blocking.

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
- **Parallelize across domains**: SOA / ELIG / SAF / END / OPS / NDEF judged in parallel (6 workers)
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
| **Method** | 5-judge cross-model panel, semantic check of 5 dimensions (C1–C5) | Deterministic pdfplumber substring match |
| **Catches** | Wrong thresholds, wrong visit scope, wrong page topic, missing details, misinterpretation | Fabricated quotes, wrong page numbers, typos that break exact match |
| **Blocking gate** | Yes — before 3C | Yes — before 4A |

The combination of 3B C2+C3 + 3D gives full protection against wrong page citations: 3D catches text fabrication, 3B C3 catches "the quote exists on the page but the page is about a different topic", 3B C2 catches wrong specific values. Nothing escapes.

---

## Output artifacts

Each pipeline run produces these files in the output directory:

| File | Description | Source |
|------|-------------|--------|
| `manifest.json` | Protocol metadata and section map | Step 1A |
| `soa_table.csv` | **Canonical SoA matrix** (Camelot) | Step 1B-Camelot |
| `soa_table.json` | SoA matrix + visit-procedure mapping (Camelot) | Step 1B-Camelot |
| `ontology.json` | SoA ontology (visits, procedures, footnotes) | Step 1B |
| `footnote_map.json` | **Deterministic footnote-to-cell mapping** (single source of truth) | Step 1C |
| `raw_SOA.json` | SOA KRIs (check-in + procedure + cross-visit) | Step 2 |
| `raw_ELIG.json` | Eligibility KRIs | Step 2 |
| `raw_SAF.json` | Safety KRIs | Step 2 |
| `raw_END.json` | Endpoint KRIs | Step 2 |
| `raw_OPS.json` | Operations KRIs | Step 2 |
| `raw_NDEF.json` | Non-Definable KRIs (populated by the NDEF Sweep; KRIs moved out of the 5 real domains) | **Step 4A-NDEF** |
| `orphan_scan_report.json` | **Protocol-wide orphan scan results (primary section sweep + secondary page sweep + consolidation + cross-check + classification + user decisions + promoted orphan KRIs)** | **Step 3.5** |
| `extracted_kris.json` | All KRIs assembled (includes promoted orphan KRIs from Step 3.5) | Step 4A |
| `Extracted_KRIs.xlsx` | Excel workbook (6 domain sheets + Summary) | Step 4A |
| `gaps_report.json` | Completeness + heuristic results | Step 3A/3A+ |
| `accuracy_report_full.json` | **100% KRI accuracy judging — 5-judge cross-model panel verdicts, consensus results, auto-corrections, user decisions, blocking gate status** | **Step 3B** |
| `consistency_report.json` | Procedure family consistency | Step 3C |
| `verify_report.json` | Full verbatim verification results | Step 3D |
| `dedup_report.json` | **Dedup results — cross-domain + intra-domain deletions + `kept_despite_similarity` audit trail** | **Step 4A-Dedup** |
| `comparison_report.json` | Golden set comparison (if provided) | Step 4C |

---

## Quality rules (apply to every KRI)

1. **Faithfulness**: Use exact drug names, doses, thresholds, timing windows from the protocol. Never generalize ("emergency treatment" → name the drugs).
2. **Data source**: Washout KRIs must say "by checking medication logs and visit timestamps".
3. **Lab panels**: Include all analytes from the protocol footnote — never just "biochemistry panel".
4. **Vitals position**: Use the exact position wording the protocol uses (e.g. "supine position").
5. **Visit prefix**: Every SOA `rule_for_llm` starts with visit code: `V1-`, `S2-`, `All visits-`.
6. **Analysis sets**: Use the protocol's exact definition — ITT ≠ mITT ≠ FAS.
7. **No hallucination**: Every KRI must cite a real section + page. If unsure, omit.
8. **Measurement detail**: Physical assessments must include units, positioning, and preparation when the protocol specifies them (e.g. "weight in kilograms, shoes removed").
9. **Visit window check-in KRI (MANDATORY)**: Every single visit in the SoA table MUST have a dedicated "check-in / within-window" KRI as its FIRST KRI. This includes all screening visits, treatment visits, follow-up visits, and unscheduled visits. The KRI verifies the visit occurred AND fell within the protocol-specified timing window (day reference ± tolerance). Never skip any visit.
10. **Table is truth**: The SoA table (via Camelot CSV) is the single source of truth for which procedures occur at which visits. Footnotes can ADD context (enrichment) but cannot OVERRIDE the table's X marks. If a footnote says "annually" but the table shows X at V10/V13/V16/V19, use the table's visits, not the footnote's interpretation.
11. **No outer quotes in supporting_quote**: The `supporting_quote` field must never begin or end with a `"` character. The `combined_ref` field adds its own surrounding quotes.
12. **No duplicate page numbers**: Never produce `"p.27, p.27"` or `"Page 27, p.27"`. Exactly one page reference per KRI.
13. **No footnote number prefix in quotes**: Raw PDF has `"13 Urinalysis..."` — the `13` is a label, not content. Strip it. Quote starts with the text: `"Urinalysis: Dipstick..."`.
14. **Script safety — always save**: Every script that modifies JSON must: (a) create a backup, (b) `json.dump(..., ensure_ascii=False)`, (c) print confirmation with record count.
15. **Footnote associations are deterministic**: They come from `footnote_map.json` (Step 1C), NEVER from LLM inference. If the map says Vital Signs = Footnote 4, the KRI cites Footnote 4. Period.
16. **Quote anchoring — one obligation per quote**: The `supporting_quote` must be the **shortest possible verbatim segment** from the protocol that anchors exactly ONE verifiable obligation. Never bundle multiple independent obligations into a single `supporting_quote`. If a sentence contains two independently verifiable rules (e.g., a dose definition AND a reporting timeline), split them into two KRIs with separate quotes. A quote that covers multiple obligations will be flagged during Step 3B accuracy judging for atomicity split. Long quotes (>200 characters) covering multiple clauses are automatically suspect — trim to the clause(s) that matter for this specific KRI's check.
17. **Discard traceability — empty reason is a pipeline error**: Every discarded KRI (at any stage: Tier 3 pipeline, de-duplication, domain validation) MUST have a non-empty `reason` field in its discard record. The reason must either: (a) name the covering KRI ID (e.g., "Covered by SAF-AE-004 — same obligation, same section"), OR (b) clearly explain why the cited text does not constitute a valid, atomically verifiable obligation. An empty, null, or placeholder reason (e.g., "N/A", "see above") is a pipeline error that blocks the run. The Compliance Monitor must verify that all discard records across all artifacts (`{domain}_tier3_filtered.json`, `dedup_report.json`, validation logs) have non-empty reasons before allowing Phase 4 assembly.
18. **Definitional rules are KRIs**: Protocol sentences that define inclusion/exclusion boundaries for clinical concepts are valid KRIs. A sentence of the form "X is defined as...", "X does not include Y when...", or "X is not considered Y unless..." encodes a verifiable rule — a site can deviate by applying the wrong definition. Extract one KRI per definitional sentence. Domain assignment: SAF for adverse event/safety definitions; OPS for operational definitions; ELIG for eligibility criteria definitions. Do NOT skip definitional rules on the assumption that they are "just context" — they are independently verifiable and sites do misapply them.
19. **`rule_for_llm` must be binary and machine-readable (non-NDEF KRIs only)**: For all KRIs that are NOT classified as NDEF, the `rule_for_llm` field must be binary, unambiguous, and machine-readable — written as a precise, checkable instruction for an LLM system. It must specify exactly WHAT to check, WHEN to check it, HOW to verify compliance, and in relation to WHAT protocol requirement. It must produce a clear YES/NO answer when applied to a data record. It must NOT be narrative prose, a paraphrase of the protocol, or a vague description of intent. Examples of violations: "Ensure the procedure was performed correctly" (not binary), "Check the endpoint definition" (not specific), "The study drug was administered" (not an instruction). NDEF KRIs are explicitly excluded from this requirement — by definition, NDEF rules cannot be expressed as a binary verifiable instruction (that is why they are NDEF), and their `rule_for_llm` instead uses the fixed format: `"NDEF — Non-verifiable: [reason why LLM cannot verify]"`.

### SOA Domain — Reference and Quote Rules (MANDATORY, NO EXCEPTIONS)

The SOA domain has strict rules because it must be 100% deterministic:

**A. Three types of SOA KRIs and their reference format:**

| Type | Reference format | `supporting_quote` source |
|------|-----------------|--------------------------|
| Table procedure WITH footnote | `Schedule of Activities, Footnote N, p.X-p.Y` | Verbatim excerpt from Footnote N's text (from `footnote_map.json`) |
| Table procedure WITHOUT footnote | `Schedule of Activities, p.X-p.Y` | Text from the SoA table page itself (procedure name or visit label) |
| Non-table KRI (from body text) | `Section N.N, p.Z` | Verbatim text from the cited protocol section |

Where `p.X-p.Y` is the full page range covering the SoA table AND all its footnote pages (e.g., `p.24-p.29`).

**B. What goes WRONG if these rules are violated (never do these):**
- Do NOT fabricate a "Section X.X" for the SoA table if it has no section number in the protocol
- Do NOT cite individual footnote pages (e.g., `p.27`) — always use the full range (`p.24-p.29`)
- Do NOT put a quote from one footnote when the reference says a different footnote number
- Do NOT include the footnote number inside the quote text (e.g., `"13 Urinalysis..."` → wrong; `"Urinalysis..."` → correct)
- Do NOT use quotes from protocol amendment pages (p.1-10), body text pages, or any page outside the SoA table range for table-derived KRIs
- Do NOT omit the Footnote number from the reference when the procedure has one in the deterministic map

**C. The `supporting_quote` for a footnoted SOA KRI is an excerpt from the footnote text in `footnote_map.json`.** It must be a verbatim substring of that footnote's text, verified by pdfplumber on the SoA footnote pages. It must NOT come from any other source.

**D. Topic-specific quotes for multi-topic footnotes (CRITICAL):**
Some footnotes are long and cover multiple distinct topics (e.g., Footnote 1 in SPIRE covers fasting, informed consent, pre-screening, visit scheduling, dosing windows, lipid testing rules — all in one footnote). When a KRI is about ONE specific topic within a multi-topic footnote:
- The `supporting_quote` MUST quote the **specific sentence(s) about that KRI's topic**, NOT the first 25 words of the footnote
- Example: KRI "IP After Blood Draws" must quote "subjects should self-inject IP only after blood samples have been collected" — NOT the fasting sentence that starts the footnote
- If a KRI's topic comes from a DIFFERENT footnote than its procedure's default, cite the correct footnote (e.g., "IP After Blood Draws" is in Footnote 20, not Footnote 1, even though the IP dispensing procedure maps to Footnote 20)
- NEVER give all KRIs under the same footnote the same generic excerpt. Each KRI quotes the part relevant to its specific check.

**Single-topic vs. multi-topic threshold**: A footnote is single-topic if it covers only one verifiable obligation or applies to only one procedure/visit combination — copy the ENTIRE footnote verbatim into every KRI it applies to. A footnote is multi-topic if it contains separate information for multiple procedures, visits, or obligations — each KRI receives ONLY the specific sentence(s) relevant to its particular procedure/visit. Never copy an entire multi-topic footnote into a KRI that only relates to part of it.

**E. Visit scope accuracy (MANDATORY)**: Cross-protocol SOA rules that apply to only some visits must NEVER be labeled 'all visits.' The `kri_name`, `description`, and `rule_for_llm` must accurately reflect the exact visits the rule covers. If a footnote or cross-visit rule applies only to V1, V3, and V5, the KRI must name those visits explicitly — not use 'all visits' as a shorthand.

---

## Comparing against a golden set

After Step 4A assembly completes, **always ask the user**:
> "Do you have a golden set to compare against? You can provide a file path or upload it."

If the user provides a golden set, run Step 4C (see `references/steps.md` for full details).

### How comparison works

**Phase 1 — Matching**: For each category (SOA, ELIG, SAF, END, OPS, NDEF) separately, match extracted KRIs to golden KRIs using semantic similarity (not just ID matching). Handle 1:many and many:1 splits.

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

**Scope**: The multi-turn method is used for Phase 2 domain extraction of ELIG, SAF, END, OPS, and **SOA-text** (the new text-only SOA layer — see "SOA-text Phase 2 extraction" below). The Phase 1 SOA deterministic process (Camelot + footnote mapping + Phase-1 step-5 cross-visit rules) is **unchanged** — it still produces the authoritative procedure × visit grid and cell-level KRIs. SOA-text runs as an additive layer that captures narrative / cross-visit / protocol-wide SOA rules the table process does not produce. Claude sub-agents are unchanged (they already iterate via the Agent tool).

**Backward compatibility**: The original `run_gemini_extraction()` (single-shot, text prompt, no PDF) is kept for other uses — e.g., Step 3B accuracy judging, Step 3.5 orphan scan — where single-shot is appropriate.

**Adjudication — consensus-based, per domain:**

| Agent consensus | Action |
|---|---|
| **7–10 agents** found it | Auto-approve into golden set |
| **4–6 agents** found it | Verify against protocol, then present decision table to user. User approves/rejects each. |
| **1–3 agents** found it | Auto-delete |

Decision table shown to user for 4–6 tier KRIs includes: KRI ID, KRI Name, agent count with breakdown (e.g., "5/10 (3C + 2G)"), verified status, reference & quote, and a decision column.

**Process is sequential per domain**: SOA → ELIG → SAF → END → OPS. Each domain completes its 10-agent extraction → merge → consensus tiers → Step 2.5 Section Obligation Inventory → Step 2.6 auto-judgment (handles T2 + T3-promoted, produces the decision table) → de-duplication BEFORE the next domain begins. In `--auto-approve-unanimous` mode (default), Step 2.6 completes without blocking; flagged items default to rejected and surface at end-of-run in Step 4A-FlaggedReview.

---

### Tier 3 Promotion Pipeline (ADDITIVE — replaces silent auto-delete, extended 3→5 steps)

KRIs found by only 1–3 agents (Tier 3) are NOT silently discarded. They enter a 5-step promotion pipeline that terminates in Step 2.6 auto-judgment (same 6-judge panel that handles T2). The rule "every discarded KRI must have a non-empty `reason`" (Rule 17) applies to every step.

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
- **Step 4A-NDEF** sweep reclassifies **non-definable KRIs** into NDEF — 6-judge panel, post-assembly. Different purpose.

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
- Flagged items are preserved verbatim in each domain's `{domain}_manual_review_decisions.json.sections.flagged_for_review` AND surfaced together in the end-of-run consolidated **Step 4A-FlaggedReview** table (`flagged_review_decisions.json`) so the user reviews all 5 domains' flagged items in one pass.
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

**Rule 17 compliance**: every auto-rejected KRI has a non-empty `reason` identifying the specific layer that rejected it.

---

### Step 4A-FlaggedReview — End-of-Run Cross-Domain Flagged Review (runs after Step 4A-NDEF)

Collects every flagged KRI from all 5 domains' Step 2.6 autojudgment outputs and produces a single consolidated table (`flagged_review_decisions.json`) with FULL KRI columns so the user can scan all flagged items in one pass, not per-domain.

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
  --skill-path ~/.claude/skills-repo/protocol-kri-extractor/SKILL.md
```

This copies all artifacts (extracted_kris.json, Extracted_KRIs.xlsx, raw domain files, manifest, ontology, footnote map, verification reports, etc.) into `~/Documents/kri-regression-vault/<protocol_id>/` alongside a snapshot of the current SKILL.md.

**If the user says no**, move on. The golden set remains in its run directory but is not vault-protected.

**At the start of any session where this skill will be edited**, run the regression test first to establish a clean baseline. Use the `kri-regression-tester` skill for this.

---

## Reference files

- `references/steps.md` — detailed LLM prompt templates for each step
- `references/kri_examples.md` — annotated KRI examples per category
- `scripts/camelot_table_extractor.py` — Camelot-based table extraction (PRIMARY for SoA)
- `scripts/vision_table_extractor.py` — Vision-based extraction + multi-pass + Heuristic 10
- `scripts/gemini_extract.py` — Gemini API extraction agents (multi-model competition)
- `scripts/step3_5_orphan_scan.py` — Protocol-wide orphan scan (6-agent panel, section + page sweeps, blocking gate)
- `scripts/step3b_accuracy.py` — Full KRI accuracy judging at 100% coverage (5-judge cross-model panel, blocking gate)
- `scripts/step3d_verify.py` — Full verbatim pdfplumber verification (blocking gate)
- `scripts/step4a_assemble.py` — Assembly + Excel generation (no LLM needed)
