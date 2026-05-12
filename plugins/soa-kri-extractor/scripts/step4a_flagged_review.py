"""
Step 4A-FlaggedReview — End-of-run cross-domain flagged-review table.

Runs AFTER Step 4A-NDEF (last step before Golden Set finalization). Collects
every flagged-and-defaulted-to-rejected KRI from all 5 domains' Step 2.6
autojudgment outputs and produces a single consolidated review table with
FULL KRI columns so the user can efficiently scan and re-include any they want.

Why this exists: with `--auto-approve-unanimous` ON (default), the pipeline
does not block on each domain's flagged list during Phase 2. Instead, flagged
items default to REJECTED and are collected here into one unified table at
the end of the run. The user reviews once — not five times — and can re-include
any KRI with a one-click flag in `flagged_review_decisions.json`. A re-run of
Phase 4 assembly then adds those KRIs back to the Golden Set.

Distinct from the per-domain flagged_for_review section in
`{domain}_manual_review_decisions.json` — that is the domain-scoped audit. This
is the cross-domain consolidated user-review table.

Usage:
  python step4a_flagged_review.py --out /path/to/run_dir/
"""

import argparse
import json
import os
import sys


DOMAINS = ["SOA", "ELIG", "SAF", "END", "OPS"]


def build_cross_domain_review(out_dir):
    """Collect every flagged_for_review row from every domain's decision table."""
    all_flagged = []
    per_domain_counts = {}

    for domain in DOMAINS:
        path = os.path.join(out_dir, f"{domain}_manual_review_decisions.json")
        if not os.path.isfile(path):
            per_domain_counts[domain] = 0
            continue
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
        flagged = table.get("sections", {}).get("flagged_for_review", [])
        per_domain_counts[domain] = len(flagged)
        for row in flagged:
            row["_source_domain"] = domain
            all_flagged.append(row)

    return all_flagged, per_domain_counts


def write_cross_domain_artifact(out_dir, all_flagged, per_domain_counts):
    review = {
        "_meta": {
            "step": "4A-FlaggedReview",
            "total_flagged": len(all_flagged),
            "per_domain_counts": per_domain_counts,
            "default_phase4_action": "rejected",
            "user_override_instructions": (
                "To re-include any flagged KRI into the Golden Set: edit this file, "
                "set `user_override` to 'include' on the relevant row, then re-run "
                "`python run.py --pdf ... --out ... --from 4a` to regenerate the "
                "Golden Set with the re-included KRIs."
            ),
        },
        "flagged_kris": all_flagged,
    }
    out_path = os.path.join(out_dir, "flagged_review_decisions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
    return out_path


def print_summary(review_path, all_flagged, per_domain_counts):
    print(f"\n[ Step 4A-FlaggedReview — Cross-domain consolidated review ]")
    print(f"  Total flagged KRIs (defaulted to rejected): {len(all_flagged)}")
    for d in DOMAINS:
        n = per_domain_counts.get(d, 0)
        if n > 0:
            print(f"    {d}: {n}")
    print(f"  Written to: {review_path}")
    if len(all_flagged) == 0:
        print("  ✓ No flagged items — Golden Set is complete as assembled.")
    else:
        print(f"  ⚠ Review {len(all_flagged)} flagged KRIs in the file above.")
        print(f"    Set `user_override: 'include'` on any row you want back in, then "
              f"re-run `run.py --from 4a` to regenerate.")


def run(out_dir):
    all_flagged, per_domain_counts = build_cross_domain_review(out_dir)
    review_path = write_cross_domain_artifact(out_dir, all_flagged, per_domain_counts)
    print_summary(review_path, all_flagged, per_domain_counts)
    return True


def apply_user_overrides(out_dir):
    """Re-include any flagged KRIs the user marked `user_override: 'include'`.

    Appends them back to their source domain's raw_{DOMAIN}.json so the next
    Phase 4 assembly picks them up.
    """
    path = os.path.join(out_dir, "flagged_review_decisions.json")
    if not os.path.isfile(path):
        print("  (no flagged_review_decisions.json — skipping override application)")
        return 0

    with open(path, encoding="utf-8") as f:
        review = json.load(f)

    applied = 0
    by_domain_re_include = {}
    for row in review.get("flagged_kris", []):
        if str(row.get("user_override") or "").lower() == "include":
            dom = row.get("_source_domain")
            if dom:
                by_domain_re_include.setdefault(dom, []).append(row)
                applied += 1

    for dom, rows in by_domain_re_include.items():
        raw_path = os.path.join(out_dir, f"raw_{dom}.json")
        if not os.path.isfile(raw_path):
            continue
        with open(raw_path, encoding="utf-8") as f:
            raw = json.load(f)
        # Re-build clean KRIs from the decision-table rows (strip underscore fields)
        for row in rows:
            clean = {k: v for k, v in row.items() if not k.startswith("_")
                     and k not in ("auto_decision", "stage", "reason", "panel_summary",
                                   "decision_source", "user_override", "tier",
                                   "agent_count")}
            # Check if already in raw (don't duplicate on re-runs)
            existing_ids = {k.get("kri_id") for k in raw}
            if clean.get("kri_id") not in existing_ids:
                raw.append(clean)
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)

    print(f"  ✓ Applied {applied} user overrides across {len(by_domain_re_include)} domains.")
    print("    Re-run `python run.py --from 4a` to regenerate the Golden Set.")
    return applied


def main():
    parser = argparse.ArgumentParser(description="Step 4A-FlaggedReview")
    parser.add_argument("--out", required=True, help="Run output directory")
    parser.add_argument("--apply-overrides", action="store_true",
                        help="After user edits flagged_review_decisions.json, "
                             "apply include-overrides back to raw_{DOMAIN}.json")
    args = parser.parse_args()

    if not os.path.isdir(args.out):
        print(f"✗ Not a directory: {args.out}")
        sys.exit(2)

    if args.apply_overrides:
        apply_user_overrides(args.out)
    else:
        run(args.out)


if __name__ == "__main__":
    main()
