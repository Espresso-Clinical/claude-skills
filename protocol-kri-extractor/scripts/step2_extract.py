"""
Step 2 — Per-Section KRI Extraction (ELIG / SAF / END / OPS)
Extracts KRIs from each in-scope protocol section identified in the manifest.
One LLM call per section group (batched by domain category).
Produces raw_ELIG.json, raw_SAF.json, raw_END.json, raw_OPS.json.

Schedule of Activities (SOA) is OUT OF SCOPE for this skill — handled by the
separate `soa-kri-extractor` skill. Every extractor prompt below carries the
SOA-exclusion methodology block.

Protocol-agnostic — driven entirely by the manifest's section map.
"""

import json, sys, re, os
import pdfplumber
import anthropic

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

SYSTEM_PROMPT = """You are a clinical research associate (CRA) and protocol expert.
You read clinical trial protocol sections and extract monitoring rules as KRIs
(Key Risk Indicators) — actionable verification instructions for site monitoring.
You always return valid JSON arrays. No markdown fences, no prose.""" + SOA_EXCLUSION_BLOCK

KRI_SCHEMA = """Each KRI must have exactly these fields:
{
  "kri_id": "CATEGORY-SUBCATEGORY-NNN  e.g. ELIG-INC-001, SAF-AE-001, END-PRI-001, OPS-IMP-001",
  "kri_name": "Short name, max 8 words",
  "description": "1-2 sentences: what protocol requirement this monitors and why it matters",
  "category_id": "ELIG|SAF|END|OPS",
  "category_label": "full category name",
  "rule_for_llm": "Actionable CRA instruction starting with 'Verify that...' Be specific: include exact drug names, thresholds, timeframes, data sources (e.g. 'by checking medication logs'), and clinical conditions verbatim from the protocol.",
  "protocol_reference": "Section X.X, Page N: \"verbatim quote ≤30 words from protocol\"",
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
- rule_for_llm: "Verify that [specific requirement] is documented/confirmed" for inclusion
- rule_for_llm: "Verify the absence of [condition]..." or "Verify that [exclusion] is not present" for exclusion
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

def extract_pages_text(pdf_path: str, page_nums: list[int]) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        parts = []
        for n in page_nums:
            if 1 <= n <= total:
                text = pdf.pages[n-1].extract_text() or ""
                if text.strip():
                    parts.append(f"[PAGE {n}]\n{text}")
    return "\n\n".join(parts)

def get_section_pages(sections: list, total_pages: int) -> list[int]:
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

def extract_category(pdf_path: str, manifest: dict,
                     category: str, output_dir: str) -> list[dict]:
    if category not in CATEGORY_CONFIGS:
        print(f"  Skipping {category} — not an in-scope domain (ELIG/SAF/END/OPS)")
        return []

    client = anthropic.Anthropic()

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    cfg = CATEGORY_CONFIGS[category]
    sections = manifest.get("section_map", {}).get(category, [])

    if not sections:
        print(f"  No sections mapped for {category} — skipping")
        return []

    pages = get_section_pages(sections, total_pages)
    print(f"  {category}: reading pages {pages[:5]}{'...' if len(pages) > 5 else ''} ({len(pages)} total)")

    return extract_single_call(client, pdf_path, manifest,
                               category, cfg, pages, output_dir)


def extract_single_call(client, pdf_path, manifest,
                        category, cfg, pages, output_dir) -> list[dict]:
    protocol_text = extract_pages_text(pdf_path, pages)
    protocol_id = manifest.get("protocol_id", "UNKNOWN")

    section_list = "\n".join(
        f"  - Section {s['section_number']}: {s['title']}"
        for s in manifest.get("section_map", {}).get(category, [])
    )

    prompt = f"""You are extracting KRIs (Key Risk Indicators) from a clinical trial protocol.

PROTOCOL: {protocol_id}
CATEGORY: {category} — {cfg['label']}
SECTIONS TO COVER:
{section_list}

EXTRACTION INSTRUCTIONS:
{cfg['instructions']}

KRI SCHEMA (every KRI must match this exactly):
{KRI_SCHEMA}

ID FORMAT for this category:
- {category}: use subcategory codes {list(cfg['subcategories'].keys())}
- Example IDs: {cfg['id_prefix']}-{list(cfg['subcategories'].keys())[0]}-001, {cfg['id_prefix']}-{list(cfg['subcategories'].keys())[0]}-002

--- PROTOCOL TEXT ---
{protocol_text}
--- END ---

