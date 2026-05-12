"""
Step 3C — Internal Consistency Check (cross-KRI, across the 4 in-scope domains)
Clusters extracted KRIs by topic keyword (e.g., LDL-C, ALT, GFR, IP storage
temperature). For each cluster of 2+ KRIs, checks whether values, units,
thresholds, or qualifiers are consistent.

Flags only — does not auto-fix. Human decides.

SOA is OUT OF SCOPE for this skill — handled by `soa-kri-extractor`.
"""

import json, sys, re, os
import pdfplumber
import anthropic

SYSTEM_PROMPT = """You are a clinical trial protocol quality expert.
You check that KRI rules referring to the same clinical concept are internally
consistent across the in-scope ELIG/SAF/END/OPS domains. You always return
valid JSON. No markdown, no prose."""

DOMAINS = ["ELIG", "SAF", "END", "OPS"]

# A small protocol-agnostic seed set of topic keywords. The cluster step is
# intentionally lightweight: it groups KRIs whose `rule_for_llm` mentions the
# same keyword. The LLM consistency check then decides whether the cluster
# actually contains inconsistent values.
TOPIC_KEYWORDS = [
    "LDL-C", "HDL-C", "Apo B", "Lp(a)",
    "ALT", "AST", "bilirubin", "creatinine", "eGFR", "GFR",
    "CK", "troponin", "hs-CRP", "hsCRP", "CRP",
    "HbA1c", "fasting glucose",
    "blood pressure", "BP",
    "IP storage", "IMP storage", "drug storage",
    "AE collection", "SAE reporting",
    "ITT", "mITT", "FAS", "Safety Analysis Set", "Per Protocol",
]


def extract_page_text(pdf_path: str, page_num: int) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if 1 <= page_num <= len(pdf.pages):
            return pdf.pages[page_num - 1].extract_text() or ""
    return ""


def cluster_by_topic(all_kris: list) -> dict:
    """Group KRIs whose `rule_for_llm` (or kri_name) mentions a shared topic keyword."""
    clusters = {}
    for kri in all_kris:
        rule = (kri.get("rule_for_llm") or "") + " " + (kri.get("kri_name") or "")
        rule_lower = rule.lower()
        for kw in TOPIC_KEYWORDS:
            if kw.lower() in rule_lower:
                clusters.setdefault(kw, []).append(kri)
                break  # first matching keyword wins per KRI
    return {kw: kris for kw, kris in clusters.items() if len(kris) >= 2}


def check_cluster_consistency(client, topic: str, kris: list, pdf_path: str) -> dict:
    kri_list = json.dumps([{
        "kri_id": k["kri_id"],
        "kri_name": k.get("kri_name", ""),
        "category_id": k.get("category_id"),
        "rule_for_llm": k.get("rule_for_llm", ""),
        "protocol_reference": k.get("protocol_reference", ""),
    } for k in kris], indent=2)

    pages_to_check = set()
    for k in kris:
        ref = k.get("protocol_reference", "")
        m = re.search(r"[Pp]age\s+(\d+)|p\.\s*(\d+)", ref)
        if m:
            pg = m.group(1) or m.group(2)
            if pg:
                pages_to_check.add(int(pg))

    protocol_context = ""
    if pages_to_check:
        page_texts = []
        for pg in sorted(list(pages_to_check)[:4]):
            text = extract_page_text(pdf_path, pg)
            if text:
                page_texts.append(f"[PAGE {pg}]\n{text[:1500]}")
        protocol_context = "\n\n".join(page_texts)

    prompt = f"""Check internal consistency for the "{topic}" concept across these KRIs.

EXTRACTED KRIs:
{kri_list}

RELEVANT PROTOCOL PAGES:
{protocol_context if protocol_context else "(no page references found)"}

Identify inconsistencies where:
1. The same value, unit, threshold, or qualifier is contradicted across KRIs
   (e.g. different ULN multiples for the same lab; different units; different
   reporting windows; different definitions for the same population label).
2. The same concept is phrased in a way that could confuse a CRA into checking
   different things across different domains.

IMPORTANT: Only flag if the protocol text indicates the values SHOULD match.
Some differences are intentional (e.g. a tighter threshold in a stopping rule
than in eligibility). Mark those as intentional.

Return JSON:
{{
  "cluster": "{topic}",
  "kri_count": {len(kris)},
  "overall_status": "CONSISTENT|HAS_INCONSISTENCIES",
  "inconsistencies": [
    {{
      "description": "what the inconsistency is",
      "affected_kri_ids": ["..."],
      "reference_kri_ids": ["..."],
      "could_be_intentional": true,
      "protocol_quote": "verbatim quote ≤20 words",
      "recommendation": "what affected KRIs should say"
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    result = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return result, tokens


def run_consistency_check(output_dir: str, pdf_path: str):
    client = anthropic.Anthropic()

    all_kris = []
    for dom in DOMAINS:
        path = os.path.join(output_dir, f"raw_{dom}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for k in data.get("kris", []):
            k.setdefault("category_id", dom)
            all_kris.append(k)

    if not all_kris:
        print("  No raw_*.json found — skipping consistency check")
        return

    print(f"\nConsistency check across {len(DOMAINS)} domains ({len(all_kris)} KRIs total)")

    clusters = cluster_by_topic(all_kris)
    print(f"  Topic clusters with 2+ KRIs: {len(clusters)}")
    for kw, kris in sorted(clusters.items(), key=lambda x: -len(x[1]))[:8]:
        print(f"    '{kw}': {len(kris)} KRIs")

    all_results, total_tokens, flagged = [], 0, 0
    for topic, kris in clusters.items():
        try:
            result, tokens = check_cluster_consistency(client, topic, kris, pdf_path)
            total_tokens += tokens
            all_results.append(result)
            real_issues = [
                i for i in result.get("inconsistencies", [])
                if not i.get("could_be_intentional")
            ]
            if real_issues:
                flagged += len(real_issues)
                print(f"\n  ⚠ {topic} ({len(kris)} KRIs):")
                for issue in real_issues:
                    print(f"    - {issue['description'][:80]}")
                    print(f"      Affected: {issue['affected_kri_ids']}")
        except Exception as e:
            print(f"  ERROR checking '{topic}': {e}")

    out_path = os.path.join(output_dir, "consistency_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "step": "3C",
                "clusters_checked": len(all_results),
                "total_inconsistencies_flagged": flagged,
                "tokens_used": total_tokens,
            },
            "clusters": all_results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Clusters checked: {len(all_results)}")
    print(f"  Inconsistencies flagged: {flagged}")
    print(f"  Saved → {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 3C — Consistency check")
    parser.add_argument("--dir", required=True, help="Run directory (must contain raw_*.json)")
    parser.add_argument("--pdf", required=True, help="Path to protocol PDF")
    args = parser.parse_args()

    run_consistency_check(args.dir, args.pdf)
