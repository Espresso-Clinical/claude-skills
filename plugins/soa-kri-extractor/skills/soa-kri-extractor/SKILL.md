---
name: soa-kri-extractor
description: >
  Advanced SOA-domain-only KRI extractor. Reads a clinical trial protocol PDF and
  produces the authoritative Golden Set of SOA (Schedule of Activities) KRIs —
  covering BOTH the structured SoA table AND narrative cross-visit / methodology /
  long-term-tracking rules from protocol body text. Use this skill whenever the
  user wants to: parse the SoA table of a clinical protocol, generate atomically
  decomposed SOA KRIs, extract Schedule-of-Activities rules at full granularity,
  or build the SOA-domain rule set for a Phase 2/3 trial. Works on any protocol
  regardless of sponsor or format. Always use this skill when the user provides
  a protocol PDF and asks for SOA / Schedule-of-Activities / visit-schedule KRIs.
---

# SOA KRI Extractor

A specialist skill that extracts SOA-domain KRIs from any clinical trial protocol PDF at full atomic granularity, with every KRI judged through the full validation gauntlet. Protocol-agnostic: no hardcoded sponsor names, protocol IDs, visit labels, or therapeutic areas.

## Ultimate goal

Produce **`soa_golden_set.json`** + **`soa_golden_set.xlsx`** — the authoritative, verified, atomically-decomposed SOA KRI list for the protocol. Every KRI is binary, machine-checkable, and ready to drive automated deviation detection.

---

## ⚠️ META-RULE — Additive only

Every refinement, update, or improvement to this skill is **additive**. Never removes, overwrites, or silently replaces previous rules. The ONLY way something gets changed, removed, or replaced is if the user explicitly says so — even then, the change must be made as an explicit, documented edit. Every step, every rule, every instruction documented here is **MANDATORY** — not optional, not skippable.

---

## Output schema — 13 fields per KRI

```json
{
  "kri_id": "SOA-<visit>-<NNN>  e.g. SOA-V1-001, SOA-SCR-014, SOA-CHECKIN-V2-009, SOA-CROSS-003, SOA-ORPHAN-FOOTNOTE-002",
  "kri_name": "<visit_label> - <procedure>   OR   <visit_label> - <window> - Check-in   OR   <descriptive cross-visit name>",
  "description": "Concrete, coherent description specific to this KRI, mentioning analytes/windows/conditions where applicable",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: ...\nCHECK: ...\nDEVIATION: ...",
  "protocol_reference": "Schedule of Activities, Footnote N, Footnote M, p.X-p.Y    OR    Section N.N, Page Y",
  "supporting_quote": "Verbatim quote(s), topic-bound, ≤30 words per quote",
  "combined_ref": "f'{protocol_reference} — \"{quote1}\", \"{quote2}\"'",
  "additional_footnotes": "Footnote N: full verbatim text — OR null",
  "severity": "critical | major | minor",
  "deviation_level": "subject | visit | site | study",
  "agent_count": 10
}
```

### Field rules

- `protocol_reference` — section label + page range ONLY. **No embedded quote.**
- `supporting_quote` — ≤30 words, copied verbatim. **NEVER** starts or ends with `"`.
- `combined_ref` — computed deterministically with em dash `—` (not hyphen).
- `severity` — `critical`: primary endpoints, analysis populations, stopping rules. `major`: secondary endpoints, biomarker endpoints, safety thresholds. `minor`: exploratory or administrative governance.
- `deviation_level` — defaults to `"subject"`. Drives the granularity of deviation detection.
- `agent_count` — `10` (deterministic) for atomic-grid KRIs. `7` for LLM-extracted SOA-text KRIs. `5` to force Step 2.6 judgment (T2 path). `≤3` triggers Tier 3 promotion pipeline.

### Three SOA KRI types and their reference format

| Type | `protocol_reference` | `supporting_quote` source |
|---|---|---|
| Table procedure WITH footnote | `Schedule of Activities, Footnote N, p.X-p.Y` | Topic-bound excerpt from Footnote N's text |
| Table procedure WITHOUT footnote | `Schedule of Activities, p.X-p.Y` | Procedure name or visit label from table page |
| Non-table KRI (body text) | `Section N.N, p.Z` | Verbatim text from cited section |

`p.X-p.Y` is the **actual Camelot-detected table pages** (from `soa_table.json.pages`), NOT the broader manifest section range.

---

## CRITICAL — The Atomicity Principle

> One procedure × one visit = one KRI. Never combine multiple procedures or multiple visits into a single KRI.

### Decomposition rules

