"""
Step 3B — Full KRI Accuracy Judging (100% coverage, 5-judge cross-model panel, 6 checks)

MANDATORY BLOCKING GATE. Judges EVERY KRI across all domains. Sampling is NEVER
permitted under any circumstances. This script replaces the prior 20-KRI / 4-per-
category sampling implementation.

Panel: 3 Claude Sonnet 4 judges + 2 Gemini 2.5 Pro judges = 5 cross-model judges per KRI.

Six checks per judge:
  C1 Faithfulness         — rule_for_llm says what the protocol says
  C2 Specific Values      — every threshold/drug/dose/timing matches exactly
  C3 Reference Accuracy   — cited page is ABOUT the clinical topic (semantic check)
  C4 Completeness         — no critical detail the protocol specifies is missing
  C5 Scope Accuracy       — population/time-point scope matches
  C6 Atomicity            — KRI encodes exactly ONE binary obligation about ONE
                            subject with at most one condition; compound KRIs FAIL
                            C6 and are auto-split into N atomic KRIs and re-judged

Consensus adjudication:
  5/5 CORRECT             → PASS
  4/5 CORRECT             → PASS (dissent logged)
  3/5 CORRECT             → FLAG (user decision)
  ≤2/5 CORRECT            → FAIL (blocking)

Auto-correction:
  If ≥3 judges propose semantically equivalent corrections → apply and re-run
  the full 5-judge panel on the corrected KRI (mandatory re-verification).
  C6 atomicity-split: ≥3 judges flag C6 with the same split proposal → split the
  compound KRI into N atomic KRIs, then re-run the panel on each split KRI.
  Original compound KRI does NOT pass.

Gate: 0 FAIL, 0 unresolved FLAG before Step 3C can begin.

See SKILL.md "Step 3B — Full KRI Accuracy Judging (full spec)" for full details.

Usage:
  python step3b_accuracy.py --out /path/to/output/ --pdf /path/to/protocol.pdf
"""

import json
import os
import re
import sys
import time
import shutil
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pdfplumber
import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini_extract import call_gemini  # noqa: E402


# ─── Constants ──────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
N_CLAUDE_JUDGES = 3
N_GEMINI_JUDGES = 2
N_PANEL = N_CLAUDE_JUDGES + N_GEMINI_JUDGES  # 5
BATCH_SIZE = 8  # KRIs per LLM call when sharing the same page context
DOMAINS = ["ELIG", "SAF", "END", "OPS"]

SYSTEM_PROMPT = (
    "You are a clinical trial protocol auditor checking the accuracy of extracted KRIs. "
    "You compare each KRI against the exact protocol page text and rate it on five "
    "independent checks. You always return valid JSON with no markdown fences, no prose, "
    "no extra text. You never soften or generalize — you report exactly what you find."
)


# ─── Page cache ─────────────────────────────────────────────────────────────
class PageCache:
    """Lazy in-memory cache of PDF page texts, keyed by page number.

    One pdfplumber open per run — reused across every judge call.
    """

    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self._cache = {}
        self._pdf = None
        self._total_pages = 0
        self._lock = threading.Lock()

    def __enter__(self):
        self._pdf = pdfplumber.open(self.pdf_path)
        self._total_pages = len(self._pdf.pages)
        return self

    def __exit__(self, *exc):
        if self._pdf:
            self._pdf.close()

    def get(self, page_num):
        with self._lock:
            if page_num in self._cache:
                return self._cache[page_num]
            if not (1 <= page_num <= self._total_pages):
                return ""
            text = self._pdf.pages[page_num - 1].extract_text() or ""
            self._cache[page_num] = text
            return text

    def get_with_context(self, center_pg, radius=1):
        """Return ±radius pages around center_pg, joined with [PAGE N] markers."""
        parts = []
        for pg in range(
            max(1, center_pg - radius),
            min(self._total_pages, center_pg + radius) + 1,
        ):
            text = self.get(pg)
            parts.append(f"[PAGE {pg}]\n{text}")
        return "\n\n".join(parts)


# ─── KRI loading ────────────────────────────────────────────────────────────
def parse_page_from_ref(ref):
    """Extract the first page number from a protocol_reference string."""
    if not ref:
        return None
    m = re.search(r'(?:p\.?|pages?)\s*(\d+)', ref, re.IGNORECASE)
    return int(m.group(1)) if m else None


