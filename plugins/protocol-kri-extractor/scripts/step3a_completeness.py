"""
Step 3A — Completeness Gate (BLOCKING)

Two complementary coverage checks, both blocking (Fix #2 + Fix #4):

  1. SECTION coverage (Fix #2): every in-scope section in manifest.section_inventory
     (disposition ELIG/SAF/END/OPS) must have at least one KRI citing one of its
     pages. SOA / non_substantive sections are exempt. A still-empty in-scope
     section — after the Step 3.5 orphan scan has already run — is a gap.

  2. OBLIGATION coverage (Fix #4): every conduct-constraining statement in each
     domain's {domain}_obligation_inventory.json (Step 2.5) must be covered by at
     least one KRI. Coverage is decided by an LLM coverage judge (semantic — does
     a KRI catch a violation of the obligation?), NOT crude substring matching,
     because the high-recall inventory sentences are longer than the ≤30-word
     quotes. The prior vacuous behaviour (empty inventory → 100%) is removed: a
     domain with mapped sections but a missing inventory is a BLOCKING error
     (Step 2.5 was not run).

Escape hatch (so the run can still finish): a gap clears if it is (a) covered,
(b) the section is re-tagged non_substantive in the manifest, or (c) the user
acknowledges it in gaps_resolutions.json. Only UNRESOLVED gaps block.

Also runs the H4 SAF heuristic (AE-collection-window presence) — unchanged.

Output: gaps_report.json. Returns a pass/fail boolean to run.py's gate framework.
"""

import json, sys, re, os, hashlib
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed

IN_SCOPE_DOMAINS = ("ELIG", "SAF", "END", "OPS")

SYSTEM_PROMPT = """You are a clinical trial quality control expert.
You audit KRI extraction outputs for completeness against an obligation
inventory and against universal clinical-trial heuristics.
You always return valid JSON. No markdown, no prose."""

COVERAGE_JUDGE_SYSTEM = """You are a clinical trial monitoring auditor deciding
whether protocol obligations are COVERED by extracted KRIs. You always return a
valid JSON array, no markdown, no prose."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _pages_cited(ref: str) -> set:
    """All page numbers referenced in a protocol_reference / combined_ref string.
    Handles 'p.70', 'p.70-71', 'p.70-p.72', 'pp. 70-72'."""
    pages = set()
    for m in re.finditer(r"p+\.?\s*(\d+)\s*(?:[-–]\s*p?\.?\s*(\d+))?", ref or "", re.IGNORECASE):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        lo, hi = min(a, b), max(a, b)
        if hi - lo <= 60:  # guard against absurd ranges from a parse glitch
            pages.update(range(lo, hi + 1))
    return pages


def _kri_summary(k: dict) -> str:
    """A model-readable summary of a KRI for the coverage judge. Uses name +
    rule_for_llm (if present) + supporting_quote, so it keeps working even after
    rule_for_llm is later removed from the schema."""
    parts = [
        (k.get("kri_name") or "").strip(),
        (k.get("rule_for_llm") or "").strip(),
        (k.get("supporting_quote") or "").strip(),
    ]
    return " | ".join(p for p in parts if p)


def _load_all_kris(output_dir: str) -> list:
    """Flatten every KRI across raw_{domain}.json (post orphan-scan promotion)."""
    out = []
    for dom in IN_SCOPE_DOMAINS:
        path = os.path.join(output_dir, f"raw_{dom}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        kris = data.get("kris", data) if isinstance(data, dict) else data
        for k in (kris or []):
            if isinstance(k, dict):
                k = dict(k)
                k.setdefault("_domain", dom)
                k["_pages"] = _pages_cited(
                    (k.get("protocol_reference") or "") + " " + (k.get("combined_ref") or "")
                )
                out.append(k)
    return out


# ─── Section coverage (Fix #2) ───────────────────────────────────────────────

def check_section_coverage(manifest: dict, all_kris: list) -> dict:
    inventory = manifest.get("section_inventory", []) or []
    gaps, checked = [], 0
    for s in inventory:
        disp = (s.get("disposition") or "").strip().upper()
        if disp not in IN_SCOPE_DOMAINS:
            continue  # out_of_scope_soa / non_substantive are exempt
        checked += 1
        pa = s.get("pages_approx") or [None, None]
        if not pa or not pa[0]:
            gaps.append({"section": s.get("section_number"), "title": s.get("title"),
                         "pages": pa, "disposition": disp,
                         "reason": "no page range resolved for this section"})
            continue
        start = int(pa[0]); end = int(pa[1] or pa[0])
        rng = set(range(start, end + 1))
        covered = any(rng & (k.get("_pages") or set()) for k in all_kris)
        if not covered:
            gaps.append({"section": s.get("section_number"), "title": s.get("title"),
                         "pages": pa, "disposition": disp,
                         "reason": "no KRI cites any page in this in-scope section"})
    return {"sections_checked": checked, "gaps": gaps}


# ─── Obligation coverage via LLM judge (Fix #4, decision A=(a)) ───────────────

def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _safe_json_array(raw: str):
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
    return []


def _judge_batch(client, batch: list, candidates: list) -> dict:
    """Ask the LLM which obligations in `batch` are covered by `candidates`.
    Returns {local_index: {covered, covering_kri_id, reason}}."""
    if not candidates:
        return {i: {"covered": False, "covering_kri_id": None,
                    "reason": "no KRI cites this page region"} for i in range(len(batch))}

    ob_lines = [{"i": i, "sentence": ob["sentence"], "page": ob["page"], "type": ob.get("type")}
                for i, ob in enumerate(batch)]
    cand_lines = [{"kri_id": c.get("kri_id"), "page": sorted(c.get("_pages") or [])[:3],
                   "summary": _kri_summary(c)[:400]} for c in candidates]

    prompt = f"""Decide whether each protocol OBLIGATION is COVERED by at least one CANDIDATE KRI.

