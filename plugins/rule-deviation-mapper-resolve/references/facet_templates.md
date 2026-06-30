# Reusable Facet Templates

These recur across families. Each is a *pattern*; ground the specifics against the actual protocol for the trial at hand (sections/footnotes/thresholds differ per protocol). Fold facets into the existing `Rule for LLM` keys (`required` + `deviation`), never new sub-keys.

## 1. Central-lab panels (Chemistry, Hematology, Coagulation, Urinalysis, Vitamins, …)
Five facets — apply uniformly to all panels of this type (parity), preserving each rule's analyte/component list and any ESD conditional:
- **Central lab** — processed by the central laboratory; a local lab instead = deviation, except in the protocol-sanctioned rare situations.
- **Window** — collected within the visit's scheduled window — *only where the protocol defines one* (e.g. ±N days for some visits; none at the Day-1/baseline or screening anchors).
- **Completeness** — the panel includes all required analytes/components; a partial panel (missing one or more) = deviation.
- **No-excess** — only the sample(s) scheduled for the visit are collected; extra/duplicate/unscheduled samples = deviation.
- **Investigator CS/NCS** — any out-of-range result is judged by the investigator and annotated "abnormal, not clinically significant" / "abnormal, clinically significant" (CS recorded as an AE).
- Remote-visit collection (home nurse / site → central) where the protocol allows it; preserve.
- **Retrofit:** when you add CS/NCS (or any new facet) to one panel, retrofit the same facet to the panels already done.

## 2. Clinician-administered (ClinRO) scales (C-SSRS, CGI-S, CGI-I, UMSARS, …)
- **eCOA modality** — administered/captured on the eCOA device per the protocol's scale-mode list; paper = deviation **only if the protocol grants no paper fallback** for that scale (some scales have a documented malfunction-paper exception; others don't — check per scale).
- **Visit window** — within the scheduled window where the protocol defines one.
- **Rater qualification** — administered by a rater qualified by education/experience/training and approved/certified for the study (the required rater qualification/certification documented at administration).

## 3. Caregiver-reported (PRO) scale (CaGI-S, …)
- Completed by the **actual primary caregiver** (not site staff / investigator), on eCOA; window where defined; "applies only if subject has a primary caregiver" conditional preserved.

## 4. "Assessment must yield a usable result"
For data-producing procedures (actigraphy, MRI, CSF, digital biomarkers): *performed ≠ done*. The data must be **captured, transferred to / available at the central reader/lab, and usable** — flag not-recorded / not-uploaded / lost / unevaluable / not-transferred. Ground on the protocol's purpose for the assessment + its delegation to the relevant manual.

## 5. Quantity / reconciliation (dispensing, accountability, collection)
- **Dispensing** — the quantity/configuration dispensed matches the RTSM/IWRS assignment (no under/over, buffers handled per assignment).
- **Accountability** — reconciles: dispensed = returned + taken; no unaccounted/lost units; dosing-compliance computed (and the protocol's compliance threshold applied, e.g. <90% / >100%).
- **Collection** — complete return of all dispensed used/empty + unused units; discarded/lost/not-returned = deviation; handle end-of-treatment / non-attendance (e.g. death) where relevant.

## 6. Ordering / sequence
- e.g. vital signs / ECG measured **before** PK sampling where they coincide (per the protocol's PK section).

## 7. Population guard
- A test performed **only where indicated** (e.g. a pregnancy test only for females of childbearing potential); flag it performed on a non-indicated subject (and broaden `applies_to` so the rule can evaluate the non-indicated case).

## 8. Conditionals to always preserve
- **ESD-at-V9 discretion** — "if the V9 visit is performed as an Early Study Discontinuation, this blood-laboratory or scale assessment is at investigator discretion and its omission is not a deviation."
- **Conditional requirements** — "required only if …" (e.g. brain MRI at ETD only if the most recent scan was > 6 months prior; medical-monitor waiver as `override`).
- **Triggers** — "an Unscheduled visit exists", etc.

## Threshold/value facts are PER-PROTOCOL
Numbers like compliance thresholds, dose ceilings, visit windows, first-dose timing, panel composition, scale modes, and which manual a thing is delegated to are **specific to each protocol** — extract them from the protocol you are working on, do not hardcode from a prior trial.
