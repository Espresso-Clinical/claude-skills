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

IN_SCOPE_DOMAINS = ("ELIG", "SAF", "END", "OPS")
DOT_LEADER_RE = re.compile(r'\.{4,}\s*\d{1,3}\s*$')


def _derive_section_map(inventory: list) -> dict:
    """Build the per-domain section_map from the complete section_inventory.

    Only entries whose disposition is one of the 4 in-scope domains are mapped;
    out_of_scope_soa and non_substantive sections are intentionally NOT mapped
    (so no extractor reads them) but they remain in section_inventory for the
    completeness gate to audit. Keeps section_map and section_inventory in sync.
    """
    section_map = {d: [] for d in IN_SCOPE_DOMAINS}
    for s in inventory or []:
        disp = (s.get("disposition") or "").strip().upper()
        if disp in section_map:
            section_map[disp].append({
                "section_number": s.get("section_number"),
                "title": s.get("title"),
                "pages_approx": s.get("pages_approx"),
                "notes": s.get("notes"),
            })
    return section_map


def _inventory_from_legacy_map(section_map: dict) -> list:
    """Back-compat: if the model returned only a legacy section_map (no
    section_inventory), synthesize an inventory so downstream steps still work."""
    inv = []
    for dom, secs in (section_map or {}).items():
        for s in (secs or []):
            entry = dict(s)
            entry["disposition"] = dom
            entry.setdefault("confidence", "high")
            inv.append(entry)
    return inv


def _find_heading_page(page_texts: dict, num: str, title: str, skip_pages: set):
    """First PDF page whose body has a line that starts with the section number
    and contains the first significant word of the title. Skips the cover/TOC
    pages and any dot-leader (TOC) lines so we land on the body heading, not the
    table of contents. Returns a page number or None.
    """
    title_words = re.findall(r"[A-Za-z]{3,}", title or "")
    first_word = title_words[0].lower() if title_words else ""
    num_re = re.compile(rf"^\s*{re.escape(str(num))}(?:\.|\s|$)")
    for pg in sorted(page_texts):
        if pg in skip_pages:
            continue
        for line in page_texts[pg].split("\n"):
            l = line.strip()
            if not l or DOT_LEADER_RE.search(l):
                continue
            if num_re.match(l) and (not first_word or first_word in l.lower()):
                return pg
    return None


def _validate_section_pages(pdf_path: str, inventory: list, total_pages: int,
                            skip_pages: set):
    """Confirm/correct each section's page range against the actual PDF text.

    1. Detect each section's true start page by locating its heading in the body.
    2. Make detected ranges CONTIGUOUS — a section ends where the next-starting
       section begins — so a short/wrong TOC page estimate can never cause an
       in-scope section's pages to be silently skipped by the extractor.
    Sections whose heading cannot be located keep their LLM-estimated range
    (never worse than before). Mutates inventory entries in place.
    """
    if not inventory:
        return
    page_texts = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(len(pdf.pages)):
            page_texts[i + 1] = pdf.pages[i].extract_text() or ""

    for s in inventory:
        num = str(s.get("section_number") or "").strip()
        if not num:
            continue
        start = _find_heading_page(page_texts, num, s.get("title") or "", skip_pages)
        if start:
            s["_detected_start"] = start

    detected = sorted(
        (s for s in inventory if s.get("_detected_start")),
        key=lambda x: x["_detected_start"],
    )
    for idx, s in enumerate(detected):
        start = s["_detected_start"]
        if idx + 1 < len(detected):
            end = max(start, detected[idx + 1]["_detected_start"])
        else:
            end = total_pages
        s["pages_approx"] = [start, end]

    for s in inventory:
        s.pop("_detected_start", None)


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
  "section_inventory": [
    {{
      "section_number": "e.g. 3, 8.1, 12",
      "title": "section title exactly as it appears in the TOC",
      "pages_approx": [start_page, end_page],
      "disposition": "ELIG | SAF | END | OPS | out_of_scope_soa | non_substantive",
      "confidence": "high | low",
      "notes": "for low confidence or partial/multi-domain coverage, explain; else null"
    }}
  ]
}}

