"""
Phase 2 Layer 4 + Layer 5 — Semantic match panel + inverse coverage audit.

Layer 4: 6-agent panel (3 Claude Sonnet + 3 Gemini 2.5 Pro) reviews each
change unit's shortlist and flags conceptually-affected KRIs. See prompt
P2L4 in references/prompts.md.

Layer 5: for change units with zero matches across L1-L4, ask the panel
whether v2 introduces a new obligation requiring a new KRI. See prompt P2L5.

Output: affected_kris.json — the consolidated per-change KRI mapping with
per-match layer + confidence + explanations.
"""

from __future__ import annotations

import json
from pathlib import Path


def run_layer_4_and_5(
    change_set: dict,
    golden: dict | list,
    l1_3: dict[str, list[dict]],
    shortlists: dict[str, list[str]],
    out_dir: Path,
) -> dict:
    """
    Builds inputs for the 6-agent panel and the inverse-audit panel, dispatches
    them via subagents, and aggregates verdicts into affected_kris.json.
    """
    raise NotImplementedError(
        "semantic_match_panel.run_layer_4_and_5 is not yet implemented. Flow:\n"
        "  1. For each change_id with a non-empty shortlist:\n"
        "       - Build panel input (change unit + shortlist KRIs).\n"
        "       - Dispatch P2L4 prompt to 3 Claude subagents + 3 Gemini calls in parallel.\n"
        "       - Aggregate per consensus table in SKILL.md Phase 2 Layer 4.\n"
        "  2. For each change_id with zero matches in (L1-L3 ∪ L4 ≥4/6):\n"
        "       - Dispatch P2L5 prompt to single Claude call.\n"
        "       - Record requires_new_kri / no_action_required.\n"
        "  3. Consolidate L1-L3 matches + L4 matches + L5 audit into affected_kris.json.\n"
        "  4. Group KRIs hit by ≥5 changes for single-pass interactive review."
    )
