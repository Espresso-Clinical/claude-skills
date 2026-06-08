# Steps Reference — Protocol KRI Extractor

Detailed instructions and prompt templates for each pipeline step.
Claude uses these directly when running the pipeline.

---

## Shared constants

```python
DOMAIN_CATEGORIES = {
    "ELIG": "Eligibility — inclusion criteria, exclusion criteria, randomization criteria",
    "SAF":  "Safety & Toxicity — AE/SAE reporting, stopping rules, toxicity management, safety monitoring",
    "END":  "Endpoints & Statistics — objectives, efficacy endpoints, analysis sets, statistical methods",
    "OPS":  "Operations & Compliance — IMP handling, blinding, records retention, regulatory, GCP compliance",
}

# Schedule of Activities (SOA) is OUT OF SCOPE for this skill — handled by
# the separate `soa-kri-extractor` skill. Every extractor prompt below carries
# the SOA-exclusion methodology block.

SOA_EXCLUSION_BLOCK = """
## Out of scope — SOA (Schedule of Activities)

Schedule-of-Activities content is handled by the separate `soa-kri-extractor`
skill. It is OUT OF SCOPE for this extractor. Do NOT emit any KRI whose subject
is one of the following:

- "Procedure X is performed at visit Y" (any procedure × visit cell).
- "Visit X must occur within ±N days of [reference]" (visit windows / check-ins).
- Any rule that anchors an obligation to a specific visit code (V1, V2, SCR,
  EDC, EOS, Day 1, Week 4, etc.) and is essentially saying that something
  *happens* at that visit.
- Content from the SoA table itself, its footnotes, or the visit-schedule
  narrative section (drug-timing separations, cross-visit windows, "all visits
  must occur" rules, sample/volume caps tied to the visit schedule, long-term
  follow-up obligations defined by visit cadence).
- "Per SOA", "per the Schedule of Activities", "per the SoA table" or
  equivalent phrasings — these are SOA-flavored and out of scope.

If you encounter SOA-flavored content while extracting your assigned domain
section, SKIP it. Do not output a KRI for it. The orphan scan (Step 3.5) and
the cross-domain dedup (Step 4A-Dedup) carry the same exclusion and will
drop any SOA-flavored KRI that slips through.

This is NOT a judgment call. If a rule is essentially about *when* or *at
which visit* something occurs, it is SOA — out of scope. Other skills handle
it. Stay strictly within your assigned domain's content type.
"""

SYSTEM_PROMPT = """You are a clinical trial protocol expert and CRA (Clinical Research Associate).
You extract information from protocol documents with precision and faithfulness.
You always return valid JSON with no markdown fences, no prose, no extra text.""" + SOA_EXCLUSION_BLOCK
```

---

## Step 1A — Protocol Manifest

**Purpose**: Read cover + TOC pages, produce `manifest.json` with a COMPLETE `section_inventory` (every TOC section + a disposition — **never omitted**) plus a derived `section_map`.

**PDF pages to read**: Cover pages (1–3) + TOC pages.

**LLM prompt** (the authoritative prompt lives in `scripts/step1a_manifest.py`):
```
Read the following pages from a clinical trial protocol and extract the manifest.

[PROTOCOL PAGES]
{pages_text}
[END]

Return a JSON object:
{
  "protocol_id": "exact protocol number from cover",
  "study_name": "short study name/acronym or null",
  "sponsor": "sponsor name",
  "compound": "investigational product name",
  "indication": "therapeutic indication in 5 words or fewer",
  "phase": "e.g. IIb, III",
  "therapeutic_area": "cardiovascular|oncology|immunology|neurology|musculoskeletal|other",
  "total_pages": N,
  "toc_pages": [...],
  "section_inventory": [
    {
      "section_number": "e.g. 8.1, 12",
      "title": "section title exactly as it appears in the TOC",
      "pages_approx": [start_page, end_page],
      "disposition": "ELIG | SAF | END | OPS | out_of_scope_soa | non_substantive",
      "confidence": "high | low",
      "notes": "for low confidence / partial-or-multi-domain coverage, else null"
    }
  ]
}

Dispositions:
- ELIG / SAF / END / OPS — the 4 in-scope domains (Eligibility; Safety & Toxicity;
  Endpoints & Statistics; Operations & Compliance). Assign the single best-fit one.
- out_of_scope_soa — Schedule-of-Activities content (SoA table, its footnotes,
  visit-schedule narrative, "procedure × visit" cells). Handled by the separate
  `soa-kri-extractor` skill. It is STILL LISTED in section_inventory with this
  disposition — never omitted — but it is not mapped to a domain.
- non_substantive — ONLY genuinely rule-free sections (title page, table of
  contents, abbreviations/glossary, references, signature page).

COMPLETENESS IS MANDATORY — NEVER OMIT A SECTION. Every numbered section, sub-
section, and appendix in the TOC appears exactly once in section_inventory, each
with a disposition. There is no "drop it" option.

BEST-FIT, NOT PERFECT-FIT. An ambiguous or multi-domain section STILL gets its
single closest in-scope domain with "confidence":"low" and a note — never dropped,
never hidden under non_substantive. Conduct-governing sections (concomitant /
prohibited medications, dose modification, discontinuation/withdrawal, informed
consent, deviation handling, blinding) are ALWAYS in-scope (typically SAF or OPS).

Return ONLY the JSON object.
```

**Post-processing (deterministic, in `step1a_manifest.py`)**:
- **Page-range validation** — locate each section's body heading in the actual PDF and make ranges contiguous, so a short/wrong TOC estimate cannot cause an in-scope section's pages to be skipped by the extractor.
- **Derive `section_map`** (ELIG/SAF/END/OPS only) from `section_inventory`. `out_of_scope_soa` / `non_substantive` sections remain in the inventory but are NOT mapped (no extractor reads them). The Step 3A completeness gate audits every in-scope section in the inventory.

**Save output**: `{out_dir}/manifest.json`

---

## Step 2 — KRI Extraction (per category, single-model Gemini panel)

**Purpose**: Extract all KRIs for one domain category using competing models.

**PDF pages to read**: Pages from `manifest.section_map[CATEGORY]` entries.

**Single-model extraction process (Item 1):**

For each domain, run **10 Gemini 3.5 Flash agents (thinking-high) in parallel** — one single-model panel, no Claude sub-agents. Independence comes from a temperature spread across the 10 agents plus the multi-turn sub-area decomposition.

Agents use `run_gemini_extraction_multi_turn()` — a multi-turn chat method with the PDF uploaded via Gemini's Files API. Each of the 10 parallel agents runs a sequence of focused sub-area turns defined per domain, which forces exhaustive extraction within each sub-area (the prior single-shot pass self-limited).

```python
from gemini_extract import run_gemini_extraction_multi_turn, save_gemini_results

# Uses the default SUB_AREA_TURNS template for the domain (see below).
results = run_gemini_extraction_multi_turn(
    domain="{CATEGORY}",              # "ELIG", "SAF", "END", or "OPS"
    pdf_path="/path/to/protocol.pdf",
    n_agents=10,
)
save_gemini_results(results, out_dir, "{CATEGORY}")
```

**Why multi-turn with PDF (vs. the original single-shot text prompt)**:

On the original `run_gemini_extraction()` method, Gemini self-limits its output on large domain prompts, producing 13-16 KRIs on OPS (75KB prompt) vs. 60-82 with the multi-turn method. The root cause is NOT a token budget issue (thinking and output tokens are separate in Gemini 2.5+) — a single broad pass makes the model stop early, while the multi-turn method forces iteration across sub-areas.

The multi-turn method gives Gemini the same iteration capability: one chat session per agent, each with the PDF attached, stepping through the domain's sub-areas one turn at a time. The focused turns force exhaustive coverage within each sub-section instead of a single self-limiting pass.

**Per-domain sub-area turn templates** (defined in `gemini_extract.py::SUB_AREA_TURNS`):

| Domain | Turns | Coverage |
|--------|-------|----------|
| **ELIG** | 2 | 1) Inclusion criteria (§4.1), 2) Exclusion criteria (§4.2) |
| **SAF** | 5 | 1) AE/SAE reporting (§8), 2) Stopping rules & IP discontinuation (§9), 3) Solicited AEs & infusion monitoring, 4) DILI thresholds (Hy's law), 5) Causality & pregnancy |
| **END** | 5 | 1) Primary + key secondary endpoints, 2) Secondary clinical efficacy endpoints, 3) Biomarker/analyte endpoints, 4) Exploratory endpoints, 5) Governance (populations, sample size, DMC, interim analysis) |
| **OPS** | 6 | 1) IP Handling & Administration (§7), 2) Blinding & Unblinding, 3) Randomization & Study Design, 4) Procedure Methodology (§6), 5) Documentation & Regulatory, 6) Appendices |

**Scope**: This applies to Phase 2 domain extraction of ELIG / SAF / END / OPS. SOA is OUT OF SCOPE for this skill (handled by `soa-kri-extractor`). All Phase-2 extraction agents are Gemini 3.5 Flash (10 per domain).

**Backward compatibility**: The original `run_gemini_extraction()` (single-shot, inline text prompt, no PDF) remains available for non-Phase-2 uses — for example, Step 3B accuracy judging and Step 3.5 orphan scan, where a single-shot call is appropriate.

