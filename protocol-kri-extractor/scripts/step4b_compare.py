"""
Step 4B — Golden Set Comparison (Optional)
LLM-judge comparison of extracted_kris.json vs a provided golden_set.json.
Batch of 15, 4 verdicts: EQUIVALENT / SUBSET / SUPERSET / DIVERGENT.
Pass 1: 1:1 semantic matching.
Pass 2: sibling check for SUBSET cases (split rules).
Produces comparison_report.json. Golden set is never modified.
"""

import json, sys, re, os
import anthropic

SYSTEM_PROMPT = """You are a clinical trial monitoring expert comparing CRA verification rules.
Your job is to judge whether pairs of rules cover the same protocol requirement.
You always return valid JSON arrays. No markdown, no prose."""

FEW_SHOT = """SCORING RUBRIC:
- EQUIVALENT: Same verification intent, same data scope, same threshold. 
  Phrasing differences don't matter. 
  "Verify absence of X" = "Verify participant does not have X" = EQUIVALENT.
- SUBSET: Same requirement but extracted is less specific — missing a data source 
  ("by checking medication logs"), a clinical detail, a threshold, or a drug name.
- SUPERSET: Same requirement but extracted adds specificity beyond the golden.
  The extracted version is more complete than golden. Not a gap.
- DIVERGENT: Different verification intent, different visit scope, or different protocol rule.

CRA CONTEXT: These rules are used by clinical research associates to detect deviations
in a clinical trial. A rule like "Verify by checking medication logs" is meaningfully 
more specific than "Verify that washout was observed" because it names the data artifact.

FEW-SHOT EXAMPLES:
[PAIR] INC1
  GOLDEN:    Verify that the participant's age is ≥ 64 years at screening.
  EXTRACTED: Verify that the participant is ≥ 64 years old at the time of the first screening visit.
  VERDICT: EQUIVALENT — same requirement, same threshold, same timing.

[PAIR] SOA-V4-075 
  GOLDEN:    V4- Verify by checking medication logs that the participant maintained 
             a 48-hour washout for short-acting analgesics.
  EXTRACTED: V4- Verify that a ≥48-hour washout from short-acting analgesics was observed.
  VERDICT: SUBSET — same requirement but extracted omits "by checking medication logs".

[PAIR] OPS-IMP-001
  GOLDEN:    Verify that IMP storage logs document ≤ -150°C conditions.
  EXTRACTED: Verify that IMP storage logs document ≤ -150°C (or -80°C short-term) in a 
             secure, access-controlled area.
  VERDICT: SUPERSET — extracted adds the short-term condition and access control detail.

[PAIR] END-55
  GOLDEN:    Verify that WOMAC data after any ICE event is explicitly handled.
  EXTRACTED: Verify that post-ICE1 and post-ICE3 WOMAC data is censored per SAP.
  VERDICT: DIVERGENT — golden covers all 5 ICE types; extracted only covers ICE1/ICE3."""

def match_kris_by_id(golden_kris: list, extracted_kris: list) -> tuple[list, list, list]:
    """Split into: exact_id_matches, id_only_in_golden, id_only_in_extracted."""
    g_map = {k["kri_id"]: k for k in golden_kris}
    e_map = {k["kri_id"]: k for k in extracted_kris}

    matched_ids = set(g_map.keys()) & set(e_map.keys())
    only_golden = set(g_map.keys()) - set(e_map.keys())
    only_extracted = set(e_map.keys()) - set(g_map.keys())

    pairs = [(g_map[kid], e_map[kid]) for kid in sorted(matched_ids)]
    return pairs, [g_map[k] for k in sorted(only_golden)], [e_map[k] for k in sorted(only_extracted)]

