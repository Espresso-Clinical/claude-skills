"""
Extract a page-range from the source protocol PDF as plain text.
Used during cross-check: the agent passes the cited page or section, this script
returns the surrounding text so the agent can verify the rule's intent against
the actual protocol wording.

Usage:
    python extract_protocol_pages.py <protocol.pdf> <start_page> <end_page>

Pages are 1-indexed. Use the same page numbers shown in the protocol's footer
(if they match the PDF's logical page numbers; some PDFs have offset front matter).
"""
import sys

try:
    import pypdf
except ImportError:  # fall back to PyPDF2
    try:
        import PyPDF2 as pypdf  # type: ignore
    except ImportError:
        print(
            "ERROR: neither pypdf nor PyPDF2 is installed. "
            "Install with: pip install pypdf",
            file=sys.stderr,
        )
        sys.exit(2)


def extract(pdf_path: str, start_page: int, end_page: int) -> str:
    reader = pypdf.PdfReader(pdf_path)
    total = len(reader.pages)
    start = max(1, start_page)
    end = min(total, end_page)
    out = []
    for i in range(start - 1, end):
        page = reader.pages[i]
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = f"[extraction failed for page {i + 1}: {exc}]"
        out.append(f"\n===== PAGE {i + 1} =====\n{text}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python extract_protocol_pages.py <protocol.pdf> <start_page> <end_page>",
            file=sys.stderr,
        )
        sys.exit(2)
    pdf_path = sys.argv[1]
    start = int(sys.argv[2])
    end = int(sys.argv[3])
    print(extract(pdf_path, start, end))
