#!/usr/bin/env python3
"""
Protocol KRI Extractor — Deterministic Full Pipeline Runner

Executes every documented step in the exact order defined by SKILL.md, and
enforces the three blocking gates (Step 3.5 orphan scan, Step 3B full accuracy
judging, Step 3D verbatim verification). If any blocking gate fails, the
pipeline stops immediately with a non-zero exit code — you must resolve the
blocking issue and re-run from the failing step before continuing.

This script is the SINGLE CANONICAL ENTRY POINT for the pipeline. Both manual
invocation and skill-driven invocation should go through here. It guarantees
the documented order and prevents any step from being silently skipped.

Usage — direct (recommended, matches SKILL.md CLI):
  python run.py --pdf /path/to/protocol.pdf --out /path/to/output/
  python run.py --pdf ... --out ... --golden /path/to/golden_set.json
  python run.py --pdf ... --out ... --from 3.5
  python run.py --pdf ... --out ... --only 3b

Usage — legacy registry (the 3 internal test protocols):
  python run.py ENX-CL-05-002
  python run.py B1481038 --compare
  python run.py LCZ696G2301 --from 2

Step order (from SKILL.md Phase 1 → Phase 4):
  1a         Manifest
  1b-camelot Camelot SoA table extraction (PRIMARY)
  1b         SoA ontology build
  1c         Deterministic footnote mapper (subprocess — needs --table-pages/--fn-pages)
  2          KRI extraction (per domain, multi-model panel)
  3.5        Protocol-wide orphan scan                     [BLOCKING]
  3a         Completeness check
  3a+        Clinical heuristics (H1-H10, inside 3a script)
  3b         Full KRI accuracy judging (100%, 5-judge panel) [BLOCKING]
  3c         Consistency check
  3d         Full verbatim pdfplumber verification            [BLOCKING]
  2.6        Auto-judgment for T2 + T3-promoted KRIs (6-judge neutral panel)
  4a         Assembly + Excel
  4a-dedup   Cross-domain + intra-domain de-duplication
  4a-ndef    Post-extraction NDEF sweep (moves non-definable KRIs into NDEF)
  4a-flagged End-of-run cross-domain flagged-review table (user review)
  4b         Golden set comparison (optional)
"""

import sys
import os
import argparse
import json
import time
import subprocess

# Ensure 'scripts' directory is importable when run from any cwd
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ─── Legacy registry (internal test protocols) ──────────────────────────────
LEGACY_PROTOCOLS = {
    "ENX-CL-05-002": {
        "pdf": "/mnt/user-data/uploads/ENX-CL-05-002_Clinical_Study_Protocol_v_2_0_Agatha_copy.pdf",
        "dir": "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002",
        "golden": "/mnt/user-data/uploads/golden_set.json",
    },
    "B1481038": {
        "pdf": "/mnt/user-data/uploads/Protocol_B1481038.pdf",
        "dir": "/home/claude/protocol-kri-extractor/output/B1481038",
        "golden": None,
    },
    "LCZ696G2301": {
        "pdf": "/mnt/user-data/uploads/Novartis__LCZ696G2301-_Phase_3_study_to_evaluate_the_efficacy_and_safety_of_LCZ696pdf.pdf",
        "dir": "/home/claude/protocol-kri-extractor/output/LCZ696G2301",
        "golden": None,
    },
}


# ─── Step catalog ───────────────────────────────────────────────────────────
# Canonical order. Each entry: (step_id, description, is_blocking)
STEP_CATALOG = [
    ("1a",          "Manifest — cover pages + TOC → section map",                 False),
    ("1b-camelot",  "Camelot SoA table extraction (PRIMARY)",                     False),
    ("1b",          "SoA ontology build",                                         False),
    ("1c",          "Deterministic footnote mapper (Step 1C)",                    False),
    ("2",           "KRI extraction (per-domain, multi-model panel)",             False),
    ("2.6",         "Auto-judgment for T2 + T3-promoted KRIs (6-judge panel)",    False),
    ("3.5",         "Protocol-wide orphan scan (3 Claude + 3 Gemini)",            True),
    ("3a",          "Completeness + clinical heuristics H1–H10",                  False),
    ("3b",          "Full KRI accuracy judging (100%, 5-judge panel)",            True),
    ("3c",          "Consistency check",                                          False),
    ("3d",          "Full verbatim pdfplumber verification",                      True),
    ("4a",          "Assembly (extracted_kris.json + Excel)",                     False),
    ("4a-dedup",    "Cross-domain + intra-domain dedup",                          False),
    ("4a-ndef",     "Post-extraction NDEF sweep (6-judge panel)",                 False),
    ("4a-flagged",  "End-of-run flagged-review table (cross-domain consolidate)", False),
    ("4b",          "Golden set comparison (optional)",                           False),
]

