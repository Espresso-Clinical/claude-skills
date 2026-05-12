# Annotated SOA KRI Examples

Real examples showing the expected structure, with each field annotated. Use these as canonical references when writing prompts or judging outputs.

## Example 1 — Procedural KRI with analyte-list enrichment

**Source:** SoA table row "Blood chemistry, hematology, ESR, CRP", X mark at SCR column, Footnote 12 specifies analytes.

```json
{
  "kri_id": "SOA-SCR-193",
  "kri_name": "SCR - Blood chemistry",
  "description": "Verifies that Blood chemistry was performed at the SCR visit per the Schedule of Activities table. The record must include all 14 required analytes per the protocol footnote.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: The Blood chemistry record at the screening (SCR) visit, per subject. Required analytes: sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, aspartate aminotransferase (AST), alanine aminotransferase (ALT), alkaline phosphatase, bilirubin, total protein, albumin.\nCHECK: Blood chemistry was performed and dated at screening (SCR) per the Schedule of Activities AND the record contains values for all 14 required analytes: sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, albumin.\nDEVIATION: For an active subject expected to attend SCR, no Blood chemistry record exists at that visit, the record is undated, OR any of the 14 required analytes (sodium, potassium, chloride, bicarbonate, BUN, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, albumin) is missing from the record.",
  "protocol_reference": "Schedule of Activities, Footnote 1, Footnote 12, p.41-p.42",
  "supporting_quote": "Blood chemistry parameters will include sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, and albumin.",
  "combined_ref": "Schedule of Activities, Footnote 1, Footnote 12, p.41-p.42 — \"Signing of informed consent and screening procedures must be performed within 30 days before randomization on Day 1.\", \"Blood chemistry parameters will include sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, and albumin.\"",
  "additional_footnotes": "Footnote 12: Blood chemistry parameters will include sodium, potassium, chloride, bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, ALT, alkaline phosphatase, bilirubin, total protein, and albumin.",
  "severity": "major",
  "deviation_level": "subject",
  "agent_count": 10
}
```

**Why this is right:**
- `kri_name` uses procedure-major prefix `SCR - <atomic procedure>` (the compound row "Blood chemistry, hematology, ESR, CRP" was atomized into 4 separate KRIs).
- `rule_for_llm` embeds the full 14-analyte list in SOURCE, CHECK, and DEVIATION.
- Both Footnote 1 (visit-level — screening window) and Footnote 12 (procedure-level — analyte list) are cited.
- Page range `p.41-p.42` is the actual Camelot-detected table pages, not the broader manifest section range.

## Example 2 — Check-in KRI with explicit date-math

```json
{
  "kri_id": "SOA-CHECKIN-V2-009",
  "kri_name": "V2 - Day 14 ±3 days - Check-in",
  "description": "Verifies that the V2 visit occurred on Day 14, within the ±3-day window relative to randomization.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: The V2 (Week 2) visit date and the randomization (Day 1) date, per subject.\nCHECK: V2 (Week 2) visit date is within ±3 days of (Day 1 + 14 days).\nDEVIATION: For an active subject, the V2 visit date is outside this window, or the visit date is missing.",
  "protocol_reference": "Schedule of Activities, Footnote 2, p.41-p.42",
  "supporting_quote": "Visit windows for Weeks 2-13 will be ±3 days of the day of the week on which the Day 1 treatment was initiated.",
  "combined_ref": "Schedule of Activities, Footnote 2, p.41-p.42 — \"Visit windows for Weeks 2-13 will be ±3 days of the day of the week on which the Day 1 treatment was initiated.\"",
  "additional_footnotes": "Footnote 2: Visit windows for Weeks 2-13 will be ±3 days of the day of the week on which the Day 1 treatment was initiated...",
  "severity": "major",
  "deviation_level": "subject",
  "agent_count": 10
}
```

**Why this is right:**
- `kri_name` includes the explicit window in its title.
- CHECK uses exact date math: `within ±3 days of (Day 1 + 14 days)`.
- References the window-defining footnote (Footnote 2).

## Example 3 — Bundle with components listed

