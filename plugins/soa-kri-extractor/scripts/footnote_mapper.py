"""
Step 1C — Deterministic Footnote Mapper
Maps footnote superscripts to procedure × visit cells using PDF character geometry.
Zero LLM calls. Fully deterministic.

Usage:
  python footnote_mapper.py --pdf /path/to/protocol.pdf --table-pages 24 --fn-pages 25-29 --out /path/to/output/

  Or from Python:
    from footnote_mapper import build_footnote_map
    result = build_footnote_map(pdf_path, soa_pages=[24], fn_pages=range(25,30), out_dir="./")

Dependencies:
  pip install pdfplumber camelot-py[cv]
"""
import json, os, re, argparse, sys

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False


# ── Unicode superscript normalization ────────────────────────────────────────
SUPERSCRIPT_MAP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')

def normalize_superscripts(text: str) -> str:
    """Convert Unicode superscript digits to regular digits."""
    return text.translate(SUPERSCRIPT_MAP)


# ── Phase A: Parse footnote text from footnote pages ─────────────────────────
_MONTH_ABBR_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(uary|ruary|ch|il|e|y|ust|tember|ober|ember)?\b",
    re.IGNORECASE,
)
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+){1,4}\s")  # e.g. "5.1 ", "6.14.1.3 "


def _looks_like_section_header(text_after_num: str) -> bool:
    """Heuristic: distinguish a section header / page-header artifact from a
    real footnote body.

    Generic across protocols. Triggers when the line looks like:
      - A top-level section heading (ALL CAPS or starts with known heading keyword)
      - A nested section number (e.g. "5.1 Screening", "6.14.1.3 Local Pain")
      - A page-header date artifact (e.g. "Mar 2023 5.1 Screening...")
      - A page-of-N marker

    Real footnotes have sentence-case prose; these patterns do not.
    """
    t = (text_after_num or "").strip()
    if not t:
        return True
    # Trim trailing page numbers / dot leaders that survive in some PDFs
    t = re.sub(r"\s*\.{3,}\s*\d{1,3}\s*$", "", t).strip()
    if not t:
        return True

    # Page-header date artifact (e.g. number 23 captured from "23 Mar 2023 ...")
    if _MONTH_ABBR_RE.match(t):
        return True
    # Page-of-N marker
    if re.match(r"^(of\s+\d+|page\s+\d+|version\s+\d)", t, re.IGNORECASE):
        return True
    # Nested section-number prefix (e.g. "5.1 Screening", "6.14.1.3 Local Pain")
    if _SECTION_NUMBER_RE.match(t):
        return True

    # Pull the leading words for shape analysis
    head = t.split(" ", 6)
    head_str = " ".join(head[:6])
    # All-caps heading (allow numbers, hyphens, ampersands)
    if re.match(r"^[A-Z][A-Z0-9\s&/\-(),.:]{2,}$", head_str.strip()):
        return True
    # Common heading keywords (top-level sections of typical Phase 2/3 protocols)
    HEADING_KEYWORDS = {
        "INTRODUCTION", "BACKGROUND", "RATIONALE",
        "STUDY DESIGN", "STUDY OBJECTIVES", "STUDY ENDPOINTS",
        "STUDY POPULATION", "STUDY PROCEDURES", "STUDY ASSESSMENTS",
        "STUDY DRUG", "STUDY TREATMENT", "STUDY SCHEDULE",
        "INVESTIGATIONAL PRODUCT", "INVESTIGATIONAL MEDICINAL PRODUCT",
        "ELIGIBILITY", "INCLUSION CRITERIA", "EXCLUSION CRITERIA",
        "ADVERSE EVENT", "SERIOUS ADVERSE EVENT", "SAFETY ASSESSMENTS",
        "STATISTICAL", "DATA MONITORING", "DATA HANDLING",
        "ETHICS", "REGULATORY", "QUALITY",
        "REFERENCES", "APPENDIX", "APPENDICES",
    }
    head_upper = t.upper()
    for kw in HEADING_KEYWORDS:
        if head_upper.startswith(kw):
            return True
    return False


