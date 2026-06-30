# Core Principles

## The protocol-only doctrine (the heart of this skill)
- The **protocol PDF is the single source of truth.** Nothing else — not the sponsor's deviation log, not the CRF, not a Clinical Monitoring Plan, not a vendor/lab/study manual, not an administrative letter — overrides or substitutes for it.
- The deviation mapping is a **diagnostic**, not a work order. Its job is to let us **verify that our rules catch the correct (protocol-grounded) deviations.** It is NOT a list of things we must make the rules catch.
- **Sponsors log deviations that aren't protocol deviations.** A logged deviation may rest on an administrative letter, a manual, a CRF field, a monitoring-plan rule, or simple human error. If the protocol doesn't ground it, it is **irrelevant to us** and we **do not** change or add a rule for it.
- **Never bend a rule to absorb a deviation.** We expand a rule only to the extent the protocol supports. If a deviation can only be "caught" by asserting something the protocol doesn't say, we leave it uncaught and say why.

## Edit-scope rules
- **Phase 1 (Extend partial) and Track A:** edit the **`Rule for LLM` cell only**. Never another column, never an unrelated rule, never add/delete a rule.
- **Track B (No match):** may **add a NEW rule**, but only (a) where the protocol grounds it and (b) in the **exact existing Golden-Set format** (all columns).
- Preserve everything else in the rule: analyte/component lists, `conditional` carve-outs (ESD-at-V9 investigator discretion; "applies only if subject has a primary caregiver"; etc.), `trigger`s, and the existing key structure.

## Expand, don't narrow
- Rules must catch the *type* of deviation, not the specific incident. Phrase clauses as general principles ("any out-of-range result not annotated CS/NCS"), not as the cited example ("subject 15544001's …").
- Illustrative examples are allowed for readability, BUT a named example drawn from a deviation/CRF/manual (e.g. a specific sub-task name) is **not** protocol text — see `grounding_criteria.md` "incorporation by reference". Prefer the protocol-grounded general phrase; add a named example only when it's clearly marked as an example and the user accepts it.

## Honest reporting (always)
- State **how many** cited lines a fix actually catches vs. doesn't (totals).
- When a fix covers **fewer** lines than it appears to, say so.
- When a deviation is **mis-logged** (e.g. an assessment "not done" at a visit where it isn't scheduled) or **out of scope**, say so plainly.
- When an edit covers **zero** cited deviations but is correct on protocol grounds (parity/consistency), say that explicitly — the justification is the protocol, not a deviation.

## The "leave uncovered" catalogue (do NOT author rules for these)
A deviation is correctly left uncovered when its requirement is not in the protocol. Common categories:
- **GCP / ICH / ICF-template details** the protocol doesn't state: time-of-signature, printed-name/DOB/checkbox fields, GCP correction-initialing, "full legal name", reimbursement-form elections.
- **Manual / SOP / operational specifics:** kit versions, lab requisition-form correctness, eCOA-vendor device/session forms (e.g. "Caregiver Completion Form", "Continuation/Visit-End" questionnaires), specific sub-task names defined only in a study manual/CRF.
- **CMP / Clinical-Monitoring-Plan requirements:** e.g. "SDV the first patient before screening the next." (Signal: the deviation says "the CRA informed the site" / "site was not aware of this requirement".)
- **Administrative-letter numbers that contradict the protocol:** e.g. a 7-day window asserted when the protocol says up to 14 days. Keep the protocol's number.
- **Within-tolerance events:** an offset that is inside the protocol's own window; a "delay" that is still inside the screening cap. Not a deviation per the protocol.
- **Inferred-not-confirmed events:** e.g. a "suspected overdose" inferred from a returned-pill discrepancy, when the protocol defines overdose as a *recorded dose* above the ceiling.
- **Mis-logged deviations:** an assessment "not done" at a visit/timepoint where the protocol never scheduled it.
- **PRO/measurement-science standards** the protocol doesn't state (e.g. "validated native-language translation") when the protocol only requires the participant *understand* the information.

For each, record where it *would* legitimately come from (CMP → accompanying-doc extractor; study manual / CRF → manual-sourced rule set; etc.).

## Binary / EDC-testability
- Domain rules that are evaluated against EDC data (e.g. SOA) are kept **binary and EDC-checkable**.
- Operational/governance obligations that are NOT EDC-field checks (confidentiality, attributability, personnel training, registry registration, IDMC oversight) live in the **OPS domain** and are observational/monitoring checks. That is the OPS standard — distinct from the binary EDC standard for assessment domains. New Track-B operational rules belong in OPS.
