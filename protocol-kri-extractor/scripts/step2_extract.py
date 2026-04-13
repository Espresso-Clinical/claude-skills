"""
Step 2 — Per-Section KRI Extraction
Extracts KRIs from each protocol section identified in the manifest.
One LLM call per section group (batched by domain category).
Produces raw_SOA.json, raw_ELIG.json, raw_SAF.json, raw_END.json, raw_OPS.json.
Protocol-agnostic — driven entirely by manifest + ontology.
"""

import json, sys, re, os
import pdfplumber
import anthropic

SYSTEM_PROMPT = """You are a clinical research associate (CRA) and protocol expert.
You read clinical trial protocol sections and extract monitoring rules as KRIs 
(Key Risk Indicators) — actionable verification instructions for site monitoring.
You always return valid JSON arrays. No markdown fences, no prose."""

KRI_SCHEMA = """Each KRI must have exactly these fields:
{
  "kri_id": "CATEGORY-SUBCATEGORY-NNN  e.g. SOA-V1-001, ELIG-INC-001, SAF-AE-001, END-PRI-001, OPS-IMP-001",
  "kri_name": "Short name, max 8 words, starts with visit code for SOA e.g. V1- IMP administration",
  "description": "1-2 sentences: what protocol requirement this monitors and why it matters",
  "category_id": "SOA|ELIG|SAF|END|OPS",
  "category_label": "full category name",
  "rule_for_llm": "Actionable CRA instruction starting with visit prefix for SOA (e.g. V1-, S2-, All visits-) or Verify that... for other categories. Be specific: include exact drug names, thresholds, timeframes, data sources (e.g. 'by checking medication logs'), and clinical conditions verbatim from the protocol.",
  "protocol_reference": "Section X.X, Page N: \"verbatim quote ≤30 words from protocol\"",
  "additional_footnotes": "Footnote N: verbatim text — or null if none"
}"""

