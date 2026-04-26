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

**What it is.** Defines how the sponsor/CRO monitors the trial: monitoring strategy and responsibility splits, visit types and frequency, on-site CRA behavioral expectations, Source Data Verification (SDV) and Source Data Review (SDR) scopes and caps, remote vs on-site monitoring, Risk-Based Monitoring (RBM) triggers, site escalation paths, the multi-stage report lifecycle for each report type, regulatory-gating-at-the-monitoring-level (e.g., RGL before screening), informed-consent timing relative to first visit, visit-bound CRA tasks (collect named logs, review named forms), end-of-trial monitoring activities, special-circumstance review workflows (paper ePRO transcription, re-screening), required eCRF entry minimums for special cases (e.g., screen failures), composite status definitions (e.g., "fully monitored"), and document/email archival format requirements.

**Key KRI categories:**
- Monitoring responsibility split by country / region — when one entity monitors specific countries and another entity monitors others, extract one KRI per (entity × country/region)
- CRA on-site behavioral expectations — periodic actions the CRA must perform during on-site visits (e.g., email check at a defined cadence)
- Regulatory Green Light (RGL) — both the gating rule (no screening before RGL) AND the RGL signature timeline post-SIV; each is its own KRI
- Multi-stage report lifecycle per report type — every named report (SIV report, Monitoring Visit Report, Centralized Monitoring Report, Follow-Up Letter to PI, etc.) typically has draft / review / finalization stages with distinct timelines; extract one KRI per (report type × stage)
- Multiple report types with distinct cadences and recipients — SIV report, MVR, Centralized Monitoring Report (often monthly), Follow-Up Letter (FUL) to the PI
- SDV scope rules with quantitative thresholds — distinct KRIs per (data domain × percentage × deadline-or-cap). Examples: 100% SDV of AEs; 100% SDV of SAEs; 100% SDV of eligibility within N monitoring visits after inclusion; SDV percentages by CRF-page type, by visit, by endpoint category
- SDR scope caps — numeric limits on SDR work (e.g., not beyond Nth screen failure per site per phase); preserve the cap unit faithfully
- Special-circumstance review workflows — emergency paper ePRO transcription → CRA on-screen review → MVR documentation; re-screening with sponsor approval and reason recorded in source
- Required eCRF entry minimums for special cases — even when most procedures for a subject are skipped (e.g., screen failures), specific eCRF pages must still be entered. **Extract one KRI per required eCRF page** (atomic). Do not collapse the list.
- Visit-bound CRA tasks — actions the CRA must perform AT each monitoring visit (collect named logs, review named forms, perform named SDV activities); each task is its own KRI
- Re-screening documentation rules — sponsor decision and reason recorded in source documents
- ICF timing relative to first visit — pre-visit / at-visit and always before any study procedure
- IMP-related monitoring activities — collection of blinded IMP temperature logs at each visit; review and SDV of named injection/administration logs
- End-of-trial monitoring activities — final IMP accountability post-Database Lock; completion of named Reconciliation and Destruction form
- "Fully monitored" composite status definition — multi-condition criterion (no further visits expected + SDR completed + essential pages SDV'ed + no outstanding queries/reports). **Extract one KRI per condition** (atomic). Optionally one additional KRI verifying the composite-status flag was set only when all conditions were met.
- Email / document archiving format requirements — specific format mandated for metadata retention (e.g., .msg or equivalent)
- Visit type definitions and frequency (Site Initiation, routine, interim, close-out; on-site vs remote) — and visit-window rules
- Monitoring visit windows (must be completed within a defined interval of a named trigger)
- Risk-trigger thresholds (data query rate, PD rate, AE reporting lag, enrollment rate, etc.) and the action they trigger
- Site escalation rules — when to escalate, to whom, within what window
- Action-item / CAPA closure windows from monitoring findings
- Monitor qualifications and training requirements (qualifications, study-specific training, refresher cadence)
- Co-monitoring / oversight rules
- Working-day vs calendar-day distinctions — preserve the unit faithfully whenever the doc names one

**Examples (illustrative, not exhaustive):**
- "Verify that monitoring activities at sites in each country were performed by the entity assigned to that country in the CMP."
- "Verify that the CRA performed the on-site behavioral activities mandated by the CMP at the cadence specified (e.g., email check during on-site visits)."
- "Verify that the site received the Regulatory Green Light before initiating any subject screening."
- "Verify that the Regulatory Green Light form was signed within the timeline specified after the Site Initiation Visit."
- "Verify that the first draft of the Site Initiation Visit report was sent to the reviewer within the timeline specified."
- "Verify that the first draft of each Monitoring Visit Report was sent to the reviewer within the timeline specified."
- "Verify that each Monitoring Visit Report was finalized within the timeline specified."
- "Verify that the Follow-Up Letter to the Principal Investigator was provided within the timeline specified after each monitoring visit."
- "Verify that the Centralized Monitoring Report was generated and finalized within the timeline specified after the data extraction date."
- "Verify that 100% Source Data Verification was completed for every reported Adverse Event."
- "Verify that 100% Source Data Verification was completed for every reported Serious Adverse Event."
- "Verify that 100% SDV for subject eligibility was completed within the number of monitoring visits specified after subject inclusion."
- "Verify that no Source Data Review was performed beyond the cap defined in the CMP for screen-failed subjects per site per phase."
- "Verify that for subjects whose ePROs were entered on paper under emergency circumstances, the CRA performed an on-screen review and documented it in the Monitoring Visit Report."
- "Verify that each eCRF page required for screen-failed subjects under the CMP was fully entered (one KRI per required page)."
- "Verify that for any re-screened subject, the source documents contained the sponsor's approval decision and the reason for re-screening."
- "Verify that the Informed Consent Form was signed before any study procedure was performed."
- "Verify that the CRA collected the blinded IMP temperature logs at each on-site monitoring visit."
- "Verify that the Reconciliation and Destruction form was completed by the CRA during final IMP accountability after Database Lock."
- "Verify that each individual condition required for a subject to be marked as 'fully monitored' was independently satisfied (one KRI per condition)."
- "Verify that required email correspondence was archived in the format mandated by the CMP for metadata retention."

**Pattern hints — CMP-specific extraction guidance:**
- **Multi-stage report lifecycle expands per (report type × stage).** For each named report (SIV / MVR / Centralized / FUL / etc.), expect distinct draft, review, and finalization timelines; extract each stage as its own KRI rather than collapsing into one rule.
- **SDV/SDR scope rules expand into multiple KRIs.** For each named data domain (AEs / SAEs / eligibility / primary endpoint / etc.), the doc usually specifies a percentage and a deadline or cap. Extract one KRI per (domain × scope × deadline-or-cap). Do not collapse "100% of AEs and SAEs" into one rule when the doc states them separately.
- **Visit-bound CRA tasks expand into multiple KRIs** — one per discrete task the CRA must perform at each visit (collect named log A, review named form B, perform SDV on domain C). Do not collapse multiple visit-bound tasks into one "do everything at every visit" rule.
- **Even-when-X-still-do-Y rules are easy to miss.** Screen-failure required pages, emergency paper ePRO on-screen review, re-screening documentation — these sound like exceptions but they are real obligations. Extract them.
- **Composite status definitions split into multiple KRIs.** "Fully monitored" with N conditions becomes N KRIs (one per condition), plus optionally one composite-flag KRI. Per the atomicity principle, default to splitting; do not collapse a list of conditions into a single rule.
- **Country-specific monitoring overrides expand into per-country KRIs** (same pattern as PV / PDHP / CSMP).
- **Working-day vs calendar-day matters** — preserve units faithfully in `rule_for_llm` and `supporting_quote`.
- **RGL has two distinct rules** — the gating rule (no screening before RGL) AND the RGL signature timeline (post-SIV). Extract both, not just the gate.
- **Behavioral expectations during visits** (email-check cadence, attendance requirements, etc.) are real KRIs even though they feel like soft expectations — they are explicit obligations in the CMP.

**What to ignore as noise:**
- Generic background statements ("Monitoring is an important activity in clinical trials…")
- Definitions sections that do not impose an obligation
- Boilerplate references to ICH GCP without specific site-level action
- Pure organizational descriptions of monitoring teams unless they assign a monitorable responsibility

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
- Study-milestone timelines and deviation triggers (e.g., Database Lock within a defined window after Last Patient Last Visit)
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

**What it is.** Defines how protocol deviations are identified, captured, classified, reviewed, reported, escalated, archived, and remediated. Names the source-of-truth system for PD reporting, the standardized PD term vocabulary, the per-classification reporting timelines, the reviewer responsibilities by classification, the review cadence and start triggers, country-specific reporting/oversight overrides, file/system hygiene rules for the PD report artefact, training requirements by audience, and the process prohibitions (e.g., no prospective waivers). Paired with the PD Classification Guide but distinct: PDHP is the *process*, PD Classification Guide is the *taxonomy*.

**Key KRI categories:**
- Source-of-truth declaration — the named system (typically the eCRF/EDC) is the official source for PD reporting; downstream documentation derives from it
- Standardized PD term vocabulary — restricted list of approved PD terms; the assigned term in the system must match the approved list exactly (one KRI per "matches approved list" check; do not enumerate the list as separate KRIs)
- Field-level reporting rules — specific values required for specific fields under specific conditions (e.g., a defined value must be selected when a PD occurs between visits)
- Deviation identification responsibilities (who finds them, how they're captured)
- Reporting timelines split by classification severity — distinct KRIs per (severity tier × timeline unit). Working-day timelines and clock-hour timelines are different obligations; preserve the unit faithfully.
- Classification doubt-resolution path — when a PD's classification is unclear, consult a named role
- Final classification deadline — tied to a named study milestone (e.g., before Database Lock; no later than Blind Data Review Meeting)
- Bidirectional reclassification notifications — Minor→Major notification to a named recipient by a named notifier; Major→Minor notification to a named recipient by a (potentially different) named notifier. Each direction is its own KRI.
- Two-tier reviewer responsibilities — different roles review PDs of different classifications (e.g., one role reviews Major, another reviews Minor)
- Review cadence + start trigger — first PD review starts a defined interval after a named milestone (e.g., FSFV); subsequent reviews at a defined cadence
- Sponsor independent periodic review — sponsor's own internal PD review meetings, separate from the CRO/site review cycle
- Country-specific reporting overrides — when one jurisdiction names a different role as the PD reporter (e.g., CRA reports PDs instead of site staff), extract a per-country KRI
- Country-specific oversight overrides — when one jurisdiction has a different investigator review pattern (e.g., quarterly investigator acknowledgement specific to one country), extract a per-country KRI
- System hygiene rules for the PD report artefact:
  - Exact file path / location (file must reside at the specified location)
  - Naming preservation across review rounds (filename and location unchanged)
  - Single-actor restriction on a system action (e.g., only the review-round initiator may press a Refresh button)
  - Backup copy convention in a named sub-folder (e.g., .xls copy in a CTM folder)
  - Per-review-round filing (file at end of each round)
- Investigator oversight log — multi-step chained obligation (extract / print / review / sign / date / file in the ISF) at a fixed cadence. **Extract one KRI per step in the chain** (atomic). Each step (extract, print, review, sign, date, file) is its own verifiable check. Optionally add one composite KRI verifying the full chain was completed at the required cadence.
- Final approval gate — all PDs approved by a named role (e.g., Sponsor) before a named milestone (e.g., BDRM)
- Final TMF archival — final PD report including all review comments filed to the TMF at study end
- Training requirements split by audience — site staff (typically trained at SIV) and study team (typically trained before engagement AND before FSFV); both with documentation obligation
- Process prohibitions — explicit "shall not" rules (e.g., no prospective protocol waivers; no removal/renaming of the PD report file; no classification changes without site notification)
- Query handling timeline — separate KRI from the PD reporting timeline itself; queries on PDs must be resolved within a defined window
- Trend analysis / recurring-deviation triggers
- Root-cause analysis and CAPA timelines (when included in the PDHP rather than a separate quality plan)
- IRB / EC / regulatory reporting rules cross-referenced from this doc

**Examples (illustrative, not exhaustive):**
- "Verify that every Protocol Deviation is captured in the named source-of-truth system per the PDHP."
- "Verify that the PD term assigned to each deviation matches one of the approved standardized PD terms listed in the PDHP."
- "Verify that the field value for the related-visit attribute follows the rule defined for between-visit deviations."
- "Verify that every Minor PD was entered in the source system within the timeline specified for Minor PDs."
- "Verify that every Major PD was entered in the source system within the timeline specified for Major PDs."
- "Verify that the consultation with the named role occurred whenever a PD's classification was in doubt."
- "Verify that the final classification of all PDs was completed before the named study milestone specified in the PDHP."
- "Verify that site staff received the notification specified for Minor-to-Major reclassifications, from the notifier role named in the PDHP."
- "Verify that site staff received the notification specified for Major-to-Minor reclassifications, from the notifier role named in the PDHP (which may differ from the Minor-to-Major notifier)."
- "Verify that PDs classified as Major were reviewed by the role named in the PDHP for Major-PD review."
- "Verify that PDs classified as Minor were reviewed by the role named in the PDHP for Minor-PD review."
- "Verify that the first PD review occurred at the interval specified after the named milestone, and that subsequent reviews occurred at the specified cadence."
- "Verify that for the country with override rules, PD reporting was performed by the role named in the PDHP for that country."
- "Verify that the PD report file resides at the exact path specified in the PDHP and was not renamed or removed."
- "Verify that each step of the investigator oversight chain (extract, print, review, sign, date, file in ISF) was independently performed at the cadence specified in the PDHP — one KRI per step."
- "Verify that all PDs received final approval from the named role prior to the named milestone."
- "Verify that PD-handling training for site staff is documented in the Site Initiation Visit report."
- "Verify that PD-handling training for study team members is documented before their engagement in the study and before First Subject First Visit."

**Pattern hints — PDHP-specific extraction guidance:**
- **Two-tier severity timelines expand into multiple KRIs** — one per (classification × timeline unit). Working days and clock hours are distinct obligations.
- **Bidirectional reclassification notifications expand into two KRIs.** Each direction often has a different notifier role; do not collapse into one rule.
- **Two-tier reviewer responsibilities expand into multiple KRIs** — one per (classification × reviewer role).
- **Country-specific reporting/oversight overrides** are common — extract per-country KRIs whenever the doc names a country with different rules from the default.
- **System hygiene rules are easy to miss.** Single-actor button restrictions, file-path preservation, naming preservation, and backup-copy conventions are real obligations and become real KRIs.
- **Multi-step chained obligations** (extract-print-review-sign-date-file) split into one KRI per step. Per the atomicity principle, default to splitting. Optionally add one composite KRI for the full chain at the required cadence.
- **Training-documented-before-X is a recurring pattern.** Extract one KRI per (audience × event-trigger). Site staff at SIV is one KRI; study team before engagement is another; study team before FSFV is another (and may overlap with the engagement KRI — extract both, dedup downstream).
- **Process prohibitions are KRIs too.** "No prospective waivers", "do not rename the report file", "no classification changes without notification" — each is a verifiable obligation.

**What to ignore:**
- Generic definitions of what a "protocol deviation" is (unless the definition imposes a check)
- Philosophical / regulatory-context statements that impose no site-level action
- Pure organizational descriptions of teams unless they assign a monitorable PD-handling responsibility

---

## PV_PLAN — Pharmacovigilance Plan

**What it is.** Defines how adverse events, serious adverse events, SUSARs/SARs, pregnancies, and safety signals are captured, classified, reviewed, coded, reported, distributed, reconciled, and archived. Covers a multi-tier timeline matrix (event severity × jurisdiction × reporting phase), multi-party review chains, blinding integrity throughout the safety workflow, central unblinding rules, technical/system standards, reconciliation activities, pregnancy module, cross-trial sharing between unblinded teams, country-specific overrides, edge-case workflows, end-of-trial data transfer, and authorship/access restrictions.

**Key KRI categories:**
- PV Plan ownership — required signers/approvers and update triggers (e.g., update when new information available; minimum signature roster)
- Day 0 / clock-start definition — explicit verifiable rule for when a reporting clock begins (typically: first awareness by a defined party AND minimum criteria met)
- Initial site reporting — Investigator → safety responsible window, by event type and severity
- Multi-tier timeline matrix — distinct timelines per (event severity × jurisdiction × reporting phase: initial / draft / review / finalize / final report / follow-up). Each cell of the matrix is its own KRI. Examples of cells: unrelated-SAE draft to reviewers; potential-SUSAR draft (typically expedited); SAR draft; SUSAR/SAR evaluation by safety responsible; fatal/life-threatening finalize; standard-expedited finalize; final CIOMS readiness; follow-up information completion window
- Multi-party review chains — draft expedited report to Reviewer 1 (medical advisor) within window X AND Reviewer 2 (sponsor safety responsible) within window Y. Each reviewer × window is its own KRI.
- Country-specific timeline overrides — when a jurisdiction has stricter timelines than the default global rule, extract a separate per-country KRI for each affected event type
- Working-day vs calendar-day distinctions — when the doc names them, extract the unit faithfully (a "5 working days" rule is not the same as "5 calendar days")
- Weekend / holiday adjustment rules for cross-trial or cross-jurisdiction reporting
- SAE report minimum content — the doc usually lists the minimum fields required for an initial report (site/subject info, event term, causality, etc.); extract one KRI verifying the minimum content is present
- Causality and expectedness — Investigator's initial causality assessment must be present from first report; expectedness assessed by named role using a named reference document (e.g., current Investigator's Brochure)
- Causality downgrade prohibition — one-way constraint that a named role may not downgrade an Investigator's "related" classification
- Technical / system standards — Safety Database structure (e.g., E2B-R3 or equivalent), sequential SAE numbering convention starting at a defined index, eCRF SAE-page entry with explicit "Serious" mark, blinded vs unblinded report formats
- Blinding integrity in PV reporting (multi-KRI cluster):
  - Blinded re-submission of any report containing unblinding or personal information; deletion/blinding of original
  - Central unblinding restricted to a designated role (e.g., PVR) via a defined channel (e.g., eCRF)
  - Unblinding notifications to other roles must NOT reveal treatment allocation
  - Blinded version of finalized expedited reports for distribution
  - Stand-alone filing location for unblinded safety information with restricted access
  - Operational study staff barred from unblinded safety information
  - PI emergency unblinding notification to PVR/safety responsible without revealing the result
  - Unblinded subject tracking ledger (overview document of subjects unblinded + persons informed)
- Reconciliation activities — periodic SAE reconciliation; **for the minimum field list, extract one KRI per field** (each field is a discrete reconciliation check); pregnancy reconciliation across eCRF + dedicated form; un-finalised SAE follow-up queries
- Discrepancy query workflow — queries to Investigator with CRA copied; resolution responsibility
- Pregnancy module — notification timeline (regardless of whether an AE occurred); postpartum follow-up duration; submission channel; reconciliation
- Cross-trial / cross-program expedited sharing — expedited reports shared between unblinded teams across studies involving the same IMP; tiered timelines by severity; weekend/holiday adjustment; single-platform-submission rule (the originating party submits to the regulatory platform; the other does not, to avoid duplicates)
- Investigator Notification (IN) — generation responsibility, distribution path to all sites
- Significant safety findings — sponsor-to-CRO (or vice versa) notification window for newly identified safety findings
- DSUR / PSUR — authoring responsibility; submission responsibility per country; data transfer timeline from CRO to Sponsor (e.g., listings within X after cut-off); annual cadence
- Edge-case workflows — fax fallback during connectivity outage (with confirmation retention + email-on-restoration); follow-up email when an eCRF safety update does not warrant a full follow-up report
- Authorship restrictions — Unblinded Case Narratives for the CSR written exclusively by a named role (e.g., PVR)
- Filing access restrictions — electronic stand-alone filing for unblinded safety data with named role restriction
- End-of-trial Safety Database transfer — file format, transport mechanism, audit trail format, recipient
- Safety Committee / DSMB cadence (when referenced in PV Plan)
- IRB / EC / regulatory reporting rules cross-referenced from this doc

**Examples (illustrative, not exhaustive):**
- "Verify that the Pharmacovigilance Plan bears signatures from all required signers per the plan."
- "Verify that the Day 0 clock-start for an SAE is documented as the date the first qualifying party received the report and minimum criteria were met."
- "Verify that the Investigator reported the SAE to the named safety responsible within the timeline specified in the PV Plan."
- "Verify that the draft expedited report for a potential SUSAR was sent to the medical reviewer within the timeline specified for that event tier."
- "Verify that the draft expedited report was reviewed by the sponsor safety responsible within the timeline specified for that event tier."
- "Verify that the final expedited report was ready for regulatory submission by the deadline specified for its severity tier."
- "Verify that any expedited reporting deadline falling on a weekend or holiday was met by the last working day prior to the deadline."
- "Verify that any SAE report containing unblinding or personal information was re-submitted in blinded form and the original was deleted or blinded."
- "Verify that central unblinding was performed exclusively by the designated role through the channel specified in the PV Plan."
- "Verify that notifications of central unblinding to roles other than the central-unblinding role did not reveal the treatment allocation."
- "Verify that the Investigator's Brochure used for expectedness assessment was the version current at the time of the suspected reaction."
- "Verify that the periodic SAE reconciliation report compared each named minimum key safety field listed in the PV Plan (one KRI per field)."
- "Verify that the Pregnancy Notification Form was completed and sent within the timeline specified, regardless of whether an AE occurred."
- "Verify that the end-of-trial Safety Database transfer was delivered in the format and through the transport mechanism specified in the PV Plan."

**Pattern hints — PV-Plan-specific extraction guidance:**
- The PV Plan typically encodes a **timeline matrix** of (event severity × jurisdiction × reporting phase). Treat each cell as a separate KRI even when the source doc states multiple cells in one paragraph or table row.
- **Multi-party review chains expand into multiple KRIs** — one per reviewer, each with its own deadline.
- **Blinding rules in PV are scattered.** Search the entire document for "blind", "unblind", "treatment allocation", "stand-alone", "access" — relevant rules appear in handling, distribution, filing, narratives, and end-of-trial sections, not in a single "Blinding" section.
- **Country-specific timelines override global timelines.** Whenever a jurisdiction has stricter rules than the default, extract a separate per-country KRI rather than burying the override.
- **Working-day vs calendar-day matters.** A "5 working days" rule is materially different from "5 calendar days". Preserve the unit faithfully in `rule_for_llm` and `supporting_quote`.
- **Weekend/holiday adjustment is its own KRI** — separate from the base timeline rule.
- **Reconciliation field lists split into one KRI per field.** Per the atomicity principle, each field is a discrete check on a discrete data element. Do not collapse the list into a single rule. A field with its own additional obligation (e.g., "causality must be present from initial report") still gets that obligation extracted as a separate KRI on top of the reconciliation-coverage KRI for the same field.
- **Cross-trial sharing rules** typically include a single-platform-submission-by-originator rule. Extract that rule explicitly — it prevents duplicate regulatory submissions.

**What to ignore:**
- Generic pharmacovigilance terminology definitions (unless the definition imposes an obligation)
- Regulatory-framework history sections
- Background on ICH / GVP / E2B standards (extract only when they convert into a specific site or sponsor action)
- Pure organizational descriptions of teams unless they assign a monitorable responsibility

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
