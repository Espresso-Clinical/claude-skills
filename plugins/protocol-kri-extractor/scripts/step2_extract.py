"""
Step 2 — Per-Section KRI Extraction (ELIG / SAF / END / OPS)

10-agent panel per domain: 10 Gemini 3.5 Flash agents (thinking-high) run
independently with a temperature spread for independence, then their outputs are
merged and clustered with SequenceMatcher to set proper agent_count for Step 2.6
tier classification. Single-model panel (Item 1) — no Claude sub-agents.

Schedule of Activities (SOA) is OUT OF SCOPE for this skill — handled by the
separate `soa-kri-extractor` skill. Every extractor prompt below carries the
SOA-exclusion methodology block.

Protocol-agnostic — driven entirely by the manifest's section map.
"""

import json, sys, re, os
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from scope_signature import scope_conflict, kri_identity  # scope-aware clustering + identity (Item 2)

# Mandatory SOA-exclusion block injected into every domain extractor prompt.
SOA_EXCLUSION_BLOCK = """

OUT OF SCOPE — SOA (Schedule of Activities)

Schedule-of-Activities content is handled by the separate `soa-kri-extractor`
skill. It is OUT OF SCOPE for this extractor. Do NOT emit any KRI whose subject
is one of the following:
  - "Procedure X is performed at visit Y" (any procedure × visit cell).
  - "Visit X must occur within ±N days of [reference]" (visit windows / check-ins).
  - Any rule that anchors an obligation to a specific visit code (V1, V2, SCR,
    EDC, EOS, Day 1, Week 4, etc.) and is essentially saying that something
    *happens* at that visit.
  - Content from the SoA table itself, its footnotes, or the visit-schedule
    narrative section.
  - "Per SOA", "per the Schedule of Activities", "per the SoA table" or
    equivalent phrasings.

If you encounter SOA-flavored content while extracting your assigned domain
section, SKIP it. Do not output a KRI for it. The orphan scan (Step 3.5) and
the cross-domain dedup (Step 4A-Dedup) carry the same exclusion and will drop
any SOA-flavored KRI that slips through. Stay strictly within your assigned
domain's content type.
"""

# Mandatory scope-atomization block injected into every domain extractor prompt (Fix #6).
SCOPE_ATOMIZATION_BLOCK = """

SCOPE ATOMIZATION — one KRI = ONE verifiable check about ONE thing at ONE scope.
Split a single protocol sentence into MULTIPLE KRIs (one per scope) whenever it spans:
  - TWO TIME-SCOPES — e.g. "prohibited prior to AND during the study" → 2 KRIs: a
    pre-treatment/screening check (reads screening history) AND an on-study check
    (reads the on-study con-med log). Capturing only the "prior to" half is a
    coverage failure.
  - TWO OBLIGATIONS in one sentence — e.g. "all unresolved AEs are followed for 30
    days post-study AND study-drug-related AEs are followed until resolution" → 2 KRIs.
  - MULTIPLE STUDY PHASES / TIME POINTS — a rule stated for both the safety run-in
    and the randomization phase, or for several visits, when the anchor or value
    differs → one KRI per phase / time point.
  - MULTIPLE ANALYTES / SUB-CRITERIA — already required; keep doing it.
Do NOT split a single-field numeric range ("BMI 18–40" is ONE check) and do NOT
split illustrative examples ("such as A, B, C" stays ONE KRI, examples in the
description). When in doubt about a compound sentence, emit the separate atomic KRIs.
"""

SYSTEM_PROMPT = """You are a clinical research associate (CRA) and protocol expert.
You read clinical trial protocol sections and extract monitoring rules as KRIs
(Key Risk Indicators) — actionable verification instructions for site monitoring.
You always return valid JSON arrays. No markdown fences, no prose.""" + SOA_EXCLUSION_BLOCK + SCOPE_ATOMIZATION_BLOCK

