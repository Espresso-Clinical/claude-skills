---
name: accompanying-doc-kri-extractor
description: >
  Extracts Key Risk Indicators (KRIs) from clinical trial documents that
  accompany a protocol — Clinical Monitoring Plan (CMP), Clinical Study
  Management Plan (CSMP), IMP Handling Manual (IMP), Protocol Deviation
  Handling Plan (PDHP), Pharmacovigilance Plan (PV Plan), Statistical Analysis
  Plan (SAP), and Protocol Deviation Classification Guide (PD Classification
  Guide). Requires a protocol Golden Set as input so KRIs already present in
  the protocol are not duplicated. Use this skill whenever a non-protocol
  trial document is provided for rule/KRI extraction. Do NOT use this skill
  for protocol PDFs (use protocol-kri-extractor instead).
---

# Accompanying Document KRI Extractor

## Ultimate Goal

Produce, for a single accompanying document, a golden set of KRIs covering **everything monitorable** in that document — every rule, obligation, threshold, timeline, process step, reporting requirement, classification criterion, statistical-handling rule, or monitoring obligation that a trial official (CRA, medical monitor, statistician, PV officer, DM lead, etc.) should see, verify, or act upon — **minus whatever the protocol's own golden set already covers**.

Output is **per-document**. Each accompanying document produces its own golden set. There is **no cross-accompanying-document deduplication** — if the same rule appears in the IMP Manual and the CMP, it appears in both output files, because each document is consumed independently by its owning function.

The protocol golden set is treated as ground truth. Matches are dropped from this document's output — never re-judged.

---

## Supported document types

| ID | Full name |
|----|-----------|
| CMP | Clinical Monitoring Plan |
| CSMP | Clinical Study Management Plan |
| IMP | IMP Handling Manual |
| PDHP | Protocol Deviation Handling Plan |
| PV_PLAN | Pharmacovigilance Plan |
| SAP | Statistical Analysis Plan |
| PD_CLASS | Protocol Deviation Classification Guide |

**At skill activation, the agent MUST confirm the document type.** If the user named it in their request, proceed. If not, **ask the user** which of the seven types the document is — do NOT attempt to auto-detect. The document title is assumed to be unambiguous; resource spent on auto-classification is wasted.

---

## ⚠️ META-RULE — Skill Updates Are Additive Only

Every step, rule, and definition in this `SKILL.md`, in `references/`, and in `scripts/` is **mandatory**. Nothing is skippable, and nothing is removed without explicit user instruction. This mirrors the `protocol-kri-extractor` skill's meta-rule and applies here identically. Silent removal, weakening, or skipping of any step is a skill violation. When in doubt, add alongside — do not replace.

---

## Inputs (required)

1. **Accompanying document PDF** — absolute path to the file.
2. **Protocol golden set JSON** — the authoritative KRI list produced by `protocol-kri-extractor` for the SAME trial. Typically at `~/Downloads/extractor/<protocol_id>/<latest_run_id>/golden_set.json`. Expected shape: `{ "kris": [ {...}, ... ] }`.
3. **Document type ID** — one of `CMP | CSMP | IMP | PDHP | PV_PLAN | SAP | PD_CLASS` (user-supplied or confirmed).

If any of these three is missing, **stop and ask the user**. Never proceed with defaults.

---

## Output directory

```
~/Downloads/extractor/<protocol_id>/<run_id>/accompanying/<doc_type>/
  run_config.json
  raw_extractions/
    claude_1.json … claude_5.json
    gemini_1.json … gemini_5.json
  consensus_report.json
  tier2_autojudgment_report.json
  tier3_promotion_report.json
  orphan_scan_report.json
  protocol_dedup_report.json          # KRIs dropped because present in protocol golden set
  intra_dedup_report.json             # duplicates within this doc
  ndef_sweep_report.json
  verification_report.json
  accompanying_golden_set.json        # final deliverable
  Accompanying_KRIs.xlsx
```

If `<protocol_id>` or `<run_id>` are not supplied by the user, ask. They anchor the output to the same trial/run as the protocol golden set so deliverables stay organized.

---

## KRI schema

Every extracted KRI matches this structure:

