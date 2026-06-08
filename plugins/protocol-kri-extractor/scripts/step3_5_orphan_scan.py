"""
Step 3.5 — Protocol-Wide Orphan Scan (MANDATORY BLOCKING)

Runs FIRST in Phase 3, after Phase 2 completes (all raw_{DOMAIN}.json written),
before Step 3A. Scans the ENTIRE protocol for rule-like statements that were not
captured by any domain extractor in Phase 2.

SOA-flavored candidates (procedure-at-visit, visit-window, SoA table content,
SoA footnotes, cross-visit timing) are dropped during candidate consolidation
with reason `out_of_scope_soa` — they belong to the separate `soa-kri-extractor`
skill and are never promoted to a KRI here.

Architecture:
  6-agent panel (6 Gemini 3.5 Flash, thinking-high) — single-model, temp-spread
  Phase 1 — Primary section sweep (section-by-section using manifest.json)
  Phase 2 — Secondary page sweep (pages NOT claimed by any section)
  Phase 3 — Candidate consolidation (high-recall; tier by agent count)
              ≥4/6 → HIGH_CONFIDENCE (auto-promote)
              2–3/6 → USER_DECISION (escalate, pipeline pauses)
              1/6   → LOW_CONFIDENCE (logged, NOT silently dropped)
  Phase 4 — Cross-check: adjudication judge vs. ALL existing KRIs
              (true-duplicate definition; atomization splits are NOT duplicates)
  Phase 5 — Domain classification via Domain Boundary Rules
              ORPH-{DOMAIN}-{NNN} KRIs appended to raw_{DOMAIN}.json
  Phase 6 — Blocking gate until orphan_scan_report.json is complete

See SKILL.md "Step 3.5 — Protocol-Wide Orphan Scan (full spec)" for full details.

Usage:
  python step3_5_orphan_scan.py --out /path/to/output/ --pdf /path/to/protocol.pdf
"""

import json
import os
import re
import sys
import time
import shutil
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import pdfplumber
import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini_extract import call_gemini  # noqa: E402


# ─── Constants ──────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
# Item 1: the scan panel is all Gemini 3.5 Flash (thinking-high). Claude count
# kept at 0 only so any external importer of the name doesn't break.
N_CLAUDE_AGENTS = 0
N_GEMINI_AGENTS = 6
N_PANEL = N_GEMINI_AGENTS  # 6
DOMAINS = ["ELIG", "SAF", "END", "OPS"]
# SOA is OUT OF SCOPE for this skill — handled by `soa-kri-extractor`. Any
# SOA-flavored candidate that an agent flags is dropped during candidate
# consolidation with reason `out_of_scope_soa` rather than being promoted to a
# KRI here. The agent prompts below carry the SOA-exclusion methodology so
# agents are told to skip SoA table content / procedure-at-visit rules / visit-
# window rules from the start.
FALLBACK_DOMAIN = "OPS"  # Used when an agent proposes an unknown domain.

DOMAIN_LABELS = {
    "ELIG": "Eligibility",
    "SAF": "Safety & Toxicity",
    "END": "Endpoints & Statistics",
    "OPS": "Operations & Compliance",
}

SYSTEM_PROMPT = (
    "You are a clinical trial protocol auditor searching for orphan KRIs — rule-like "
    "statements in the protocol that are NOT already captured by the provided list of "
    "extracted KRIs. You favor high recall: when in doubt, FLAG the statement. "
    "Adjudication filters false positives later. You always return valid JSON with no "
    "markdown fences, no prose, no extra text.\n\n"
    "OUT OF SCOPE — SOA (Schedule of Activities). Schedule-of-Activities content is "
    "handled by the separate `soa-kri-extractor` skill. Do NOT flag any candidate "
    "whose subject is 'procedure X at visit Y', 'visit X within ±N days', any "
    "rule anchored to a specific visit code that says something HAPPENS at that "
    "visit, the SoA table itself, its footnotes, or the visit-schedule narrative. "
    "If you see such content, skip it — set proposed_domain to 'OUT_OF_SCOPE_SOA' "
    "and the consolidation step will drop it with reason `out_of_scope_soa`. Do "
    "NOT silently reclassify SoA content under ELIG/SAF/END/OPS — that would "
    "smuggle out-of-scope content into this skill's output. Skip is the only "
    "correct action."
)


