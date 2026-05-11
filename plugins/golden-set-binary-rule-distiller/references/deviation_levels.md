# Deviation Level — subject / site / trial

Every rewritten rule gets a `Deviation Level` value: one of `subject`, `site`, or `trial`. This tells the downstream engine the granularity of the flag — at which level the deviation should be reported and aggregated.

## The three levels

### subject

Use `subject` when the deviation is tied to data about an individual study subject. Most rules are subject-level.

Examples:
- Inclusion/exclusion criteria (each subject either meets or fails the criterion)
- Visit-procedure adherence (each subject either had the procedure or didn't)
- AE reporting timing (the AE belongs to a specific subject)
- AE field-completeness (the AE belongs to a specific subject)
- Stopping-rule triggers (the lab value or AE belongs to a specific subject)
- Pregnancy reporting, contraception compliance (per-subject status)
- Per-dose administration parameters (volume, duration, route) — each dose ties to a subject

**Subtlety on AE rules:** AE timeliness and field-completeness rules look like they could be "site CRF data quality", but the deviation occurs per subject because each AE belongs to a subject. Aggregating across a site is one analytic view of the same subject-level data; that's the engine's job, not the rule's.

### site

Use `site` when the data anchor is a site/facility-level asset, log, or process — something not tied to a specific subject.

Examples:
- IP storage freezer temperature logs
- IP shipment records (per shipment to a site)
- Vial packaging specifications per IP lot
- Monitoring logs (per monitoring visit)
- Screening logs (per site)
- IRB approval before site initiation
- Pharmacy preparation logs (preparer identity per IP-prep event)
- Indistinguishable-container attestation per IP lot
- Records retention policy per site
- Single-IRB attestation
- Confidential subject list maintained by site
- Emergency unblinding events (governed by Study Blinding Plan, audit-trailed at the site/system level)
- Screen-failure documentation (site-level screening log)

### trial

Use `trial` when the data anchor is a cumulative or aggregate trial-level metric — something only meaningful when you look across all subjects/sites.

Examples:
- Study pause triggers (e.g., "≥ 2 subjects with same related Grade 3+ AE")
- SUSAR reporting to FDA/IRB (sponsor-level reporting)
- DMC composition (≥ 3 members), DMC meeting cadence, DMC reports
- Randomization ratio (e.g., 2:1 across all randomized subjects)
- Enrollment caps (e.g., digit-DFO ≤ 30% of cumulative randomized)
- Final analysis timing and blinding scope
- Sponsor early-termination authority

## How to pick the level — quick decision tree

Ask: "What's the smallest unit at which this rule generates one flag?"

- If a single subject's data is enough to generate one flag → `subject`.
- If a single site's data is enough to generate one flag → `site`.
- If you need to aggregate across multiple subjects or sites to generate one flag → `trial`.

## Edge cases and reviewer disagreements

These are areas where reasonable reviewers disagree. The default below is what passed cleanest in the most recent panel review:

- **Per-AE field-completeness (causality, CTCAE grade, impact, outcome):** `subject`. The AE belongs to a subject. Site-level CRF-quality aggregation is the engine's job downstream.
- **Per-AE timeliness (CRF entry within 24h/72h):** `subject`. Same logic.
- **Per-dose administration parameters (e.g., IV bag volume):** `subject` when the dose is administered to a subject; `site` only if the rule is about pharmacy prep quality independent of any specific dose.
- **Container labeling, blinded prep:** `site`. Quality of the pharmacy process.
- **Cross-sheet duplicates with different levels:** flag the duplicate in the audit log; align levels when the dedupe is authorized.

## Avoiding common mistakes

- Don't default everything to `subject`. The Deviation Level column has real meaning — site-level and trial-level rules should be tagged correctly so the engine aggregates correctly.
- Don't put a single rule at multiple levels by trying to be inclusive. Pick the single most natural level. If a rule genuinely fires at two levels (e.g., per-vial and per-site), it usually wants to be split into two atomic rules.
- For pause triggers and DMC rules, prefer `trial` — these are aggregate signals that don't really make sense at subject level.