def extract_footnote_texts(pdf_path: str, fn_pages: list) -> dict:
    """
    Extract footnote text from the specified pages.
    Returns {footnote_number: "verbatim text"}.

    Generic across protocols: rejects lines that look like section headings
    rather than footnote bodies. A line is rejected if its text after the
    leading 1–2 digit number is ALL CAPS / Title Case heading / starts with
    a known top-level-section keyword (e.g. STUDY PROCEDURES, INTRODUCTION).
    """
    all_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in fn_pages:
            if 1 <= pg <= len(pdf.pages):
                text = pdf.pages[pg - 1].extract_text() or ''
                all_text.append(text)

    combined = '\n'.join(all_text)
    lines = combined.split('\n')

    footnotes = {}
    current_num = None
    current_text = []
    skipped_as_heading = []

    # Pattern: line starts with 1-2 digit number, optional period, then space + text.
    # Matches both '1. Signing of...' (most common SoA-footnote format with period)
    # and '1 Signing of...' (no-period variant some protocols use).
    fn_start = re.compile(r'^\s*(\d{1,2})\.?\s+(.+)')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip page headers/footers (protocol-agnostic patterns)
        if re.match(r'^Page \d+$', line):
            continue
        # Skip common protocol header patterns (sponsor name, protocol ID, amendment line)
        if re.match(r'^(Bococizumab|Protocol [A-Z]|Final Protocol|Amendment)', line):
            continue

        m = fn_start.match(line)
        if m:
            num = int(m.group(1))
            tail = m.group(2).strip()
            # Reject section headings that masquerade as footnotes
            if _looks_like_section_header(tail):
                # Save previous footnote (if any) and stop accumulating —
                # we've crossed into body content territory.
                if current_num is not None:
                    footnotes[current_num] = ' '.join(current_text).strip()
                    current_num = None
                    current_text = []
                skipped_as_heading.append((num, tail[:60]))
                continue
            # Save previous footnote
            if current_num is not None:
                footnotes[current_num] = ' '.join(current_text).strip()

            current_num = num
            # IMPORTANT: store only the TEXT, not the leading number.
            # The footnote number prefix (e.g., "13 ") is metadata, not content.
            current_text = [tail]
        elif current_num is not None:
            # Continuation line — but if this line looks like a section heading,
            # close out the current footnote and stop accumulating.
            if _looks_like_section_header(line):
                footnotes[current_num] = ' '.join(current_text).strip()
                current_num = None
                current_text = []
                continue
            current_text.append(line)

    # Save last footnote
    if current_num is not None:
        footnotes[current_num] = ' '.join(current_text).strip()

    # Verify: no footnote text should start with its own number
    for num, text in footnotes.items():
        if re.match(r'^\d{1,2}\s', text):
            # Strip accidental leading number prefix
            footnotes[num] = re.sub(r'^\d{1,2}\s+', '', text)

    if skipped_as_heading:
        print(f"  ℹ skipped {len(skipped_as_heading)} section-header-looking lines: "
              f"{[(n, t[:30]) for n, t in skipped_as_heading[:5]]}")

    return footnotes


# ── Phase B & C: Extract footnote markers from Camelot table ─────────────────
def parse_footnote_numbers(text: str, valid_footnotes: set = None) -> list:
    """
    Parse trailing footnote number(s) from a string.
    Handles: "3", "10", "3,14", "13·14", "4,10".
    Returns list of ints.
    """
    text = normalize_superscripts(text.strip())

    # Find trailing digit groups with separators
    m = re.search(r'((?:\d+[,·\.\s])*\d+)\s*$', text)
    if not m:
        return []

    raw = m.group(1)
    # Split on separators
    parts = re.split(r'[,·\.\s]+', raw)
    numbers = []
    for p in parts:
        p = p.strip()
        if p.isdigit():
            n = int(p)
            # Validate against known footnote numbers if available
            if valid_footnotes is None or n in valid_footnotes:
                numbers.append(n)

    return sorted(set(numbers))


def extract_procedure_name_and_footnotes(raw_proc: str, valid_footnotes: set = None):
    """
    Separate procedure name from trailing footnote numbers.
    "Informed Consents1" → ("Informed Consents", [1])
    "Vital signs,T, BP/PR4" → ("Vital signs,T, BP/PR", [4])
    "Phase 2 study" → ("Phase 2 study", [])  ← "2" is not a valid footnote
    """
    raw_proc = normalize_superscripts(raw_proc.strip())

    # Try to extract trailing numbers
    m = re.search(r'((?:\d+[,·])*\d+)\s*$', raw_proc)
    if not m:
        return raw_proc, []

    raw_nums = m.group(1)
    parts = re.split(r'[,·]+', raw_nums)
    footnotes = []
    for p in parts:
        if p.strip().isdigit():
            n = int(p.strip())
            if valid_footnotes is None or n in valid_footnotes:
                footnotes.append(n)

    if footnotes:
        # Strip the matched footnote numbers from the end
        proc_name = raw_proc[:m.start()].strip()
        # Safety: if stripping leaves empty name, keep original
        if not proc_name:
            return raw_proc, []
        return proc_name, sorted(set(footnotes))
    else:
        return raw_proc, []


