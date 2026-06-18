# Steps Reference — soa-kri-extractor

Detailed per-step prompt templates and logic. See `SKILL.md` for the canonical specification.

## Pipeline overview

```
PHASE 1 — Discover
  Step 1   Manifest                         (LLM, cover + TOC)
  Step 2   Camelot SoA table                (deterministic, multi-row header)
  Step 3   Vision fallback                  (vision, conditional)
  Step 4   Column boundary verification     (deterministic)
  Step 5   SoA ontology + cross-visit rules (LLM)
  Step 6   Deterministic footnote mapper    (ZERO LLM)
  Step 7   Atomic Normalization             (deterministic + LLM: umbrella test split + low-confidence binding)
  Step 8   Alias / Canonical Name Map       (deterministic + LLM body-text scan)

PHASE 2 — Extract
  Step 9   Deterministic SOA generator      (ZERO LLM, atomic-grid → KRIs)
  Step 10  SOA-text narrative LLM panel     (LLM, 12 sub-area turns)
  Step 11  Section Obligation Inventory     (LLM safety net)
  Step 12  Auto-judgment (4-layer + 6-judge)(LLM panel, all SOA KRIs)

PHASE 3 — Validate
  Step 13  Protocol-wide orphan scan        (6-agent LLM panel — BLOCKING)
  Step 14  Completeness gate                (deterministic)
  Step 15  Clinical heuristics H1–H10       (deterministic)
  Step 16  Full accuracy judging (5-judge × 6 checks)  (LLM — BLOCKING)
  Step 17  Consistency check                (deterministic)
  Step 18  Verbatim verification            (deterministic — BLOCKING)

PHASE 4 — Assemble
  Step 19  Assembly                         (deterministic, procedure-major order)
  Step 20  Intra-SOA dedup                  (deterministic, with alias-map semantic)
  Step 21  NDEF sweep                       (6-judge LLM panel)
  Step 22  Flagged-review consolidated table (deterministic)
```

## Step 7 — Atomic Normalization: footnote-driven test decomposition (1D-ii-b)

Runs inside `atomic_normalizer.normalize()` **after** the deterministic row-label split
(1D-ii) and **before** the per-cell unit emission. Purpose: split an *umbrella* row —
a single procedure row whose label is a generic category (e.g. `"Laboratory tests"`,
`"Safety labs"`, `"Blood tests"`) but whose **footnotes name ≥2 distinct tests** — into
one procedure per named test, so each becomes its own atomic KRI per marked visit.

**Gate (deterministic, zero-cost):** only consider a row when (a) the row was NOT already
split by 1D-ii (single label), (b) the label is not a recognized bundle, and (c) the label
matches the generic-umbrella pattern. This keeps the LLM call off the vast majority of rows.

**Decision (LLM-assisted — option A):** for a gated row, pass the row label + its numbered
footnote texts to the model, which returns the distinct named tests literally enumerated in
those footnotes, each tagged with the footnote(s) that define it, plus the shared
timing/acceptability footnotes that apply to all of them. If the footnotes name fewer than 2
distinct tests (e.g. they only list the analytes of one test), the row stays whole.

Prompt:

```
You are normalizing a clinical-trial Schedule of Activities row.

Row label: "{proc_name}"
Footnotes attached to this row:
{numbered_footnote_texts}

A row is an UMBRELLA when its label is a generic category (e.g. "laboratory tests",
"safety labs", "blood tests") and its footnotes enumerate TWO OR MORE DISTINCT named
tests/panels (e.g. a biochemistry panel, a blood count, a coagulation panel).

Return STRICT JSON only:
{
  "is_umbrella": true|false,
  "tests": [ {"test_name": "<distinct named test>", "component_footnotes": [<int>, ...]} ],
  "shared_footnotes": [<int>, ...]   // timing / acceptability footnotes applying to ALL tests
}

Rules:
- "tests" must have >=2 entries, else set is_umbrella=false and tests=[].
- Use the test names exactly as the footnotes/label name them; do NOT invent tests.
- A footnote that only lists the analytes of ONE test is NOT an umbrella → is_umbrella=false.
- component_footnotes = the footnote(s) that define that test's analytes/components.
- shared_footnotes = timing/window/acceptability notes that are not specific to one test.
```