An obligation is COVERED only if a KRI would CATCH A VIOLATION of it — i.e. it checks
the same requirement: same subject, same condition/threshold, same time-scope, same
population. Wording differences are irrelevant. Partial coverage (a KRI covers only part
of a compound obligation, e.g. the "prior to" half but not the "during the study" half)
is NOT covered. A KRI on a different requirement that merely shares a topic is NOT covered.

OBLIGATIONS:
{json.dumps(ob_lines, ensure_ascii=False)}

CANDIDATE KRIs:
{json.dumps(cand_lines, ensure_ascii=False)}

Return a JSON array, one object per obligation index i:
[{{"i": 0, "covered": true, "covering_kri_id": "SAF-AE-010", "reason": "<=15 words"}}]
Return ONLY the JSON array."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            system=COVERAGE_JUDGE_SYSTEM,
        )
        verdicts = _safe_json_array(resp.content[0].text)
    except Exception as e:
        # Fail closed: treat as uncovered so a judge error can't hide a gap.
        return {i: {"covered": False, "covering_kri_id": None,
                    "reason": f"coverage judge error: {e}"} for i in range(len(batch))}

    out = {}
    for v in verdicts:
        if isinstance(v, dict) and isinstance(v.get("i"), int):
            out[v["i"]] = {"covered": bool(v.get("covered")),
                           "covering_kri_id": v.get("covering_kri_id"),
                           "reason": (v.get("reason") or "")[:160]}
    for i in range(len(batch)):
        out.setdefault(i, {"covered": False, "covering_kri_id": None,
                           "reason": "no verdict returned — treated as uncovered"})
    return out