**Custom sub-area turns**: Callers can override the default template by passing `sub_area_turns=[(name, prompt), ...]` explicitly. This is useful for protocol-specific focus (e.g., adding a turn for a unique appendix) without modifying the skill defaults.

**Adjudication (after both sets complete) — consensus-based, per domain:**

Merge all 10 agent outputs (10 Gemini 3.5 Flash). For each unique KRI found across agents, count how many agents produced it (match by semantic similarity of `rule_for_llm`):

| Agent consensus | Action |
|---|---|
| **7–10 agents (T1)** found it | **Auto-approve** — goes directly into the domain's golden set |
| **4–6 agents (T2)** found it | **Step 2.6 auto-judgment** — 6-judge neutral panel (6 Gemini 3.5 Flash, thinking-high) pre-decides accept / reject / flag. In `--auto-approve-unanimous` mode (default ON), flagged items default to rejected at Phase 4 and surface in `flagged_review_decisions.json` (Step 4A-FlaggedReview) for end-of-run user review. In `--interactive` mode, pipeline pauses per-domain on flagged items. See the Step 2.6 section in SKILL.md for full spec. |
| **1–3 agents (T3)** found it | **Tier 3 promotion pipeline** (T3-1 Coverage / T3-2 Verbatim / T3-2.5 Atomicity / T3-3 Panel / T3-4 Aggregate — same 6-judge panel as T2). NOT auto-deleted. Dispositions recorded in `{domain}_tier3_filtered.json`. |

**Decision table format (shown to user for 4–6 agent KRIs):**

For each KRI in the 4–6 range, present:

```
┌──────────────┬─────────────────────────────────┬─────────────────────────────────────────┬───────────────────┬──────────┬──────────────────────────────┬──────────┐
│ KRI ID       │ KRI Name                        │ Description                             │ Agents            │ Verified │ Reference & Quote            │ Decision │
├──────────────┼─────────────────────────────────┼─────────────────────────────────────────┼───────────────────┼──────────┼──────────────────────────────┼──────────┤
│ SAF-AE-007   │ SAE Reporting 48h Window        │ Monitors SAE reporting within 48 hours  │ 5/10 (3C + 2G)   │ YES      │ Section 8.14, p.118 — "..."  │ ?        │
│ SAF-STOP-003 │ CK >10x ULN Stopping Rule      │ Monitors CK elevation stopping trigger  │ 4/10 (2C + 2G)   │ YES      │ Section 8.5, p.105 — "..."   │ ?        │
│ SAF-PREG-002 │ Male Partner Contraception      │ Monitors partner contraception require. │ 6/10 (4C + 2G)   │ NO       │ Section 4.1, p.55 — "..."    │ ?        │
└──────────────┴─────────────────────────────────┴─────────────────────────────────────────┴───────────────────┴──────────┴──────────────────────────────┴──────────┘
```

Where:
- **Agents**: total count + breakdown (e.g., "5/10" = 5 of the 10 Gemini agents)
- **Description**: 1-2 sentence description of what this KRI monitors and why it matters
- **Verified**: YES if the supporting quote was found verbatim on the cited protocol page via pdfplumber, NO otherwise
- **Reference & Quote**: the `combined_ref` field (protocol reference + verbatim quote)
- **Decision**: user fills in — approve or reject

**Process per domain:**
1. Run 10 agents → merge → apply consensus tiers
2. Present the 4–6 tier decision table to the user
3. **WAIT** for user approval/rejection on each row
4. Apply user decisions
5. Proceed to de-duplication within this domain
6. Only then move to the next domain

**Domain processing order**: ELIG → SAF → END → OPS (one at a time, user approval between each).

Save adjudication results in `{out_dir}/{cat}_adjudication.json`.

**KRI schema** (every KRI must match exactly):
```json
{
  "kri_id": "SAF-AE-001",
  "kri_name": "SAE reporting within 24h",
  "description": "1-2 sentences: what this monitors and why",
  "category_id": "SAF",
  "category_label": "Safety & Toxicity",
  "rule_for_llm": "Verify that [exact actionable check]",
  "protocol_reference": "Section 9.2, p.52",
  "supporting_quote": "Verbatim text from protocol — no outer quotes",
  "combined_ref": "Section 9.2, p.52 — \"Verbatim text from protocol\"",
  "additional_footnotes": "Footnote 10: verbatim text — or null",
  "severity": "critical|major|minor"
}
```

**Atomicity rule**: Every KRI must be atomic — ONE verifiable check about ONE thing at ONE time point. Never combine multiple endpoints, analytes, criteria, or time points into a single KRI.

**ID format by category**:
- ELIG: `ELIG-INC-{NNN}` and `ELIG-EXC-{NNN}`
- SAF: `SAF-AE-{NNN}`, `SAF-ALLERGY-{NNN}`, `SAF-PREG-{NNN}`, `SAF-RM-{NNN}`, `SAF-STOP-{NNN}`
- END: `END-PRI-{NNN}` (primary), `END-KSEC-{NNN}` (key secondary), `END-SEC-{NNN}` (other secondary), `END-BIO-{NNN}` (biomarker), `END-HCRU-{NNN}` (health care resource utilization), `END-EXP-{NNN}` (exploratory)
- GOV: `GOV-POP-{NNN}` (analysis populations), `GOV-INT-{NNN}` (interim analysis/alpha), `GOV-END-{NNN}` (study end), `GOV-DMC-{NNN}` (DMC rules)
- OPS: `OPS-IMP-{NNN}`, `OPS-BLIND-{NNN}`, `OPS-RECS-{NNN}`, `OPS-COMP-{NNN}`

### ELIG prompt

**ATOMICITY**: One criterion or sub-criterion = one KRI. Multi-part criteria (e.g. 14a-14k) must produce one KRI per letter.

**ATOMICITY — compound clauses (refinement)**: Split compound criteria ONLY when BOTH preconditions hold (see SKILL.md "Atomization of compound clauses" for full rules):
1. Each sub-condition can actually FAIL for some real subject (no always-true clauses like "male or female")
2. The list is a TRUE ENUMERATION (distinct testable conditions), NOT illustrative examples under an umbrella term

Quick examples:
- "NASH or HBsAg or HCV antibody or other liver disease" → 4 KRIs ✓ (true enumeration of distinct lab tests)
- "HBOT or CTP within 30 days" → 2 KRIs ✓ (two distinct interventions)
- "ALT or AST >3×ULN and/or bilirubin >1.5×ULN" → 3 KRIs ✓ (three distinct lab values)
- "Pregnant and/or breastfeeding" → 2 KRIs ✓ (two distinct states, each testable)
- "Males or females ≥18 to <85" → do NOT create a "sex" KRI ✗ (always TRUE — covers all humans); only age is verifiable content
- "any medication (such as BRMs, cancer immunomodulators, systemic steroids) causing immunosuppression" → ONE KRI ✗ (illustrative examples under umbrella "any medication that causes immunosuppression"; put examples in `description`)
- "surface area ≥1 cm² and ≤40 cm²" → ONE KRI ✗ (single data field `surface_area_cm2`, one range check)

Verifiability test: (a) can sub-KRI actually fail? (b) does it read a different data field than siblings? BOTH must be YES to split. When in doubt, keep combined.

```
Extract Eligibility KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES:
- One KRI per criterion or per meaningful sub-criterion (e.g. 5a, 5b → two KRIs)
- Inclusion rule_for_llm: "Verify that [requirement] is documented/confirmed"
- Exclusion rule_for_llm: "Verify the absence of [condition]" (preferred phrasing)
- Include exact numeric thresholds, timeframes, clinical terms verbatim
- Lab thresholds: list each parameter and exact threshold value
- Multi-part exclusion criteria (e.g. criterion 14a through 14k): one KRI per letter
- Timing in criteria: if a criterion specifies a timeframe (e.g. "symptoms ≥ 3 months",
  "X-ray within 6 months"), embed the timeframe directly in rule_for_llm — not only
  in additional_footnotes
- Investigator framing: if a criterion is framed as "Investigator-assessed" or
  "in the Investigator's judgment", preserve that framing in the rule

Return ONLY a JSON array
```

### SAF prompt

**ATOMICITY**: One reporting rule, one stopping rule, one emergency protocol = one KRI. Never combine AE reporting + SAE reporting into one KRI.

**ATOMICITY — compound clauses (refinement)**: Apply the refined compound-clause rule (SKILL.md "Atomization of compound clauses"). Split ONLY when BOTH preconditions hold: (1) each sub-condition can actually fail, (2) it's a true enumeration not illustrative examples. Do NOT split single-field ranges or always-true clauses. Examples: "ALT or AST >3×ULN or bilirubin >2×ULN" → 3 KRIs ✓ (each a distinct lab); solicited AE list (malaise, arthralgia, fever, chills, skin rash, anorexia, nausea, vomiting) → 8 KRIs ✓ (each a distinct named AE); "report SAE within 24h AND follow up within 30 days" → 2 KRIs ✓ (two distinct timeline obligations).