def judge_batch(client, pairs: list) -> tuple[list, int]:
    """Judge a batch of (golden, extracted) KRI pairs."""
    pair_text = "\n\n".join(
        f"[PAIR {i+1}] {g['kri_id']}\n"
        f"  GOLDEN:    {g.get('rule_for_llm') or '(no rule)'}\n"
        f"  EXTRACTED: {e.get('rule_for_llm') or '(no rule)'}"
        for i, (g, e) in enumerate(pairs)
    )

    prompt = f"""{FEW_SHOT}

NOW EVALUATE THE FOLLOWING {len(pairs)} PAIRS.
Return ONLY a JSON array with exactly {len(pairs)} objects:
[
  {{"kri_id": "...", "verdict": "EQUIVALENT|SUBSET|SUPERSET|DIVERGENT", 
    "reason": "one sentence max"}}
]

{pair_text}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    results = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return results, tokens

def sibling_check(client, subset_pairs: list, extracted_kris: list) -> list:
    """Pass 2: for SUBSET cases, check if a sibling extracted KRI completes the coverage."""
    if not subset_pairs:
        return []

    e_map = {k["kri_id"]: k for k in extracted_kris}
    # Group extracted by visit prefix for finding siblings
    siblings_by_visit = {}
    for k in extracted_kris:
        prefix = re.match(r'^([A-Z0-9]+-[A-Z0-9]+)', k.get("kri_id", ""))
        if prefix:
            p = prefix.group(1)
            siblings_by_visit.setdefault(p, []).append(k)

    results = []
    for g, e in subset_pairs:
        # Find siblings: same visit prefix, different ID
        prefix = re.match(r'^([A-Z0-9]+-[A-Z0-9]+)', e.get("kri_id", ""))
        siblings = []
        if prefix:
            p = prefix.group(1)
            siblings = [k for k in siblings_by_visit.get(p, [])
                       if k["kri_id"] != e["kri_id"]][:3]

        if not siblings:
            results.append({"kri_id": g["kri_id"], "pass2_verdict": "STILL_SUBSET", "reason": "no siblings found"})
            continue

        sibling_text = "\n".join(
            f"  SIBLING ({s['kri_id']}): {s.get('rule_for_llm', '')}"
            for s in siblings
        )

        prompt = f"""A golden KRI was scored SUBSET. Check if sibling extracted KRIs complete the coverage.

GOLDEN:
  {g['kri_id']}: {g.get('rule_for_llm', '')}

PRIMARY EXTRACTED MATCH:
  {e['kri_id']}: {e.get('rule_for_llm', '')}

SIBLING EXTRACTED KRIs (same visit group):
{sibling_text}

Does the PRIMARY + any combination of SIBLINGS together cover everything the GOLDEN requires?

Return JSON: {{"kri_id": "{g['kri_id']}", "pass2_verdict": "COMBINED_MATCH|STILL_SUBSET",
"contributing_siblings": ["list of sibling kri_ids that contribute"], "reason": "one sentence"}}"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        results.append(json.loads(raw))

    return results

