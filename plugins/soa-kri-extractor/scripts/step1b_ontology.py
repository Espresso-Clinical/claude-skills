"""
Step 1B — SoA Ontology Builder
Reads the Schedule of Activities (or equivalent) table from any clinical trial
protocol PDF. Produces ontology.json: visits, procedures, footnotes, marker legend.
Protocol-agnostic — no assumptions about visit names, procedure names, or format.
"""

import json, sys, re, os
import pdfplumber
import anthropic

SYSTEM_PROMPT = """You are a clinical trial protocol expert who reads Schedule of Activities tables.
You extract information with precision — every visit, every procedure row, every footnote verbatim.
You always return valid JSON with no markdown fences, no prose, no extra text."""

def extract_pages_text(pdf_path: str, page_nums: list[int]) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        parts = []
        for n in page_nums:
            if 1 <= n <= total:
                text = pdf.pages[n-1].extract_text() or ""
                parts.append(f"[PAGE {n}]\n{text}")
    return "\n\n".join(parts)

def get_soa_pages(manifest: dict) -> list[int]:
    """Get SoA page range from manifest, plus a buffer for footnotes."""
    soa_sections = manifest.get("section_map", {}).get("SOA", [])
    pages = set()
    for s in soa_sections:
        pa = s.get("pages_approx") or [None, None]
        start, end = pa[0], pa[1]
        if start and end:
            for p in range(int(start), int(end) + 1):
                pages.add(p)
        elif start:
            # Add buffer pages after start for footnotes
            for p in range(int(start), int(start) + 8):
                pages.add(p)
    return sorted(pages) if pages else []

def build_ontology(pdf_path: str, manifest: dict) -> dict:
    client = anthropic.Anthropic()

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    soa_pages = get_soa_pages(manifest)
    if not soa_pages:
        raise ValueError("No SOA pages found in manifest — run Step 1A first")

    print(f"  Reading SoA pages: {soa_pages}")
    input_text = extract_pages_text(pdf_path, soa_pages)

    user_prompt = f"""Read the following pages from a clinical trial protocol. 
They contain the Schedule of Activities (also called: Visit Schedule, Assessment Schedule, 
Schedule of Events, or equivalent) — a matrix where rows are procedures and columns are visits.

--- PROTOCOL PAGES ---
{input_text}
--- END PAGES ---

Extract the complete SoA structure. Return a JSON object with this exact schema:

{{
  "soa_section_title": "exact title as it appears in the document",
  "marker_legend": {{
    "X": "meaning of X marker (e.g. required, recorded in database)",
    "S": "meaning of S marker if present, else null",
    "other_markers": {{}}
  }},
  "epochs": ["list of epoch names in order, e.g. Screening, Treatment, Follow-up"],
  "visits": [
    {{
      "visit_id": "short stable ID you assign, e.g. V_SCREEN, V_BASELINE, V_W4",
      "original_label": "exact label from table header, e.g. S-I, Visit 5, Week 4",
      "epoch": "screening|treatment|follow_up|end_of_study|unscheduled",
      "day_reference": "day/week/month number from header row, e.g. Day 0, Week 4, null if absent",
      "window": "visit window if shown, e.g. ±3 days, Day -45 to 0, null if absent",
      "is_treatment_day": true/false
    }}
  ],
  "procedures": [
    {{
      "procedure_id": "short stable ID you assign, e.g. PROC_VITALS, PROC_SAFETY_LABS",
      "canonical_name": "your normalized procedure name, concise and descriptive",
      "original_label": "exact label from table row",
      "category": "one of: consent_eligibility, demographics_history, physical_assessment, 
                   laboratory, imaging, questionnaire_pro, intervention, safety_monitoring, 
                   concomitant_therapy, administrative, biomarker, other",
      "required_at": ["visit_id list where marker = required (X or equivalent)"],
      "source_only_at": ["visit_id list where marker = source doc only (S or equivalent)"],
      "not_applicable_at": [],
      "footnote_numbers": ["list of footnote numbers that apply to this row, as strings"]
    }}
  ],
  "footnotes": {{
    "1": "verbatim footnote text",
    "2": "verbatim footnote text"
  }},
  "cross_visit_rules": [
    "any general rules stated in the SoA section header/text that apply across multiple visits"
  ]
}}

Critical rules:
- Do NOT invent visits or procedures — only extract what is actually in the table
- Use your own visit_id and procedure_id values (stable, snake_case, no spaces)
- required_at / source_only_at must reference visit_id values you defined above
- footnotes: include FULL verbatim text of every footnote number, not truncated
- If a procedure row spans sub-rows (e.g. "Laboratory / Chemistry Group / Hematology"), 
  create one entry per meaningful row — do not flatten or skip sub-rows
- cross_visit_rules: capture any timing rules, washout requirements, or sequencing 
  rules mentioned in the SoA section text (not just the table)
- Return ONLY the JSON object"""

    print(f"  Calling Claude for ontology ({len(soa_pages)} pages)...")
    max_tokens = 16000
    last_err = None
    response = None
    ontology = None
    for attempt in range(3):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user_prompt}],
            system=SYSTEM_PROMPT,
            timeout=180.0,
        )
        if response.stop_reason == "max_tokens":
            print(f"  ⚠ ontology output hit max_tokens={max_tokens}; retrying with double cap")
            max_tokens = min(max_tokens * 2, 32000)
            last_err = "max_tokens truncation"
            continue
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        try:
            ontology = json.loads(raw)
            break
        except json.JSONDecodeError as e:
            last_err = f"JSONDecodeError: {e}"
            print(f"  ⚠ ontology JSON parse failed (attempt {attempt+1}/3): {e}")
            continue
    if ontology is None:
        raise RuntimeError(f"build_ontology failed after 3 attempts — {last_err}")
    ontology["_meta"] = {
        "step": "1B",
        "protocol_id": manifest.get("protocol_id"),
        "source_pdf": os.path.basename(pdf_path),
        "soa_pages_read": soa_pages,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens
    }
    return ontology