# ─── PDF utilities ──────────────────────────────────────────────────────────
def load_pdf_text_for_pages(pdf_path, page_nums):
    """Load text for a list of page numbers, joined with [PAGE N] markers."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for pg in page_nums:
            if 1 <= pg <= total:
                text = pdf.pages[pg - 1].extract_text() or ""
                parts.append(f"[PAGE {pg}]\n{text}")
    return "\n\n".join(parts)


# ─── Manifest & KRI loading ─────────────────────────────────────────────────
def load_manifest_and_kris(output_dir):
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    all_kris = []
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
        all_kris.extend(kris)
    return manifest, all_kris, domain_files


def get_kris_citing_pages(all_kris, page_set):
    """Return KRIs whose protocol_reference cites any page in page_set."""
    if not isinstance(page_set, set):
        page_set = set(page_set)
    matching = []
    for k in all_kris:
        ref = k.get("protocol_reference", "")
        m = re.search(r'p\.?\s*(\d+)(?:\s*-\s*p\.?\s*(\d+))?', ref)
        if not m:
            continue
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        for pg in range(start, end + 1):
            if pg in page_set:
                matching.append(k)
                break
    return matching


# ─── Scanner prompts ────────────────────────────────────────────────────────
# Two prompt variants:
#   SCAN_PROMPT_TEMPLATE         — standard: section has existing KRIs; agents
#                                  flag only statements NOT covered by them.
#   ZERO_KRI_SCAN_PROMPT_TEMPLATE — emphasized: section has ZERO existing KRIs;
#                                  agents apply maximum recall and extract every
#                                  rule-like statement as a candidate orphan.
#                                  This closes the gap where Phase 2 produced no
#                                  KRIs for a section and the orphan scan was
#                                  the last safety net.
SCAN_PROMPT_TEMPLATE = """You are scanning a portion of a clinical trial protocol for rule-like statements that are NOT already captured by the existing extracted KRIs.

A rule-like statement is ANY of: obligation, threshold, prohibition, requirement, schedule, procedure, criterion, timing, method, stopping rule, reporting rule, eligibility sub-criterion, endpoint definition, statistical method, or governance rule.

Be HIGH RECALL — when in doubt, flag it. It is better to flag a non-orphan than to miss a real orphan. Adjudication will filter false positives later.

CRITICAL — ATOMIZATION IS NOT DUPLICATION:
If the protocol contains a compound rule that an existing KRI covers only partially — e.g., the existing KRI checks LDL-C percent change and the protocol also defines Apo B percent change as a separate analyte — the Apo B check is an ORPHAN and must be flagged. Different atomic aspects of the same clinical area are DIFFERENT KRIs.

PROTOCOL TEXT:
{section_text}

EXISTING KRIs ALREADY CITING PAGES IN THIS TEXT:
{existing_kris}

Find every rule-like statement that is NOT already covered by one of the existing KRIs. Return a JSON array, one entry per candidate orphan:
[
  {{
    "candidate_text": "the rule-like statement as a verbatim or near-verbatim excerpt from the protocol (<=30 words)",
    "page": <page number where it appears>,
    "surrounding_context": "<=50 words of context around the statement for disambiguation",
    "proposed_domain": "ELIG|SAF|END|OPS|OUT_OF_SCOPE_SOA",
    "reason_not_covered": "brief explanation of why this is not already covered by an existing KRI"
  }},
  ...
]

Return ONLY the JSON array. No markdown. No prose. Empty array [] if no orphans found."""


ZERO_KRI_SCAN_PROMPT_TEMPLATE = """You are scanning a portion of a clinical trial protocol. **This section has ZERO existing extracted KRIs** — Phase 2 extraction produced no KRIs citing any page in this section, and this scan is the last safety net before the pipeline advances.

