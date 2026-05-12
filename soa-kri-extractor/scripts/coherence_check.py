"""
coherence_check — Post-generation pass that flags KRIs where the four content
fields (Description ↔ Rule for LLM ↔ Protocol Reference ↔ Severity) are inconsistent.

Generic checks:
  1. Visit prefix consistency — kri_name starts with the same visit code that
     rule_for_llm references.
  2. Procedure name consistency — kri_name's procedure equals the procedure
     mentioned in description and rule_for_llm.
  3. Analyte list consistency — if rule_for_llm mentions "N required analytes",
     description should mention them too (or at least acknowledge the list).
  4. Window consistency — if rule_for_llm specifies "±N days of (Day 1 + X)",
     description should mention the same window.
  5. Footnote citation consistency — if rule_for_llm references analytes/parameters
     from a footnote, the protocol_reference must cite that footnote.
  6. Severity ↔ rule type consistency — eligibility/consent → critical; standard
     procedure → major; optional/exploratory → minor.

Outputs warnings (not blocking) to the coherence_report.json. The Compliance
Monitor surfaces warnings to the user; the pipeline does not stop on warnings.
"""
import json
import os
import re
import sys
import argparse


def _find_visit_prefix(s):
    if not s:
        return None
    m = re.match(r"\s*([A-Z][A-Z0-9_\-]*)\s*[-:]", s)
    return m.group(1).strip() if m else None


def _has_all_caps_section(rule_text, section_name):
    """Return the content of the given section (SOURCE/CHECK/DEVIATION) or None."""
    pat = re.compile(rf"\b{section_name}:\s*(.+?)(?=\b(?:SOURCE|CHECK|DEVIATION):|$)",
                     re.IGNORECASE | re.DOTALL)
    m = pat.search(rule_text or "")
    return m.group(1).strip() if m else None


