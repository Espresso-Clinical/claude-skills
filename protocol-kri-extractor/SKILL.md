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

### Target audience (foundational principle)

The extracted KRIs serve **operational and clinical trial professionals only**: sponsor ClinOps, CRAs, CROs, and CRCs. Every KRI must be something these roles would need to verify during site monitoring, subject management, or trial oversight. **Do NOT extract** rules meant purely for biostatisticians, data scientists, or regulatory statisticians (e.g., statistical model specifications, alpha spending, sample size calculations). If a rule is not actionable by a CRA/CRC/ClinOps professional, it does not belong in the KRI set.

### Verifiability requirement (foundational principle)

Every KRI must be **binary-verifiable by a system** — a clear YES/NO check with unambiguous, measurable criteria. Rules that depend on subjective human judgment ("clinically significant", "if appropriate", "per local regulations"), vague time expressions without numeric thresholds ("promptly", "reasonable time"), or effort-based language ("efforts were made") are **not verifiable** and must be separated into the NDEF (Non-Defined) domain. See Quality Rule 16 for the full detection criteria.

## Output schema

Every extracted KRI matches this structure:
```json
{
  "kri_id": "SOA-V1-001",
  "kri_name": "V1 (Screening) — Vital Signs",
  "description": "What this KRI monitors and why it matters. For check-in KRIs: MUST state the protocol-specified visit window verbatim (e.g. 'Week 14 ± 3 days').",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V1- Verify that [specific actionable check with exact values, data source, timepoint, and binary condition]. See rule_for_llm writing guide below.",
  "protocol_reference": "Section X.X, Page N: \"verbatim quote ≤30 words\". Multiple sources allowed — see multi-reference rule below.",
  "supporting_quote": "Verbatim quote from protocol — or null.",
  "additional_footnotes": "Footnote N: [verbatim text from protocol] — or null. See footnote rules below.",
  "combined_ref": "Pre-built combined column for Excel output. Build rule: SOA table KRIs → 'Table: Schedule of Activities, pages XX-XX — Footnote N: \"text\"'. All other KRIs → 'Section X.X, p.XX — \"verbatim quote\"'. See Protocol Reference & Quote column rules in Step 11. Built during final assembly — not during extraction.",
  "domain": "SOA",
  "non_verifiable_reason": "Only present for NDEF KRIs. Explains why the rule is non-verifiable, quoting the problematic phrase from rule_for_llm. — or omitted for all other domains."
}
```

### rule_for_llm writing guide (mandatory)

`rule_for_llm` is a **system instruction for an LLM agent** — not a human-readable summary. The agent will read this field and decide whether a subject is compliant or non-compliant. Write it as a precise, executable binary check.

Every `rule_for_llm` must answer all four of these questions:

1. **WHAT** — What specific data item, field, or fact must be checked?
   *(e.g., "LDL-C value from screening labs", "IMP administration date in eCRF", "SAE report submission timestamp")*

2. **WHERE / FROM WHAT SOURCE** — In which record or system is this data found?
   *(e.g., "in the subject's medication history", "in the eCRF visit date field", "in the lab report", "in the IP accountability log")*

3. **WHEN** — At what timepoint, visit, or relative to what event?
   *(e.g., "at Screening Visit", "within 24 hours of the event", "prior to first IMP dose", "at Visit 8 (Week 14)")*

4. **WHAT CONDITION makes it PASS (YES) or FAIL (NO)** — The binary decision rule, expressed with exact thresholds, comparators, or relationships.
   *(e.g., "is ≥ 70 mg/dL", "falls within ±3 days of the target date", "is absent from medical history", "was completed before IMP administration", "is documented as performed")*

**Examples of correct vs. incorrect `rule_for_llm`**:

| ❌ Too vague | ✅ Correct |
|---|---|
| `"V1 — Verify IMP was administered correctly"` | `"V1 — Verify that the IMP injection date/time (eCRF IMP administration field) falls within the protocol-specified dosing window: 1 day before to 4 days after the target visit date. YES if within window, NO if outside."` |
| `"Verify subject met eligibility"` | `"ELIG-INC — Verify that the subject's LDL-C value documented in the screening lab report is ≥ 70 mg/dL. Timepoint: Screening. Source: lab report. YES if ≥ 70 mg/dL, NO if < 70 mg/dL or missing."` |
| `"SAE must be reported promptly"` | `"SAF-AE — Verify that each SAE was reported to the sponsor within 24 hours of the investigator's first documented awareness. Source: SAE report submission timestamp vs. investigator awareness date in eCRF. YES if ≤ 24h, NO if > 24h."` |
| `"Verify fasting was observed"` | `"SOA-CROSS — Verify that the subject fasted for ≥ 10 hours before blood draw visits (V1, V2, V3, V5, V7, V9) as documented in the eCRF fasting field. Exceptions: CK, LFTs, and pregnancy tests do not require fasting. YES if fasting ≥ 10h documented or procedure is an excepted type, NO if fasting < 10h or field is empty for a required visit."` |

**Do NOT write** `rule_for_llm` as a plain English description of the KRI. It must read as an instruction the system can act on.

### Footnote rules (mandatory)

**Rule F1 — Always verbatim**: `additional_footnotes` must always be copied word-for-word exactly as written in the protocol. No paraphrasing, no summarizing, no rewording. Copy typos, punctuation, and formatting exactly.

