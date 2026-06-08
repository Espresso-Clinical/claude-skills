"""
Step 2.6 — Auto-judgment for T2 + T3-promoted KRIs (per domain)

Replaces the manual Phase-2 decision-table gate with an automated 4-layer
pre-decision. Enables overnight runs: `--auto-approve-unanimous` (default ON)
lets the pipeline complete without blocking; flagged items default to REJECTED
and surface at end-of-run in the cross-domain flagged-review table for user
re-inclusion (see step4a_flagged_review.py).

DISTINCTION from other judging steps in the skill:
  - Step 2.6 decides INCLUSION in the Golden Set. Runs per-domain during
    Phase 2 on T2 + T3-promoted candidates only.
  - Step 3B decides CORRECTNESS of every KRI after assembly (100% coverage,
    5-judge panel). Runs in Phase 3.
  - Step 3.5 orphan scan discovers MISSED rules (6-agent panel). Runs in Phase 3.
Each panel has its own distinct purpose, distinct timing, and distinct artifact.
Step 2.6 does NOT replace any of the above; it only handles the Phase-2
inclusion decision that the user previously did manually.

Four layers per candidate:
  Layer 1   — Verification gate (deterministic: verbatim anchor + binary
              rule + reference sanity)
  Layer 1.5 — Atomicity check (deterministic: precondition-based refinement
              from SKILL.md "Atomization of compound clauses")
  Layer 2   — Coverage/dedup check (deterministic: already covered by T1?)
  Layer 3   — 6-judge neutral panel (3 Claude + 3 Gemini, same CRA-framed
              prompt, consistent with the 10-agent extraction panel's framing)
  Layer 4   — Aggregate decision (auto_approve / auto_reject / flag)

Tier 3 pipeline integration (called from run.py step 2.6 runner):
  T3-1 Coverage Filter (deterministic) → handled inside Layer 2
  T3-2 Verbatim verification            → handled inside Layer 1
  T3-2.5 Atomicity check (NEW)           → handled inside Layer 1.5
  T3-3 Panel                             → Layer 3
  T3-4 Aggregate                         → Layer 4

Artifacts produced per domain:
  {domain}_autojudgment_report.json  — all layer-by-layer results (full audit)
  {domain}_manual_review_decisions.json — sectioned decision table:
      sections.auto_approved    — KRIs the panel accepted
      sections.flagged_for_review — KRIs the panel could not decide (DEFAULT:
          REJECTED at Phase-4; surface in end-of-run flagged-review table)
      sections.auto_rejected    — KRIs the panel rejected
  {domain}_tier3_filtered.json — extended schema recording T3 dispositions
      including Layer-1.5 atomicity rejections

Usage:
  python step2_6_autojudgment.py --out /path/to/run_dir/ --domain ELIG \\
    [--pdf /path/to/protocol.pdf] [--auto-approve-unanimous|--interactive]
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini_extract import call_gemini  # noqa: E402
from autojudgment_prompts import (  # noqa: E402
    JUDGE_PROMPT,
    N_CLAUDE_JUDGES,
    N_GEMINI_JUDGES,
    N_PANEL_TOTAL,
    L4_AUTO_APPROVE_ACCEPT_MIN,
    L4_AUTO_APPROVE_REJECT_MAX,
    L4_AUTO_REJECT_REJECT_MIN,
    L4_AUTO_REJECT_ACCEPT_MAX,
)


CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Tier thresholds (out of 10) — MUST match SKILL.md canonical values
TIER_T1_MIN = 7   # 7–10 agents → auto-approved, skip Step 2.6
TIER_T2_MIN = 4   # 4–6 agents → judged by Step 2.6
TIER_T3_MAX = 3   # 1–3 agents → T3 pipeline + Step 2.6


# ─── Layer 1 — Verification gate (deterministic) ────────────────────────────
def _normalize(s):
    if not s:
        return ""
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def layer1_verification_gate(kri, pdf_page_cache):
    """Verbatim anchor + binary rule + reference sanity."""
    quote = (kri.get("supporting_quote") or "").strip()
    rule = (kri.get("rule_for_llm") or "").strip()
    ref = (kri.get("protocol_reference") or "").strip()

    if len(rule) < 8:
        return {"pass": False, "reason": "rule_for_llm empty or trivial"}

    # NOTE (Fix #5): no "binary/verifiable" reject here. Per Quality Rule 15 this
    # skill does NOT filter non-binary / definitional / conditional / investigator-
    # or-sponsor-decision rules — that filtering happens downstream (the distiller /
    # the user). Only genuine quality failures (empty rule, fabricated quote, bad
    # reference) reject at this gate.

    if len(quote) < 5:
        return {"pass": False, "reason": "supporting_quote empty or trivial"}

    m = re.search(r"p\.?\s*(\d+)", ref)
    if not m:
        return {"pass": False, "reason": "protocol_reference has no parseable page"}
    page = int(m.group(1))

    if pdf_page_cache is not None:
        page_text = pdf_page_cache.get(page)
        if page_text is None:
            return {"pass": True, "reason": "verbatim check deferred to Step 3D (page not cached)"}
        if _normalize(quote) not in _normalize(page_text):
            return {"pass": False, "reason": f"supporting_quote not verbatim on p.{page}"}

    return {"pass": True, "reason": "Layer 1 verification gate passed"}


# ─── Layer 1.5 — Atomicity check (deterministic) ────────────────────────────
def layer1_5_atomicity(kri):
    """Apply atomization-of-compound-clauses preconditions deterministically.

    Rejects KRIs that are:
      - always-true clauses ("Males or females", "Male or female subjects")
      - illustrative-example splits (`description` includes "such as" and the
        rule tokenized out one example — hard to detect deterministically,
        so we only flag the most obvious cases)
      - single-field numeric range splits ("age >= 18" paired with "age < 85"
        detected via kri_id / kri_name similarity across the candidate set —
        out of scope for a per-KRI check; we catch the obvious always-true
        and subjective-threshold cases only)

    Returns {"pass": bool, "reason": str}.
    """
    rule = (kri.get("rule_for_llm") or "").strip().lower()
    name = (kri.get("kri_name") or "").strip().lower()

    # Always-true sex/gender tautology — the one genuinely-empty case we still
    # reject (SKILL.md atomicity example "Males or females"). Tightened (Fix #5):
    # only fires when the rule is ESSENTIALLY ONLY the sex clause (short, no age or
    # other clinical content), so a real criterion that merely mentions sex is
    # never dropped.
    sex_patterns = [
        r"\b(male|females?)\s+or\s+(males?|female)\b",
        r"\bsubject is male or female\b",
    ]
    if len(rule) < 60 and "age" not in rule:
        for p in sex_patterns:
            if re.search(p, rule):
                return {"pass": False, "reason": "always-true clause — sex/gender is universal, not a verifiable check"}

    # NOTE (Fix #5): the "pure definition" auto-reject is REMOVED. Per Quality
    # Rule 14, definitional rules ("X is defined as ...", "X does not include ...")
    # ARE valid KRIs — a site can deviate by applying the wrong definition. They
    # are kept here; the user / downstream distiller decides whether to drop them.

    # Subjective qualifiers with no measurable threshold — pass through; this
    # skill does not classify non-binary KRIs (filtering happens downstream).
    subjective = ["as appropriate", "as needed", "as required", "if clinically appropriate"]
    for s in subjective:
        if s in rule and not re.search(r"\d", rule):
            return {"pass": True, "reason": "subjective wording — kept as-is; downstream filter handles non-binary rules"}

    return {"pass": True, "reason": "Layer 1.5 atomicity check passed"}


# ─── Layer 2 — Coverage/dedup check (deterministic) ─────────────────────────
def layer2_coverage_check(kri, tier1_kris):
    """Check if this candidate is already covered by an approved T1 KRI."""
    candidate_rule = _normalize(kri.get("rule_for_llm", ""))
    if not candidate_rule:
        return {"pass": True, "reason": "no rule to match", "covering_kri_id": None}

    for t1 in tier1_kris:
        t1_rule = _normalize(t1.get("rule_for_llm", ""))
        if not t1_rule:
            continue
        if candidate_rule == t1_rule or candidate_rule in t1_rule or t1_rule in candidate_rule:
            return {
                "pass": False,
                "reason": f"covered by {t1.get('kri_id', '?')}",
                "covering_kri_id": t1.get("kri_id"),
            }

    return {"pass": True, "reason": "no T1 coverage", "covering_kri_id": None}


# ─── Layer 3 — 6-judge neutral panel ────────────────────────────────────────
def _judge_claude(client, kri):
    prompt = _build_judge_user_prompt(kri)
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=JUDGE_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return _parse_vote(text, "claude")
    except Exception as e:
        return {"model": "claude", "vote": "error", "reason": str(e)[:200]}


def _judge_gemini(kri):
    prompt = _build_judge_user_prompt(kri)
    try:
        text = call_gemini(prompt, system_prompt=JUDGE_PROMPT, temperature=0.1, task="judge").strip()
        return _parse_vote(text, "gemini")
    except Exception as e:
        return {"model": "gemini", "vote": "error", "reason": str(e)[:200]}


def _build_judge_user_prompt(kri):
    return "KRI to judge:\n" + json.dumps(
        {
            "kri_id": kri.get("kri_id"),
            "category_id": kri.get("category_id"),
            "kri_name": kri.get("kri_name"),
            "description": (kri.get("description") or "")[:300],
            "rule_for_llm": kri.get("rule_for_llm", ""),
            "protocol_reference": kri.get("protocol_reference"),
            "supporting_quote": kri.get("supporting_quote"),
        },
        ensure_ascii=False,
    )


def _parse_vote(raw, model):
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1].lstrip("json").strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    try:
        obj = json.loads(t)
    except Exception:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                obj = json.loads(t[s:e + 1])
            except Exception:
                return {"model": model, "vote": "error", "reason": "unparseable"}
        else:
            return {"model": model, "vote": "error", "reason": "no JSON"}

    vote = (obj.get("vote") or "").lower()
    if vote not in ("accept", "reject", "conditional"):
        return {"model": model, "vote": "error", "reason": f"invalid vote '{vote}'"}
    return {"model": model, "vote": vote, "reason": str(obj.get("reason", ""))[:250]}


def layer3_panel(kri, claude_client):
    """Run 6 judges (3 Claude + 3 Gemini) in parallel."""
    votes = []
    with ThreadPoolExecutor(max_workers=N_PANEL_TOTAL) as ex:
        futures = []
        for _ in range(N_CLAUDE_JUDGES):
            futures.append(ex.submit(_judge_claude, claude_client, kri))
        for _ in range(N_GEMINI_JUDGES):
            futures.append(ex.submit(_judge_gemini, kri))
        for f in as_completed(futures):
            votes.append(f.result())
    return votes


# ─── Layer 4 — Aggregate decision ───────────────────────────────────────────
def layer4_aggregate(votes):
    accept_ct = sum(1 for v in votes if v.get("vote") == "accept")
    reject_ct = sum(1 for v in votes if v.get("vote") == "reject")
    cond_ct = sum(1 for v in votes if v.get("vote") == "conditional")
    error_ct = sum(1 for v in votes if v.get("vote") == "error")

    summary = f"{accept_ct}A/{reject_ct}R/{cond_ct}C/{error_ct}E"

    if accept_ct >= L4_AUTO_APPROVE_ACCEPT_MIN and reject_ct <= L4_AUTO_APPROVE_REJECT_MAX:
        return {"action": "auto_approve",
                "reason": f"panel unanimous accept ({summary})",
                "summary": summary}

    if reject_ct >= L4_AUTO_REJECT_REJECT_MIN and accept_ct <= L4_AUTO_REJECT_ACCEPT_MAX:
        return {"action": "auto_reject",
                "reason": f"panel unanimous reject ({summary})",
                "summary": summary}

    return {"action": "flag",
            "reason": f"panel split — no unanimous decision ({summary})",
            "summary": summary}


# ─── Tier classification ────────────────────────────────────────────────────
def classify_tier(agent_count):
    if agent_count >= TIER_T1_MIN:
        return "T1"
    if agent_count >= TIER_T2_MIN:
        return "T2"
    return "T3"


# ─── PDF page cache for Layer 1 verbatim check ──────────────────────────────
def _build_pdf_cache(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        return None
    cache = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                cache[i] = page.extract_text() or ""
            except Exception:
                cache[i] = ""
    return cache


# ─── Main orchestrator ──────────────────────────────────────────────────────
def run_autojudgment_for_domain(out_dir, domain, pdf_path=None,
                                auto_approve_unanimous=True):
    raw_path = os.path.join(out_dir, f"raw_{domain}.json")
    if not os.path.isfile(raw_path):
        print(f"✗ raw_{domain}.json not found at {raw_path}")
        return False

    with open(raw_path, encoding="utf-8") as f:
        loaded = json.load(f)

    # Accept both schemas: a flat list of KRI dicts (legacy) and the wrapped
    # {"_meta": {...}, "kris": [...]} format produced by step2_extract.py.
    if isinstance(loaded, dict) and "kris" in loaded:
        all_kris = loaded["kris"]
    elif isinstance(loaded, list):
        all_kris = loaded
    else:
        print(f"✗ raw_{domain}.json has unexpected shape (type={type(loaded).__name__}); skipping.")
        return False

    # Drop any non-dict entries defensively (e.g., stray strings from a bad merge).
    all_kris = [k for k in all_kris if isinstance(k, dict)]

    # Partition by extraction-panel vote count
    t1, t2, t3 = [], [], []
    for k in all_kris:
        n = int(k.get("agent_count", 1))
        tier = classify_tier(n)
        k["_tier"] = tier
        k["_agent_count"] = n
        if tier == "T1":
            t1.append(k)
        elif tier == "T2":
            t2.append(k)
        else:
            t3.append(k)

    print(f"Step 2.6 — Auto-judgment for {domain}")
    print(f"  T1 (auto-keep):       {len(t1)}")
    print(f"  T2 (judged):          {len(t2)}")
    print(f"  T3 (promoted+judged): {len(t3)}")

    pdf_cache = _build_pdf_cache(pdf_path) if pdf_path and os.path.isfile(pdf_path) else None

    candidates = t2 + t3
    claude_client = anthropic.Anthropic()

    per_kri_results = []
    approved_kris = list(t1)   # T1 → auto-keep
    rejected_kris = []          # failed any deterministic layer OR panel-rejected OR flagged (default reject)
    flagged_kris = []           # panel split — defaults to rejected but surfaces in end-of-run review
    t3_dispositions = []

    for kri in candidates:
        result = {"kri_id": kri.get("kri_id"),
                  "tier": kri["_tier"],
                  "agent_count": kri["_agent_count"]}

        # Layer 1 — Verification
        l1 = layer1_verification_gate(kri, pdf_cache)
        result["layer1_verification"] = l1
        if not l1["pass"]:
            kri["_autojudgment_decision"] = "auto_reject"
            kri["_autojudgment_stage"] = "Layer 1 — verification"
            kri["_autojudgment_reason"] = l1["reason"]
            rejected_kris.append(kri)
            per_kri_results.append(result)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "rejected",
                                        "stage": "T3-2 verbatim",
                                        "reason": l1["reason"]})
            continue

        # Layer 1.5 — Atomicity
        l15 = layer1_5_atomicity(kri)
        result["layer1_5_atomicity"] = l15
        if not l15["pass"]:
            kri["_autojudgment_decision"] = "auto_reject"
            kri["_autojudgment_stage"] = "Layer 1.5 — atomicity"
            kri["_autojudgment_reason"] = l15["reason"]
            rejected_kris.append(kri)
            per_kri_results.append(result)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "rejected",
                                        "stage": "T3-2.5 atomicity",
                                        "reason": l15["reason"]})
            continue

        # Layer 2 — Coverage
        l2 = layer2_coverage_check(kri, t1)
        result["layer2_coverage"] = l2
        if not l2["pass"]:
            kri["_autojudgment_decision"] = "auto_reject"
            kri["_autojudgment_stage"] = "Layer 2 — coverage"
            kri["_autojudgment_reason"] = l2["reason"]
            rejected_kris.append(kri)
            per_kri_results.append(result)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "rejected",
                                        "stage": "T3-1 coverage filter",
                                        "reason": l2["reason"]})
            continue

        # Layer 3 — 6-judge panel
        votes = layer3_panel(kri, claude_client)
        result["layer3_panel"] = votes

        # Layer 4 — Aggregate
        l4 = layer4_aggregate(votes)
        result["layer4_aggregate"] = l4
        kri["_autojudgment_decision"] = l4["action"]
        kri["_autojudgment_stage"] = "Layer 4 — aggregate"
        kri["_autojudgment_reason"] = l4["reason"]
        kri["_autojudgment_panel_summary"] = l4["summary"]

        if l4["action"] == "auto_approve":
            approved_kris.append(kri)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "promoted",
                                        "stage": "T3-4 auto-approve",
                                        "reason": l4["reason"]})
        elif l4["action"] == "auto_reject":
            rejected_kris.append(kri)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "rejected",
                                        "stage": "T3-4 auto-reject",
                                        "reason": l4["reason"]})
        else:  # flag
            flagged_kris.append(kri)
            if kri["_tier"] == "T3":
                t3_dispositions.append({"kri_id": kri.get("kri_id"),
                                        "disposition": "flagged",
                                        "stage": "T3-4 flag",
                                        "reason": l4["reason"]})

        per_kri_results.append(result)

    # Interactive mode: block if any flagged items remain unresolved
    if not auto_approve_unanimous and flagged_kris:
        print(f"  ⚠ {len(flagged_kris)} KRIs flagged — interactive mode, pipeline blocks until resolved.")
        return False

    # Auto-approve-unanimous mode: flagged items DEFAULT TO REJECTED at Phase 4,
    # but are preserved in the end-of-run flagged-review table for user re-inclusion.
    _write_artifacts(out_dir, domain, per_kri_results, approved_kris,
                     rejected_kris, flagged_kris, t3_dispositions,
                     auto_approve_unanimous)

    # Rewrite raw_{DOMAIN}.json: in auto-approve mode, ONLY approved KRIs go in
    # (flagged items are defaulted to rejected for Phase-4 assembly). Flagged
    # items remain in the decision-table artifact and in the end-of-run flagged
    # review table for user re-inclusion.
    final = list(approved_kris)
    clean = [{kk: vv for kk, vv in k.items() if not kk.startswith("_")} for k in final]
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)

    print(f"  ✓ approved={len(approved_kris)}  rejected={len(rejected_kris)}  "
          f"flagged={len(flagged_kris)} (defaulted to rejected in auto mode)")
    print(f"  raw_{domain}.json now contains {len(final)} approved KRIs")
    return True


def _write_artifacts(out_dir, domain, per_kri_results, approved, rejected, flagged,
                     t3_dispositions, auto_mode):
    # Autojudgment report (full audit trail)
    report = {
        "_meta": {
            "domain": domain,
            "panel_total": N_PANEL_TOTAL,
            "panel_composition": {"claude": N_CLAUDE_JUDGES, "gemini": N_GEMINI_JUDGES},
            "tiers": {"t1_min": TIER_T1_MIN, "t2_min": TIER_T2_MIN},
            "mode": "auto_approve_unanimous" if auto_mode else "interactive",
            "flagged_default_action": "reject_at_phase_4_review_end_of_run",
        },
        "totals": {
            "approved": len(approved),
            "rejected": len(rejected),
            "flagged": len(flagged),
        },
        "per_kri": per_kri_results,
    }
    with open(os.path.join(out_dir, f"{domain}_autojudgment_report.json"),
              "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Decision table (sectioned)
    decision_table = {
        "domain": domain,
        "mode": report["_meta"]["mode"],
        "flagged_default_action": report["_meta"]["flagged_default_action"],
        "sections": {
            "auto_approved": [_table_row(k) for k in approved
                              if k.get("_autojudgment_decision") == "auto_approve"],
            "flagged_for_review": [_table_row(k) for k in flagged],
            "auto_rejected": [_table_row(k) for k in rejected],
        },
    }
    with open(os.path.join(out_dir, f"{domain}_manual_review_decisions.json"),
              "w", encoding="utf-8") as f:
        json.dump(decision_table, f, indent=2, ensure_ascii=False)

    # T3 filtered artifact (extended schema)
    with open(os.path.join(out_dir, f"{domain}_tier3_filtered.json"),
              "w", encoding="utf-8") as f:
        json.dump({"dispositions": t3_dispositions}, f, indent=2, ensure_ascii=False)


def _table_row(kri):
    return {
        "kri_id": kri.get("kri_id"),
        "category_id": kri.get("category_id"),
        "category_label": kri.get("category_label"),
        "kri_name": kri.get("kri_name"),
        "description": kri.get("description"),
        "rule_for_llm": kri.get("rule_for_llm"),
        "protocol_reference": kri.get("protocol_reference"),
        "supporting_quote": kri.get("supporting_quote"),
        "combined_ref": kri.get("combined_ref"),
        "additional_footnotes": kri.get("additional_footnotes"),
        "severity": kri.get("severity"),
        "tier": kri.get("_tier"),
        "agent_count": f"{kri.get('_agent_count', 0)}/10",
        "auto_decision": kri.get("_autojudgment_decision"),
        "stage": kri.get("_autojudgment_stage"),
        "reason": kri.get("_autojudgment_reason"),
        "panel_summary": kri.get("_autojudgment_panel_summary"),
        "decision_source": "auto",
        "user_override": None,
    }


# ─── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Step 2.6 — Auto-judgment for T2 + T3-promoted KRIs")
    parser.add_argument("--out", required=True, help="Run output directory")
    parser.add_argument("--domain", required=True,
                        help="Domain: ELIG, SAF, END, or OPS")
    parser.add_argument("--pdf", help="Protocol PDF (enables Layer-1 verbatim check)")
    parser.add_argument("--auto-approve-unanimous", dest="auto_approve_unanimous",
                        action="store_true", default=True,
                        help="Pipeline completes without blocking on flagged "
                             "items; flagged default to rejected, surface at "
                             "end-of-run review table (default: on)")
    parser.add_argument("--interactive", dest="auto_approve_unanimous",
                        action="store_false",
                        help="Block on flagged list until user resolves")
    args = parser.parse_args()

    if not os.path.isdir(args.out):
        print(f"✗ Not a directory: {args.out}")
        sys.exit(2)

    ok = run_autojudgment_for_domain(
        out_dir=args.out,
        domain=args.domain,
        pdf_path=args.pdf,
        auto_approve_unanimous=args.auto_approve_unanimous,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
