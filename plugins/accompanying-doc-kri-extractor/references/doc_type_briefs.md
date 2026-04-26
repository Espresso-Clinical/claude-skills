# Document-Type Extraction Briefs

These briefs are **guides, not limiters.** For every document type, extract EVERY rule, obligation, threshold, timeline, classification criterion, reporting requirement, handling procedure, statistical handling instruction, or monitoring obligation present in the document — **even if it does not match the examples below**. The examples show the *kinds of things* the document usually contains and the *language patterns* to watch for. They do not exhaust the set.

When extracting, err on the side of inclusion. Stage 3 consensus tiering and Stage 7 verification will filter false positives. Missed rules are far harder to recover than extracted noise.

Universal extraction targets (apply to every doc type):
- Numeric thresholds (percentages, counts, durations, dose limits, temperature ranges)
- Time windows and deadlines (reporting windows, review windows, visit windows)
- Mandatory actions ("must", "shall", "is required to", "will")
- Prohibited actions ("must not", "shall not", "is prohibited")
- Classification / categorization criteria
- Responsibility assignments ("the Sponsor is responsible for …", "the CRA will …")
- Escalation triggers (who, when, to whom)
- Documentation / record-keeping obligations
- Training / qualification requirements
- Audit / inspection readiness requirements
- Quality-control / review rules

---

## CMP — Clinical Monitoring Plan

**What it is.** Defines how the sponsor/CRO monitors the trial: monitoring strategy, visit types and frequency, Source Data Verification (SDV) coverage, remote vs on-site monitoring, Risk-Based Monitoring (RBM) triggers, site escalation paths, monitor qualifications, CAPA handling for monitoring findings.

**Key KRI categories:**
- SDV coverage rules (percentages by CRF page type, by visit, by endpoint category)
- Visit type definitions and frequency (site initiation, routine, interim, close-out; on-site vs remote)
- Monitoring visit windows (must be completed within N days of …)
- Risk-trigger thresholds (data query rate, PD rate, AE reporting lag, enrollment rate triggering escalation)
- Site escalation rules (when to escalate, to whom, within what window)
- Report turnaround times (monitoring visit report due N days after visit)
- Action-item / CAPA closure windows
- Monitor qualifications and training requirements
- Co-monitoring / oversight rules

**Examples (illustrative, not exhaustive):**
- "Verify that SDV coverage for primary endpoint CRF pages is 100%."
- "Verify that every routine monitoring visit was followed by a monitoring visit report filed within 10 business days."
- "Verify that any site with a query resolution time >14 days was escalated to the Lead CRA."
- "Verify that the Site Initiation Visit occurred before any subject was enrolled at that site."

**What to ignore as noise:**
- Generic background statements ("Monitoring is an important activity in clinical trials…")
- Definitions sections that do not impose an obligation
- Boilerplate references to ICH GCP without specific site-level action

---

## CSMP — Clinical Study Management Plan

**What it is.** Governs the overall operational conduct of the study across all functions and parties: project governance, committee cadence, vendor and lab oversight, study-milestone gating, multi-country/multi-entity responsibility splits, approval and signature gates, tracker lifecycles, regulatory gating (e.g., green-light to start screening), TMF/eTMF format and archiving, training documentation, document approval workflows, and cross-document escalation paths.

**Key KRI categories:**
- Governance committee cadence (frequency, membership, quorum) and minutes filing windows
- Vendor and lab contact + CV collection — one KRI per named vendor/lab; CV is a separate sub-requirement (extract a distinct KRI when the doc requires CV in addition to contact info)
- Multi-country / multi-entity responsibility splits — when the doc states "Entity X is responsible in country/site set A, Sponsor (or other entity) is responsible in country/site set B", extract one KRI per (entity × responsibility × region) combination
- Approval-before-milestone gates — every "Document X must be signed/approved by Party Y before Milestone Z" becomes its own KRI (e.g., PI signs blinding plan before randomization enrollment; PV Plan approved before FSFV; BDRM minutes signed before DB Hard Lock; CSR approved before finalization; DSMB Charter approved before activation)
- Document approval workflows — "drafted by A, reviewed by B, approved by C and D" — extract approval-by-each-party as separate KRIs
- Tracker lifecycle — for every named tracker (MVR/FUL trackers, Training Tracker, Essential Documents Tracker, Risk Assessment Log, etc.), extract three KRIs: (1) existence/creation, (2) ongoing maintenance / update cadence, (3) final filing in the TMF at end of study
- Regulatory gating — Regulatory Green Light (or equivalent) before any screening activity; country-specific extra Site Initiation Visits before specific study phases
- TMF/eTMF format rules — electronic-only mandate, no parallel hard copies, archiving responsibility named
- TMF upload responsibility splits — who uploads what, by region/site/document type
- Database Lock & close-out gates — SDV completion + query resolution before Close Out Visit; DBL within a defined window after LPLV; signed DBL Approval form
- Medical coding workflow — coding conventions document approval (by which parties); final medical coding approved before DB Hard Lock
- Cross-document escalation paths — IMP issues → immediate sponsor phone call; safety issues → Medical Monitor; data issues → Data Manager — even if these duplicate other docs at extraction time, dedup against the protocol golden set is a downstream stage
- Translation responsibility per language/country
- Risk Assessment Log version-by-version approval cadence
- Study-milestone timelines and deviation triggers (e.g., DBL ≤ 1 month after LPLV)
- Training documentation — start-date and study-specific training recorded for each staff role on the named tracker
- PI- and site-specific signature obligations (e.g., site blinding plan signed by PI before randomization)
- Vendor oversight KPIs (SLA thresholds, performance-review cadence)
- Cross-functional coordination rules (how handoffs happen between DM, Monitoring, Safety, Stats)