**Rule F2 — Short footnotes: copy in full**: If the footnote is of reasonable length and covers one topic, copy the entire footnote verbatim.

**Rule F3 — Long/multi-topic footnotes: extract only the relevant passage**: If a footnote is long and covers multiple unrelated topics (e.g., visit windows, informed consent, fasting rules, and dosing windows all in one footnote), identify the sentence(s) or clause(s) directly relevant to THIS specific KRI's procedure × visit and quote only those — verbatim. If the relevant content is mid-sentence within a longer sentence that also covers irrelevant material, quote the full sentence. Never truncate mid-sentence.

**Rule F4 — Footnote location**: Footnotes can appear anywhere in the SoA section:
- As superscripts in the procedure name column (most common)
- As superscripts on the X marks within cells (e.g. "X¹⁰")
- In the visit column header row
- In a separate footnote legend below the table
All are equally valid. A KRI inherits the footnotes from its procedure row AND from its specific cell (if the X mark itself carries a superscript).

**Rule F5 — Check-in KRI window in description**: Every check-in KRI `description` field MUST state the protocol-specified timing window for that visit. If the window is defined in the table itself, use that. If defined in a footnote, extract the exact relevant sentence from that footnote and state it clearly in the description. Example: *"Verifies that Visit 8 (Week 14) occurred within the allowed window of ±3 days. Protocol: 'Visits 8 (the Week 14 visit), 11 (the Week 52 visit), both which will have visit window of ±3 days'."*

Six categories (universal across all trials — from ICH GCP, not protocol-specific):
- **SOA** — Schedule of Activities
- **ELIG** — Eligibility (inclusion + exclusion)
- **SAF** — Safety & Toxicity
- **END** — Endpoints & Statistics
- **OPS** — Operations & Compliance
- **NDEF** — Non-Defined KRIs (non-verifiable rules)

---

## How to run

### Step 0 — Setup (first time only)
```bash
pip install pdfplumber pymupdf camelot-py[cv] opencv-python-headless openpyxl --break-system-packages -q
```

### Input required
- Protocol PDF file path
- Output directory (will be created)
- Optional: golden set JSON path (for final comparison)

---

## Pipeline overview

The full pipeline runs in **5 phases**, executed sequentially. Each phase must be fully completed before the next begins. The user directs each phase transition.

| Phase | Name | Steps |
|---|---|---|
| Phase 1 | Domain Extraction | Steps 1–2 |
| Phase 2 | Cross-Domain Deduplication | Steps 3–4 |
| Phase 3 | Orphan Sweep (Gap Analysis) | Steps 5–6 |
| Phase 4 | Undefined KRI Isolation | Steps 7–8 |
| Phase 5 | Final Golden Set Audit & Traceability | Steps 9–11 |

---

## Step-by-step

### Phase 1 — Domain Extraction

#### Pre-Step — Discover

Before any domain extraction begins, run the discovery sub-pipeline:

**Step 1A — Manifest**: Read cover pages + TOC. Map every section to SOA/ELIG/SAF/END/OPS.

**Step 1B-Camelot — Table Extraction (PRIMARY)**: Use Camelot (lattice mode) via `scripts/camelot_table_extractor.py` to extract the SoA table into `soa_table.csv` and `soa_table.json`. This is the **PRIMARY** source of truth for the SoA procedure × visit grid. Camelot reads table line geometry from the PDF and gives ~99% structural accuracy — deterministic, reproducible, and not affected by LLM variance. Handles multi-page tables automatically. The CSV and JSON outputs become the canonical SoA data for all downstream steps.

**Step 1B-Vision — Vision Fallback (SECONDARY)**: For cells where Camelot detects the lattice structure but the cell content contains footnote superscripts (e.g., "X¹⁰", "X¹³·¹⁴") that Camelot may read as empty, use Claude Vision at 450 DPI as fallback. Also use multi-pass vision (full + left 55% crop + right 55% crop at 450 DPI) with majority voting for wide tables (>12 columns) to recover any cells Camelot missed. Save conflicts in `multipass_conflicts.json`.

**Step 1B-ColDetect — Column Boundary Detection**: After extraction, run `scripts/vision_table_extractor.py` column detection to verify column boundaries match the Camelot-extracted structure. Flag any discrepancies.

**Step 1B — Ontology**: Build the SoA ontology from the Camelot-extracted table data (verified by vision fallback where needed). Run **Footnote Cross-Validation** as a safety net.

---

#### Step 1 — SOA Extraction

Extract the SOA domain using the structured 6-step process anchored on the Camelot table.

**SOA — 6-step structured process**:
1. **Visit mapping**: Pull all visits and their timing from the Camelot CSV. Establish naming conventions (V0, V1, V2... EDC_EOS). From this point forward, use ONLY these canonical names.
2. **Table verification**: Compare the Camelot CSV against the PDF image for verification. Flag any discrepancies. Save `soa_table.csv` and `soa_table.json` as the tracking artifacts.
3. **Check-in KRIs**: For each visit, create ONE check-in KRI verifying the subject attended within the protocol-specified timing window.
4. **Procedure KRIs**: For each visit, create ONE KRI listing ALL procedures required at that visit (in the format: `V1 - procedure name`). Also create one KRI per procedure × visit cell.
5. **Footnote enrichment**: After the table-based KRIs are complete, read all footnotes from the protocol and enrich each KRI with relevant footnote details. Also create **cross-visit rule KRIs** for protocol-wide rules (fasting requirements, dosing windows, 10-day lipid rule, IP administration sequence, missed visit escalation, EDC retention, safety follow-up periods, etc.).
6. **Self-verification**: Cross-check that every X cell in the Camelot CSV has a corresponding KRI. Report: `N/N cells covered = 100%`.

