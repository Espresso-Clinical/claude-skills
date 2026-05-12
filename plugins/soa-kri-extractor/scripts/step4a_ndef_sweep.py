"""
Step 4A-NDEF — Post-Extraction NDEF Sweep (MANDATORY, runs AFTER Step 4A-Dedup)

Reviews every KRI across the 5 real domains (SOA/ELIG/SAF/END/OPS) and moves any
whose rule is not deterministically machine-checkable into NDEF. NDEF is
populated exclusively by this sweep — extractors never produce NDEF entries.

Panel: 3 Claude Sonnet 4 judges + 3 Gemini 2.5 Pro judges = 6 cross-model judges.

Consensus tiers (on NON_DEFINABLE votes out of 6):
  5-6 → T1 auto-move to NDEF
  3-4 → T2 user decision table
  0-2 → keep in source domain

Qualifying criteria for NON_DEFINABLE (binding — see SKILL.md Rule 4):
  - Investigator judgment ("in the opinion of", "if clinically significant")
  - Undefined time windows ("as soon as possible", "in a timely manner")
  - Undefined effort/quantity ("reasonable effort", "adequate")
  - Subjective thresholds
  - Any other wording that cannot produce a deterministic YES/NO on subject data

Usage:
  python step4a_ndef_sweep.py --out /path/to/run_dir/
  python step4a_ndef_sweep.py --out /path/to/run_dir/ --auto-approve-t2   # non-interactive
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini_extract import call_gemini  # noqa: E402


# ─── Constants ──────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
N_CLAUDE_JUDGES = 3
N_GEMINI_JUDGES = 3
N_PANEL = N_CLAUDE_JUDGES + N_GEMINI_JUDGES  # 6
SOURCE_DOMAINS = ["SOA", "ELIG", "SAF", "END", "OPS"]

T1_THRESHOLD = 5  # ≥5 NON_DEFINABLE votes → auto-move
T2_THRESHOLD = 3  # ≥3 NON_DEFINABLE votes → user decision

SYSTEM_PROMPT = (
    "You are a clinical trial protocol auditor deciding whether a KRI's rule can be "
    "verified by a machine unambiguously. You vote DEFINABLE only if the rule produces "
    "a deterministic YES/NO answer on concrete subject data. You vote NON_DEFINABLE if "
    "the rule relies on clinical judgment, vague time windows, undefined effort or "
    "quantity, or any other non-binary wording. You always return valid JSON with no "
    "markdown fences, no prose, no extra text."
)

JUDGE_INSTRUCTION = """You will judge a single KRI's rule_for_llm for machine-verifiability.

Return NON_DEFINABLE if the rule contains ANY of these patterns:
  - Investigator judgment wording: "in the opinion of", "if clinically significant",
    "clinically relevant", "per clinical judgment", "investigator discretion"
  - Undefined time windows: "as soon as possible", "in a timely manner", "promptly",
    "without undue delay", "reasonable time"
  - Undefined effort or quantity: "reasonable effort", "adequate", "sufficient",
    "appropriate", "best effort"
  - Subjective thresholds: qualitative thresholds with no measurable numeric value
  - Any other wording that cannot produce a deterministic YES/NO on subject data

Return DEFINABLE if the rule can be checked against a concrete data field with a
deterministic YES/NO (e.g., specific numeric thresholds, named data fields, concrete
time windows in hours/days/weeks, countable events, binary presence/absence).

KRI to judge:
{kri_json}

Return JSON:
{{"vote": "DEFINABLE"|"NON_DEFINABLE", "reason": "<one sentence, <=25 words, citing the specific wording from rule_for_llm>"}}
"""


# ─── Judge calls ────────────────────────────────────────────────────────────
def _judge_claude(client, kri):
    """One Claude judge pass on one KRI. Returns {vote, reason} or None on error."""
    prompt = JUDGE_INSTRUCTION.format(kri_json=json.dumps({
        "kri_id": kri.get("kri_id"),
        "category_id": kri.get("category_id"),
        "rule_for_llm": kri.get("rule_for_llm", ""),
    }, ensure_ascii=False))
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return _parse_vote(text)
    except Exception as e:
        return {"vote": "ERROR", "reason": f"Claude API error: {e}"}


def _judge_gemini(kri):
    """One Gemini judge pass on one KRI. Returns {vote, reason} or None on error."""
    prompt = JUDGE_INSTRUCTION.format(kri_json=json.dumps({
        "kri_id": kri.get("kri_id"),
        "category_id": kri.get("category_id"),
        "rule_for_llm": kri.get("rule_for_llm", ""),
    }, ensure_ascii=False))
    try:
        text = call_gemini(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.1).strip()
        return _parse_vote(text)
    except Exception as e:
        return {"vote": "ERROR", "reason": f"Gemini API error: {e}"}


def _parse_vote(text):
    """Extract {vote, reason} JSON from a judge response, tolerant of code fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1].lstrip("json").strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    try:
        obj = json.loads(t)
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(t[start:end + 1])
            except Exception:
                return {"vote": "ERROR", "reason": "unparseable response"}
        else:
            return {"vote": "ERROR", "reason": "no JSON object in response"}
    vote = obj.get("vote", "").upper()
    if vote not in ("DEFINABLE", "NON_DEFINABLE"):
        return {"vote": "ERROR", "reason": f"invalid vote '{vote}'"}
    return {"vote": vote, "reason": str(obj.get("reason", ""))[:250]}


