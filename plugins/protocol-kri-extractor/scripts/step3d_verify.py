"""
Step 3D — Full Verbatim Verification (MANDATORY BLOCKING GATE)
Verifies every KRI's supporting_quote is a verbatim substring of the cited protocol page text.
Auto-corrects wrong page numbers (searches ±2 pages). Strips accidental outer quotes.
Pipeline CANNOT advance to Step 4A until this script reports 0 failures.

Usage:
  python step3d_verify.py --pdf /path/to/protocol.pdf --json /path/to/extracted_kris.json

Dependencies:
  pip install pdfplumber --break-system-packages -q
"""
import json, re, argparse, shutil, pathlib, sys

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


def norm(t: str) -> str:
    """Normalize whitespace — collapses all runs of whitespace to single space."""
    return re.sub(r'\s+', ' ', t).strip()


def strip_outer_quotes(s: str) -> str:
    """Remove outer double-quote wrapping if present. Safety net."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"') and len(s) > 1:
        return s[1:-1]
    if s.startswith('"'):
        return s.lstrip('"')
    return s


def extract_cited_pages(ref: str):
    """Return (start_page, end_page) from protocol_reference.
    Handles ranges like 'p.24-p.29' and single pages like 'p.46'."""
    m_range = re.search(r'(?:p\.?|pages?)\s*(\d+)\s*-\s*(?:p\.?|pages?)\s*(\d+)', ref, re.IGNORECASE)
    if m_range:
        return int(m_range.group(1)), int(m_range.group(2))
    m_single = re.search(r'(?:p\.?|pages?)\s*(\d+)', ref, re.IGNORECASE)
    if m_single:
        pg = int(m_single.group(1))
        return pg, pg
    return None, None


def update_ref_page(ref: str, old_pg: int, new_pg: int) -> str:
    """Replace old page number with new page number in a protocol_reference string."""
    new_ref = re.sub(r'\bp\.' + str(old_pg) + r'\b', f'p.{new_pg}', ref)
    if new_ref == ref:
        # Append if substitution didn't fire (shouldn't happen given extract_cited_page found it)
        new_ref = ref.rstrip(', ') + f', p.{new_pg}'
    return new_ref


def verify_all(pdf_path: str, json_path: str) -> dict:
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber --break-system-packages -q")

    with open(json_path) as f:
        raw = json.load(f)

    # Support both list format and {"kris": [...]} format
    if isinstance(raw, list):
        kris = raw
        data = raw
    else:
        kris = raw.get("kris", [])
        data = raw

    print(f"Loading {len(kris)} KRIs from {json_path}")
    print(f"Caching all pages from {pdf_path} ...")

    # Cache all pages in a single PDF open for performance
    page_cache = {}
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            page_cache[i] = page.extract_text() or ''

    print(f"Cached {n_pages} pages. Running verification...")

    passed       = []
    auto_fixed   = []
    failed       = []
    no_page      = []

    for k in kris:
        kid = k.get('kri_id', '?')
        ref = k.get('protocol_reference', '') or ''
        q   = k.get('supporting_quote', '') or ''

        # Safety-net: strip outer quotes that should never be there
        q_clean = strip_outer_quotes(q)
        if not q_clean:
            failed.append({'kri_id': kid, 'reason': 'EMPTY_QUOTE', 'ref': ref})
            continue

        pg_start, pg_end = extract_cited_pages(ref)
        if pg_start is None:
            no_page.append({'kri_id': kid, 'reason': 'NO_PAGE_IN_REF', 'ref': ref})
            continue

        # Search cited page range ± 2
        found_pg = None
        for p2 in range(max(1, pg_start - 2), min(n_pages, pg_end + 2) + 1):
            if norm(q_clean) in norm(page_cache.get(p2, '')):
                found_pg = p2
                break

        if found_pg is None:
            failed.append({
                'kri_id':   kid,
                'cited_pg': f'{pg_start}-{pg_end}' if pg_start != pg_end else pg_start,
                'quote':    q_clean[:100],
                'ref':      ref,
            })
        else:
            # Always save the cleaned quote back
            k['supporting_quote'] = q_clean

            # For page ranges (e.g., p.24-p.29), don't auto-correct — the range is intentional
            if pg_start == pg_end and found_pg != pg_start:
                # Single-page ref, found on different page — auto-correct
                new_ref = update_ref_page(ref, pg_start, found_pg)
                k['protocol_reference'] = new_ref
                k['combined_ref'] = f'{new_ref} \u2014 "{q_clean}"'
                auto_fixed.append({
                    'kri_id':  kid,
                    'old_ref': ref,
                    'new_ref': new_ref,
                    'old_pg':  pg_start,
                    'new_pg':  found_pg,
                })
            else:
                k['combined_ref'] = f'{ref} \u2014 "{q_clean}"'

            passed.append(kid)

    total = len(kris)
    n_pass  = len(passed)
    n_fix   = len(auto_fixed)
    n_fail  = len(failed)
    n_nopg  = len(no_page)

    # ── Save corrected JSON (with backup) ─────────────────────────────────────
    backup = pathlib.Path(json_path).with_suffix('.pre_verify.json')
    shutil.copy(json_path, backup)

    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Save verify report ────────────────────────────────────────────────────
    out_dir   = pathlib.Path(json_path).parent
    rpt_path  = out_dir / 'verify_report.json'
    report = {
        'total': total,
        'passed': n_pass,
        'auto_corrected': n_fix,
        'failed': n_fail,
        'no_page_ref': n_nopg,
        'auto_corrections': auto_fixed,
        'failures': failed,
        'no_page_kris': no_page,
    }
    with open(rpt_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ── Print summary ─────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║       STEP 3D — VERBATIM VERIFICATION       ║")
    print("╠══════════════════════════════════════════════╣")
    print(f"║  Total KRIs        : {total:<24}║")
    print(f"║  Passed (correct)  : {n_pass:<24}║")
    print(f"║  Auto-corrected    : {n_fix:<24}║")
    print(f"║  No page ref       : {n_nopg:<24}║")
    print(f"║  FAILED            : {n_fail:<24}║")
    print("╠══════════════════════════════════════════════╣")
    status = "✓ ALL PASS — proceed to Step 4A" if (n_fail + n_nopg) == 0 else "✗ FAILURES REMAIN — fix before Step 4A"
    print(f"║  {status:<43}║")
    print("╚══════════════════════════════════════════════╝")
    print(f"\nBackup: {backup}")
    print(f"Saved:  {json_path} ({total} KRIs)")
    print(f"Report: {rpt_path}")

    if auto_fixed:
        print(f"\nAuto-corrected page references ({n_fix}):")
        for c in auto_fixed:
            print(f"  {c['kri_id']}: p.{c['old_pg']} → p.{c['new_pg']}")

    if failed:
        print(f"\n⚠ FAILING KRIs — must be fixed manually before Step 4A ({n_fail}):")
        for f in failed:
            print(f"  {f['kri_id']} (cited p.{f.get('cited_pg','?')}): {repr(f.get('quote','')[:80])}")
        print("\nFor each failing KRI:")
        print("  1. Open the PDF at the cited page ± 2 pages")
        print("  2. Find the actual verbatim text")
        print("  3. Update supporting_quote to match the PDF exactly")
        print("  4. Update protocol_reference to the correct page")
        print("  5. Re-run this script")

    if no_page:
        print(f"\n⚠ KRIs with no page number in protocol_reference ({n_nopg}):")
        for np in no_page:
            print(f"  {np['kri_id']}: {np['ref']}")

    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Step 3D — Full verbatim verification')
    parser.add_argument('--pdf',  required=True, help='Path to protocol PDF')
    parser.add_argument('--json', required=True, help='Path to extracted_kris.json')
    args = parser.parse_args()

    report = verify_all(args.pdf, args.json)

    # Exit with error code if failures remain (blocks pipeline automation)
    if report['failed'] or report['no_page_kris']:
        sys.exit(1)
    else:
        sys.exit(0)
