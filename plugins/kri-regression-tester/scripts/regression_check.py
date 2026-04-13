#!/usr/bin/env python3
"""
Programmatic regression checks for frozen golden sets against the current
extractor skill rules.

Validates schema compliance, field formats, domain boundaries, quality rules,
severity values, and NDEF classification for every KRI in every frozen golden set.

Usage:
    python regression_check.py \
        --vault ~/Documents/kri-regression-vault \
        --skill ~/.claude/skills-repo/protocol-kri-extractor/SKILL.md

Outputs regression_report.json in the vault root directory.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone


# --- Current schema definition (update when skill schema changes) ---

REQUIRED_FIELDS = [
    "kri_id", "kri_name", "description", "category_id", "category_label",
    "rule_for_llm", "protocol_reference",
]

# Fields that should exist but may be null
OPTIONAL_FIELDS = [
    "supporting_quote", "additional_footnotes", "combined_ref",
    "domain", "non_verifiable_reason",
]

VALID_DOMAINS = {"SOA", "ELIG", "SAF", "END", "OPS", "NDEF"}

VALID_SEVERITIES = {"critical", "major", "minor"}

# KRI ID patterns per domain
ID_PATTERNS = {
    "SOA": r"^SOA-",
    "ELIG": r"^ELIG-",
    "SAF": r"^SAF-",
    "END": r"^(END-|STAT-|GOV-)",
    "OPS": r"^OPS-",
    "NDEF": r"^NDEF-",
}

# NDEF trigger phrases — KRIs with these in rule_for_llm should be NDEF
NDEF_TRIGGERS = [
    "clinically significant",
    "investigator discretion",
    "investigator's opinion",
    "investigator opinion",
    "as appropriate",
    "if appropriate",
    "per local regulations",
    "as soon as possible",
    "promptly",
    "efforts were made",
    "adequate",
    "sufficient",
    "if clinically indicated",
    "clinical judgment",
]

# Domain boundary keywords — heuristic checks
SOA_OWNERSHIP_PHRASES = [
    "per SOA", "per schedule", "per the SoA table", "at visit",
    "was performed at", "was collected at", "was measured at",
]


class Finding:
    """A single regression finding."""
    def __init__(self, protocol_id, kri_id, kri_name, domain, field, issue, severity="regression"):
        self.protocol_id = protocol_id
        self.kri_id = kri_id
        self.kri_name = kri_name
        self.domain = domain
        self.field = field
        self.issue = issue
        self.severity = severity  # "regression", "warning", "additive"

    def to_dict(self):
        return {
            "protocol_id": self.protocol_id,
            "kri_id": self.kri_id,
            "kri_name": self.kri_name,
            "domain": self.domain,
            "field": self.field,
            "issue": self.issue,
            "severity": self.severity,
        }


def load_golden_set(golden_dir: Path) -> list:
    """Load KRIs from extracted_kris.json."""
    kris_path = golden_dir / "extracted_kris.json"
    if not kris_path.exists():
        return []
    with open(kris_path) as f:
        data = json.load(f)
    kris = data.get("kris", data) if isinstance(data, dict) else data
    return kris if isinstance(kris, list) else []


def check_schema(protocol_id: str, kris: list) -> list:
    """Check that all required fields exist in every KRI."""
    findings = []
    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))

        for field in REQUIRED_FIELDS:
            if field not in kri or kri[field] is None:
                findings.append(Finding(
                    protocol_id, kid, kname, domain, field,
                    f"Required field '{field}' is missing or null"
                ))
    return findings


def check_field_formats(protocol_id: str, kris: list) -> list:
    """Check field format rules."""
    findings = []
    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))

        # Severity validation
        severity = kri.get("severity")
        if severity and severity not in VALID_SEVERITIES:
            findings.append(Finding(
                protocol_id, kid, kname, domain, "severity",
                f"Invalid severity '{severity}'. Expected one of: {VALID_SEVERITIES}"
            ))

        # Category ID validation
        cat = kri.get("category_id")
        if cat and cat not in VALID_DOMAINS:
            findings.append(Finding(
                protocol_id, kid, kname, domain, "category_id",
                f"Invalid category_id '{cat}'. Expected one of: {VALID_DOMAINS}"
            ))

        # KRI ID pattern validation
        if cat and cat in ID_PATTERNS:
            if not re.match(ID_PATTERNS[cat], kid):
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "kri_id",
                    f"KRI ID '{kid}' doesn't match expected pattern for {cat}: {ID_PATTERNS[cat]}",
                    severity="warning"
                ))

        # Quality Rule 11 — no outer quotes in supporting_quote
        sq = kri.get("supporting_quote", "")
        if sq and isinstance(sq, str):
            if (sq.startswith('"') and sq.endswith('"')) or sq.startswith('"'):
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "supporting_quote",
                    "supporting_quote starts or ends with '\"' — violates Quality Rule 11"
                ))

        # Quality Rule 12 — no duplicate page numbers
        ref = kri.get("protocol_reference", "")
        if ref:
            pages = re.findall(r'p\.(\d+)', ref)
            if len(pages) != len(set(pages)):
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "protocol_reference",
                    f"Duplicate page numbers in protocol_reference: {ref} — violates Quality Rule 12"
                ))

        # Combined_ref format check (should contain em dash)
        cref = kri.get("combined_ref", "")
        if cref and isinstance(cref, str) and len(cref) > 10:
            if "\u2014" not in cref and " --- " not in cref and " -- " not in cref:
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "combined_ref",
                    "combined_ref may not follow the expected format (missing em dash separator)",
                    severity="warning"
                ))

    return findings


def check_domain_boundaries(protocol_id: str, kris: list) -> list:
    """Heuristic check for domain boundary violations."""
    findings = []
    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))
        rule = kri.get("rule_for_llm", "").lower()

        # Rule 1: SOA owns procedure-at-visit checks
        # If a SAF or OPS KRI talks about "at visit" or "per SOA", it might belong in SOA
        if domain in ("SAF", "OPS"):
            for phrase in SOA_OWNERSHIP_PHRASES:
                if phrase.lower() in rule:
                    findings.append(Finding(
                        protocol_id, kid, kname, domain, "category_id",
                        f"KRI in {domain} contains '{phrase}' — may belong in SOA per Domain Boundary Rule 1",
                        severity="warning"
                    ))
                    break

    return findings


def check_ndef_classification(protocol_id: str, kris: list) -> list:
    """Check for non-NDEF KRIs that contain NDEF trigger phrases."""
    findings = []
    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))
        rule = kri.get("rule_for_llm", "").lower()

        if domain != "NDEF":
            for trigger in NDEF_TRIGGERS:
                if trigger.lower() in rule:
                    findings.append(Finding(
                        protocol_id, kid, kname, domain, "category_id",
                        f"Non-NDEF KRI contains NDEF trigger phrase '{trigger}' in rule_for_llm — "
                        f"may need reclassification to NDEF",
                        severity="warning"
                    ))
                    break

    return findings


def check_atomicity(protocol_id: str, kris: list) -> list:
    """Basic atomicity heuristics — flag KRIs that might combine multiple checks."""
    findings = []

    # Patterns that suggest multiple things combined
    multi_patterns = [
        (r'\band\b.*\band\b.*\band\b', "Multiple 'and' conjunctions — possible atomicity violation"),
        (r'verify that .+ and .+ and .+', "Multiple checks in a single verify statement"),
    ]

    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))
        rule = kri.get("rule_for_llm", "")

        for pattern, msg in multi_patterns:
            if re.search(pattern, rule, re.IGNORECASE):
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "rule_for_llm",
                    f"Atomicity warning: {msg}",
                    severity="warning"
                ))
                break

    return findings


def check_soa_visit_prefix(protocol_id: str, kris: list) -> list:
    """Quality Rule 5 — every SOA rule_for_llm starts with visit code."""
    findings = []
    for kri in kris:
        kid = kri.get("kri_id", "UNKNOWN")
        kname = kri.get("kri_name", "")
        domain = kri.get("category_id", kri.get("domain", ""))
        rule = kri.get("rule_for_llm", "")

        if domain == "SOA" and rule:
            # Check if starts with a visit prefix like V1-, S2-, All visits-, etc.
            if not re.match(r'^(V\d+|S\d+|All visits|EDC|EOS|Unscheduled)', rule):
                findings.append(Finding(
                    protocol_id, kid, kname, domain, "rule_for_llm",
                    "SOA KRI rule_for_llm doesn't start with visit code prefix — violates Quality Rule 5",
                    severity="warning"
                ))
    return findings


def run_all_checks(vault: Path) -> dict:
    """Run all checks across all frozen protocols."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault_path": str(vault),
        "protocols": {},
        "summary": {
            "total_protocols": 0,
            "total_kris_checked": 0,
            "total_regressions": 0,
            "total_warnings": 0,
            "total_additive": 0,
            "passed": True,
        },
    }

    # Find all frozen protocols
    protocol_dirs = sorted([
        d for d in vault.iterdir()
        if d.is_dir() and (d / "metadata.json").exists()
    ])

    if not protocol_dirs:
        print("No frozen protocols found in the vault.")
        return report

    for pdir in protocol_dirs:
        pid = pdir.name
        golden_dir = pdir / "golden_set"
        kris = load_golden_set(golden_dir)

        if not kris:
            print(f"  WARNING: No KRIs found for {pid}")
            continue

        # Run all check categories
        all_findings = []
        all_findings.extend(check_schema(pid, kris))
        all_findings.extend(check_field_formats(pid, kris))
        all_findings.extend(check_domain_boundaries(pid, kris))
        all_findings.extend(check_ndef_classification(pid, kris))
        all_findings.extend(check_atomicity(pid, kris))
        all_findings.extend(check_soa_visit_prefix(pid, kris))

        # Organize findings
        regressions = [f for f in all_findings if f.severity == "regression"]
        warnings = [f for f in all_findings if f.severity == "warning"]
        additive = [f for f in all_findings if f.severity == "additive"]

        report["protocols"][pid] = {
            "total_kris": len(kris),
            "regressions": [f.to_dict() for f in regressions],
            "warnings": [f.to_dict() for f in warnings],
            "additive": [f.to_dict() for f in additive],
            "passed": len(regressions) == 0,
        }

        report["summary"]["total_protocols"] += 1
        report["summary"]["total_kris_checked"] += len(kris)
        report["summary"]["total_regressions"] += len(regressions)
        report["summary"]["total_warnings"] += len(warnings)
        report["summary"]["total_additive"] += len(additive)
        if regressions:
            report["summary"]["passed"] = False

        # Print progress
        status = "PASS" if not regressions else f"FAIL ({len(regressions)} regressions)"
        print(f"  {pid}: {len(kris)} KRIs — {status}, {len(warnings)} warnings")

    return report


