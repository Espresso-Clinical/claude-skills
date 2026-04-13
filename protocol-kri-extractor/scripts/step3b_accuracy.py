"""
Step 3B — Accuracy Critic
Random sample of 20 KRIs (4 per category). Re-reads their cited protocol pages
and verifies faithfulness: correct thresholds, drug names, timing, data sources.
Flags WRONG / IMPRECISE / CORRECT per KRI.
Triggers targeted re-extraction for WRONG items.
"""

import json, sys, re, os, random
import pdfplumber
import anthropic

SYSTEM_PROMPT = """You are a clinical trial protocol auditor checking accuracy of extracted KRIs.
You compare each KRI against the exact protocol text and rate its faithfulness.
You always return valid JSON. No markdown, no prose."""

def extract_page_text(pdf_path: str, page_num: int) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if 1 <= page_num <= len(pdf.pages):
            return pdf.pages[page_num-1].extract_text() or ""
    return ""

def parse_page_from_ref(protocol_reference: str) -> int | None:
    """Extract page number from protocol_reference field."""
    m = re.search(r'[Pp]age\s+(\d+)', protocol_reference or "")
    return int(m.group(1)) if m else None

def verify_kri_batch(client, kri_batch: list, pdf_path: str) -> list:
    """Verify a batch of KRIs against their source pages."""
    # Gather all unique pages needed
    pages_needed = set()
    for kri in kri_batch:
        pg = parse_page_from_ref(kri.get("protocol_reference", ""))
        if pg:
            pages_needed.add(pg)
            pages_needed.add(pg + 1)  # include next page for context

    page_texts = {}
    for pg in sorted(pages_needed):
        text = extract_page_text(pdf_path, pg)
        if text:
            page_texts[pg] = text

    protocol_context = "\n\n".join(
        f"[PAGE {pg}]\n{text}" for pg, text in sorted(page_texts.items())
    )

    kri_list = json.dumps([{
        "kri_id": k["kri_id"],
        "rule_for_llm": k.get("rule_for_llm", ""),
        "protocol_reference": k.get("protocol_reference", ""),
        "additional_footnotes": k.get("additional_footnotes", "")
    } for k in kri_batch], indent=2)

    prompt = f"""Verify the accuracy of these KRIs against the protocol text provided.

KRIs TO VERIFY:
{kri_list}

PROTOCOL SOURCE PAGES:
{protocol_context}

For each KRI, verify:
1. Is the rule_for_llm faithful to what the protocol actually says?
2. Are all specific values correct (thresholds, drug names, doses, timing windows)?
3. Is the protocol_reference section/page accurate?
4. Are any critical details missing that the protocol specifies?

Rate each KRI:
- CORRECT: faithful, complete, all specifics accurate
- IMPRECISE: right intent but missing a specific detail (e.g. missing CRP from lab list,
  missing 'supine' from vitals, missing 'by checking medication logs')
- WRONG: incorrect threshold, wrong visit scope, misrepresents the protocol requirement

Return a JSON array:
[
  {{
    "kri_id": "...",
    "verdict": "CORRECT|IMPRECISE|WRONG",
    "issue": "specific problem if IMPRECISE or WRONG, null if CORRECT",
    "corrected_rule": "corrected rule_for_llm text if WRONG or IMPRECISE, null if CORRECT",
    "protocol_evidence": "verbatim quote ≤25 words that proves your verdict"
  }}
]"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    results = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return results, tokens

def run_accuracy_check(output_dir: str, pdf_path: str, sample_size: int = 20):
    client = anthropic.Anthropic()

    # Collect all KRIs across categories
    all_kris_by_cat = {}
    for cat in ["SOA", "ELIG", "SAF", "END", "OPS"]:
        raw_path = os.path.join(output_dir, f"raw_{cat}.json")
        if os.path.exists(raw_path):
            with open(raw_path) as f:
                data = json.load(f)
            # Only include KRIs that have a protocol_reference with a page number
            kris_with_ref = [k for k in data.get("kris", [])
                             if parse_page_from_ref(k.get("protocol_reference", ""))]
            all_kris_by_cat[cat] = kris_with_ref

    # Sample 4 per category (or all if fewer)
    per_cat = max(1, sample_size // len(all_kris_by_cat))
    sample = []
    for cat, kris in all_kris_by_cat.items():
        n = min(per_cat, len(kris))
        chosen = random.sample(kris, n) if len(kris) >= n else kris
        sample.extend(chosen)
        print(f"  Sampled {len(chosen)} from {cat}")

    print(f"\n  Total sample: {len(sample)} KRIs")

    # Verify in batches of 5 (to keep context manageable + ensure page text fits)
    all_verdicts = []
    total_tokens = 0
    for i in range(0, len(sample), 5):
        batch = sample[i:i+5]
        print(f"  Verifying batch {i//5 + 1} ({len(batch)} KRIs)...")
        verdicts, tokens = verify_kri_batch(client, batch, pdf_path)
        all_verdicts.extend(verdicts)
        total_tokens += tokens

    # Summarize
    counts = {"CORRECT": 0, "IMPRECISE": 0, "WRONG": 0}
    for v in all_verdicts:
        counts[v.get("verdict", "WRONG")] += 1

    accuracy_pct = counts["CORRECT"] / len(all_verdicts) * 100 if all_verdicts else 0
    print(f"\n  Accuracy: {accuracy_pct:.0f}%")
    print(f"  CORRECT: {counts['CORRECT']}  IMPRECISE: {counts['IMPRECISE']}  WRONG: {counts['WRONG']}")

    wrong_or_imprecise = [v for v in all_verdicts if v.get("verdict") != "CORRECT"]
    if wrong_or_imprecise:
        print(f"\n  Issues found:")
        for v in wrong_or_imprecise:
            print(f"    [{v['verdict']}] {v['kri_id']}: {(v.get('issue') or '')[:80]}")

    # Save report
    out_path = os.path.join(output_dir, "accuracy_report.json")
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "step": "3B",
                "sample_size": len(all_verdicts),
                "accuracy_pct": accuracy_pct,
                "tokens_used": total_tokens,
                "pass": accuracy_pct >= 85
            },
            "summary": counts,
            "verdicts": all_verdicts
        }, f, indent=2)
    print(f"\n  Saved → {out_path}")
    print(f"  Pass threshold: ≥85%  →  {'✓ PASS' if accuracy_pct >= 85 else '✗ FAIL — re-extraction needed'}")
    return accuracy_pct >= 85

if __name__ == "__main__":
    PROTOCOLS = {
        "ENX-CL-05-002": {
            "dir": "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002",
            "pdf": "/mnt/user-data/uploads/ENX-CL-05-002_Clinical_Study_Protocol_v_2_0_Agatha_copy.pdf"
        },
        "B1481038": {
            "dir": "/home/claude/protocol-kri-extractor/output/B1481038",
            "pdf": "/mnt/user-data/uploads/Protocol_B1481038.pdf"
        },
        "LCZ696G2301": {
            "dir": "/home/claude/protocol-kri-extractor/output/LCZ696G2301",
            "pdf": "/mnt/user-data/uploads/Novartis__LCZ696G2301-_Phase_3_study_to_evaluate_the_efficacy_and_safety_of_LCZ696pdf.pdf"
        }
    }
    target = sys.argv[1] if len(sys.argv) > 1 else "ENX-CL-05-002"
    p = PROTOCOLS[target]
    run_accuracy_check(p["dir"], p["pdf"])