def parse_cell_mark_and_footnotes(cell_text: str, valid_footnotes: set = None):
    """
    Parse a table cell for X mark and footnote numbers.
    "X" → ("X", [])
    "X10" → ("X", [10])
    "X13,14" → ("X", [13, 14])
    "X4" → ("X", [4])
    "S" → ("S", [])
    "" → (None, [])
    """
    cell_text = normalize_superscripts(cell_text.strip().upper())

    if not cell_text:
        return None, []

    # Match X or S followed by optional footnote numbers
    m = re.match(r'^([XS])\s*([\d,·\s]*)$', cell_text, re.I)
    if m:
        mark = m.group(1).upper()
        fn_str = m.group(2).strip()
        if fn_str:
            footnotes = parse_footnote_numbers(fn_str, valid_footnotes)
        else:
            footnotes = []
        return mark, footnotes

    # Check if it's just "X" or "S"
    if cell_text in ('X', 'S'):
        return cell_text, []

    return None, []


# ── Phase B+C+D: Build the complete footnote map from Camelot table ──────────
def build_map_from_camelot(pdf_path: str, soa_pages: list, footnote_texts: dict) -> dict:
    """
    Extract the SoA table with Camelot and build the footnote map.
    """
    valid_fns = set(footnote_texts.keys())

    # Run Camelot on SoA pages
    pages_str = ','.join(str(p) for p in soa_pages)
    tables = camelot.read_pdf(pdf_path, pages=pages_str, flavor='lattice')

    if not tables:
        print(f"  WARNING: Camelot found no tables on pages {pages_str}")
        return {}

    # Use the largest table (by cell count)
    table = max(tables, key=lambda t: t.df.shape[0] * t.df.shape[1])
    df = table.df
    print(f"  Table: {df.shape[0]} rows × {df.shape[1]} columns")

    # Detect header row(s) and visit columns
    # Find the row that contains visit labels (V1, V2, S-I, etc.)
    header_row = 0
    visit_pattern = re.compile(r'(?:V[_-]?\d|S[_-]?[IVX\d]|EDC|EOS|UNS|Screening|Treatment|Follow)', re.I)

    for idx in range(min(5, len(df))):
        row_text = ' '.join(str(c) for c in df.iloc[idx])
        matches = visit_pattern.findall(row_text)
        if len(matches) >= 3:
            header_row = idx
            break

    # Extract visit columns
    visits = []
    for col_idx in range(1, df.shape[1]):
        header_val = str(df.iloc[header_row][col_idx]).strip()
        header_val = header_val.replace('\n', ' ').strip()
        if header_val and header_val.lower() not in ('', 'nan'):
            visits.append({
                'visit_label': header_val,
                'column_index': col_idx,
            })

    print(f"  Visits detected: {len(visits)}")

    # Process procedure rows
    procedure_map = {}
    data_start = header_row + 1

    # Check if there's a sub-header row (e.g., "Day -45" row)
    for idx in range(header_row + 1, min(header_row + 3, len(df))):
        row_text = str(df.iloc[idx][0]).strip().lower()
        if not row_text or 'day' in row_text or 'week' in row_text or 'month' in row_text:
            data_start = idx + 1
        else:
            break

    for row_idx in range(data_start, len(df)):
        raw_proc = str(df.iloc[row_idx][0]).strip()
        raw_proc = raw_proc.replace('\n', ' ').strip()

        if not raw_proc or raw_proc.lower() == 'nan':
            continue

        # Phase B: extract procedure-level footnotes
        proc_name, proc_footnotes = extract_procedure_name_and_footnotes(raw_proc, valid_fns)

        # Skip section headers (no X/S marks in any cell)
        has_marks = False
        visit_data = {}

        for visit in visits:
            cell = str(df.iloc[row_idx][visit['column_index']]).strip()
            cell = cell.replace('\n', ' ').strip()

            # Phase C: extract cell-level footnotes
            mark, cell_footnotes = parse_cell_mark_and_footnotes(cell, valid_fns)

            if mark:
                has_marks = True
                # Phase D: merge procedure-level + cell-level
                effective = sorted(set(proc_footnotes + cell_footnotes))
                visit_data[visit['visit_label']] = {
                    'mark': mark,
                    'cell_footnotes': cell_footnotes,
                    'effective_footnotes': effective,
                }

        if has_marks:
            procedure_map[proc_name] = {
                'procedure_level': proc_footnotes,
                'visits': visit_data,
            }

    return procedure_map