KRI_SCHEMA = """Each KRI must have exactly these fields:
{
  "kri_id": "CATEGORY-SUBCATEGORY-NNN  e.g. ELIG-INC-001, SAF-AE-001, END-PRI-001, OPS-IMP-001",
  "kri_name": "Short name, max 8 words",
  "description": "2-3 sentences stating the verifiable requirement WITH its exact specifics — drug names, doses, thresholds, timing windows, analytes, population/visit scope, and any condition — copied faithfully from the protocol. The description + supporting_quote carry the rule's full content (the downstream distiller authors the machine rule from them). Do NOT write a 'Verify that...' instruction.",
  "category_id": "ELIG|SAF|END|OPS",
  "category_label": "full category name",
  "protocol_reference": "Section X.X, p.N — section label and page number ONLY, no embedded quote (e.g. 'Section 4.4.1, p.65')",
  "supporting_quote": "Verbatim text copied exactly from the cited protocol page, ≤30 words, with NO outer double quotes",
  "severity": "critical|major|minor",
  "additional_footnotes": "Footnote N: verbatim text — or null if none"
}"""

CATEGORY_CONFIGS = {
    "ELIG": {
        "label": "Eligibility",
        "id_prefix": "ELIG",
        "subcategories": {
            "INC": "Inclusion criteria",
            "EXC": "Exclusion criteria"
        },
        "instructions": """Extract one KRI per criterion (or per meaningful sub-criterion).
- Inclusion: ELIG-INC-001, ELIG-INC-002, ...
- Exclusion: ELIG-EXC-001, ELIG-EXC-002, ...
- Multi-part criteria (e.g. 5a, 5b): one KRI per lettered sub-part
- Capture the criterion's exact requirement (inclusion) or excluded condition (exclusion) in the description
- Include exact numeric thresholds, timeframes, and clinical terms verbatim
- Lab abnormality thresholds: list each parameter and its threshold value"""
    },
    "SAF": {
        "label": "Safety & Toxicity",
        "id_prefix": "SAF",
        "subcategories": {
            "AE": "AE/SAE collection and reporting",
            "PREG": "Pregnancy reporting",
            "ALLERGY": "Allergic reaction management",
            "DSMB": "Safety monitoring committees",
            "RM": "Rescue medication",
            "STOP": "Treatment discontinuation/stopping rules",
            "AESI": "Adverse events of special interest"
        },
        "instructions": """Extract every safety-relevant rule: AE collection windows, SAE reporting timelines,
allergic reaction management protocols, stopping rules, DSMB triggers, rescue medication limits.
- Include exact reporting timeframes (24h, 48h, etc.)
- Include exact drug names and doses for emergency treatments
- Include specific AESI categories as defined in the protocol
- Distinguish: pre-IMP conditions = medical history (not AE)
- Include post-study follow-up safety collection rules"""
    },
    "END": {
        "label": "Endpoints & Statistics",
        "id_prefix": "END",
        "subcategories": {
            "PRI": "Primary endpoints",
            "KSEC": "Key secondary endpoints",
            "SEC": "Secondary endpoints",
            "EXP": "Exploratory endpoints",
            "ICE": "Intercurrent events",
            "ASET": "Analysis sets",
            "STAT": "Statistical methods",
            "INTER": "Interim analysis"
        },
        "instructions": """Extract one KRI per endpoint, analysis set definition, and key statistical rule.
- Primary first, then key secondary, secondary, exploratory (in protocol order)
- One KRI per ICE type (ICE1, ICE2, etc.) if defined
- Analysis sets: exact boundary definitions (ITT = all randomized; mITT = ≥1 dose + baseline + ≥1 post-baseline)
- Statistical methods: ANCOVA covariates, gatekeeping sequence, alpha levels
- Baseline definitions: general (Day 0 pre-dose) and endpoint-specific (e.g. ADP-NRS weekly average)
- Interim analysis: exact trigger criteria"""
    },
    "OPS": {
        "label": "Operations & Compliance",
        "id_prefix": "OPS",
        "subcategories": {
            "IMP": "IMP storage and handling",
            "BLIND": "Blinding procedures",
            "RECS": "Records and documentation",
            "COMP": "Regulatory and GCP compliance",
            "ADMIN": "Administrative procedures"
        },
        "instructions": """Extract operational compliance rules: IMP storage conditions, blinding procedures,
record retention requirements, eCRF requirements, regulatory compliance rules.
- Include exact temperature ranges, storage conditions
- Unblinding: who can do it, documentation required
- Record retention: exact duration (years)
- eCRF: data restrictions, approval requirements
- Participant withdrawal: replacement rules"""
    }
}

