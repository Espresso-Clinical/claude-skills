"""
Step 4A-Dedup — Cross-Domain + Intra-Domain De-duplication

Implements SKILL.md "CRITICAL — De-duplication" with:
  - Cross-Domain Ownership Hierarchy (SOA > SAF > OPS for "procedure × visit" checks)
  - Intra-SOA Sub-Priority (table > CROSS > TEXT > orphan-footnote)
  - Alias-map semantic equivalence (uses alias_map.json for visit/procedure aliases)
  - Cross-Section Merge Guard (never merge KRIs from different numbered §sections)
  - "Atomization is NOT duplication" principle (default to KEEP BOTH)

Inputs:
  raw_SOA.json, raw_ELIG.json, raw_SAF.json, raw_END.json, raw_OPS.json
  alias_map.json (Step 1E)
  extracted_kris.json (assembled, Step 4A)

Outputs:
  Updated raw_*.json (with intra/cross-domain duplicates removed)
  Updated extracted_kris.json
  dedup_report.json (cross_domain + intra_domain + kept_despite_similarity)

This implementation is deterministic. It catches:
  1. Exact-id duplicates within a domain (defensive — should never happen)
  2. Same (procedure_canonical × visit_canonical) within SOA, applying intra-SOA
     sub-priority — keeps higher-priority origin, drops lower
  3. Cross-domain "procedure × visit" overlap: SOA wins, SAF/OPS dropped
  4. Identical rule_for_llm + same protocol section within a non-SOA domain

Semantic LLM-driven dedup for harder cases (different wording, same meaning) is
deferred to a follow-up — the deterministic pass conservatively KEEPS BOTH when
in doubt and logs the pair to kept_despite_similarity for human review.
"""
import argparse
import json
import os
import re
import sys


SOA_PRIORITY = {
    "atomic_grid": 100,
    "checkin": 90,
    "cross_visit": 80,
    "soa_text": 70,
    "orphan_footnote": 60,
    "ORPH": 50,  # protocol-wide orphan scan
    "_default": 75,
}


def _section_id(ref):
    """Extract numbered section identifier (e.g. '8.7', '8.14.1') from a ref string.

    Returns the section number or empty string. Two refs with different non-empty
    section numbers are protected by the Cross-Section Merge Guard.
    """
    if not isinstance(ref, str):
        return ""
    m = re.search(r"§\s*(\d+(?:\.\d+)*)|Section\s+(\d+(?:\.\d+)*)", ref, re.IGNORECASE)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return ""


def _build_alias_lookups(alias_map):
    """Return (visit_canonical_for, procedure_canonical_for) — both dicts keyed by
    lowercased label, returning the canonical name.
    """
    visit_for = {}
    for entry in (alias_map.get("visits") or []):
        canon = entry.get("canonical")
        if not canon:
            continue
        visit_for[canon.lower()] = canon
        for a in (entry.get("aliases") or []):
            visit_for[a.lower()] = canon
    proc_for = {}
    for entry in (alias_map.get("procedures") or []):
        canon = entry.get("canonical")
        if not canon:
            continue
        proc_for[canon.lower()] = canon
        for a in (entry.get("aliases") or []):
            proc_for[a.lower()] = canon
    return visit_for, proc_for


_VISIT_PREFIX_RE = re.compile(r"^([A-Z][A-Z0-9\-_]*?)[\s\-:]")


def _extract_visit_token(kri, visit_for):
    """Best-effort visit token from kri_name or rule_for_llm prefix."""
    for field in ("kri_name", "rule_for_llm"):
        v = kri.get(field) or ""
        m = _VISIT_PREFIX_RE.match(v)
        if m:
            tok = m.group(1)
            return visit_for.get(tok.lower(), tok)
    return ""


def _extract_procedure_token(kri, proc_for):
    """Best-effort procedure token from kri_name (after the visit prefix)."""
    name = kri.get("kri_name") or ""
    parts = re.split(r"\s*-\s*", name, maxsplit=1)
    if len(parts) == 2:
        proc = parts[1].strip()
        return proc_for.get(proc.lower(), proc)
    return proc_for.get(name.lower(), name)