**Compound procedure rows** (split when distinct procedure-level names are joined by `,`, `and`, or `or`):
- `"Blood chemistry, hematology, ESR, and CRP"` → 4 atomic procedures ✓
- `"Ulcer culture and antibiotic susceptibility testing"` → 2 atomic procedures ✓

**Compound visit columns** (split when range / list / multi-visit set):
- `"W2-11"` → V2, V3, V4, V5, V6, V7, V8, V9, V10, V11 ✓
- `"V3, V5, V7"` → 3 atomic visits ✓
- `"all visits"` named multi-visit set → expand to N atomic per-visit KRIs ✓

**Cross-visit rules valid for all visits** → emit N atomic per-visit KRIs (one rule per visit), never a single multi-visit KRI.

**Footnote-driven test decomposition** (umbrella lab / assessment rows) — when a single row's *label* is a generic category (e.g. `"Laboratory tests"`, `"Safety labs"`, `"Clinical laboratory assessments"`, `"Blood tests"`) but its **footnotes enumerate ≥2 distinct named tests**, split into one atomic KRI per named test, per visit the row is marked — then drop the umbrella:
- `"Laboratory tests"` + footnotes naming a chemistry panel, a blood count, and a coagulation panel → `Biochemistry`, `Complete Blood Count`, `Coagulation` (3 KRIs per marked visit) ✓
- The split set is **footnote-driven, not fixed**: emit exactly as many KRIs as the footnotes name distinct tests. A row whose footnote merely lists the **analytes of ONE test** is NOT split (see *When NOT to split*).
- Each child KRI binds **only its own footnote slice** — the chemistry KRI cites the chemistry-analyte footnote, not the blood-count footnote — and **enumerates every analyte / component that test measures** inside `SOURCE/CHECK/DEVIATION` (per *Footnote enrichment IN rule_for_llm*).
- **Shared timing / acceptability footnotes** (e.g. `"results acceptable up to 3 months prior"`, `"may be drawn 4 days before the visit and reviewed prior to IP"`) are folded into the `CHECK`/`DEVIATION` of **every** child test, and **carve-outs are preserved** (e.g. `"hsCRP preferred over CRP"`, `"direct bilirubin required only if total bilirubin is abnormal"`).
- **Structural and protocol-agnostic** — fires only when a generic row actually hides multiple named tests in its footnotes, and stays silent otherwise. A protocol that already lists the tests as **separate rows** converges on the same per-test KRIs via the ordinary row split above; both layouts yield one KRI per named test.

### When NOT to split

- **Recognized standardized bundles** stay whole (component lists go in `rule_for_llm`):
  ```
  Vital signs, Complete blood count (CBC), Basic metabolic panel (BMP),
  Comprehensive metabolic panel (CMP), 12-lead ECG, Lipid panel, Lipid profile,
  Liver function tests (LFTs), Renal function tests (RFTs), Coagulation panel,
  Urinalysis, Physical examination, Full physical examination
  ```
- **A footnote that lists the analytes of a single test does NOT trigger a split** — `"Blood count includes RBC, HGB, HCT, WBC, platelets…"` is ONE recognized panel (`Complete Blood Count`), enumerated in `rule_for_llm`, never atomized per-analyte. Footnote-driven decomposition (above) splits only when the footnotes name ≥2 **distinct tests**; each resulting child that is itself a panel then stays whole.
- **Parentheticals** are protected — `"Manual ulcer measurements (depth and surface area)"` stays whole.
- **Slash separators** (`/`) are NOT split — `"Assessment of clinical signs/symptoms of ulcer infection"` is one concept.
- **Illustrative markers** force keep-whole: `such as`, `including`, `to include`, `e.g.`, `i.e.`, `for example`.
- **Single-word fragments** must be in `SHORT_ACRONYM_OK` OR be ≥7 chars AND not in `NON_PROCEDURE_FRAGMENTS`. Otherwise → review queue.

### Stoplists

**SHORT_ACRONYM_OK** (single-word atomic procedures allowed):
```
esr, crp, cbc, ecg, ekg, bmp, cmp, lfts, rfts, bp, hr, rr, spo2, pe, vs,
wbc, rbc, plt, hgb, ast, alt, ggt, alp, bun, ldl, hdl, tg, tc, ana, ck,
tsh, t4, t3, psa, ada, pk, pcsk9
```

**NON_PROCEDURE_FRAGMENTS** (never accept alone):
```
prior, both, either, neither, and, or, after, before, during, with,
without, the, a, an, any, all, some, to, include, including, such, as,
for, in, of, on, by, from, at, is, are, was, were
```

