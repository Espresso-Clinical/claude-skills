#!/usr/bin/env python3
"""
amendment-sync — canonical orchestrator.

Single entry point that runs Phase 1 → Phase 5 in order, enforcing the
blocking gates documented in SKILL.md.

Phase order:
  preflight  -> Verify v1 Golden Set corresponds to old document (10-quote sample, >=9 verbatim).
  phase1     -> Change detection (Path A amendment table + Path B section-aligned diff).
  phase2     -> Affected-KRI mapping (5-layer matching).
  phase3     -> Interactive review loop (the user-facing core).
  phase4     -> Verbatim verification + scoped accuracy panel + dedup + NDEF sweep.
  phase5     -> Save versioned outputs + migration report.

Blocking gates (pipeline exits non-zero if any fail):
  preflight  -> mismatched Golden Set
  phase4.1   -> verbatim verification must reach 100% pass on full v2 working set
  phase4.2   -> accuracy panel must reach 0 FAIL / 0 unresolved FLAG on changed/new subset

Resumable: --resume reads decisions.jsonl + change_set.json from --out and
continues the interactive loop where it stopped.
"""

import argparse
import json
import os
import sys
from pathlib import Path


PHASES = ["preflight", "phase1", "phase2", "phase3", "phase4", "phase5"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Update a Golden Set to a new document version.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--old-doc", required=True, help="Path to old document PDF.")
    p.add_argument("--new-doc", required=True, help="Path to new document PDF.")
    p.add_argument(
        "--golden",
        required=True,
        help="Path to v1 extracted_kris.json OR the run directory containing it.",
    )
    p.add_argument(
        "--new-version",
        required=True,
        help="New document version label (e.g., v4.0, Amendment-3). "
        "Used in output filenames.",
    )
    p.add_argument(
        "--doc-type",
        choices=["protocol", "accompanying"],
        default="protocol",
        help="Source document type. Selects extractor prompts/sub-areas at Phase 3.2/3.3.",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Output directory (canonical: ~/Downloads/amendment-sync/<protocol_id>/<old>_to_<new>/).",
    )
    p.add_argument(
        "--from",
        dest="from_phase",
        choices=PHASES,
        default="preflight",
        help="Resume from a specific phase.",
    )
    p.add_argument(
        "--only",
        choices=PHASES,
        help="Run only a single phase (for debugging).",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted interactive session — reads decisions.jsonl and skips already-decided changes.",
    )
    p.add_argument(
        "--show-speculative-matches",
        action="store_true",
        help="Surface Layer 4 low-confidence (2-3/6) semantic matches in the interactive review.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Phase 1 + Phase 2 only. Produce change_set.json and affected_kris.json; skip the interactive loop.",
    )
    return p.parse_args()


def resolve_golden(path_arg: str) -> Path:
    """--golden may be a file or a run directory; resolve to the extracted_kris.json file."""
    p = Path(path_arg).expanduser().resolve()
    if p.is_file():
        return p
    if p.is_dir():
        candidate = p / "extracted_kris.json"
        if candidate.exists():
            return candidate
        raise SystemExit(f"--golden directory does not contain extracted_kris.json: {p}")
    raise SystemExit(f"--golden path does not exist: {p}")


def ensure_outdir(path_arg: str) -> Path:
    out = Path(path_arg).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# Phase implementations are dispatched to sibling scripts. The orchestrator
# imports them lazily so a single failing import does not break the whole CLI.
# ---------------------------------------------------------------------------


def run_preflight(args, out_dir: Path, golden_path: Path) -> None:
    """Pre-flight integrity check: 10-quote sample, >=9 must match the old doc."""
    from preflight import verify_golden_matches_old_doc

    result = verify_golden_matches_old_doc(
        old_doc=Path(args.old_doc).expanduser().resolve(),
        golden=golden_path,
        sample_size=10,
        min_passes=9,
    )
    (out_dir / "preflight_report.json").write_text(json.dumps(result, indent=2))
    if not result["pass"]:
        raise SystemExit(
            f"PREFLIGHT FAIL: only {result['passes']}/{result['sample_size']} v1 quotes "
            f"matched the old document verbatim. Verify that --golden corresponds to --old-doc."
        )
    print(f"preflight: {result['passes']}/{result['sample_size']} quotes verified — PASS")


def run_phase1(args, out_dir: Path) -> None:
    """Phase 1 — Change detection (dual-path)."""
    from amendment_table_parser import parse_amendment_table
    from section_aligned_diff import compute_section_aligned_diff
    from change_merger import merge_change_sources

    print("phase1: parsing amendment-history table (Path A)...")
    amendment_changes = parse_amendment_table(
        new_doc=Path(args.new_doc).expanduser().resolve(),
        out_dir=out_dir,
    )

    print("phase1: computing section-aligned diff (Path B)...")
    diff_changes = compute_section_aligned_diff(
        old_doc=Path(args.old_doc).expanduser().resolve(),
        new_doc=Path(args.new_doc).expanduser().resolve(),
        out_dir=out_dir,
    )

    print("phase1: merging into change_set.json...")
    merge_change_sources(
        amendment_changes=amendment_changes,
        diff_changes=diff_changes,
        out_dir=out_dir,
    )


def run_phase2(args, out_dir: Path, golden_path: Path) -> None:
    """Phase 2 — Affected-KRI mapping (5-layer)."""
    from kri_matcher import run_layers_1_to_3
    from kri_embedder import build_shortlists
    from semantic_match_panel import run_layer_4_and_5

    change_set = json.loads((out_dir / "change_set.json").read_text())
    golden = json.loads(golden_path.read_text())

    print("phase2: running Layers 1-3 (deterministic match)...")
    l1_3 = run_layers_1_to_3(
        change_set=change_set,
        golden=golden,
        old_doc=Path(args.old_doc).expanduser().resolve(),
        out_dir=out_dir,
    )

    print("phase2: building embedding shortlists...")
    shortlists = build_shortlists(
        change_set=change_set,
        golden=golden,
        already_matched=l1_3,
        top_k=30,
        out_dir=out_dir,
    )

    print("phase2: running Layer 4 semantic panel + Layer 5 inverse audit...")
    run_layer_4_and_5(
        change_set=change_set,
        golden=golden,
        l1_3=l1_3,
        shortlists=shortlists,
        out_dir=out_dir,
    )


def run_phase3(args, out_dir: Path, golden_path: Path) -> None:
    """Phase 3 — Interactive review loop."""
    from interactive_review import run_interactive_loop

    run_interactive_loop(
        change_set=json.loads((out_dir / "change_set.json").read_text()),
        affected_kris=json.loads((out_dir / "affected_kris.json").read_text()),
        golden_path=golden_path,
        old_doc=Path(args.old_doc).expanduser().resolve(),
        new_doc=Path(args.new_doc).expanduser().resolve(),
        doc_type=args.doc_type,
        out_dir=out_dir,
        resume=args.resume,
        show_speculative=args.show_speculative_matches,
    )


def run_phase4(args, out_dir: Path) -> None:
    """Phase 4 — verbatim verification + accuracy panel + dedup + NDEF."""
    # Phase 4 reuses the extractor's scripts directly. We invoke them as
    # subprocesses (or via import if the extractor is on sys.path) so this
    # skill never duplicates that logic.
    from phase4_validate import run_phase4_validation

    run_phase4_validation(
        new_doc=Path(args.new_doc).expanduser().resolve(),
        working_golden=out_dir / "golden_set_working.json",
        out_dir=out_dir,
    )


def run_phase5(args, out_dir: Path) -> None:
    """Phase 5 — save versioned outputs + migration report."""
    from migration_report import assemble_versioned_outputs

    assemble_versioned_outputs(
        out_dir=out_dir,
        new_version=args.new_version,
    )


def main() -> None:
    args = parse_args()
    out_dir = ensure_outdir(args.out)
    golden_path = resolve_golden(args.golden)

    # Ensure sibling scripts are importable when run.py is launched directly.
    sys.path.insert(0, str(Path(__file__).parent.resolve()))

    phases_to_run = (
        [args.only]
        if args.only
        else PHASES[PHASES.index(args.from_phase) :]
    )

    if args.dry_run:
        phases_to_run = [p for p in phases_to_run if p in ("preflight", "phase1", "phase2")]
        print(f"dry-run: phases = {phases_to_run}")

    dispatch = {
        "preflight": lambda: run_preflight(args, out_dir, golden_path),
        "phase1": lambda: run_phase1(args, out_dir),
        "phase2": lambda: run_phase2(args, out_dir, golden_path),
        "phase3": lambda: run_phase3(args, out_dir, golden_path),
        "phase4": lambda: run_phase4(args, out_dir),
        "phase5": lambda: run_phase5(args, out_dir),
    }

    for phase in phases_to_run:
        print(f"\n=== {phase} ===")
        dispatch[phase]()

    print("\ndone.")


if __name__ == "__main__":
    main()
