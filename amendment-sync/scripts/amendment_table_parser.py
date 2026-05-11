"""
Phase 1 Path A — Parse the amendment-history table from the first 30 pages
of the new document.

Implementation: dispatched at runtime to a Claude Sonnet subagent using the
P1A prompt from references/prompts.md. The subagent receives the
pdfplumber-extracted text + any Camelot-extracted tables from pages 1-30
and returns the structured change list.

This script provides the deterministic pre-processing (text + table
extraction) and post-processing (validation + normalization) around that
LLM call. The LLM call itself is performed by the orchestrator's parent
agent context — this module returns a manifest of what to send.

If no amendment summary is found, returns an empty list and logs
{"amendment_table": null} in the run's _meta. Never raises.
"""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber


PROMPT_KEY = "P1A"  # references/prompts.md anchor


def _extract_first_pages(pdf_path: Path, n: int = 30) -> str:
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(min(n, len(pdf.pages))):
            t = pdf.pages[i].extract_text() or ""
            parts.append(f"--- page {i + 1} ---\n{t}")
    return "\n".join(parts)


def parse_amendment_table(new_doc: Path, out_dir: Path) -> list[dict]:
    text_dump = _extract_first_pages(new_doc, n=30)
    payload = {
        "prompt_key": PROMPT_KEY,
        "new_doc": str(new_doc),
        "first_pages_text": text_dump,
    }
    (out_dir / "amendment_parser_input.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )

    # The orchestrator (parent agent) consumes amendment_parser_input.json,
    # runs the P1A prompt against Claude Sonnet, and writes the result to
    # amendment_table_changes.json before invoking Phase 1 Path B + merge.
    out_file = out_dir / "amendment_table_changes.json"
    if out_file.exists():
        result = json.loads(out_file.read_text())
        if result.get("found"):
            return result.get("changes", [])
        return []
    raise RuntimeError(
        "amendment_table_changes.json not found. The orchestrator must run "
        "the P1A prompt (see references/prompts.md) on amendment_parser_input.json "
        "and write the structured output before run.py proceeds."
    )