---

## CRITICAL — Rule for LLM: 3-line SOURCE/CHECK/DEVIATION format

Every `rule_for_llm` MUST be formatted as three labeled lines:

```
SOURCE: <data field / record / measurement, per <unit>>
CHECK: <the verification rule with exact thresholds, windows, lists>
DEVIATION: <what counts as a deviation, with exact failure conditions>
```

### Templates

**Procedural KRI (procedure × visit cell):**

> ⚠️ Before applying this template, identify the source table's primary-key shape. Most procedural records are `(subject, visit)` keyed — the template below applies directly. But some tables are `(subject, visit)` keyed with **timepoint COLUMNS** (e.g. `<field>_pre / _mid / _post`) instead of separate timepoint rows. For those, do NOT look for separate `D1_PRE` / `D1_POST` records — see the timepoint-columns variant below.

```
SOURCE: The <procedure> record at the <visit_display_name> (<visit_id>) visit, per subject[. Required <items>: <list>].
CHECK: <procedure> was performed and dated at <visit_display_name> per the Schedule of Activities[. The record contains values for all N required <items>: <list>][. <methodology / timing>].
DEVIATION: For an active subject expected to attend <visit_display_name>, no <procedure> record exists at that visit, or the record is undated[. Or any of the N required <items> is missing].
```

**Procedural KRI variant — timepoint-columns source (single visit row with pre/mid/post cells):**

Use when the source table merges sub-visit timepoints into a single visit row with timepoint-suffixed columns. SOURCE references the specific cells; CHECK requires the cells be populated. Note: per-cell timestamps are typically NOT captured, so any temporal check ("after iv_end_time") will fail — drop it.

```
SOURCE: <source_table> row at visit_label='<visit>' (visno='<NN>'), per subject; specifically the cells <cell_1>, <cell_2>, ..., <cell_K>.
CHECK: The row exists, is dated (available_at), AND at least one of the K target cells is non-null (assessment performed).
DEVIATION: Row is missing OR all K target cells are null.
```

**Procedural KRI variant — assessment-of-event gated on occurrence:**

Use when the SoA lists "Assessment of [event type]" at certain visits but the assessment is only meaningful when the underlying event has occurred (e.g. amputations, surgical procedures, hospitalizations). Without the gate, the rule fires unconditionally on every subject who never experienced the event and produces noise.

```
SOURCE: <event_table> rows for this subject (event_date column); the visit date for V<N> from <visits_table>.
CHECK: Conditional on event status as of V<N>:
       (a) If any <event_table>.event_date <= V<N> visit date: an assessment record is required at V<N> and must be dated.
       (b) If no event has occurred on or before V<N>: this rule is N/A.
DEVIATION: Event occurred on or before V<N> AND no corresponding assessment record exists, OR record is undated.
```

**Check-in (window relative to randomization):**

> ⚠️ The `<offset>` MUST be derived from the protocol's Day-N label for the visit, NOT from `Week_number × 7`. Most protocols define Day 1 = first day of Week 1, which makes the Week-N target = `Day 1 + (Day_N − 1)` days. Look up the SoA's Day label (e.g. "Day 8" for Week 2) and use `Day_N − 1` as the offset. Encoding `Week_number × 7` is wrong by exactly one week and produces a 100% false-positive rate on any subject whose visits are on schedule (when the window is tight, e.g. ±3 days).

```
SOURCE: The <visit_id> (<visit_label>, Day <day_N>) visit date and the randomization (Day 1) date, per subject.
CHECK: <visit_id> visit date is within ±<N> days of (Day 1 + <day_N − 1> days), per the protocol footnote on visit windows.
DEVIATION: For an active subject, the <visit_id> visit date is outside this window, or the visit date is missing.
```

**Day 1 same-day ordering:**
```
SOURCE: The <visit_id> visit date and the Day 1 study-treatment administration timestamp, per subject.
CHECK: <visit_id> occurred on the same calendar day as Day 1 treatment, <before|after> the treatment was administered.
DEVIATION: For a treated subject, the <visit_id> visit date is not the Day 1 date, or the recorded order vs treatment administration is wrong.
```

**Screening before randomization:**
```
SOURCE: The screening (<visit_id>) visit date and the randomization (Day 1) date, per subject.
CHECK: Screening occurred within <N> days before randomization (i.e., 0 ≤ Day 1 − <visit_id> date ≤ <N> days).
DEVIATION: For a randomized subject, screening occurred more than <N> days before randomization, or screening date is missing.
```

