"""
Step 4A-Dedup — Cross-Domain + Intra-Domain De-duplication for the 4 in-scope
domains (ELIG, SAF, END, OPS).

Schedule of Activities (SOA) is OUT OF SCOPE for this skill (handled by
`soa-kri-extractor`). This script's Pass 0 is the LAST-LINE safety net for the
prompt-level SOA-exclusion methodology: any KRI whose rule is essentially
"procedure happened at visit Y", "visit X within ±N days", "per the SoA table",
etc. is dropped here with reason `out_of_scope_soa`.

Implements SKILL.md "CRITICAL — De-duplication":
  - Pass 0  — SOA-flavored safety net (MANDATORY first pass)
  - Pass 1  — Identical kri_id collisions within a domain (defensive)
  - Pass 2  — Cross-domain dedup between ELIG/SAF/END/OPS per ownership hierarchy
  - Pass 3  — Intra-domain semantic dedup (same protocol_reference + same rule)
  - Cross-Section Merge Guard — different numbered §sections NEVER merged
  - "Atomization is NOT duplication" — default to KEEP BOTH

Inputs:
  raw_ELIG.json, raw_SAF.json, raw_END.json, raw_OPS.json

Outputs:
  Updated raw_*.json (with duplicates removed)
  dedup_report.json with `cross_domain`, `intra_domain`, `kept_despite_similarity` sections
"""
import argparse
import json
import os
import re
import sys

from scope_signature import scope_conflict  # Fix #6 — never merge different-scope KRIs


DOMAINS = ["ELIG", "SAF", "END", "OPS"]


# Cross-domain ownership hierarchy (higher = wins, lower = deleted on a true
# duplicate). Used in Pass 2.
OWNERSHIP_PRIORITY = {
    "SAF":  100,  # safety thresholds, AE/SAE reporting, stopping rules
    "OPS":   90,  # measurement technique, operational procedures
    "END":   80,  # endpoint definitions, governance rules
    "ELIG":  70,  # eligibility criteria
}


# Patterns that signal a SOA-flavored rule. These are scanned in Pass 0 (last-
# line safety net for the extractor-prompt-level exclusion). Order matters
# only slightly — we OR them together. Keep the list conservative so we don't
# false-positive on legitimate SAF/OPS rules that happen to mention a visit.
SOA_FLAG_PATTERNS = [
    r"\bper\s+SOA\b",
    r"\bper\s+the\s+schedule\b",
    r"\bper\s+the\s+SoA\b",
    r"\bschedule\s+of\s+activities\b",
    r"\bvisit\s+window\b",
    r"\bwithin\s+±\s*\d+\s*days\b",
    r"\bwithin\s+\+/-\s*\d+\s*days\b",
    r"\bcheck[-\s]?in\s+visit\b",
    r"\bperformed\s+at\s+(?:visit\s+)?[SVD]\d",
    r"\bcollected\s+at\s+(?:visit\s+)?[SVD]\d",
    r"\bmeasured\s+at\s+(?:visit\s+)?[SVD]\d",
]
SOA_FLAG_RE = re.compile("|".join(SOA_FLAG_PATTERNS), re.IGNORECASE)


def _section_id(ref):
    """Extract numbered section identifier (e.g. '8.7', '8.14.1') from a ref string.
    Two refs with different non-empty section numbers are protected by the
    Cross-Section Merge Guard.
    """
    if not isinstance(ref, str):
        return ""
    m = re.search(r"§\s*(\d+(?:\.\d+)*)|Section\s+(\d+(?:\.\d+)*)", ref, re.IGNORECASE)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return ""


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_soa_flavored(kri):
    """Pass 0 detector: is this KRI essentially a SOA-flavored rule?"""
    rule = kri.get("rule_for_llm") or ""
    name = kri.get("kri_name") or ""
    haystack = f"{name} || {rule}"
    return bool(SOA_FLAG_RE.search(haystack))