**Examples (illustrative, not exhaustive):**
- "Verify that contact information for the main contact at each named vendor or lab is uploaded to the eTMF."
- "Verify that a CV for the main contact at each vendor where a CV is required is uploaded to the eTMF."
- "Verify that the country-specific entity responsible for regulatory submissions executed those submissions in its assigned countries."
- "Verify that the Principal Investigator signed the site blinding plan before the first patient was enrolled in the randomization phase at that site."
- "Verify that the Pharmacovigilance Plan was signed and approved by the Sponsor prior to the First Subject First Visit."
- "Verify that minutes from the Blind Data Review Meeting were signed by both the CRO and the Sponsor before the Database Hard Lock."
- "Verify that all Source Data Verification was completed and all data queries resolved before the Close Out Visit was marked complete."
- "Verify that the Database Lock occurred within one month of the Last Patient Last Visit."
- "Verify that the Sponsor signed the Database Lock Approval form authorizing the lock."
- "Verify that sites did not begin any screening activities before receiving the Regulatory Green Light via documented email communication."
- "Verify that the named Essential Documents Tracker was maintained throughout the study and filed in the TMF at study end."
- "Verify that the Trial Master File was maintained electronically and no parallel hard-copy file was kept."

**Pattern hints — CSMP-specific extraction guidance:**
- **Responsibility splits expand into multiple KRIs.** When the doc says "Entity X for region A, Entity Y for region B," extract one KRI per (entity × responsibility × region). Do not collapse into a single rule.
- **Approval gates are everywhere.** Every "X must be approved/signed by Y before Z" is one KRI. Scan for verbs: "approve", "sign", "review", "endorse", "authorize" — each combined with a milestone.
- **Trackers have a 3-part lifecycle.** For each named tracker, extract: (1) it exists, (2) it is maintained per the stated cadence, (3) it is filed in the TMF at end of study. Three KRIs minimum per tracker.
- **Vendor rules multiply by number of vendors named.** A blanket "contact info for the main contact at each lab is uploaded to eTMF" becomes one KRI per named lab. The CSMP usually enumerates them.
- **Country-specific extra steps are common.** When one country/region has additional requirements that others don't, extract a separate KRI per country (or one KRI scoped to that country) — never bury in a "global" rule.
- **Cross-doc echoes are expected.** CSMP frequently restates rules from the IMP Manual / PV Plan / SAP at the process level. Extract them anyway — the Stage 5a dedup-vs-protocol step (and the no-cross-accompanying-doc-dedup design) handles redundancy correctly downstream.

**What to ignore:**
- Organization-chart content (unless it imposes a monitorable responsibility)
- Generic project-management philosophy and rationale paragraphs
- Boilerplate SOP cross-references that impose no specific action
- TMF section index numbering / formatting standards (unless tied to a deliverable obligation)
- Pure contact lists with no associated obligation

---

## IMP — IMP Handling Manual

**What it is.** Defines how the Investigational Medicinal Product is received, stored, prepared, administered, returned, and destroyed. Covers shipment receipt, temperature storage and excursions, accountability, expiry/retest, dose preparation, equipment handling (water baths, thermometers, alarms), visual integrity inspection, blinding logistics during preparation and injection, sponsor release gates, complaint/escalation, and dispense/disposal documentation.