STEP_ORDER = [s[0] for s in STEP_CATALOG]
STEP_DESC = {s[0]: s[1] for s in STEP_CATALOG}
BLOCKING_STEPS = {s[0] for s in STEP_CATALOG if s[2]}


def step_num(s: str) -> float:
    """Sort key for step ordering. Matches STEP_ORDER sequence exactly."""
    try:
        return float(STEP_ORDER.index(s))
    except ValueError:
        return 99.0


# ─── Blocking-gate helper ──────────────────────────────────────────────────
class BlockingGateFailed(Exception):
    """Raised when a blocking step fails. Stops the pipeline immediately."""

    def __init__(self, step_id, reason):
        self.step_id = step_id
        self.reason = reason
        super().__init__(f"Blocking gate failed at Step {step_id}: {reason}")


def enforce(step_id, ok, reason=""):
    """If a blocking step returned False, raise; otherwise continue."""
    if step_id in BLOCKING_STEPS and not ok:
        raise BlockingGateFailed(step_id, reason or "step returned failure")


# ─── Step runners ──────────────────────────────────────────────────────────
def run_step_1a(pdf, out_dir, **kw):
    from step1a_manifest import build_manifest
    print(f"\n[ Step 1A — {STEP_DESC['1a']} ]")
    protocol_id = kw.get("protocol_id") or os.path.basename(pdf).rsplit(".", 1)[0]
    manifest = build_manifest(pdf, protocol_id)
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved {manifest_path}")
    return True


def run_step_1b_camelot(pdf, out_dir, **kw):
    try:
        from camelot_table_extractor import run_extraction as camelot_run
    except Exception as e:
        print(f"  ⚠ Step 1B-Camelot: import failed — {e}. Skipping (non-blocking).")
        return True
    print(f"\n[ Step 1B-Camelot — {STEP_DESC['1b-camelot']} ]")
    try:
        camelot_run(pdf, out_dir)
    except Exception as e:
        print(f"  ⚠ Camelot extraction errored — {e}. Continuing without SoA table.")
    return True


def run_step_1b_ontology(pdf, out_dir, **kw):
    from step1b_ontology import build_ontology, print_summary
    print(f"\n[ Step 1B — {STEP_DESC['1b']} ]")
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    ontology = build_ontology(pdf, manifest)
    ontology_path = os.path.join(out_dir, "ontology.json")
    with open(ontology_path, "w") as f:
        json.dump(ontology, f, indent=2, ensure_ascii=False)
    print_summary(ontology)
    print(f"  ✓ Saved {ontology_path}")
    return True


def run_step_1c(pdf, out_dir, **kw):
    print(f"\n[ Step 1C — {STEP_DESC['1c']} ]")
    # Derive SoA table pages and footnote pages from soa_table.json if available
    soa_json = os.path.join(out_dir, "soa_table.json")
    if not os.path.exists(soa_json):
        print("  ⚠ soa_table.json missing — run Step 1B-Camelot first. Skipping 1C.")
        return True
    try:
        with open(soa_json) as f:
            soa_data = json.load(f)
        table_pages = sorted(set(soa_data.get("pages", []) or []))
        # Footnote pages — typical protocol puts them on the pages following the table.
        # Conservative default: same pages as table + next 5 pages.
        if not table_pages:
            print("  ⚠ soa_table.json has no pages field — skipping 1C.")
            return True
        fn_start = table_pages[-1]
        fn_end = fn_start + 5
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "footnote_mapper.py"),
            "--pdf", pdf,
            "--table-pages", ",".join(str(p) for p in table_pages),
            "--fn-pages", f"{fn_start}-{fn_end}",
            "--out", out_dir,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ⚠ footnote_mapper exited {result.returncode} — continuing without 1C.")
            print(f"    stderr: {result.stderr[-500:]}")
        else:
            print(result.stdout.strip()[-800:])
    except Exception as e:
        print(f"  ⚠ Step 1C errored — {e}. Continuing without footnote map.")
    return True


def run_step_2(pdf, out_dir, **kw):
    from step2_extract import run_extraction
    print(f"\n[ Step 2 — {STEP_DESC['2']} ]")
    manifest_path = os.path.join(out_dir, "manifest.json")
    ontology_path = os.path.join(out_dir, "ontology.json")
    cats = kw.get("categories")
    run_extraction(pdf, manifest_path, ontology_path, out_dir, cats)
    return True