**Cross-visit / narrative rule:**
```
SOURCE: Per <subject|measurement>: <listed data fields and reference points>.
CHECK: <the rule with all conditions and thresholds spelled out>.
DEVIATION: <every concrete failure condition, exhaustively listed>.
```

---

## CRITICAL — Footnote enrichment IN rule_for_llm

When a footnote provides **specific items, parameters, components, or analyte lists** that define what the procedure must include, those items MUST appear in the `SOURCE / CHECK / DEVIATION` lines of `rule_for_llm`, not just in the citation.

### Concrete example — Blood chemistry

**WRONG (citation-only):**
```
CHECK: Blood chemistry was performed and dated at SCR per the Schedule of Activities.
```

**CORRECT (enrichment embedded):**
```
SOURCE: The Blood chemistry record at the screening (SCR) visit, per subject. Required analytes: sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, albumin.
CHECK: Blood chemistry was performed and dated at screening (SCR) per the Schedule of Activities AND the record contains values for all 14 required analytes.
DEVIATION: For an active subject expected to attend SCR, no Blood chemistry record exists, the record is undated, or any of the 14 required analytes is missing.
```

### What categories of footnote details to embed

| Footnote content | Where to embed |
|---|---|
| Analyte / parameter list | SOURCE + CHECK + DEVIATION (all 3) |
| Specific measurements (BP, HR, temp, weight; ECG leads; depth + surface area) | SOURCE + CHECK |
| Timing constraint within visit (`pre-dose`, `within 1h`) | CHECK + DEVIATION |
| Conditional applicability (`if AE`, `if symptoms present`) | CHECK (as precondition) |
| Equipment / methodology (`supine`, `5 min rest`, `12-lead`) | CHECK |
| Sample type / volume / handling | SOURCE + DEVIATION |
| Sub-visit timing (pre-dose, post-dose, peak) | SOURCE + CHECK |
| Frequency-within-visit (`twice`, `every 15 min`) | CHECK + DEVIATION |
| Named drugs / agents named under a permitted / prohibited / rescue cue (e.g. `"patients may use acetaminophen and/or metamizole"`) | SOURCE — surfaced so the drug names are captured; final rule wording is authored downstream by the Distiller |

Implementation: `footnote_enrichment_parser.py` extracts these from the topic-bound footnote fragment (Step 1D-iv) and the SOA generator (Step 9) injects them into the rule.

### Recognized bundles list components in rule_for_llm

`Vital signs` stays as ONE KRI but the rule lists its components:

```
SOURCE: The Vital signs record at the V3 visit, per subject. Required measurements: blood pressure (systolic + diastolic), heart rate, body temperature, weight (kg).
CHECK: Vital signs (BP, HR, temperature, weight) were measured and recorded at V3.
DEVIATION: Record is missing, undated, or missing any of BP, HR, temperature, weight.
```

**Dosing-visit variant — pre/post-dose timepoints (Footnote-5 pattern):**

When the protocol's vital-signs footnote requires two timepoints at dosing visits (typically pre-dose + ~15 min post-dose), the rule must enforce **timepoint count**, not just record existence. A single row at the visit_label satisfies the naive rule but misses the post-dose set.

```
SOURCE: <vitals_table> rows at the V<N> (dosing visit) visit, per subject; required components <list>; each row's timepoint identified by exam_time.
CHECK: At V<N>, <vitals_table> has AT LEAST TWO rows with the same visit_label and DISTINCT exam_time values (per protocol footnote: pre-dose + ~15 min post-dose). Each timepoint set has all required components non-null.
DEVIATION: Fewer than 2 distinct-exam_time rows at the dosing visit, OR any required component null in either set.
```

If the protocol has a body-temp-from-AE-solicitation carve-out (e.g. footnote allowing post-dose body temp to come from a solicited-AE table), state the carve-out in SOURCE.

---

## CRITICAL — Citation & quote format: topic-bound, multi-footnote

### Combine all applicable footnotes for a KRI

Multiple footnotes apply when:
- **Visit-column footnote** (e.g., `Screening¹`) — applies to every procedure at SCR
- **Procedure-row footnote** (e.g., `Blood chemistry...¹²`) — applies to every visit of that procedure
- **X-cell footnote** (e.g., `X⁴`) — applies to that specific cell only

All applicable footnotes cited in `combined_ref`:
```
Schedule of Activities, Footnote 1, Footnote 6, p.40-p.50 — "quote from F1, topic-bound", "quote from F6, topic-bound"
```

### Topic-bind each quote