Because no existing KRIs cover this section, every rule-like statement you find here is very likely an orphan. Apply MAXIMUM RECALL — extract every obligation, threshold, prohibition, requirement, schedule, procedure, criterion, timing, method, stopping rule, reporting rule, eligibility sub-criterion, endpoint definition, statistical method, or governance rule you can identify. Do not filter, do not self-edit, do not assume anything is "too minor" — adjudication and cross-check will filter false positives later.

If this section genuinely contains no rule-like content (e.g. title page, table of contents, references, signature block), return an empty array. Otherwise err strongly toward flagging.

CRITICAL — ATOMIZATION IS NOT DUPLICATION:
A compound rule in the protocol with N atomic sub-conditions becomes N separate orphan candidates. Do not collapse them.

PROTOCOL TEXT:
{section_text}

Return a JSON array, one entry per candidate orphan:
[
  {{
    "candidate_text": "the rule-like statement as a verbatim or near-verbatim excerpt from the protocol (<=30 words)",
    "page": <page number where it appears>,
    "surrounding_context": "<=50 words of context around the statement for disambiguation",
    "proposed_domain": "ELIG|SAF|END|OPS|OUT_OF_SCOPE_SOA",
    "reason_not_covered": "zero-KRI section — no existing KRI covers this content"
  }},
  ...
]

Return ONLY the JSON array. No markdown. No prose. Empty array [] only if the section genuinely has no rule-like content."""


def build_scan_prompt(section_text, existing_kris):
    """Pick the prompt variant based on whether the section has any existing KRIs.

    Zero-KRI sections get the emphasized maximum-recall prompt; sections with
    existing KRIs get the standard "find what's not already covered" prompt.
    """
    if not existing_kris:
        return ZERO_KRI_SCAN_PROMPT_TEMPLATE.format(section_text=section_text)
    kri_list = json.dumps(
        [
            {"kri_id": k["kri_id"], "rule_for_llm": k.get("rule_for_llm", "")}
            for k in existing_kris
        ],
        indent=2,
        ensure_ascii=False,
    )
    return SCAN_PROMPT_TEMPLATE.format(section_text=section_text, existing_kris=kri_list)


def _parse_array_response(raw):
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        m = re.search(r'\[[\s\S]*\]', text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


# ─── Scanner agents ─────────────────────────────────────────────────────────
# Temperature spread gives independence among the same-model (Gemini) scanners.
_SCAN_TEMPS = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35]


def run_gemini_scanner(agent_id, section_text, existing_kris, temperature=0.2):
    prompt = build_scan_prompt(section_text, existing_kris)
    try:
        response_text = call_gemini(prompt, system_prompt=SYSTEM_PROMPT,
                                    temperature=temperature, task="judge")
        candidates = _parse_array_response(response_text)
        for c in candidates:
            c["agent_id"] = agent_id
            c["model"] = "gemini-3.5-flash"
        return candidates
    except Exception as e:
        return [{"agent_id": agent_id, "model": "gemini-3.5-flash", "error": str(e)}]


def run_scan_panel(section_text, existing_kris):
    """Run the full N_PANEL-agent panel on a section in parallel. Single-model
    panel (Item 1) — N_PANEL Gemini 3.5 Flash scanners (thinking-high), with a
    temperature spread for independence. Returns combined candidates."""
    temps = (_SCAN_TEMPS * ((N_PANEL // len(_SCAN_TEMPS)) + 1))[:N_PANEL]
    all_candidates = []
    with ThreadPoolExecutor(max_workers=N_PANEL) as ex:
        futures = [
            ex.submit(run_gemini_scanner, f"G{i + 1}", section_text, existing_kris, temps[i])
            for i in range(N_PANEL)
        ]
        for f in as_completed(futures):
            candidates = f.result()
            all_candidates.extend([c for c in candidates if "error" not in c])
    return all_candidates


# ─── Consolidation (Phase 3) ────────────────────────────────────────────────
def consolidate_candidates(all_candidates, client):
    """Cluster semantically similar candidates; return one consolidated record per cluster."""
    if not all_candidates:
        return []

    # Build a compact view for the clustering prompt
    compact = [
        {
            "idx": i,
            "text": c.get("candidate_text", ""),
            "agent": c.get("agent_id"),
            "page": c.get("page"),
        }
        for i, c in enumerate(all_candidates)
    ]

    prompt = f"""Cluster these candidate orphan KRIs by semantic similarity. Two candidates belong to the same cluster if they describe the same rule-like statement (even when phrased differently).