```
Extract Safety & Toxicity KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

══════════════════════════════════════════════════════════════════
MANDATORY — SAF DOMAIN BOUNDARY (read before extracting anything)
══════════════════════════════════════════════════════════════════
SAF contains ONLY rules about:
  ✓ Numeric safety thresholds and the required clinical response when exceeded
    (e.g. CK >5× ULN → stop IP; TG ≥600 mg/dL → unscheduled visit; AST/ALT ≥3× ULN → workup)
  ✓ AE/SAE collection windows and reporting timelines (report within 24h/48h to sponsor)
  ✓ IP stopping rules and dose discontinuation triggers
  ✓ Emergency/rescue protocols with exact drug names and doses
  ✓ Causality assessment requirements
  ✓ Pregnancy-related safety follow-up (EDP reporting, neonatal death, partner exposure)
  ✓ Dose modification rules and their triggers (e.g. IP frequency change after confirmed LDL-C)

SAF does NOT contain — do not extract these into SAF:
  ✗ "Procedure X was collected at Visit Y" → OUT OF SCOPE (soa-kri-extractor)
  ✗ Visit timing windows → OUT OF SCOPE (soa-kri-extractor)
  ✗ How to perform a measurement (position, technique, duration) → belongs in OPS
  ✗ Equipment standardization (same arm, same cuff) → belongs in OPS
  ✗ Sample tube type or processing steps → belongs in OPS
  ✗ IRT registration, record-keeping, IP storage → belongs in OPS

SELF-CHECK before adding each KRI: ask "Is this about a safety THRESHOLD or REPORTING OBLIGATION, 
or is it about WHEN/HOW something is done?" If when/how → do not add to SAF.
══════════════════════════════════════════════════════════════════

EXTRACTION RULES:
- Cover: AE/SAE collection windows, reporting timelines (24h, 48h), allergic reaction 
  management (exact drug names + doses), stopping rules, DSMB triggers, rescue medication 
  dose caps, pregnancy reporting, AESI definitions, post-injection observation period
- Include exact drug names and doses for emergency treatment protocols
- Include exact reporting timeframes
- Distinguish: pre-IMP conditions = medical history (not AE)
- Boundary rules: what is collected when (e.g. only SAEs beyond 6 months)
- Concomitant medication timing: prohibited medications with specific washout/exclusion
  windows (e.g. "IA corticosteroids prohibited within 3 months") should each get their
  own KRI with the exact timing

Return ONLY a JSON array
```

### END prompt (TWO sub-categories: Endpoints, Governance)

**IMPORTANT — Atomicity**: Every endpoint, every analyte, and every governance rule gets its own separate KRI. Never combine multiple endpoints or multiple analytes into one KRI. If the protocol lists 15 secondary endpoints, produce 15 KRIs. If it lists 13 biomarker analytes, produce 13 KRIs.

**ATOMICITY — compound clauses (refinement)**: Apply the refined compound-clause rule (SKILL.md "Atomization of compound clauses"). Split ONLY when BOTH preconditions hold: (1) each sub-condition can actually fail, (2) it's a true enumeration not illustrative examples. Do NOT split single-field ranges or always-true clauses. Example: "composite of CV death, MI, stroke, and UA" → 4 component KRIs + 1 composite-definition KRI (each component is a distinct testable event).

**Run the END extraction in TWO passes** to ensure complete coverage:

**Pass 1 — Endpoint Definitions (Sections 2.x / Objectives & Endpoints)**:
```
Extract Endpoint Definition KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES — ENDPOINT DEFINITIONS:
You MUST create ONE SEPARATE KRI for EACH endpoint listed in the protocol.
Do NOT combine multiple endpoints into one KRI. Do NOT summarize a list of endpoints.
Every single bullet point, every single analyte, every single composite definition = its own KRI.

- PRIMARY ENDPOINT: One KRI with exact composite definition, time-from-randomization language,
  and adjudication requirement. kri_id: END-PRI-001. severity: critical.

- KEY SECONDARY ENDPOINTS: One SEPARATE KRI per distinct key secondary endpoint.
  Each composite endpoint definition is separate. Even if they share a section header,
  decompose them into individual KRIs.
  kri_id: END-KSEC-001, END-KSEC-002, etc. severity: critical.

- OTHER SECONDARY / CLINICAL ENDPOINTS: One SEPARATE KRI per individual endpoint.
  Break out every item in the list: CV death, any MI (fatal+non-fatal), fatal MI,
  non-fatal MI, any stroke, fatal stroke, non-fatal stroke, hospitalization for UA,
  hospitalization for CHF, coronary revascularization, CABG, PCI, arterial
  revascularization, all-cause death — each one = one KRI.
  kri_id: END-SEC-001, END-SEC-002, etc. severity: major.

- BIOMARKER ENDPOINTS: One SEPARATE KRI per analyte × measurement type.
  If protocol says "percent change and nominal change in LDL-C at Week 14, and
  percent change to last available" → that is 3 KRIs for LDL-C alone.
  If protocol lists 13 analytes for percent change at Week 14 → 13 KRIs.
  Include the exact visit/week number and measurement method (e.g. "direct measurement").
  kri_id: END-BIO-001, END-BIO-002, etc. severity: major.

- HCRU (Health Care Resource Utilization) ENDPOINTS: One SEPARATE KRI per HCRU metric.
  All-cause hospitalizations, CV hospitalizations, ER visits, physician office visits,
  outpatient rehab visits, 30-day readmissions (all-cause and CV separately) — each = one KRI.
  Include the specific measures collected (diagnoses, length of stay, discharge disposition).
  kri_id: END-HCRU-001, END-HCRU-002, etc. severity: minor.

- EXPLORATORY ENDPOINTS: One SEPARATE KRI per exploratory endpoint if any.
  kri_id: END-EXP-001, etc. severity: minor.

Rule format: "Verify that [the endpoint] is [calculated/defined] as [exact definition from protocol]"
Every KRI rule must specify: what is measured, from when (e.g. "time from randomization"),
and the exact definition (e.g. "first adjudicated and confirmed occurrence of...").

Return ONLY a JSON array
```

**Pass 2 — Governance (Sections 9.x / Interim Analysis, Study Design)**:
```
Extract Governance KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

EXTRACTION RULES — GOVERNANCE:
One SEPARATE KRI per governance rule.

- ANALYSIS POPULATION DEFINITIONS: One SEPARATE KRI per analysis set.
  FAS/ITT: exact inclusion criteria (e.g. "all randomized subjects regardless of
  dose changes, adherence, or discontinuation"). severity: critical.
  SAS: exact inclusion criteria (e.g. "received at least one dose of randomized
  study medication"). severity: critical.
  Any other analysis sets (per-protocol, mITT, etc.): one KRI each.
  kri_id: GOV-POP-001, GOV-POP-002, etc.

- INTERIM ANALYSIS TRIGGER: Exact conditions that must be met simultaneously.
  Include event count thresholds (e.g. "75% of 508 subjects with primary endpoint event"),
  which endpoints must be met, AND conditions. severity: critical.
  kri_id: GOV-INT-001

- ALPHA SPENDING: Method name (e.g. Heybittle-Peto), exact alpha value (e.g. 0.001),
  adjustment to final analysis alpha (e.g. 0.00002). severity: critical.
  kri_id: GOV-INT-002

- STUDY END DEFINITION: Event count target, time-based criterion, whichever-occurs-later
  logic. severity: major.
  kri_id: GOV-END-001

- DMC REVIEW RULES: If protocol specifies DMC review triggers (e.g. all-cause death
  monitoring with Bonferroni adjustment), create a KRI. severity: major.
  kri_id: GOV-DMC-001

Rule format: "Verify that [population/trigger/rule] is [defined/performed] as [exact spec]"

Return ONLY a JSON array
```

### OPS prompt

**ATOMICITY**: One operational rule = one KRI. IMP storage, IMP handling, blinding, unblinding, retention — each is a separate KRI.

**ATOMICITY — compound clauses (refinement)**: Apply the refined compound-clause rule (SKILL.md "Atomization of compound clauses"). Split ONLY when BOTH preconditions hold: (1) each sub-condition can actually fail, (2) it's a true enumeration not illustrative examples under an umbrella term. Do NOT split single-field ranges or always-true clauses. Example: "IP stored at ≤-80°C and shipped on dry ice" → 2 KRIs (storage temperature and shipment condition are distinct verifiable facts).

