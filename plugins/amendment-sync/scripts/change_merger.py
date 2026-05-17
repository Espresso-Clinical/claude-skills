"""
Phase 1 final step — merge amendment-table changes (Path A) with diff
changes (Path B) into a single change_set.json with overlap detection
and re-diff trigger for amendment-only entries (per SKILL.md Phase 1
"Merge" section).
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _section_num(s: str) -> str | None:
    m = re.search(r"([\d]+(?:\.\d+)*)", s or "")
    return m.group(1).rstrip(".") if m else None


def _overlaps(a: dict, b: dict) -> bool:
    """Two changes overlap if their v2 sections match AND their pages are close."""
    a_sec = _section_num(a.get("section_v2") or a.get("section_affected") or "")
    b_sec = _section_num(b.get("section_v2") or b.get("section_affected") or "")
    if a_sec and b_sec and (a_sec == b_sec or a_sec.startswith(b_sec + ".") or b_sec.startswith(a_sec + ".")):
        a_pg = a.get("page_v2") or a.get("page_in_new_doc")
        b_pg = b.get("page_v2") or b.get("page_in_new_doc")
        if a_pg is None or b_pg is None:
            return True
        return abs(a_pg - b_pg) <= 2
    return False


def _confidence_from_semantic_kind(kind: str | None) -> str:
    return {
        "substantive": "high",
        "rephrase_no_meaning_change": "medium",
        "cosmetic": "low",
    }.get(kind or "substantive", "medium")


def merge_change_sources(
    amendment_changes: list[dict],
    diff_changes: list[dict],
    out_dir: Path,
) -> dict:
    """
    Produce change_set.json by unioning the two paths with overlap detection.

    For each diff change that overlaps an amendment-table row, the merged
    record carries source: ["amendment_table", "diff"] and confidence: "high".
    Diff-only changes carry source: ["diff"] with confidence per semantic_kind.
    Amendment-only entries carry source: ["amendment_table"] and trigger a
    re_diff_needed flag for Phase 2 to handle (see SKILL.md Phase 1 Merge).
    """
    merged: list[dict] = []
    used_amend = set()
    next_id = 1

    def cid() -> str:
        nonlocal next_id
        s = f"CHG-{next_id:04d}"
        next_id += 1
        return s

    for d in diff_changes:
        overlapping = [a for a in amendment_changes if _overlaps(d, a)]
        if overlapping:
            for a in overlapping:
                used_amend.add(id(a))
            merged.append(
                {
                    "change_id": cid(),
                    "source": ["amendment_table", "diff"],
                    "confidence": "high",
                    "section_v1": d.get("section_v1"),
                    "section_v2": d.get("section_v2"),
                    "page_v1": d.get("page_v1"),
                    "page_v2": d.get("page_v2"),
                    "change_type": d.get("change_type"),
                    "semantic_kind": d.get("semantic_kind"),
                    "old_text": d.get("old_text"),
                    "new_text": d.get("new_text"),
                    "context_v1": d.get("context_v1"),
                    "context_v2": d.get("context_v2"),
                    "amendment_description": overlapping[0].get("description"),
                    "amendment_rationale": overlapping[0].get("rationale"),
                }
            )
        else:
            merged.append(
                {
                    "change_id": cid(),
                    "source": ["diff"],
                    "confidence": _confidence_from_semantic_kind(d.get("semantic_kind")),
                    **{k: d.get(k) for k in (
                        "section_v1", "section_v2", "page_v1", "page_v2",
                        "change_type", "semantic_kind",
                        "old_text", "new_text", "context_v1", "context_v2",
                    )},
                }
            )

    for a in amendment_changes:
        if id(a) in used_amend:
            continue
        merged.append(
            {
                "change_id": cid(),
                "source": ["amendment_table"],
                "confidence": "medium",
                "re_diff_needed": True,
                "section_v1": None,
                "section_v2": a.get("section_affected"),
                "page_v1": None,
                "page_v2": a.get("page_in_new_doc"),
                "change_type": a.get("change_type"),
                "semantic_kind": "substantive",
                "old_text": None,
                "new_text": None,
                "amendment_description": a.get("description"),
                "amendment_rationale": a.get("rationale"),
            }
        )

    payload = {
        "_meta": {
            "total_changes": len(merged),
            "from_diff_only": sum(1 for c in merged if c["source"] == ["diff"]),
            "from_amendment_only": sum(1 for c in merged if c["source"] == ["amendment_table"]),
            "from_both": sum(1 for c in merged if set(c["source"]) == {"diff", "amendment_table"}),
            "amendment_table_found": bool(amendment_changes),
        },
        "changes": merged,
    }
    (out_dir / "change_set.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )
    m = payload["_meta"]
    print(
        f"  change_set.json: {m['total_changes']} changes "
        f"(diff-only={m['from_diff_only']}, "
        f"amend-only={m['from_amendment_only']}, "
        f"both={m['from_both']})"
    )
    return payload
