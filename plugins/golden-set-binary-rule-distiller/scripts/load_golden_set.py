"""
Load and validate a Golden Set xlsx.
Emits a JSON file with one object per rule, preserving sheet, row order, and all columns.

Usage:
    python load_golden_set.py <input.xlsx> <output.json>
"""
import sys
import json
import pandas as pd

# Columns that must be present — these are the source material the skill uses
# to AUTHOR the Rule for LLM from scratch.
REQUIRED_COLS = [
    "KRI ID", "Category", "KRI Name", "Description",
    "Protocol Reference & Quote", "Severity",
]

# "Rule for LLM" is NOT required on input. In the current workflow the Golden
# Set arrives without it (or with it empty); the distiller authors it from the
# required columns + the footnotes/quotes + the protocol PDF. If present on
# input it is treated as a non-authoritative hint only.
OPTIONAL_COLS = ["Rule for LLM"]


def load_golden_set(xlsx_path: str, out_json: str) -> int:
    sheets = pd.read_excel(xlsx_path, sheet_name=None)
    rows = []
    for sheet_name, df in sheets.items():
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            print(
                f"WARN: sheet {sheet_name!r} missing required columns: {missing}",
                file=sys.stderr,
            )
        for _, r in df.iterrows():
            row = {"sheet": sheet_name}
            for col in df.columns:
                row[col] = None if pd.isna(r[col]) else str(r[col])
            rows.append(row)
    with open(out_json, "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python load_golden_set.py <input.xlsx> <output.json>", file=sys.stderr)
        sys.exit(2)
    n = load_golden_set(sys.argv[1], sys.argv[2])
    print(f"Loaded {n} rules from {sys.argv[1]} into {sys.argv[2]}")