def check_obligation_coverage(client, domain: str, obligations: list, all_kris: list) -> dict:
    """LLM-judged coverage for one domain's obligations. Candidate KRIs for each
    batch are those citing the obligation pages ±1 (any domain)."""
    by_page = {}
    for k in all_kris:
        for p in (k.get("_pages") or []):
            by_page.setdefault(p, []).append(k)

    covered, gaps = 0, []
    for batch in _chunks(obligations, 12):
        seen, candidates = set(), []
        for ob in batch:
            for p in range(ob.get("page", 0) - 1, ob.get("page", 0) + 2):
                for k in by_page.get(p, []):
                    if id(k) not in seen:
                        seen.add(id(k)); candidates.append(k)
        verdicts = _judge_batch(client, batch, candidates)
        for i, ob in enumerate(batch):
            v = verdicts[i]
            if v["covered"]:
                covered += 1
            else:
                gaps.append({"sentence": ob["sentence"], "page": ob.get("page"),
                             "section": ob.get("section"), "type": ob.get("type"),
                             "severity": ob.get("severity", "MODERATE"),
                             "reason": v["reason"]})
    total = len(obligations)
    return {"domain": domain, "total_expected": total, "total_covered": covered,
            "coverage_pct": round(100.0 * covered / total, 1) if total else 100.0,
            "gaps": gaps}


# ─── H4 SAF heuristic (unchanged) ────────────────────────────────────────────

def check_h4_ae_collection_window(client, saf_kris: list, protocol_id: str) -> dict:
    if not saf_kris:
        return {"h4_covered": False, "h4_kri_id": None,
                "h4_reason": "raw_SAF.json is empty — no AE-collection-window KRI present"}
    summary = [{"kri_id": k["kri_id"], "kri_name": k.get("kri_name", ""),
                "rule_for_llm": (k.get("rule_for_llm") or k.get("supporting_quote") or "")[:200]}
               for k in saf_kris]
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
        model="claude-sonnet-4-20250514", max_tokens=400,
        messages=[{"role": "user", "content": prompt}], system=SYSTEM_PROMPT)
    raw = re.sub(r"^```[a-z]*\n?", "", response.content[0].text.strip())
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


# ─── Resolutions / escape hatch ──────────────────────────────────────────────

def _gap_key(domain: str, ob_gap: dict) -> str:
    raw = f"{domain}|{ob_gap.get('page')}|{ob_gap.get('section')}|{ob_gap.get('sentence','')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _load_resolutions(output_dir: str) -> dict:
    path = os.path.join(output_dir, "gaps_resolutions.json")
    if not os.path.exists(path):
        return {"sections": {}, "obligations": {}}
    try:
        with open(path) as f:
            r = json.load(f)
        return {"sections": r.get("sections", {}) or {},
                "obligations": r.get("obligations", {}) or {}}
    except (json.JSONDecodeError, OSError):
        return {"sections": {}, "obligations": {}}


def _ack(entry) -> bool:
    if entry is True:
        return True
    return isinstance(entry, dict) and bool(entry.get("acknowledged"))


# ─── Main ────────────────────────────────────────────────────────────────────