CATEGORY_LABELS = {
    "ELIG": "Eligibility",
    "SAF": "Safety & Toxicity",
    "END": "Endpoints & Statistics",
    "OPS": "Operations & Compliance",
}

# ─── SequenceMatcher clustering helpers ──────────────────────────────────────

def normalize_rule(rule):
    if not rule:
        return ""
    r = rule.lower()
    r = re.sub(r"[^\w\s]", " ", r)
    r = re.sub(r"\s+", " ", r).strip()
    r = re.sub(r"^(verify that|confirm that|check that|ensure that)\s+", "", r)
    return r


def rules_similar(a, b, threshold=0.72):
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < 10 or len(b) < 10:
        return False
    if max(len(a), len(b)) / max(1, min(len(a), len(b))) > 2.5:
        return False
    if SequenceMatcher(None, a, b).ratio() < threshold:
        return False
    # Fix #6 — scope-aware: two text-similar rules that assert DIFFERENT
    # time-scopes (prior vs during) or study phases (run-in vs randomization)
    # are atomization splits, NOT duplicates — keep them in separate clusters so
    # the merge step cannot re-collapse what scope atomization split.
    if scope_conflict(a, b):
        return False
    return True


def cluster_agent_outputs(all_agent_kris):
    """
    all_agent_kris: list of (agent_label, kris_list) where agent_label is e.g. "C1", "G1"
    Returns: list of clusters. Each cluster is a list of dicts {kri, agent_label}.
    """
    clusters = []
    for agent_label, kris in all_agent_kris:
        for kri in kris:
            norm = normalize_rule(kri_identity(kri))
            if not norm:
                continue
            placed = False
            for cluster in clusters:
                rep_norm = normalize_rule(kri_identity(cluster[0]["kri"]))
                if rules_similar(norm, rep_norm):
                    cluster.append({"kri": kri, "agent_label": agent_label})
                    placed = True
                    break
            if not placed:
                clusters.append([{"kri": kri, "agent_label": agent_label}])
    return clusters


def pick_representative(cluster):
    """Pick the KRI with the richest description as the representative."""
    return max(cluster, key=lambda x: len(x["kri"].get("description", "") or ""))


def merge_clusters(clusters):
    """
    Convert clusters to merged KRI list.
    Each output KRI gets agent_count = number of distinct agents in the cluster.
    """
    merged = []
    for cluster in clusters:
        distinct_agents = len({entry["agent_label"] for entry in cluster})
        rep = pick_representative(cluster)
        kri = dict(rep["kri"])
        kri["agent_count"] = distinct_agents
        merged.append(kri)
    return merged


# ─── PDF helpers ──────────────────────────────────────────────────────────────

def extract_pages_text(pdf_path: str, page_nums: list) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        parts = []
        for n in page_nums:
            if 1 <= n <= total:
                text = pdf.pages[n-1].extract_text() or ""
                if text.strip():
                    parts.append(f"[PAGE {n}]\n{text}")
    return "\n\n".join(parts)


def get_section_pages(sections: list, total_pages: int) -> list:
    pages = set()
    for s in sections:
        pa = s.get("pages_approx") or [None, None]
        start, end = pa[0], pa[1]
        if start:
            start = int(start)
            end = int(end) if end else min(start + 15, total_pages)
            for p in range(start, end + 1):
                pages.add(p)
    return sorted(pages)