def run_panel(kri, claude_client):
    """Run all 6 judges on one KRI. Returns per-judge votes + aggregate."""
    votes = []
    with ThreadPoolExecutor(max_workers=N_PANEL) as ex:
        futures = []
        for i in range(N_CLAUDE_JUDGES):
            futures.append(ex.submit(_judge_claude, claude_client, kri))
        for i in range(N_GEMINI_JUDGES):
            futures.append(ex.submit(_judge_gemini, kri))
        for f in as_completed(futures):
            votes.append(f.result())

    non_def_count = sum(1 for v in votes if v.get("vote") == "NON_DEFINABLE")
    def_count = sum(1 for v in votes if v.get("vote") == "DEFINABLE")
    reasons = [v["reason"] for v in votes if v.get("vote") == "NON_DEFINABLE" and v.get("reason")]

    if non_def_count >= T1_THRESHOLD:
        tier = "T1"
    elif non_def_count >= T2_THRESHOLD:
        tier = "T2"
    else:
        tier = "KEEP"

    return {
        "votes": votes,
        "non_definable_count": non_def_count,
        "definable_count": def_count,
        "tier": tier,
        "top_reason": reasons[0] if reasons else "",
    }


# ─── Classification / movement ──────────────────────────────────────────────
def build_ndef_entry(kri, reason, new_id):
    """Produce the NDEF-classified version of a KRI."""
    entry = dict(kri)  # shallow copy
    entry["original_kri_id"] = kri.get("kri_id")
    entry["original_domain"] = kri.get("category_id")
    entry["kri_id"] = new_id
    entry["category_id"] = "NDEF"
    entry["category_label"] = "Non-Definable"
    entry["rule_for_llm"] = f"NDEF — Non-verifiable: {reason}" if reason else "NDEF — Non-verifiable: rule not deterministically machine-checkable"
    return entry


# ─── I/O helpers ────────────────────────────────────────────────────────────
def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─── Decision-table UX for T2 ───────────────────────────────────────────────
def prompt_user_for_t2(t2_items, auto_approve):
    """Returns a dict {kri_id: True/False} for move-to-NDEF decisions."""
    decisions = {}
    if not t2_items:
        return decisions
    if auto_approve:
        for item in t2_items:
            decisions[item["kri"]["kri_id"]] = True
        return decisions

    print("\n" + "=" * 78)
    print(f"NDEF Sweep — T2 decision table ({len(t2_items)} KRIs)")
    print("=" * 78)
    print(f"{'#':>3} | {'Source':6} | {'KRI ID':18} | {'Votes':7} | Reason")
    print("-" * 78)
    for idx, item in enumerate(t2_items, 1):
        kri = item["kri"]
        panel = item["panel"]
        print(
            f"{idx:>3} | {kri.get('category_id',''):6} | "
            f"{kri.get('kri_id','')[:18]:18} | "
            f"{panel['non_definable_count']}/{N_PANEL}    | "
            f"{panel['top_reason'][:60]}"
        )
        print(f"    rule: {(kri.get('rule_for_llm') or '')[:140]}")
    print("-" * 78)
    print("Enter comma-separated indices to MOVE to NDEF (e.g. 1,3,5), 'all', or 'none':")
    raw = input("> ").strip().lower()
    move_set = set()
    if raw == "all":
        move_set = set(range(1, len(t2_items) + 1))
    elif raw and raw != "none":
        for token in raw.split(","):
            try:
                move_set.add(int(token.strip()))
            except ValueError:
                pass
    for idx, item in enumerate(t2_items, 1):
        decisions[item["kri"]["kri_id"]] = idx in move_set
    return decisions