def dedup(raw_by_domain):
    """Return (kept_by_domain, report)."""
    cross_log = []
    intra_log = []
    kept_log = []

    # Flat map of every KRI, tagged with its domain
    all_kris = []
    for dom, ks in raw_by_domain.items():
        for k in (ks or []):
            if isinstance(k, dict):
                k = dict(k)
                k["_domain"] = dom
                all_kris.append(k)

    # ── Pass 0 — SOA-flavored safety net (MANDATORY first) ──────────────────
    soa_dropped_ids = set()
    for k in all_kris:
        if _is_soa_flavored(k):
            soa_dropped_ids.add(id(k))
            cross_log.append({
                "deleted_kri_id": k.get("kri_id"),
                "deleted_from_domain": k.get("_domain"),
                "duplicate_of": None,
                "reason": "SOA-flavored — handled by soa-kri-extractor",
                "rule_type": "out_of_scope_soa",
                "rule_preview": (k.get("rule_for_llm") or "")[:120],
            })

    # ── Pass 1 — Identical kri_id collisions within a domain ────────────────
    seen_ids_per_dom = {}
    dup_id_drops = set()
    for k in all_kris:
        if id(k) in soa_dropped_ids:
            continue
        kid = k.get("kri_id")
        dom = k.get("_domain")
        if not kid:
            continue
        key = (dom, kid)
        prev = seen_ids_per_dom.setdefault(key, k)
        if prev is not k:
            dup_id_drops.add(id(k))
            intra_log.append({
                "domain": dom,
                "deleted_kri_id": kid,
                "duplicate_of": kid,
                "reason": "Identical kri_id collision within domain — kept first occurrence",
                "values_compared": {},
            })

    # ── Pass 2 — Cross-domain dedup on (normalized rule, section) ───────────
    cross_dropped_ids = set()
    grouped = {}
    for k in all_kris:
        if id(k) in soa_dropped_ids or id(k) in dup_id_drops:
            continue
        rule = _normalize(k.get("rule_for_llm", ""))
        sec = _section_id(k.get("protocol_reference") or "")
        if not rule:
            continue
        grouped.setdefault((rule, sec), []).append(k)

    for (rule, sec), group in grouped.items():
        if len(group) <= 1:
            continue
        # Multi-KRI cluster sharing rule + section. Are they cross-domain?
        domains_present = set(kk["_domain"] for kk in group)
        if len(domains_present) == 1:
            continue  # intra-domain — handled by Pass 3
        ranked = sorted(group, key=lambda x: -OWNERSHIP_PRIORITY.get(x["_domain"], 0))
        keeper = ranked[0]
        for loser in ranked[1:]:
            # Cross-Section Merge Guard (sec already matches inside this group;
            # this is a defensive check for safety).
            keeper_sec = _section_id(keeper.get("protocol_reference") or "")
            loser_sec = _section_id(loser.get("protocol_reference") or "")
            if keeper_sec and loser_sec and keeper_sec != loser_sec:
                kept_log.append({
                    "kri_id_a": keeper["kri_id"],
                    "kri_id_b": loser["kri_id"],
                    "reason_kept": (
                        f"Different protocol sections (§{keeper_sec} ≠ "
                        f"§{loser_sec}) — Cross-Section Merge Guard"
                    ),
                })
                continue
            # Scope Merge Guard (Fix #6) — never merge two KRIs that assert
            # different time-scopes (prior vs during) or study phases. These are
            # atomization splits, not duplicates. (No-op while grouping is by
            # identical rule text; protective if the dedup key ever loosens.)
            if scope_conflict(keeper.get("rule_for_llm") or "", loser.get("rule_for_llm") or ""):
                kept_log.append({
                    "kri_id_a": keeper["kri_id"],
                    "kri_id_b": loser["kri_id"],
                    "reason_kept": "Different scope (time-scope/phase) — atomization split, not a duplicate (Fix #6)",
                })
                continue
            cross_dropped_ids.add(id(loser))
            cross_log.append({
                "deleted_kri_id": loser["kri_id"],
                "deleted_from_domain": loser["_domain"],
                "duplicate_of": keeper["kri_id"],
                "keeper_domain": keeper["_domain"],
                "reason": (
                    f"Cross-domain duplicate — kept higher-priority domain "
                    f"({keeper['_domain']}) over {loser['_domain']}"
                ),
                "rule_type": "cross_domain",
            })

    # ── Pass 3 — Intra-domain semantic dedup (same rule + same section) ─────
    intra_dropped_ids = set()
    for (rule, sec), group in grouped.items():
        domains_present = set(kk["_domain"] for kk in group)
        if len(domains_present) != 1:
            continue  # already handled cross-domain in Pass 2
        # Filter out already-dropped ones
        live = [kk for kk in group if id(kk) not in cross_dropped_ids]
        if len(live) <= 1:
            continue
        # Keep the KRI with the richer description; drop the rest
        ranked = sorted(
            live,
            key=lambda x: -len((x.get("description") or "") + (x.get("rule_for_llm") or "")),
        )
        keeper = ranked[0]
        for loser in ranked[1:]:
            # Scope Merge Guard (Fix #6) — keep both if scopes differ.
            if scope_conflict(keeper.get("rule_for_llm") or "", loser.get("rule_for_llm") or ""):
                kept_log.append({
                    "kri_id_a": keeper["kri_id"],
                    "kri_id_b": loser["kri_id"],
                    "reason_kept": "Different scope (time-scope/phase) — atomization split, not a duplicate (Fix #6)",
                })
                continue
            intra_dropped_ids.add(id(loser))
            intra_log.append({
                "domain": loser["_domain"],
                "deleted_kri_id": loser["kri_id"],
                "duplicate_of": keeper["kri_id"],
                "reason": "Intra-domain semantic duplicate (same rule + same section); kept richer description",
                "values_compared": {"section": sec},
            })

    # ── Build kept output ───────────────────────────────────────────────────
    kept_by_domain = {dom: [] for dom in raw_by_domain.keys()}
    for k in all_kris:
        if id(k) in soa_dropped_ids:
            continue
        if id(k) in dup_id_drops:
            continue
        if id(k) in cross_dropped_ids:
            continue
        if id(k) in intra_dropped_ids:
            continue
        clean = {kk: vv for kk, vv in k.items() if kk != "_domain"}
        kept_by_domain.setdefault(k["_domain"], []).append(clean)

    out_of_scope_soa_count = sum(
        1 for c in cross_log if c.get("rule_type") == "out_of_scope_soa"
    )

    report = {
        "_meta": {
            "step": "4A-Dedup",
            "out_of_scope_soa_deletions": out_of_scope_soa_count,
            "cross_domain_deletions": len(cross_log) - out_of_scope_soa_count,
            "intra_domain_deletions": len(intra_log),
            "kept_despite_similarity": len(kept_log),
        },
        "cross_domain": cross_log,
        "intra_domain": intra_log,
        "kept_despite_similarity": kept_log,
    }
    return kept_by_domain, report


def main():
    ap = argparse.ArgumentParser(description="Step 4A-Dedup — cross + intra-domain dedup (ELIG/SAF/END/OPS)")
    ap.add_argument("--out", required=True, help="Run output directory containing raw_*.json")
    args = ap.parse_args()

    out_dir = args.out
    raw_by_domain = {}
    for dom in DOMAINS:
        path = os.path.join(out_dir, f"raw_{dom}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        kris = data.get("kris", data) if isinstance(data, dict) else data
        raw_by_domain[dom] = [k for k in kris if isinstance(k, dict)]

    kept, report = dedup(raw_by_domain)

    # Write back to raw_*.json with a one-shot backup per file
    for dom, kris in kept.items():
        path = os.path.join(out_dir, f"raw_{dom}.json")
        backup = path + ".pre_dedup.json"
        if os.path.exists(path) and not os.path.exists(backup):
            with open(path) as src, open(backup, "w") as dst:
                dst.write(src.read())
        with open(path, "w") as f:
            json.dump({
                "_meta": {"step": "4A-Dedup-applied", "domain": dom, "kri_count": len(kris)},
                "kris": kris,
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