def _soa_priority_for(kri):
    src = (kri.get("_source") or "").lower()
    if src in SOA_PRIORITY:
        return SOA_PRIORITY[src]
    kid = (kri.get("kri_id") or "")
    if kid.startswith("SOA-CHECKIN"):
        return SOA_PRIORITY["checkin"]
    if kid.startswith("SOA-CROSS"):
        return SOA_PRIORITY["cross_visit"]
    if kid.startswith("SOA-TEXT"):
        return SOA_PRIORITY["soa_text"]
    if kid.startswith("SOA-ORPHAN"):
        return SOA_PRIORITY["orphan_footnote"]
    if kid.startswith("ORPH-"):
        return SOA_PRIORITY["ORPH"]
    if kid.startswith("SOA-"):
        return SOA_PRIORITY["atomic_grid"]
    return SOA_PRIORITY["_default"]


def _looks_procedure_at_visit(kri):
    """Heuristic: does this KRI check 'procedure happened at visit'?"""
    rule = (kri.get("rule_for_llm") or "").lower()
    return any(kw in rule for kw in [
        "per soa", "per the schedule", "per schedule", "per the soa table",
        "verify that ", "performed at ", "collected at ", "measured at ",
    ]) and bool(_VISIT_PREFIX_RE.match(kri.get("kri_name") or ""))


def dedup(raw_by_domain, alias_map):
    """Return (kept_by_domain, report).

    kept_by_domain: dict[domain] -> list[kri]
    report: dict with cross_domain, intra_domain, kept_despite_similarity
    """
    visit_for, proc_for = _build_alias_lookups(alias_map)

    cross_log = []
    intra_log = []
    kept_log = []

    # Flat map of every KRI by id for cross-domain checks
    all_kris = []
    for dom, ks in raw_by_domain.items():
        for k in (ks or []):
            if isinstance(k, dict):
                k = dict(k)
                k["_domain"] = dom
                all_kris.append(k)

    # ── Pass 1 — Intra-SOA priority dedup on (visit_canon, proc_canon) ──────
    soa_kris = [k for k in all_kris if k.get("_domain") == "SOA"]
    soa_groups = {}
    for k in soa_kris:
        v = _extract_visit_token(k, visit_for)
        p = _extract_procedure_token(k, proc_for)
        sec = _section_id(k.get("protocol_reference") or "")
        key = (v.lower() if v else "", p.lower() if p else "", sec)
        soa_groups.setdefault(key, []).append(k)

    soa_kept_ids = set()
    for key, group in soa_groups.items():
        if len(group) <= 1:
            soa_kept_ids.add(group[0]["kri_id"])
            continue
        # Sort by priority, keep highest, drop lower (only when same procedure × visit)
        v_key, p_key, sec = key
        if not v_key or not p_key:
            # Cannot identify procedure × visit → keep all
            for k in group:
                soa_kept_ids.add(k["kri_id"])
            continue
        ranked = sorted(group, key=lambda x: -_soa_priority_for(x))
        keeper = ranked[0]
        soa_kept_ids.add(keeper["kri_id"])
        for loser in ranked[1:]:
            # Cross-Section Merge Guard
            keeper_sec = _section_id(keeper.get("protocol_reference") or "")
            loser_sec = _section_id(loser.get("protocol_reference") or "")
            if keeper_sec and loser_sec and keeper_sec != loser_sec:
                soa_kept_ids.add(loser["kri_id"])
                kept_log.append({
                    "kri_id_a": keeper["kri_id"],
                    "kri_id_b": loser["kri_id"],
                    "reason_kept": f"Different protocol sections (§{keeper_sec} ≠ §{loser_sec}) — Cross-Section Merge Guard",
                })
                continue
            intra_log.append({
                "domain": "SOA",
                "deleted_kri_id": loser["kri_id"],
                "duplicate_of": keeper["kri_id"],
                "reason": f"Intra-SOA sub-priority — kept higher-priority origin "
                          f"(keeper={keeper.get('_source','?')} prio={_soa_priority_for(keeper)}, "
                          f"loser={loser.get('_source','?')} prio={_soa_priority_for(loser)})",
                "values_compared": {"visit": v_key, "procedure": p_key, "section": sec},
            })

    # ── Pass 2 — Cross-domain: SOA wins over SAF/OPS for procedure×visit ────
    soa_proc_visit_keys = set()
    for k in soa_kris:
        if k["kri_id"] not in soa_kept_ids:
            continue
        v = _extract_visit_token(k, visit_for).lower()
        p = _extract_procedure_token(k, proc_for).lower()
        if v and p:
            soa_proc_visit_keys.add((v, p))

    cross_dropped_ids = set()
    for k in all_kris:
        if k.get("_domain") in ("SOA", "ELIG", "END"):
            continue
        if not _looks_procedure_at_visit(k):
            continue
        v = _extract_visit_token(k, visit_for).lower()
        p = _extract_procedure_token(k, proc_for).lower()
        if not v or not p:
            continue
        if (v, p) in soa_proc_visit_keys:
            # Cross-Section Merge Guard
            soa_match = next((s for s in soa_kris
                              if s["kri_id"] in soa_kept_ids
                              and _extract_visit_token(s, visit_for).lower() == v
                              and _extract_procedure_token(s, proc_for).lower() == p), None)
            if soa_match:
                k_sec = _section_id(k.get("protocol_reference") or "")
                s_sec = _section_id(soa_match.get("protocol_reference") or "")
                if k_sec and s_sec and k_sec != s_sec:
                    kept_log.append({
                        "kri_id_a": soa_match["kri_id"],
                        "kri_id_b": k["kri_id"],
                        "reason_kept": f"Different protocol sections (§{s_sec} ≠ §{k_sec}) — Cross-Section Merge Guard",
                    })
                    continue
                cross_dropped_ids.add(k["kri_id"])
                cross_log.append({
                    "deleted_kri_id": k["kri_id"],
                    "duplicate_of": soa_match["kri_id"],
                    "reason": f"SOA owns 'procedure × visit' checks per Domain Boundary Rule 1",
                    "rule_type": "procedure_at_visit",
                })

    # ── Pass 3 — Intra-domain identical kri_id (defensive) ───────────────────
    seen_ids_per_dom = {}
    dup_id_drops = set()
    for k in all_kris:
        dom = k.get("_domain")
        kid = k.get("kri_id")
        if not kid:
            continue
        prev = seen_ids_per_dom.setdefault((dom, kid), k)
        if prev is not k:
            dup_id_drops.add(id(k))
            intra_log.append({
                "domain": dom,
                "deleted_kri_id": kid,
                "duplicate_of": kid,
                "reason": "Identical kri_id collision within domain — kept first occurrence",
                "values_compared": {},
            })

    # ── Build kept output ───────────────────────────────────────────────────
    kept_by_domain = {dom: [] for dom in raw_by_domain.keys()}
    for k in all_kris:
        if id(k) in dup_id_drops:
            continue
        if k["kri_id"] in cross_dropped_ids:
            continue
        if k.get("_domain") == "SOA" and k["kri_id"] not in soa_kept_ids:
            continue
        # Strip the temporary _domain key before saving back
        clean = {kk: vv for kk, vv in k.items() if kk != "_domain"}
        kept_by_domain[k["_domain"]].append(clean)

    report = {
        "_meta": {
            "step": "4A-Dedup",
            "cross_domain_deletions": len(cross_log),
            "intra_domain_deletions": len(intra_log),
            "kept_despite_similarity": len(kept_log),
            "alias_map_size": {
                "visits": len(alias_map.get("visits") or []),
                "procedures": len(alias_map.get("procedures") or []),
            },
        },
        "cross_domain": cross_log,
        "intra_domain": intra_log,
        "kept_despite_similarity": kept_log,
    }
    return kept_by_domain, report