Two candidates are in DIFFERENT clusters if they check different atomic things (e.g., "Apo B percent change" and "LDL-C percent change" are different — they are both valid orphans, not one cluster).

CANDIDATES:
{json.dumps(compact, indent=2, ensure_ascii=False)}

Return a JSON array of clusters:
[
  {{
    "cluster_text": "canonical statement for the cluster",
    "indices": [0, 3, 7],
    "unique_agents": ["C1", "C3", "G2"]
  }},
  ...
]

Return ONLY the JSON array. No markdown. No prose."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        clusters = _parse_array_response(response.content[0].text)
    except Exception:
        # Fallback: treat every candidate as its own cluster (no clustering)
        clusters = [
            {
                "cluster_text": c.get("candidate_text", ""),
                "indices": [i],
                "unique_agents": [c.get("agent_id")],
            }
            for i, c in enumerate(all_candidates)
        ]

    consolidated = []
    for cluster in clusters:
        indices = cluster.get("indices", [])
        if not indices:
            continue
        representative_idx = indices[0]
        if representative_idx >= len(all_candidates):
            continue
        rep = dict(all_candidates[representative_idx])
        # Deduplicate supporting agents across cluster instances
        agents_in_cluster = set()
        for i in indices:
            if i < len(all_candidates):
                a = all_candidates[i].get("agent_id")
                if a:
                    agents_in_cluster.add(a)
        # Override with clustering result's unique_agents if provided
        if cluster.get("unique_agents"):
            agents_in_cluster |= set(cluster["unique_agents"])
        rep["agent_count"] = len(agents_in_cluster)
        rep["supporting_agents"] = sorted(agents_in_cluster)
        rep["cluster_text"] = cluster.get("cluster_text", rep.get("candidate_text"))
        rep["cluster_size"] = len(indices)
        rep["all_instances"] = [
            all_candidates[i] for i in indices if i < len(all_candidates)
        ]
        consolidated.append(rep)

    return consolidated


def classify_promotion_tier(candidate):
    n = candidate.get("agent_count", 0)
    if n >= 4:
        return "HIGH_CONFIDENCE"
    if n >= 2:
        return "USER_DECISION"
    return "LOW_CONFIDENCE"


