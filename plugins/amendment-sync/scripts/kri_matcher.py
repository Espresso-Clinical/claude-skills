"""
Phase 2 Layers 1-3 — deterministic KRI-to-change matching.

  Layer 1 — Reference anchor: KRI.protocol_reference cites the changed section/page.
  Layer 2 — Quote substring: KRI.supporting_quote overlaps change.old_text.
  Layer 3 — Reverse context window: change.old_text falls within the KRI's
            ±1-page context window in the old document.

Output: a dict keyed by change_id with one entry per match, used by Phase 2
Layer 4 to skip already-matched KRIs when building embedding shortlists, and
used directly by Phase 3 as a high-precision starting set.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pdfplumber


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def _parse_pages(ref: str) -> list[int]:
    m_range = re.search(r"p\.(\d+)-p\.(\d+)", ref)
    if m_range:
        a, b = int(m_range.group(1)), int(m_range.group(2))
        return list(range(a, b + 1))
    m_single = re.search(r"p\.(\d+)", ref)
    return [int(m_single.group(1))] if m_single else []


def _section_token(ref: str) -> str | None:
    m = re.search(r"Section\s+([\d\.]+)", ref)
    if m:
        return m.group(1).rstrip(".")
    if "Schedule of Activities" in ref:
        return "SoA"
    return None


def _layer1_reference(change: dict, kris: list[dict]) -> list[dict]:
    """Match by section or page citation."""
    matches: list[dict] = []
    chg_sec = (change.get("section_v1") or "").strip()
    chg_pg = change.get("page_v1")
    chg_sec_num = re.search(r"([\d]+(?:\.\d+)*)", chg_sec)
    chg_sec_num = chg_sec_num.group(1) if chg_sec_num else None

    for k in kris:
        ref = k.get("protocol_reference", "") or ""
        kri_sec = _section_token(ref)
        kri_pages = _parse_pages(ref)
        section_hit = bool(
            chg_sec_num and kri_sec and (kri_sec == chg_sec_num or kri_sec.startswith(chg_sec_num + "."))
        )
        page_hit = bool(chg_pg and chg_pg in kri_pages)
        if section_hit or page_hit:
            matches.append(
                {
                    "kri_id": k["kri_id"],
                    "layer": "L1-reference",
                    "confidence": "high",
                    "explanation": (
                        f"Reference '{ref}' matches change section "
                        f"'{chg_sec}' / page {chg_pg} "
                        f"(section_hit={section_hit}, page_hit={page_hit})"
                    ),
                }
            )
    return matches


def _layer2_quote(change: dict, kris: list[dict]) -> list[dict]:
    """Match by supporting_quote substring overlap with change.old_text."""
    matches: list[dict] = []
    old_norm = _norm(change.get("old_text", ""))
    if not old_norm:
        return matches
    for k in kris:
        quote = k.get("supporting_quote", "") or ""
        if quote.startswith('"') and quote.endswith('"') and len(quote) > 1:
            quote = quote[1:-1]
        q_norm = _norm(quote)
        if not q_norm:
            continue
        if q_norm in old_norm or old_norm in q_norm:
            matches.append(
                {
                    "kri_id": k["kri_id"],
                    "layer": "L2-quote",
                    "confidence": "high",
                    "explanation": (
                        "Supporting quote overlaps changed text "
                        f"(q_len={len(q_norm)}, old_len={len(old_norm)})"
                    ),
                }
            )
    return matches


def _build_context_windows(
    old_doc: Path, kris: list[dict], context_pad: int = 1
) -> dict[str, str]:
    """For each KRI, extract its cited pages ± context_pad pages, return normalized text."""
    pages_needed: dict[int, str] = {}
    kri_to_pages: dict[str, list[int]] = {}
    for k in kris:
        ref = k.get("protocol_reference", "") or ""
        pgs = _parse_pages(ref)
        if not pgs:
            kri_to_pages[k["kri_id"]] = []
            continue
        a = max(1, min(pgs) - context_pad)
        b = max(pgs) + context_pad
        all_pgs = list(range(a, b + 1))
        kri_to_pages[k["kri_id"]] = all_pgs
        for pg in all_pgs:
            pages_needed.setdefault(pg, "")

    if pages_needed:
        with pdfplumber.open(old_doc) as pdf:
            n_pages = len(pdf.pages)
            for pg in list(pages_needed):
                if 1 <= pg <= n_pages:
                    pages_needed[pg] = pdf.pages[pg - 1].extract_text() or ""

    windows: dict[str, str] = {}
    for kri_id, pgs in kri_to_pages.items():
        text = " ".join(pages_needed.get(pg, "") for pg in pgs)
        windows[kri_id] = _norm(text)
    return windows


def _layer3_context(change: dict, kris: list[dict], windows: dict[str, str]) -> list[dict]:
    """Match by change.old_text falling inside any KRI's context window."""
    matches: list[dict] = []
    old_norm = _norm(change.get("old_text", ""))
    if not old_norm or len(old_norm) < 12:
        return matches  # too short to be a meaningful positional anchor
    for k in kris:
        win = windows.get(k["kri_id"], "")
        if win and old_norm in win:
            matches.append(
                {
                    "kri_id": k["kri_id"],
                    "layer": "L3-context",
                    "confidence": "medium",
                    "explanation": "Changed text falls inside KRI's ±1-page context window in v1.",
                }
            )
    return matches


def _consolidate(per_change: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Per change_id, deduplicate KRIs across layers; preserve all layers per KRI."""
    out: dict[str, list[dict]] = {}
    for chg, matches in per_change.items():
        by_kri: dict[str, dict] = {}
        for m in matches:
            kid = m["kri_id"]
            if kid in by_kri:
                by_kri[kid]["match_layers"].append(m["layer"])
                by_kri[kid]["explanations"][m["layer"]] = m["explanation"]
                if m["confidence"] == "high":
                    by_kri[kid]["confidence"] = "high"
            else:
                by_kri[kid] = {
                    "kri_id": kid,
                    "match_layers": [m["layer"]],
                    "confidence": m["confidence"],
                    "explanations": {m["layer"]: m["explanation"]},
                }
        out[chg] = list(by_kri.values())
    return out


def run_layers_1_to_3(
    change_set: dict,
    golden: dict | list,
    old_doc: Path,
    out_dir: Path,
) -> dict[str, list[dict]]:
    kris = golden.get("kris", golden) if isinstance(golden, dict) else golden
    changes: Iterable[dict] = change_set.get("changes", [])

    print("  building KRI context windows from old doc...")
    windows = _build_context_windows(old_doc, kris)

    per_change: dict[str, list[dict]] = {}
    for chg in changes:
        cid = chg["change_id"]
        m1 = _layer1_reference(chg, kris)
        m2 = _layer2_quote(chg, kris)
        m3 = _layer3_context(chg, kris, windows)
        per_change[cid] = m1 + m2 + m3

    consolidated = _consolidate(per_change)

    (out_dir / "matches_layers_1_3.json").write_text(
        json.dumps({"matches": consolidated}, indent=2, ensure_ascii=False)
    )
    n_matched = sum(1 for v in consolidated.values() if v)
    print(f"  layers 1-3 produced matches for {n_matched}/{len(consolidated)} changes")
    return consolidated