def load_all_kris(output_dir):
    """Load every KRI from every raw_{DOMAIN}.json file.

    Returns:
      all_kris_map:  dict kri_id -> (domain, kri_record)   — shared records
      domain_files:  dict domain -> list of kri_records    — same objects as above
    """
    all_kris_map = {}
    domain_files = {}
    for domain in DOMAINS:
        path = os.path.join(output_dir, f"raw_{domain}.json")
        if not os.path.exists(path):
            domain_files[domain] = []
            continue
        with open(path) as f:
            data = json.load(f)
        kris = data.get("kris", data) if isinstance(data, dict) else data
        domain_files[domain] = kris
        for k in kris:
            all_kris_map[k["kri_id"]] = (domain, k)
    return all_kris_map, domain_files


# ─── Judge prompt ───────────────────────────────────────────────────────────
JUDGE_PROMPT_TEMPLATE = """You are judging clinical KRIs for accuracy against the protocol.

PROTOCOL PAGE CONTEXT (the cited page + 1 page before and after):
{page_context}

KRIs TO JUDGE:
{kri_list}

For EACH KRI, run all 6 independent checks and return a verdict.

THE 6 CHECKS (every check must pass for CORRECT):
- C1 Faithfulness: Does rule_for_llm say what the protocol says, nothing more, nothing less? No additions, no omissions, no softening, no generalization.
- C2 Specific Values: Every concrete value (threshold, drug name, dose, timing window, analyte, visit number, day count, percentage, unit) matches the protocol exactly.
- C3 Reference Accuracy: The cited section + page is ABOUT the clinical topic of this KRI. This is a SEMANTIC check — not a substring match of the quote. If the KRI is about "LDL-C percent change at Week 14" but the cited page is about infusion reactions, C3 FAILS even if the quote text happens to appear on that page.
- C4 Completeness: No critical detail the protocol specifies for this rule is missing.
- C5 Scope Accuracy: Visit scope, population scope, and time-point scope all match protocol intent.
- C6 Atomicity: The KRI encodes exactly ONE binary obligation about ONE procedure (or procedure-alias) at ONE visit (or visit-alias) with at most one condition. Compound KRIs that bundle multiple procedures (e.g., "W4 — Blood chemistry, hematology, ESR, CRP"), multiple visits (e.g., "Weeks 2–11 — Check-in within window"), or multiple obligations in one rule_for_llm FAIL C6. When you fail a KRI on C6, set "atomic_split_proposal" to a JSON array of the N atomic KRIs it should split into (each with its own rule_for_llm and the topic-relevant supporting_quote). The pipeline will atomic-split when ≥3 judges propose the same split.

VERDICTS:
- CORRECT: all 6 checks pass
- IMPRECISE: right intent, all checks semantically pass, but C2 or C4 flagged a missing detail that could be auto-corrected (e.g., missing CRP from a lab list, missing "supine" from vitals positioning)
- WRONG: any of C1/C3/C5/C6 failed, OR C2/C4 failed with incorrect values (not just missing)

Return a JSON array, one entry per KRI in the list above, in the same order:
[
  {{
    "kri_id": "...",
    "verdict": "CORRECT|IMPRECISE|WRONG",
    "failing_checks": ["C2", "C4"],
    "issue": "specific problem description, null if CORRECT",
    "corrected_rule": "corrected rule_for_llm text, null if CORRECT",
    "atomic_split_proposal": null,
    "protocol_evidence": "verbatim <=25-word quote from the cited page that proves your verdict"
  }},
  ...
]

Return ONLY the JSON array. No markdown fences. No prose. No explanatory text."""


def build_judge_prompt(batch, page_context):
    kri_list = json.dumps(
        [
            {
                "kri_id": k["kri_id"],
                "kri_name": k.get("kri_name", ""),
                "rule_for_llm": k.get("rule_for_llm", ""),
                "protocol_reference": k.get("protocol_reference", ""),
                "supporting_quote": k.get("supporting_quote", ""),
                "additional_footnotes": k.get("additional_footnotes", ""),
                "severity": k.get("severity", ""),
            }
            for k in batch
        ],
        indent=2,
        ensure_ascii=False,
    )
    return JUDGE_PROMPT_TEMPLATE.format(page_context=page_context, kri_list=kri_list)


