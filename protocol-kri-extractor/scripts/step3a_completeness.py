"""
Step 3A — Completeness Critic
Checks extracted KRIs for completeness against the ontology.
For SOA: every procedure × visit cell must have a KRI.
For other categories: every subsection must have coverage.
Outputs gaps.json — fed back to step2 for re-extraction of missing items.
"""

import json, sys, re, os
import anthropic

SYSTEM_PROMPT = """You are a clinical trial quality control expert.
You audit KRI extraction outputs for completeness against a reference ontology.
You always return valid JSON. No markdown, no prose."""

def check_soa_completeness(client, kris: list, ontology: dict, protocol_id: str) -> dict:
    """Cross-reference every procedure × visit cell against extracted KRIs."""

    visits = ontology.get("visits", [])
    procedures = ontology.get("procedures", [])

    # Build expected set: (procedure_id, visit_id) for all required combinations
    expected = set()
    for proc in procedures:
        for v_id in proc.get("required_at", []):
            expected.add((proc["procedure_id"], v_id))

    # Build found set from KRIs — extract visit prefix and procedure hint from kri_name
    # Use LLM to do this mapping accurately
    kri_summary = [{"kri_id": k["kri_id"], "kri_name": k.get("kri_name", ""),
                    "rule_for_llm": (k.get("rule_for_llm") or "")[:80]}
                   for k in kris]

    visits_json = json.dumps(visits, indent=2)
    procs_json = json.dumps([{
        "procedure_id": p["procedure_id"],
        "canonical_name": p["canonical_name"],
        "required_at": p["required_at"]
    } for p in procedures], indent=2)

    prompt = f"""Protocol: {protocol_id}

You are checking whether the following extracted KRIs provide complete coverage 
of the Schedule of Activities.

ONTOLOGY — EXPECTED COVERAGE (procedure × visit combinations):
Visits: {visits_json}

Procedures (with required_at visit IDs):
{procs_json}

EXTRACTED SOA KRIs:
{json.dumps(kri_summary, indent=2)}

For each procedure in the ontology, check whether a KRI exists for each visit 
where it is required (in required_at list).

A KRI covers a procedure × visit if the KRI's visit prefix (e.g. V1-, S1-, V4-) 
matches the visit and the KRI name/rule refers to that procedure.

Return a JSON object:
{{
  "total_expected": <number of procedure×visit cells>,
  "total_covered": <number covered by at least one KRI>,
  "coverage_pct": <0-100>,
  "gaps": [
    {{
      "procedure_id": "...",
      "canonical_name": "...",
      "missing_at_visits": ["visit_id1", "visit_id2"],
      "severity": "CRITICAL|MODERATE|MINOR",
      "note": "brief explanation"
    }}
  ]
}}

Severity:
- CRITICAL: intervention, lab, or consent procedure missing at a treatment visit
- MODERATE: assessment missing at follow-up visit
- MINOR: administrative or low-risk procedure missing"""

    print(f"  Checking SOA completeness ({len(expected)} expected cells, {len(kris)} KRIs)...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw), response.usage.input_tokens + response.usage.output_tokens

def check_category_completeness(client, category: str, kris: list,
                                manifest: dict, ontology: dict) -> dict:
    """Check that all subsections in manifest have KRI coverage."""
    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    sections = manifest.get("section_map", {}).get(category, [])
    kri_summary = [{"kri_id": k["kri_id"], "kri_name": k.get("kri_name", ""),
                    "rule_for_llm": (k.get("rule_for_llm") or "")[:100]}
                   for k in kris]

    prompt = f"""Protocol: {protocol_id}
Category: {category}

The following protocol sections should be covered by KRIs:
{json.dumps(sections, indent=2)}

Extracted KRIs for this category:
{json.dumps(kri_summary, indent=2)}

Check: does every major requirement area in the sections have at least one KRI?
Common gaps to look for:
- ELIG: every numbered inclusion AND exclusion criterion should have ≥1 KRI
- SAF: reporting timelines, emergency management, pregnancy, stopping rules
- END: each named endpoint level (primary, key secondary, secondary, exploratory),
       each ICE type, each analysis set definition, key statistical rules
- OPS: IMP handling, blinding, records, regulatory/GCP

Return JSON:
{{
  "coverage_assessment": "brief overall assessment in 1-2 sentences",
  "total_kris": {len(kris)},
  "gaps": [
    {{
      "area": "short description of what is missing",
      "expected_kri_count": <estimate>,
      "severity": "CRITICAL|MODERATE|MINOR",
      "protocol_hint": "section number or topic where this content lives"
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw), response.usage.input_tokens + response.usage.output_tokens

def run_completeness_check(output_dir: str, manifest_path: str, ontology_path: str):
    client = anthropic.Anthropic()

    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(ontology_path) as f:
        ontology = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    print(f"\nCompleteness check: {protocol_id}")

    all_gaps = {}
    total_tokens = 0

    for cat in ["SOA", "ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(output_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            print(f"  {cat}: no raw file found — skipping")
            continue

        with open(raw_path) as f:
            raw_data = json.load(f)
        kris = raw_data.get("kris", [])
        print(f"\n  {cat}: {len(kris)} KRIs")

        try:
            if cat == "SOA":
                result, tokens = check_soa_completeness(client, kris, ontology, protocol_id)
                pct = result.get("coverage_pct", 0)
                gaps = result.get("gaps", [])
                print(f"    Coverage: {pct:.0f}% ({result.get('total_covered')}/{result.get('total_expected')})")
            else:
                result, tokens = check_category_completeness(client, cat, kris, manifest, ontology)
                gaps = result.get("gaps", [])
                print(f"    Assessment: {result.get('coverage_assessment', '')[:80]}")

            total_tokens += tokens
            critical = [g for g in gaps if g.get("severity") == "CRITICAL"]
            moderate = [g for g in gaps if g.get("severity") == "MODERATE"]
            print(f"    Gaps: {len(gaps)} ({len(critical)} CRITICAL, {len(moderate)} MODERATE)")
            for g in critical[:3]:
                area = g.get("area") or g.get("canonical_name", "")
                print(f"      ⚠ CRITICAL: {area[:70]}")

            all_gaps[cat] = {"result": result, "tokens": tokens}

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback; traceback.print_exc()

    # Save gaps report
    out_path = os.path.join(output_dir, "gaps_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {"step": "3A", "protocol_id": protocol_id, "tokens_used": total_tokens},
            "gaps_by_category": all_gaps
        }, f, indent=2)
    print(f"\n  Saved → {out_path}")
    print(f"  Total tokens: {total_tokens}")

if __name__ == "__main__":
    PROTOCOLS = {
        "ENX-CL-05-002": "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002",
        "B1481038":       "/home/claude/protocol-kri-extractor/output/B1481038",
        "LCZ696G2301":    "/home/claude/protocol-kri-extractor/output/LCZ696G2301"
    }
    target = sys.argv[1] if len(sys.argv) > 1 else "ENX-CL-05-002"
    d = PROTOCOLS[target]
    run_completeness_check(d, os.path.join(d, "manifest.json"), os.path.join(d, "ontology.json"))