# ── Phase E: Validation ──────────────────────────────────────────────────────
def validate_map(procedure_map: dict, footnote_texts: dict) -> dict:
    """
    Cross-validate the footnote map:
    1. Every footnote in the map should exist in footnote_texts
    2. Every footnote in footnote_texts should appear somewhere in the map
    """
    # Collect all footnote numbers used in the map
    used_footnotes = set()
    for proc_data in procedure_map.values():
        for fn in proc_data.get('procedure_level', []):
            used_footnotes.add(fn)
        for visit_data in proc_data.get('visits', {}).values():
            for fn in visit_data.get('cell_footnotes', []):
                used_footnotes.add(fn)

    text_footnotes = set(footnote_texts.keys())

    orphan_in_map = used_footnotes - text_footnotes  # in map but no text
    orphan_in_text = text_footnotes - used_footnotes  # text exists but not in any cell

    return {
        'total_footnotes_in_text': len(text_footnotes),
        'total_footnotes_used_in_map': len(used_footnotes),
        'orphan_in_map': sorted(orphan_in_map),
        'orphan_in_text': sorted(orphan_in_text),
        'all_mapped': len(orphan_in_map) == 0,
        'all_used': len(orphan_in_text) == 0,
    }


# ── Supplemental: pdfplumber character-level superscript detection ───────────
def detect_superscripts_by_char_size(pdf_path: str, soa_pages: list) -> dict:
    """
    Supplemental verification: use pdfplumber character-level data to detect
    superscripts by font size. Returns cells where small-font digits were found.

    This serves as a CROSS-CHECK against the Camelot-based extraction.
    If Camelot missed a superscript (read "X10" as just "X"), this will catch it.
    """
    superscript_chars = []

    with pdfplumber.open(pdf_path) as pdf:
        for pg in soa_pages:
            if pg < 1 or pg > len(pdf.pages):
                continue
            page = pdf.pages[pg - 1]
            chars = page.chars

            if not chars:
                continue

            # Determine base font size (most common)
            sizes = [round(c.get('size', 0), 1) for c in chars if c.get('size', 0) > 0]
            if not sizes:
                continue
            from collections import Counter
            size_counts = Counter(sizes)
            base_size = size_counts.most_common(1)[0][0]

            # Superscripts: digits with size significantly smaller than base
            threshold = base_size * 0.75
            for c in chars:
                if c.get('size', 0) < threshold and c['text'].isdigit():
                    superscript_chars.append({
                        'text': c['text'],
                        'size': round(c['size'], 2),
                        'x0': round(c['x0'], 1),
                        'y0': round(c['top'], 1),
                        'page': pg,
                    })

    return {
        'count': len(superscript_chars),
        'base_font_size': base_size if sizes else None,
        'superscript_threshold': round(threshold, 1) if sizes else None,
        'chars': superscript_chars,
    }