def run_comparison(extracted_path: str, golden_path: str, output_dir: str):
    client = anthropic.Anthropic()

    with open(extracted_path) as f:
        extracted_data = json.load(f)
    with open(golden_path) as f:
        golden_data = json.load(f)

    extracted_kris = extracted_data.get("kris", [])
    golden_kris = golden_data.get("kris", [])

    protocol_id = extracted_data.get("_meta", {}).get("protocol", "UNKNOWN")
    print(f"\nComparing: {protocol_id}")
    print(f"  Extracted: {len(extracted_kris)} KRIs")
    print(f"  Golden:    {len(golden_kris)} KRIs")

    # Split by ID overlap
    pairs, only_golden, only_extracted = match_kris_by_id(golden_kris, extracted_kris)
    print(f"\n  ID-matched pairs:      {len(pairs)}")
    print(f"  Only in golden:        {len(only_golden)}")
    print(f"  Only in extracted:     {len(only_extracted)}")

    # Pass 1: judge all matched pairs in batches of 15
    BATCH_SIZE = 15
    all_verdicts = []
    total_tokens = 0

    print(f"\n  Pass 1: judging {len(pairs)} pairs in batches of {BATCH_SIZE}...")
    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i:i+BATCH_SIZE]
        print(f"    Batch {i//BATCH_SIZE + 1}/{(len(pairs)-1)//BATCH_SIZE + 1}...", end=" ")
        verdicts, tokens = judge_batch(client, batch)
        all_verdicts.extend(verdicts)
        total_tokens += tokens
        print(f"{tokens} tokens")

    # Tally Pass 1
    counts = {"EQUIVALENT": 0, "SUBSET": 0, "SUPERSET": 0, "DIVERGENT": 0}
    verdict_map = {v["kri_id"]: v for v in all_verdicts}
    for v in all_verdicts:
        counts[v.get("verdict", "DIVERGENT")] += 1

    # Pass 2: sibling check for SUBSET cases
    subset_kri_ids = {v["kri_id"] for v in all_verdicts if v.get("verdict") == "SUBSET"}
    g_map = {k["kri_id"]: k for k in golden_kris}
    e_map = {k["kri_id"]: k for k in extracted_kris}
    subset_pairs = [(g_map[kid], e_map[kid]) for kid in subset_kri_ids if kid in g_map and kid in e_map]

    print(f"\n  Pass 2: sibling check for {len(subset_pairs)} SUBSET cases...")
    pass2_results = sibling_check(client, subset_pairs, extracted_kris)
    pass2_map = {r["kri_id"]: r for r in pass2_results}

    # Adjust counts: COMBINED_MATCH → treat as EQUIVALENT
    combined_matches = sum(1 for r in pass2_results if r.get("pass2_verdict") == "COMBINED_MATCH")
    counts["EQUIVALENT"] += combined_matches
    counts["SUBSET"] -= combined_matches

    # Build final report
    by_cat = {}
    for gk in golden_kris:
        cat = gk.get("category_id", "UNKNOWN")
        kid = gk["kri_id"]
        verdict_info = verdict_map.get(kid, {})
        verdict = verdict_info.get("verdict", "MISSING")
        if kid in pass2_map and pass2_map[kid].get("pass2_verdict") == "COMBINED_MATCH":
            verdict = "COMBINED_MATCH"
        by_cat.setdefault(cat, {"EQUIVALENT": 0, "SUBSET": 0, "SUPERSET": 0,
                                 "DIVERGENT": 0, "COMBINED_MATCH": 0, "MISSING": 0})
        by_cat[cat][verdict] += 1

    # Overall score
    total_golden = len(golden_kris)
    good = counts["EQUIVALENT"] + counts["SUPERSET"]
    partial = counts["SUBSET"]
    score = (good + 0.5 * partial) / total_golden * 100 if total_golden else 0

    print(f"\n  {'='*45}")
    print(f"  COMPARISON RESULTS")
    print(f"  {'='*45}")
    print(f"  EQUIVALENT:     {counts['EQUIVALENT']:>4} ({counts['EQUIVALENT']/total_golden:.0%})")
    print(f"  SUPERSET:       {counts['SUPERSET']:>4} ({counts['SUPERSET']/total_golden:.0%})")
    print(f"  SUBSET:         {counts['SUBSET']:>4} ({counts['SUBSET']/total_golden:.0%})")
    print(f"  DIVERGENT:      {counts['DIVERGENT']:>4} ({counts['DIVERGENT']/total_golden:.0%})")
    print(f"  MISSING:        {len(only_golden):>4}")
    print(f"  EXTRA (novel):  {len(only_extracted):>4}")
    print(f"  COMBINED_MATCH: {combined_matches:>4} (split rules resolved)")
    print(f"  {'─'*45}")
    print(f"  OVERALL SCORE:  {score:.0f}/100")
    verdict = "PASS" if score >= 80 else ("ITERATE" if score >= 60 else "REWORK")
    print(f"  RECOMMENDATION: {verdict}")

    print(f"\n  Per-category:")
    print(f"  {'CAT':<6} {'EQ':>4} {'SUP':>4} {'SUB':>5} {'DIV':>5} {'MISS':>5}")
    for cat in ["SOA", "ELIG", "SAF", "END", "OPS"]:
        c = by_cat.get(cat, {})
        print(f"  {cat:<6} {c.get('EQUIVALENT',0):>4} {c.get('SUPERSET',0):>4} "
              f"{c.get('SUBSET',0):>5} {c.get('DIVERGENT',0):>5} {c.get('MISSING',0):>5}")

    # Save
    out_path = os.path.join(output_dir, "comparison_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "step": "4B",
                "protocol_id": protocol_id,
                "extracted_count": len(extracted_kris),
                "golden_count": len(golden_kris),
                "overall_score": round(score, 1),
                "recommendation": verdict,
                "tokens_used": total_tokens
            },
            "counts": counts,
            "by_category": by_cat,
            "pass1_verdicts": all_verdicts,
            "pass2_results": pass2_results,
            "only_in_golden": [k["kri_id"] for k in only_golden],
            "only_in_extracted": [k["kri_id"] for k in only_extracted]
        }, f, indent=2)
    print(f"\n  Saved → {out_path}")
    print(f"  Total tokens: {total_tokens}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 4B — Compare extracted KRIs against golden set")
    parser.add_argument("--extracted", required=True, help="Path to extracted_kris.json")
    parser.add_argument("--golden",    required=True, help="Path to golden_set.json")
    parser.add_argument("--dir",       required=True, help="Output directory for comparison report")
    args = parser.parse_args()

    run_comparison(
        extracted_path=args.extracted,
        golden_path=args.golden,
        output_dir=args.dir
    )