```
Extract Operations & Compliance KRIs from this protocol section.
Protocol: {protocol_id}

PROTOCOL TEXT:
{section_text}

══════════════════════════════════════════════════════════════════
MANDATORY — OPS DOMAIN BOUNDARY (read before extracting anything)
══════════════════════════════════════════════════════════════════
OPS contains:
  ✓ How to perform assessments (measurement position, technique, duration)
    e.g. "BP measured sitting, arm supported at heart level, after 5 min rest"
    e.g. "Weight measured in indoor clothing without shoes"
    e.g. "Pulse rate measured manually at brachial/radial artery for ≥30 seconds"
  ✓ Longitudinal standardization (same arm, same cuff, same scale throughout study)
  ✓ IP storage, handling, dispensing, accountability (temperatures, qualified staff, destruction)
  ✓ Informed consent documentation, re-consent, surrogate consent
  ✓ CRF corrections, record retention, delegation of authority logs
  ✓ Regulatory compliance (IRB approvals, inspection notification, clinical holds)
  ✓ IP compliance assessment and run-in compliance thresholds
  ✓ Blinding procedures (one carton at a time, emergency unblinding documentation)
  ✓ Measurement methodology rules that describe HOW (not WHEN) a procedure is performed

OPS does NOT contain — do not extract these into OPS:
  ✗ Visit timing windows → OUT OF SCOPE (soa-kri-extractor)
  ✗ "Procedure X happens at Visit Y" → OUT OF SCOPE (soa-kri-extractor)
  ✗ IRT registration at visits → OUT OF SCOPE (soa-kri-extractor)
  ✗ Safety thresholds (CK >5× ULN, TG ≥600 mg/dL) → belongs in SAF
  ✗ AE/SAE reporting timelines → belongs in SAF

SELF-CHECK before adding each KRI: ask "Is this about HOW something is done (technique,
standardization, compliance), or is it about WHEN it's done (out of scope — soa-kri-extractor)
or WHAT threshold triggers a response (SAF)?" Only HOW rules belong in OPS.
══════════════════════════════════════════════════════════════════

EXTRACTION RULES:
- Cover: IMP storage conditions (exact temperatures), who handles IMP, who administers,
  blinding approach, unblinding documentation, record retention duration,
  eCRF requirements, participant withdrawal/replacement rules,
  regulatory approvals required, 21 CFR Part 11 compliance
- Include exact temperature ranges
- Include exact retention durations (years)
- Measurement methodology: include ALL standardized measurement technique rules
  (positioning, timing within visit, equipment requirements, longitudinal consistency rules)
- Central analyses: cover all central review requirements — imaging (X-ray, MRI),
  lab, ECG — including verification that data was transmitted to the central facility
  and results were reviewed centrally
- Data governance: include Investigator approval/sign-off of eCRF data, delegation
  of authority logs, and any regulatory sign-off requirements
- Participant rights: include ICF copy provision to participant, re-consent rules,
  and any participant notification requirements

Return ONLY a JSON array
```

**Save output**: `{out_dir}/raw_{CATEGORY}.json`

---

## Step 4A-Dedup — Cross-Domain + Intra-Domain Duplicate Detection (mandatory after Step 4A)

**Purpose**: After all 4 in-scope domains are assembled into `extracted_kris.json`, (a) delete any KRI that is SOA-flavored (last-line safety net for the prompt-level exclusion methodology) and (b) remove cross-domain and intra-domain duplicates.

**SOA-flavored safety net (FIRST, MANDATORY)**: Before any other dedup logic, scan every KRI in `extracted_kris.json`. If the rule is essentially "procedure happened at visit Y", "visit X within ±N days", "per the SoA table", or any other SOA-flavored pattern → delete with reason `"SOA-flavored — handled by soa-kri-extractor"` and log under `dedup_report.json.cross_domain` with `rule_type: "out_of_scope_soa"`. This is the final enforcement of Domain Boundary Rule 1.

**Cross-domain ownership hierarchy** (between the 4 in-scope domains; higher = wins, lower = deleted if same clinical check exists):
1. SAF — owns safety thresholds, reporting timelines, stopping rules
2. OPS — owns measurement technique and operational procedure rules
3. ELIG — owns inclusion / exclusion criteria
4. END — owns endpoint definitions and governance rules

**Semantic equivalence**: Within-domain dedup uses semantic matching (not literal string match). Conservative threshold: only flag as duplicate when the two KRIs check the same subject, with the same condition and same threshold values, in the same context. When in doubt, KEEP BOTH and log under `kept_despite_similarity`.

**Process**:

```python
# Pseudocode for Step 4A-Dedup
SOA_FLAGS = ("at visit", "per soa", "per schedule", "per the soa table",
             "within ±", "visit window", "visit timing")

# Pass 0 — SOA-flavored safety net
for kri in extracted_kris:
    rule = kri.rule_for_llm.lower()
    if any(flag in rule for flag in SOA_FLAGS):
        delete(kri, reason="SOA-flavored — handled by soa-kri-extractor",
               rule_type="out_of_scope_soa")

# Pass A — Cross-domain dedup (between the 4 in-scope domains)
for each pair (kri_a, kri_b) in (SAF, OPS, ELIG, END):
    if same atomic check AND different domains:
        keep the one in the owning domain per the hierarchy above
        delete the other, log under dedup_report.json.cross_domain

# Pass B — Intra-domain dedup
for each domain:
    for each pair of KRIs with semantically equivalent rule_for_llm:
        keep the one with the richer description and more specific protocol reference
        delete the other, log under dedup_report.json.intra_domain
```

**LLM prompt for cross-domain dedup review**:
```
You are reviewing assembled KRIs for cross-domain duplicates across the 4
in-scope domains (ELIG, SAF, END, OPS). SOA is OUT OF SCOPE for this skill
(handled by soa-kri-extractor). Any SOA-flavored KRI you encounter must be
deleted with reason "SOA-flavored — handled by soa-kri-extractor".

DOMAIN OWNERSHIP RULES:
- SAF owns: safety thresholds, AE/SAE reporting timelines, stopping rules, clinical responses
- OPS owns: measurement technique, IP handling, documentation procedures
- ELIG owns: inclusion / exclusion criteria
- END owns: endpoint definitions and governance rules

KRIs TO REVIEW:
{all_kris}

For each KRI, determine:
1. Is it SOA-flavored? → delete with reason "out_of_scope_soa"
2. Is it a duplicate of another KRI in a different in-scope domain? → keep the owner per the hierarchy
3. Is it a duplicate of another KRI in the same domain? → keep the richer one

Return JSON array of deletions:
[{"delete_id": "...", "duplicate_of": "...", "reason": "...", "rule_type": "out_of_scope_soa|cross_domain|intra_domain"}]
```

**Save**: `{out_dir}/dedup_report.json`

Apply all deletions, then re-save `extracted_kris.json` and regenerate the Excel workbook.

---

## Step 2.5 — Section Obligation Inventory (MANDATORY, runs after each domain extraction)

**Purpose**: After completing extraction for a domain (and before Step 2.6), build the **completeness yardstick** for that domain — a high-recall inventory of every conduct-constraining statement in its mapped sections. Step 3A measures coverage against this and blocks on gaps. Implemented in `scripts/step2_5_obligation_inventory.py`.

**Input**: Full text of all sections mapped to this domain (from `manifest.section_map`).

**Process**:

1. **Capture every conduct-constraining statement with MAXIMUM RECALL — NO obligation-marker pre-filter.** Do NOT restrict to "must / shall / prohibited / within-N". Capture equally: obligations and requirements (with or without "must"); **permissions and conditional permissions** ("permitted if the dosage is stable"); prohibitions; definitions and definitional boundaries; timing / window rules; thresholds and dose triggers; methods; governance / documentation rules; and sponsor- or investigator-decision conditionals. When in doubt, INCLUDE. Over-capture is correct — the user filters later, and a missed sentence becomes an undetectable coverage gap. (The marker-based pre-filter used by earlier versions is removed: it dropped real in-scope rules, e.g. permitted-therapy stability conditions phrased as permissions.) Mechanism: one high-recall LLM pass per mapped section.

2. **If one sentence carries several independent constraints** (e.g. "prohibited prior to AND during the study"), emit one entry per independent constraint.

3. **Save artifact**: `{out_dir}/{domain}_obligation_inventory.json` — schema `obligations: [{sentence, page, section, type, severity}]` (exactly what Step 3A reads).

```json
{
  "_meta": {"step": "2.5", "domain": "SAF", "sections_scanned": 7, "obligations_found": 84},
  "domain": "SAF",
  "obligations": [
    {"sentence": "Any SAE will be reported to the Sponsor within 24 hours.", "page": 84, "section": "15.6", "type": "timing", "severity": "CRITICAL"},
    {"sentence": "permitted during the study if the dosage is stable for at least 2 months prior to Day 0", "page": 71, "section": "12.2", "type": "permission", "severity": "MAJOR"}
  ]
}
```

**Scope boundary (deliberate)**: Step 2.5 only **builds** the yardstick. It does NOT check coverage, does NOT create KRIs, and does NOT promote to Tier 3. Coverage measurement + gap-blocking is **Step 3A** (which reads this inventory); recovery of genuinely-missed rules is the **Step 3.5 orphan scan**. The three are complementary: 2.5 = yardstick, 3A = measure + block, 3.5 = find + add.

---

## Step 2.6 — Auto-Judgment for T2 + T3-Promoted KRIs (MANDATORY, replaces manual decision table)

**Purpose**: Convert the prior manual Phase-2 decision-table gate into an automated pre-decision step so the pipeline can run end-to-end overnight without blocking on per-domain user review. Decides INCLUSION in the Golden Set only — does NOT replace Step 3B accuracy judging (which decides CORRECTNESS post-assembly).

**Script**: `scripts/step2_6_autojudgment.py`
**Runs after**: Step 2.5 Section Obligation Inventory (per domain).
**Runs before**: Phase 3 (orphan scan, accuracy judging).

**Input**: `raw_{DOMAIN}.json` with each KRI tagged `agent_count` (1–10).

**4-layer engine per candidate**:

| Layer | Type | Check |
|---|---|---|
| Layer 1 — Verification | Deterministic | Verbatim `supporting_quote` + non-empty `rule_for_llm` + parseable `protocol_reference`. Does NOT reject for non-binariness (Quality Rule 15 — downstream filters non-binary rules) |
| Layer 1.5 — Atomicity | Deterministic | Rejects only genuinely-empty always-true tautologies (e.g. "Males or females"). Definitional / conditional / judgment rules are KEPT (Quality Rule 14) |
| Layer 2 — Coverage/dedup | Deterministic | Already covered by approved T1 KRI? |
| Layer 3 — 6-judge panel | LLM | 6 Gemini 3.5 Flash judges (thinking-high) vote accept / reject / conditional on each KRI |
| Layer 4 — Aggregate | Deterministic | ≥5 accept + ≤1 reject → auto_approve · ≥5 reject + ≤1 accept → auto_reject · else → flag |

**Judge prompt**: neutral CRA-framed (same framing as the 10-agent extraction panel). See `scripts/autojudgment_prompts.py`.

**Tier 3 pipeline integration** (T3 KRIs flow through ALL layers):
  - T3-1 Coverage Filter = Layer 2
  - T3-2 Verbatim Verification = Layer 1
  - T3-2.5 Atomicity Check (new) = Layer 1.5
  - T3-3 6-Judge Panel = Layer 3
  - T3-4 Aggregate = Layer 4

**Output artifacts** (per domain):
  - `{domain}_autojudgment_report.json` — full layer-by-layer audit (every candidate, every judge vote + reason).
  - `{domain}_manual_review_decisions.json` — sectioned table: `auto_approved` / `flagged_for_review` / `auto_rejected`.
  - `{domain}_tier3_filtered.json` — extended schema: per-KRI disposition with stage + reason (Quality Rule 13 applies).

**CLI flag** `--auto-approve-unanimous` (default ON):
  - ON: pipeline runs without blocking; flagged items default to rejected at Phase 4, surfaced end-of-run in Step 4A-FlaggedReview for user review + optional re-inclusion.
  - `--interactive`: pipeline pauses per-domain on flagged items. User resolves every flagged row before advancing.

**Scope**: `--auto-approve-unanimous` affects Step 2.6 ONLY. Step 3.5 orphan scan USER_DECISION items and Step 3B accuracy FLAG items retain their own independent pause behavior.

**Blocking gate**: Phase 3 cannot begin until each domain's `{domain}_autojudgment_report.json` exists. In `--interactive` mode the gate also requires every flagged row to have a user decision. In auto-approve mode the gate shifts forward to Phase 4 (Golden Set won't finalize if user has pending overrides in `flagged_review_decisions.json`).

---

## Step 4A-FlaggedReview — End-of-Run Cross-Domain Flagged Review

**Purpose**: Consolidate every flagged-then-rejected KRI from all 4 in-scope domains into a single user-review table at end of run, so the user reviews everything in one pass rather than per-domain during the run.

**Script**: `scripts/step4a_flagged_review.py`
**Runs after**: Step 4A-Dedup (last step before Golden Set finalization).

**Artifact**: `flagged_review_decisions.json` (cross-domain, full KRI columns per row). Each row has `user_override` defaulting to null.