```json
{
  "kri_id": "IMP-003",
  "kri_name": "Temperature excursion reporting window",
  "description": "What this KRI monitors and why it matters.",
  "doc_type": "IMP",
  "doc_type_label": "IMP Handling Manual",
  "rule_for_llm": "Verify that any temperature excursion at the site was reported to the sponsor within 24 hours of detection.",
  "document_reference": "Section 6.3, p.18",
  "supporting_quote": "Any temperature excursion must be reported to the sponsor within 24 hours of detection.",
  "combined_ref": "Section 6.3, p.18 — \"Any temperature excursion must be reported to the sponsor within 24 hours of detection.\"",
  "severity": "critical|major|minor",
  "ndef": false
}
```

**Field rules (identical intent to the protocol skill — read carefully):**

- `kri_id` — format `<DOC_TYPE>-<3-digit sequence>` (e.g. `CMP-001`, `SAP-042`). Assigned in Stage 8 in document order.
- `supporting_quote` — verbatim text ≤30 words copied **exactly** from the PDF page. **NEVER wrap in outer double quotes.** Do not start or end the string with `"`. The `combined_ref` field adds its own quotes.
- `combined_ref` — always computed as `f'{document_reference} — "{supporting_quote}"'` (em dash `—`, not hyphen `-`).
- `document_reference` — section label + page number only (e.g. `"Section 4.4.1, p.65"`). **No embedded quote.** If the document has no numbered sections, use the heading text + page (e.g. `"Risk-Based Monitoring Approach, p.12"`).
- `severity` — **critical**: patient-safety-affecting rules, primary-endpoint handling, regulatory-reporting timelines. **major**: secondary endpoints, key operational controls, deviation categorization rules. **minor**: administrative/descriptive rules, minor operational guidance.
- `ndef` — set to `true` ONLY by the Stage 6 NDEF sweep. Never set by extractors.
- No trailing whitespace in any text field; no duplicate page numbers in `document_reference`.

---

## CRITICAL — Atomicity Principle (applies to ALL doc types)

Every KRI must be atomic. A single KRI represents exactly **ONE** verifiable check about **ONE** thing at **ONE** time point in **ONE** clinical context. Never combine multiple rules, multiple thresholds, multiple time points, or multiple clinical settings into a single KRI.

Examples of violations (WRONG):
- "Verify temperature excursions and humidity excursions are reported within 24 hours" → must be 2 KRIs
- "Verify SDV rate is 100% for primary endpoint data, 30% for secondary" → must be 2 KRIs
- "Verify SAEs are reported within 24h and SUSARs within 7 days" → must be 2 KRIs
- "Verify deviations are classified as major, minor, or critical" → must be 3 KRIs (one per category definition) OR one KRI about the categorization obligation, depending on context

Examples of correct atomicity:
- "Verify that every temperature excursion was reported to the sponsor within 24 hours of detection"
- "Verify that SDV coverage for primary-endpoint CRF pages is 100%"
- "Verify that SAEs are reported to the sponsor within 24 hours of site awareness"

---

## ⚠️ MANDATORY — Compliance Monitor Agent (runs throughout entire pipeline)

Every execution of this skill MUST launch a **Compliance Monitor Agent** at the very start — before Stage 1 begins — via the Agent tool with `subagent_type="general-purpose"`. This agent runs in parallel with the entire pipeline. It is not optional.

**What it does:**
- After each stage, verifies the stage's required artifact exists on disk and conforms to the expected schema.
- Verifies Stage 2 produced exactly 10 raw extractions (5 Claude + 5 Gemini).
- Verifies Stage 3 tier counts sum to the total candidate set.
- Verifies Stage 7 shows 100% PASS (or user-resolved FLAG decisions) before Stage 8 starts.
- Verifies the protocol-golden-set dedup (Stage 5a) ran BEFORE intra-dedup (Stage 5b).
- Reports at every phase gate; blocks advancement if any required artifact is missing.

---

## Pipeline — 8 stages (all mandatory, run in order)

### Stage 1 — Setup & confirm

1. Confirm the document type with the user (see "Supported document types").
2. Ask for `<protocol_id>` and `<run_id>` if not provided.
3. Verify the protocol golden set JSON path exists and loads as valid JSON with a `kris` key.
4. Create the output directory (see above).
5. Write `run_config.json` containing: input PDF path, doc type, protocol golden set path, protocol golden set SHA-256 hash, output dir, start timestamp.

**Artifact:** `run_config.json`.

