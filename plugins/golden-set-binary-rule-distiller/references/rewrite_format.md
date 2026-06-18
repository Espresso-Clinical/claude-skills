# Authoring format — the YAML "Protocol rule"

This file is the working reference for Stage 3: **authoring the `Rule for LLM` from scratch**. The incoming Golden Set has no usable `Rule for LLM` — you write it fresh from the rule's columns + footnotes + the protocol PDF.

The `Rule for LLM` is a **"Protocol rule"**: a *data-agnostic clinical statement of the check*, authored from the protocol alone. It is serialized as **YAML** inside the single cell.

## What "data-agnostic" means (the protocol layer)

The Protocol rule describes a KRI **purely from the protocol** — what to check, who's in scope, when, which items, what's a violation — in clinical terms. It carries **no knowledge of how the data is built**: no table names, no columns, no codes, no joins, no EDC/CRF field names. Resolving the rule to real data points is a separate downstream tool's job and is deliberately **outside this format**. If you catch yourself naming a table, a column, a visit-id mapping ("V1 → 'Visit 1'"), or a join, delete it — that belongs downstream, not here.

## The slots

```yaml
intent: one-line plain-English purpose
applies_to: the clinical denominator — WHO/WHAT must satisfy this
evidence_expected: the clinical artifact the protocol says must exist (the thing, not where it is stored)
acceptance:            # open set of sub-slots — use ONLY the ones the rule needs
  timing: ...          # window / acceptability window
  required: ...        # mandatory items
  preferred: ...       # non-mandatory but preferred
  conditional: ...     # conditional trigger / exception
  trigger: ...         # the condition that activates the check (e.g. an optional procedure's record exists)
  pass: ...            # the plain pass condition (criteria-style rules)
  override: ...        # a documented waiver that satisfies the rule
deviation: the violation in clinical terms, derived from applies_to + acceptance
provenance: terse pointer only — section + page (NO footnote numbers)
```

- The six **top-level slots are always present**: `intent`, `applies_to`, `evidence_expected`, `acceptance`, `deviation`, `provenance`.
- `acceptance` **sub-slots are an open set** — none is mandatory. Pick whichever the rule, its description, its reference, and its footnotes actually call for. The common ones are listed above; add another only if it genuinely clarifies (and keep the name plain). Footnotes become first-class clinical logic here.
- `provenance` is a **terse pointer** (section + page; **no footnote numbers**). Do NOT repeat the verbatim quote — it already lives, untouched, in the `Protocol Reference & Quote` column.

## Authoring rules

### 1. Comprehensiveness — harvest from every column AND every footnote
The authored rule is the ONLY artifact the deviation engine runs on, so every checkable detail must live inside it. Sweep the columns and the footnotes/quotes behind them and fold in: analyte/parameter lists (each value in a panel), time & acceptability windows ("up to 4 days prior", "available 3 months prior is acceptable"), mandatory subsets and AND/OR logic ("sodium … and AST or ALT"), conditional triggers ("only if total bilirubin is abnormal", "for women of childbearing potential only"), and the protocol's pass-vs-deviation definition. **Never leave a checkable detail sitting only in a footnote or another column.**

### 2. Clarity — plain clinical language, no meta-commentary
Every slot must read as a clear clinical statement that both the engine and a human can act on without decoding. **Do NOT** write self-referential caveats or tags such as:
- ❌ `completeness: "presence and dating only — does NOT require every component"`
- ❌ `panel: "RBC, HGB, ... [footnote 12 definition]"`

If individual items are **not** mandatory, simply don't list them under `required`; the `deviation` line's silence about them already means they aren't required. Put the descriptive list in `evidence_expected` instead (see SOA-014 below). Clarity is non-negotiable — a rule full of jargon is a failed rule even if it's "complete".

**No footnote numbers, anywhere in the rule.** Carry the footnote's *content* into the slots, but never the citation. ❌ `"... up to 4 days prior [footnote 14]"`, ❌ `"Footnote 13"`, ❌ a `provenance` of `"SoA Run-In, Footnote 14, p.26."`. ✅ `"... up to 4 days prior"`, ✅ `provenance: "SoA Run-In, p.26."`. The rule does not care which footnote number a detail came from; the numbered citation already lives, untouched, in the `Protocol Reference & Quote` column.

### 3. `applies_to` is a clinical denominator, never a data filter
Write a clinical population: "enrolled subjects", "every SAE", "every activated site", "every IP administration". **Never** adjectives like "active" or "expected to attend", and never a data filter.
- For **eligibility criteria** the denominator is **"enrolled subjects"**: the criterion is assessed at screening, but the *deviation* is enrolling an ineligible subject — a screen failure is not a deviation.
- **Never use "randomized"** unless the provision is specifically about the randomized phase. (In this trial the safety run-in phase is *not* randomized, so eligibility/run-in rules must not say "randomized".)

