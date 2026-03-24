"""
Step 4A — Assembly
Merges raw_SOA.json, raw_ELIG.json, raw_SAF.json, raw_END.json, raw_OPS.json
into a single extracted_kris.json. No LLM required.

Usage:
  python step4a_assemble.py --out /path/to/output/ --manifest /path/to/manifest.json
"""
import json, os, re, argparse

CATEGORY_LABELS = {
    "SOA": "Schedule of Activities",
    "ELIG": "Eligibility",
    "SAF": "Safety & Toxicity",
    "END": "Endpoints & Statistics",
    "OPS": "Operations & Compliance"
}

def assemble(out_dir: str, manifest_path: str) -> str:
    with open(manifest_path) as f:
        manifest = json.load(f)

    all_kris, categories_meta = [], []

    for cat in ["SOA", "ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(out_dir, f"raw_{cat}.json")
        if not os.path.exists(raw_path):
            print(f"  {cat}: not found, skipping")
            continue

        with open(raw_path) as f:
            data = json.load(f)
        kris = data.get("kris", [])

        # Normalize fields, deduplicate by rule_for_llm
        seen, cleaned = set(), []
        for k in kris:
            rule = (k.get("rule_for_llm") or "").strip().lower()
            if rule and rule in seen:
                continue
            if rule:
                seen.add(rule)
            if not k.get("rule_for_llm") and not k.get("kri_name"):
                continue
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
            cleaned.append(entry)

        all_kris.extend(cleaned)
        categories_meta.append({
            "id": cat,
            "label": CATEGORY_LABELS[cat],
            "kri_count": len(cleaned),
            "kri_ids": [k["kri_id"] for k in cleaned]
        })
        print(f"  {cat}: {len(cleaned)} KRIs")

    output = {
        "_meta": {
            "version": "1.0.0",
            "protocol": manifest.get("protocol_id", "UNKNOWN"),
            "sponsor": manifest.get("sponsor", ""),
            "extracted_by": "protocol-kri-extractor",
            "total_kris": len(all_kris),
            "total_categories": len(categories_meta)
        },
        "categories": categories_meta,
        "kris": all_kris
    }

    out_path = os.path.join(out_dir, "extracted_kris.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Total: {len(all_kris)} KRIs → {out_path}")
    return out_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output directory with raw_*.json files")
    parser.add_argument("--manifest", required=True, help="Path to manifest.json")
    args = parser.parse_args()
    assemble(args.out, args.manifest)
