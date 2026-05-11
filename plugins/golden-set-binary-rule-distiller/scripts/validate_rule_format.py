"""
Validate that every "Rule for LLM" cell in a Golden Set xlsx follows the
agreed 3-line SOURCE / CHECK / DEVIATION structure, and that the
"Deviation Level" column is populated with one of {subject, site, trial}.

Usage:
    python validate_rule_format.py <input.xlsx>

Exit code:
    0 = all rules valid
    1 = one or more violations (printed to stderr)
"""
import re
import sys
import pandas as pd

SRC_RE = re.compile(r"(?m)^SOURCE:")
CHK_RE = re.compile(r"(?m)^CHECK:")
DEV_RE = re.compile(r"(?m)^DEVIATION:")
LEVELS = {"subject", "site", "trial"}


def validate(xlsx_path: str) -> int:
    sheets = pd.read_excel(xlsx_path, sheet_name=None)
    violations = []
    total = 0
    for sheet_name, df in sheets.items():
        if "Rule for LLM" not in df.columns:
            violations.append(f"[{sheet_name}] missing 'Rule for LLM' column")
            continue
        if "Deviation Level" not in df.columns:
            violations.append(f"[{sheet_name}] missing 'Deviation Level' column")
            continue
        for _, r in df.iterrows():
            total += 1
            kid = str(r.get("KRI ID", "?"))
            rule = str(r.get("Rule for LLM", ""))
            level = str(r.get("Deviation Level", "")).strip().lower()

            problems = []
            if not SRC_RE.search(rule):
                problems.append("missing SOURCE: line")
            if not CHK_RE.search(rule):
                problems.append("missing CHECK: line")
            if not DEV_RE.search(rule):
                problems.append("missing DEVIATION: line")
            if level not in LEVELS:
                problems.append(f"Deviation Level={level!r} not in {sorted(LEVELS)}")

            if problems:
                violations.append(f"[{sheet_name}] {kid}: " + "; ".join(problems))

    if violations:
        print(f"Total rules: {total}", file=sys.stderr)
        print(f"Violations: {len(violations)}", file=sys.stderr)
        for v in violations:
            print("  " + v, file=sys.stderr)
        return 1

    print(f"All {total} rules valid (SOURCE/CHECK/DEVIATION + Deviation Level).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_rule_format.py <input.xlsx>", file=sys.stderr)
        sys.exit(2)
    sys.exit(validate(sys.argv[1]))