### 4. `evidence_expected` names a clinical artifact, never restates the criterion
- ✅ "the subject's prior investigational-product / interventional-trial exposure history for the 60 days before first treatment, and any documented Sponsor approval"
- ❌ "the eligibility determination for exclusion #22" (circular — just restates the criterion)

### 5. No filler
Drop subject-state preambles ("for an active subject expected to attend…") and restated visit labels. Keep every clinical parameter, value, window, and condition; cut everything that adds length without adding a check.

### 6. Never invent specifics the protocol doesn't authorize
Comprehensiveness means including everything the protocol *does* state — it never means inventing what it doesn't. If the protocol says "approximately 30 minutes", the rule says "approximately 30 minutes" — never "25–35 minutes". When the protocol is intentionally fuzzy, write "substantially deviates per applicable sponsor SOP" and let the downstream engine judge the margin. These two rules (comprehensive ↔ no-invent) are mirror images: exhaustive of the protocol, silent beyond it.

### 7. Author to the protocol, not to the source columns
The `Description` and `Protocol Reference & Quote` are hypotheses. If the `Description` conflicts with the protocol — e.g. a templated "±3-day window relative to randomization" where the SoA actually says the Screening window is "Day -29 to 0" — **author to the protocol** and surface the discrepancy in the audit log. Do NOT edit the Description (immutability).

### 8. Presence-only vs required-subset (labs)
- A **screening lab** is usually **presence-only**: put its component list in `evidence_expected` as a description, give the acceptability window in `acceptance.timing`, and make the `deviation` "no result performed/dated in the window". Do NOT add a `required` item list and do NOT add a `completeness` caveat.
- A **pre-treatment lab** that a footnote makes mandatory ("the following must be available and reviewed prior to first treatment: …") DOES get a `required` subset (the mandatory items, with AND/OR logic) and a `preferred` full panel.
The analyte list is a deviation trigger **only** where a footnote makes it mandatory.

### 9. Timeliness rules — name the date proxy in `evidence_expected`
A "within N hours/days of an event" rule is authored as a date difference. In `evidence_expected`, name the two dated artifacts the check differences (the event date and the action date). When the exact clock the protocol names isn't recorded, fall back to the closest available dates and say so plainly — never drop the rule for lack of the precise timestamp. If no clean clock exists at all, narrow the `deviation` to the part that is recorded (e.g. "the outcome was not recorded"). See filter_criteria.md "Timeliness / reporting-deadline rules".

