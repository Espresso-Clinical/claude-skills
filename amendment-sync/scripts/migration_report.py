"""
Phase 5 — Save versioned outputs and assemble the migration report.

Reads decisions.jsonl + change_set.json + affected_kris.json +
golden_set_working.json + the Phase 4 reports, then writes:

  golden_set_<new_version>.json
  Extracted_KRIs_<new_version>.xlsx   (via extractor's step4a_assemble.py)
  migration_report.json
  removed_kris.json                   (KRIs marked REMOVE)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def assemble_versioned_outputs(out_dir: Path, new_version: str) -> None:
    """
    Final assembly. Invoked by run.py after Phase 4 succeeds.
    """
    raise NotImplementedError(
        "migration_report.assemble_versioned_outputs is not yet implemented. Flow:\n"
        "  1. Read golden_set_working.json.\n"
        "  2. Strip working-only fields (e.g., transient flags), keep version_metadata.\n"
        "  3. Save as golden_set_<new_version>.json.\n"
        "  4. Invoke protocol-kri-extractor/scripts/step4a_assemble.py to write\n"
        "     Extracted_KRIs_<new_version>.xlsx with the standard 7-column layout.\n"
        "  5. Aggregate decisions.jsonl + change_set.json + affected_kris.json +\n"
        "     Phase 4 reports into migration_report.json with these sections:\n"
        "       _meta: protocol_id, old_version, new_version, timestamps, counts\n"
        "       changes_summary: total + per semantic_kind + per source\n"
        "       kri_summary: unchanged / edited / split / merged / removed / new\n"
        "       per_kri: full before/after for every changed KRI\n"
        "       validation: phase4 step-by-step pass/fail\n"
        "  6. Extract REMOVE decisions into removed_kris.json with rationale.\n"
        "  7. Print the final summary block (see SKILL.md Phase 5)."
    )