**Key KRI categories:**
- Storage temperature ranges and freezer alarm thresholds (°C limits, alarm bounds)
- Temperature excursion detection, reporting windows, and quarantine handling
- Shipment receipt workflow (timestamp of receipt, timestamp of opening, ID matching, data-logger handling, EDC upload of forms)
- Sponsor release gate (quarantine until sponsor verifies temperature compliance and releases for clinical use)
- Accountability reconciliation (received vs dispensed vs returned vs disposed, with documentation)
- Expiry / retest date verification at each use, including selection rules (e.g., earliest expiry first)
- Dose preparation steps (selection, tagging, thawing, mixing, aspiration volume, port handling)
- Equipment specifics — water bath (target temp ±tolerance, thermometer placement, stabilization wait, cleaning), freezer thermometer calibration, alarm system calibration
- Stability windows — split into separate KRIs per window (total at room temperature, post-aspiration in syringe, dry-ice shipper time limit)
- Timestamp capture obligations — every handoff in the IMP lifecycle is its own timestamp KRI (receipt, opening, removal from storage, thawing start, thawing end, aspiration, administration interruptions)
- Dual-verification chains — kit ID vs shipment form, Dispense PDF vs label vs patient number, performed at multiple stages
- Visual integrity inspection — bag/cassette damage (cracks, tears, holes, seals), post-thaw inspection, cell clumps/aggregates immediately before injection
- Disinfection procedures — port wipe, injection-site swab (alcohol concentration, dwell time, dry time)
- Manual labeling and tagging — site-completed primary labels (subject + visit number with permanent marker), patient-number kit tags
- Blinding integrity in preparation — separate preparation area, delegated unblinded preparer, syringe masking when injector is blinded
- Blinding integrity in administration — blinded staff exclusion during injection, patient view screen, injector role separation from baseline/follow-up assessments
- Emergency unblinding procedures and timelines
- Document/PDF lifecycle — EDC uploads (shipment form PDF, data-logger output PDF, dispense PDF), patient binder filing, ISF monthly temperature printout
- Anesthesia and injection-site restrictions (e.g., prohibited routes/sites, needle replacement immediately before injection)
- Returned / unused IMP handling, disposal documentation, retention of empty packaging for CRA accountability
- Destruction documentation requirements
- Damaged-IMP and complaint workflow — halt-and-quarantine, complaint form path, sponsor notification

**Examples (illustrative, not exhaustive):**
- "Verify that the time of IMP shipment receipt was documented on the shipment form."
- "Verify that the temperature data-logger reading was downloaded and reviewed before the IMP was released for clinical use."
- "Verify that the sponsor confirmed shipment temperature was within the specified storage range before releasing the IMP from quarantine."
- "Verify that the IMP unit selected for the subject had the earliest expiry date among available units."
- "Verify that the kit ID on the dispense record matches the kit ID on the unit label and the assigned subject number."
- "Verify that the IMP was administered within the specified total room-temperature stability window from the end of thawing to completion of injection."
- "Verify that the IMP was administered within the specified post-aspiration stability window from syringe fill to completion of injection."
- "Verify that the syringe was masked before reaching a blinded injector when the study is blinded."
- "Verify that any defect or damage identified during IMP integrity inspection was reported via the sponsor's complaint form and the unit was quarantined."
- "Verify that the freezer alarm system was set to the temperature limits specified in the IMP Manual."

**Pattern hints — IMP-specific extraction guidance:**
- **Timestamp obligations are a pattern, not a single rule.** Every handoff in the IMP lifecycle (receipt, opening, removal, thaw start, thaw end, aspiration, administration) typically has its own timestamp-capture rule. Scan for them all and emit one KRI per handoff.
- **Dual-verification chains are common.** When the doc says "verify X matches Y," extract one KRI per verification step — even if multiple verifications appear in one paragraph.
- **Blinding rules are scattered, not centralized.** Search the entire document for "blind", "unblinded", "masked", "delegated" — relevant rules appear in preparation, administration, and access-control sections. Don't expect one "Blinding" section.
- **Equipment rules become multiple KRIs.** A single piece of equipment (water bath, thermometer, alarm) typically generates several KRIs: target setting, calibration, placement/use procedure, cleaning/maintenance.
- **Stability windows must be split.** Total room-temperature stability and post-aspiration stability are distinct KRIs even if mentioned in one sentence.