**SOA ordering convention** (mandatory — preserved in final assembly):
The SOA KRI list must be ordered as follows:
1. **Check-in KRIs** — one per visit, in chronological visit order (V0, V1, V2, ... V20, EDC_EOS)
2. **Procedure bundle KRIs** — one per visit, same chronological order
3. **Procedure × Visit KRIs** — grouped **by procedure** (not by visit). Within each procedure group, visits appear in chronological order. The procedure groups follow the row order of the SOA table (e.g., Informed Consent → Contact IRT → Medical History → ... → HCRU Assessment).
4. **Cross-visit / footnote rules** — at the end (SOA-ALL-xxx), for protocol-wide rules not tied to a single procedure × visit cell.

This ordering ensures a CRA can review all visits for one procedure together, rather than jumping between procedures for each visit. The assembly step must preserve this insertion order for SOA (never re-sort SOA KRIs alphabetically by kri_id).

**Validate SOA**: Run Phase 3 validation checks (3A, 3A+, 3B, 3C — see below) on the SOA domain immediately after extraction. Save `raw_SOA.json`.

---

#### Step 2 — Domain-Specific Extraction (ELIG → SAF → END → OPS)

Run this step as a **sequential loop** over the four remaining domains in order: ELIG, SAF, END, OPS. Complete all three sub-steps for one domain before moving to the next. Do not start the next domain until the current domain's Verified Master List has been saved.

For each domain, execute the following three sub-steps:

---

##### Sub-step 2.1 — Parallel Extraction (5 independent agents)

Appoint **5 independent sub-agents** simultaneously. Instruct each one to run the skill's extraction module strictly on the current target domain. Each agent works entirely independently — no coordination, no shared context between agents.

Each agent performs the full **3-pass extraction process**:

- **Pass A — Primary extraction**: Extract KRIs from sections tagged to this domain in the manifest (`section_map`). Apply full atomization rules: each KRI must represent exactly ONE independently verifiable binary condition (a YES/NO check a CRA can perform without needing to verify anything else simultaneously). Compound conditions must be split. **Target audience filter applies during extraction** — do not extract rules that are not actionable by CRAs/CRCs/ClinOps (see Quality Rule 15). For END specifically: skip pure statistical methodology (model specs, alpha calculations, power analyses, imputation methods) and only extract operationally relevant endpoint rules (what to measure, when, how, response criteria, data collection requirements).
- **Pass B — Cross-sectional sweep**: Read the ENTIRE protocol text (all sections, footnotes, appendices). Find any rule, requirement, or statement relevant to this domain that was NOT already captured in Pass A — including rules buried in sections formally belonging to other domains, in method descriptions, in footnotes, or scattered throughout the document. Extract only net-new KRIs.
- **Pass C — Atomic decomposition**: Review the combined Pass A + B KRI list. Identify any remaining KRI whose `rule_for_llm` contains more than one independently verifiable condition. Split each into atomic KRIs. Output the final domain KRI list.

Save each agent's output as `{domain}_agent{N}.json` (e.g., `elig_agent1.json` through `elig_agent5.json`). After all 5 complete, report a summary table: agent number, KRI count.

---

##### Sub-step 2.2 — Consensus Scoring (Frequency Matrix)

The main agent compares all 5 agent outputs and builds a **Frequency Matrix** — a mathematical consensus across agents to identify the most certain KRIs.

**Matching methodology**: Group KRIs across agents that check the same underlying clinical requirement. Two KRIs are the same rule if a CRA would verify the same clinical requirement from the same protocol source — even if named or worded differently. Use normalized name matching plus key-term overlap to group semantically equivalent KRIs. Atomization differences (one agent split a compound rule, another kept it combined) must be resolved: the split version wins if the compound was correctly decomposed.

**Tier classification**:
- **Tier 1 — Ironclad** (4–5 agent votes): Auto-approved. Select the single best version: the agent version with the most complete `description` and `rule_for_llm`. Save the Tier 1 list immediately.
- **Tier 2 — Debatable** (2–3 agent votes): Sent to adjudication. Preserve ALL agent versions for each Tier 2 KRI so judges can compare them.
- **Discard** (1 agent vote only): Dropped as outliers — single-agent findings with insufficient consensus to be trusted.

Save outputs:
- `{domain}_tier1.json` — auto-approved Tier 1 KRIs (best version of each)
- `{domain}_tier2.json` — disputed KRIs with vote count and all agent versions
- `{domain}_discarded.json` — single-vote outliers

Report the counts: Tier 1 (N KRIs), Tier 2 (N KRIs), Discarded (N KRIs).

---

##### Sub-step 2.3 — Adjudication (2 Judge Agents)

Appoint **2 independent "Judge" sub-agents** to adjudicate the Tier 2 KRIs. Each judge receives:
- The full protocol PDF
- The full Tier 2 list (with all agent versions for each disputed KRI)
- The current Tier 1 list (so judges can detect overlap with already-approved KRIs)

