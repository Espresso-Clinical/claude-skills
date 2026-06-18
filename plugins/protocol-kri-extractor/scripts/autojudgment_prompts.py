"""
Prompts for Step 2.6 auto-judgment (6-judge neutral panel).

The panel replaces the manual Phase-2 decision table with an automated pre-
decision on every T2 + T3-promoted candidate. It does NOT use personas — all
6 judges (Gemini 3.5 Flash, thinking-high; run at a temperature spread for
independence) share the same CRA-framed judgment prompt to stay consistent with
the 10-agent extraction panel's framing.

Step 2.6 decides INCLUSION in the Golden Set. It is distinct from:
  - Step 3B accuracy judging (decides CORRECTNESS, runs post-assembly on 100%)
  - Step 3.5 orphan scan (discovers MISSED rules)
"""


# ─── Shared guardrail block (inherited by every judge prompt) ────────────────
SHARED_GUARDRAIL_BLOCK = """
GUARDRAILS — apply to every KRI you judge:

1. **Verbatim anchor**: reject if `supporting_quote` is not a near-verbatim substring
   of the cited protocol page. Fabrication is a hard reject.

2. **Atomicity**: reject if the KRI is non-atomic (combines multiple verifiable checks,
   multiple time points, multiple analytes, or multiple populations into one rule).
   Respect the atomization-of-compound-clauses refinement: always-true clauses,
   illustrative-example splits, and single-field range splits are atomicity violations.

3. **Domain boundary**: respect the in-scope domain boundaries — Rule 2 (SAF owns
   thresholds + response), Rule 3 (OPS owns methodology), ELIG owns inclusion/
   exclusion criteria, END owns endpoint and governance rules. **Rule 1 — SOA is
   OUT OF SCOPE for this skill (handled by `soa-kri-extractor`).** If a candidate
   KRI is essentially "procedure happened at visit Y", "visit X within ±N days",
   or any other SOA-flavored pattern, REJECT with reason "out_of_scope_soa".

4. **Do NOT reject for non-binariness, vagueness, or being definitional/conditional/
   judgment-based.** This skill does NOT filter non-binary rules — that happens
   downstream (Quality Rule 15). The user filters them later. KEEP (never reject for
   this reason):
     - definitional rules ("X is defined as ...", "X does not include ...") — Quality Rule 14
     - conditional rules and permissions ("permitted if stable", "only when instructed")
     - investigator- or sponsor-decision rules ("in the investigator's opinion",
       "according to Sponsor instruction", "as clinically appropriate")
     - qualitative protocol wording ("as soon as possible") — preserve it verbatim
   Reject ONLY for the reasons in guardrails 1–3 and 5.

5. **Coverage**: if the KRI duplicates an approved Tier-1 KRI already covered by
   the deterministic dedup filter, it should already have been caught by Layer 2.
   If you see a duplicate pair the filter missed, flag it.

Return valid JSON with no markdown fences, no prose, no extra text.
"""


# ─── Neutral judge prompt — same for all 6 judges (6 Gemini 3.5 Flash) ───────
JUDGE_PROMPT = """You are a clinical research associate (CRA) and protocol expert judging whether a candidate KRI (Key Risk Indicator) should be included in the Golden Set for a clinical trial protocol.

You receive ONE candidate KRI at a time, along with the extraction-panel vote count and per-layer auto-judgment results. Based on:
  - the KRI's `kri_name` and `description` (the verifiable requirement + its specifics),
  - its `supporting_quote` and `protocol_reference`,
  - its atomicity (one check per rule),
  - whether it is a genuine protocol statement (obligation, permission, condition, definition, or governance rule),

decide one of three verdicts:
  - "accept" — the KRI captures a real protocol statement, atomic, faithfully framed. It need NOT be binary or quantitative — definitional, conditional, and judgment-based rules are acceptable.
  - "reject" — ONLY for: the `supporting_quote` is fabricated / not on the cited page; the KRI is not a real protocol statement (invented); it is SOA out-of-scope; or it is a true duplicate of an approved KRI. Do NOT reject merely because a rule is non-binary, vague, definitional, conditional, or judgment-based.
  - "conditional" — the KRI is close to acceptable but needs a minor edit (note the edit in your reason)

Provide a ONE-sentence reason (≤25 words) citing specific protocol wording or the specific guardrail that informs your vote.

Return JSON: {"vote": "accept"|"reject"|"conditional", "reason": "<one sentence>"}
""" + SHARED_GUARDRAIL_BLOCK


# ─── Panel structure constants (single source of truth for Step 2.6) ─────────
# Item 1: all panel judges are Gemini 3.5 Flash (thinking-high). The Claude count
# is retained as 0 only so any external importer of the name doesn't break.
N_CLAUDE_JUDGES = 0
N_GEMINI_JUDGES = 6
N_PANEL_TOTAL = N_GEMINI_JUDGES  # 6

# Aggregate decision thresholds (Layer 4):
#   ≥5 accept AND ≤1 reject → auto_approve
#   ≥5 reject AND ≤1 accept → auto_reject
#   Anything else           → flag for review (defaults to REJECT at Phase-4;
#                                              user reviews end-of-run table)
L4_AUTO_APPROVE_ACCEPT_MIN = 5
L4_AUTO_APPROVE_REJECT_MAX = 1
L4_AUTO_REJECT_REJECT_MIN = 5
L4_AUTO_REJECT_ACCEPT_MAX = 1
