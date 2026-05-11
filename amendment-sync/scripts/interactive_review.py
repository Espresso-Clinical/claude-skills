"""
Phase 3 — Interactive review loop.

Walks the user through every change in change_set.json, presenting the
affected KRIs from affected_kris.json and capturing one of:
KEEP / REANCHOR / EDIT_MANUAL / EDIT_PANEL / SPLIT / MERGE / REMOVE / DEFER
per KRI. Decisions are appended to decisions.jsonl immediately and applied
to golden_set_working.json incrementally for crash-safety.

This module is driven by the orchestrator's parent agent — the actual
human dialog (questions, menus, side-by-side rendering of v1 vs v2 text)
happens in the agent's main conversation context, not via stdin. This
script provides the state machine, the decision log writer, the
working-Golden-Set mutation helpers, and the deferred-items final-pass
manager.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


DECISIONS = {
    "KEEP",
    "REANCHOR",
    "EDIT_MANUAL",
    "EDIT_PANEL",
    "SPLIT",
    "MERGE",
    "REMOVE",
    "DEFER",
}


def run_interactive_loop(
    change_set: dict,
    affected_kris: dict,
    golden_path: Path,
    old_doc: Path,
    new_doc: Path,
    doc_type: str,
    out_dir: Path,
    resume: bool,
    show_speculative: bool,
) -> None:
    """
    State machine for the interactive loop. The orchestrator's parent agent
    invokes the per-change render + per-KRI decision steps via SendMessage /
    AskUserQuestion. This function manages the on-disk state.
    """
    raise NotImplementedError(
        "interactive_review.run_interactive_loop is not yet implemented. The runtime\n"
        "shape is:\n"
        "  1. Initialize golden_set_working.json from --golden (copy) if not present.\n"
        "  2. Initialize decisions.jsonl (touch) if not present.\n"
        "  3. If --resume, read decisions.jsonl and build a set of already-decided\n"
        "     (change_id, kri_id) pairs.\n"
        "  4. For each change in change_set.changes (skip pairs already decided):\n"
        "       a. Render change to user (via parent agent).\n"
        "       b. For each affected KRI (filtered by show_speculative):\n"
        "            - Render KRI.\n"
        "            - Ask user for decision (one of DECISIONS).\n"
        "            - Apply decision to golden_set_working.json (helpers below).\n"
        "            - Append JSON line to decisions.jsonl.\n"
        "       c. If change is requires_new_kri, run Phase 3.3 net-new flow.\n"
        "  5. Final pass: revisit DEFER items.\n"
        "  6. Stamp version_metadata on every KRI in golden_set_working.json.\n"
        "\n"
        "Apply helpers needed (each mutates golden_set_working.json on disk):\n"
        "  - apply_keep(kri_id, change_id, reason)\n"
        "  - apply_reanchor(kri_id, change_id, new_quote, new_ref, new_combined_ref)\n"
        "  - apply_edit(kri_id, change_id, fields_changed, new_values)\n"
        "  - apply_split(kri_id, change_id, new_kris)\n"
        "  - apply_merge(kri_ids, change_id, merged_kri)\n"
        "  - apply_remove(kri_id, change_id, reason)\n"
        "  - apply_new(kri_id, change_id, new_kri)"
    )