**Judge mandate — strict traceability standard**:
Each judge must evaluate every Tier 2 KRI and render a PROMOTE or REJECT verdict with full written justification:

- **PROMOTE**: The judge found a verbatim protocol quote that explicitly supports this KRI as a distinct, verifiable clinical requirement — AND — the rule is not already substantively covered by an existing Tier 1 KRI — AND — the rule belongs to this domain (not better classified in another domain).
  - Justification must include: the exact verbatim quote, section number, and page number.
- **REJECT**: The judge could NOT find a verbatim supporting quote, OR the rule is substantively already covered in Tier 1, OR the rule belongs in a different domain.
  - Justification must state the specific reason: "no verbatim quote found", "already in Tier 1 as [KRI ID]", or "belongs in [OTHER DOMAIN] because [reason]".

**Judges work independently** — no coordination between them.

**Reconciliation (main agent)**:
After both judges complete their verdicts, the main agent reconciles:
- **Both PROMOTE**: KRI is promoted. Use the best agent version (longest `rule_for_llm` with correct domain classification). Add to the Verified Master List.
- **Both REJECT**: KRI is discarded. Log reason.
- **Split verdict (J1=PROMOTE, J2=REJECT or vice versa)**: Apply the **stricter standard** — PROMOTE only if the promoting judge provided a genuine verbatim citation AND the KRI is a truly distinct verifiable rule not already captured in Tier 1. If in doubt, REJECT. Domain misclassification rejections always win (domain trumps content).

**Build Verified Master List**:
Merge promoted Tier 2 KRIs with the Tier 1 list. This is the final domain output.
Save as `raw_{DOMAIN}.json` (e.g., `raw_ELIG.json`).

Report: Tier 1 count + promoted Tier 2 count = total verified KRIs for this domain.

After saving `raw_{DOMAIN}.json`, proceed immediately to the next domain in the loop (ELIG → SAF → END → OPS).

---

### Phase 2 — Cross-Domain Deduplication

Runs after all five domain files (`raw_SOA.json`, `raw_ELIG.json`, `raw_SAF.json`, `raw_END.json`, `raw_OPS.json`) are complete.

#### Step 3 — Master Merge

Provide the 5 finalized domain-specific lists to the main agent. Load all five files into a single working set. This is the pre-deduplication master pool.

#### Step 4 — Three-Agent Sequential Deduplication

Deduplication runs as a **sequential chain of 3 independent sub-agents**, each building on the previous agent's output. This achieves a certainty level of 3 independent verifications.

**Agent 1 (Dedup Round 1)**:
- Receives: the full master pool (all 5 domain lists combined)
- Task: Perform full deduplication:
  - **Within-domain**: For each domain, identify clusters of KRIs that check the same underlying clinical requirement (even if worded differently). Keep the single most complete and specific version. A duplicate means: a CRA would consult the same protocol source and verify the same requirement — not just similar wording.
  - **Cross-domain**: Find KRIs across different domains that check the same underlying clinical requirement. Assign each to the single most appropriate domain and remove it from the other(s). Domain priority when equally appropriate: SOA > ELIG > SAF > END > OPS.
- Output: 5 clean domain lists + `dedup_round1_report.json` (every removal documented: dropped KRI ID, kept KRI ID, reason)

**Agent 2 (Dedup Round 2)**:
- Receives: Agent 1's 5 clean domain lists + Agent 1's dedup report
- Task: Review Agent 1's work. Re-run the full deduplication independently. Identify any duplicates Agent 1 missed AND verify Agent 1 did not incorrectly remove distinct KRIs. Produce a corrected set of 5 domain lists.
- Output: 5 clean domain lists (Agent 2 version) + `dedup_round2_report.json`

**Agent 3 (Dedup Round 3 — Final)**:
- Receives: Agent 2's 5 clean domain lists + both previous dedup reports
- Task: Final independent deduplication pass. Resolve any remaining duplicates and confirm Agent 2's decisions. This agent's output is authoritative.
- Output: 5 final clean domain lists (overwrites `raw_{DOMAIN}.json`) + `dedup_final_report.json`

Save `dedup_report.json` as a consolidated log of all 3 rounds documenting every removal decision.

---

### Phase 3 — Orphan Sweep (Gap Analysis)

Ensures no verifiable protocol rule was missed across all five domains.

#### Step 5 — Parallel Orphan Search (5 agents)

Appoint **5 independent sub-agents** simultaneously to search for missing KRIs.

Each agent receives:
- The full protocol PDF
- The complete deduplicated master list (all 5 domains)

Each agent performs a full orphan search:

**Step E1 — Build coverage index**: Extract every section number referenced in `protocol_reference` fields across all KRIs. Build a set of "covered sections." Compare against ALL sections in the TOC.

**Step E2 — Gap classification**: For each TOC section with zero KRI coverage, read its text and classify:
- `HAS_RULES`: contains at least one verifiable clinical requirement — proceed to orphan extraction
- `NARRATIVE_ONLY`: background, rationale, introductory text — acceptable to have no KRIs
- `REFERENCE_ONLY`: cross-references or appendix headers — skip

**Step E3 — Orphan extraction**: For each `HAS_RULES` uncovered section, run a targeted extraction pass with full protocol context. Explicitly compare against the existing KRI list: "Extract only net-new rules not already covered by any existing KRI." Apply the same quality rules (atomization, verifiability, target audience filter) as in the original extraction.

