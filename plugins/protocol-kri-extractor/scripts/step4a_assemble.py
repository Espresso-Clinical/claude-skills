"""
Step 4A — Assembly
Merges all validated per-category KRI files into a single cohesive extracted_kris.json.
Pure Python — no LLM. Deduplicates, re-sequences IDs, builds _meta and categories blocks.
Output matches the agreed golden set schema exactly.
"""

import json, sys, os, re
from collections import defaultdict

CATEGORY_LABELS = {
    "SOA":  "Schedule of Activities",
    "ELIG": "Eligibility",
    "SAF":  "Safety & Toxicity",
    "END":  "Endpoints & Statistics",
    "OPS":  "Operations & Compliance"
}

def normalize_id(kri_id: str, cat: str, seq: int) -> str:
    """Keep existing ID if well-formed, otherwise generate clean one."""
    if re.match(r'^[A-Z]+-[A-Z0-9]+-\d{3}$', kri_id):
        return kri_id
    # Regenerate
    # Extract subcategory hint from existing ID
    parts = kri_id.split("-")
    if len(parts) >= 2:
        sub = parts[1] if parts[1].isalpha() else "GEN"
    else:
        sub = "GEN"
    return f"{cat}-{sub}-{seq:03d}"

def deduplicate(kris: list) -> list:
    """Remove exact duplicate rule_for_llm values, keeping first occurrence."""
    seen_rules = set()
    out = []
    for k in kris:
        rule = (k.get("rule_for_llm") or "").strip().lower()
        if rule and rule in seen_rules:
            continue
        if rule:
            seen_rules.add(rule)
        out.append(k)
    return out

def assemble(output_dir: str, manifest_path: str) -> dict:
    with open(manifest_path) as f:
        manifest = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    study_name = manifest.get("study_name", "")
    sponsor = manifest.get("sponsor", "")

    all_kris = []
    categories_meta = []
    cats_in_order = ["SOA", "ELIG", "SAF", "END", "OPS"]

    for cat in cats_in_order:
        raw_path = os.path.join(output_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            print(f"  {cat}: no raw file — skipping")
            continue

        with open(raw_path) as f:
            data = json.load(f)

        kris = data.get("kris", [])

        # Normalize fields
        cleaned = []
        for k in kris:
            entry = {
                "kri_id":              k.get("kri_id", ""),
                "kri_name":            k.get("kri_name", ""),
                "description":         k.get("description", None),
                "category_id":         cat,
                "category_label":      CATEGORY_LABELS[cat],
                "rule_for_llm":        k.get("rule_for_llm", None),
                "protocol_reference":  k.get("protocol_reference", None),
                "additional_footnotes": k.get("additional_footnotes", None)
            }
            # Skip empty/placeholder rows
            if not entry["rule_for_llm"] and not entry["kri_name"]:
                continue
            cleaned.append(entry)

        # Deduplicate
        before = len(cleaned)
        cleaned = deduplicate(cleaned)
        if before != len(cleaned):
            print(f"  {cat}: removed {before - len(cleaned)} duplicates")

        # Re-sequence IDs cleanly within category
        for i, k in enumerate(cleaned, 1):
            k["kri_id"] = normalize_id(k["kri_id"], cat, i)

        all_kris.extend(cleaned)
        kri_ids = [k["kri_id"] for k in cleaned]
        categories_meta.append({
            "id":          cat,
            "label":       CATEGORY_LABELS[cat],
            "kri_count":   len(cleaned),
            "kri_ids":     kri_ids
        })
        print(f"  {cat}: {len(cleaned)} KRIs")

    output = {
        "_meta": {
            "version":        "1.0.0",
            "description":    f"Extracted KRI set for {protocol_id}",
            "protocol":       f"{protocol_id} / {study_name}" if study_name else protocol_id,
            "sponsor":        sponsor,
            "extracted_by":   "protocol-kri-extractor v1",
            "total_kris":     len(all_kris),
            "total_categories": len(categories_meta),
            "schema": {
                "kri_id":              "Stable identifier: CATEGORY-SUBCATEGORY-NNN",
                "kri_name":            "Short display name",
                "description":         "What this KRI monitors",
                "category_id":         "SOA|ELIG|SAF|END|OPS",
                "category_label":      "Full category name",
                "rule_for_llm":        "Actionable CRA verification instruction",
                "protocol_reference":  "Section and page citation with verbatim quote",
                "additional_footnotes": "Applicable footnote text, or null"
            }
        },
        "categories": categories_meta,
        "kris": all_kris
    }

    return output

def run_assembly(output_dir: str, manifest_path: str):
    protocol_id = json.load(open(manifest_path)).get("protocol_id", "UNKNOWN")
    print(f"\nAssembling: {protocol_id}")

    result = assemble(output_dir, manifest_path)

    out_path = os.path.join(output_dir, "extracted_kris.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total = result["_meta"]["total_kris"]
    print(f"\n  Total KRIs: {total}")
    for cat in result["categories"]:
        print(f"    {cat['id']}: {cat['kri_count']}")
    print(f"\n  Saved → {out_path}")
    return out_path

if __name__ == "__main__":
    PROTOCOLS = {
        "ENX-CL-05-002": "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002",
        "B1481038":       "/home/claude/protocol-kri-extractor/output/B1481038",
        "LCZ696G2301":    "/home/claude/protocol-kri-extractor/output/LCZ696G2301"
    }
    target = sys.argv[1] if len(sys.argv) > 1 else "ENX-CL-05-002"
    d = PROTOCOLS[target]
    run_assembly(d, os.path.join(d, "manifest.json"))