def run_step_3_5(pdf, out_dir, **kw):
    from step3_5_orphan_scan import run_orphan_scan
    print(f"\n[ Step 3.5 — {STEP_DESC['3.5']} ]  (BLOCKING)")
    passed = run_orphan_scan(out_dir, pdf)
    if not passed:
        print("\n  ✗ Step 3.5 BLOCKED — user decisions pending.")
        print("  Review orphan_scan_report.json, resolve USER_DECISION items, then")
        print("  re-run with: --from 3.5")
    return bool(passed)


def run_step_3a(pdf, out_dir, **kw):
    from step3a_completeness import run_completeness_check
    print(f"\n[ Step 3A/3A+ — {STEP_DESC['3a']} ]")
    manifest_path = os.path.join(out_dir, "manifest.json")
    ontology_path = os.path.join(out_dir, "ontology.json")
    run_completeness_check(out_dir, manifest_path, ontology_path)
    return True


def run_step_3b(pdf, out_dir, **kw):
    from step3b_accuracy import run_full_accuracy_judging
    print(f"\n[ Step 3B — {STEP_DESC['3b']} ]  (BLOCKING, 100% coverage)")
    passed = run_full_accuracy_judging(out_dir, pdf)
    if not passed:
        print("\n  ✗ Step 3B BLOCKED — resolve all FAIL and FLAG items in")
        print("  accuracy_report_full.json, then re-run with: --from 3b")
    return bool(passed)


def run_step_3c(pdf, out_dir, **kw):
    from step3c_consistency import run_consistency_check
    print(f"\n[ Step 3C — {STEP_DESC['3c']} ]")
    ontology_path = os.path.join(out_dir, "ontology.json")
    run_consistency_check(out_dir, pdf, ontology_path)
    return True


