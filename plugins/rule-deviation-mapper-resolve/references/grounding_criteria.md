# Grounding Criteria — what is "protocol-grounded"?

For every facet you want to add (or every No-match theme), classify it before proposing.

## GROUNDED — author / extend
1. **Stated in the protocol body** — the requirement appears in the protocol text, a section (§), or a Schedule-of-Activities footnote. Quote it.
2. **Incorporation by reference (delegation)** — the protocol explicitly hands the operational detail to a **named document** (laboratory manual, pharmacy manual, RTSM, Precision Motion Study Manual, digital biomarker manual, imaging manual). In that case:
   - The **binding requirement you encode is "comply with the named manual / per Table X"** — that sentence is protocol text, so it IS grounded.
   - You **may not** copy specific items out of that manual/CRF into the rule **as named protocol requirements** — that reaches past the protocol. The manual/CRF supplies the specifics; the protocol only points to it.
   - A named example borrowed from the manual/CRF/deviation (e.g. a specific sub-task) is **not** protocol text. If you include one for readability, mark it clearly as an example, and prefer the general phrase ("all required components per the Manual"). If strict protocol-only purity is required, **omit the named example** and keep only "per the Manual" — it still catches the omission because the Manual defines the components.

## NOT GROUNDED — leave uncovered
Anything in the `core_principles.md` "leave uncovered" catalogue: GCP/ICF-template details, manual/SOP/vendor specifics, CMP/monitoring-plan rules, administrative-letter numbers that contradict the protocol, within-tolerance events, inferred-not-confirmed events, mis-logged deviations, measurement-science standards the protocol doesn't state.

## The decision-point escalation rule (do NOT decide alone)
When the protocol is **ambiguous**, or the only way to catch a cited line is **stricter than the protocol allows**, or there is a genuine design fork — **present it to the user as an explicit choice with a recommendation.** Never silently pick. Frame it as:
- **Option A (protocol-faithful)** — what the protocol strictly supports (usually the recommendation).
- **Option B (stricter / beyond protocol)** — what the deviation/sponsor implies, clearly labelled as going beyond the protocol.
Examples seen in practice:
- A conditional requirement gated on the protocol (e.g. triplicate only if OLE-enrolling) vs. flagging it unconditionally as the sponsor did → present A/B.
- A window the protocol sets at 14 days vs. an administrative-letter 7 days → recommend keeping 14, ask.
- An "assessment yields usable result" availability facet (groundable by analogy) vs. a specific timing number from a manual → add the general availability, leave the manual number, flag it.
- Whether to add a facet that covers **zero** cited deviations purely for parity → ask.

## Self-audit before proposing
Re-walk **every** cited line against the proposed rule text. Confirm: each line's underlying principle is captured; no facet was missed; every "left uncaught" line has a stated reason. Only then present the traceability table.