When a footnote covers multiple topics:
- Each KRI gets ONLY the sentence(s) about its specific procedure × visit
- If a footnote's content doesn't apply to the KRI, do NOT cite it (e.g., ESR/CRP should not cite a Blood chemistry/Hematology parameter-list footnote unless that footnote also contains ESR/CRP-specific text)
- NEVER copy an entire multi-topic footnote into a single-topic KRI

### Citation format catalog

| KRI type | `combined_ref` |
|---|---|
| Procedure × visit with footnote | `Schedule of Activities, Footnote N, [Footnote M, ...], p.X-p.Y — "<quote1>", "<quote2>"` |
| Procedure × visit no footnote | `Schedule of Activities, p.X-p.Y — "<procedure name>"` |
| Check-in with window footnote | `Schedule of Activities, Footnote N, p.X-p.Y — "<window footnote quote>"` |
| Check-in Day-1 same-day | `Schedule of Activities, Day 1 row, p.X-p.Y — "<contextual note>"` |
| Cross-visit / narrative | `Section N.N, Page Y: "<quote>"` |

**Page range** = actual Camelot table pages (`soa_table.json.pages`), NOT the broader manifest section range.

**Footnote ordering** in the reference: numeric ascending (`Footnote 1, Footnote 6`).

---

## CRITICAL — Description, Rule for LLM, Reference, Severity coherence

All four fields must be coherent. The Description's specific items (analytes, windows, conditions) must match the Rule for LLM's CHECK/DEVIATION. The Reference quote must be the exact source of specifics in the Rule for LLM. Severity must match rule gravity.

Implementation: `coherence_check.py` runs post-generation and flags KRIs where Description ↔ Rule ↔ Reference ↔ Severity are inconsistent.

---

## CRITICAL — Ordering: PROCEDURE-MAJOR

KRIs are laid out procedure-by-procedure, with all visits of that procedure together, before moving to the next procedure. Sequential KRI IDs reflect this order. Check-in KRIs come at the end, grouped together. Cross-visit / narrative rules come after check-ins.

Example:
```
SOA-SCR-001     SCR - Informed consent
SOA-SCR-002     SCR - Eligibility assessment
SOA-D1_PRE-003  D1_PRE - Eligibility assessment       ← same procedure, next visit
SOA-SCR-004     SCR - Demographic
...
SOA-SCR-008     SCR - Prior and concomitant medications
SOA-D1_PRE-009  D1_PRE - Prior and concomitant medications
SOA-D1_POST-010 D1_POST - Prior and concomitant medications
SOA-V2-011      V2 - Prior and concomitant medications
...
SOA-CHECKIN-SCR-001  SCR - Check-in within window
...
SOA-CROSS-001
SOA-ORPHAN-FOOTNOTE-001
```

---

## Pipeline — 21 steps

```
PHASE 1 — Discover
  Step 1 — Manifest (cover + TOC pages, LLM)
  Step 2 — Camelot SoA table extraction (deterministic, with multi-row header)
  Step 3 — Vision fallback (superscript recovery)
  Step 4 — Column boundary verification
  Step 5 — SoA ontology + cross-visit rules (LLM)
  Step 6 — Deterministic footnote mapper
  Step 7 — Atomic Normalization (1D — visit + procedure decomp, footnote-driven test decomposition, conditionality, topic-bound footnotes)
  Step 8 — Alias / Canonical Name Map

PHASE 2 — Extract
  Step 9 — Deterministic SOA generator (atomic grid → KRIs with SOURCE/CHECK/DEVIATION)
  Step 10 — SOA-text narrative LLM panel (cross-visit / methodology / long-term rules)
  Step 11 — Section Obligation Inventory (safety net)
  Step 12 — Auto-judgment (4-layer + 6-judge panel) — applied to ALL SOA KRIs

PHASE 3 — Validate
  Step 13 — Protocol-wide orphan scan (6-agent panel, BLOCKING)
  Step 14 — Completeness gate (atomic-unit coverage: every grid X-mark → a rule, + LLM ontology check)
  Step 15 — Clinical heuristics H1–H10
  Step 16 — Full accuracy judging (5-judge × 6 checks, BLOCKING)
  Step 17 — Consistency check
  Step 18 — Full verbatim verification (deterministic, page-range aware, BLOCKING)

PHASE 4 — Assemble
  Step 19 — Assembly (JSON + Excel, procedure-major)
  Step 20 — Intra-SOA dedup (priority hierarchy + Cross-Section Merge Guard + alias-map semantic)
  Step 21 — Flagged-review consolidated table
```
> Non-binary / non-verifiable rules are NOT segregated by this skill — the downstream golden-set-binary-rule-distiller's binary filter drops them.