### Stage 2 — Parallel 10-agent extraction

Run **ten sub-agents in parallel** on the full document:

- **5 Claude sub-agents** — launched via the Agent tool with `subagent_type="general-purpose"`. Each agent is independent and does not see the others' outputs.
- **5 Gemini agents** — launched via `scripts/gemini_extract.py` (five calls, each with a different random seed).

All ten agents receive the same input bundle:

1. The full document (PDF text, page-by-page)
2. The full contents of `references/extraction_rules.md`
3. The **type-specific brief** from `references/doc_type_briefs.md` for the confirmed doc type
4. An explicit instruction: **"The brief's examples are illustrative, not exhaustive. Extract EVERY rule, obligation, threshold, timeline, classification criterion, reporting requirement, handling procedure, statistical-handling instruction, or monitoring obligation present anywhere in the document, even if it does not match the examples. Err on the side of inclusion — Stage 3 consensus will filter false positives."**

Each agent emits a JSON file conforming to the KRI schema (minus `kri_id`, which is assigned in Stage 8). Output filenames: `raw_extractions/claude_{1..5}.json` and `raw_extractions/gemini_{1..5}.json`.

**Artifacts:** 10 files in `raw_extractions/`.

### Stage 3 — Consensus tiering

For every candidate KRI across the 10 outputs, count how many agents produced a semantically equivalent KRI (use a two-pass match: textual similarity ≥0.7 on `supporting_quote` OR semantic equivalence on `rule_for_llm`).

- **Tier 1 — 7-10 agents agree** → auto-approved into the candidate set.
- **Tier 2 — 4-6 agents agree** → sent to the **Tier 2 auto-judgment panel** (6 neutral judges: 3 Claude + 3 Gemini) which issues a per-KRI verdict (approve / reject / flag). Approved → candidate set. Flagged items are surfaced to the user at end-of-run in `flagged_review_decisions.json`. In default auto-approve-unanimous mode, a flag without unanimous approve defaults to rejected; in `--interactive` mode, the user decides every flag.
- **Tier 3 — 1-3 agents agree** → sent through the **T3 promotion pipeline** (same gates as the protocol skill, in order):
  - **T3-1 Coverage** — is the underlying obligation genuinely present in the document?
  - **T3-2 Verbatim** — is the `supporting_quote` verbatim on the cited page?
  - **T3-2.5 Atomicity** — is the KRI atomic per the atomicity principle?
  - **T3-3 Panel** — 6-judge panel re-assesses.
  - **T3-4 Aggregate** — final decision.
  Survivors → candidate set. Rejects logged.

**Tier 3 KRIs are never auto-deleted.** They go through the full promotion pipeline.

**Artifacts:** `consensus_report.json`, `tier2_autojudgment_report.json`, `tier3_promotion_report.json`.

### Stage 4 — Orphan scan (page-by-page)

Because accompanying documents have no SoA/domain structure, the orphan scan is **page-by-page, not section-by-section**.

**Architecture:** 4-agent panel — **2 Claude + 2 Gemini**.

**Phase 4.1 — Per-page sweep.** Each of the 4 agents reads every page of the document and lists every obligation, threshold, timeline, rule, classification criterion, or monitoring instruction present on that page.

**Phase 4.2 — Consolidation.** Candidates are consolidated across the 4 agents. A candidate must have ≥2-agent agreement to survive consolidation.

**Phase 4.3 — Cross-check.** Each consolidated candidate is matched against the Stage 3 candidate set. If NOT covered, it is an orphan.

**Phase 4.4 — Promotion gates.** Orphans are passed through the same T3 promotion gates (Coverage / Verbatim / Atomicity / Panel). Survivors are appended to the candidate set.

**Artifact:** `orphan_scan_report.json`.

### Stage 5 — Deduplication (two sub-stages, run in order)

**Stage 5a — Dedup against protocol golden set (runs FIRST).**

For every candidate KRI produced through Stages 2-4, compute a match against every KRI in the protocol golden set. A match is declared if EITHER:

- Semantic equivalence score ≥ 0.85 on `rule_for_llm` AND both KRIs check the same obligation, OR
- `supporting_quote` is verbatim-present in any protocol golden set KRI's `supporting_quote`.

