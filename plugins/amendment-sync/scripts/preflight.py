"""
Pre-flight integrity check: verify the v1 Golden Set corresponds to the
old document supplied via --old-doc.

Process: sample 10 random KRIs, run Step 3D-style verbatim verification on
each (the same logic the extractor uses for its blocking gate). If fewer
than 9/10 match verbatim, the Golden Set does not correspond to the old
document and the pipeline halts.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pdfplumber


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def _parse_page_range(ref: str) -> tuple[int, int] | None:
    m_range = re.search(r"p\.(\d+)-p\.(\d+)", ref)
    if m_range:
        return int(m_range.group(1)), int(m_range.group(2))
    m_single = re.search(r"p\.(\d+)", ref)
    if m_single:
        v = int(m_single.group(1))
        return v, v
    return None


def verify_golden_matches_old_doc(
    old_doc: Path,
    golden: Path,
    sample_size: int = 10,
    min_passes: int = 9,
    rng_seed: int = 1337,
) -> dict:
    data = json.loads(golden.read_text())
    kris = data.get("kris", data) if isinstance(data, dict) else data
    if not kris:
        raise SystemExit(f"Golden Set has no KRIs: {golden}")

    rng = random.Random(rng_seed)
    sample = rng.sample(kris, min(sample_size, len(kris)))

    pages: dict[int, str] = {}
    passes: list[dict] = []
    fails: list[dict] = []

    with pdfplumber.open(old_doc) as pdf:
        n_pages = len(pdf.pages)
        for k in sample:
            kid = k.get("kri_id", "?")
            quote = k.get("supporting_quote", "") or ""
            if quote.startswith('"') and quote.endswith('"') and len(quote) > 1:
                quote = quote[1:-1]
            ref = k.get("protocol_reference", "")
            rng_pages = _parse_page_range(ref)
            if not rng_pages:
                fails.append({"kri_id": kid, "reason": "NO_PAGE_IN_REF", "ref": ref})
                continue
            pg_start, pg_end = rng_pages
            found_pg: int | None = None
            for pg in range(max(1, pg_start - 2), min(n_pages, pg_end + 2) + 1):
                if pg not in pages:
                    pages[pg] = pdf.pages[pg - 1].extract_text() or ""
                if _norm(quote) and _norm(quote) in _norm(pages[pg]):
                    found_pg = pg
                    break
            if found_pg is None:
                fails.append(
                    {"kri_id": kid, "reason": "QUOTE_NOT_FOUND", "ref": ref, "quote_preview": quote[:80]}
                )
            else:
                passes.append({"kri_id": kid, "found_pg": found_pg, "cited_ref": ref})

    return {
        "pass": len(passes) >= min_passes,
        "passes": len(passes),
        "fails": len(fails),
        "sample_size": len(sample),
        "min_passes_required": min_passes,
        "pass_records": passes,
        "fail_records": fails,
        "old_doc": str(old_doc),
        "golden": str(golden),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--old-doc", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--sample-size", type=int, default=10)
    ap.add_argument("--min-passes", type=int, default=9)
    args = ap.parse_args()
    result = verify_golden_matches_old_doc(
        old_doc=Path(args.old_doc).expanduser().resolve(),
        golden=Path(args.golden).expanduser().resolve(),
        sample_size=args.sample_size,
        min_passes=args.min_passes,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