### 10. Visit-anchored procedures — `timing` is the visit, not the visit's window
For a procedure/test/assessment scheduled at a specific visit, `acceptance.timing` states that it was performed **at/for that visit** (by its visit label — "performed at the V3 visit", "performed and dated for the Screening visit"), NOT the visit's calendar window ("Day 12-16", "Day -29 to 0"). The visit's date window is checked by its **own dedicated visit-timing rule** (the "check-in within window" rule), so a per-procedure rule must never restate it — that would duplicate the visit check and mis-attribute the window to the procedure. Keep in `timing` the procedure's **own** footnote-defined acceptability window ("may be drawn up to 4 days before the visit", "a result from up to 3 months before eligibility confirmation is acceptable") and any pre-dose sequencing clause ("prior to IP administration").
- ✅ `timing: "performed at the V3 visit, prior to IP administration"`
- ✅ `timing: "performed and dated for the Screening visit; a result from up to 3 months before eligibility confirmation is acceptable"`
- ❌ `timing: "performed Day 12-16"` (that Day window is the visit's own check — it belongs to the visit check-in rule, not the procedure)

### 11. Optional / Sponsor-gated procedures — invert the rule (deviation = performed WITHOUT authorization)
When a procedure is performed only at discretion but the authorization is *documentable* — "per Sponsor instruction", an imaging-plan designation, a recorded per-protocol gate — do NOT author an ordinary presence rule (omission is not a deviation here) and do NOT drop it. **Invert** it: the deviation is performing it WITHOUT documented authorization. Make omission-is-not-a-deviation explicit, and use:
- `conditional`: state plainly that the procedure is optional, has no default requirement, and that OMISSION IS NOT A DEVIATION
- `trigger`: the procedure record exists in the subject's data
- `pass`: EITHER it was not performed, OR it was performed AND the authorization is documented
- `deviation`: performed WITHOUT documented authorization

`evidence_expected` must name the authorization artifact (e.g. "the Sponsor imaging-plan instruction designating the patient, or its documented absence") plus the procedure record. Distinguish from a procedure *required for a protocol-designated subset* ("applicable sites", "all main-phase patients per the imaging plan") — that stays an ordinary presence rule scoped to the designated population via `conditional`, with the normal "designated subject lacking it" deviation (rule 8). Drop only when there is neither a documentable authorization nor a protocol-defined recorded trigger to check against.

### 12. Presence/activity rules check performance, not another domain's conclusion
An "activity performed" rule (a SOA assessment, a visit procedure) verifies that the activity was **performed and documented** — it must NOT re-judge a conclusion owned by another domain. A "screening eligibility assessment performed" rule checks that the assessment happened; whether the subject actually met eligibility is ELIG's job, not this rule's. Narrow an overreaching rule to what its own data shows: the `deviation` is "the activity was not performed/documented", never "…and the criteria were not all met". Align sibling rules across phases/visits to the same corrected scope.

## Worked examples (real rules, across the five domains)

### SOA-008 — V1 Biochemistry (required-subset lab; the flagship)
```yaml
intent: "Pre-treatment biochemistry was available and reviewed before the first V1 dose."
applies_to: "subjects who reached V1 (first treatment)"
evidence_expected: "a biochemistry result usable for the V1 pre-treatment review."
acceptance:
  timing: "drawn up to 4 days before V1 and available/reviewed before first treatment - a recent screening draw can satisfy it"
  required: "sodium, potassium, glucose, bilirubin, creatinine, (AST or ALT)"
  preferred: "full panel (albumin, LDH, GGT, ALP, CRP/hsCRP, urea, total protein)"
  conditional: "direct bilirubin only if total bilirubin is abnormal"
deviation: "a V1 subject with no qualifying biochemistry in the window carrying the required items."
provenance: "SoA Run-In, p.26."
```

### SOA-014 — Screening Complete Blood Count (presence-only lab)
```yaml
intent: "A complete blood count was performed for the Screening visit."
applies_to: "subjects who attended the Screening visit (Day -29 to 0)"
evidence_expected: "a complete blood count result for Screening (red blood cell count, hemoglobin, hematocrit, MCH, MCHC, MCV, white blood cell count with differential, and platelet count)."
acceptance:
  timing: "performed and dated for Screening; a result available from up to 3 months before eligibility confirmation is acceptable"
deviation: "a Screening attendee with no complete blood count performed and dated within the acceptable window."
provenance: "SoA Run-In, p.26."
```
Contrast with SOA-008: the components sit in `evidence_expected` (a description), there is no `required` list, and the deviation is purely about the result being absent — so individual components are not separately required, **without any caveat needed**.

### SOA-059 — Screening X-ray (window + preferred + conditional)
```yaml
intent: "A qualifying knee X-ray supported screening eligibility."
applies_to: "subjects who attended the Screening visit (Day -29 to 0)"
evidence_expected: "a posteroanterior knee X-ray image read for the trial."
acceptance:
  timing: "taken at Screening, or within 3 months prior to screening - a recent pre-screening image can satisfy it"
  required: "a posteroanterior image, read centrally"
  preferred: "acquired using a fixed-flexion frame; central read within ~7 business days"
  conditional: "a local/regional expert read is acceptable only if approved by the Sponsor"
deviation: "a Screening attendee with no qualifying posteroanterior knee X-ray within the acceptable window (or read locally without Sponsor approval)."
provenance: "SoA Run-In, p.26."
```

### SOA-203c — V6 MRI, Sponsor-instructed subset (inverted optional)
```yaml
intent: "An MRI at V6 is performed only for the subset designated by Sponsor instruction; performing it WITHOUT a Sponsor instruction is the deviation, omitting it is not."
applies_to: "subjects who attended the V6 (6 months) visit in the randomized phase"
evidence_expected: "the Sponsor imaging-plan instruction designating the patient for imaging (or its documented absence), and any V6 MRI scan record."
acceptance:
  conditional: "MRI at V6 is optional, performed only for the Sponsor-designated subset per the imaging plan; there is no default requirement and OMISSION IS NOT A DEVIATION"
  trigger: "a V6 MRI scan exists in the subject's record"
  pass: "EITHER no V6 MRI was performed, OR a V6 MRI was performed AND a Sponsor instruction designating the patient is documented"
deviation: "a subject who underwent a V6 MRI WITHOUT a documented Sponsor instruction authorizing it."
provenance: "SoA Randomized Phase p.31-34; §14.4.3 p.78."
```
The check is inverted: the deviation is unauthorized *performance*, not omission. Contrast Mode 2 (required-for-designated-subset, e.g. CRPM "for subjects at applicable sites"), authored as an ordinary scoped presence rule.

### ELIG-EXC-022 — Recent-IP exclusion (pass + override; eligibility denominator)
```yaml
intent: "Subject had no other IP / interventional-trial participation within 60 days of first treatment (exclusion #22)."
applies_to: "enrolled subjects"
evidence_expected: "the subject's prior investigational-product / interventional-trial exposure history for the 60 days before first treatment, and any documented Sponsor approval."
acceptance:
  pass: "no IP receipt or interventional-trial participation in the 60 days before first treatment"
  override: "documented Sponsor approval waives the criterion"
deviation: "an enrolled subject who received an IP or participated in another interventional trial within 60 days before first treatment without documented Sponsor approval."
provenance: "§8.2 p.62, Exclusion #22."
```
Note `applies_to: "enrolled subjects"` — NOT "randomized" (assessed at screening; the deviation is enrolling someone ineligible).

### SAF-AE-010 — SAE 24-hour reporting (timing; per-event denominator)
```yaml
intent: "Each SAE was reported to the Sponsor within 24 hours of awareness."
applies_to: "subjects who had a Serious Adverse Event (evaluated per SAE)"
evidence_expected: "the investigator-awareness time and the SAE-form submission time to the Sponsor."
acceptance:
  timing: "SAE form submitted to the Sponsor no later than 24 hours after the investigator becomes aware"
deviation: "an SAE reported to the Sponsor more than 24 hours after investigator awareness."
provenance: "§15.6 p.84."
```
If the precise awareness timestamp isn't captured, `evidence_expected` names the closest recorded dates instead (e.g. the SAE onset date and the SAE-form entry date) and the check becomes (entry date − onset date) ≤ 24 h — state the proxy explicitly rather than dropping the rule.

### OPS-COMP-003 — EC/IRB approval before activation (site denominator)
```yaml
intent: "Each site's EC/IRB approval was received before it was activated."
applies_to: "every activated site"
evidence_expected: "the unconditional EC/IRB Letter of Approval and its receipt date, and the site activation date."
acceptance:
  timing: "the EC/IRB Letter of Approval is received by the Sponsor before site activation"
  required: "the letter specifically identifies the approved documents"
deviation: "a site activated on or before the EC/IRB Letter of Approval was received."
provenance: "§17.1.2 p.94."
```

### END-OBL-032 — Run-in dose de-escalation (trial-level conditional action)
```yaml
intent: "Dosing was de-escalated to Dose -1 when Dose 1 safety/tolerability could not be confirmed."
applies_to: "the trial (run-in dose-escalation decision)"
evidence_expected: "the STC outcome for Allocetra Dose 1 (50x10^6 cells) and the dose used for the subsequent cohort/injections."
acceptance:
  pass: "if safety/tolerability of Dose 1 (50x10^6 cells) cannot be confirmed, the dose is de-escalated to Dose -1 (25x10^6 cells, cohort -1)"
  conditional: "per the run-in plan, Cohort -1 is triggered if >=1 Cohort 0 subject fails STC after the 1st injection, or >=1 Cohort 1 subject fails STC after any injection"
deviation: "Dose 1 safety/tolerability not confirmed, yet dosing was not de-escalated to Dose -1."
provenance: "§2 p.22-23 (run-in plan §6.1.1 p.46)."
```

## Common pitfalls

- **Naming data structures.** Any table/column/code/join belongs downstream, never in the rule.
- **Meta-commentary in a slot.** "presence and dating only", "[footnote X definition]", "contrast SOA-008" — all jargon. State the clinical fact plainly; let `required`/`deviation` carry the logic.
- **`applies_to` as a data filter or "randomized".** Use the clinical denominator; eligibility → "enrolled subjects".
- **`evidence_expected` restating the criterion.** Name the artifact (a history, an assessment, a finding, a result, a letter).
- **Leaving a footnote out of the logic.** A window or required-subset in a footnote MUST enter `acceptance`, not stay a quote.
- **Inventing tolerances.** Preserve the protocol's fuzziness.
- **Editing an existing column to "fix" it.** Author to the protocol and flag the discrepancy in the audit log; never touch the source cell.

## Validation

After authoring all rules, run `scripts/validate_rule_format.py` to confirm, for every `Rule for LLM` cell:
- it parses as **valid YAML**;
- it contains the six required top-level slots (`intent`, `applies_to`, `evidence_expected`, `acceptance`, `deviation`, `provenance`);
- `acceptance` is a non-empty mapping (sub-slots open — the validator does not enforce specific sub-slot names);
- the `Deviation Level` column is populated with `subject`, `site`, or `trial`.

Fix any rule that fails before producing the final xlsx.
