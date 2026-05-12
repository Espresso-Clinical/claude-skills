"""
Step 3C — Internal Consistency Check
Groups extracted KRIs by procedure family (using ontology).
For each family appearing at 3+ visits, checks that details present
at some visits are not missing at others without a protocol-stated reason.
Flags only — does not auto-fix. Human decides.
"""

import json, sys, re, os
import pdfplumber
import anthropic

SYSTEM_PROMPT = """You are a clinical trial protocol quality expert.
You check that KRI rules for the same procedure are internally consistent across visits.
You always return valid JSON. No markdown, no prose."""

def extract_page_text(pdf_path: str, page_num: int) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if 1 <= page_num <= len(pdf.pages):
            return pdf.pages[page_num-1].extract_text() or ""
    return ""

def group_by_procedure(kris: list, ontology: dict) -> dict:
    """Map each SOA KRI to a procedure family using ontology canonical names."""
    # Build lookup: visit_id → original_label
    visit_labels = {v["visit_id"]: v["original_label"]
                    for v in ontology.get("visits", [])}

    # Build procedure name map from ontology
    proc_map = {}
    for proc in ontology.get("procedures", []):
        proc_map[proc["procedure_id"]] = proc["canonical_name"]

    # Group KRIs by extracting procedure name from kri_name
    # Strip visit prefix (e.g. "V1- ", "S1- ", "V4- ")
    families = {}
    for kri in kris:
        name = kri.get("kri_name", "")
        # Strip visit prefix pattern like "V1- ", "S2- ", "V4-", "UNS-"
        bare = re.sub(r'^[A-Z0-9]+[-–]\s*', '', name).strip()
        # Normalize
        bare_norm = bare.lower().strip()
        if bare_norm:
            families.setdefault(bare_norm, {
                "canonical_name": bare,
                "kris": []
            })
            families[bare_norm]["kris"].append(kri)

    # Only return families with 3+ members (worth checking)
    return {k: v for k, v in families.items() if len(v["kris"]) >= 3}

def check_family_consistency(client, family_name: str, kris: list,
                              pdf_path: str, ontology: dict) -> dict:
    """Check consistency within a procedure family."""

    kri_list = json.dumps([{
        "kri_id": k["kri_id"],
        "kri_name": k.get("kri_name", ""),
        "rule_for_llm": k.get("rule_for_llm", ""),
        "additional_footnotes": k.get("additional_footnotes", "")
    } for k in kris], indent=2)

    # Get protocol pages from references
    pages_to_check = set()
    for k in kris:
        ref = k.get("protocol_reference", "")
        m = re.search(r'[Pp]age\s+(\d+)', ref)
        if m:
            pages_to_check.add(int(m.group(1)))

    protocol_context = ""
    if pages_to_check:
        page_texts = []
        for pg in sorted(list(pages_to_check)[:4]):  # max 4 pages
            text = extract_page_text(pdf_path, pg)
            if text:
                page_texts.append(f"[PAGE {pg}]\n{text[:1500]}")  # truncate per page
        protocol_context = "\n\n".join(page_texts)

    prompt = f"""Check internal consistency for the "{family_name}" procedure across these visits.

EXTRACTED KRIs:
{kri_list}

RELEVANT PROTOCOL PAGES:
{protocol_context if protocol_context else "(no page references found — use your knowledge of the procedure)"}

Identify inconsistencies where:
1. A detail is present in some visit KRIs but absent from others with no visit-specific reason
   (e.g. "without shoes" for weight, "supine" for vitals, "including CRP" for labs,
   "by checking medication logs" for washout, specific drug names in safety procedures)
2. The same concept is phrased differently across visits in a way that could confuse a CRA
3. A visit-specific condition was correctly added at some visits but missed at others

IMPORTANT: Only flag if the protocol text (or standard clinical practice) indicates
the detail SHOULD be consistent. Some differences are intentional (e.g. vitals measured
twice on treatment days but once on follow-up days). Mark those as intentional.

Return JSON:
{{
  "family": "{family_name}",
  "visit_count": {len(kris)},
  "overall_status": "CONSISTENT|HAS_INCONSISTENCIES",
  "inconsistencies": [
    {{
      "description": "what the inconsistency is",
      "affected_kri_ids": ["list of KRI IDs that have the issue"],
      "reference_kri_ids": ["list of KRI IDs that have the correct/complete version"],
      "could_be_intentional": true/false,
      "protocol_quote": "verbatim quote ≤20 words that shows what the protocol says",
      "recommendation": "what the affected KRIs should say"
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    result = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return result, tokens

def run_consistency_check(output_dir: str, pdf_path: str, ontology_path: str):
    client = anthropic.Anthropic()

    with open(ontology_path) as f:
        ontology = json.load(f)

    # Load SOA KRIs
    soa_path = os.path.join(output_dir, "raw_SOA.json")
    if not os.path.exists(soa_path):
        print("  No raw_SOA.json found — skipping consistency check")
        return

    with open(soa_path) as f:
        soa_data = json.load(f)
    kris = soa_data.get("kris", [])

    protocol_id = soa_data.get("_meta", {}).get("protocol_id", "UNKNOWN")
    print(f"\nConsistency check: {protocol_id} ({len(kris)} SOA KRIs)")

    # Group by procedure family
    families = group_by_procedure(kris, ontology)
    print(f"  Procedure families with 3+ visits: {len(families)}")
    for fname, fdata in sorted(families.items(), key=lambda x: -len(x[1]["kris"]))[:8]:
        print(f"    '{fdata['canonical_name']}': {len(fdata['kris'])} visits")

    # Check each family
    all_results = []
    total_tokens = 0
    flagged = 0

    for fname, fdata in families.items():
        try:
            result, tokens = check_family_consistency(
                client, fdata["canonical_name"], fdata["kris"], pdf_path, ontology
            )
            total_tokens += tokens
            all_results.append(result)

            issues = result.get("inconsistencies", [])
            real_issues = [i for i in issues if not i.get("could_be_intentional")]
            if real_issues:
                flagged += len(real_issues)
                print(f"\n  ⚠ {fdata['canonical_name']} ({len(fdata['kris'])} visits):")
                for issue in real_issues:
                    print(f"    - {issue['description'][:80]}")
                    print(f"      Affected: {issue['affected_kri_ids']}")
                    print(f"      Fix: {(issue.get('recommendation') or '')[:80]}")

        except Exception as e:
            print(f"  ERROR checking '{fname}': {e}")

    # Save report
    out_path = os.path.join(output_dir, "consistency_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "step": "3C",
                "protocol_id": protocol_id,
                "families_checked": len(all_results),
                "total_inconsistencies_flagged": flagged,
                "tokens_used": total_tokens
            },
            "families": all_results
        }, f, indent=2)

    print(f"\n  Families checked: {len(all_results)}")
    print(f"  Inconsistencies flagged: {flagged}")
    print(f"  Saved → {out_path}")
    print(f"  Tokens: {total_tokens}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 3C — Consistency check")
    parser.add_argument("--dir", required=True, help="Run directory (must contain ontology.json, raw_*.json)")
    parser.add_argument("--pdf", required=True, help="Path to protocol PDF")
    args = parser.parse_args()

    run_consistency_check(
        args.dir,
        args.pdf,
        os.path.join(args.dir, "ontology.json")
    )
