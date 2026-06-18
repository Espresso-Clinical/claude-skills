"""
cross_domain_router — S5: route cross-domain rules OUT of the SOA golden set.

When the SOA pass surfaces a non-SOA rule (medication restriction, washout,
prior-exposure, or stopping / treatment-discontinuation rule), it is flagged and
handed to its home domain (SAF or ELIG) instead of being kept in SOA — preventing
cross-domain duplicates. The Core extractor (protocol-kri-extractor) ingests the
handoff; this skill only flags + removes.

Conservative by design (no LLM, protocol-agnostic phrasing):
  - Only NON-visit-anchored KRIs are candidates (kri_id SOA-CROSS-* /
    SOA-ORPHAN-FOOTNOTE-*). Per-visit grid and check-in KRIs — including a
    visit-anchored washout like "V1 - Analgesic washout before Day 0 pain
    assessment" — are ALWAYS kept in SOA.
  - Default keep: a candidate is routed only on a clear restriction / washout /
    prior-exposure / stopping signal.

Inputs:  <out_dir>/raw_SOA.json
Outputs: <out_dir>/routed_to_core.json  (routed-out rules + suggested domain + reason)
         <out_dir>/raw_SOA.json         (rewritten with only kept SOA KRIs; .bak backup)
"""
import argparse
import json
import os
import re

# (signal regex, target_domain, kind) — universal restriction phrasing.
ROUTE_SIGNALS = [
    (r"\bwash[\s-]?out\b",                                                "ELIG", "washout"),
    (r"\bprior (?:exposure|treatment|use|therapy|medication)\b",          "ELIG", "prior-exposure"),
    (r"\bpreviously (?:received|treated|exposed)\b",                      "ELIG", "prior-exposure"),
    (r"\b(?:prohibited|not permitted|not allowed|disallowed|forbidden)\b", "SAF",  "restriction"),
    (r"\bmust not (?:be )?(?:use|used|tak|receiv|administer)",            "SAF",  "restriction"),
    (r"\b(?:permanently )?discontinu",                                    "SAF",  "stopping"),
    (r"\bstopping rule\b|\bstop (?:study )?treatment\b",                  "SAF",  "stopping"),
    (r"\bwithhold (?:the )?(?:dose|injection|treatment)\b",               "SAF",  "stopping"),
    (r"\binjection (?:must be |should be )?delay",                        "SAF",  "stopping"),
    (r"\bwithdraw(?:al)? (?:of |the )?(?:subject|patient|participant)\b", "SAF",  "stopping"),
]

# Only non-visit-anchored KRIs are eligible for routing.
CANDIDATE_ID = re.compile(r"^SOA-(?:CROSS|ORPHAN-FOOTNOTE)-", re.IGNORECASE)


def classify_text(text):
    """Return (target_domain, kind, matched_text) if free text matches a cross-domain
    signal, else (None, None, None). Shared by the router and the SOA generator (S6),
    so a cross-domain cross-visit rule is routed out rather than distributed."""
    for pat, domain, kind in ROUTE_SIGNALS:
        m = re.search(pat, text or "", re.IGNORECASE)
        if m:
            return domain, kind, m.group(0)
    return None, None, None


def classify(kri):
    """Return (target_domain, kind, matched_text) if this KRI should be routed OUT
    of SOA, else (None, None, None)."""
    if not CANDIDATE_ID.match(kri.get("kri_id", "")):
        return None, None, None
    blob = " ".join(
        str(kri.get(f, "") or "")
        for f in ("kri_name", "description", "rule_for_llm", "supporting_quote")
    )
    return classify_text(blob)


def route_cross_domain(kris):
    """Split kris into (kept_soa, routed_out). routed_out entries gain
    suggested_domain + route_reason."""
    kept, routed = [], []
    for k in kris:
        domain, kind, matched = classify(k)
        if domain:
            entry = dict(k)
            entry["suggested_domain"] = domain
            entry["route_reason"] = (
                f"{kind} rule surfaced in SOA (matched '{matched}') — belongs in {domain}"
            )
            routed.append(entry)
        else:
            kept.append(k)
    return kept, routed


def run(out_dir):
    path = os.path.join(out_dir, "raw_SOA.json")
    if not os.path.exists(path):
        print("  cross_domain_router: raw_SOA.json not found — skipping")
        return
    with open(path) as f:
        data = json.load(f)
    kris = data.get("kris", data) if isinstance(data, dict) else data
    kept, routed = route_cross_domain(kris)

    # Backup, then rewrite raw_SOA.json with kept-only.
    with open(path + ".bak", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if isinstance(data, dict):
        data["kris"] = kept
        out_data = data
    else:
        out_data = kept
    with open(path, "w") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "routed_to_core.json"), "w") as f:
        json.dump({"routed_out": routed, "count": len(routed)}, f, indent=2, ensure_ascii=False)

    by_dom = {}
    for r in routed:
        by_dom[r["suggested_domain"]] = by_dom.get(r["suggested_domain"], 0) + 1
    summary = ", ".join(f"{d}:{n}" for d, n in sorted(by_dom.items())) or "none"
    print(f"  cross_domain_router: kept {len(kept)} SOA, routed {len(routed)} out "
          f"({summary}) → routed_to_core.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="S5 — route cross-domain rules out of SOA")
    ap.add_argument("--out", required=True, help="Run directory (contains raw_SOA.json)")
    run(ap.parse_args().out)
