# Methodology Notes — amendment-sync

This document expands on the rationale behind the design decisions in `SKILL.md`. It is reference material — not normative. The normative spec is `SKILL.md`. When this file disagrees with `SKILL.md`, `SKILL.md` wins.

---

## Why dual-path change detection

Neither detection path is sufficient alone.

**Amendment tables (Path A) are precision-biased and incomplete.** Sponsors curate them. They list intended changes, often with descriptions that summarize rather than enumerate. A sponsor who edits 30 sentences across §5 might list one row: "§5 Dose modification — revised per FDA feedback". Path A would surface one change unit; the user would miss 29.

**Line-level diffs (Path B) are recall-biased and noisy.** A naive `difflib` diff across two protocols produces hundreds of hunks, most of which are formatting artifacts from pdfplumber (different page breaks, different hyphenation, different table-cell reflow). The semantic classifier (P1B) prunes this to a reviewable set, but even after classification a long protocol can produce 50+ change units.

**Together they triangulate.** A change that appears in both has high confidence (sponsor agrees + diff agrees → it's real and substantive). A change only in the diff is a sponsor-omitted edit (real, often small, often missed). A change only in the amendment table that the diff did not catch is a flag: the sponsor described a change our diff did not detect → re-diff that section with higher sensitivity, because we likely missed a moved or restructured sentence.

This mirrors the extractor's Step 3.5 orphan scan: primary section sweep + secondary page sweep, with their union being exhaustive.

---

## Why section-aligned (not page-aligned) diff

Pages drift between document versions. A new figure on p.32 pushes everything after by one page. A page-aligned diff would flag every paragraph from p.33 onward as "changed" — useless.

Sections are the semantic unit that survives version updates. `§5.4.1 Dose Modification` is `§5.4.1 Dose Modification` in both versions even if it now lives on different pages. Aligning by section number (with fuzzy match for renumbering) preserves the semantic frame. Within an aligned section, `difflib` operates on sentences, which is the right granularity for clinical-trial text.

The cost: building the section map for both versions. We pay this cost by reusing the extractor's Step 1A logic — no new code needed.

---

## Why 5 matching layers

A single matching method has known failure modes documented in Phase 2 of `SKILL.md`. The 5-layer approach is a defense-in-depth design:

- **Layers 1–3 are deterministic, fast, and high-precision.** They produce confident matches at near-zero LLM cost.
- **Layer 4 is the high-recall safety net.** It catches conceptual links the deterministic layers cannot — cross-section dependencies, terminology renames, defined-term changes.
- **Layer 5 is the structural audit.** It catches the case where a real change has no v1 KRI counterpart (new content in v2) or the case where one KRI is hit by many changes (consolidation for the interactive loop).

Each layer's failure mode is covered by another layer:
- L1 misses indirect references → L2 catches quote overlap → L3 catches positional context → L4 catches conceptual links → L5 catches structural gaps.

The 5-layer redundancy is intentional. Skipping any layer creates a known blind spot.

---

## Why interactive (not auto-approve-unanimous)

The user directed this explicitly. The rationale: version migrations are higher-stakes per-change than initial extractions because (a) the Golden Set is already validated and trusted, so a bad auto-edit is a regression on validated content, and (b) the user has institutional knowledge about which changes matter clinically that an auto-judgment panel cannot replicate.

The crash-safety mechanism (`decisions.jsonl` + incremental writes to the working Golden Set) is what makes the interactive mode tolerable for long sessions. The user can stop mid-loop and resume without losing decisions.

---

## Why every change matters — including cosmetic and rephrase

The Golden Set is the authoritative monitoring rule set for that document version. Its `supporting_quote` and `protocol_reference` fields are verbatim citations. When the document is reformatted, retyped, or rephrased, those verbatim citations stop matching the latest text. Downstream tools that verify the citations against the current document will fail — even though nothing semantically changed.

The user's directive that cosmetic and rephrase changes still propagate into KRI updates is what keeps the Golden Set in lockstep with the source. The classification only changes *how* the propagation happens:

- **Cosmetic change** → REANCHOR (Phase 3.1) usually suffices: re-bind quote, update page, keep rule text.
- **Rephrase no meaning change** → REANCHOR or EDIT_MANUAL (user updates description/quote, keeps rule semantics).
- **Substantive change** → EDIT_PANEL (regenerate via panel, full quality re-judging).

---

## Why scope the accuracy panel (4.2) but not the verbatim check (4.1)

Step 4.1 (verbatim verification) is cheap — it's a pdfplumber substring match. Running it on all 312 KRIs costs <1 second of compute and catches reference drift on UNCHANGED KRIs (e.g., a page number that shifted but the KRI was not flagged as affected because the section content was identical).

Step 4.2 (accuracy panel) is expensive — 5 LLM agents per KRI, page text loaded as context. Running it on all 312 KRIs when only 78 changed wastes ~75% of judging budget on KRIs already judged in the original extraction. Scoping to the changed/new subset preserves quality (changed KRIs get full 5-judge cross-model judging) while controlling cost.

The trade-off: an UNCHANGED KRI that has a subtle accuracy error introduced into v2 (e.g., the protocol now contradicts a KRI that used to be correct) is not caught by 4.2. This is acceptable because (a) such errors are rare — they require v2 to introduce a contradiction with content that did not directly change, which contradicts the definition of "unchanged" — and (b) the verbatim check would still catch the reference if the supporting quote no longer matches v2 at the cited page.

---

## What this skill is NOT

- **Not a re-extractor.** When a document has changed substantially (>50% of KRIs would be edited), it is cheaper and safer to re-run the extractor from scratch on the new document. This skill is for incremental updates, not rewrites.
- **Not a comparison tool.** Comparing two Golden Sets (e.g., v1 Golden Set vs. an independently extracted v2 Golden Set) is the extractor's Step 4C job, not this skill's.
- **Not a backward migration.** This skill goes old→new. Going new→old (regressing a Golden Set to an older document version) is not in scope.
- **Not an auto-pilot.** Every disposition decision is made by the user. The skill proposes; the user disposes.

---

## Failure modes and mitigations

| Failure mode | Mitigation |
|---|---|
| User supplies a Golden Set that does not match the old document | Pre-flight integrity check: 10-quote verbatim sample, ≥9 must match, else STOP. |
| Diff path produces hundreds of cosmetic hunks | Semantic classifier (P1B) labels them cosmetic; the interactive loop groups consecutive cosmetic changes by section so the user can batch-approve. |
| Embedding shortlist (Layer 4) misses a conceptual match | Layer 5 inverse audit catches it: any unmatched substantive change is reviewed for new-KRI need. |
| User stops mid-session | `decisions.jsonl` + incremental working Golden Set writes make resume seamless. |
| Section alignment fails (renumbered + retitled) | Fingerprint match on first 100 chars of section body. If still no match, surface to user as `section_alignment_uncertain`. |
| Camelot fails on amendment table | Fallback to plain pdfplumber + LLM parse. If still no table found, log "no amendment table" and proceed with Path B alone. |
| KRI regeneration panel produces lower-quality output than v1 | Panel-judging via Step 2.6 auto-judgment catches it. User reviews and rejects. v1 KRI stays in place with REANCHOR-only update if regeneration is rejected. |