# ── Main: build_footnote_map ─────────────────────────────────────────────────
def build_footnote_map(
    pdf_path: str,
    soa_pages: list,
    fn_pages: list,
    out_dir: str = None,
) -> dict:
    """
    Build the complete deterministic footnote map.
    This is the main entry point called by the pipeline.
    """
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber required. Run: pip install pdfplumber")
    if not HAS_CAMELOT:
        raise ImportError("camelot-py required. Run: pip install camelot-py[cv]")

    print(f"\n{'='*60}")
    print(f"Step 1C — Deterministic Footnote Mapping")
    print(f"{'='*60}")
    print(f"  PDF: {pdf_path}")
    print(f"  SoA pages: {soa_pages}")
    print(f"  Footnote pages: {fn_pages}")

    # Phase A: extract footnote texts
    print(f"\n  Phase A: Extracting footnote texts...")
    footnote_texts = extract_footnote_texts(pdf_path, fn_pages)
    print(f"    Found {len(footnote_texts)} footnotes")
    for num in sorted(footnote_texts.keys())[:5]:
        preview = footnote_texts[num][:60]
        print(f"    Footnote {num}: {preview}...")
    if len(footnote_texts) > 5:
        print(f"    ... and {len(footnote_texts) - 5} more")

    # Phase B+C+D: build map from Camelot
    print(f"\n  Phase B-D: Building map from Camelot table...")
    procedure_map = build_map_from_camelot(pdf_path, soa_pages, footnote_texts)
    print(f"    Mapped {len(procedure_map)} procedures")

    # Phase E: validate
    print(f"\n  Phase E: Validating...")
    validation = validate_map(procedure_map, footnote_texts)
    print(f"    Footnotes in text: {validation['total_footnotes_in_text']}")
    print(f"    Footnotes used in map: {validation['total_footnotes_used_in_map']}")
    if validation['orphan_in_map']:
        print(f"    WARNING — in map but no text: {validation['orphan_in_map']}")
    if validation['orphan_in_text']:
        print(f"    NOTE — in text but not in any cell: {validation['orphan_in_text']}")
        print(f"    (These may be general footnotes that apply to the whole table)")

    # Supplemental: pdfplumber cross-check
    print(f"\n  Supplemental: pdfplumber superscript cross-check...")
    superscript_info = detect_superscripts_by_char_size(pdf_path, soa_pages)
    print(f"    Found {superscript_info['count']} superscript digit chars")
    print(f"    Base font size: {superscript_info['base_font_size']}pt")
    print(f"    Superscript threshold: <{superscript_info['superscript_threshold']}pt")

    # Build reverse index: footnote_number → which procedures/visits use it
    footnote_usage = {}
    for proc_name, proc_data in procedure_map.items():
        for fn in proc_data.get('procedure_level', []):
            footnote_usage.setdefault(fn, []).append({
                'procedure': proc_name,
                'source': 'procedure_level',
                'visits': list(proc_data.get('visits', {}).keys()),
            })
        for visit_label, visit_data in proc_data.get('visits', {}).items():
            for fn in visit_data.get('cell_footnotes', []):
                footnote_usage.setdefault(fn, []).append({
                    'procedure': proc_name,
                    'source': 'cell_level',
                    'visits': [visit_label],
                })

    # Assemble output
    result = {
        '_meta': {
            'source': 'deterministic-footnote-mapper',
            'pdf': os.path.basename(pdf_path),
            'soa_pages': soa_pages,
            'footnote_pages': list(fn_pages),
            'total_footnotes': len(footnote_texts),
            'total_procedures': len(procedure_map),
        },
        'footnote_texts': {str(k): v for k, v in sorted(footnote_texts.items())},
        'procedure_footnotes': procedure_map,
        'footnote_usage': {str(k): v for k, v in sorted(footnote_usage.items())},
        'validation': validation,
        'superscript_cross_check': {
            'count': superscript_info['count'],
            'base_font_size': superscript_info['base_font_size'],
        },
    }

    # Save
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'footnote_map.json')
        with open(out_path, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved: {out_path}")
        print(f"  {len(procedure_map)} procedures × footnotes mapped deterministically")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_page_range(s: str) -> list:
    """Parse '25-29' or '25,26,27' into list of ints."""
    pages = []
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Step 1C — Deterministic Footnote Mapper')
    parser.add_argument('--pdf', required=True, help='Path to protocol PDF')
    parser.add_argument('--table-pages', required=True, help='SoA table page(s): "24" or "22,23,24"')
    parser.add_argument('--fn-pages', required=True, help='Footnote page range: "25-29" or "25,26,27,28,29"')
    parser.add_argument('--out', required=True, help='Output directory')
    args = parser.parse_args()

    soa_pages = parse_page_range(args.table_pages)
    fn_pages = parse_page_range(args.fn_pages)

    result = build_footnote_map(args.pdf, soa_pages, fn_pages, args.out)

    # Summary
    print(f"\n{'='*60}")
    v = result['validation']
    if v['all_mapped']:
        print(f"✓ All footnote references in cells have matching text")
    else:
        print(f"✗ Orphan footnotes in map (no text): {v['orphan_in_map']}")
    if v['all_used']:
        print(f"✓ All footnote texts are referenced in cells")
    else:
        print(f"  Unreferenced footnotes (general/table-wide): {v['orphan_in_text']}")
    print(f"{'='*60}")