**Re-inclusion workflow**:
  1. User reviews `flagged_review_decisions.json`.
  2. User sets `user_override: "include"` on any row they want re-added.
  3. User runs `python scripts/step4a_flagged_review.py --out /path/ --apply-overrides` (re-adds included KRIs to their source domain's `raw_{DOMAIN}.json`).
  4. User re-runs `python run.py --pdf ... --out ... --from 4a` to regenerate the Golden Set with re-included KRIs.

This decouples overnight pipeline completion from user review. Default behavior preserves the conservative (safer) Golden Set; user expands it post-hoc if needed.

---

## Step 3A — Completeness Gate (BLOCKING)

**Purpose**: A blocking gate with two complementary coverage checks. Implemented in `scripts/step3a_completeness.py`; returns a pass/fail boolean to `run.py`'s gate framework.

**Check 1 — Section coverage**: every in-scope section in `manifest.section_inventory` (disposition ELIG/SAF/END/OPS) must have ≥1 KRI citing one of its pages. `out_of_scope_soa` / `non_substantive` are exempt. A still-empty in-scope section — after the Step 3.5 orphan scan already ran — is a gap.

**Check 2 — Obligation coverage**: every statement in each `{domain}_obligation_inventory.json` (Step 2.5) must be covered by ≥1 KRI. Coverage is decided by an **LLM coverage judge** ("would a KRI catch a violation of this obligation?"), NOT substring matching — the high-recall inventory sentences are longer than the ≤30-word quotes. **Partial coverage of a compound obligation (e.g. the "prior to" half but not the "during the study" half) counts as NOT covered.** A domain with mapped sections but a missing inventory is a blocking error (Step 2.5 was not run).

**Output**: `gaps_report.json` — `section_coverage`, `obligation_coverage_by_domain`, the H4 result, `pass_gate`, and unresolved-gap counts. Each obligation gap carries a `gap_key`.

**Gate**: the pipeline cannot advance to Step 3B until 0 unresolved section gaps AND 0 unresolved obligation gaps. **Escape hatch** — a gap clears by (a) covering it with a KRI, (b) re-tagging the section `non_substantive` in the manifest, or (c) acknowledging it in `gaps_resolutions.json` (`{"sections": {"<num>": {"acknowledged": true, "reason": "…"}}, "obligations": {"<gap_key>": {"acknowledged": true, "reason": "…"}}}`), then re-run `--from 3a`.

### Step 3A+ — H4 SAF Heuristic (single retained heuristic)

After the Step 3A completeness gate's coverage checks, run one protocol-agnostic heuristic. (The prior H1–H10 heuristics were SOA-flavored — they checked procedure × visit relationships and SoA-table geometry — and were removed when SOA extraction moved to the separate `soa-kri-extractor` skill. Only H4 is retained, retargeted as a SAF heuristic.)

**H4 — Adverse-Event Collection Window**: Verify that `raw_SAF.json` contains at least one KRI defining the AE collection window starting at first IP dose (e.g., "AEs collected from first IP administration through 30 days post-last-dose"). If absent, promote a candidate via the Tier 3 / orphan-scan pathway so the obligation is captured.

**LLM prompt**:
```
You are a clinical trial protocol expert checking AE-collection-window coverage.

Read the SAF KRIs below. Does at least one KRI clearly define when AE collection
starts and ends (relative to first IP administration and last IP administration)?

SAF KRIs:
{saf_kri_names_and_rules}

Return JSON:
{
  "h4_covered": true | false,
  "h4_kri_id": "<id of the covering KRI, or null>",
  "h4_reason": "<one sentence — either where it is covered, or what is missing>"
}
```

**Action**: If `h4_covered == false`, scan the protocol's safety / pharmacovigilance section for the AE-collection-window sentence and promote it as an orphan candidate (`ORPH-SAF-{NNN}`) into `raw_SAF.json` for downstream Phase 3 validation.
---

## Step 3.5 — Protocol-Wide Orphan Scan (MANDATORY BLOCKING, runs FIRST in Phase 3)

**Purpose**: After Phase 2 completes, scan the entire protocol to find rule-like content that was not captured by any domain extractor. See `SKILL.md` for the full spec — this file mirrors the operational summary.

**Input**: full PDF + `manifest.json` + all `raw_{DOMAIN}.json` files.

**Architecture**: 6-agent panel — 6 Gemini 3.5 Flash (thinking-high), single-model with a temperature spread.

**Phase 1 — Primary section sweep (section-by-section)**: For each section in `manifest.json`, each of the 6 agents independently scans the section's full text with the list of existing KRIs already citing pages in that section. Each agent returns candidate orphan rule-like statements.

**Zero-KRI section emphasis** (mandatory): sections where the existing-KRI list is empty are flagged as zero-KRI sections and dispatched with an alternate prompt variant that instructs maximum recall — every rule-like statement is treated as a candidate orphan, no self-filtering, no "too minor" filtering. Per-section coverage (existing-KRI count, zero-KRI flag, candidates flagged) is recorded in `orphan_scan_report.json` under `primary_sweep.section_coverage_audit`. See SKILL.md Step 3.5 full spec for terminology (note: "zero-KRI section" here is distinct from Step 2.5's "uncovered obligations" — different scope).

**Phase 2 — Secondary page sweep (orphan pages only)**: For every PDF page NOT claimed by any section in `manifest.json`, run the same 6-agent scan page-by-page.

**Phase 3 — Consolidation** (high-recall candidate, consensus promotion):
- ≥4/6 agents → HIGH CONFIDENCE → auto-promote
- 2–3/6 agents → USER DECISION → escalate, pipeline pauses for response
- 1/6 agent → LOW CONFIDENCE → NOT dropped silently; logged in `low_confidence_candidates` in the report

**Phase 4 — Cross-check**: adjudication judge checks each promoted candidate against ALL existing KRIs across ALL domains for true-duplicate coverage (atomization splits are NOT duplicates — see dedup section). Covered candidates are dropped with a logged reason.

**Phase 5 — Domain classification & KRI generation**: surviving candidates classified per Domain Boundary Rules. Full KRI records generated with `ORPH-` prefixed IDs and appended to the corresponding `raw_{DOMAIN}.json`.

**Phase 6 — Gating**: Step 3A cannot start until the scan is complete, all user decisions are resolved, cross-check is done, classification is done, and `orphan_scan_report.json` is written. Compliance Monitor enforces this.

**Save output**: `{out_dir}/orphan_scan_report.json` with sections: `_meta`, `primary_sweep`, `secondary_sweep`, `consolidation`, `low_confidence_candidates`, `user_decisions`, `cross_check`, `classification`, `promoted_orphans`.

**Promoted orphans flow through the rest of Phase 3** (3A, 3A+, 3B, 3C, 3D) exactly like Phase 2 KRIs.

---

## Step 3B — Full KRI Accuracy Judging (MANDATORY BLOCKING, 100% coverage)

**Purpose**: Verify the clinical content of EVERY KRI (100% coverage across all domains, including orphan KRIs promoted in Step 3.5) against the protocol. Sampling is NEVER permitted. The prior 20-KRI / 4-per-category sampling approach is replaced and must not be re-introduced. See `SKILL.md` for the full spec — this file mirrors the operational summary.

**Input**: all KRIs across all `raw_{DOMAIN}.json` files + full PDF.

**Architecture — 5-judge Gemini panel per KRI**:
- G1–G5 → Gemini 3.5 Flash, thinking-high (5 independent judges, temperature-spread for independence)

**Per-KRI input to each judge**: KRI record + full text of cited page(s) + 1 page before and after.

**The 6 checks each judge runs**:
1. **C1 Faithfulness** — does `rule_for_llm` say what the protocol says, nothing more, nothing less?
2. **C2 Specific values** — every threshold, drug, dose, timing window, analyte, day count, percentage, unit matches exactly
3. **C3 Reference accuracy** — cited section + page is ABOUT the clinical topic (semantic, not substring; catches wrong-page-but-quote-happens-to-appear cases).
4. **C4 Completeness** — no critical detail the protocol specifies is missing
5. **C5 Scope accuracy** — population, time-point scope match protocol intent
6. **C6 Atomicity** — the KRI encodes exactly ONE binary obligation about ONE subject with at most one condition. Compound KRIs (e.g., `LDL-C, Apo B, and TG at Week 14`, multiple obligations in one `rule_for_llm`) FAIL C6. Auto-correction = split into N atomic KRIs and re-judge each split.

**Per-judge verdict JSON**:
```json
{
  "judge_id": "C1",
  "model": "claude-sonnet-4",
  "kri_id": "SAF-003",
  "verdict": "CORRECT | IMPRECISE | WRONG",
  "failing_checks": ["C2", "C4"],
  "issue": "specific problem or null",
  "corrected_rule": "corrected text or null",
  "protocol_evidence": "verbatim ≤25-word quote proving verdict"
}
```

**Consensus adjudication per KRI**:
- 5/5 CORRECT → PASS
- 4/5 CORRECT + 1 non-CORRECT → PASS (with dissent logged)
- 3/5 CORRECT + 2 non-CORRECT → FLAG → user decision, pipeline pauses
- ≤2/5 CORRECT → FAIL → blocking

**Auto-correction** (IMPRECISE or FAIL):
1. Collect all `corrected_rule` proposals from judges
2. If ≥3 judges propose semantically equivalent corrections → merge and apply
3. **Re-run the full 5-judge panel on the corrected KRI** (mandatory re-verification — never apply without re-verification)
4. If re-verified at ≥4/5 CORRECT → PASS, log the correction
5. **C6 atomicity-split correction** (special case): when ≥3 judges flag C6 FAIL with the same atomic-split proposal, split the compound KRI into N atomic KRIs (one per atomic obligation), then re-run the full 5-judge panel on each split KRI. The original compound KRI does not pass; only the split atomic KRIs that themselves achieve ≥4/5 CORRECT pass.
6. Otherwise → user decision

**Gating** (all must be true before Step 3C can begin):
- 0 FAIL
- 0 unresolved FLAG
- Every IMPRECISE either auto-corrected + re-verified ≥4/5 CORRECT, or explicitly user-accepted

**Batching and cost control**:
- Group KRIs by cited page → load page text once per run, reuse
- Batch up to 8 KRIs per LLM call when they share the same page context
- Parallel workers across domains (4 concurrent: ELIG, SAF, END, OPS)
- 5 judges per KRI run in parallel, not sequentially
- Page text cache in memory, keyed by page number

**Save output**: `{out_dir}/accuracy_report_full.json` with sections: `_meta` (including pass_gate boolean), `per_kri` (all 5 judge verdicts + consensus + correction + user decision per KRI), `blocking_issues`, `auto_correction_log`, `user_decisions`.

**Relationship to Step 3D**: 3B checks clinical meaning (semantic); 3D checks verbatim substring (deterministic). Both run. Neither replaces the other. The combination catches both wrong clinical content AND fabricated quotes AND wrong-page-but-substring-match cases.

---

## Step 3C — Consistency Check

**Purpose**: Identify cross-KRI inconsistencies — same clinical concept mentioned in multiple KRIs (e.g., a threshold value referenced in both SAF and OPS, or two ELIG criteria using different units for the same lab) must have consistent values, units, and references.

**Grouping**: Cluster KRIs that share a topic keyword (e.g., LDL-C, ALT, GFR, IP storage temperature). Only check clusters with 2+ members.

**For each cluster**, read the cited PDF pages, then:

**LLM prompt**:
```
Check internal consistency for the "{topic}" concept across these KRIs.

KRIs:
{kri_list}

PROTOCOL PAGES:
{relevant_page_text}

Identify inconsistencies where a value, unit, threshold, or qualifier present
in some KRIs is contradicted by others — e.g.:
- Different ULN multiples for the same lab
- Different reporting windows for the same event
- Different unit conventions (mg/dL vs mmol/L) for the same analyte
- Different definitions for the same population label

Mark differences as intentional only if the protocol explicitly states different
requirements per context.

Return JSON:
{
  "cluster": "{topic}",
  "overall_status": "CONSISTENT|HAS_INCONSISTENCIES",
  "inconsistencies": [
    {
      "description": "what the inconsistency is",
      "affected_kri_ids": ["..."],
      "reference_kri_ids": ["..."],
      "could_be_intentional": false,
      "protocol_quote": "verbatim ≤20 words",
      "recommendation": "what affected KRIs should say"
    }
  ]
}
```

**Action**: Flag inconsistencies for user review. Do not auto-fix.

**Save output**: `{out_dir}/consistency_report.json`

---

## Step 4A — Assembly (Python, no LLM)

Run this Python code to merge all category files:

```python
import json, re, os

CATEGORY_LABELS = {
    "ELIG": "Eligibility",
    "SAF": "Safety & Toxicity",
    "END": "Endpoints & Statistics",
    "OPS": "Operations & Compliance"
}

def assemble(out_dir, manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    all_kris, categories_meta = [], []
    
    for cat in ["ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(out_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            continue
        with open(raw_path) as f:
            data = json.load(f)
        kris = data.get("kris", [])
        
        # Normalize + deduplicate
        seen, cleaned = set(), []
        for i, k in enumerate(kris, 1):
            rule = (k.get("rule_for_llm") or "").strip().lower()
            if rule and rule in seen: continue
            if rule: seen.add(rule)
            if not k.get("rule_for_llm") and not k.get("kri_name"): continue
            k["category_id"] = cat
            k["category_label"] = CATEGORY_LABELS[cat]
            cleaned.append(k)
        
        all_kris.extend(cleaned)
        categories_meta.append({
            "id": cat, "label": CATEGORY_LABELS[cat],
            "kri_count": len(cleaned),
            "kri_ids": [k["kri_id"] for k in cleaned]
        })
    
    output = {
        "_meta": {
            "version": "1.0.0",
            "protocol": manifest.get("protocol_id", "UNKNOWN"),
            "sponsor": manifest.get("sponsor", ""),
            "extracted_by": "protocol-kri-extractor",
            "total_kris": len(all_kris),
            "total_categories": len(categories_meta)
        },
        "categories": categories_meta,
        "kris": all_kris
    }
    
    out_path = os.path.join(out_dir, "extracted_kris.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    return out_path
```

### Excel output (always generate alongside JSON)

After assembling `extracted_kris.json`, also generate `Extracted_KRIs.xlsx` using openpyxl.
The Excel workbook has one sheet per in-scope domain (ELIG, SAF, END, OPS — 4 sheets) plus a Summary sheet.

**Exact column structure — identical for ALL domain sheets, no deviations:**

| Column | Field | Width |
|--------|-------|-------|
| KRI ID | `kri_id` | 16 |
| Category | `category_label` | 28 |
| KRI Name | `kri_name` | 34 |
| Description | `description` | 52 |
| Rule for LLM | `rule_for_llm` | 60 |
| Protocol Reference & Quote | `combined_ref` | 90 |

**No "Domain" column.** No separate "Protocol Reference" column. No separate "Supporting Quote" column. The `combined_ref` field is the single source for the last column.

Formatting:
- Dark blue header row (1F4E79) with white bold text, frozen at row 1
- Text wrapping enabled on all cells, thin borders
- Domain-specific row colors: ELIG=FCE5CD, SAF=F4CCCC, END=CFE2F3, OPS=EAD1DC

```python
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

def generate_excel(out_dir, all_kris_by_category):
    """Generate Extracted_KRIs.xlsx matching golden set format."""
    SHEETS = [
        ("ELIGIBILITY", "Eligibility", False),
        ("SAF&TOX", "Safety & Toxicity", False),
        ("END&STAT", "Endpoints & Statistics", False),
        ("OPE&COM", "Operations & Compliance", False),
    ]
    CAT_MAP = {"ELIGIBILITY": "ELIG", "SAF&TOX": "SAF",
               "END&STAT": "END", "OPE&COM": "OPS"}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    hdr_font = Font(bold=True, size=11, color="FFFFFF")
    hdr_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    wrap = Alignment(wrap_text=True, vertical="top")
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                    top=Side(style='thin'), bottom=Side(style='thin'))

    for sheet_name, cat_label, has_footnotes in SHEETS:
        ws = wb.create_sheet(sheet_name)
        cat_key = CAT_MAP[sheet_name]
        kris = all_kris_by_category.get(cat_key, [])

        if has_footnotes:
            headers = ["KRI Name", "Description", "category",
                       "Rule to Check- for LLM", "Referance ", "Additional Footnotes"]
        else:
            headers = ["KRI Name", "Description", "category",
                       "Referance ", "Rule to Check- for LLM"]

        for col, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=col, value=h)
            c.font = hdr_font; c.fill = hdr_fill; c.alignment = wrap; c.border = border

        for i, kri in enumerate(kris, 2):
            name = kri.get("kri_name", kri.get("kri_id", ""))
            desc = kri.get("description", "")
            rule = kri.get("rule_for_llm", "")
            ref = kri.get("protocol_reference", "")
            fn = kri.get("additional_footnotes") or ""

            if has_footnotes:
                row = [name, desc, cat_label, rule, ref, fn]
            else:
                row = [name, desc, cat_label, ref, rule]

            for col, val in enumerate(row, 1):
                c = ws.cell(row=i, column=col, value=str(val) if val else "")
                c.alignment = wrap; c.border = border

        widths = [35, 50, 20, 55, 45, 40] if has_footnotes else [35, 50, 20, 45, 55]
        for col, w in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w
        ws.freeze_panes = "A2"

    xlsx_path = os.path.join(out_dir, "Extracted_KRIs.xlsx")
    wb.save(xlsx_path)
    return xlsx_path
```

---

## Step 4B — Golden Set Prompt

After Step 4A assembly completes, **always ask the user**:

> "Do you have a golden set (reference KRI file) to compare against? If so, please provide the file path or upload it."

Wait for the user's response. If they provide a golden set path or file, proceed to Step 4C.
If they say no, the pipeline is complete.

**Accepted golden set formats**:
- JSON file with a `kris` array (same schema as `extracted_kris.json`)
- JSON file that IS a flat array of KRI objects
- JSON file with category-level keys (e.g. `{"ELIG": [...], "SAF": [...]}`). If the golden set also contains a `"SOA"` key, those entries are loaded into a side channel as "out of scope for this skill" and excluded from this skill's comparison score.

Normalize the golden set into a flat list of KRI objects before proceeding.

**Save normalized golden set**: `{out_dir}/golden_set_normalized.json`

---

## Step 4C — Golden Set Comparison

Run category-by-category comparison. For each of the 5 categories, run 3 phases in sequence.
Use parallel subagents to process multiple categories simultaneously when possible.

### Phase 1 — Semantic Matching

For each category, match extracted KRIs to golden KRIs based on semantic similarity
of the `rule_for_llm` and `kri_name` fields — not ID matching (IDs may differ between sets).

**Matching prompt** (per category, batch up to 20 golden KRIs at a time):
```
You are a clinical trial protocol expert matching CRA verification rules.

GOLDEN KRIs ({CATEGORY}):
{golden_kris_json}

EXTRACTED KRIs ({CATEGORY}):
{extracted_kris_json}

For each GOLDEN KRI, find the best-matching EXTRACTED KRI(s) based on what the rule
verifies — the same clinical requirement, same visit scope, same data check.
Matching is by meaning, not by ID or phrasing.

Rules:
- A golden KRI may match 1 extracted KRI (1:1) or multiple (1:many if the extracted
  set split the golden rule into finer-grained KRIs)
- An extracted KRI may match multiple golden KRIs (many:1 if the extracted set merged
  golden rules)
- Some golden KRIs may have NO match (missing from extraction)
- Some extracted KRIs may have NO golden match (extra in extraction)

Return JSON:
{
  "matches": [
    {
      "golden_kri_id": "...",
      "golden_rule": "the rule_for_llm text",
      "matched_extracted_ids": ["id1", "id2"] or [],
      "match_type": "1:1|1:many|many:1|unmatched"
    }
  ],
  "unmatched_extracted": ["extracted_id1", "extracted_id2"]
}
```

### Phase 2 — Semantic Judging

For each matched pair (or group), evaluate semantic equivalence.

**Judge prompt** (batch up to 15 pairs per call):
```
You are a clinical trial monitoring expert comparing CRA verification rules.

JUDGING PHILOSOPHY — TWO TIERS:
This comparison uses TWO separate criteria for judging:

TIER 1 — SEMANTIC COVERAGE (lenient):
  Does the extracted KRI check the SAME clinical requirement as the golden KRI?
  If yes, differences in phrasing, sentence structure, word choice, or level of
  detail in HOW the rule is expressed do NOT matter. Focus on WHAT is being
  verified, not HOW the sentence is worded.
  Examples that are EQUIVALENT under semantic coverage:
  - "Verify absence of X" vs "Verify participant does not have X"
  - "Confirm weight was recorded" vs "Verify body weight measurement was performed"
  - "Check consent was obtained" vs "Verify ICF signed and dated before procedures"
  - "Verify vitals were taken" vs "Verify vital signs (BP, HR, temp) were measured"
    (if both refer to the same visit and same clinical check)

TIER 2 — FACTUAL PRECISION (strict):
  When EITHER rule (golden or extracted) contains specific factual details from the
  protocol, those details MUST be accurate and present. Factual details include:
  - Numeric values: thresholds, doses, ages, lab ranges (e.g. "≥64 years", "≤-150°C")
  - Visit windows: timing tolerances (e.g. "±3 days", "Day -45 to 0")
  - Drug/compound names: exact names, not generic descriptions (e.g. "diphenhydramine
    50 mg IV" not "antihistamine")
  - Specific time periods: washout durations (e.g. "≥48 hours", "within 3 months")
  - Named instruments/scales: (e.g. "WOMAC Total", "PHQ-9", "KL grade")
  - Named procedures with specific method: (e.g. "ultrasound-guided", "central read")
  If these factual details match or are both absent → no penalty.
  If one has them and the other omits them → mark as SUBSET or SUPERSET.
  If both have them but they DIFFER → mark as DIVERGENT.

SCORING RUBRIC (applying both tiers):
- EQUIVALENT: Same clinical requirement (Tier 1 pass). Any factual details present
  in both rules are consistent (Tier 2 pass). Wording differences are irrelevant.
  A rule that says more about context or rationale but checks the same thing = EQUIVALENT.
- SUBSET: Same clinical requirement (Tier 1 pass) but extracted OMITS a specific
  factual detail (drug name, dose, threshold, timing, method) that the golden includes
  and that comes from the protocol. Only flag as SUBSET if the missing detail would
  change what a CRA actually checks in practice.
- SUPERSET: Same clinical requirement (Tier 1 pass) but extracted ADDS a specific
  factual detail beyond the golden that comes from the protocol.
- DIVERGENT: Different clinical requirement (Tier 1 fail), OR same requirement but
  factual details contradict each other (e.g. "±3 days" vs "±7 days").

IMPORTANT — DO NOT mark as SUBSET for:
  - Different phrasing that means the same thing
  - Different sentence structure or ordering
  - One rule being more verbose or descriptive than the other
  - One rule including explanatory context the other omits
  - Minor differences in how the same data source is referenced
  These are ALL considered EQUIVALENT if the clinical check is the same.

FEW-SHOT EXAMPLES:
[PAIR] INC1
  GOLDEN:    Verify age ≥ 64 years at screening.
  EXTRACTED: Verify participant is ≥ 64 years old at first screening visit.
  VERDICT: EQUIVALENT — same check, same threshold, phrasing irrelevant

[PAIR] WEIGHT
  GOLDEN:    V4- Verify weight measured in kilograms, shoes removed.
  EXTRACTED: V4- Verify weight was recorded.
  VERDICT: SUBSET — missing factual details "in kilograms" and "shoes removed"

[PAIR] CONSENT
  GOLDEN:    S1- Verify ICF signed before procedures.
  EXTRACTED: S1- Verify informed consent form is signed and dated by participant
             before any study-specific procedures, with copy provided to participant.
  VERDICT: SUPERSET — adds "dated", "copy provided" factual details

[PAIR] SAF-AE-007
  GOLDEN:    Verify SAEs are reported to the sponsor within 24 hours of investigator awareness.
  EXTRACTED: Verify SAEs are reported to the sponsor within 24 hours of awareness.
  VERDICT: EQUIVALENT — same clinical check (24-hour SAE reporting window). Wording
           differences are irrelevant; both rules would cause a CRA to verify the same thing.

[PAIR] OPS1
  GOLDEN:    Verify IMP storage logs document ≤ -150°C.
  EXTRACTED: Verify IMP storage logs document ≤ -150°C (or -80°C short-term) in secure area.
  VERDICT: SUPERSET — adds short-term condition and access control

[PAIR] ELIG-INC-12
  GOLDEN:    Verify the subject's eGFR is ≥ 30 mL/min/1.73m² at screening.
  EXTRACTED: Verify the subject's eGFR is ≥ 60 mL/min/1.73m² at screening.
  VERDICT: DIVERGENT — factual detail (threshold) contradicts

NOW EVALUATE {N} PAIRS. For each pair return:
{
  "golden_kri_id": "...",
  "extracted_kri_id": "...",
  "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT",
  "reason": "one sentence explaining why, referencing Tier 1 and Tier 2",
  "key_difference": "the specific factual detail missing/added/changed, or null if EQUIVALENT"
}

Return ONLY a JSON array of exactly {N} objects.
```

### Phase 3 — Protocol Evidence for Differences

This is the critical new step. For every non-EQUIVALENT pair, go back to the protocol PDF
and find what the protocol actually says. This creates the 3-column comparison the user needs.

**For each non-EQUIVALENT pair**:
1. Parse the `protocol_reference` from both the extracted and golden KRI
2. Read those PDF pages (and any additional pages referenced in footnotes)
3. Determine which version (extracted or golden) is more faithful to the protocol

**Evidence prompt** (batch up to 10 differences per call):
```
You are a clinical trial protocol expert. For each difference below, determine what the
protocol actually says and which version (extracted or golden) is more faithful.

PROTOCOL TEXT:
{relevant_pages_text}

DIFFERENCES TO RESOLVE:
{differences_list_with_extracted_and_golden_rules}

For each difference, return:
{
  "golden_kri_id": "...",
  "extracted_kri_id": "...",
  "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT",
  "extracted_rule": "the extracted rule_for_llm",
  "golden_rule": "the golden rule_for_llm",
  "protocol_says": "What the protocol actually states — include section number, page,
                     and a verbatim quote (≤30 words). If information comes from multiple
                     places, cite all of them.",
  "protocol_references": [
    "Section X.X, Page N: \"verbatim quote\"",
    "Footnote N, Page M: \"verbatim quote\""
  ],
  "more_faithful": "extracted|golden|neither",
  "explanation": "1-2 sentences explaining who is right and what is missing/wrong/added"
}

Return ONLY a JSON array.
```

### Phase 4 — Coverage Gaps

After all categories are judged:
- List golden KRIs with NO extracted match → "Missing from extraction"
- List extracted KRIs with NO golden match → "Extra in extraction"

For each gap, read the relevant protocol pages and note whether the KRI is supported
by the protocol text (i.e., is the golden KRI a real requirement? Is the extra extracted
KRI a valid rule from the protocol?).

### Assembling the comparison report

Merge all per-category results into a single `comparison_report.json`:

```json
{
  "_meta": {
    "protocol_id": "...",
    "golden_set_path": "...",
    "extracted_total": N,
    "golden_total": N,
    "comparison_date": "ISO date"
  },
  "score": {
    "formula": "(EQUIVALENT + SUPERSET + 0.5*SUBSET) / total_golden * 100",
    "value": 85.3,
    "verdict": "PASS|ITERATE|REWORK",
    "thresholds": {"pass": 80, "iterate": 60}
  },
  "summary_by_category": [
    {
      "category": "SAF",
      "golden_count": N,
      "extracted_count": N,
      "equivalent": N,
      "subset": N,
      "superset": N,
      "divergent": N,
      "missing_from_extracted": N,
      "extra_in_extracted": N
    }
  ],
  "differences": [
    {
      "category": "SAF",
      "golden_kri_id": "...",
      "extracted_kri_id": "...",
      "verdict": "SUBSET",
      "extracted_rule": "...",
      "golden_rule": "...",
      "protocol_says": "...",
      "protocol_references": ["Section X, Page N: \"quote\""],
      "more_faithful": "golden",
      "explanation": "Extracted rule omits the data source..."
    }
  ],
  "missing_from_extracted": [
    {
      "golden_kri_id": "...",
      "golden_rule": "...",
      "category": "...",
      "protocol_supported": true,
      "protocol_reference": "Section X, Page N"
    }
  ],
  "extra_in_extracted": [
    {
      "extracted_kri_id": "...",
      "extracted_rule": "...",
      "category": "...",
      "protocol_supported": true,
      "protocol_reference": "Section X, Page N"
    }
  ]
}
```

**Scoring**: `(EQUIVALENT + SUPERSET + 0.5×SUBSET) / total_golden × 100`
- ≥80 → **PASS**
- 60–79 → **ITERATE** (re-extract categories with most SUBSET/DIVERGENT)
- <60 → **REWORK** (re-run full pipeline)

**Save output**: `{out_dir}/comparison_report.json`

### Presenting the report to the user

After saving the JSON, present a human-readable summary:

1. **Overall score** and PASS/ITERATE/REWORK verdict
2. **Per-category table** with verdict counts
3. **Top differences** — show the 3-column view (extracted | golden | protocol says)
   for the most impactful differences (DIVERGENT first, then SUBSET)
4. **Coverage gaps** — missing and extra KRIs with protocol support status
5. **Recommendations** — which categories or specific KRIs to fix if score < 80

---

## Step 3D — Full Verbatim Verification (MANDATORY BLOCKING GATE)

**Purpose**: Verify that every KRI's `supporting_quote` is a verbatim substring of the text on its cited protocol page. Deterministic — no LLM. Must reach 100% pass before Step 4A can begin.

**Run**: `python scripts/step3d_verify.py --pdf /path/to/protocol.pdf --json /path/to/extracted_kris.json`

**How it works**:
1. Load all KRIs from `extracted_kris.json`
2. Extract all PDF pages into an in-memory cache using pdfplumber
3. For each KRI:
   - Parse the page range from `protocol_reference` (handles `p.X`, `p.X-p.Y`)
   - Search the cited page range ±2 pages for `norm(supporting_quote)` as a substring of `norm(page_text)`, where `norm` collapses all whitespace to single spaces
   - **PASS**: quote found → save stripped quote and recompute `combined_ref`
   - **AUTO-CORRECT**: quote found on a different page than cited → update `protocol_reference` and `combined_ref`, log the correction
   - **FAIL**: quote not found anywhere in range → must be fixed manually

4. Save backup before writing corrected JSON (`extracted_kris.pre_verify.json`)
5. Write corrected `extracted_kris.json`
6. Save `{out_dir}/verify_report.json`

**Known PDF quirks to handle**:
- Curly apostrophes (`\u2019` `'`) vs straight (`'`) — must match the PDF's actual character
- Private-use characters (e.g., `\uf0b1` for ±) — copy from pdfplumber output, not typed
- Merged words (e.g., "IPadministration", "14days") — pdfplumber strips spaces at word boundaries in some PDFs

**Fabricated quote = hard failure**: A `supporting_quote` that cannot be found verbatim in the cited page is a **fabricated quote** — a hard pipeline failure. Not a warning, not a soft flag. The pipeline stops immediately. The KRI must be corrected before proceeding. No exceptions.

**Blocking gate**: If `verify_report.json` shows any FAIL, the pipeline stops. Fix each failing KRI (correct the quote or the page reference), then re-run Step 3D until 0 failures. Only then proceed to Step 4A.

**Output — `verify_report.json`**:
```json
{
  "_meta": { "step": "3D", "total": 675, "pass": 675, "auto_corrected": 3, "fail": 0, "gate": "PASS" },
  "pass": ["ELIG-INC-001", "SAF-AE-001", "..."],
  "auto_corrected": [
    { "kri_id": "GOV-INT-002", "old_pg": 47, "new_pg": 48 }
  ],
  "fail": []
}
```

---

## Step 4D — Comparison Verification (runs after Step 4C)

**Purpose**: Reconciliation pass to reduce false negatives and false positives in the Step 4C comparison report. Catches cases where the LLM comparison judged two semantically equivalent KRIs as DIVERGENT or MISSING due to wording differences.

**Input**: `comparison_report.json` from Step 4C + full `extracted_kris.json` + golden set KRIs.

**Process**:

1. **False-negative scan (MISSING verdicts)**:
   - For each golden KRI marked MISSING (no extracted match found), search the extracted KRI set for any KRI whose `rule_for_llm` contains the same key terms: procedure name + visit prefix + primary threshold/value (if any)
   - If a match is found → reclassify as EQUIVALENT or SUBSET (whichever is more precise) and log the correction with the matching extracted KRI ID

2. **False-positive scan (DIVERGENT verdicts)**:
   - For each pair marked DIVERGENT, re-read both `rule_for_llm` texts and the cited protocol pages
   - Confirm they truly check different clinical requirements — not just differently worded versions of the same check
   - If they are the same check worded differently → reclassify as EQUIVALENT

3. **Save output**: `{out_dir}/comparison_verified.json` with all reclassifications and a corrected score.

```json
{
  "_meta": {
    "step": "4D",
    "original_score": 74.2,
    "corrected_score": 81.5,
    "reclassifications": 9
  },
  "reclassifications": [
    {
      "kri_id_golden": "ELIG-INC-012",
      "original_verdict": "MISSING",
      "corrected_verdict": "EQUIVALENT",
      "matched_extracted_kri": "ELIG-INC-018",
      "reason": "Same inclusion criterion, different wording"
    }
  ]
}
```

**Blocking**: None — Step 4D is a reconciliation pass, not a blocking gate. Its output refines the comparison result but does not gate any subsequent step.