**Effect on units:** when `is_umbrella` is true, the row's `atomic_procs` is replaced by the
returned `test_name`s; each child carries `footnote_numbers = component_footnotes +
shared_footnotes` so 1D-iv topic-binding and Step 9 enrichment cite only that test's slice and
enumerate only that test's analytes. The split is recorded under `umbrella_rows_split`. When no
API client is available the pass is skipped (row left whole) and the row is added to
`review_queue` with reason `"possible umbrella lab row — LLM enumeration unavailable"`.

## Step 9 — SOA generator: the 3-line rule_for_llm

The deterministic SOA generator emits one KRI per atomic unit. The `rule_for_llm` field MUST be 3 lines:

```
SOURCE: The <procedure> record at the <visit_display> visit, per subject. Required <items>: <list>.
CHECK: <procedure> was performed and dated at <visit_display> per the Schedule of Activities AND the record contains values for all N required <items>: <list>. Methodology: <m>. Timing: <t>.
DEVIATION: For an active subject expected at <visit_display>, no <procedure> record exists, the record is undated, OR any of the N required <items> is missing. OR methodology requirements (<m>) were not met.
```

Sources of the `<items>` list:
1. `footnote_enrichment_parser.parse_enrichment()` extracts analyte / parameter lists from the topic-bound footnote fragment (Step 7 1D-iv).
2. `bundle_component_table.get_bundle_components()` provides component lists for recognized bundles (Vital signs → BP, HR, temp; CBC → RBC, HGB, ...).

`parse_enrichment()` also captures **named drugs/agents** when a footnote frames them with a permitted / prohibited / rescue cue (e.g. `"patients may use acetaminophen and/or metamizole (dipyrone)"`). These are surfaced in the SOURCE line only (one labeled clause) so the drug names are not lost; the rule wording is left light because the Distiller re-authors it.

## Step 12 — Auto-judgment 6-judge panel prompt

```
You are a CRA reviewing whether this proposed KRI should be included in the
SOA Golden Set.

KRI under review:
{kri_record_json}

Protocol page context (cited page + 1 page before/after):
{page_context}

Footnote text (if cited):
{footnote_text}

Vote: ACCEPT | REJECT | CONDITIONAL
Reason: ≤25 words. Reject if:
  - Rule is not binary or machine-checkable
  - Quote is not verbatim from the cited page
  - Reference is wrong section or wrong footnote
  - KRI is non-atomic (compound rule — multiple procedures or multiple visits)
  - KRI duplicates an already-approved KRI
  - Required items / analytes are missing from the rule when the footnote specifies them

Return JSON: {"vote": "ACCEPT|REJECT|CONDITIONAL", "reason": "..."}
```

Aggregate (Layer 4):
- ≥5 accept (≤1 reject) → `auto_approve`
- ≥5 reject (≤1 accept) → `auto_reject`
- Otherwise → `flag`

## Step 16 — Accuracy judging C1–C6 prompt

```
You are judging clinical SOA KRIs for accuracy against the protocol.

PROTOCOL PAGE CONTEXT (cited page + 1 page before/after):
{page_context}

FOOTNOTE TEXT (if cited):
{footnote_text}

KRI TO JUDGE:
{kri_record_json}

Run all 6 independent checks and return a verdict.

THE 6 CHECKS (every check must pass for CORRECT):
- C1 Faithfulness: rule_for_llm says what protocol says, nothing more / less.
- C2 Specific Values: every threshold, drug, dose, timing window, analyte,
     visit number, day count, percentage, unit matches the protocol exactly.
- C3 Reference Accuracy: the cited section + page is ABOUT the clinical topic
     of this KRI (semantic). For SOA footnoted KRIs, supporting_quote MUST come
     from the cited Footnote — if cited Footnote 12 but quote is from Footnote 13,
     C3 FAILS.
- C4 Completeness: no critical detail the protocol specifies is missing.
- C5 Scope Accuracy: visit / population / time-point scope matches protocol intent.
- C6 Atomicity: KRI encodes exactly ONE binary obligation about ONE procedure
     at ONE visit. Compound KRIs FAIL C6 — set "atomic_split_proposal" to the
     N atomic KRIs it should split into.

Return JSON:
{
  "verdict": "CORRECT | IMPRECISE | WRONG",
  "failing_checks": ["C2", "C4"],
  "issue": "specific problem or null",
  "corrected_rule": "corrected rule_for_llm text or null",
  "atomic_split_proposal": null | [{kri_name, rule_for_llm, supporting_quote}, ...],
  "protocol_evidence": "verbatim ≤25-word quote from cited page proving verdict"
}
```

