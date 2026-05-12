"""
Step 1A — Protocol Manifest Builder
Reads cover pages + TOC from any clinical trial protocol PDF.
Produces manifest.json: protocol identity + section → domain category map.
Protocol-agnostic: works on any Phase 2/3 trial regardless of sponsor/format.
"""

import json, sys, re, os
import pdfplumber
import anthropic

# ─── In-scope domain categories (ICH GCP, minus SOA which is handled separately) ─
# Schedule of Activities (SOA) is OUT OF SCOPE for this skill — handled by
# the separate `soa-kri-extractor` skill. SoA sections in the protocol must be
# LEFT UNMAPPED (do not add an "SOA" key to section_map).
DOMAIN_CATEGORIES = {
    "ELIG": "Eligibility — inclusion criteria, exclusion criteria, randomization criteria",
    "SAF":  "Safety & Toxicity — AE/SAE reporting, stopping rules, toxicity management, safety monitoring",
    "END":  "Endpoints & Statistics — objectives, efficacy endpoints, analysis sets, statistical methods",
    "OPS":  "Operations & Compliance — IMP handling, blinding, records retention, regulatory, GCP compliance",
}

SYSTEM_PROMPT = """You are a clinical trial protocol expert. 
You read protocol documents and extract structured information accurately.
You always return valid JSON with no markdown fences, no prose, no extra text."""

def extract_pages_text(pdf_path: str, page_nums: list[int]) -> str:
    """Extract text from specific pages, joined with page markers."""
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        parts = []
        for n in page_nums:
            if 1 <= n <= total:
                text = pdf.pages[n-1].extract_text() or ""
                parts.append(f"[PAGE {n}]\n{text}")
    return "\n\n".join(parts)

def find_toc_pages(pdf_path: str) -> list[int]:
    """Locate TOC pages — search first 40 pages for STRONG TOC markers.

    Strong markers (any one is decisive):
      - The literal phrase 'Table of Contents' on the page
      - Lines with dot-leaders followed by a page number (e.g. "5.7 Missed Visits ......... 50")
        — characteristic of a real TOC, almost never present in body content

    Falls back to the previous weaker heuristic (numbered-section lines) only if
    no strong-marker pages are found, to remain compatible with older protocols
    whose TOC lacks dot leaders. The fallback was the original behavior — kept
    as a safety net so we never lose functionality on protocols where the new
    heuristic produces no candidates.
    """
    DOT_LEADER = re.compile(r'\.{4,}\s*\d{1,3}\s*$')
    NUM_HEADING = re.compile(r'^\d[\d.]*\s+\w')
    with pdfplumber.open(pdf_path) as pdf:
        n = min(40, len(pdf.pages))
        strong = []
        weak = []
        for i in range(n):
            text = pdf.pages[i].extract_text() or ""
            text_lower = text.lower()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            dot_lines = [l for l in lines if DOT_LEADER.search(l)]
            has_toc_phrase = "table of contents" in text_lower
            if has_toc_phrase or len(dot_lines) >= 3:
                strong.append(i + 1)
                continue
            num_lines = [l for l in lines if NUM_HEADING.match(l) and ('.' in l or re.search(r'\d{1,3}$', l))]
            if len(num_lines) >= 5:
                weak.append(i + 1)

    candidates = strong if strong else weak
    if not candidates:
        return []
    result = [candidates[0]]
    for p in candidates[1:]:
        if p - result[-1] <= 2:
            result.append(p)
        if len(result) >= 6:
            break
    return result

def build_manifest(pdf_path: str, protocol_id: str) -> dict:
    client = anthropic.Anthropic()
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
    
    print(f"  PDF: {total_pages} pages")
    
    # Cover pages (1-3) + TOC pages
    toc_pages = find_toc_pages(pdf_path)
    cover_pages = list(range(1, min(4, total_pages + 1)))
    all_pages = sorted(set(cover_pages + toc_pages))
    print(f"  Reading pages: {all_pages} (cover + TOC at {toc_pages})")
    
    input_text = extract_pages_text(pdf_path, all_pages)
    
    user_prompt = f"""Read the following pages from a clinical trial protocol PDF and extract the manifest.

PROTOCOL FILE: {os.path.basename(pdf_path)}

--- PROTOCOL PAGES ---
{input_text}
--- END PAGES ---

Extract and return a JSON object with this exact structure:

{{
  "protocol_id": "exact protocol number as shown on cover page",
  "study_name": "short study name or acronym if available, else null",
  "sponsor": "sponsor organization name",
  "compound": "investigational product name",
  "indication": "therapeutic indication in 5 words or fewer",
  "phase": "e.g. IIb, III, II/III",
  "therapeutic_area": "one of: cardiovascular, oncology, immunology, neurology, endocrinology, respiratory, musculoskeletal, infectious_disease, other",
  "total_pages": {total_pages},
  "toc_pages": {toc_pages},
  "section_map": {{
    "ELIG": [],
    "SAF":  [],
    "END":  [],
    "OPS":  []
  }}
}}

OUT OF SCOPE — DO NOT MAP: Schedule-of-Activities (SoA) sections — the SoA
table itself, its footnote pages, the visit-schedule narrative, and any section
primarily about "procedure × visit" rules or visit windows. These are handled
by the separate `soa-kri-extractor` skill. Leave them entirely out of
section_map. Do NOT add an "SOA" key. Do NOT reclassify them under ELIG/SAF/
END/OPS — just omit them.

For section_map, scan the TOC carefully and assign every IN-SCOPE section to
its primary domain. The 4 in-scope domain categories and what they cover:
{json.dumps(DOMAIN_CATEGORIES, indent=2)}

Each section entry must have:
{{
  "section_number": "e.g. 3, 8.1, 6.4",
  "title": "section title as it appears in TOC",
  "pages_approx": [start_page, end_page],
  "notes": "brief note if section only partially covers this domain, else null"
}}

Rules:
- A section can appear in at most one category (its PRIMARY domain)
- Appendices go in their primary domain  
- If a section has no relevant domain, omit it entirely
- pages_approx: estimate from TOC page numbers shown; use [null, null] if not visible
- Return ONLY the JSON object, no prose, no markdown"""

    print(f"  Calling Claude for manifest...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        system=SYSTEM_PROMPT
    )
    
    raw = response.content[0].text.strip()
    # Strip any accidental markdown fences
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    
    manifest = json.loads(raw)
    manifest["_meta"] = {
        "step": "1A",
        "source_pdf": os.path.basename(pdf_path),
        "input_pages": all_pages,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens
    }
    return manifest

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 1A — Build protocol manifest")
    parser.add_argument("--pdf",      required=True, help="Path to protocol PDF")
    parser.add_argument("--protocol", required=True, help="Protocol ID (e.g. B1481038)")
    parser.add_argument("--out",      required=True, help="Output path for manifest.json")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"Building manifest: {args.protocol}")
    try:
        manifest = build_manifest(args.pdf, args.protocol)
        with open(args.out, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  Saved → {args.out}")
        total_sections = sum(len(v) for v in manifest["section_map"].values())
        print(f"  Sections mapped: {total_sections}")
        for cat, sections in manifest["section_map"].items():
            if sections:
                titles = [s["section_number"] + " " + s["title"][:35] for s in sections]
                print(f"    {cat}: {titles}")
        print(f"  Tokens: {manifest['_meta']['tokens_used']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
