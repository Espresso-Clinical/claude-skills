"""
Step 3A — Completeness Critic
Checks extracted KRIs for completeness against the ontology.
For SOA: every procedure × visit cell must have a KRI. Two complementary checks —
(1) check_soa_completeness: LLM, coverage vs the ontology's required_at;
(2) check_grid_coverage (S4): deterministic, every Camelot atomic-grid X-mark
    (procedure × visit) must map to a rule — the grid is the source of truth (Rule #7).
For other categories: every subsection must have coverage.
Outputs gaps.json — fed back to step2 for re-extraction of missing items.
"""

import json, sys, re, os
import anthropic

SYSTEM_PROMPT = """You are a clinical trial quality control expert.
You audit KRI extraction outputs for completeness against a reference ontology.
You always return valid JSON. No markdown, no prose."""

def _normalize_proc(name: str) -> str:
    """Normalize a procedure name for grid↔KRI matching: lowercase, strip visit
    windows, drop non-alphanumerics."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\([^()]*(?:(?:days?|weeks?)\s*\d+|±\s*\d+\s*day|bi-?weekly|schedule)[^()]*\)", " ", s)
    s = re.sub(r"±\s*\d+\s*days?", " ", s)
    s = re.sub(r"\b(?:days?|weeks?)\s*\d+\s*[-–—]\s*\d+\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def check_grid_coverage(atomic_grid: dict, kris: list) -> dict:
    """S4 — deterministic coverage gate: every atomic-grid X-mark (procedure × visit)
    must map to a procedure KRI. Flags any X-mark with no matching rule.

    The Camelot SoA grid is the single source of truth for which procedures occur at
    which visits (Quality Rule #7). This is ZERO-LLM and complements the ontology-based
    check_soa_completeness() above (which judges coverage against the LLM ontology)."""
    units = atomic_grid.get("atomic_units", []) or []

    # Covered set from KRI names of the form "{visit_id} - {procedure}".
    covered = set()
    for k in kris:
        name = k.get("kri_name") or ""
        if " - " not in name:
            continue
        visit, proc = name.split(" - ", 1)
        covered.add((visit.strip().lower(), _normalize_proc(proc)))

    uncovered, seen = [], set()
    for u in units:
        visit = (u.get("visit_atomic") or "").strip()
        key = (visit.lower(), _normalize_proc(u.get("procedure_atomic") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        if key not in covered:
            uncovered.append({
                "procedure": u.get("procedure_atomic"),
                "visit": visit,
                "unit_id": u.get("unit_id"),
                "umbrella_origin": u.get("umbrella_origin"),
                "severity": "CRITICAL",
            })
    return {
        "check": "grid_coverage",
        "total_grid_cells": len(seen),
        "covered_cells": len(seen) - len(uncovered),
        "uncovered_cells": len(uncovered),
        "uncovered": uncovered,
    }


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
                # S4 — deterministic grid-truth coverage (Camelot grid = source of truth)
                grid_path = os.path.join(output_dir, "soa_atomic_grid.json")
                if os.path.exists(grid_path):
                    with open(grid_path) as gf:
                        atomic_grid = json.load(gf)
                    grid_cov = check_grid_coverage(atomic_grid, kris)
                    result["grid_coverage"] = grid_cov
                    print(f"    Grid coverage: {grid_cov['covered_cells']}/{grid_cov['total_grid_cells']} "
                          f"X-marks; {grid_cov['uncovered_cells']} with NO matching rule")
                    for uc in grid_cov["uncovered"][:5]:
                        print(f"      ⚠ uncovered grid X-mark: {uc['visit']} - {str(uc['procedure'])[:50]}")
                else:
                    print("    ⚠ soa_atomic_grid.json not found — skipping grid-coverage check")
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


def run_completeness(output_dir: str):
    """run.py entry point (Step 14) — resolves manifest.json / ontology.json from the
    run dir and delegates to run_completeness_check(). (Previously run.py imported this
    name but it was undefined, so Step 14 raised ImportError at runtime.)"""
    return run_completeness_check(
        output_dir,
        os.path.join(output_dir, "manifest.json"),
        os.path.join(output_dir, "ontology.json"),
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 3A — Completeness check")
    parser.add_argument("--dir", required=True, help="Run directory (must contain manifest.json, ontology.json, raw_*.json)")
    args = parser.parse_args()

    run_completeness_check(
        args.dir,
        os.path.join(args.dir, "manifest.json"),
        os.path.join(args.dir, "ontology.json")
    )
