"""
Validate that every "Rule for LLM" cell in a Golden Set xlsx is a well-formed
YAML "Protocol rule", and that the "Deviation Level" column is populated with
one of {subject, site, trial}.

A valid Protocol rule:
  - parses as YAML into a mapping;
  - contains the six required top-level slots:
      intent, applies_to, evidence_expected, acceptance, deviation, provenance
  - has `acceptance` as a non-empty mapping (sub-slots are an OPEN set — this
    validator does NOT enforce specific sub-slot names).

Usage:
    python validate_rule_format.py <input.xlsx>

Exit code:
    0 = all rules valid
    1 = one or more violations (printed to stderr)
"""
import sys
import pandas as pd

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

REQUIRED_SLOTS = ["intent", "applies_to", "evidence_expected",
                  "acceptance", "deviation", "provenance"]
LEVELS = {"subject", "site", "trial"}


def _check_rule_text(rule: str):
    """Return a list of problems for a single Rule-for-LLM cell."""
    if not rule or not rule.strip():
        return ["empty Rule for LLM"]

    problems = []
    if HAVE_YAML:
        try:
            parsed = yaml.safe_load(rule)
        except yaml.YAMLError as e:
            return [f"not valid YAML ({str(e).splitlines()[0]})"]
        if not isinstance(parsed, dict):
            return ["YAML did not parse into a mapping"]
        for slot in REQUIRED_SLOTS:
            if slot not in parsed:
                problems.append(f"missing slot: {slot}")
        if "acceptance" in parsed:
            acc = parsed.get("acceptance")
            if not isinstance(acc, dict) or not acc:
                problems.append("acceptance must be a non-empty mapping")
    else:
        # Fallback (PyYAML unavailable): tolerant line-prefix check.
        for slot in REQUIRED_SLOTS:
            if f"{slot}:" not in rule:
                problems.append(f"missing slot: {slot}")
    return problems


def validate(xlsx_path: str) -> int:
    if not HAVE_YAML:
        print("WARN: PyYAML not installed — using a tolerant line check, not a real YAML parse.",
              file=sys.stderr)
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
            rule = "" if pd.isna(r.get("Rule for LLM")) else str(r.get("Rule for LLM", ""))
            level = ("" if pd.isna(r.get("Deviation Level"))
                     else str(r.get("Deviation Level", ""))).strip().lower()

            problems = _check_rule_text(rule)
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

    print(f"All {total} rules valid (YAML Protocol-rule slots + Deviation Level).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_rule_format.py <input.xlsx>", file=sys.stderr)
        sys.exit(2)
    sys.exit(validate(sys.argv[1]))
