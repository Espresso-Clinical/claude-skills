#!/usr/bin/env python3
"""
Freeze a completed extraction run into the regression vault.

Copies all relevant artifacts from a run directory into the vault,
snapshots the current extractor skill, and generates metadata.

Usage:
    python freeze.py \
        --source ~/Downloads/extractor/B1481038/run_003/ \
        --vault ~/Documents/kri-regression-vault \
        --protocol-id B1481038 \
        --protocol-name "ODYSSEY OUTCOMES" \
        --skill-path ~/.claude/skills-repo/protocol-kri-extractor/SKILL.md \
        [--notes "Optional approval notes"]
"""

import argparse
import json
import shutil
import os
from datetime import datetime, timezone
from pathlib import Path


# Artifacts to copy from the source run directory
ARTIFACTS = [
    # Primary
    "extracted_kris.json",
    "Extracted_KRIs.xlsx",
    # Per-domain
    "raw_SOA.json",
    "raw_ELIG.json",
    "raw_SAF.json",
    "raw_END.json",
    "raw_OPS.json",
    "raw_NDEF.json",
    # Intermediate / structural
    "manifest.json",
    "ontology.json",
    "soa_table.csv",
    "soa_table.json",
    "footnote_map.json",
    # Validation reports
    "verify_report.json",
    "gaps_report.json",
    "accuracy_report.json",
    "consistency_report.json",
    "crossdomain_dedup_report.json",
]


def count_kris_by_domain(kris_path: Path) -> dict:
    """Count KRIs per domain from extracted_kris.json."""
    with open(kris_path) as f:
        data = json.load(f)

    kris = data.get("kris", data) if isinstance(data, dict) else data
    if not isinstance(kris, list):
        return {}

    counts = {}
    for kri in kris:
        domain = kri.get("category_id") or kri.get("domain") or "UNKNOWN"
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def get_git_info(skill_path: Path) -> str:
    """Try to get git commit hash for the skill file."""
    try:
        import subprocess
        repo_dir = skill_path.parent
        while repo_dir != repo_dir.parent:
            if (repo_dir / ".git").exists():
                break
            repo_dir = repo_dir.parent
        else:
            return "unknown"

        result = subprocess.run(
            ["git", "log", "-1", "--format=%H %ai", "--", str(skill_path)],
            cwd=repo_dir, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def freeze(source: Path, vault: Path, protocol_id: str, protocol_name: str,
           skill_path: Path, notes: str = "") -> Path:
    """Freeze a run into the vault. Returns the vault protocol directory."""

    # Validate source has the primary artifact
    kris_path = source / "extracted_kris.json"
    if not kris_path.exists():
        raise FileNotFoundError(
            f"extracted_kris.json not found in {source}. "
            "Cannot freeze an incomplete run."
        )

    # Create vault directory
    protocol_dir = vault / protocol_id
    golden_dir = protocol_dir / "golden_set"
    snapshot_dir = protocol_dir / "skill_snapshot"

    if protocol_dir.exists():
        raise FileExistsError(
            f"Protocol {protocol_id} already exists in the vault at {protocol_dir}. "
            "If you want to re-freeze, remove or rename the existing entry first."
        )

    golden_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Copy artifacts
    copied = []
    missing = []
    for artifact in ARTIFACTS:
        src = source / artifact
        if src.exists():
            shutil.copy2(src, golden_dir / artifact)
            copied.append(artifact)
        else:
            missing.append(artifact)

    # Also copy any additional json/csv/xlsx files not in the standard list
    for f in source.iterdir():
        if f.is_file() and f.suffix in (".json", ".csv", ".xlsx") and f.name not in ARTIFACTS:
            shutil.copy2(f, golden_dir / f.name)
            copied.append(f"(extra) {f.name}")

    # Snapshot the extractor skill
    if skill_path.exists():
        shutil.copy2(skill_path, snapshot_dir / "SKILL.md")
    else:
        print(f"WARNING: Skill file not found at {skill_path}")

    # Count KRIs
    domain_counts = count_kris_by_domain(kris_path)
    total_kris = sum(domain_counts.values())

    # Generate metadata
    metadata = {
        "protocol_id": protocol_id,
        "protocol_name": protocol_name,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "frozen_by": "user",
        "extractor_skill_version": get_git_info(skill_path),
        "total_kris": total_kris,
        "domain_counts": domain_counts,
        "source_run_dir": str(source),
        "artifacts_copied": copied,
        "artifacts_missing": missing,
        "notes": notes,
    }

    with open(protocol_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*60}")
    print(f"FROZEN: {protocol_name} ({protocol_id})")
    print(f"{'='*60}")
    print(f"Vault path:  {protocol_dir}")
    print(f"Total KRIs:  {total_kris}")
    print(f"Domains:     {json.dumps(domain_counts)}")
    print(f"Copied:      {len(copied)} artifacts")
    if missing:
        print(f"Missing:     {', '.join(missing)}")
    print(f"Skill snapshot: {snapshot_dir / 'SKILL.md'}")
    print(f"{'='*60}\n")

    return protocol_dir


def main():
    parser = argparse.ArgumentParser(description="Freeze a golden set into the regression vault")
    parser.add_argument("--source", required=True, help="Path to the completed extraction run directory")
    parser.add_argument("--vault", required=True, help="Path to the regression vault")
    parser.add_argument("--protocol-id", required=True, help="Protocol identifier (e.g., B1481038)")
    parser.add_argument("--protocol-name", required=True, help="Human-readable protocol name")
    parser.add_argument("--skill-path", required=True, help="Path to the current extractor SKILL.md")
    parser.add_argument("--notes", default="", help="Optional approval notes")
    args = parser.parse_args()

    freeze(
        source=Path(args.source).expanduser(),
        vault=Path(args.vault).expanduser(),
        protocol_id=args.protocol_id,
        protocol_name=args.protocol_name,
        skill_path=Path(args.skill_path).expanduser(),
        notes=args.notes,
    )


if __name__ == "__main__":
    main()
