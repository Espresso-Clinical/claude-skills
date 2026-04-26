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

**What it is.** Governs the overall operational conduct of the study across all functions: project governance, committee cadence, vendor oversight, timelines, risk management process, meeting structure, documentation structure, TMF filing.

**Key KRI categories:**
- Governance committee cadence (frequency, membership, quorum)
- Meeting minutes filing windows
- TMF completeness and filing deadlines (documents filed within N days of generation)
- Vendor oversight KPIs (SLA thresholds, performance-review cadence)
- Risk register update cadence
- Study milestone timelines and deviation triggers
- Escalation paths for operational issues
- Cross-functional coordination rules (how handoffs happen between DM, Monitoring, Safety, Stats)

**Examples (illustrative):**
- "Verify that the Study Management Team meeting minutes were filed to the TMF within 5 business days of each meeting."
- "Verify that the study risk register was reviewed and updated at least every quarter."
- "Verify that every vendor SLA breach was logged in the issue tracker and escalated to the Vendor Oversight Lead."

**What to ignore:**
- Organization-chart content (unless it imposes a monitorable responsibility)
- Contact lists
- Generic project-management philosophy

---

## IMP — IMP Handling Manual

**What it is.** Defines how the Investigational Medicinal Product is received, stored, dispensed, prepared, administered, returned, and destroyed. Covers temperature storage, accountability, shipment handling, retest dates, expiry, returns, destruction, excursion handling.

**Key KRI categories:**
- Storage temperature ranges (°C thresholds, exception handling)
- Temperature excursion reporting windows and thresholds
- Shipment receipt checks (temperature log review, quantity reconciliation, integrity checks)
- Accountability reconciliation rules (dispensed vs returned, tolerance thresholds)
- Expiry / retest date tracking
- Dose preparation rules (diluent, timing, light exposure, stability windows)
- Dispensing documentation requirements
- Returned / unused IMP handling
- Destruction documentation requirements
- Blinding integrity rules (for blinded studies)
- Emergency unblinding procedures and timelines

**Examples (illustrative):**
- "Verify that any temperature excursion outside the storage range was reported to the sponsor within 24 hours of detection."
- "Verify that site accountability logs reconcile received - dispensed - returned with zero unexplained variance."
- "Verify that no IMP was dispensed after its expiry or retest date."
- "Verify that reconstituted drug was administered within the specified in-use stability window (per dilution instructions)."

**What to ignore:**
- Generic pharmacology information
- Full chemical structure descriptions
- Manufacturer address/contact info

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