**What to ignore:**
- Generic pharmacology / mechanism-of-action background
- Full chemical structure or formulation chemistry
- Manufacturer address / contact info (unless it's an escalation target embedded in a rule)
- Regulatory framework boilerplate that imposes no site-level action

---

## PDHP — Protocol Deviation Handling Plan

**What it is.** Defines how protocol deviations are identified, documented, classified, reviewed, reported, and remediated. Often paired with the PD Classification Guide but distinct: PDHP is the *process*, PD Classification Guide is the *taxonomy*.

**Key KRI categories:**
- Deviation identification responsibilities (who finds them, how they're captured)
- Documentation windows (PD must be logged within N days of identification/occurrence)
- Classification process (who classifies, when, review requirements)
- Escalation rules by classification level (major → sponsor within N days; critical → immediate)
- Root-cause analysis requirements
- CAPA timelines
- Sponsor/IRB/EC/regulatory reporting rules
- Trend analysis / recurring-deviation triggers
- Database / deviation log entry requirements

**Examples (illustrative):**
- "Verify that every protocol deviation was entered into the deviation log within 5 business days of identification."
- "Verify that every major deviation received a root-cause analysis before closure."
- "Verify that critical deviations were reported to the Sponsor Medical Monitor within 24 hours of identification."

**What to ignore:**
- Generic definitions of what a "protocol deviation" is (unless they impose a check)
- Philosophical/regulatory-context statements

---

## PV_PLAN — Pharmacovigilance Plan

**What it is.** Defines how adverse events, serious adverse events, SUSARs, and safety signals are captured, reviewed, coded, reported, and reconciled. Covers SAE timelines, MedDRA coding rules, expedited reporting, DSUR/PSUR obligations, reconciliation with clinical database.

**Key KRI categories:**
- SAE reporting timelines (site → sponsor, sponsor → regulatory) by seriousness/expectedness
- SUSAR expedited reporting windows (7-day for fatal/life-threatening, 15-day otherwise — confirm against doc)
- MedDRA coding / medical review cadence
- Reconciliation rules between clinical and safety databases (frequency, tolerance)
- Follow-up requirements for ongoing SAEs
- Line-listing and aggregate reporting cadence
- Signal detection process and thresholds
- DSUR / PSUR preparation windows
- Safety Committee cadence
- IRB / EC / regulatory reporting rules

**Examples (illustrative):**
- "Verify that every SAE was reported from site to sponsor within 24 hours of site awareness."
- "Verify that every SUSAR met regulatory expedited-reporting requirements (7-day fatal/life-threatening; 15-day otherwise)."
- "Verify that safety-database / clinical-database reconciliation was performed at least quarterly."
- "Verify that every SAE narrative was medically reviewed before locking the case."

**What to ignore:**
- Generic pharmacovigilance terminology definitions
- Regulatory-framework history sections

---

## SAP — Statistical Analysis Plan

**What it is.** Defines the statistical methodology for the trial: analysis populations, primary/secondary endpoint analyses, handling of missing data, interim analyses, adjustments for multiplicity, subgroup analyses, sensitivity analyses.

**Key KRI categories:**
- Analysis population definitions and inclusion/exclusion rules (ITT, mITT, PP, Safety, PK)
- Primary endpoint analysis method (test, model, significance level)
- Secondary endpoint hierarchy and multiplicity-adjustment rule
- Missing-data handling rules (imputation method, tipping-point analysis, PMM, etc.)
- Interim analysis triggers (timing, stopping rules, alpha spending)
- Subgroup analysis definitions
- Sensitivity analyses required
- Data cutoffs and lock triggers
- Handling of COVID / external impact deviations (if present)
- Derived variable definitions that require monitoring (baseline windows, last-observation rules)
- Analyses required at specific visits/timepoints

**Examples (illustrative):**
- "Verify that analysis of the primary endpoint uses the ITT population as defined in Section 3.1."
- "Verify that missing primary-endpoint data is handled using Multiple Imputation with 100 draws per subject."
- "Verify that subjects with <80% treatment compliance are excluded from the Per-Protocol population."
- "Verify that the interim analysis was triggered when 50% of target events were accrued."

**What to ignore:**
- Pure background statistical theory (unless it becomes a binding rule)
- Sections marked "for information only" or "not part of the primary analysis"

---

## PD_CLASS — Protocol Deviation Classification Guide

**What it is.** The taxonomy document. Defines categories and severity levels for protocol deviations with specific criteria for each. Typically a large table or hierarchical list.

**Key KRI categories:**
- Category-level definitions (informed consent, eligibility, study procedures, IMP handling, safety reporting, data integrity, etc.)
- Severity level criteria (Critical / Major / Minor — or the document's own scheme) with specific trigger conditions per category
- Concrete thresholds that determine severity (e.g., "missing a Week-12 visit by >14 days = Major")
- Patient-impact criteria
- Data-integrity-impact criteria
- Reporting consequence per category/severity (which triggers expedited sponsor/regulatory notification)

**Examples (illustrative):**
- "Verify that any eligibility-criterion violation was classified as Critical."
- "Verify that any missed primary-endpoint assessment visit was classified as Major."
- "Verify that any IMP dose administered to the wrong subject was classified as Critical."
- "Verify that any deviation with patient-safety impact was classified as Critical regardless of category."

**What to ignore:**
- The document's own definition of "what a protocol deviation is" (covered by PDHP)
- Process statements about HOW to classify (covered by PDHP) — extract only the *criteria*, not the *process*

**Important:** PD_CLASS and PDHP frequently overlap. Cross-check with the protocol golden set AND remember that dedup happens in Stage 5 — at extraction time, favor recall over precision.
