# Rewrite format — SOURCE / CHECK / DEVIATION style guide

This file is the working reference for Stage 3 (rewrite `Rule for LLM`).

## The format — exactly three lines

```
SOURCE: <data the engine should pull, in plain natural language>
CHECK: <the precise compliance condition>
DEVIATION: <the exact condition that flags a deviation, including missing-data cases>
```

Three lines. No preamble, no postscript, no extra fields. The Severity stays in its existing column. The Deviation Level goes into its own new column. Nothing else belongs inside `Rule for LLM`.

## Hard rules for writing each line

### Short and sharp
One short sentence per line. No paragraphs. The downstream engine has to parse this — verbose prose is friction.

### Natural language only
No EDC/CRF field names. No schema references. No code-like notation.

| Don't write | Write instead |
|---|---|
| `vitals.weight_kg` | The subject's screening body weight |
| `cm.ae_severity_grade` | The CTCAE grade recorded on the AE form |
| `subject_visit_log[visit_id='V2'].visit_date` | The V2 visit date |
| `pharmacy_log.preparer_unblinded_flag` | The IP preparer's unblinded role status |

The skill doesn't know the user's CRF/EDC schema and shouldn't pretend to. The downstream LLM engine will map the natural language to the actual data fields at runtime.

### Never invent specifics the protocol doesn't authorize

This is the single most important rule in this file. It exists because past runs failed by inventing tolerances to "make rules more binary".