Matches are **dropped from this document's output** and logged to `protocol_dedup_report.json` with the matched protocol KRI's `kri_id`, the similarity score, and the matched field. This gives the user a full audit trail of what was removed and why.

**Stage 5b — Intra-document dedup (runs AFTER 5a).**

Within the surviving candidate set for THIS document only, collapse semantic duplicates using the same two-pass detection (textual ∩ semantic). When a duplicate cluster is found, keep the KRI with:

1. The most specific `rule_for_llm` (most concrete values/thresholds)
2. The best `supporting_quote` (closest to verbatim rule text)
3. The earliest page reference (tiebreaker)

Merged duplicates are logged to `intra_dedup_report.json`.

**No cross-accompanying-document dedup.** Each accompanying document is independent.

**Artifacts:** `protocol_dedup_report.json`, `intra_dedup_report.json`.

### Stage 6 — NDEF sweep

Sweep every surviving KRI and set `ndef: true` if the rule **cannot be deterministically checked** by a downstream LLM-based monitoring agent. Non-definable indicators include:

- Rules with open-ended judgment language: "as appropriate", "where feasible", "at the Sponsor's discretion", "the CRA should use judgment", "if clinically indicated"
- Purely advisory or descriptive statements with no verifiable action
- Rules requiring external information not available from trial data (e.g., regulatory-interpretation dependent)
- Rules whose threshold/timing is not specified and cannot be inferred

NDEF items are **moved to a separate `ndef_kris` array in the final output** — they do not enter the main `kris` array. They are preserved (not deleted) so the user can still see what the document contains.

**Artifact:** `ndef_sweep_report.json` (lists every KRI evaluated, the verdict, and the trigger phrase when flagged).

### Stage 7 — Final verification (correctness check, blocking gate)

A **5-judge cross-model panel (3 Claude + 2 Gemini)** independently reviews **EVERY** surviving KRI (both the main list and the `ndef_kris` list) against these 5 checks:

- **C1 — Reference accuracy.** The `document_reference` points to the actual section/page in the PDF. The page number exists. The section label matches the document's actual structure.
- **C2 — Verbatim accuracy.** The `supporting_quote` appears verbatim on the cited page. Whitespace and punctuation normalization is allowed; word-level changes are not.
- **C3 — Rule correctness.** The `rule_for_llm` is a deterministic, checkable instruction that accurately reflects the obligation described by the quote. Exception: KRIs in `ndef_kris` are only checked for the other criteria.
- **C4 — Description fidelity.** The `description` accurately reflects what the KRI is monitoring and why it matters. No contradiction with the `rule_for_llm`.
- **C5 — Schema/field compliance.** No outer quotes on `supporting_quote`; `combined_ref` uses em dash `—` and correctly concatenates the other two fields; `severity` ∈ {critical, major, minor}; `doc_type` matches the run's confirmed type; no duplicate page numbers; no trailing whitespace.

**Verdicts per judge:** PASS / FAIL / FLAG (with one-sentence reason).

**Consensus adjudication:**
- 5/5 PASS → retained.
- Any FAIL on C1/C2 (reference or verbatim) → the KRI is **dropped** from the output (logged with reason). Never auto-corrected — a wrong citation or fabricated quote means the KRI itself is unreliable.
- FAIL on C5 (schema) → auto-corrected (normalize whitespace, strip outer quotes, fix em dash, etc.) and re-verified.
- FAIL on C3/C4 → surfaced to the user as a FLAG for decision.
- Any FLAG → surfaced to the user; user resolves (retain / drop / edit) before Stage 8.

**Blocking gate:** Stage 8 (assemble) cannot begin until `verification_report.json` shows 100% PASS (after auto-corrections and user-resolved flags). This is a hard gate — the Compliance Monitor enforces it.

**Artifact:** `verification_report.json` (per-KRI per-check per-judge verdicts).

### Stage 8 — Assemble

1. Assign `kri_id` values to every retained KRI in document order, numbered `<DOC_TYPE>-001`, `<DOC_TYPE>-002`, … Continue numbering into `ndef_kris` (they do not restart from 001).
2. Compute `combined_ref` for every KRI.
3. Write `accompanying_golden_set.json`:
   ```json
   {
     "meta": {
       "doc_type": "IMP",
       "doc_type_label": "IMP Handling Manual",
       "protocol_id": "...",
       "run_id": "...",
       "protocol_golden_set_sha256": "...",
       "generated_at": "..."
     },
     "kris":       [ ... ],
     "ndef_kris":  [ ... ]
   }
   ```