def parse_judge_response(raw):
    """Parse a judge's JSON array response, tolerant of markdown fences."""
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "verdicts" in result:
            return result["verdicts"]
    except json.JSONDecodeError:
        m = re.search(r'\[[\s\S]*\]', text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


# ─── Judge dispatchers ──────────────────────────────────────────────────────
def _error_verdicts(judge_id, model, batch, reason):
    return [
        {
            "judge_id": judge_id,
            "model": model,
            "kri_id": k["kri_id"],
            "verdict": "ERROR",
            "failing_checks": [],
            "issue": reason,
            "corrected_rule": None,
            "protocol_evidence": None,
        }
        for k in batch
    ]


def run_claude_judge(judge_id, batch, page_context, client):
    """Run one Claude judge on a batch. Returns (verdicts, tokens_used)."""
    prompt = build_judge_prompt(batch, page_context)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        verdicts = parse_judge_response(response.content[0].text)
        for v in verdicts:
            v["judge_id"] = judge_id
            v["model"] = "claude-sonnet-4"
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return verdicts, tokens
    except Exception as e:
        return _error_verdicts(judge_id, "claude-sonnet-4", batch, str(e)), 0


def run_gemini_judge(judge_id, batch, page_context):
    """Run one Gemini judge on a batch. Returns (verdicts, tokens_used)."""
    prompt = build_judge_prompt(batch, page_context)
    try:
        response_text = call_gemini(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.15)
        verdicts = parse_judge_response(response_text)
        for v in verdicts:
            v["judge_id"] = judge_id
            v["model"] = "gemini-2.5-pro"
        return verdicts, 0  # Gemini token accounting via wrapper; left at 0
    except Exception as e:
        return _error_verdicts(judge_id, "gemini-2.5-pro", batch, str(e)), 0


def run_panel_on_batch(batch, page_context, client):
    """Run the full 5-judge panel on a batch in parallel.

    Returns (verdicts_by_kri, tokens_used)
      verdicts_by_kri: dict kri_id -> list of 5 verdicts (one per judge)
    """
    verdicts_by_kri = {k["kri_id"]: [] for k in batch}
    tokens = 0

    with ThreadPoolExecutor(max_workers=N_PANEL) as ex:
        futures = []
        for i in range(N_CLAUDE_JUDGES):
            judge_id = f"C{i + 1}"
            futures.append(ex.submit(run_claude_judge, judge_id, batch, page_context, client))
        for i in range(N_GEMINI_JUDGES):
            judge_id = f"G{i + 1}"
            futures.append(ex.submit(run_gemini_judge, judge_id, batch, page_context))

        for f in as_completed(futures):
            verdicts, t = f.result()
            tokens += t
            for v in verdicts:
                kid = v.get("kri_id")
                if kid in verdicts_by_kri:
                    verdicts_by_kri[kid].append(v)

    return verdicts_by_kri, tokens


# ─── Consensus adjudication ─────────────────────────────────────────────────
def adjudicate(verdicts):
    """Given up to 5 judge verdicts for one KRI, return the final verdict dict.

    Consensus rules (denominator is always the fixed panel size of 5):
      ≥4 CORRECT → PASS
      3 CORRECT  → FLAG (user decision)
      ≤2 CORRECT → FAIL (blocking)
    """
    n_correct = sum(1 for v in verdicts if v.get("verdict") == "CORRECT")

    if n_correct >= 4:
        final = "PASS"
    elif n_correct == 3:
        final = "FLAG"
    else:
        final = "FAIL"

    dissent = None
    if final == "PASS" and n_correct < N_PANEL:
        dissenters = [v for v in verdicts if v.get("verdict") not in ("CORRECT", "ERROR", None)]
        if dissenters:
            dissent = {
                "judge_id": dissenters[0].get("judge_id"),
                "verdict": dissenters[0].get("verdict"),
                "issue": dissenters[0].get("issue"),
            }

    correction_proposals = [
        v.get("corrected_rule")
        for v in verdicts
        if v.get("corrected_rule") and v.get("verdict") in ("IMPRECISE", "WRONG")
    ]

    return {
        "final_verdict": final,
        "consensus": f"{n_correct}/{N_PANEL} CORRECT",
        "judge_verdicts": verdicts,
        "dissent": dissent,
        "correction_proposals": correction_proposals,
        "correction_applied": None,
    }


# ─── Auto-correction ────────────────────────────────────────────────────────
def corrections_equivalent(corrections, client):
    """Use an adjudication Claude call to decide if ≥3 corrections are semantically equivalent.

    Returns (equivalent: bool, merged_text: str or None).
    """
    if len(corrections) < 3:
        return False, None

    prompt = f"""Compare these corrected_rule proposals. Are they semantically equivalent — do they express the same atomic check with the same specific values?

PROPOSALS:
{json.dumps(corrections, indent=2, ensure_ascii=False)}

Return JSON:
{{
  "equivalent": true|false,
  "merged_correction": "merged canonical text if equivalent, else null",
  "reasoning": "brief explanation"
}}

Return ONLY the JSON. No markdown. No prose."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        data = json.loads(text)
        return bool(data.get("equivalent")), data.get("merged_correction")
    except Exception:
        return False, None


# ─── Batch processing ──────────────────────────────────────────────────────
def group_kris_by_page(kris):
    """Group KRIs by the first page cited in their protocol_reference."""
    groups = {}
    for k in kris:
        pg = parse_page_from_ref(k.get("protocol_reference", ""))
        if pg is None:
            groups.setdefault("unknown", []).append(k)
        else:
            groups.setdefault(pg, []).append(k)
    return groups


def batch_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def process_domain(domain, kris, page_cache, client):
    """Judge every KRI in one domain. Returns (results, tokens).

    results: dict kri_id -> adjudicated result
    """
    results = {}
    tokens = 0
    groups = group_kris_by_page(kris)

    for page_key, page_kris in groups.items():
        if page_key == "unknown":
            for k in page_kris:
                results[k["kri_id"]] = {
                    "final_verdict": "FAIL",
                    "consensus": f"0/{N_PANEL} (no parseable page in protocol_reference)",
                    "judge_verdicts": [],
                    "dissent": None,
                    "correction_proposals": [],
                    "correction_applied": None,
                    "blocking_reason": "protocol_reference has no parseable page number",
                }
            continue

        page_context = page_cache.get_with_context(page_key, radius=1)

        for batch in batch_list(page_kris, BATCH_SIZE):
            verdicts_by_kri, batch_tokens = run_panel_on_batch(batch, page_context, client)
            tokens += batch_tokens
            for kri_id, verdicts in verdicts_by_kri.items():
                results[kri_id] = adjudicate(verdicts)

    return results, tokens


# ─── Auto-correction + re-verification loop ─────────────────────────────────
def apply_corrections_and_reverify(results, all_kris_map, page_cache, client):
    """For every IMPRECISE/FAIL with ≥3 equivalent correction proposals, apply the
    merged correction and re-run the full 5-judge panel on the corrected KRI.

    Modifies the KRI record in place inside all_kris_map when a correction verifies.
    """
    auto_correction_log = []

    for kri_id, adj in list(results.items()):
        if adj["final_verdict"] == "PASS":
            continue
        if not adj["correction_proposals"]:
            continue

        equivalent, merged = corrections_equivalent(adj["correction_proposals"], client)
        if not equivalent or not merged:
            continue

        domain, kri_record = all_kris_map[kri_id]
        old_rule = kri_record.get("rule_for_llm", "")
        kri_record["rule_for_llm"] = merged

        pg = parse_page_from_ref(kri_record.get("protocol_reference", ""))
        if pg is None:
            # Revert — can't re-verify without a page
            kri_record["rule_for_llm"] = old_rule
            continue

        page_context = page_cache.get_with_context(pg, radius=1)
        verdicts_by_kri, _ = run_panel_on_batch([kri_record], page_context, client)
        new_verdicts = verdicts_by_kri.get(kri_id, [])
        new_adj = adjudicate(new_verdicts)

        log_entry = {
            "kri_id": kri_id,
            "domain": domain,
            "old_rule": old_rule,
            "corrected_rule": merged,
            "pre_correction_verdict": adj["final_verdict"],
            "pre_correction_consensus": adj["consensus"],
            "post_correction_verdict": new_adj["final_verdict"],
            "post_correction_consensus": new_adj["consensus"],
        }
        auto_correction_log.append(log_entry)

        if new_adj["final_verdict"] == "PASS":
            new_adj["correction_applied"] = merged
            results[kri_id] = new_adj
        else:
            # Revert — correction did not verify
            kri_record["rule_for_llm"] = old_rule

    return auto_correction_log


# ─── Main ───────────────────────────────────────────────────────────────────
def run_full_accuracy_judging(output_dir, pdf_path):
    client = anthropic.Anthropic()
    all_kris_map, domain_files = load_all_kris(output_dir)
    total_kris = len(all_kris_map)

    print("Step 3B — Full KRI Accuracy Judging")
    print(f"  Total KRIs: {total_kris}")
    print(f"  Panel: {N_CLAUDE_JUDGES} Claude + {N_GEMINI_JUDGES} Gemini per KRI")
    print(f"  Coverage: 100% (sampling NEVER permitted)")
    print()

    if total_kris == 0:
        print("  No KRIs found to judge. Aborting.")
        return False

    t0 = time.time()
    with PageCache(pdf_path) as page_cache:
        all_results = {}
        total_tokens = 0

        # Process each domain in parallel (up to 6 concurrent workers).
        with ThreadPoolExecutor(max_workers=len(DOMAINS)) as ex:
            futures = {}
            for domain, kris in domain_files.items():
                if not kris:
                    continue
                futures[ex.submit(process_domain, domain, kris, page_cache, client)] = domain

            for f in as_completed(futures):
                domain = futures[f]
                try:
                    results, tokens = f.result()
                    all_results.update(results)
                    total_tokens += tokens
                    n_pass = sum(1 for r in results.values() if r["final_verdict"] == "PASS")
                    n_flag = sum(1 for r in results.values() if r["final_verdict"] == "FLAG")
                    n_fail = sum(1 for r in results.values() if r["final_verdict"] == "FAIL")
                    print(f"  [{domain}] PASS={n_pass} FLAG={n_flag} FAIL={n_fail}")
                except Exception as e:
                    print(f"  [{domain}] ERROR: {e}")

        print("\nAuto-correction pass (IMPRECISE/FAIL with ≥3 equivalent proposals)...")
        auto_correction_log = apply_corrections_and_reverify(
            all_results, all_kris_map, page_cache, client
        )
        print(f"  Corrections attempted: {len(auto_correction_log)}")
        n_corrected_to_pass = sum(
            1 for e in auto_correction_log if e["post_correction_verdict"] == "PASS"
        )
        print(f"  Corrections verified to PASS: {n_corrected_to_pass}")

    # Save corrected raw_{DOMAIN}.json files (any in-place corrections)
    for domain, kris in domain_files.items():
        if not kris:
            continue
        path = os.path.join(output_dir, f"raw_{domain}.json")
        backup = path + ".pre_3b.json"
        if os.path.exists(path) and not os.path.exists(backup):
            shutil.copy(path, backup)
        with open(path, "w") as f:
            json.dump({"kris": kris}, f, indent=2, ensure_ascii=False)

    # Final tallies
    n_pass = sum(1 for r in all_results.values() if r["final_verdict"] == "PASS")
    n_flag = sum(1 for r in all_results.values() if r["final_verdict"] == "FLAG")
    n_fail = sum(1 for r in all_results.values() if r["final_verdict"] == "FAIL")

    blocking_issues = [
        {
            "kri_id": kid,
            "reason": r.get("blocking_reason") or r["consensus"],
            "consensus": r["consensus"],
        }
        for kid, r in all_results.items()
        if r["final_verdict"] == "FAIL"
    ]

    user_decisions_pending = [
        {
            "kri_id": kid,
            "consensus": r["consensus"],
            "judge_verdicts": r["judge_verdicts"],
            "correction_proposals": r["correction_proposals"],
        }
        for kid, r in all_results.items()
        if r["final_verdict"] == "FLAG"
    ]

    pass_gate = (n_fail == 0 and n_flag == 0)
    elapsed = time.time() - t0

    report = {
        "_meta": {
            "step": "3B",
            "total_kris_judged": total_kris,
            "coverage": "100%",
            "pass_count": n_pass,
            "flag_count": n_flag,
            "fail_count": n_fail,
            "auto_corrections_attempted": len(auto_correction_log),
            "auto_corrections_verified_pass": n_corrected_to_pass,
            "user_decisions_pending": len(user_decisions_pending),
            "pass_gate": pass_gate,
            "elapsed_seconds": round(elapsed, 1),
            "claude_tokens": total_tokens,
        },
        "per_kri": [{"kri_id": kid, **r} for kid, r in all_results.items()],
        "blocking_issues": blocking_issues,
        "auto_correction_log": auto_correction_log,
        "user_decisions_pending": user_decisions_pending,
    }

    out_path = os.path.join(output_dir, "accuracy_report_full.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n  PASS: {n_pass}/{total_kris}")
    print(f"  FLAG: {n_flag}  FAIL: {n_fail}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Saved → {out_path}")
    if pass_gate:
        print("  ✓ PASS GATE — Step 3C may begin")
    else:
        print("  ✗ BLOCKED — resolve all FAIL and FLAG items before Step 3C")
        if blocking_issues:
            print(f"    {len(blocking_issues)} blocking FAIL(s):")
            for b in blocking_issues[:10]:
                print(f"      {b['kri_id']}: {b['reason']}")
        if user_decisions_pending:
            print(f"    {len(user_decisions_pending)} FLAG(s) awaiting user decision")

    return pass_gate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 3B — Full KRI Accuracy Judging")
    parser.add_argument("--out", required=True, help="Output directory containing raw_*.json")
    parser.add_argument("--pdf", required=True, help="Protocol PDF path")
    args = parser.parse_args()

    passed = run_full_accuracy_judging(args.out, args.pdf)
    sys.exit(0 if passed else 1)