See `references/steps.md` for detailed prompts and per-step logic.

---

## Step 12 — Auto-judgment (the major upgrade for SOA)

**This skill applies Step 12 to EVERY SOA KRI, including deterministic atomic-grid KRIs.** The parent skill skipped Step 2.6 for SOA (T1 auto-keep). The new skill forces SOA KRIs through the 4-layer decision table.

**4-layer engine:**

| Layer | What it checks |
|---|---|
| **L1 Verification gate** | Verbatim `supporting_quote` substring on cited page **range** (all pages, not just first). Binary `rule_for_llm`. Reference parses to real pages. |
| **L1.5 Atomicity** | Always-true / illustrative / pure-definition rejection. |
| **L2 Coverage/dedup** | Already covered by an approved peer? |
| **L3 6-judge neutral panel** | 3 Claude + 3 Gemini independently vote accept/reject/conditional. |
| **L4 Aggregate** | ≥5 accept → auto_approve. ≥5 reject → auto_reject. Else → flag. |

---

## Step 16 — Accuracy judging (5-judge × 6 checks)

**Panel:** 3 Claude Sonnet judges + 2 Gemini 2.5 Pro judges per KRI.

**Per-KRI input to each judge:**
- KRI record (all 13 fields)
- Full text of cited page(s) + 1 page before and after
- For SOA KRIs with footnote reference: full footnote text

**The 6 checks (C1–C6):**

| Check | What it verifies |
|---|---|
| **C1 — Faithfulness** | `rule_for_llm` says what protocol says, nothing more / less. No softening, no generalization. |
| **C2 — Specific values** | Every threshold, drug, dose, timing window, analyte, visit number, day count, percentage, unit matches the protocol exactly. |
| **C3 — Reference accuracy** | Cited page is ABOUT the clinical topic (semantic check). For SOA footnoted KRIs: `supporting_quote` MUST come from the cited footnote — if cited Footnote 12 but quote is from Footnote 13, FAIL. |
| **C4 — Completeness** | No critical detail the protocol specifies is missing. |
| **C5 — Scope accuracy** | Visit / population / time-point scope matches protocol intent. |
| **C6 — Atomicity** | KRI encodes exactly ONE binary obligation about ONE procedure at ONE visit with at most one condition. Compound KRIs FAIL. Auto-correction = split into N atomic KRIs and re-judge each. |

**Consensus:**
- 5/5 CORRECT → PASS
- 4/5 CORRECT + 1 dissent → PASS (logged)
- 3/5 CORRECT + 2 non-CORRECT → FLAG (user decision)
- ≤2/5 → FAIL (blocking)

---

## Step 19 — Cross-domain route-out (S5)

Before assembly, `cross_domain_router.py` flags SOA-surfaced rules whose content is really a **medication restriction, washout, prior-exposure, or stopping / treatment-discontinuation** rule, removes them from the SOA golden set, and writes them to **`routed_to_core.json`** with a `suggested_domain` (washout / prior-exposure → ELIG; restriction / stopping → SAF) for the Core extractor to ingest. The aim: SOA holds only visit-anchored assessments; the same restriction never lives in both SOA and SAF/ELIG.

**Conservative — no LLM, default keep:**
- Only **non-visit-anchored** KRIs are candidates (`SOA-CROSS-*`, `SOA-ORPHAN-FOOTNOTE-*`). Per-visit grid / check-in KRIs are **always kept** — including a *visit-anchored* washout like `V1 - Analgesic washout before Day 0 pain assessment` and the per-visit `Concomitant medications` **recording** activity.
- A candidate is routed only on a clear restriction / washout / prior-exposure / stopping signal; otherwise it stays in SOA.

---

## Step 20 — Intra-SOA dedup

**Priority hierarchy (highest → lowest):**

| Origin | Priority |
|---|---|
| SOA-table (atomic-grid derived) | 100 — never deleted |
| SOA-CHECKIN | 90 |
| SOA-CROSS (cross-visit from ontology) | 80 |
| SOA-TEXT (narrative-only) | 70 |
| SOA-ORPHAN-FOOTNOTE | 60 |

**Cross-Section Merge Guard:** KRIs from different numbered `§` sections NEVER merged.

**Semantic equivalence via `alias_map`:** KRIs whose only difference is a visit-alias (`W4` vs `Day 28`) or procedure-alias (`Vital signs` vs `BP+HR+temperature panel`) are recognized as the same atomic check. Conservative threshold: same procedure + same visit + same condition + same threshold.