| Protocol says | Don't rewrite as | Do rewrite as |
|---|---|---|
| "approximately 30 minutes" | "between 25 and 35 minutes" | "approximately 30 minutes; flag if substantially deviates per applicable sponsor SOP" |
| "approximately 30% of subjects" | "greater than 30% of subjects" | "approximately 30% of subjects per protocol; flag when cumulative share substantially exceeds 30%" |
| "labeled in accordance with federal/local regulations and clearly labeled for investigational use only" | "label includes sponsor name, protocol ID, lot, storage temp, and IUO marking" (5 invented fields) | "labeled in accordance with federal/local regulations AND clearly marked 'investigational use only'" (the protocol's two clauses, verbatim) |
| "every 4 to 6 months" | "every 3.5 to 6.5 months (4-6 mo ± 2 weeks)" | "every 4 to 6 months" |
| "randomized 2:1" | "active arm share between 60% and 73% cumulatively" | "randomized in a 2:1 ratio per the IRT specification; flag if cumulative ratio substantially departs from 2:1" |
| "soaked with 2× the applied volume" | "within ±10% of 2× the applied volume" | "soaked with 2× the applied volume per protocol" |

The pattern: if the protocol uses fuzzy language ("approximately", "about", "ideally", "preferably"), the rewrite preserves that fuzziness. The DEVIATION line can use phrases like "substantially deviates", "substantially exceeds", or "is materially out of range per applicable sponsor SOP" — those are honest reflections that the protocol left a tolerance unspecified, and they let the downstream LLM engine apply runtime judgment without the skill having invented a number.

### Include missing-data as a deviation when relevant

Whenever the rule's intent is data presence, the DEVIATION line must explicitly call out missing data as a deviation cause. For example:

```
SOURCE: The V2 visit date and the randomization (Day 1) date, per subject.
CHECK: V2 visit date is within ±3 days of (Day 1 + 14 days).
DEVIATION: For an active subject, V2 visit date is outside this window, OR V2 visit date is missing.
```

Without the missing-data clause, the engine might silently pass over subjects whose V2 was never recorded.

### Cross-check discipline — every rule, every time

Before writing each rule's three lines, the agent MUST:

1. Open the protocol PDF at the cited reference (page or section in the `Protocol Reference & Quote` column).
2. Read the surrounding context — the full paragraph or section, not just the quoted snippet.
3. Verify the rule's intent against the protocol's actual wording.
4. Write the three lines using only specifics that are present in the protocol text. Carry over the protocol's exact thresholds, numbers, and qualifiers.
5. If the cited reference does not actually support the rule's intent, mark the rule as a drop candidate and surface it in the audit log. Do not fabricate.

## Worked examples — before and after

These come from a real Golden Set run. The "Before" column shows the original (sometimes malformed) Rule for LLM. The "After" column shows the rewritten 3-line form.

### Example 1 — SOA visit-procedure rule

Before:
```
D1_PRE- Verify that Eligibility assessment was performed at D1_PRE per the Schedule of Activities.
```

After:
```
SOURCE: The Eligibility assessment record at the Day 1 pre-treatment (D1_PRE) visit, per subject.
CHECK: Eligibility assessment was performed and dated at D1_PRE per the Schedule of Activities.
DEVIATION: For an active subject expected to attend D1_PRE, no Eligibility assessment record exists at that visit, or the record is undated.
```

### Example 2 — Visit-window check

Before:
```
V2- Verifies that the V2 visit occurred in Week 2 , ±3 days window.
```

After:
```
SOURCE: The V2 (Week 2) visit date and the randomization (Day 1) date, per subject.
CHECK: V2 visit date is within ±3 days of (Day 1 + 14 days).
DEVIATION: For an active subject, V2 visit date is outside this ±3-day window, or the visit date is missing.
```

### Example 3 — Subject-level exclusion criterion

Before:
```
Verify that the subject is excluded if body weight is <50 kg.
```

After:
```
SOURCE: The subject's screening body weight.
CHECK: Screening body weight is ≥ 50 kg.
DEVIATION: Subject was randomized with screening weight < 50 kg, or screening weight is missing.
```

### Example 4 — Event-level timing (SAE reporting)

Before:
```
Verify that all SAEs are reported by entering them into the CRF within 24 hours from the time the investigator first learned of the event.
```

After:
```
SOURCE: Per SAE — the investigator-awareness datetime and the CRF entry datetime.
CHECK: CRF entry occurs within 24 hours of investigator awareness.
DEVIATION: For any SAE, CRF entry datetime is more than 24 hours after investigator awareness, or either timestamp is missing.
```

### Example 5 — Site-level threshold

Before:
```
Verify that phage preparations are stored at <= -80 degrees C and remain frozen until just prior to administration.
```

After:
```
SOURCE: The IP-storage freezer temperature log and per-vial thaw timestamps, per site.
CHECK: Every freezer reading is ≤ −80 °C AND each vial remains frozen until just before dose preparation.
DEVIATION: Any freezer reading > −80 °C, or any vial thawed before dose-prep start.
```

### Example 6 — Fuzzy protocol target (the trap)

Before:
```
Verify IV infusion duration is approximately 30 minutes.
```

After (CORRECT — preserves protocol's fuzziness):
```
SOURCE: Per IV-dosing session — infusion start and stop timestamps.
CHECK: Infusion duration matches the protocol target of approximately 30 minutes.
DEVIATION: Any infusion duration substantially deviates from 30 minutes per applicable sponsor SOP, or either timestamp is missing.
```

After (WRONG — invents tolerances):
```
SOURCE: Per IV-dosing session — infusion start and stop timestamps.
CHECK: Infusion duration is between 25 and 35 minutes.
DEVIATION: Any infusion duration < 25 min or > 35 min, or either timestamp is missing.
```

The wrong version invents the 25-35 bound. The protocol never says where the line is. A 24-min infusion is not a protocol violation — the protocol doesn't define it that way.

## Common pitfalls

- **Stuffing two checks into one rule.** If the protocol describes two distinct conditions, split into two atomic rules (or two atomic sub-rules: e.g., `ELIG-INC-013a` and `ELIG-INC-013b`). Don't write a compound DEVIATION line saying "report each sub-condition separately" — that's a punt to the engine.
- **Cross-referencing other rule IDs in the rule body.** "Exclude AEs already covered by SAF-025/026/027/028." The engine reads rules independently and shouldn't have to track inter-rule dependencies. State the exclusion condition in clinical terms ("exclude ALT/AST elevations").
- **Adding 'engine output guidance' inside the rule.** Phrases like "report each sub-condition separately" or "the engine should aggregate by subject" don't belong in the rule body. They're meta-guidance, not the check itself.
- **Adding subjective filters that aren't measurable.** "Flag if the investigator considers it abnormal" turns a binary rule into a judgment call. Use the actual data threshold.
- **Re-encoding the same provision in two sheets.** If the same protocol provision shows up in both ELIG and OPS, surface the duplication in the audit log. Don't silently merge or rewrite both rules — that's a user-authorization decision.

## Validation

After writing all the rewrites, run `scripts/validate_rule_format.py` to confirm:
- Every rule's `Rule for LLM` value contains `SOURCE:`, `CHECK:`, and `DEVIATION:` each on its own line.
- No rule has a fourth line beyond those three.
- The `Deviation Level` column is populated with `subject`, `site`, or `trial`.

If any rule fails validation, fix it before producing the final xlsx.
