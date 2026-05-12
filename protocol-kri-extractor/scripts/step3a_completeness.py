"""
Step 3A — Completeness Check
For each in-scope domain (ELIG, SAF, END, OPS), verify that every obligation
sentence recorded in `{domain}_obligation_inventory.json` (Step 2.5) has at
least one KRI whose `supporting_quote` covers it.

Also runs the H4 SAF heuristic — the single retained heuristic from the prior
H1–H10 set after SOA extraction moved to the separate `soa-kri-extractor`
skill. H4 verifies that raw_SAF.json contains a KRI defining the AE collection
window starting at first IP dose.

Outputs gaps_report.json — fed back to step 2 / Tier 3 for re-extraction or
candidate promotion of missing items.
"""

import json, sys, re, os
import anthropic

SYSTEM_PROMPT = """You are a clinical trial quality control expert.
You audit KRI extraction outputs for completeness against an obligation
inventory and against universal clinical-trial heuristics.
You always return valid JSON. No markdown, no prose."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_obligation_coverage(domain: str, kris: list, inventory: dict) -> dict:
    """Determine which obligation sentences in the inventory are covered by ≥1 KRI."""
    obligations = inventory.get("obligations", []) if isinstance(inventory, dict) else []
    if not obligations:
        return {
            "domain": domain,
            "total_expected": 0,
            "total_covered": 0,
            "coverage_pct": 100.0,
            "gaps": [],
        }

    quotes = [_normalize(k.get("supporting_quote", "")) for k in kris]
    covered, gaps = 0, []
    for ob in obligations:
        sentence = _normalize(ob.get("sentence", ""))
        if not sentence:
            continue
        is_covered = any(sentence in q or q in sentence for q in quotes if q)
        if is_covered:
            covered += 1
        else:
            gaps.append({
                "obligation_sentence": ob.get("sentence"),
                "page": ob.get("page"),
                "section": ob.get("section"),
                "severity": ob.get("severity", "MODERATE"),
                "note": "uncovered obligation — promote to Tier 3 / orphan scan",
            })

    total = len([o for o in obligations if _normalize(o.get("sentence", ""))])
    return {
        "domain": domain,
        "total_expected": total,
        "total_covered": covered,
        "coverage_pct": round(100.0 * covered / total, 1) if total else 100.0,
        "gaps": gaps,
    }


def check_h4_ae_collection_window(client, saf_kris: list, protocol_id: str) -> dict:
    """H4 — verify SAF has a KRI defining the AE collection window starting at
    first IP dose (and ending at a defined cutoff). The only retained heuristic
    after SOA extraction moved to soa-kri-extractor.
    """
    if not saf_kris:
        return {
            "h4_covered": False,
            "h4_kri_id": None,
            "h4_reason": "raw_SAF.json is empty — no AE-collection-window KRI present",
        }

    summary = [
        {"kri_id": k["kri_id"], "kri_name": k.get("kri_name", ""),
         "rule_for_llm": (k.get("rule_for_llm") or "")[:200]}
        for k in saf_kris
    ]

    prompt = f"""Protocol: {protocol_id}

You are checking AE-collection-window coverage in the SAF KRI set.

Does at least one SAF KRI clearly define when adverse-event (AE) collection
STARTS (relative to first IP administration) AND when it ENDS (e.g. last dose,
N days post-last-dose, end of follow-up)?

SAF KRIs:
{json.dumps(summary, indent=2)}

Return JSON:
{{
  "h4_covered": true | false,
  "h4_kri_id": "<id of the covering KRI, or null>",
  "h4_reason": "<one sentence — either where it is covered, or what is missing>"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


def run_completeness_check(output_dir: str, manifest_path: str):
    client = anthropic.Anthropic()

    with open(manifest_path) as f:
        manifest = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    print(f"\nCompleteness check: {protocol_id}")

    all_results = {}

    for cat in ["ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(output_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            print(f"  {cat}: no raw file found — skipping")
            continue
        with open(raw_path) as f:
            kris = json.load(f).get("kris", [])

        inv_path = os.path.join(output_dir, f"{cat}_obligation_inventory.json")
        inventory = {}
        if os.path.exists(inv_path):
            with open(inv_path) as f:
                inventory = json.load(f)

        result = check_obligation_coverage(cat, kris, inventory)
        critical = [g for g in result["gaps"] if g.get("severity") == "CRITICAL"]
        print(f"  {cat}: {len(kris)} KRIs — coverage "
              f"{result['coverage_pct']:.0f}% ({result['total_covered']}/{result['total_expected']}), "
              f"gaps: {len(result['gaps'])} ({len(critical)} CRITICAL)")
        all_results[cat] = result

    # H4 SAF heuristic
    saf_path = os.path.join(output_dir, "raw_SAF.json")
    if os.path.exists(saf_path):
        with open(saf_path) as f:
            saf_kris = json.load(f).get("kris", [])
        try:
            h4 = check_h4_ae_collection_window(client, saf_kris, protocol_id)
            print(f"\n  H4 SAF heuristic: covered={h4.get('h4_covered')} — "
                  f"{h4.get('h4_reason', '')[:80]}")
            all_results["_h4_saf"] = h4
        except Exception as e:
            print(f"  H4 SAF heuristic — ERROR: {e}")

    out_path = os.path.join(output_dir, "gaps_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {"step": "3A", "protocol_id": protocol_id},
            "obligation_coverage_by_domain": {
                k: v for k, v in all_results.items() if not k.startswith("_")
            },
            "h4_saf_heuristic": all_results.get("_h4_saf"),
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved → {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 3A — Completeness check")
    parser.add_argument("--dir", required=True, help="Run directory (must contain manifest.json and raw_*.json)")
    args = parser.parse_args()

    run_completeness_check(args.dir, os.path.join(args.dir, "manifest.json"))