# ─── Main pipeline ──────────────────────────────────────────────────────────
def run_sweep(out_dir, auto_approve_t2=False):
    extracted_path = os.path.join(out_dir, "extracted_kris.json")
    kris = load_json(extracted_path, default=[])
    if not kris:
        print(f"✗ No KRIs found at {extracted_path}")
        return 1

    # Only judge KRIs currently in one of the 5 real domains.
    # (Any existing NDEF entries — there shouldn't be any at this stage — are left alone.)
    candidates = [k for k in kris if k.get("category_id") in SOURCE_DOMAINS]
    print(f"→ {len(candidates)} KRIs to evaluate across {SOURCE_DOMAINS}")

    claude_client = anthropic.Anthropic()
    panels = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        future_map = {ex.submit(run_panel, k, claude_client): k for k in candidates}
        done = 0
        for f in as_completed(future_map):
            kri = future_map[f]
            panels[kri["kri_id"]] = f.result()
            done += 1
            if done % 25 == 0 or done == len(candidates):
                print(f"  judged {done}/{len(candidates)}")

    # Partition by tier
    t1_items, t2_items, keep_count = [], [], 0
    for kri in candidates:
        panel = panels[kri["kri_id"]]
        entry = {"kri": kri, "panel": panel}
        if panel["tier"] == "T1":
            t1_items.append(entry)
        elif panel["tier"] == "T2":
            t2_items.append(entry)
        else:
            keep_count += 1

    print(f"\nPanel results: T1 auto-move={len(t1_items)}  T2 user-review={len(t2_items)}  KEEP={keep_count}")

    # T2 user decisions
    t2_decisions = prompt_user_for_t2(t2_items, auto_approve_t2)

    # Build final move list
    to_move = []
    for item in t1_items:
        to_move.append(item)
    for item in t2_items:
        if t2_decisions.get(item["kri"]["kri_id"]):
            to_move.append(item)

    if not to_move:
        print("→ No KRIs moved to NDEF.")
        _write_report(out_dir, panels, t2_decisions, [])
        return 0

    # Reclassify moved KRIs and write outputs
    ndef_entries = []
    moved_ids = set()
    for idx, item in enumerate(to_move, 1):
        kri = item["kri"]
        reason = item["panel"]["top_reason"]
        new_id = f"NDEF-{idx:03d}"
        ndef_entries.append(build_ndef_entry(kri, reason, new_id))
        moved_ids.add(kri.get("kri_id"))

    # Rewrite source-domain raw files
    for domain in SOURCE_DOMAINS:
        path = os.path.join(out_dir, f"raw_{domain}.json")
        raw = load_json(path, default=None)
        if raw is None:
            continue
        filtered = [k for k in raw if k.get("kri_id") not in moved_ids]
        if len(filtered) != len(raw):
            save_json(path, filtered)
            print(f"  raw_{domain}.json: {len(raw)} → {len(filtered)} (-{len(raw)-len(filtered)})")

    # Write raw_NDEF.json
    save_json(os.path.join(out_dir, "raw_NDEF.json"), ndef_entries)
    print(f"  raw_NDEF.json: {len(ndef_entries)} KRIs")

    # Rewrite extracted_kris.json with reclassification applied
    updated_kris = []
    ndef_by_orig = {e["original_kri_id"]: e for e in ndef_entries}
    for k in kris:
        if k.get("kri_id") in ndef_by_orig:
            updated_kris.append(ndef_by_orig[k["kri_id"]])
        else:
            updated_kris.append(k)
    save_json(extracted_path, updated_kris)
    print(f"  extracted_kris.json: {len(updated_kris)} KRIs (final classification)")

    _write_report(out_dir, panels, t2_decisions, ndef_entries)
    print("\n✓ NDEF Sweep complete. Re-run Step 4A Excel generation to produce final Excel.")
    return 0


def _write_report(out_dir, panels, t2_decisions, ndef_entries):
    report = {
        "panel_size": N_PANEL,
        "thresholds": {"t1_non_definable": T1_THRESHOLD, "t2_non_definable": T2_THRESHOLD},
        "total_judged": len(panels),
        "moved_to_ndef": len(ndef_entries),
        "per_kri": [
            {
                "kri_id": kid,
                "tier": p["tier"],
                "non_definable_count": p["non_definable_count"],
                "definable_count": p["definable_count"],
                "top_reason": p["top_reason"],
                "votes": p["votes"],
                "user_decision_move": t2_decisions.get(kid),
            }
            for kid, p in panels.items()
        ],
        "ndef_entries": [
            {"original_kri_id": e["original_kri_id"], "original_domain": e["original_domain"], "new_kri_id": e["kri_id"], "reason": e["rule_for_llm"]}
            for e in ndef_entries
        ],
    }
    save_json(os.path.join(out_dir, "ndef_sweep_report.json"), report)


# ─── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Step 4A-NDEF — Post-Extraction NDEF Sweep")
    parser.add_argument("--out", required=True, help="Run output directory (contains extracted_kris.json and raw_{DOMAIN}.json files)")
    parser.add_argument("--auto-approve-t2", action="store_true", help="Auto-approve all T2 candidates (non-interactive mode)")
    args = parser.parse_args()

    if not os.path.isdir(args.out):
        print(f"✗ Not a directory: {args.out}")
        sys.exit(2)

    sys.exit(run_sweep(args.out, auto_approve_t2=args.auto_approve_t2))


if __name__ == "__main__":
    main()