4. Render `Accompanying_KRIs.xlsx` with one sheet `KRIs` + one sheet `NDEF` + one sheet `Dropped (vs protocol)`. Main columns: `KRI ID`, `KRI Name`, `Description`, `Doc Type`, `Rule for LLM`, `Document Reference & Quote` (= `combined_ref`), `Severity`, `NDEF`.

**Artifacts:** `accompanying_golden_set.json`, `Accompanying_KRIs.xlsx`.

---

## How to run

### First time

Ensure the Gemini secrets file from the protocol skill is available:

```
~/.claude/secrets/protocol-kri-extractor.json
```

This skill reuses that file for Gemini API access.

### Canonical entry point

```bash
python scripts/run.py \
  --pdf <absolute-path-to-accompanying-doc.pdf> \
  --doc-type <CMP|CSMP|IMP|PDHP|PV_PLAN|SAP|PD_CLASS> \
  --protocol-golden-set <absolute-path-to-golden_set.json> \
  --protocol-id <protocol_id> \
  --run-id <run_id>
```

`run.py` performs the deterministic work (setup, Gemini extractions, dedup, NDEF, verification aggregation, assembly). The top-level Claude instance — following this SKILL.md — is responsible for the Agent-tool work: spawning the 5 Claude extraction sub-agents (Stage 2), the Tier 2 and Tier 3 judge panels (Stage 3), the orphan-scan panel (Stage 4), and the Stage 7 verification panel. SKILL.md is the orchestration contract; `run.py` is the deterministic helper.

### Step-by-step execution contract for Claude

Claude, when this skill is invoked, you do the following in order:

1. **Confirm doc type and run inputs** (Stage 1).
2. Run `python scripts/run.py setup ...` to create the output dir and `run_config.json`.
3. **Launch 5 Claude extraction sub-agents in parallel** (Stage 2), giving each the full document text + extraction rules + doc-type brief. Save outputs to `raw_extractions/claude_{1..5}.json`.
4. **Run `python scripts/gemini_extract.py` five times in parallel** (different seeds) to produce `raw_extractions/gemini_{1..5}.json`.
5. **Run consensus tiering** via `python scripts/consensus_tier.py` — produces `consensus_report.json` with T1/T2/T3 classification.
6. **For T2:** launch a 6-judge auto-judgment panel (3 Claude Agents + 3 Gemini calls) on every T2 KRI. Save verdicts to `tier2_autojudgment_report.json`.
7. **For T3:** launch the T3 promotion pipeline (coverage + verbatim + atomicity + panel + aggregate). Save to `tier3_promotion_report.json`.
8. **Launch the orphan-scan panel** (2 Claude + 2 Gemini, page-by-page) and apply the promotion gates. Save to `orphan_scan_report.json`.
9. **Run `python scripts/dedup_vs_protocol.py`** to drop KRIs already in the protocol golden set. Save to `protocol_dedup_report.json`.
10. **Run `python scripts/intra_dedup.py`** for within-document dedup. Save to `intra_dedup_report.json`.
11. **Run `python scripts/ndef_sweep.py`** (or launch an Agent with the NDEF rules from SKILL.md if the script is a stub). Save to `ndef_sweep_report.json`.
12. **Launch the Stage 7 verification panel** (5 judges). Save to `verification_report.json`. **Blocking gate: 100% PASS before continuing.**
13. **Run `python scripts/assemble.py`** to produce `accompanying_golden_set.json` and `Accompanying_KRIs.xlsx`.
14. Report back to the user with counts, location, and any surfaced flags.

---

## Non-negotiable rules

- The protocol golden set is treated as ground truth — nothing in it is re-derived or re-judged.
- Every stage emits its artifact to disk **before** the next stage runs.
- No stage is skipped for speed, cost, or convenience.
- The 10-agent parallel extraction is mandatory; fewer than 10 agents = skill violation.
- The orphan-scan panel is mandatory (4 agents); skipping it = skill violation.
- The NDEF sweep is mandatory and runs AFTER dedup.
- The final verification panel blocks assembly. Assembly without a passing verification report = skill violation.
- **No cross-accompanying-document dedup.** Each document's golden set is independent.