def run_completeness_check(output_dir: str, manifest_path: str) -> bool:
    """Returns True if the completeness gate passes (no UNRESOLVED gaps)."""
    client = anthropic.Anthropic()
    with open(manifest_path) as f:
        manifest = json.load(f)
    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    print(f"\nCompleteness gate: {protocol_id}")

    resolutions = _load_resolutions(output_dir)
    all_kris = _load_all_kris(output_dir)

    # 1) Section coverage ------------------------------------------------------
    sec_result = check_section_coverage(manifest, all_kris)
    sec_unresolved = [g for g in sec_result["gaps"]
                      if not _ack(resolutions["sections"].get(str(g.get("section"))))]
    print(f"  Section coverage: {sec_result['sections_checked']} in-scope sections, "
          f"{len(sec_result['gaps'])} empty ({len(sec_unresolved)} unresolved)")

    # 2) Obligation coverage (per domain) -------------------------------------
    obligation_by_domain, ob_unresolved_total = {}, 0
    inventory_errors = []
    mapped_domains = {d for d in IN_SCOPE_DOMAINS if manifest.get("section_map", {}).get(d)}

    def _domain_job(cat):
        inv_path = os.path.join(output_dir, f"{cat}_obligation_inventory.json")
        if not os.path.exists(inv_path):
            if cat in mapped_domains:
                return cat, None, f"{cat}: obligation inventory MISSING — Step 2.5 not run"
            return cat, {"domain": cat, "total_expected": 0, "total_covered": 0,
                         "coverage_pct": 100.0, "gaps": []}, None
        with open(inv_path) as f:
            obligations = json.load(f).get("obligations", [])
        return cat, check_obligation_coverage(client, cat, obligations, all_kris), None

    with ThreadPoolExecutor(max_workers=4) as ex:
        for cat, result, err in ex.map(_domain_job, IN_SCOPE_DOMAINS):
            if err:
                inventory_errors.append(err)
                print(f"  ✗ {err}")
                continue
            obligation_by_domain[cat] = result
            unresolved = [g for g in result["gaps"]
                          if not _ack(resolutions["obligations"].get(_gap_key(cat, g)))]
            for g in result["gaps"]:
                g["gap_key"] = _gap_key(cat, g)
            ob_unresolved_total += len(unresolved)
            print(f"  {cat}: obligation coverage {result['coverage_pct']:.0f}% "
                  f"({result['total_covered']}/{result['total_expected']}), "
                  f"{len(result['gaps'])} gaps ({len(unresolved)} unresolved)")

    # 3) H4 SAF heuristic ------------------------------------------------------
    h4 = None
    saf_kris = [k for k in all_kris if k.get("_domain") == "SAF"]
    if saf_kris:
        try:
            h4 = check_h4_ae_collection_window(client, saf_kris, protocol_id)
            print(f"  H4 SAF heuristic: covered={h4.get('h4_covered')} — {h4.get('h4_reason','')[:80]}")
        except Exception as e:
            print(f"  H4 SAF heuristic — ERROR: {e}")

    # Gate decision -----------------------------------------------------------
    pass_gate = (not sec_unresolved) and (ob_unresolved_total == 0) and (not inventory_errors)

    # strip in-memory _pages/_domain helpers from any echoed KRI (none here) and write
    report = {
        "_meta": {"step": "3A", "protocol_id": protocol_id, "blocking": True,
                  "pass_gate": pass_gate,
                  "section_gaps_unresolved": len(sec_unresolved),
                  "obligation_gaps_unresolved": ob_unresolved_total,
                  "inventory_errors": inventory_errors},
        "section_coverage": sec_result,
        "obligation_coverage_by_domain": obligation_by_domain,
        "h4_saf_heuristic": h4,
        "how_to_resolve": ("To clear a gap: add/extend a KRI that covers it, OR re-tag the "
                           "section non_substantive in manifest.json, OR acknowledge it in "
                           "gaps_resolutions.json ({\"sections\":{\"<num>\":{\"acknowledged\":true,"
                           "\"reason\":\"...\"}},\"obligations\":{\"<gap_key>\":{\"acknowledged\":true,"
                           "\"reason\":\"...\"}}}), then re-run --from 3a."),
    }
    out_path = os.path.join(output_dir, "gaps_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n  {'✓ PASS' if pass_gate else '✗ BLOCKED'} — "
          f"{len(sec_unresolved)} section + {ob_unresolved_total} obligation unresolved gaps"
          f"{', ' + str(len(inventory_errors)) + ' inventory errors' if inventory_errors else ''}")
    print(f"  Saved → {out_path}")
    return pass_gate


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 3A — Completeness gate (blocking)")
    parser.add_argument("--dir", required=True, help="Run directory (must contain manifest.json and raw_*.json)")
    args = parser.parse_args()
    ok = run_completeness_check(args.dir, os.path.join(args.dir, "manifest.json"))
    sys.exit(0 if ok else 1)