Each agent saves its orphan findings as `orphans_agent{N}.json`. After all 5 complete, report a summary table: agent number, orphan count found.

#### Step 6 — Orphan Verification & Domain Assignment (2 Judge Agents)

Appoint **2 independent "Judge" sub-agents** to verify the orphan candidates.

Each judge receives:
- All 5 orphan agent outputs combined (the union of all proposed orphans)
- The full protocol PDF
- The complete deduplicated master list (to check against)

Each judge must:
1. For each proposed orphan KRI: find the exact verbatim protocol quote that proves it is a genuine gap (a real rule not already in the master list).
2. CONFIRM only KRIs that: (a) have a verbatim supporting quote, (b) are genuinely absent from the master list (not semantically covered by any existing KRI), and (c) are binary-verifiable by a system.
3. REJECT proposed orphans that are: already covered, not binary-verifiable, or belong to NDEF.

**Reconciliation (main agent)**:
- Keep only orphan KRIs that **both judges confirmed** with verbatim citations. Discard all others.
- For each confirmed orphan, classify it into the domain that best fits among SOA/ELIG/SAF/END/OPS (apply domain definitions strictly).
- Merge confirmed orphans into the corresponding domain `raw_{DOMAIN}.json` files.
- Log all assignments in `orphan_report.json`.

---

### Phase 4 — Undefined KRI Isolation

Runs after the Orphan Sweep is complete and all 5 domain files are finalized.

#### Step 7 — Filter Subjective KRIs (NDEF Detection)

Trigger the skill's Undefined KRI module against the complete updated Master List. Scan ALL KRIs across all 5 operational domains for rules that are NOT binary-verifiable by a system (see Quality Rule 16 for the full detection pattern list).

#### Step 8 — Isolate into NDEF Domain

Each non-verifiable KRI is:
- **Reclassified** (not duplicated) — removed from its original domain and moved to NDEF. The total KRI count does not change — only the domain assignment changes.
- Tagged with `category_id: "NDEF"`, `category_label: "Non-Defined KRIs"`
- Given a `non_verifiable_reason` field quoting the specific problematic phrase from its `rule_for_llm`
- Its original `kri_id` is preserved (not renamed)

The Master List after this step contains **only strictly deterministic, binary-verifiable KRIs** in the 5 operational domains. All subjective, human-decision, or non-binary rules are in NDEF.

Output: `raw_NDEF.json`. The original domain `raw_*.json` files are updated to exclude the reclassified KRIs.

---

### Phase 5 — Final Golden Set Audit & Traceability Matrix

#### Step 9 — Red Team Verification

Appoint a final, independent **"Red Team Auditor"** sub-agent. Provide it with:
- The complete, purely deterministic Master List (all 5 operational domain files, post-NDEF filtering)
- The full protocol PDF

The auditor's mandate: perform a **strict reverse-trace** on every single KRI in the Master List. For each KRI, the auditor must:
1. Locate the exact protocol section and page that proves this KRI is explicitly measurable by the protocol's defined data collection plan.
2. Verify the KRI's `rule_for_llm` accurately reflects what the protocol actually says (no over-specification, no under-specification, no hallucinated thresholds).
3. Verify the KRI is actionable by a CRA/CRC/ClinOps professional (not a biostatistician-only rule).

#### Step 10 — Stress Test

For each KRI the auditor cannot fully verify with a direct protocol citation:
- **Route to NDEF**: If a KRI is not binary-verifiable at site level by a CRA — because it requires sponsor-internal data, specialist medical judgment, adjudication committee output, or has no defined threshold/eCRF field — it is NOT a separate "unmeasurable" category. Reclassify it directly as `NDEF` (same as Phase 4). Do not create a separate UNMEASURABLE bucket.
- **Flag for manual validation**: If it is genuinely uncertain whether a KRI is site-verifiable — partial protocol support exists but requires human expert judgment — flag it as `NEEDS_MANUAL_REVIEW`.
- **Confirm**: If the KRI passes the reverse-trace, mark it `VERIFIED` with the exact quote + section.

There are only **two** outputs from the Stress Test: `VERIFIED` and `NEEDS_MANUAL_REVIEW`. Anything that would previously have been called "unmeasurable" is an NDEF candidate and must be routed through the NDEF reclassification logic.

#### Step 10b — Manual Review Presentation & Removal (MANDATORY)

After the Stress Test, ALWAYS report the audit summary and handle flagged KRIs as follows — even if zero KRIs were flagged.

---

**PART 1 — Audit Summary (always shown)**

Report the following confirmation to the user:

> ✅ **Red Team Audit Complete**
> - **[N] KRIs fully verified ([X]%)** — protocol quote confirmed, binary-verifiable, included in Golden Set.
> - **[N] KRIs flagged NEEDS_MANUAL_REVIEW ([X]%)** — removed from Golden Set pending your review.
> - **Golden Set now contains [VERIFIED count] confirmed KRIs only.**

---

**PART 2 — Immediately remove ALL flagged KRIs from the Golden Set**

Before presenting anything to the user, perform these steps automatically:
1. Remove every `NEEDS_MANUAL_REVIEW` KRI from `golden_set.json`
2. Remove the same KRIs from `extracted_kris.json`
3. Save removed KRIs to `pending_manual_review.json` (so nothing is lost)
4. Do NOT update `Traceability_Matrix.xlsx` or `Extracted_KRIs.xlsx` yet — those are updated after the user reviews