# ─── Cross-check (Phase 4) ──────────────────────────────────────────────────
def cross_check_against_existing(candidate, all_kris, client):
    """Adjudication judge: is this candidate ALREADY covered under the true-duplicate definition?"""
    prompt = f"""Is this candidate orphan KRI ALREADY covered by any of the existing KRIs listed below?

A candidate is "already covered" ONLY if an existing KRI checks the EXACT SAME atomic thing:
- Same clinical check
- Same specific values (same threshold, same drug, same dose, same timing window, same analyte, same population scope)
- Same time point or visit
- Same clinical context

Atomization splits are NOT duplicates. If the candidate checks a different atomic aspect of the same clinical area (e.g., a different analyte, a different visit, a different sub-criterion), the candidate is NOT covered — return covered=false.

CANDIDATE:
{json.dumps({
    "text": candidate.get("candidate_text"),
    "proposed_domain": candidate.get("proposed_domain"),
    "page": candidate.get("page"),
    "surrounding_context": candidate.get("surrounding_context"),
}, indent=2, ensure_ascii=False)}

EXISTING KRIs:
{json.dumps(
    [{"kri_id": k["kri_id"], "rule_for_llm": k.get("rule_for_llm", "")} for k in all_kris],
    indent=2,
    ensure_ascii=False,
)}

Return JSON:
{{
  "covered": true|false,
  "covering_kri_id": "kri_id if covered, else null",
  "reason": "brief explanation"
}}

Return ONLY the JSON. No markdown. No prose."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        return json.loads(text)
    except Exception as e:
        return {
            "covered": False,
            "covering_kri_id": None,
            "reason": f"adjudication error — keeping candidate conservatively ({e})",
        }


# ─── Classification (Phase 5) ───────────────────────────────────────────────
def _clean_quote(text, max_words=30):
    if not text:
        return ""
    text = text.strip()
    if text.startswith('"'):
        text = text.lstrip('"').strip()
    if text.endswith('"'):
        text = text.rstrip('"').strip()
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    return text


def build_orphan_kri(candidate, orphan_idx, existing_section_hint=None):
    """Build a full KRI record from a promoted candidate."""
    domain = candidate.get("proposed_domain", FALLBACK_DOMAIN)
    if domain not in DOMAINS:
        domain = FALLBACK_DOMAIN

    pg = candidate.get("page")
    section_hint = existing_section_hint or candidate.get("_section") or "Orphan Scan"
    ref = f"Section {section_hint}, p.{pg}" if pg else f"Section {section_hint}"

    quote = _clean_quote(candidate.get("candidate_text", ""))
    rule = f"Verify that {quote}" if quote else "Verify orphan rule (needs manual refinement)"

    return {
        "kri_id": f"ORPH-{domain}-{orphan_idx:03d}",
        "kri_name": f"Orphan: {quote[:60]}" if quote else f"Orphan #{orphan_idx:03d}",
        "description": (
            f"Orphan KRI captured by Step 3.5 protocol-wide scan. "
            f"Source: {candidate.get('_source', 'unknown')}. "
            f"Supporting agents: {candidate.get('agent_count', 0)}/{N_PANEL}."
        ),
        "category_id": domain,
        "category_label": DOMAIN_LABELS.get(domain, DOMAIN_LABELS[FALLBACK_DOMAIN]),
        "rule_for_llm": rule,
        "protocol_reference": ref,
        "supporting_quote": quote,
        "combined_ref": f'{ref} — "{quote}"',
        "additional_footnotes": None,
        "severity": "major",
        "_orphan_scan_meta": {
            "agent_count": candidate.get("agent_count"),
            "supporting_agents": candidate.get("supporting_agents"),
            "source_sweep": candidate.get("_source"),
            "reason_not_covered": candidate.get("reason_not_covered"),
        },
    }, domain


# ─── Main pipeline ──────────────────────────────────────────────────────────
def run_orphan_scan(output_dir, pdf_path):
    client = anthropic.Anthropic()
    manifest, all_kris, domain_files = load_manifest_and_kris(output_dir)

    print("Step 3.5 — Protocol-Wide Orphan Scan (BLOCKING)")
    print(f"  Existing KRIs loaded: {len(all_kris)}")
    print(f"  Panel: {N_PANEL} Gemini 3.5 Flash (thinking-high)")
    print()

    t0 = time.time()

    # ── Phase 1 — Primary section sweep ────────────────────────────────────
    print("Phase 1 — Primary section sweep (section-by-section)")
    primary_candidates = []
    section_map = manifest.get("section_map", {})
    claimed_pages = set()
    # Per-section coverage audit — records existing-KRI count and whether the
    # section triggered the zero-KRI emphasis prompt. Written to the report.
    section_coverage_audit = []

    for domain_key, sections in section_map.items():
        if not isinstance(sections, list):
            continue
        for section in sections:
            pages_approx = section.get("pages_approx") or [None, None]
            start = pages_approx[0] if pages_approx else None
            end = pages_approx[1] if len(pages_approx) > 1 else start
            if not start:
                continue
            if not end:
                end = start
            page_range = list(range(start, end + 1))
            claimed_pages.update(page_range)

            section_text = load_pdf_text_for_pages(pdf_path, page_range)
            if not section_text.strip():
                continue

            existing = get_kris_citing_pages(all_kris, set(page_range))
            section_number = section.get("section_number", "?")
            is_zero_kri = len(existing) == 0
            tag = " [ZERO-KRI → emphasized scan]" if is_zero_kri else ""
            print(
                f"  [{domain_key}] §{section_number} pp {start}-{end} "
                f"({len(existing)} existing KRIs){tag}...",
                flush=True,
            )

            candidates = run_scan_panel(section_text, existing)
            for c in candidates:
                c["_source"] = "primary_section_sweep"
                c["_section"] = section_number
                c["_is_zero_kri_section"] = is_zero_kri
            primary_candidates.extend(candidates)
            section_coverage_audit.append({
                "domain": domain_key,
                "section": section_number,
                "pages": [start, end],
                "existing_kri_count": len(existing),
                "is_zero_kri_section": is_zero_kri,
                "candidates_flagged": len(candidates),
            })
            print(f"    → {len(candidates)} candidate(s)")

    # ── Phase 2 — Secondary page sweep (orphan pages) ──────────────────────
    print("\nPhase 2 — Secondary page sweep (pages not claimed by any section)")
    total_pages = manifest.get("total_pages") or 0
    if total_pages == 0:
        # Fall back to a pdfplumber open for page count
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

    all_pages = set(range(1, total_pages + 1))
    orphan_pages = sorted(all_pages - claimed_pages)
    print(f"  Orphan pages: {len(orphan_pages)} / {total_pages} total")

    secondary_candidates = []
    for pg in orphan_pages:
        page_text = load_pdf_text_for_pages(pdf_path, [pg])
        if not page_text.strip():
            continue
        existing = get_kris_citing_pages(all_kris, {pg})
        candidates = run_scan_panel(page_text, existing)
        for c in candidates:
            c["_source"] = "secondary_page_sweep"
            c["_page"] = pg
            if "_section" not in c:
                c["_section"] = "Orphan Page"
        secondary_candidates.extend(candidates)

    print(f"  Secondary sweep candidates: {len(secondary_candidates)}")

    # ── Phase 3 — Consolidation ────────────────────────────────────────────
    print("\nPhase 3 — Consolidation (clustering + tier classification)")
    all_candidates = primary_candidates + secondary_candidates
    print(f"  Total raw candidates (pre-cluster): {len(all_candidates)}")

    consolidated = consolidate_candidates(all_candidates, client)

    high_conf = [c for c in consolidated if classify_promotion_tier(c) == "HIGH_CONFIDENCE"]
    user_dec = [c for c in consolidated if classify_promotion_tier(c) == "USER_DECISION"]
    low_conf = [c for c in consolidated if classify_promotion_tier(c) == "LOW_CONFIDENCE"]

    print(f"  Consolidated clusters: {len(consolidated)}")
    print(f"  HIGH_CONFIDENCE (≥4/6 auto-promote):    {len(high_conf)}")
    print(f"  USER_DECISION  (2–3/6 → user review):   {len(user_dec)}")
    print(f"  LOW_CONFIDENCE (1/6 → logged, not dropped): {len(low_conf)}")

    # ── Phase 4 — Cross-check against existing KRIs ────────────────────────
    print("\nPhase 4 — Cross-check against existing KRIs")
    promoted = []
    dropped = []
    for c in high_conf:
        check = cross_check_against_existing(c, all_kris, client)
        if check.get("covered"):
            dropped.append(
                {
                    "candidate_text": c.get("candidate_text"),
                    "covering_kri_id": check.get("covering_kri_id"),
                    "reason": check.get("reason"),
                }
            )
        else:
            promoted.append(c)
    print(f"  Dropped (already covered): {len(dropped)}")
    print(f"  Promoted to classification: {len(promoted)}")

    # ── Phase 5 — Classification & KRI generation ──────────────────────────
    print("\nPhase 5 — Domain classification & KRI generation")
    promoted_kris = []
    classification_counts = {d: 0 for d in DOMAINS}
    per_domain_counters = {d: 0 for d in DOMAINS}
    dropped_out_of_scope_soa = []

    for c in promoted:
        tentative_domain = c.get("proposed_domain", FALLBACK_DOMAIN)
        # SOA is OUT OF SCOPE for this skill — drop with reason `out_of_scope_soa`.
        if tentative_domain == "OUT_OF_SCOPE_SOA" or tentative_domain == "SOA":
            dropped_out_of_scope_soa.append({
                "candidate_text": c.get("candidate_text"),
                "page": c.get("page"),
                "proposed_domain": tentative_domain,
                "reason": "out_of_scope_soa — handled by soa-kri-extractor",
            })
            continue
        if tentative_domain not in DOMAINS:
            tentative_domain = FALLBACK_DOMAIN
        per_domain_counters[tentative_domain] += 1
        idx = per_domain_counters[tentative_domain]

        kri, domain = build_orphan_kri(c, idx)
        promoted_kris.append(kri)
        classification_counts[domain] += 1
        domain_files.setdefault(domain, []).append(kri)

    if dropped_out_of_scope_soa:
        print(f"  Dropped {len(dropped_out_of_scope_soa)} SOA-flavored candidate(s) "
              f"as out_of_scope_soa (handled by soa-kri-extractor)")

    # ── Save updated raw_{DOMAIN}.json files ───────────────────────────────
    for domain, kris in domain_files.items():
        if not kris:
            continue
        path = os.path.join(output_dir, f"raw_{domain}.json")
        backup = path + ".pre_3_5.json"
        if os.path.exists(path) and not os.path.exists(backup):
            shutil.copy(path, backup)
        with open(path, "w") as f:
            json.dump({"kris": kris}, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0

    # ── Build report ───────────────────────────────────────────────────────
    report = {
        "_meta": {
            "step": "3.5",
            "total_agents": N_PANEL,
            "agent_breakdown": {"gemini_scan_panel": N_PANEL, "claude_adjudication_calls": "consolidate + cross_check (single calls, not a panel)"},
            "sections_scanned": sum(
                len(s) if isinstance(s, list) else 0 for s in section_map.values()
            ),
            "orphan_pages_scanned": len(orphan_pages),
            "total_pages": total_pages,
            "elapsed_seconds": round(elapsed, 1),
        },
        "primary_sweep": {
            "total_candidates": len(primary_candidates),
            "zero_kri_sections": [
                s for s in section_coverage_audit if s["is_zero_kri_section"]
            ],
            "section_coverage_audit": section_coverage_audit,
        },
        "secondary_sweep": {
            "orphan_pages": orphan_pages,
            "total_candidates": len(secondary_candidates),
        },
        "consolidation": {
            "raw_total": len(all_candidates),
            "clusters": len(consolidated),
            "high_confidence": len(high_conf),
            "user_decision": len(user_dec),
            "low_confidence": len(low_conf),
        },
        "low_confidence_candidates": low_conf,
        "user_decisions_pending": user_dec,
        "cross_check": {
            "dropped_as_covered": len(dropped),
            "dropped_list": dropped,
            "promoted_to_classification": len(promoted),
        },
        "classification": {
            "by_domain": classification_counts,
            "dropped_as_out_of_scope_soa": len(dropped_out_of_scope_soa),
        },
        "out_of_scope_soa": dropped_out_of_scope_soa,
        "promoted_orphans": promoted_kris,
    }

    out_path = os.path.join(output_dir, "orphan_scan_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved → {out_path}")
    print(f"  Promoted orphans: {len(promoted_kris)}")
    print(f"  Classification: {classification_counts}")
    print(f"  Elapsed: {elapsed:.1f}s")

    if user_dec:
        print(
            f"\n  ⚠ {len(user_dec)} USER_DECISION items pending — review them in "
            f"orphan_scan_report.json and re-run after decisions are made."
        )
        print("  ✗ BLOCKED — Step 3A cannot start until all user decisions are resolved.")
        return False

    print("  ✓ Step 3.5 complete — Step 3A may begin.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 3.5 — Protocol-Wide Orphan Scan")
    parser.add_argument("--out", required=True, help="Output directory containing raw_*.json + manifest.json")
    parser.add_argument("--pdf", required=True, help="Protocol PDF path")
    args = parser.parse_args()

    passed = run_orphan_scan(args.out, args.pdf)
    sys.exit(0 if passed else 1)