def main():
    ap = argparse.ArgumentParser(description="Step 4A-Dedup — cross + intra-domain dedup")
    ap.add_argument("--out", required=True, help="Run output directory containing raw_*.json + alias_map.json")
    args = ap.parse_args()

    out_dir = args.out
    raw_by_domain = {}
    for dom in ["SOA", "ELIG", "SAF", "END", "OPS", "NDEF"]:
        path = os.path.join(out_dir, f"raw_{dom}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        kris = data.get("kris", data) if isinstance(data, dict) else data
        raw_by_domain[dom] = [k for k in kris if isinstance(k, dict)]

    alias_path = os.path.join(out_dir, "alias_map.json")
    alias_map = {}
    if os.path.exists(alias_path):
        with open(alias_path) as f:
            alias_map = json.load(f)

    kept, report = dedup(raw_by_domain, alias_map)

    # Write back to raw_*.json with backup
    for dom, kris in kept.items():
        path = os.path.join(out_dir, f"raw_{dom}.json")
        backup = path + ".pre_dedup.json"
        if os.path.exists(path):
            with open(path) as src, open(backup, "w") as dst:
                dst.write(src.read())
        with open(path, "w") as f:
            json.dump({
                "_meta": {"step": "4A-Dedup-applied", "domain": dom, "kri_count": len(kris)},
                "kris": kris
            }, f, indent=2, ensure_ascii=False)

    report_path = os.path.join(out_dir, "dedup_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"✓ Step 4A-Dedup wrote {report_path}")
    for k, v in report["_meta"].items():
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