## Step 10 — SOA-text narrative LLM panel (12 sub-area turns)

The panel scans protocol body text (excluding SoA pages already handled in Phase 1) for rules that don't fit the table. 12 sub-areas:

1. Drug-administration timing & separations (§5/§7 narrative)
2. Study-wide duration & schedule meta-rules (§3/§4)
3. Cross-visit procedure methodology (§6)
4. Long-term follow-up obligations (§9/§10)
5. Global visit windows & tolerances
6. Sample & volume caps
7. **Permitted concomitant-medication windows** (NEW — ENX-style SOA-144)
8. **Measurement methodology rules** (posture, rest, recall periods)
9. **Treatment delay / discontinuation triggers**
10. **Long-term AE tracking + post-study follow-up windows**
11. **Consent expiration / re-consent rules**
12. **Lost-to-follow-up contact mandates**

Each sub-area prompt:

```
You are scanning protocol body text for a SPECIFIC class of SOA-domain rules:
{sub_area_description}

Protocol body pages (excluding SoA table pages):
{body_text}

Extract every rule of this class as a KRI in this exact format:
{
  "kri_id": "SOA-TEXT-{NNN}",
  "kri_name": "<short descriptive name>",
  "description": "1-3 sentences",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: ...\nCHECK: ...\nDEVIATION: ...",
  "protocol_reference": "Section N.N, Page Y",
  "supporting_quote": "verbatim ≤30 words",
  "additional_footnotes": null,
  "severity": "critical|major|minor",
  "deviation_level": "subject|visit|site|study"
}

Scope rules (MANDATORY):
1. Do NOT extract "procedure X at visit Y" KRIs — those come from the table.
2. Do NOT extract footnote rules that attach to specific table cells.
3. Only emit narrative / cross-visit / protocol-wide rules.

Return a JSON array. No markdown fences, no prose.
```

## Step 13 — Protocol-wide orphan scan prompt

For each section in the manifest's SoA-relevant section_map + neighboring narrative sections, dispatch to a 6-agent panel (3 Claude + 3 Gemini):

```
Section: {section_number} {section_title}, pages {page_range}
Existing KRIs covering these pages: {kri_list_compact}

Scan this section for rule-like statements (obligations, thresholds, prohibitions,
requirements, schedules, procedures, criteria, timings, methods) that are NOT
captured by any existing KRI listed above.

For zero-KRI sections, apply MAXIMUM recall — every rule-like statement is very
likely an orphan. Do not self-filter.

Return JSON array of candidates:
[
  {
    "candidate_text": "verbatim rule statement",
    "page": <int>,
    "surrounding_context": "≤50 words",
    "proposed_domain": "SOA",
    "proposed_subcategory": "CHECKIN | CROSS | TEXT | ORPHAN-FOOTNOTE | PROCEDURE"
  }, ...
]
```

Consolidation: ≥4/6 agents → HIGH (auto-promote); 2-3/6 → USER_DECISION; 1/6 → LOW (logged).

## Step 21 — NDEF sweep prompt

```
You are determining whether this KRI's rule_for_llm can produce a deterministic
YES/NO answer when applied to subject data.

KRI:
{kri_record_json}

Vote: DEFINABLE or NON_DEFINABLE.

NON_DEFINABLE if the rule involves:
  - Investigator judgment ("in the investigator's opinion", "if clinically significant")
  - Undefined time windows ("as soon as possible", "promptly", "in a timely manner")
  - Undefined effort / quantity ("reasonable effort", "adequate", "sufficient")
  - Subjective thresholds
  - Any non-binary wording

DEFINABLE if the rule has:
  - Numeric threshold or window
  - Named data field
  - Countable event
  - Yes/no observable condition

Return: {"vote": "DEFINABLE|NON_DEFINABLE", "reason": "≤20 words"}
```

6-agent panel (3 Claude + 3 Gemini). ≥5 NON_DEFINABLE → move to NDEF. 3-4 → user decision. 0-2 → keep in source.
