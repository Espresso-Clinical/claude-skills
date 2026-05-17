"""
Phase 2 Layer 4 — Embedding shortlist construction.

For each change unit, compute embedding similarity between the change's text
(old_text + new_text + context_v1) and every KRI's
(rule_for_llm + description + supporting_quote). Take the top-K KRIs by
cosine similarity, excluding KRIs already matched by Layers 1-3.

The shortlist becomes the input to the P2L4 semantic match panel.

Embedding provider: OpenAI text-embedding-3-small by default, configurable.
API key location follows the extractor's convention:
~/.claude/secrets/protocol-kri-extractor.json. If the key is missing, this
module falls back to local sentence-transformers (offline) — slower but
deterministic and free.
"""

from __future__ import annotations

import json
from pathlib import Path


def build_shortlists(
    change_set: dict,
    golden: dict | list,
    already_matched: dict[str, list[dict]],
    top_k: int,
    out_dir: Path,
) -> dict[str, list[str]]:
    """
    Returns: {change_id: [kri_id, ...]} ordered by descending similarity, length <= top_k.
    Excludes KRIs already in already_matched[change_id].
    """
    raise NotImplementedError(
        "kri_embedder.build_shortlists is not yet implemented. The intended flow is:\n"
        "  1. Embed each KRI (rule_for_llm + description + supporting_quote) once.\n"
        "  2. For each change, embed (old_text + new_text + context_v1).\n"
        "  3. Compute cosine similarity, exclude already-matched KRIs, take top-K.\n"
        "  4. Write shortlists.json to out_dir for the semantic panel.\n"
        "Until implemented, the orchestrator should skip Layer 4 or supply shortlists "
        "manually. Layers 1-3 still run and produce high-precision matches."
    )