The Golden Set must contain **only `VERIFIED` KRIs** before it is shown to the user.

---

**PART 3 — Present flagged KRIs for manual review (single table)**

If any KRIs were flagged as `NEEDS_MANUAL_REVIEW`, present them to the user in this exact format:

**🟡 NEEDS MANUAL REVIEW — [N] KRIs**
*Partial protocol support exists, but expert judgment is required to confirm binary verifiability at site level, domain assignment, or whether the rule belongs in NDEF.*

| # | KRI ID | Domain | Description | What Needs Your Verification | Protocol Page | Direct Protocol Quote | Your Decision |
|---|---|---|---|---|---|---|---|
| 1 | ... | ... | Full description | Specific question for reviewer | **p.XX** (mandatory) | **"Exact verbatim text from protocol"** (mandatory) | ☐ Confirm / ☐ Revise / ☐ Remove / ☐ Move to NDEF |

**Rules for this table:**
- `Protocol Page` must always be a specific page number — never a section number alone.
- `Direct Protocol Quote` must be the exact verbatim text from the protocol that is the basis of the KRI — never paraphrased.
- If either field cannot be filled, the KRI should be classified as NDEF (no protocol basis = not a valid KRI).

---

**PART 4 — Review loop**

After presenting the table, wait for the user to review. Accept batch decisions or one by one. For each user decision:
- **Confirm** → add back to `golden_set.json` and `extracted_kris.json` as `VERIFIED`, add to appropriate `raw_*.json`
- **Revise** → user provides corrected description → add back with updated description as `VERIFIED`
- **Remove** → permanently drop from all files
- **Move to NDEF** → add to `raw_NDEF.json` with NDEF classification, add to `golden_set.json` and `extracted_kris.json` with domain=NDEF

After ALL decisions are collected, update `Traceability_Matrix.xlsx` and `Extracted_KRIs.xlsx` to reflect the final state.

#### Step 11 — Golden Table Generation

Output the absolute final **"Golden Set"** as:

1. **`golden_set.json`** — the fully verified Master List containing **only `VERIFIED` KRIs**. All `NEEDS_MANUAL_REVIEW` items must have been resolved (via user review in Step 10b) before this file is considered final. There is no UNMEASURABLE category — anything non-verifiable goes to NDEF.

2. **`Traceability_Matrix.xlsx`** — one sheet ("Traceability Matrix"), one row per KRI, sorted SOA→ELIG→SAF→END→OPS→NDEF then by kri_id within domain. **Mandatory 6 columns — never omit, never add extras (no Audit Status column, no Notes column):**

| Column | Source field | Rules |
|---|---|---|
| KRI ID | `kri_id` | Unique identifier |
| KRI Name | `kri_name` | 3–8 word informative name for CRA display. SOA format: "Vx (Visit Name) — [Procedure]" e.g. "V1 (Screening) — Vital Signs". Operational: "[Category] — [Concept]" e.g. "IP Storage — 2–8°C Requirement". **Never empty.** |
| Category | `category_label` | Full domain name — never the abbreviation code. SOA→"Schedule of Activities" / ELIG→"Eligibility" / SAF→"Safety & Toxicity" / END→"Endpoints & Statistics" / OPS→"Study Operations & Compliance" / NDEF→"Non-Defined KRIs" |
| Description | `description` | Full rule description |
| Rule for LLM | `rule_for_llm` | Machine-readable binary check: "[KRI_ID] — Verify that [specific condition]. Source: [where CRA finds evidence]. YES if [pass condition]; NO if [fail or missing]." **Never empty.** |
| Protocol Reference & Quote | `combined_ref` (pre-built field) | **One combined column — not two.** Build rule: **SOA KRIs from the SOA table** → reference is the table location, e.g. `Table: Schedule of Activities, pages XX-XX`. If a footnote applies: `Table: Schedule of Activities, pages XX-XX — Footnote N: "[exact footnote text]"`. **All other KRIs** (including SOA KRIs that originate from named protocol sections outside the SOA table): `Section X.X, p.XX — "[verbatim quote]"`. **How to identify SOA table KRIs**: A SOA KRI came from the SOA table if its `protocol_reference` page numbers fall within the SOA table's page range in the protocol. A SOA KRI came from another protocol section if its page numbers fall outside that range — keep the section reference for those. Quote always in `" "`. Never paraphrase. Always include page number. Do NOT repeat the footnote label twice (write "Footnote 4: [text]" once only). |

