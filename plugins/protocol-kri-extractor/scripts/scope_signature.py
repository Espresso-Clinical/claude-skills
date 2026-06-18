"""
scope_signature — canonical scope-conflict detection (Fix #6).

Single source of truth shared by the clustering step (step2_extract.py) and the
dedup step (step4a_dedup.py) so two KRIs that differ in TIME-SCOPE or STUDY PHASE
are never silently merged back together — even when their wording is similar.

Scope atomization splits a compound rule into atomic per-scope KRIs (e.g.
"prohibited prior to AND during the study" → a pre-treatment KRI + an on-study
KRI). Those splits are NOT duplicates; clustering and dedup must keep them apart.
`scope_conflict(a, b)` returns True when two rule texts assert DIFFERENT scopes,
so callers keep both. It returns False when scopes match or are absent (so genuine
duplicates still merge and agent_count stays correct).
"""

import re

# Time-scope cues
_TIME_PRIOR = re.compile(
    r"\b(prior to|before|pre[-\s]?(dose|treatment|study|baseline|enrol)|preceding|"
    r"within\s+\d+\s+\w+\s+prior)\b", re.IGNORECASE)
_TIME_DURING = re.compile(
    r"\b(during the study|during treatment|throughout|while\s+(on|enrolled|receiving)|"
    r"on[-\s]?study|on treatment|over the study period)\b", re.IGNORECASE)
_TIME_POST = re.compile(
    r"\b(post[-\s]?(dose|treatment|study|injection)|post-study|"
    r"after\s+(the\s+)?(last|final|study)|following\s+(the\s+)?(last|final)\s+(treatment|dose|injection))\b",
    re.IGNORECASE)

# Study-phase cues
_PHASE_RUNIN = re.compile(r"\b(run[-\s]?in|safety run)\b", re.IGNORECASE)
_PHASE_RAND = re.compile(r"\brandomi[sz](ation|ed)\s+phase\b", re.IGNORECASE)


def scope_tags(text: str):
    """Return (time_tags, phase_tags) as sets, e.g. ({'PRIOR'}, set())."""
    t = text or ""
    time = set()
    if _TIME_PRIOR.search(t):
        time.add("PRIOR")
    if _TIME_DURING.search(t):
        time.add("DURING")
    if _TIME_POST.search(t):
        time.add("POST")
    phase = set()
    if _PHASE_RUNIN.search(t):
        phase.add("RUNIN")
    if _PHASE_RAND.search(t):
        phase.add("RAND")
    return time, phase


def kri_identity(kri: dict) -> str:
    """Semantic identity of a KRI for clustering/dedup (Item 2 — rule_for_llm removed).

    The verbatim `supporting_quote` is the most reliable anchor: two agents extracting
    the SAME rule cite the same/overlapping quote (≈1.0 similarity), while different
    rules (different analytes/criteria) and atomization splits get DIFFERENT quotes
    (Quality Rule 12 — each split anchors its own shortest verbatim segment), so they
    stay separate. Prose descriptions are NOT used as the primary key because their
    boilerplate makes different rules look similar and the same rule look different.
    Falls back to kri_name + description only when no quote is present (e.g. orphan
    stubs). Shared by step2_extract (clustering) and step4a_dedup (dedup) so the key
    lives in one place."""
    q = (kri.get("supporting_quote") or "").strip()
    if q:
        return q
    return f"{kri.get('kri_name', '')} {kri.get('description', '')}".strip()


def scope_conflict(a: str, b: str) -> bool:
    """True if a and b assert DIFFERENT time-scopes or study-phases.

    Conservative: fires ONLY when both sides carry a tag of the same kind and the
    tag sets differ (e.g. {PRIOR} vs {DURING}, or {RUNIN} vs {RAND}). If either
    side has no time/phase tag, there is no conflict — genuine duplicates and
    same-scope agent outputs still merge.
    """
    ta, pa = scope_tags(a)
    tb, pb = scope_tags(b)
    if ta and tb and ta != tb:
        return True
    if pa and pb and pa != pb:
        return True
    return False