def main():
    parser = argparse.ArgumentParser(description="Run programmatic regression checks")
    parser.add_argument("--vault", required=True, help="Path to the regression vault")
    parser.add_argument("--skill", required=True, help="Path to the current extractor SKILL.md")
    parser.add_argument("--output", help="Output report path (default: vault/regression_report.json)")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    skill_path = Path(args.skill).expanduser()

    if not vault.exists():
        print(f"ERROR: Vault not found at {vault}")
        sys.exit(1)
    if not skill_path.exists():
        print(f"ERROR: Skill not found at {skill_path}")
        sys.exit(1)

    print(f"\nRunning regression checks...")
    print(f"  Vault: {vault}")
    print(f"  Skill: {skill_path}\n")

    report = run_all_checks(vault)

    # Save report
    output_path = Path(args.output) if args.output else vault / "regression_report.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Final summary
    s = report["summary"]
    print(f"\n{'='*60}")
    if s["passed"]:
        print("REGRESSION TEST: PASSED")
    else:
        print("REGRESSION TEST: FAILED")
    print(f"  Protocols checked: {s['total_protocols']}")
    print(f"  KRIs checked:      {s['total_kris_checked']}")
    print(f"  Regressions:       {s['total_regressions']}")
    print(f"  Warnings:          {s['total_warnings']}")
    print(f"  Additive:          {s['total_additive']}")
    print(f"  Report saved to:   {output_path}")
    print(f"{'='*60}\n")

    sys.exit(0 if s["passed"] else 1)


if __name__ == "__main__":
    main()