def run_step_3d(pdf, out_dir, **kw):
    print(f"\n[ Step 3D — {STEP_DESC['3d']} ]  (BLOCKING, 100% verbatim)")
    # Step 3D runs against extracted_kris.json which is produced by Step 4A.
    # But SKILL.md specifies 3D runs BEFORE 4A. The convention is that 3D can
    # operate on raw_*.json merged on-the-fly, OR on extracted_kris.json if
    # 4A already ran. Here we merge raw_*.json into a temporary file for 3D,
    # then let 4A produce the canonical extracted_kris.json afterwards.
    import pathlib
    try:
        from step3d_verify import verify_all
    except Exception as e:
        print(f"  ✗ Step 3D import failed — {e}")
        return False

    # Build a temporary merged KRI set from raw_*.json
    merged = {"kris": []}
    for domain in ["SOA", "ELIG", "SAF", "END", "OPS", "NDEF"]:
        path = os.path.join(out_dir, f"raw_{domain}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        kris = data.get("kris", data) if isinstance(data, dict) else data
        merged["kris"].extend(kris)

    if not merged["kris"]:
        print("  ✗ Step 3D — no KRIs found in raw_*.json")
        return False

    tmp_path = os.path.join(out_dir, "_step3d_merged.json")
    with open(tmp_path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    try:
        results = verify_all(pdf, tmp_path)
    except Exception as e:
        print(f"  ✗ Step 3D errored — {e}")
        return False

    n_fail = len(results.get("fail", []))
    n_pass = len(results.get("pass", []))
    n_auto = len(results.get("auto_corrected", []))
    total = n_pass + n_fail
    print(f"  PASS: {n_pass}/{total}  AUTO-CORRECTED: {n_auto}  FAIL: {n_fail}")

    # Save a copy of the report
    report_path = os.path.join(out_dir, "verify_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Blocking: 100% pass required
    if n_fail > 0:
        print("\n  ✗ Step 3D BLOCKED — fix failing quotes in raw_*.json, then re-run --from 3d")
        return False
    return True


def run_step_4a(pdf, out_dir, **kw):
    from step4a_assemble import run_assembly
    print(f"\n[ Step 4A — {STEP_DESC['4a']} ]")
    manifest_path = os.path.join(out_dir, "manifest.json")
    run_assembly(out_dir, manifest_path)
    return True


def run_step_4a_dedup(pdf, out_dir, **kw):
    print(f"\n[ Step 4A-Dedup — {STEP_DESC['4a-dedup']} ]")
    # TODO(implementation): There is no standalone dedup script yet — the dedup
    # logic is currently documented in SKILL.md and performed by the skill agent
    # at runtime (or folded into step4a_assemble.py in future). This step is a
    # placeholder that logs the requirement; the actual dedup is currently the
    # agent's responsibility per SKILL.md "Step 4A-Dedup — Two-pass Detection".
    print("  (Dedup logic handled by the skill agent per SKILL.md §4A-Dedup.)")
    print("  (Cross-domain pass + intra-domain pass + kept_despite_similarity audit.)")
    dedup_stub = os.path.join(out_dir, "dedup_report.json")
    if not os.path.exists(dedup_stub):
        with open(dedup_stub, "w") as f:
            json.dump({
                "_meta": {
                    "note": "Stub written by run.py. Replace with real dedup_report.json "
                            "once the dedup script is implemented."
                },
                "cross_domain": [],
                "intra_domain": [],
                "kept_despite_similarity": [],
            }, f, indent=2, ensure_ascii=False)
    return True


def run_step_2_6(pdf, out_dir, **kw):
    """Step 2.6 — Auto-judgment for every T2 + T3-promoted KRI, per domain.

    Runs the 4-layer engine (verification, atomicity, coverage, 6-judge panel,
    aggregate) on raw_{DOMAIN}.json. Writes {domain}_autojudgment_report.json,
    {domain}_manual_review_decisions.json, {domain}_tier3_filtered.json.

    With --auto-approve-unanimous (default ON), pipeline does NOT block on
    flagged list — items defaulted to rejected and surfaced at end-of-run
    in Step 4A-FlaggedReview.
    """
    from step2_6_autojudgment import run_autojudgment_for_domain
    print(f"\n[ Step 2.6 — {STEP_DESC['2.6']} ]")
    auto = bool(kw.get("auto_approve_unanimous", True))
    domains = kw.get("categories") or ["SOA", "ELIG", "SAF", "END", "OPS"]
    if isinstance(domains, str):
        domains = [d.strip() for d in domains.split(",")]
    ok_all = True
    for domain in domains:
        raw_path = os.path.join(out_dir, f"raw_{domain}.json")
        if not os.path.isfile(raw_path):
            print(f"  (skip {domain} — raw_{domain}.json not present)")
            continue
        ok = run_autojudgment_for_domain(
            out_dir=out_dir, domain=domain, pdf_path=pdf,
            auto_approve_unanimous=auto,
        )
        ok_all = ok_all and ok
    return ok_all


def run_step_4a_flagged(pdf, out_dir, **kw):
    """Step 4A-FlaggedReview — end-of-run cross-domain consolidated table."""
    from step4a_flagged_review import run as run_flagged
    print(f"\n[ Step 4A-FlaggedReview — {STEP_DESC['4a-flagged']} ]")
    return run_flagged(out_dir)


def run_step_4a_ndef(pdf, out_dir, **kw):
    from step4a_ndef_sweep import run_sweep
    print(f"\n[ Step 4A-NDEF — {STEP_DESC['4a-ndef']} ]")
    auto = bool(kw.get("auto_approve_t2", False))
    rc = run_sweep(out_dir, auto_approve_t2=auto)
    return rc == 0


def run_step_4b(pdf, out_dir, **kw):
    golden = kw.get("golden")
    if not golden or not os.path.exists(golden):
        print(f"\n[ Step 4B — Skipped (no golden set) ]")
        return True
    from step4b_compare import run_comparison
    print(f"\n[ Step 4B — Golden set comparison ]")
    extracted = os.path.join(out_dir, "extracted_kris.json")
    run_comparison(extracted_path=extracted, golden_path=golden, output_dir=out_dir)
    return True


STEP_RUNNERS = {
    "1a":          run_step_1a,
    "1b-camelot":  run_step_1b_camelot,
    "1b":          run_step_1b_ontology,
    "1c":          run_step_1c,
    "2":           run_step_2,
    "3.5":         run_step_3_5,
    "3a":          run_step_3a,
    "3b":          run_step_3b,
    "3c":          run_step_3c,
    "3d":          run_step_3d,
    "4a":          run_step_4a,
    "4a-dedup":    run_step_4a_dedup,
    "2.6":         run_step_2_6,
    "4a-ndef":     run_step_4a_ndef,
    "4a-flagged":  run_step_4a_flagged,
    "4b":          run_step_4b,
}


# ─── Pipeline driver ───────────────────────────────────────────────────────
def run_pipeline(pdf, out_dir, golden=None, from_step=None, only_steps=None,
                 protocol_id=None, categories=None, auto_approve_unanimous=True):
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"PROTOCOL KRI EXTRACTOR — Deterministic Pipeline")
    print(f"  PDF:    {pdf}")
    print(f"  Output: {out_dir}")
    if golden:
        print(f"  Golden: {golden}")
    print(f"  Step order: {' → '.join(STEP_ORDER)}")
    print(f"  Blocking gates: {', '.join(sorted(BLOCKING_STEPS))}")
    print(f"{'=' * 60}")

    # Resolve which steps to run
    if only_steps:
        steps_to_run = [s for s in STEP_ORDER if s in only_steps]
    elif from_step:
        if from_step not in STEP_ORDER:
            print(f"\n✗ Unknown --from step: {from_step}")
            print(f"  Valid: {STEP_ORDER}")
            return False
        start_idx = STEP_ORDER.index(from_step)
        steps_to_run = STEP_ORDER[start_idx:]
    else:
        steps_to_run = list(STEP_ORDER)

    t_start = time.time()
    kw = {"golden": golden, "protocol_id": protocol_id, "categories": categories,
          "auto_approve_unanimous": auto_approve_unanimous}

    try:
        for step_id in steps_to_run:
            runner = STEP_RUNNERS[step_id]
            ok = runner(pdf, out_dir, **kw)
            enforce(step_id, ok)
    except BlockingGateFailed as e:
        print(f"\n{'=' * 60}")
        print(f"✗ PIPELINE BLOCKED at Step {e.step_id}")
        print(f"  Reason: {e.reason}")
        print(f"  Resolve the issue and re-run: python run.py --pdf {pdf} --out {out_dir} --from {e.step_id}")
        print(f"{'=' * 60}")
        return False

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"✓ PIPELINE COMPLETE in {elapsed:.0f}s")
    print(f"  Output: {out_dir}/extracted_kris.json")
    print(f"{'=' * 60}")
    return True


# ─── CLI ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Protocol KRI Extractor — deterministic pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Step order:\n"
            + "\n".join(
                f"  {sid:<12} {desc}" + ("  [BLOCKING]" if sid in BLOCKING_STEPS else "")
                for sid, desc, _ in STEP_CATALOG
            )
        ),
    )
    # Direct mode (matches SKILL.md documented CLI)
    parser.add_argument("--pdf", help="Path to protocol PDF")
    parser.add_argument("--out", help="Output directory")
    parser.add_argument("--golden", help="Optional path to golden set JSON")
    # Selection
    parser.add_argument("--from", dest="from_step", help="Resume from this step")
    parser.add_argument("--only", dest="only_steps",
                        help="Run only these steps (comma-separated)")
    parser.add_argument("--categories", help="For Step 2: comma-separated domains")
    parser.add_argument("--auto-approve-unanimous", dest="auto_approve_unanimous",
                        action="store_true", default=True,
                        help="Step 2.6: auto-approve/reject on panel unanimous vote; "
                             "flagged items default to rejected (surfaced at end-of-run "
                             "in flagged_review_decisions.json for user re-inclusion). "
                             "Default: ON (enables overnight runs). Scope: Step 2.6 only — "
                             "Step 3.5 orphan scan and Step 3B accuracy retain their own "
                             "independent user-decision gates.")
    parser.add_argument("--interactive", dest="auto_approve_unanimous",
                        action="store_false",
                        help="Step 2.6: disable auto-approve; block per-domain on "
                             "flagged list until user resolves every row")
    # Legacy mode
    parser.add_argument("protocol", nargs="?", help="Legacy registry protocol ID (or 'all')")
    parser.add_argument("--compare", action="store_true",
                        help="Legacy: run Step 4B golden set comparison")
    args = parser.parse_args()

    only_steps = set(args.only_steps.split(",")) if args.only_steps else None

    # Direct mode takes precedence
    if args.pdf and args.out:
        ok = run_pipeline(
            pdf=args.pdf,
            out_dir=args.out,
            golden=args.golden,
            from_step=args.from_step,
            only_steps=only_steps,
            categories=args.categories,
            auto_approve_unanimous=args.auto_approve_unanimous,
        )
        sys.exit(0 if ok else 1)

    # Legacy registry mode
    if args.protocol:
        targets = list(LEGACY_PROTOCOLS.keys()) if args.protocol == "all" else [args.protocol]
        all_ok = True
        for pid in targets:
            if pid not in LEGACY_PROTOCOLS:
                print(f"✗ Unknown protocol: {pid}. Choose from: {list(LEGACY_PROTOCOLS.keys())}")
                all_ok = False
                continue
            p = LEGACY_PROTOCOLS[pid]
            golden = p["golden"] if args.compare else None
            ok = run_pipeline(
                pdf=p["pdf"],
                out_dir=p["dir"],
                golden=golden,
                from_step=args.from_step,
                only_steps=only_steps,
                protocol_id=pid,
                categories=args.categories,
                auto_approve_unanimous=args.auto_approve_unanimous,
            )
            all_ok = all_ok and ok
        sys.exit(0 if all_ok else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