**Default when in doubt:** KEEP BOTH and log under `kept_despite_similarity`.

**Atomization is NOT duplication:** atomic splits of a compound rule are correct output, never merged back.

---

## Quality rules (every KRI must satisfy)

1. **Faithfulness:** Use exact drug names, doses, thresholds, timing windows from the protocol. Never generalize.
2. **Lab panels:** Include all analytes from the protocol footnote — never just `"biochemistry panel"`. Long-format lab tables often store the same analyte under multiple `lab_parameter` strings with varying unit suffixes (e.g. `CRP (mg/dL)`, `CRP (mg/L)`, `CRP ()`). Either enumerate all known variants in the IN-clause inside SOURCE, or specify in CHECK that matching is unit-suffix-insensitive (match the analyte root, strip trailing parentheticals).
3. **Vitals position:** Use the exact position wording the protocol uses.
4. **Visit prefix:** Every SOA `rule_for_llm` starts with visit code: `V1-`, `S2-`, `SCR-`, `D1_PRE-`, `D1_POST-`, `All visits-`.
5. **No hallucination:** Every KRI must cite a real section + page.
6. **Visit window check-in KRI (MANDATORY):** Every atomic visit MUST have a dedicated check-in KRI as its FIRST KRI for that visit.
7. **Table is truth:** The SoA table (via Camelot CSV) is the single source of truth for which procedures occur at which visits. Footnotes can ADD context (enrichment) but cannot OVERRIDE the table's X marks. Step 14's deterministic `check_grid_coverage` enforces this both ways: every atomic-grid X-mark (procedure × visit) MUST map to a rule, and any X-mark with no matching rule is flagged in `gaps_report.json`.
8. **No outer quotes in `supporting_quote`:** Never begin or end with `"`.
9. **No duplicate page numbers:** Never produce `"p.27, p.27"` or `"Page 27, p.27"`.
10. **No footnote number prefix in quotes:** Strip leading footnote-number markers.
11. **Script safety:** Every script that modifies JSON must (a) create a backup, (b) `json.dump(..., ensure_ascii=False)`, (c) print confirmation with record count.
12. **Footnote associations are deterministic:** They come from `footnote_map.json` (Step 6), NEVER from LLM inference.
13. **Quote anchoring — one obligation per quote.**
14. **Discard traceability:** Every discarded KRI must have a non-empty `reason` field.
15. **`rule_for_llm` must be binary and machine-readable**: unambiguous, specifies WHAT to check, WHEN, HOW, in relation to WHAT protocol requirement.
16. **3-line SOURCE/CHECK/DEVIATION format is MANDATORY** for `rule_for_llm`.
17. **Footnote details embedded in rule_for_llm** when the footnote provides parameter / analyte / measurement / methodology specifics.
18. **Bundle component lists** in `rule_for_llm` for recognized standardized bundles.
19. **Procedure-major ordering** in the assembled output.
20. **Per-cell timestamps are typically absent**: source tables in the timepoint-columns shape (procedural variant) usually carry only a row-level `available_at` or `exam_date`; the individual `<field>_pre / _mid / _post` cells are not time-stamped. Do NOT write CHECK clauses that require a cell to be populated "after" another timestamp (e.g. "the post-cell must be populated after iv_end_time"). The cell-populated condition is the testable evidence per protocol design; the temporal check is unverifiable and produces silent `insufficient_data`.
21. **Investigator-judgment conditionals**: When the SoA item is gated on investigator clinical judgment ("only if deemed necessary"), the judgment itself is not captured in EDC. Two valid choices: (a) bind the rule to a proxy gate that IS in EDC (e.g. "if an AE was filed at or near this visit") and encode the proxy in CHECK; OR (b) flag the rule as untestable and skip it. Do NOT write the rule as absolute — it produces noise on every subject for whom the judgment conditional didn't trigger.
22. **Severity calibration — clinical vs data-quality omissions**: Distinguish two failure modes in DEVIATION wording. (1) Clinical assessment omission (whole record missing, procedure not performed) → assign protocol-driven severity (often `major`). (2) Data-quality omission (record present but date null, units inconsistent across visits, sub-field skipped while main field is captured) → typically `minor` — the procedure happened, the EDC entry was sloppy. When the rule could trigger on both modes, prefer two KRIs (one per severity) over a mixed-severity rule. Per-visit lab and assessment rules are the most common offenders.
23. **Name the source table explicitly in SOURCE**: SOURCE must reference exact source-table names (e.g. `raw_vital`, `raw_solicited_ae`, `micro_culture_results`), not narrative paraphrases ("the vital-signs record", "the solicited-AE assessment"). Exact names enable downstream wiring verification and prevent the downstream LLM from guessing the source.
24. **Procedure name = procedure only (no visit window, no other-visit clause)**: A procedure/test/assessment KRI's `kri_name` is `<visit_code> - <procedure>` only. NEVER embed the visit's allowable window (`(Day X-Y)`, `(Week N)`, `± N days`, `bi-weekly schedule`) or a clause that belongs to a different visit. The visit window lives in that visit's **check-in** KRI (whose name IS `<visit_label> - <window> - Check-in`); the procedure's own footnote-defined timing (e.g. "may be drawn up to 4 days before the visit") stays in the rule body, not the name. `soa_generator` strips any visit-window pattern deterministically (`_strip_visit_window`) from the procedure name and its other display fields (description, supporting quote, rule body), while keeping the raw label for bundle/severity/enrichment lookups. Wrong-visit clauses that survive in the rule body are out of scope for the name and are cleaned downstream by the Distiller (D6).

