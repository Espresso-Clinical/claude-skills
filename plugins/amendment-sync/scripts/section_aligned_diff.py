"""
Phase 1 Path B — Section-aligned full-document diff.

Pipeline:
  B1. Build section maps for both documents (reuses extractor's Step 1A).
  B2. Align sections by number then by title fuzzy match (rapidfuzz).
  B3. Per aligned pair, run difflib at sentence granularity, then dispatch
      P1B semantic classifier on each hunk via a subagent.

The deterministic core (B1 alignment + B3 difflib) runs here. The LLM
classification of each hunk is dispatched via prompt P1B (see
references/prompts.md). The orchestrator drives that dispatch and writes
the classified hunks back to diff_changes.json before merging.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber
from rapidfuzz import fuzz


SENTENCE_BOUNDARY = re.compile(r"(?<=[\.\?\!])\s+(?=[A-Z\d])")


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def _split_sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_BOUNDARY.split(text or "") if s.strip()]


def _build_section_map(pdf_path: Path) -> list[dict]:
    """
    Lightweight section map: scan for section headers of the form 'N', 'N.N',
    'N.N.N' followed by a title. This is a fallback; production runs should
    reuse the extractor's step1a_manifest.py for higher fidelity.
    """
    header_re = re.compile(r"^([\d]+(?:\.\d+){0,4})\s+([A-Z][^\n]{2,120})$", re.MULTILINE)
    sections: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            for m in header_re.finditer(text):
                sections.append(
                    {
                        "section_number": m.group(1).rstrip("."),
                        "title": m.group(2).strip(),
                        "page": i + 1,
                    }
                )
    return sections


def _align_sections(v1: list[dict], v2: list[dict]) -> list[dict]:
    pairs: list[dict] = []
    v2_by_num = {s["section_number"]: s for s in v2}
    used_v2 = set()
    for s1 in v1:
        n = s1["section_number"]
        if n in v2_by_num:
            s2 = v2_by_num[n]
            pairs.append({"v1": s1, "v2": s2, "method": "number_exact", "confidence": "high"})
            used_v2.add(n)
            continue
        # fuzzy title match
        best, best_score = None, 0
        for s2 in v2:
            if s2["section_number"] in used_v2:
                continue
            score = fuzz.token_set_ratio(s1["title"], s2["title"])
            if score > best_score:
                best, best_score = s2, score
        if best and best_score >= 80:
            pairs.append({"v1": s1, "v2": best, "method": "title_fuzzy", "confidence": "medium", "score": best_score})
            used_v2.add(best["section_number"])
        else:
            pairs.append({"v1": s1, "v2": None, "method": "no_match", "confidence": "low"})
    for s2 in v2:
        if s2["section_number"] not in used_v2:
            pairs.append({"v1": None, "v2": s2, "method": "section_added", "confidence": "n/a"})
    return pairs


def _section_text(pdf_path: Path, start_page: int, end_page: int) -> str:
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        for pg in range(start_page, min(end_page, n) + 1):
            parts.append(pdf.pages[pg - 1].extract_text() or "")
    return "\n".join(parts)


def _section_page_range(section: dict, all_sections: list[dict]) -> tuple[int, int]:
    """Page range of a section: from its page to the next section's page minus one."""
    start = section["page"]
    after = [s for s in all_sections if s["page"] > start]
    end = (min(after, key=lambda s: s["page"])["page"] - 1) if after else start + 5
    return start, end


def _diff_hunks(v1_text: str, v2_text: str) -> list[dict]:
    a = _split_sentences(v1_text)
    b = _split_sentences(v2_text)
    sm = SequenceMatcher(None, [_norm(s) for s in a], [_norm(s) for s in b])
    hunks: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            {
                "tag": tag,  # 'replace' | 'delete' | 'insert'
                "old_text": " ".join(a[i1:i2]),
                "new_text": " ".join(b[j1:j2]),
                "v1_sentence_range": [i1, i2],
                "v2_sentence_range": [j1, j2],
            }
        )
    return hunks


def compute_section_aligned_diff(old_doc: Path, new_doc: Path, out_dir: Path) -> list[dict]:
    v1_sections = _build_section_map(old_doc)
    v2_sections = _build_section_map(new_doc)
    pairs = _align_sections(v1_sections, v2_sections)
    (out_dir / "section_alignment.json").write_text(
        json.dumps({"pairs": pairs, "v1_sections": v1_sections, "v2_sections": v2_sections}, indent=2)
    )

    raw_hunks: list[dict] = []
    for pair in pairs:
        s1, s2 = pair.get("v1"), pair.get("v2")
        if s1 and s2:
            a_start, a_end = _section_page_range(s1, v1_sections)
            b_start, b_end = _section_page_range(s2, v2_sections)
            v1_text = _section_text(old_doc, a_start, a_end)
            v2_text = _section_text(new_doc, b_start, b_end)
            for h in _diff_hunks(v1_text, v2_text):
                raw_hunks.append(
                    {
                        **h,
                        "section_v1": f"{s1['section_number']} {s1['title']}",
                        "section_v2": f"{s2['section_number']} {s2['title']}",
                        "page_v1": s1["page"],
                        "page_v2": s2["page"],
                        "change_type": {"replace": "modified", "insert": "added", "delete": "removed"}[h["tag"]],
                    }
                )
        elif s2 and not s1:
            a_start, a_end = _section_page_range(s2, v2_sections)
            new_text = _section_text(new_doc, a_start, a_end)
            raw_hunks.append(
                {
                    "tag": "section_added",
                    "old_text": "",
                    "new_text": new_text,
                    "section_v1": None,
                    "section_v2": f"{s2['section_number']} {s2['title']}",
                    "page_v1": None,
                    "page_v2": s2["page"],
                    "change_type": "added",
                }
            )
        elif s1 and not s2:
            a_start, a_end = _section_page_range(s1, v1_sections)
            old_text = _section_text(old_doc, a_start, a_end)
            raw_hunks.append(
                {
                    "tag": "section_removed",
                    "old_text": old_text,
                    "new_text": "",
                    "section_v1": f"{s1['section_number']} {s1['title']}",
                    "section_v2": None,
                    "page_v1": s1["page"],
                    "page_v2": None,
                    "change_type": "removed",
                }
            )

    (out_dir / "diff_hunks_unclassified.json").write_text(
        json.dumps({"hunks": raw_hunks}, indent=2, ensure_ascii=False)
    )

    classified_path = out_dir / "diff_changes.json"
    if classified_path.exists():
        return json.loads(classified_path.read_text()).get("changes", raw_hunks)

    raise RuntimeError(
        "diff_changes.json not found. The orchestrator must run the P1B "
        "semantic-kind classifier (see references/prompts.md) on each hunk in "
        "diff_hunks_unclassified.json and write classified diff_changes.json "
        "before merging. Each classified hunk must carry semantic_kind in "
        "{cosmetic, rephrase_no_meaning_change, substantive}."
    )
