"""
Prompts for Step 2.6 auto-judgment (6-judge neutral panel).

The panel replaces the manual Phase-2 decision table with an automated pre-
decision on every T2 + T3-promoted candidate. It does NOT use personas — all
6 judges (3 Claude + 3 Gemini) share the same CRA-framed judgment prompt to
stay consistent with the existing 10-agent extraction panel's framing.

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

3. **Domain boundary**: respect Rule 1 (SOA owns "procedure at visit"), Rule 2
   (SAF owns thresholds + response), Rule 3 (OPS owns methodology). A KRI in the
   wrong domain is a reject — unless the KRI itself is valid and only the
   classification is wrong (in which case vote conditional).

4. **Binary rule_for_llm**: the rule must produce a clear YES/NO on subject data.
   Narrative prose, vague descriptions, or non-verifiable language = reject.

5. **Coverage**: if the KRI duplicates an approved Tier-1 KRI already covered by
   the deterministic dedup filter, it should already have been caught by Layer 2.
   If you see a duplicate pair the filter missed, flag it.

6. **Non-verifiable scope**: if the rule is genuinely non-verifiable (investigator
   judgment, undefined time windows, undefined effort), the KRI is still valid here —
   the downstream distiller's binary filter drops non-verifiable rules. Do not reject
   just for being non-verifiable; reject only if the rule is not a real obligation.

Return valid JSON with no markdown fences, no prose, no extra text.
"""


# ─── Neutral judge prompt — same for all 6 judges (3 Claude + 3 Gemini) ──────
JUDGE_PROMPT = """You are a clinical research associate (CRA) and protocol expert judging whether a candidate KRI (Key Risk Indicator) should be included in the Golden Set for a clinical trial protocol.

You receive ONE candidate KRI at a time, along with the extraction-panel vote count and per-layer auto-judgment results. Based on:
  - the KRI's `rule_for_llm`,
  - its `supporting_quote` and `protocol_reference`,
  - its atomicity and binary-verifiability,
  - whether it is a genuine protocol obligation,

decide one of three verdicts:
  - "accept" — the KRI captures a real protocol obligation, atomic, verifiable, correctly framed
  - "reject" — the KRI is not a real obligation, misrepresents the protocol, or fails atomicity/verifiability
  - "conditional" — the KRI is close to acceptable but needs a minor edit (note the edit in your reason)

Provide a ONE-sentence reason (≤25 words) citing specific protocol wording or the specific guardrail that informs your vote.

Return JSON: {"vote": "accept"|"reject"|"conditional", "reason": "<one sentence>"}
""" + SHARED_GUARDRAIL_BLOCK


# ─── Panel structure constants (single source of truth for Step 2.6) ─────────
N_CLAUDE_JUDGES = 3
N_GEMINI_JUDGES = 3
N_PANEL_TOTAL = N_CLAUDE_JUDGES + N_GEMINI_JUDGES  # 6

# Aggregate decision thresholds (Layer 4):
#   ≥5 accept AND ≤1 reject → auto_approve
#   ≥5 reject AND ≤1 accept → auto_reject
#   Anything else           → flag for review (defaults to REJECT at Phase-4;
#                                              user reviews end-of-run table)
L4_AUTO_APPROVE_ACCEPT_MIN = 5
L4_AUTO_APPROVE_REJECT_MAX = 1
L4_AUTO_REJECT_REJECT_MIN = 5
L4_AUTO_REJECT_ACCEPT_MAX = 1