---

## How to run

### Setup (first time only)

```bash
pip install pdfplumber pymupdf camelot-py[cv] opencv-python-headless openpyxl anthropic --break-system-packages -q
```

### Inputs

- Protocol PDF file path
- Output directory (will be created)

**Canonical run directory:** `~/Downloads/extractor/<protocol_id>/<run_id>/`

### Full pipeline command

```bash
python scripts/run.py \
  --pdf /path/to/protocol.pdf \
  --out /path/to/output/ \
  [--auto-approve-unanimous|--interactive]
```

**Step order** (enforced by `run.py`):
`1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22`

**Blocking gates:** Step 13 (orphan scan), Step 16 (accuracy), Step 18 (verbatim).

---

## Output artifacts

| File | Source |
|---|---|
| `manifest.json` | Step 1 |
| `soa_table.csv`, `soa_table.json` | Step 2 |
| `vision_SOA_table.json` | Step 3 |
| `column_detection.json` | Step 4 |
| `ontology.json` | Step 5 |
| `footnote_map.json` | Step 6 |
| `soa_atomic_grid.json` | Step 7 |
| `alias_map.json` | Step 8 |
| `raw_SOA.json` | Steps 9 + 10 |
| `SOA_obligation_inventory.json` | Step 11 |
| `SOA_autojudgment_report.json`, `SOA_manual_review_decisions.json`, `SOA_tier3_filtered.json` | Step 12 |
| `orphan_scan_report.json` | Step 13 |
| `gaps_report.json` | Step 14 |
| `heuristics_report.json` | Step 15 |
| `accuracy_report_full.json` | Step 16 |
| `consistency_report.json` | Step 17 |
| `verify_report.json` | Step 18 |
| `soa_golden_set.json`, `soa_golden_set.xlsx` | Step 19 |
| `routed_to_core.json` | Step 19 (S5 cross-domain route-out) |
| `dedup_report.json` | Step 20 |
| `flagged_review_decisions.json` | Step 21 |

---

## Reference files

- `references/steps.md` — detailed per-step prompt templates and logic
- `references/kri_examples.md` — annotated SOA KRI examples by type
- `scripts/run.py` — orchestrator (canonical entry point)
- `scripts/camelot_table_extractor.py` — Step 2 (with multi-row header fix)
- `scripts/footnote_mapper.py` — Step 6 (section-header filter, regex for both `1. text` and `1 text` formats)
- `scripts/atomic_normalizer.py` — Step 7
- `scripts/alias_map_builder.py` — Step 8
- `scripts/soa_generator.py` — Step 9 (the deterministic SOA generator with SOURCE/CHECK/DEVIATION)
- `scripts/footnote_enrichment_parser.py` — extracts analyte / parameter / measurement lists from footnote text
- `scripts/severity_rubric.py` — applies severity rubric (critical / major / minor)
- `scripts/coherence_check.py` — flags Description ↔ Rule ↔ Reference ↔ Severity mismatches
- `scripts/bundle_component_table.py` — recognized-bundle component map
- `scripts/step3_5_orphan_scan.py` — Step 13
- `scripts/step3b_accuracy.py` — Step 16 (5-judge × 6 checks C1-C6)
- `scripts/step3d_verify.py` — Step 18 (page-range aware)
- `scripts/cross_domain_router.py` — Step 19 (S5 cross-domain route-out)
- `scripts/step4a_dedup.py` — Step 20 (intra-SOA priority)
- `scripts/sync-to-cache.sh` — sync source → plugin cache