def _strip_outer_quotes(s):
    if not isinstance(s, str):
        return s
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].strip()
    return s.lstrip('"').rstrip('"').strip()


def _split_legacy_protocol_reference(ref):
    """Older prompts produced 'Section X.X, Page N: "quote"' as a single field.
    Split into (clean_ref, quote) — no-op if already clean.
    """
    if not isinstance(ref, str):
        return ref, ""
    m = re.match(r'^(.*?):\s*"(.+)"\s*$', ref.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return ref.strip(), ""


def _normalize_kris(kris, category):
    """Ensure every KRI matches the SKILL.md output schema and has agent_count.

    Handles legacy outputs (single embedded-quote protocol_reference) and missing
    fields (supporting_quote, combined_ref, severity, agent_count). Drops outer
    double quotes from supporting_quote per Quality Rule 11.

    NOTE: Does NOT overwrite agent_count if already set (e.g. by the 10-agent
    panel merger). Only sets a default of 1 when the field is absent or invalid.
    """
    out = []
    for k in kris or []:
        if not isinstance(k, dict):
            continue
        # Item 2: rule_for_llm is no longer part of the schema — drop it if an
        # agent emitted one anyway (the downstream distiller authors it from scratch).
        k.pop("rule_for_llm", None)
        # category_id / category_label
        k.setdefault("category_id", category)
        k.setdefault("category_label", CATEGORY_LABELS.get(category, category))

        # Clean up protocol_reference + supporting_quote (handle legacy format)
        ref = k.get("protocol_reference", "") or ""
        quote = k.get("supporting_quote", "") or ""
        if not quote:
            ref_clean, ref_quote = _split_legacy_protocol_reference(ref)
            if ref_quote:
                ref = ref_clean
                quote = ref_quote
        quote = _strip_outer_quotes(quote)
        ref = ref.strip()
        k["protocol_reference"] = ref
        k["supporting_quote"] = quote

        # combined_ref — always recompute deterministically
        if ref and quote:
            k["combined_ref"] = f'{ref} — "{quote}"'
        elif ref:
            k["combined_ref"] = ref
        else:
            k.setdefault("combined_ref", "")

        # additional_footnotes — null is allowed
        if "additional_footnotes" not in k:
            k["additional_footnotes"] = None

        # severity — default major if missing/invalid
        sev = (k.get("severity") or "").lower().strip()
        if sev not in {"critical", "major", "minor"}:
            sev = "major"
        k["severity"] = sev

        # agent_count — preserve merger-set value; only default when absent/invalid
        if not isinstance(k.get("agent_count"), int):
            k["agent_count"] = 1

        out.append(k)
    return out


# ─── 10-agent panel extraction ────────────────────────────────────────────────

def _run_gemini_panel(pdf_path, category, output_dir, n_agents=5):
    """Run N Gemini agents via multi-turn native PDF extraction.
    Returns list of (label, kris) tuples, or raises on unrecoverable error.
    """
    from gemini_extract import run_gemini_extraction_multi_turn, save_gemini_results

    raw_results = run_gemini_extraction_multi_turn(
        domain=category,
        pdf_path=pdf_path,
        n_agents=n_agents,
    )

    # save_gemini_results uses its own naming convention; also save our naming
    labeled = []
    for agent_idx, kris in raw_results:
        label = f"G{agent_idx}"
        # Save per-agent file with our naming convention
        path = os.path.join(output_dir, f"gemini_agent_{label}_{category.lower()}.json")
        with open(path, "w") as f:
            json.dump(kris, f, indent=2)
        print(f"  Gemini agent {label}: {len(kris)} KRIs saved")
        labeled.append((label, kris))

    return labeled


# ─── Main extraction entry point ──────────────────────────────────────────────

def run_extraction(pdf_path: str, manifest_path: str,
                   output_dir: str, categories: list = None):
    with open(manifest_path) as f:
        manifest = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    cats = categories or ["ELIG", "SAF", "END", "OPS"]

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    all_results = {}
    total_tokens = 0

    for cat in cats:
        print(f"\n{'='*50}")
        print(f"  Domain: {cat} — {CATEGORY_LABELS.get(cat, cat)}")
        print(f"{'='*50}")

        if cat not in CATEGORY_CONFIGS:
            print(f"  Skipping {cat} — not an in-scope domain (ELIG/SAF/END/OPS)")
            continue

        cfg = CATEGORY_CONFIGS[cat]
        sections = manifest.get("section_map", {}).get(cat, [])

        if not sections:
            print(f"  No sections mapped for {cat} — skipping")
            continue

        pages = get_section_pages(sections, total_pages)
        print(f"  Pages: {pages[:5]}{'...' if len(pages) > 5 else ''} ({len(pages)} total)")

        try:
            # ── 10 Gemini 3.5 Flash agents (thinking-high), temperature-spread
            #    for independence. Single-model panel (Item 1) — no Claude sub-agents.
            print(f"\n  [Gemini panel — 10 agents (gemini-3.5-flash, thinking-high)]")
            gemini_results = _run_gemini_panel(pdf_path, cat, output_dir, n_agents=10)

            # ── Merge & cluster all agent outputs ────────────────────────────
            all_agent_kris = gemini_results
            total_agents = len(all_agent_kris)
            print(f"\n  Clustering outputs from {total_agents} agents...")

            clusters = cluster_agent_outputs(all_agent_kris)
            merged_kris = merge_clusters(clusters)

            # ── Step 4: Schema normalization (preserves agent_count) ─────────
            merged_kris = _normalize_kris(merged_kris, cat)

            # Print per-cluster summary
            agent_count_dist = {}
            for k in merged_kris:
                ac = k.get("agent_count", 1)
                agent_count_dist[ac] = agent_count_dist.get(ac, 0) + 1

            print(f"  Merged: {len(merged_kris)} KRIs from {len(clusters)} clusters")
            for ac in sorted(agent_count_dist.keys(), reverse=True):
                print(f"    agent_count={ac}: {agent_count_dist[ac]} KRIs")

            all_results[cat] = merged_kris

            # ── Step 5: Save domain file ──────────────────────────────────────
            meta = {
                "step": "2",
                "protocol_id": protocol_id,
                "category": cat,
                "kri_count": len(merged_kris),
                "panel": "10x gemini-3.5-flash (thinking-high)",
                "agents_gemini": len(gemini_results),
                "total_agents": total_agents,
            }

            out_path = os.path.join(output_dir, f"raw_{cat}.json")
            with open(out_path, "w") as f:
                json.dump({"_meta": meta, "kris": merged_kris}, f, indent=2)
            print(f"  Saved → {out_path}")

        except Exception as e:
            print(f"  ERROR in {cat}: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'='*55}")
    print(f"Extraction complete.")
    print(f"Total KRIs: {sum(len(v) for v in all_results.values())}")
    for cat, kris in all_results.items():
        print(f"  {cat}: {len(kris)} KRIs")

    return all_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 2 — Extract KRIs from protocol (10-agent panel)")
    parser.add_argument("--pdf",  required=True, help="Path to protocol PDF")
    parser.add_argument("--dir",  required=True, help="Output directory (must contain manifest.json)")
    parser.add_argument("--cats", default=None,  help="Comma-separated category list, e.g. ELIG,SAF (default: ELIG,SAF,END,OPS)")
    args = parser.parse_args()

    cats = args.cats.split(",") if args.cats else None
    print(f"\n{'='*55}")
    print(f"Extracting KRIs: {os.path.basename(args.pdf)}" + (f" (categories: {cats})" if cats else " (all in-scope categories)"))
    print(f"Mode: 10-agent Gemini panel (gemini-3.5-flash, thinking-high) with SequenceMatcher clustering")

    run_extraction(
        pdf_path=args.pdf,
        manifest_path=os.path.join(args.dir, "manifest.json"),
        output_dir=args.dir,
        categories=cats
    )