Formatting: blue header (#4472C4, white bold), frozen row 1, wrap text, auto-fit column widths.

3. **`Extracted_KRIs.xlsx`** — 6 sheets, one per domain. **Same 6 columns as above on every sheet.** Sheet names:

| Sheet | Domain | Sort |
|---|---|---|
| SOA | SOA | Preserve original JSON order — never sort by kri_id |
| ELIGIBILITY | ELIG | Sort by kri_id |
| SAF&TOX | SAF | Sort by kri_id |
| END&STAT | END | Sort by kri_id |
| OPS&COM | OPS | Sort by kri_id |
| NON-DEFINED | NDEF | Sort by kri_id |

Same formatting as Traceability_Matrix.

4. **`extracted_kris.json`** — all KRIs assembled (all 6 domains, deduplicated, NDEF-filtered, Red Team verified). Must include all fields: `kri_id`, `kri_name`, `category_label`, `description`, `rule_for_llm`, `combined_ref`, `domain`.

---

### Validation Checks (run after Step 1 for SOA; referenced throughout)

**Step 3A — Completeness**: Every Camelot CSV cell with "X" must have a KRI.
**Step 3A+ — Clinical Heuristics**: 10 protocol-agnostic heuristics:
- H1-H7: Drug accountability at EOS, pre-questionnaire procedures, ICF at first contact, AE from first dose, concomitant meds at all visits, screening symmetry, vital signs dual measurement.
- **H8 — Edge-Column Footnote Reconciliation**: For procedures in the first/last column, cross-check against footnotes. If a footnote says "at EDC/EOS" but ontology shows V0 (or vice versa), correct it.
- **H9 — Epoch Boundary Plausibility Check**: If a procedure has marks in treatment epoch (V5-V20) but also a single isolated mark in screening (V0/V1), flag it for review. Single marks in a distant epoch are suspicious.
- **H10 — Contiguous Coverage Gap Detection**: For procedures with 5+ visits, check for suspicious holes (>15% gap ratio). Re-verify gaps against the Camelot CSV. Use `detect_contiguous_gaps()` from `scripts/vision_table_extractor.py`.
**Step 3B — Accuracy**: 20 random KRIs re-verified against source pages. Threshold ≥85%.
**Step 3C — Consistency**: Same procedure across visits must have consistent details.

---

## Output artifacts

Each pipeline run produces these files in the output directory:

| File | Description | Phase |
|------|-------------|-------|
| `manifest.json` | Protocol metadata and section map | Pre-Step |
| `soa_table.csv` | **Canonical SoA matrix** (Camelot) | Pre-Step |
| `soa_table.json` | SoA matrix + visit-procedure mapping (Camelot) | Pre-Step |
| `ontology.json` | SoA ontology (visits, procedures, footnotes) | Pre-Step |
| `raw_SOA.json` | SOA KRIs (check-in + procedure + cross-visit, validated) | Step 1 |
| `{domain}_agent{N}.json` | Per-domain per-agent extraction output (5 files per domain) | Step 2.1 |
| `{domain}_tier1.json` | Auto-approved Tier 1 KRIs for each domain | Step 2.2 |
| `{domain}_tier2.json` | Disputed Tier 2 KRIs with all agent versions | Step 2.2 |
| `{domain}_discarded.json` | Single-vote outliers discarded from consensus | Step 2.2 |
| `raw_ELIG.json` | Verified ELIG Master List (Tier 1 + promoted Tier 2) | Step 2.3 |
| `raw_SAF.json` | Verified SAF Master List (Tier 1 + promoted Tier 2) | Step 2.3 |
| `raw_END.json` | Verified END Master List (Tier 1 + promoted Tier 2) | Step 2.3 |
| `raw_OPS.json` | Verified OPS Master List (Tier 1 + promoted Tier 2) | Step 2.3 |
| `dedup_round1_report.json` | Agent 1 deduplication log | Step 4 |
| `dedup_round2_report.json` | Agent 2 deduplication log | Step 4 |
| `dedup_final_report.json` | Agent 3 (final) deduplication log | Step 4 |
| `dedup_report.json` | Consolidated deduplication log (all 3 rounds) | Step 4 |
| `orphans_agent{N}.json` | Per-agent orphan findings (5 files) | Step 5 |
| `orphan_report.json` | Verified orphans + domain assignment log | Step 6 |
| `raw_NDEF.json` | Non-Defined KRIs (non-verifiable rules reclassified from all domains) | Step 8 |
| `golden_set.json` | Red Team audited master list — contains only VERIFIED KRIs after Step 10b review | Step 9–10 |
| `pending_manual_review.json` | KRIs removed from Golden Set pending user manual review (NEEDS_MANUAL_REVIEW) | Step 10b |
| `Traceability_Matrix.xlsx` | Full traceability matrix: KRI × domain × protocol quote (7 columns, no audit status) | Step 11 |
| `extracted_kris.json` | All KRIs assembled (all 6 domains, deduplicated, NDEF-filtered, audited) | Step 11 |
| `Extracted_KRIs.xlsx` | Final Excel workbook (6 sheets: SOA, ELIGIBILITY, SAF&TOX, END&STAT, OPS&COM, NON-DEFINED) | Step 11 |
| `gaps_report.json` | Completeness + heuristic results | Validation |
| `accuracy_report.json` | 20-KRI accuracy sample | Validation |
| `consistency_report.json` | Procedure family consistency | Validation |

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
9. **Visit window check-in KRI (MANDATORY)**: Every single visit in the SoA table MUST have a dedicated "check-in / within-window" KRI as its FIRST KRI. This includes all screening visits, treatment visits, follow-up visits, and unscheduled visits. The KRI verifies the visit occurred AND fell within the protocol-specified timing window (day reference ± tolerance). The `description` field MUST state the exact protocol-specified window verbatim. Never skip any visit.
10. **Table is truth**: The SoA table (via Camelot CSV) is the single source of truth for which procedures occur at which visits. Footnotes can ADD context (enrichment) but cannot OVERRIDE the table's X marks. If a footnote says "annually" but the table shows X at V10/V13/V16/V19, use the table's visits, not the footnote's interpretation.
11. **Footnotes verbatim**: `additional_footnotes` is always exact protocol text — never a summary or paraphrase. For short/single-topic footnotes: copy in full. For long/multi-topic footnotes: copy only the sentence(s) relevant to this specific KRI, but never truncate mid-sentence. See Footnote Rules F1–F5 above.
12. **rule_for_llm is a system instruction**: The `rule_for_llm` field must be written as a precise, binary, executable check for an LLM agent — specifying WHAT data to check, WHERE it comes from, WHEN (timepoint/visit), and WHAT binary condition determines pass/fail. Never write it as a prose description of the KRI. See rule_for_llm writing guide above.
13. **SOA cross-visit scope accuracy**: When creating KRIs for rules that apply to multiple visits (from footnotes, cross-sectional sweep, or other protocol sections), name and describe the KRI to reflect the EXACT scope stated in the source. Do NOT label a KRI as "All Visits" if the rule applies only to a subset of visits — state the exact visits or visit types (e.g. "Dosing Visits V1, V2, V3, V5" or "Visits with blood draws"). If a cross-visit rule has multiple source references in the protocol, list ALL of them in `protocol_reference` with their exact citations.
14. **Multiple protocol references**: If a KRI's rule is supported by more than one location in the protocol (e.g. stated in a footnote AND cross-referenced in the procedure section), include all references. Format: `"Section X.X, Page N: \"quote\"; Footnote Y, Page M: \"quote\""`. Never collapse multiple sources into one or omit secondary references.
15. **Target audience filter**: The extracted KRIs serve operational and clinical trial professionals: sponsor ClinOps, CRAs, CROs, and CRCs. KRIs must be actionable by these roles. Do NOT extract KRIs for:
    - Pure statistical methodology (alpha calculations, Type I error rates, significance levels, multiplicity adjustments)
    - Sample size / power calculations
    - Statistical analysis methods (ANCOVA, MMRM, regression methodology details)
    - Proportion/percentage calculation formulas
    - Sensitivity analysis methodology
    - Missing data imputation methodology
    - Subgroup analysis statistical methodology
    - Confidence interval calculation methods

    DO extract endpoint KRIs that ARE operationally relevant:
    - Primary/secondary endpoint definitions (what to measure, when, how)
    - Endpoint collection procedures and timing
    - Response criteria definitions that affect clinical decisions
    - Discontinuation/withdrawal rules tied to endpoint thresholds
    - Data collection requirements, eCRF completion rules, query resolution timelines

    In the END domain, only include rules that a CRA, CRC, or ClinOps professional would need to verify during monitoring or site management. Anything meant purely for biostatisticians analyzing the trial data should be excluded.
16. **Non-verifiable KRI detection (NDEF domain)**: After extraction and deduplication, scan ALL KRIs across all domains for rules that are NOT binary-verifiable by a system. A KRI is non-verifiable if its `rule_for_llm` meets any of these criteria:
    - References subjective judgment ("clinical judgment", "investigator discretion", "medical opinion", "as needed", "if appropriate", "as deemed necessary")
    - Uses vague/unmeasurable time expressions ("reasonable time", "promptly", "as soon as possible", "timely manner") WITHOUT specific numeric thresholds
    - Uses effort-based language ("efforts were made", "attempt to", "try to", "encourage")
    - References unmeasurable conditions ("adequate", "sufficient", "appropriate", "significant", "excessive", "reasonable")
    - Depends on external undefined criteria ("per local regulations", "per institutional policy", "per standard practice") where the specific requirement varies by site
    - Contains conditional logic that can't be system-checked ("if clinically indicated", "if medically necessary", "based on clinical assessment")

    Non-verifiable KRIs are moved to a 6th domain called **NDEF** (Non-Defined KRIs):
    - `category_id`: "NDEF"
    - `category_label`: "Non-Defined KRIs"
    - Each NDEF KRI gets an additional field: `non_verifiable_reason` — a specific explanation of why the rule is non-verifiable, quoting the problematic phrase from the `rule_for_llm`.
    - The original `kri_id` is preserved (not renamed).

---

## Comparing against a golden set

After Step 11 assembly completes, **always ask the user**:
> "Do you have a golden set to compare against? You can provide a file path or upload it."

If the user provides a golden set, run the comparison module (see `references/steps.md` for full details).

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

## Freezing a Golden Set (Regression Vault)

After a full extraction run is complete, validated (Step 3D passes at 100%), assembled (Step 4A), and the user has reviewed and approved the golden set — **ask the user if they want to freeze it in the regression vault.**

The regression vault preserves approved golden sets so that future skill updates can be checked for regressions. Each frozen golden set is immutable and represents ground truth for that protocol.

**When to ask:** After Step 4A assembly is complete and the user has confirmed they are satisfied with the results. Say something like:

> "The golden set for [protocol] is complete and validated. Would you like to freeze it in the regression vault? This preserves it so we can detect if future skill updates break anything."

**If the user says yes**, use the `kri-regression-tester` skill's freeze operation. Specifically, run:

```bash
python ~/.claude/skills-repo/kri-regression-tester/scripts/freeze.py \
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
- `scripts/step4a_assemble.py` — Assembly + Excel generation (no LLM needed)