def print_summary(ontology: dict):
    visits = ontology.get("visits", [])
    procs = ontology.get("procedures", [])
    footnotes = ontology.get("footnotes", {})
    epochs = ontology.get("epochs", [])

    print(f"  Epochs: {epochs}")
    print(f"  Visits: {len(visits)}")
    for v in visits:
        marker = "🩺" if v.get("is_treatment_day") else "  "
        print(f"    {marker} {v['visit_id']:<18} {v['original_label']:<12} [{v['epoch']}] {v.get('day_reference') or ''}")

    print(f"\n  Procedures: {len(procs)}")
    cat_counts = {}
    for p in procs:
        cat = p.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:<30} {n}")

    print(f"\n  Footnotes: {len(footnotes)}")
    cross = ontology.get("cross_visit_rules", [])
    print(f"  Cross-visit rules: {len(cross)}")
    if cross:
        for r in cross[:3]:
            print(f"    - {r[:90]}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 1B — Build protocol ontology")
    parser.add_argument("--pdf",      required=True, help="Path to protocol PDF")
    parser.add_argument("--manifest", required=True, help="Path to manifest.json from Step 1A")
    parser.add_argument("--out",      required=True, help="Output path for ontology.json")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"Building ontology from: {os.path.basename(args.pdf)}")
    if not os.path.exists(args.manifest):
        print(f"  ERROR: manifest not found at {args.manifest} — run step1a first")
        sys.exit(1)
    with open(args.manifest) as f:
        manifest = json.load(f)
    try:
        ontology = build_ontology(args.pdf, manifest)
        with open(args.out, "w") as f:
            json.dump(ontology, f, indent=2)
        print(f"  Saved → {args.out}")
        print_summary(ontology)
        print(f"  Tokens: {ontology['_meta']['tokens_used']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