CATEGORY_CONFIGS = {
    "SOA": {
        "label": "Schedule of Activities",
        "id_prefix": "SOA",
        "subcategories": {
            "screening": "S1, S2 visits",
            "treatment": "V1, V2, V3 (or equivalent treatment visits)",
            "followup": "Follow-up and EOS visits",
            "unscheduled": "Unscheduled visits",
            "cross_visit": "Rules spanning multiple visits"
        },
        "instructions": """Extract one KRI per procedure per visit where that procedure is required.
- For every row in the SoA table that has an X (or equivalent marker) at a visit, create a KRI
- rule_for_llm MUST start with the visit prefix: "V1-", "S1-", "V4-", "All visits-", etc.
- Include visit window/timing in check-in KRIs (e.g. 'within 90 ± 7 days')
- For treatment visits: vital signs measured twice (pre and post injection)
- Include ALL footnote details that apply to the procedure × visit combination
- Washout KRIs: always say "by checking medication logs and visit timestamps"
- Lab KRIs: include all specific analytes named in the footnote (do not generalize)
- Be faithful to the protocol: use exact drug names, doses, timing windows as written"""
    },
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

def extract_category(pdf_path: str, manifest: dict, ontology: dict,
                     category: str, output_dir: str) -> list[dict]:
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

    # For large SOA, split into batches by visit group
    # For others, extract in one call (or two if > 20 pages)
    if category == "SOA" and len(pages) > 12:
        return extract_soa_batched(client, pdf_path, manifest, ontology, pages, output_dir)
    else:
        return extract_single_call(client, pdf_path, manifest, ontology,
                                   category, cfg, pages, output_dir)

def extract_single_call(client, pdf_path, manifest, ontology,
                        category, cfg, pages, output_dir) -> list[dict]:
    protocol_text = extract_pages_text(pdf_path, pages)
    protocol_id = manifest.get("protocol_id", "UNKNOWN")

    # Build ontology context (visits + procedure list relevant to this category)
    visits_context = json.dumps(ontology.get("visits", []), indent=2)
    footnotes_context = json.dumps(ontology.get("footnotes", {}), indent=2)

    section_list = "\n".join(
        f"  - Section {s['section_number']}: {s['title']}"
        for s in manifest.get("section_map", {}).get(category, [])
    )

    prompt = f"""You are extracting KRIs (Key Risk Indicators) from a clinical trial protocol.

PROTOCOL: {protocol_id}
CATEGORY: {category} — {cfg['label']}
SECTIONS TO COVER:
{section_list}

VISIT REFERENCE (from SoA ontology):
{visits_context}

FOOTNOTES REFERENCE:
{footnotes_context}

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

    kris = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens
    print(f"  → {len(kris)} KRIs extracted ({tokens} tokens)")
    return kris, tokens

def extract_soa_batched(client, pdf_path, manifest, ontology, all_pages, output_dir) -> tuple:
    """Split SOA extraction into visit group batches."""
    visits = ontology.get("visits", [])
    cfg = CATEGORY_CONFIGS["SOA"]
    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    footnotes_context = json.dumps(ontology.get("footnotes", {}), indent=2)

    # Group visits by epoch
    epoch_groups = {}
    for v in visits:
        epoch = v.get("epoch", "other")
        epoch_groups.setdefault(epoch, []).append(v)

    all_kris = []
    total_tokens = 0
    counter = {"SOA": 0}

    for epoch, epoch_visits in epoch_groups.items():
        visit_ids = [v["visit_id"] for v in epoch_visits]
        visits_json = json.dumps(epoch_visits, indent=2)

        # Get relevant pages for this epoch (use full set — we can't slice by visit)
        batch_pages = all_pages

        protocol_text = extract_pages_text(pdf_path, batch_pages)

        prompt = f"""You are extracting Schedule of Activities (SOA) KRIs for the {epoch.upper()} epoch.

PROTOCOL: {protocol_id}
EPOCH: {epoch}
VISITS IN THIS BATCH: {visit_ids}

VISITS DETAIL:
{visits_json}

FOOTNOTES:
{footnotes_context}

EXTRACTION INSTRUCTIONS:
{cfg['instructions']}

KRI SCHEMA:
{KRI_SCHEMA}

ID FORMAT: SOA-[VISIT_CODE]-[NNN]
Examples: SOA-S1-001, SOA-V1-001, SOA-V4-001, SOA-UNS-001, SOA-CROSS-001
For cross-visit rules use: SOA-CROSS-NNN

SCOPE: Extract KRIs ONLY for visits in this batch: {visit_ids}
Also extract cross-visit rules that apply to these visits.

--- PROTOCOL TEXT ---
{protocol_text}
--- END ---

Return ONLY a JSON array of KRI objects for this epoch's visits."""

        print(f"  Calling Claude for SOA epoch={epoch} visits={visit_ids}...")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        batch_kris = json.loads(raw)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        total_tokens += tokens
        all_kris.extend(batch_kris)
        print(f"    → {len(batch_kris)} KRIs ({tokens} tokens)")

    return all_kris, total_tokens

def run_extraction(pdf_path: str, manifest_path: str, ontology_path: str,
                   output_dir: str, categories: list = None):
    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(ontology_path) as f:
        ontology = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    cats = categories or ["SOA", "ELIG", "SAF", "END", "OPS"]

    all_results = {}
    total_tokens = 0

    for cat in cats:
        print(f"\n--- {cat} ---")
        try:
            result = extract_category(pdf_path, manifest, ontology, cat, output_dir)
            if isinstance(result, tuple):
                kris, tokens = result
            else:
                kris, tokens = result, 0
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
    PROTOCOLS = {
        "ENX-CL-05-002": {
            "pdf": "/mnt/user-data/uploads/ENX-CL-05-002_Clinical_Study_Protocol_v_2_0_Agatha_copy.pdf",
            "dir": "/home/claude/protocol-kri-extractor/output/ENX-CL-05-002"
        },
        "B1481038": {
            "pdf": "/mnt/user-data/uploads/Protocol_B1481038.pdf",
            "dir": "/home/claude/protocol-kri-extractor/output/B1481038"
        },
        "LCZ696G2301": {
            "pdf": "/mnt/user-data/uploads/Novartis__LCZ696G2301-_Phase_3_study_to_evaluate_the_efficacy_and_safety_of_LCZ696pdf.pdf",
            "dir": "/home/claude/protocol-kri-extractor/output/LCZ696G2301"
        }
    }

    target = sys.argv[1] if len(sys.argv) > 1 else "ENX-CL-05-002"
    cats = sys.argv[2].split(",") if len(sys.argv) > 2 else None  # e.g. "SOA,ELIG"

    if target not in PROTOCOLS:
        print(f"Unknown protocol. Choose from: {list(PROTOCOLS.keys())}")
        sys.exit(1)

    p = PROTOCOLS[target]
    print(f"\n{'='*55}")
    print(f"Extracting KRIs: {target}" + (f" (categories: {cats})" if cats else " (all categories)"))

    run_extraction(
        pdf_path=p["pdf"],
        manifest_path=os.path.join(p["dir"], "manifest.json"),
        ontology_path=os.path.join(p["dir"], "ontology.json"),
        output_dir=p["dir"],
        categories=cats
    )