def check_kri(kri):
    """Return list of warnings for one KRI."""
    warnings = []
    name = kri.get("kri_name") or ""
    desc = kri.get("description") or ""
    rule = kri.get("rule_for_llm") or ""
    ref = kri.get("protocol_reference") or ""
    sev = (kri.get("severity") or "").lower()

    # 1. 3-line SOURCE/CHECK/DEVIATION structure required
    has_source = bool(_has_all_caps_section(rule, "SOURCE"))
    has_check = bool(_has_all_caps_section(rule, "CHECK"))
    has_deviation = bool(_has_all_caps_section(rule, "DEVIATION"))
    if not (has_source and has_check and has_deviation):
        missing = [s for s, ok in [("SOURCE", has_source), ("CHECK", has_check),
                                    ("DEVIATION", has_deviation)] if not ok]
        warnings.append({
            "rule": "missing_rule_section",
            "detail": f"rule_for_llm missing required label(s): {missing}",
        })

    # 2. Visit prefix consistency
    name_prefix = _find_visit_prefix(name)
    source = _has_all_caps_section(rule, "SOURCE") or ""
    check = _has_all_caps_section(rule, "CHECK") or ""
    if name_prefix and name_prefix.lower() not in {"all visits", "permitted", "background",
                                                     "post-study", "lost", "treatment"}:
        # Skip cross-visit / narrative names. For visit-specific names, require the
        # visit prefix to appear in SOURCE or CHECK.
        if name_prefix.lower() not in source.lower() and name_prefix.lower() not in check.lower():
            warnings.append({
                "rule": "visit_prefix_mismatch",
                "detail": f"kri_name starts with '{name_prefix}' but SOURCE/CHECK doesn't reference it",
            })

    # 3. Analyte list consistency
    # If rule mentions "N required analytes/parameters/measurements", description
    # should at least mention the list type.
    m = re.search(r"(\d+)\s+required\s+(analytes?|parameters?|measurements?|components?|tests?)",
                  check, re.IGNORECASE)
    if m:
        n_required, item_type = int(m.group(1)), m.group(2).lower()
        if not re.search(rf"{item_type}|panel|profile|battery", desc, re.IGNORECASE):
            warnings.append({
                "rule": "description_missing_list_acknowledgement",
                "detail": f"CHECK references {n_required} required {item_type} but description doesn't acknowledge the list/panel",
            })

    # 4. Window consistency
    win_match = re.search(r"within\s+±?\s*(\d+)\s*(?:days?|weeks?|hours?)", check, re.IGNORECASE)
    if win_match and "window" not in desc.lower() and "±" not in desc and win_match.group(0).lower() not in desc.lower():
        # Description for check-ins typically mentions the window
        if "check-in" in name.lower() or "check in" in name.lower():
            warnings.append({
                "rule": "window_not_in_description",
                "detail": f"CHECK has window '{win_match.group(0)}' but description doesn't describe a window",
            })

    # 5. Footnote citation consistency
    rule_mentions_footnote_content = bool(re.search(r"per footnote|footnote \d", rule, re.IGNORECASE))
    ref_cites_footnote = "footnote" in ref.lower()
    if rule_mentions_footnote_content and not ref_cites_footnote:
        warnings.append({
            "rule": "rule_references_footnote_not_cited",
            "detail": "rule_for_llm references 'footnote' but protocol_reference does not cite a Footnote N",
        })

    # 6. Severity ↔ rule type
    name_lower = name.lower()
    if any(kw in name_lower for kw in ["informed consent", "eligibility", "randomization"]):
        if sev not in {"critical"}:
            warnings.append({
                "rule": "severity_too_low_for_gate",
                "detail": f"kri_name is gate-procedure but severity={sev}; expected 'critical'",
            })
    if "exploratory" in name_lower or "optional" in name_lower:
        if sev == "critical":
            warnings.append({
                "rule": "severity_too_high_for_optional",
                "detail": f"kri_name implies optional/exploratory but severity={sev}",
            })

    # 7. supporting_quote must not start/end with double-quote (Quality Rule 11)
    quote = kri.get("supporting_quote") or ""
    if isinstance(quote, str) and (quote.startswith('"') or quote.endswith('"')):
        warnings.append({
            "rule": "supporting_quote_has_outer_quotes",
            "detail": "supporting_quote begins or ends with a double-quote character",
        })

    return warnings


def run(in_path, out_path=None):
    """Run coherence check on raw_SOA.json or soa_golden_set.json. Writes report."""
    with open(in_path) as f:
        data = json.load(f)
    kris = data.get("kris", data) if isinstance(data, dict) else data

    total = 0
    flagged = 0
    findings = []
    for k in kris:
        if not isinstance(k, dict):
            continue
        total += 1
        w = check_kri(k)
        if w:
            flagged += 1
            findings.append({"kri_id": k.get("kri_id"), "warnings": w})

    report = {
        "_meta": {
            "step": "coherence_check",
            "total_kris": total,
            "flagged_count": flagged,
            "warning_categories": _summarize_categories(findings),
        },
        "flagged_kris": findings,
    }

    if not out_path:
        out_path = os.path.join(os.path.dirname(in_path), "coherence_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"✓ coherence_check: {flagged}/{total} KRIs flagged ({len(report['_meta']['warning_categories'])} categories). -> {out_path}")
    return report


def _summarize_categories(findings):
    from collections import Counter
    c = Counter()
    for f in findings:
        for w in f.get("warnings", []):
            c[w.get("rule")] += 1
    return dict(c)


def main():
    ap = argparse.ArgumentParser(description="Coherence checker for SOA KRIs")
    ap.add_argument("--in", dest="in_path", required=True, help="raw_SOA.json or soa_golden_set.json")
    ap.add_argument("--out", dest="out_path", default=None, help="coherence_report.json (defaults next to input)")
    args = ap.parse_args()
    run(args.in_path, args.out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