Return a JSON array of KRI objects. Every rule or requirement in the protocol text 
that a CRA would need to verify must become a KRI.
Return ONLY the JSON array, starting with [ and ending with ]."""

    print(f"  Calling Claude for {category}...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    kris, tokens_repair = _safe_json_loads_kris(raw, client, category, output_dir)
    tokens = response.usage.input_tokens + response.usage.output_tokens + tokens_repair
    print(f"  → {len(kris)} KRIs extracted ({tokens} tokens)")
    return kris, tokens


# ─── Robust JSON parsing for LLM responses ───────────────────────────────────
def _safe_json_loads_kris(raw: str, client, category: str, output_dir: str = None):
    """Parse model output as JSON, applying common cleanups + a one-shot repair pass on failure.

    Cleanups handle the LLM error modes most often seen on long extractions:
      - Smart/curly quotes → straight quotes
      - Trailing commas before } or ]
      - Stray markdown fences left after the basic strip
      - Leading prose/preamble before the JSON array

    On unrecoverable failure, dispatches a single 'fix this JSON' Claude call.
    Returns (parsed_list, tokens_used_in_repair).
    """
    repair_tokens = 0

    def _try(text):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "kris" in obj:
                obj = obj["kris"]
            if not isinstance(obj, list):
                return None
            return [k for k in obj if isinstance(k, dict)]
        except (json.JSONDecodeError, TypeError):
            return None

    parsed = _try(raw)
    if parsed is not None:
        return parsed, repair_tokens

    # Cleanup pass 1 — quotes + trailing commas + array carve-out
    cleaned = raw
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')  # curly double quotes
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")  # curly single quotes
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)                  # trailing commas
    # Carve out the outermost JSON array if there is leading/trailing prose
    m = re.search(r'\[[\s\S]*\]', cleaned)
    if m:
        cleaned = m.group(0)

    parsed = _try(cleaned)
    if parsed is not None:
        return parsed, repair_tokens

    # One-shot model-driven repair
    print(f"  ⚠ JSON parse failed for {category} — invoking repair pass...")
    repair_prompt = (
        "The following text was supposed to be a JSON array of KRI objects but failed to parse. "
        "Return ONLY a corrected JSON array with the same content (start with [ and end with ]). "
        "Do not add or remove any KRI; only fix syntax issues (unescaped quotes, trailing commas, malformed strings). "
        "No markdown fences, no prose, no explanation.\n\n"
        f"BROKEN JSON:\n{raw[:60000]}"
    )
    try:
        rsp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": repair_prompt}],
            system="You repair JSON. You return only valid JSON arrays — nothing else.",
        )
        repair_text = rsp.content[0].text.strip()
        repair_text = re.sub(r'^```[a-z]*\n?', '', repair_text)
        repair_text = re.sub(r'\n?```$', '', repair_text)
        repair_tokens = rsp.usage.input_tokens + rsp.usage.output_tokens
        parsed = _try(repair_text)
        if parsed is not None:
            return parsed, repair_tokens
    except Exception as e:
        print(f"  ⚠ Repair-pass call failed: {e}")

    # Last resort — log raw output so the user can fix manually, return empty
    if output_dir:
        debug_path = os.path.join(output_dir, f"_raw_{category}_unparseable.txt")
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  ⚠ Saved unparseable output to {debug_path}; returning 0 KRIs for {category}.")
        except Exception:
            pass
    return [], repair_tokens

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
    """
    out = []
    for k in kris or []:
        if not isinstance(k, dict):
            continue
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

        # agent_count — drives Step 2.6 tier classification.
        # Single-shot LLM extraction is not a real 10-agent panel; we set it to
        # 7 so the KRI lands in T1 (auto-keep) rather than T3 (auto-rejected).
        if "agent_count" not in k or not isinstance(k.get("agent_count"), int):
            k["agent_count"] = 7

        out.append(k)
    return out


def run_extraction(pdf_path: str, manifest_path: str,
                   output_dir: str, categories: list = None):
    with open(manifest_path) as f:
        manifest = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    cats = categories or ["ELIG", "SAF", "END", "OPS"]

    all_results = {}
    total_tokens = 0

    for cat in cats:
        print(f"\n--- {cat} ---")
        try:
            result = extract_category(pdf_path, manifest, cat, output_dir)
            if isinstance(result, tuple):
                kris, tokens = result
            else:
                kris, tokens = result, 0

            # Schema normalization — every KRI must have the SKILL.md output schema
            # plus agent_count for the Step 2.6 tier classifier.
            kris = _normalize_kris(kris, cat)

            all_results[cat] = kris
            total_tokens += tokens

            # Save per-category file
            out_path = os.path.join(output_dir, f"raw_{cat}.json")
            with open(out_path, "w") as f:
                json.dump({
                    "_meta": {"step": "2", "protocol_id": protocol_id,
                              "category": cat, "kri_count": len(kris),
                              "tokens_used": tokens},
                    "kris": kris
                }, f, indent=2)
            print(f"  Saved → {out_path}")

        except Exception as e:
            print(f"  ERROR in {cat}: {e}")
            import traceback; traceback.print_exc()

    print(f"\n{'='*40}")
    print(f"Extraction complete. Total KRIs: {sum(len(v) for v in all_results.values())}")
    print(f"Total tokens: {total_tokens}")
    for cat, kris in all_results.items():
        print(f"  {cat}: {len(kris)}")

    return all_results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 2 — Extract KRIs from protocol")
    parser.add_argument("--pdf",  required=True, help="Path to protocol PDF")
    parser.add_argument("--dir",  required=True, help="Output directory (must contain manifest.json)")
    parser.add_argument("--cats", default=None,  help="Comma-separated category list, e.g. ELIG,SAF (default: ELIG,SAF,END,OPS)")
    args = parser.parse_args()

    cats = args.cats.split(",") if args.cats else None
    print(f"\n{'='*55}")
    print(f"Extracting KRIs: {os.path.basename(args.pdf)}" + (f" (categories: {cats})" if cats else " (all in-scope categories)"))

    run_extraction(
        pdf_path=args.pdf,
        manifest_path=os.path.join(args.dir, "manifest.json"),
        output_dir=args.dir,
        categories=cats
    )