```json
{
  "kri_id": "SOA-V3-042",
  "kri_name": "V3 - Vital signs including weight",
  "description": "Verifies that Vital signs (BP, HR, temperature, weight) were measured at the V3 visit per the Schedule of Activities. Methodology requirements: supine position, after at least 5 minutes of rest, pre-dose.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: The Vital signs record at the V3 (Week 3) visit, per subject. Required measurements: blood pressure (systolic and diastolic), heart rate, body temperature, weight (kg).\nCHECK: Vital signs including weight was performed and dated at V3 (Week 3) per the Schedule of Activities AND the record contains values for all 4 required measurements: blood pressure (systolic and diastolic), heart rate, body temperature, weight (kg). Methodology: supine position; after at least 5 minutes of rest. Timing: pre-dose.\nDEVIATION: For an active subject expected to attend V3, no Vital signs record exists at that visit, the record is undated, OR any of the 4 required measurements (BP, HR, temperature, weight) is missing. OR methodology requirements (supine position, 5-min rest, pre-dose) were not met.",
  "protocol_reference": "Schedule of Activities, Footnote 5, p.41-p.42",
  "supporting_quote": "To be measured at all visits from Week 2 up through Week 11 ... vital signs are to be measured before any phage administration during the visit, and again at approximately 15 minutes after the end of the last phage administration.",
  "combined_ref": "Schedule of Activities, Footnote 5, p.41-p.42 — \"To be measured at all visits from Week 2 up through Week 11 ... vital signs are to be measured before any phage administration during the visit, and again at approximately 15 minutes after the end of the last phage administration.\"",
  "additional_footnotes": "Footnote 5: To be measured at all visits from Week 2 up through Week 11 ...",
  "severity": "major",
  "deviation_level": "subject",
  "agent_count": 10
}
```

**Why this is right:**
- "Vital signs" is a recognized standardized bundle, kept whole, with all 4 components listed in the rule.
- Methodology (supine, rest) and timing (pre-dose) are extracted from the footnote and embedded in CHECK / DEVIATION.

## Example 4 — Cross-visit narrative rule (from protocol body)

```json
{
  "kri_id": "SOA-TEXT-007",
  "kri_name": "Permitted NSAID / Topical Window",
  "description": "Oral over-the-counter NSAIDs and topical therapies applied to the index knee are permitted only during the treatment period and up to exactly 2 weeks following the last intra-articular injection.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: Per participant: dates of oral OTC NSAID and/or topical-therapy use applied to the index knee, and the date of the last IMP injection.\nCHECK: Oral OTC NSAIDs and topical therapies applied to the index knee are used only during the treatment period and no later than 2 weeks after the last IMP injection.\nDEVIATION: Any oral OTC NSAID or topical-therapy use occurred before the treatment period or more than 2 weeks after the last IMP injection.",
  "protocol_reference": "Section 11.1.1, Page 64",
  "supporting_quote": "Oral over-the-counter NSAIDs: May be used during the treatment period and up to 2 weeks following the last injection, for management of acute pain or swelling.",
  "combined_ref": "Section 11.1.1, Page 64 — \"Oral over-the-counter NSAIDs: May be used during the treatment period and up to 2 weeks following the last injection, for management of acute pain or swelling.\"",
  "additional_footnotes": null,
  "severity": "major",
  "deviation_level": "subject",
  "agent_count": 7
}
```

**Why this is right:**
- Cross-visit / narrative rule extracted by the SOA-text panel (sub-area 7: permitted concomitant-medication windows).
- Reference cites the section + page in the body text, not the SoA table.
- `agent_count=7` reflects single-shot LLM extraction (vs deterministic atomic-grid's 10).

## Example 5 — Orphan footnote KRI

```json
{
  "kri_id": "SOA-ORPHAN-FOOTNOTE-001",
  "kri_name": "Footnote 23 - To include dates of all debridements",
  "description": "Verifies obligation from Footnote 23, which is unanchored to any specific cell. Content: dates of all debridements performed on the study foot since the most recent study visit, with type (bone vs soft tissue) and site.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "SOURCE: Per subject: dates and details of all debridements performed on the study foot since the most recent study visit.\nCHECK: All debridements are documented with date, type (bone or soft tissue), and site (study ulcer for soft tissue; original bone-infection site for bone).\nDEVIATION: Any debridement record is missing date, type, or site information.",
  "protocol_reference": "Schedule of Activities, Footnote 23, p.41-p.42",
  "supporting_quote": "To include dates of all debridements performed on the study foot since the most recent study visit and for each debridement, whether the debridement was of bone or soft tissue, and whether the debridement was at the site of the study ulcer for soft tissue debridements, or at the site of the original bone infection at the start of the study, for bone debridements.",
  "combined_ref": "Schedule of Activities, Footnote 23, p.41-p.42 — \"To include dates of all debridements performed on the study foot since the most recent study visit...\"",
  "additional_footnotes": "Footnote 23: To include dates of all debridements performed on the study foot...",
  "severity": "minor",
  "deviation_level": "subject",
  "agent_count": 10
}
```

**Why this is right:**
- Footnote 23 exists in the protocol footnote text but isn't anchored to any cell in the SoA table → orphan-footnote sweep captures it.
- The rule is concrete enough for binary verification.
- Severity `minor` because it's a documentation clarification, not a primary safety/efficacy obligation.
