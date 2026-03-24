#!/usr/bin/env python3
"""
Protocol KRI Extractor — Full Pipeline Runner
Usage:
  python run.py ENX-CL-05-002              # full pipeline, no comparison
  python run.py ENX-CL-05-002 --compare    # full pipeline + golden set comparison
  python run.py ENX-CL-05-002 --from 2     # resume from step 2
  python run.py ENX-CL-05-002 --steps 1a,1b,2  # run only specific steps
  python run.py all                         # all 3 protocols, no comparison
"""

import sys, os, argparse, json, time

# ── Protocol registry ─────────────────────────────────────────────────────────
PROTOCOLS = {
    "ENX-CL-05-002": {
        "pdf":    "/mnt/user-data/uploads/ENX-CL-05-002_Clinical_Study_Protocol_v_2_0_Agatha_copy.pdf",
        "dir":    "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002",
        "golden": "/mnt/user-data/uploads/golden_set.json"
    },
    "B1481038": {
        "pdf":    "/mnt/user-data/uploads/Protocol_B1481038.pdf",
        "dir":    "/home/claude/protocol-kri-extractor/output/B1481038",
        "golden": None
    },
    "LCZ696G2301": {
        "pdf":    "/mnt/user-data/uploads/Novartis__LCZ696G2301-_Phase_3_study_to_evaluate_the_efficacy_and_safety_of_LCZ696pdf.pdf",
        "dir":    "/home/claude/protocol-kri-extractor/output/LCZ696G2301",
        "golden": None
    }
}

STEP_ORDER = ["1a", "1b", "2", "3a", "3b", "3c", "4a", "4b"]

def step_num(s: str) -> float:
    mapping = {"1a": 1.1, "1b": 1.2, "2": 2, "3a": 3.1, "3b": 3.2, "3c": 3.3, "4a": 4.1, "4b": 4.2}
    return mapping.get(s, 99)

def run_protocol(protocol_id: str, args):
    if protocol_id not in PROTOCOLS:
        print(f"Unknown protocol: {protocol_id}. Choose from: {list(PROTOCOLS.keys())}")
        return

    p = PROTOCOLS[protocol_id]
    os.makedirs(p["dir"], exist_ok=True)

    print(f"\n{'='*60}")
    print(f"PROTOCOL: {protocol_id}")
    print(f"Output:   {p['dir']}")
    print(f"{'='*60}")

    # Determine which steps to run
    from_step = args.from_step or "1a"
    only_steps = set(args.steps.split(",")) if args.steps else None
    run_compare = args.compare and p["golden"] and os.path.exists(p["golden"])

    def should_run(step: str) -> bool:
        if only_steps:
            return step in only_steps
        return step_num(step) >= step_num(from_step)

    manifest_path = os.path.join(p["dir"], "manifest.json")
    ontology_path = os.path.join(p["dir"], "ontology.json")
    t_start = time.time()

    # ── Step 1A ───────────────────────────────────────────────────────────────
    if should_run("1a"):
        print("\n[ Step 1A — Protocol Manifest ]")
        from scripts.step1a_manifest import build_manifest
        manifest = build_manifest(p["pdf"], protocol_id)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  ✓ Saved {manifest_path}")

    # ── Step 1B ───────────────────────────────────────────────────────────────
    if should_run("1b"):
        print("\n[ Step 1B — SoA Ontology ]")
        from scripts.step1b_ontology import build_ontology, print_summary
        with open(manifest_path) as f:
            manifest = json.load(f)
        ontology = build_ontology(p["pdf"], manifest)
        with open(ontology_path, "w") as f:
            json.dump(ontology, f, indent=2)
        print_summary(ontology)
        print(f"  ✓ Saved {ontology_path}")

    # ── Step 2 ────────────────────────────────────────────────────────────────
    if should_run("2"):
        print("\n[ Step 2 — KRI Extraction ]")
        from scripts.step2_extract import run_extraction
        with open(manifest_path) as f:
            manifest = json.load(f)
        with open(ontology_path) as f:
            ontology = json.load(f)
        cats = args.categories.split(",") if args.categories else None
        run_extraction(p["pdf"], manifest_path, ontology_path, p["dir"], cats)

    # ── Step 3A ───────────────────────────────────────────────────────────────
    if should_run("3a"):
        print("\n[ Step 3A — Completeness Check ]")
        from scripts.step3a_completeness import run_completeness_check
        run_completeness_check(p["dir"], manifest_path, ontology_path)

    # ── Step 3B ───────────────────────────────────────────────────────────────
    if should_run("3b"):
        print("\n[ Step 3B — Accuracy Check ]")
        from scripts.step3b_accuracy import run_accuracy_check
        run_accuracy_check(p["dir"], p["pdf"])

    # ── Step 3C ───────────────────────────────────────────────────────────────
    if should_run("3c"):
        print("\n[ Step 3C — Consistency Check ]")
        from scripts.step3c_consistency import run_consistency_check
        run_consistency_check(p["dir"], p["pdf"], ontology_path)

    # ── Step 4A ───────────────────────────────────────────────────────────────
    if should_run("4a"):
        print("\n[ Step 4A — Assembly ]")
        from scripts.step4a_assemble import run_assembly
        run_assembly(p["dir"], manifest_path)

    # ── Step 4B ───────────────────────────────────────────────────────────────
    if should_run("4b") and run_compare:
        print("\n[ Step 4B — Golden Set Comparison ]")
        from scripts.step4b_compare import run_comparison
        run_comparison(
            extracted_path=os.path.join(p["dir"], "extracted_kris.json"),
            golden_path=p["golden"],
            output_dir=p["dir"]
        )
    elif should_run("4b") and not run_compare:
        print("\n[ Step 4B — Skipped (no golden set or --compare not set) ]")

    elapsed = time.time() - t_start
    print(f"\n✓ Done: {protocol_id} in {elapsed:.0f}s")
    print(f"  Output: {p['dir']}/extracted_kris.json")

def main():
    parser = argparse.ArgumentParser(description="Protocol KRI Extractor")
    parser.add_argument("protocol", help="Protocol ID or 'all'")
    parser.add_argument("--from", dest="from_step", default=None,
                        help="Resume from step (1a, 1b, 2, 3a, 3b, 3c, 4a, 4b)")
    parser.add_argument("--steps", default=None,
                        help="Comma-separated steps to run only, e.g. '1a,1b'")
    parser.add_argument("--categories", default=None,
                        help="For step 2: comma-separated categories e.g. 'SOA,ELIG'")
    parser.add_argument("--compare", action="store_true",
                        help="Run step 4B golden set comparison (requires golden set path)")
    args = parser.parse_args()

    if args.protocol == "all":
        for pid in PROTOCOLS:
            run_protocol(pid, args)
    else:
        run_protocol(args.protocol, args)

if __name__ == "__main__":
    # Add parent dir to path so 'scripts' module resolves
    sys.path.insert(0, os.path.dirname(__file__))
    main()
