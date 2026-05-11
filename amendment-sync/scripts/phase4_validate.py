"""
Phase 4 — Validation passes against the new document.

  4.1 Verbatim verification (100%, BLOCKING) — full working set vs new doc.
       Reuses protocol-kri-extractor/scripts/step3d_verify.py.
  4.2 Accuracy panel (scoped to disposition in {EDITED, SPLIT, MERGE, NEW}).
       Reuses protocol-kri-extractor/scripts/step3b_accuracy.py.
  4.3 Dedup pass (100%, MANDATORY).
       Reuses protocol-kri-extractor/scripts/step4a_dedup.py.
  4.4 NDEF sweep (100%, MANDATORY).
       Reuses protocol-kri-extractor/scripts/step4a_ndef_sweep.py.

The reuse is direct: this skill does not reimplement extractor logic. The
extractor's scripts are imported (or invoked as subprocesses) so any
upstream refinement to the extractor's quality bar propagates here
automatically.
"""

from __future__ import annotations

import json
from pathlib import Path


EXTRACTOR_SCRIPTS = Path(
    "~/.claude/skills-repo/protocol-kri-extractor/scripts"
).expanduser().resolve()


def run_phase4_validation(new_doc: Path, working_golden: Path, out_dir: Path) -> None:
    """
    Sequence: 4.1 (blocking) → 4.2 (blocking on scoped subset) → 4.3 → 4.4.

    Each step writes its report under out_dir/. Failures in 4.1 or 4.2 trigger
    the corrective sub-loop (re-anchor or edit) per SKILL.md Phase 4.
    """
    raise NotImplementedError(
        f"phase4_validate.run_phase4_validation is not yet implemented.\n"
        f"Expected extractor scripts at: {EXTRACTOR_SCRIPTS}\n"
        "Steps:\n"
        "  1. Invoke step3d_verify.py --pdf <new_doc> --json <working_golden>\n"
        "       Required: 100% pass. Failures → surface to user for REANCHOR/EDIT.\n"
        "  2. Filter working_golden to disposition ∈ {EDITED, SPLIT, MERGE, NEW} and\n"
        "     invoke step3b_accuracy.py on the subset against <new_doc>.\n"
        "       Required: 0 FAIL, 0 unresolved FLAG.\n"
        "  3. Invoke step4a_dedup.py on working_golden (full set).\n"
        "  4. Invoke step4a_ndef_sweep.py on working_golden (full set).\n"
        "  5. Write phase4_summary.json with per-step pass/fail + report paths."
    )