COMPLETENESS IS MANDATORY — NEVER OMIT A SECTION:
- Every numbered section, sub-section, and appendix listed in the TOC MUST appear
  exactly once in section_inventory. Skipping any section is the single most
  serious error you can make. Every entry MUST carry a disposition — there is no
  "drop it" option.

DISPOSITION RULES:
- ELIG / SAF / END / OPS — the in-scope domains. Assign the single best-fit one.
  The 4 in-scope domains and what they cover:
{json.dumps(DOMAIN_CATEGORIES, indent=2)}
- out_of_scope_soa — use ONLY for Schedule-of-Activities content: the SoA table,
  its footnote pages, the visit-schedule narrative, and sections primarily about
  "procedure × visit" rules or visit windows. (Handled by a separate skill — but
  it still MUST be listed in the inventory with this disposition, never omitted.)
- non_substantive — use ONLY for sections that genuinely contain NO rule-like
  content: title page, table of contents, list of abbreviations/glossary,
  references/bibliography, signature page. When in any doubt, do NOT use this —
  pick a domain instead.

BEST-FIT, NOT PERFECT-FIT:
- If a section spans multiple domains or is ambiguous, STILL pick the single
  closest in-scope domain and set "confidence": "low" with a note. Never drop it,
  and never hide a content-bearing section under non_substantive to avoid choosing.
- Conduct-governing sections are ALWAYS in-scope (never non_substantive). Examples:
  concomitant / prior therapy, permitted & prohibited medications, dose
  modification, treatment discontinuation / withdrawal, informed consent,
  protocol-deviation handling, blinding / unblinding. These are typically SAF or OPS.

PAGES:
- pages_approx: estimate [start_page, end_page] from the TOC page numbers. When an
  explicit end is not shown, use the next section's start page as this section's end.
  Use [null, null] only if no page number is visible at all.

Return ONLY the JSON object, no prose, no markdown."""

    print(f"  Calling Claude for manifest...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
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

    # ── Coverage-complete handling (Fix #1) ──────────────────────────────────
    # The model returns a COMPLETE section_inventory (every TOC section + a
    # disposition). We (a) validate each section's page range against the actual
    # PDF so a mapped section can't be under-paged, and (b) derive the per-domain
    # section_map deterministically from the inventory so the two never drift.
    inventory = manifest.get("section_inventory")
    if inventory is None:
        # Legacy fallback: synthesize an inventory from a returned section_map so
        # the rest of the pipeline (and Fix #2's gate) still has the inventory.
        inventory = _inventory_from_legacy_map(manifest.get("section_map", {}))
        manifest["section_inventory"] = inventory

    _validate_section_pages(pdf_path, inventory, total_pages, skip_pages=set(all_pages))
    manifest["section_map"] = _derive_section_map(inventory)

    manifest["_meta"] = {
        "step": "1A",
        "source_pdf": os.path.basename(pdf_path),
        "input_pages": all_pages,
        "section_count": len(inventory),
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
        from collections import Counter
        inv = manifest.get("section_inventory", [])
        disp_counts = Counter((s.get("disposition") or "?").strip().upper() for s in inv)
        print(f"  Section inventory: {len(inv)} sections — {dict(disp_counts)}")
        low_conf = [s for s in inv if (s.get("confidence") or "").lower() == "low"]
        if low_conf:
            print(f"  Low-confidence (forced best-fit) sections: {len(low_conf)}")
            for s in low_conf:
                print(f"    §{s.get('section_number')} {(s.get('title') or '')[:35]} → {s.get('disposition')}")
        total_sections = sum(len(v) for v in manifest["section_map"].values())
        print(f"  Sections mapped to domains: {total_sections}")
        for cat, sections in manifest["section_map"].items():
            if sections:
                titles = [str(s.get("section_number")) + " " + (s.get("title") or "")[:35] for s in sections]
                print(f"    {cat}: {titles}")
        print(f"  Tokens: {manifest['_meta']['tokens_used']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
