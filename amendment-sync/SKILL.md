---
name: amendment-sync
description: >
  Analyzes amendments and new versions of clinical-trial documents (protocols
  or accompanying docs — CMP/CSMP/IMP/PDHP/PV/SAP/PD_CLASS) and syncs an
  existing Golden Set to match the new version — without re-running the full
  extractor from scratch. Use this skill whenever a new version, revision, or
  amendment of a document is released and the user already has a validated
  Golden Set built from an older version. Takes the old document, the new
  document, and the old Golden Set as input. Identifies every change between
  the two versions in two complementary ways: (1) parses any "Amendment
  History" / "Summary of Changes" table at the start of the new document, and
  (2) runs a section-aligned full-document diff to catch every difference at
  any granularity — including single-word edits, rephrases, cosmetic edits,
  and substantive content changes. Locates the KRIs in the Golden Set that
  are affected by each change using a 5-layer matching strategy (reference,
  quote, context-window, semantic LLM panel, inverse coverage audit). Runs a
  fully interactive change-by-change review loop with the user to decide
  per-KRI disposition (keep / re-anchor / edit / split / merge / remove /
  add-new) and applies edits directly to a working copy of the Golden Set.
  Saves the resulting Golden Set with the new document version number.
  Trigger on: "new amendment", "amendment N", "v2/v3/v4 of [protocol]", "new
  version of [document]", "sync the golden set", "update the golden set for
  the new version", "the protocol was revised".
---

# amendment-sync — Sync a Golden Set to a New Document Version

## Ultimate Goal

This skill **migrates an existing Golden Set forward to a new document version**, preserving everything that did not change in the document, and updating only the KRIs whose source content changed. The deliverable is a versioned Golden Set (`golden_set_v<N>.json` + `Extracted_KRIs_v<N>.xlsx`) that reflects the new document version, plus a complete migration report showing every decision made.

The skill never re-extracts from scratch. It is a targeted, change-driven update tool that runs interactively change-by-change with the user.

---

## ⚠️ META-RULE — Skill Updates Are Additive Only (NEVER violate this)

Every refinement, update, or improvement to this skill is **additive**. It adds to what is already defined. It never removes, overwrites, or silently replaces previous rules. The same no-removal rule documented in `protocol-kri-extractor/SKILL.md` applies here:

- Never delete a rule that was not explicitly requested to be deleted
- Never skip, defer, or reorder any step for speed, efficiency, brevity, or convenience — if it is documented here, it runs in full
- Never weaken mandatory language ("MUST", "BLOCKING", "mandatory") into optional language
- Every change is preserved through an explicit user instruction or surfaces a conflict to the user

This rule applies to Claude when editing this file, and to the skill pipeline itself when running an update.

---

## ⚠️ MANDATORY — Universal change capture (no change is too small)

**Every difference between the two document versions is a change** — including single-word edits, punctuation, capitalization, reordering, formatting that affects text extraction, and rephrases that do not change meaning. The skill MUST capture every such difference in Phase 1 and propagate it into the Golden Set in Phase 4. The user explicitly directed that even text-only changes (no conceptual or significant change) must result in updating the relevant KRIs so that the Golden Set's content stays verbatim-aligned with the latest document version.

No change is silently dropped on the grounds of being "cosmetic" or "trivial". A change may be *classified* as cosmetic/rephrase/substantive (this controls how it is reviewed and whether the panel needs to regenerate the KRI's rule text vs. only re-anchor the reference/quote), but every classification still flows through the interactive review and applies its appropriate update to the affected KRIs.

---

## Inputs

| Argument | Description |
|---|---|
| `--old-doc` | Path to the old document PDF (the version the existing Golden Set was built from). |
| `--new-doc` | Path to the new document PDF (the version we are migrating to). |
| `--golden` | Path to the existing `golden_set.json` (or directly to the run directory containing `extracted_kris.json` + `raw_{DOMAIN}.json` + `manifest.json` + `footnote_map.json`). |
| `--new-version` | New document version label as it should appear in output filenames (e.g., `v4.0`, `Amendment-3`, `2026-05-rev`). User-supplied; no parsing assumption. |
| `--doc-type` | Optional. `protocol` (default) or `accompanying` (CMP/CSMP/IMP/PDHP/PV/SAP/PD_CLASS). Selects the matching extractor's prompts/sub-areas when Phase 4 needs to regenerate KRIs. |
| `--out` | Output directory. Canonical: `~/Downloads/amendment-sync/<protocol_id>/<old_version>_to_<new_version>/`. |

### Pre-flight integrity check (MANDATORY, BLOCKING)

Before Phase 1 begins, run a sanity check that the v1 Golden Set actually corresponds to the old document:

1. Sample 10 random KRIs from the Golden Set.
2. For each, run `pdfplumber` verbatim verification of `supporting_quote` against the **old** document at the cited page (Step 3D logic from the extractor).
3. If <9/10 quotes match verbatim → STOP. The Golden Set does not correspond to the supplied old document. Report the mismatch and ask the user to confirm inputs.

This check prevents the catastrophic failure mode where a user supplies a Golden Set built from a different document version and the update silently applies wrong edits.

---

## Output

The final deliverable is a versioned Golden Set written to the output directory:

| File | Description |
|---|---|
| `golden_set_<new_version>.json` | The updated Golden Set, with all interactive decisions applied. Schema identical to the original `extracted_kris.json`. |
| `Extracted_KRIs_<new_version>.xlsx` | Excel workbook, same column structure as the extractor. One sheet per domain (SOA, ELIG, SAF, END, OPS, NDEF). |
| `migration_report.json` | Every change unit + every affected KRI + every interactive decision made + before/after diffs per KRI. Audit trail. |
| `change_set.json` | Phase 1 output — all detected changes from both detection paths, before any KRI mapping. |
| `affected_kris.json` | Phase 2 output — change-to-KRI matches with per-match layer + confidence + explanations. |
| `decisions.jsonl` | Append-only log of every interactive decision (one line per decision), written as the user makes each call. Crash-safe — if the session is interrupted, the skill resumes from the last logged decision. |
| `removed_kris.json` | All KRIs removed during the update, with rationale and v1 reference preserved. Never silently deleted. |

Every KRI in `golden_set_<new_version>.json` carries provenance fields:

```json
{
  "kri_id": "SAF-003",
  "...standard fields...",
  "version_metadata": {
    "origin_v1_kri_id": "SAF-003",
    "change_ids": ["CHG-014"],
    "disposition": "EDITED",
    "fields_changed": ["rule_for_llm", "supporting_quote", "protocol_reference"],
    "decision_timestamp": "2026-05-11T14:33:00Z"
  }
}
```

For unchanged KRIs, `change_ids: []`, `disposition: "UNCHANGED"`, `fields_changed: []`. For new KRIs added in v2, `origin_v1_kri_id: null`, `disposition: "NEW"`.

---

## Phase 1 — Change Detection (dual-path, both mandatory)

Both detection paths run on every update. Neither is optional. Their outputs merge into a single `change_set.json`.

### Path A — Amendment-history table parse

Many protocols include a structured change summary near the start of the document, under headings like:
- "Amendment History"
- "Summary of Changes"
- "Protocol Amendment Summary"
- "Document Revision History"
- "Schedule of Amendments"

**Process** (`scripts/amendment_table_parser.py`):

1. Extract the first 30 pages of the new document with `pdfplumber` + `camelot` (for any tabular amendment summary).
2. Run an LLM pass (Claude Sonnet) over the extracted text to locate the amendment summary and parse it into structured rows:
   ```json
   {
     "change_id": "AMEND-CHG-001",
     "source": "amendment_table",
     "section_affected": "5.4.1 Dose Modification",
     "change_type": "modified | added | removed | clarified",
     "description": "verbatim text from the amendment table",
     "rationale": "verbatim rationale if provided",
     "page_in_new_doc": 12
   }
   ```
3. If no amendment table is found, log explicitly: `"amendment_table": null` in `change_set.json._meta`. Proceed to Path B alone. **Never fail the run because no amendment table exists** — most accompanying docs and some protocols do not have one.

**Output**: `amendment_table_changes.json` (intermediate, also rolled into `change_set.json`).

### Path B — Section-aligned full-document diff

This path is the line-level safety net. It catches everything Path A misses (and Path A misses a lot — sponsors often understate changes in the amendment table).

**Process** (`scripts/section_aligned_diff.py`):

1. **Build section maps for both documents.** Reuse `protocol-kri-extractor`'s Step 1A `step1a_manifest.py` logic. Output: `manifest_v1.json` and `manifest_v2.json` — section number → page range.

2. **Align sections across versions.** For each section in v1, find its counterpart in v2 by:
   - Exact section number match (`5.4.1` ↔ `5.4.1`)
   - Fuzzy title match when numbers shift (e.g., section renumbered)
   - Title + first-100-character fingerprint similarity for cases where both number and title changed
   Output: `section_alignment.json` with per-section pair + confidence. Sections in v1 with no v2 counterpart → flagged as `section_removed`. Sections in v2 with no v1 counterpart → flagged as `section_added`.

3. **Per aligned section pair, run two-stage diff:**
   - **Stage 1 (deterministic)**: Python `difflib.SequenceMatcher` on normalized text (collapse whitespace, normalize curly quotes, strip page headers/footers). Emit every insertion, deletion, replacement at sentence granularity.
   - **Stage 2 (semantic classification)**: For each diff hunk from Stage 1, an LLM call classifies the change:
     - `cosmetic` — whitespace, punctuation, capitalization, formatting only. NO semantic difference.
     - `rephrase_no_meaning_change` — wording changed but the verifiable obligation is identical.
     - `substantive` — the obligation, threshold, scope, timing, or value changed.
   Per the universal change capture rule, **all three classes are kept** — `cosmetic` and `rephrase` still propagate into KRI text updates so the Golden Set stays verbatim-aligned. The classification only controls downstream behavior (re-anchor only vs. full regenerate).

4. **For `section_added` (new in v2):** the entire section is captured as one or more `new_content` change units. These feed into Phase 4 net-new extraction.

5. **For `section_removed` (gone from v2):** captured as `removed_section` change units. Every KRI citing this section will be surfaced for removal in Phase 3.

**Output**: `diff_changes.json` (intermediate) with one record per change unit:
```json
{
  "change_id": "DIFF-CHG-NNN",
  "source": "diff",
  "section_v1": "5.4.1",
  "section_v2": "5.4.1",
  "page_v1": 65,
  "page_v2": 67,
  "change_type": "modified | added | removed",
  "semantic_kind": "cosmetic | rephrase_no_meaning_change | substantive",
  "old_text": "verbatim v1 text",
  "new_text": "verbatim v2 text",
  "context_v1": "±200 chars surrounding v1 text",
  "context_v2": "±200 chars surrounding v2 text"
}
```

### Merge: `change_set.json`

The two paths' outputs are unioned, with overlap detection:

- A diff change unit whose `section_v2` + page overlaps an amendment-table row's `section_affected` is merged. The merged record carries `source: ["amendment_table", "diff"]` and `confidence: high` (both paths agree).
- Diff-only changes carry `source: ["diff"]`, confidence determined by `semantic_kind` (substantive = high, rephrase = medium, cosmetic = low).
- Amendment-table-only changes (table mentions a change but diff did not catch it) carry `source: ["amendment_table"]`, confidence: medium — and trigger a re-diff of the cited section with more aggressive sensitivity, because if the sponsor says a section changed, the diff should have caught it; failure to do so means our diff missed something subtle (e.g., a moved sentence).

**Gating**: `change_set.json` must exist and be non-empty before Phase 2 begins. An empty change set means the two documents are identical at the text level — in which case the skill prints a confirmation message and exits without writing a new Golden Set.

---

## Phase 2 — Affected-KRI Mapping (5-layer matching)

For each change unit in `change_set.json`, identify the KRIs in the v1 Golden Set that are conceptually or textually affected. Use all 5 layers; **never rely on one**. Each layer catches what the others miss.

### Layer 1 — Reference anchor (deterministic, high precision)

For each change unit, pull every KRI whose `protocol_reference` cites the affected v1 section or page. Direct hit.

- Match rule: KRI's `protocol_reference` contains `section_v1` (as substring after normalization) OR cites a page within `page_v1 ± 0` (exact page) OR the KRI's reference page range intersects `page_v1`.
- Output: `{change_id, kri_id, layer: "L1-reference", confidence: "high"}` per match.

### Layer 2 — Quote substring match (deterministic, high precision when it fires)

For each change unit, search every KRI's `supporting_quote` against the `old_text` of the change.

- Match rule: `norm(kri.supporting_quote)` is a substring of `norm(change.old_text)` OR `norm(change.old_text)` is a substring of `norm(kri.supporting_quote)`. `norm()` = collapse whitespace + normalize quotes (same `norm()` used in `step3d_verify.py`).
- This is the strongest possible link — the KRI's evidence text literally is (or contains) the text that changed.
- Output: `{change_id, kri_id, layer: "L2-quote", confidence: "high"}`.

### Layer 3 — Reverse lookup via KRI context window (deterministic, catches L1/L2 gaps)

For every KRI, pre-compute its **context window** in v1: the full text of its cited page(s) ±1 page. Then for each change unit, check whether `change.old_text` falls inside any KRI's context window.

- Match rule: `norm(change.old_text) in norm(kri.context_window_v1)`.
- Catches KRIs whose strict reference doesn't include the changed page (e.g., reference says §5.4.1 p.65 but the change is on p.66 of the same logical block).
- Catches SoA KRIs whose footnote text falls in the context window.
- Output: `{change_id, kri_id, layer: "L3-context", confidence: "medium"}` (medium because the link is positional, not semantic).

### Layer 4 — Semantic / conceptual match (LLM multi-model panel)

A 6-agent panel (3 Claude Sonnet + 3 Gemini 2.5 Pro) is the safety net for conceptual links that Layers 1–3 miss.

**Shortlist construction (critical efficiency step):** for each change unit, compute embedding similarity between the change's text (`old_text` + `new_text` + `context_v1`) and every KRI's `rule_for_llm + description + supporting_quote`. Take the top-K KRIs by cosine similarity (default K=30, configurable). Use OpenAI `text-embedding-3-small` or Gemini embeddings — see `scripts/kri_embedder.py`.

The shortlist is only fed to the panel if the KRI is not already matched by Layers 1–3 (deduplication). The panel sees ≤30 candidates per change.

**Panel prompt** (`references/prompts.md` → `semantic_match_panel`):
- Input: the change unit + the shortlist of candidate KRIs.
- Question: "Which of these KRIs are conceptually affected by this change, even if their reference or quote does not directly overlap? Conceptual links include: shared defined terms, terminology renames, cross-section dependencies, related thresholds, related visit/procedure scope."
- Output per agent: list of `{kri_id, reason ≤25 words}` for KRIs the agent considers affected.

**Consensus:**

| Agents flagging a KRI | Confidence |
|---|---|
| ≥4 of 6 | medium-high — surfaced in the interactive review as a confident semantic hit |
| 2–3 of 6 | low-medium — surfaced with explicit caveat ("speculative semantic match") |
| 1 of 6 | logged in `affected_kris.json.low_confidence` but NOT surfaced in the interactive review unless the user explicitly enables `--show-speculative-matches`. The user can audit the low-confidence list at any time. |
| 0 of 6 | not surfaced |

### Layer 5 — Inverse coverage audit (catches structural gaps)

After Layers 1–4 produce affected KRIs per change, run an inverse audit:

- **For every substantive change unit with zero matched KRIs (across all 4 layers):** ask the panel "Should this change have produced a v2 KRI? Was there really no v1 KRI tied to this content?" Two possible outcomes:
  - **Panel says yes, the change introduces a new obligation that v1 did not cover** → mark the change as `requires_new_kri: true` for Phase 4 net-new extraction.
  - **Panel says no, this change does not need a KRI** (e.g., it's a typo fix in an introductory paragraph) → log and move on.
- **For every KRI that appears in many change matches (≥5):** consolidate so the interactive review surfaces the KRI once with all its affecting changes, not once per change.

### Output — `affected_kris.json`

```json
{
  "_meta": {
    "total_changes": 87,
    "changes_with_matches": 62,
    "changes_no_match_requires_new_kri": 9,
    "changes_no_match_no_action": 16,
    "total_kris_v1": 312,
    "kris_affected": 78,
    "kris_unchanged": 234
  },
  "matches": [
    {
      "change_id": "CHG-014",
      "matched_kris": [
        {
          "kri_id": "SAF-003",
          "match_layers": ["L1-reference", "L3-context", "L4-semantic"],
          "confidence": "high",
          "match_explanations": {
            "L1": "Reference cites §5.4.1 p.65; change is in §5.4.1 p.65",
            "L3": "Change text overlaps KRI context window",
            "L4": "5/6 agents flagged this KRI as conceptually affected"
          }
        }
      ]
    }
  ],
  "requires_new_kri": [
    {"change_id": "CHG-022", "section_v2": "5.5 (new)", "reason": "..."}
  ],
  "low_confidence_speculative": [
    {"change_id": "CHG-031", "kri_id": "OPS-018", "agent_count": "2/6", "reason": "..."}
  ]
}
```

---

## Phase 3 — Interactive Review Loop (the core of the skill)

This is where the skill spends most of its time with the user. The loop is fully interactive — change-by-change, live, with the user deciding every action.

### Loop structure

For each change unit in `change_set.json`, in order (sorted by section, then page, then change_id):

1. **Present the change to the user.** Render:
   - Change ID and source(s) (`amendment_table`, `diff`, or both).
   - Section reference: v1 location → v2 location.
   - `semantic_kind` classification.
   - Side-by-side: `old_text` vs `new_text` with character-level diff highlighting.
   - Surrounding context from both versions.
   - Amendment table description + rationale if applicable.

2. **Present the affected KRIs** (from `affected_kris.json`). For each affected KRI:
   - Full v1 KRI record (all fields).
   - Match metadata: which layers fired, confidence, explanations.
   - The KRI's current `supporting_quote` and `protocol_reference`, with annotation if the quote no longer matches verbatim in v2.

3. **Per-KRI decision menu.** The user chooses one of:

   | Decision | Action |
   |---|---|
   | `KEEP` | The change does not actually affect this KRI. KRI unchanged in v2 Golden Set. Reason logged. |
   | `REANCHOR` | The KRI's content is unchanged but the reference/quote needs updating (e.g., page shifted, sentence reworded with same meaning). Re-bind `supporting_quote` + `protocol_reference` to v2 — either deterministically (if the quote still exists verbatim in v2) or via a panel-assisted re-anchor (Phase 3.1 below). |
   | `EDIT` | The KRI's rule_for_llm, description, kri_name, supporting_quote, and/or protocol_reference need to change to reflect v2. Two sub-modes: `EDIT_MANUAL` (user types the new text directly) and `EDIT_PANEL` (invoke a multi-model panel to regenerate per Phase 3.2 below; user reviews and accepts/refines the proposal). |
   | `SPLIT` | The change atomized a previously-combined obligation. The v1 KRI becomes N v2 KRIs. Each new KRI is generated via Phase 3.2 panel. |
   | `MERGE` | Two v1 KRIs became one in v2 (rare but possible — e.g., two criteria consolidated). User selects which KRIs to merge; panel generates the merged KRI. |
   | `REMOVE` | The rule was deleted in v2 (procedure cancelled, criterion removed, section deleted). KRI moves to `removed_kris.json` with rationale + change_id. NOT silently deleted. |
   | `DEFER` | The user is unsure and wants to skip this KRI for now. Logged with `deferred: true`; surfaced again in a final pass at the end of Phase 3. |

4. **Net-new KRI prompt** (for change units flagged `requires_new_kri` in Phase 2). The user is shown the new v2 content and asked to confirm extraction. If confirmed, Phase 3.3 generates the new KRI(s) via panel; user reviews and accepts.

5. **Log decision immediately** to `decisions.jsonl` (one line per decision, JSON object). This is the crash-safe checkpoint — if the session terminates, resume reads `decisions.jsonl` and skips already-decided changes/KRIs.

6. **Apply edit to working copy of the Golden Set** immediately after the decision is logged. The Golden Set on disk is mutated incrementally. At any point during the loop, `golden_set_working.json` reflects the user's accumulated decisions.

### Phase 3.1 — Panel-assisted re-anchor (REANCHOR decision)

When a KRI is REANCHORed and its v1 quote no longer matches verbatim in v2:

1. Run a deterministic search first: try fuzzy substring match on v2 cited section (e.g., 90% token overlap). If found → propose the v2 substring as the new quote.
2. If deterministic search fails, dispatch to a 3-agent panel (2 Claude + 1 Gemini) with: v1 quote, v2 section text, KRI's `rule_for_llm`. Each agent returns the verbatim v2 substring (≤30 words) that anchors the same obligation, or `NO_MATCH`.
3. Show the proposed new quote to the user; user accepts, edits, or rejects.
4. On accept: update `supporting_quote` + `protocol_reference` + `combined_ref` + `additional_footnotes` (if applicable). Run `step3d_verify.py` logic on the new quote against v2 PDF before saving.

### Phase 3.2 — Panel-assisted regeneration (EDIT_PANEL, SPLIT, MERGE decisions)

When the user opts for panel regeneration:

1. Dispatch to the **same multi-model panel infrastructure** as `protocol-kri-extractor`'s Phase 2 (5 Claude + 5 Gemini). Reuse `scripts/gemini_extract.py` and the existing Claude subagent pattern. Scope: ONLY the v2 section affected by this change.
2. Apply the same Step 2.6 auto-judgment (`scripts/step2_6_autojudgment.py`) — verification gate, atomicity, dedup, 6-judge panel, aggregate.
3. Present the regenerated KRI(s) to the user with the panel verdict and tier.
4. User accepts, edits, or rejects. On accept → write to working Golden Set.

This reuses the extractor's quality bar — the same atomicity rules, domain boundary rules, quote anchoring rules, and faithfulness rules — without duplicating the logic in this skill.

### Phase 3.3 — Net-new KRI generation (NEW decision)

For change units flagged `requires_new_kri`:

1. Identify the v2 section/page containing the new content.
2. Determine likely domain (SOA / ELIG / SAF / END / OPS) using the extractor's Domain Boundary Rules.
3. Dispatch a scoped panel run (same as Phase 3.2) against just the new section text.
4. Run Step 2.5 obligation inventory and Step 2.6 auto-judgment.
5. Present the proposed new KRI(s) to the user; user accepts, edits, or rejects.
6. On accept → append to the appropriate domain in the working Golden Set with `disposition: "NEW"`, `origin_v1_kri_id: null`, `change_ids: [CHG-XXX]`.

### Phase 3 gating

The loop completes when:
- Every change unit has been processed (or explicitly deferred).
- Every deferred item has been revisited in the final pass.
- The user confirms "done" with Phase 3.

---

## Phase 4 — Apply Edits & Validate

After Phase 3 completes, the working Golden Set already reflects every interactive decision. Phase 4 runs the terminal validation passes scoped appropriately.

### Step 4.1 — Verbatim verification (100%, MANDATORY, BLOCKING)

Run `scripts/step3d_verify.py` (from the extractor) against the **new** document PDF on the **entire** working Golden Set — not just changed KRIs.

- Why on the entire set: KRIs marked UNCHANGED still need verification, because page numbers shift between versions and pdfplumber text extraction can differ even for unchanged sentences.
- Output: `verify_report_v<N>.json`.
- Gating: 100% pass required before Step 4.2. Any FAIL triggers a corrective sub-loop — surface the failing KRI to the user, who can REANCHOR (Phase 3.1 logic) or EDIT.

### Step 4.2 — Accuracy panel on changed and new KRIs (Step 3B logic, scoped)

Run `scripts/step3b_accuracy.py` against the new document, but **scoped to KRIs whose disposition is EDITED, SPLIT, MERGE, or NEW** in this update. Unchanged KRIs were already accuracy-judged in the original extraction and do not need re-judging.

- Why not also run on UNCHANGED: cost. The extractor's Step 3B is 100% coverage; re-running it on a Golden Set that only changed in 78/312 KRIs wastes ~75% of judging budget. The reanchor verification in Step 4.1 is sufficient for unchanged KRIs.
- Output: `accuracy_report_v<N>.json` covering the changed/new subset.
- Gating: 0 FAIL, 0 unresolved FLAG on the scoped subset.

### Step 4.3 — Dedup pass (100%, MANDATORY)

Run `scripts/step4a_dedup.py` against the working Golden Set. Dedup runs globally because edits and additions can introduce cross-domain duplicates that did not exist in the v1 set.

- Output: `dedup_report_v<N>.json`.

### Step 4.4 — NDEF sweep (100%, MANDATORY)

Run `scripts/step4a_ndef_sweep.py` on the working Golden Set. New or edited KRIs may have crossed the definable/non-definable boundary in either direction.

- Output: `ndef_sweep_report_v<N>.json`.

### Step 4.5 — Final assembly

Run `scripts/step4a_assemble.py` to produce the final `Extracted_KRIs_<new_version>.xlsx` from the working Golden Set. Column structure exactly matches the extractor:

| Column | Field | Width |
|--------|-------|-------|
| KRI ID | `kri_id` | 16 |
| Category | `category_label` | 28 |
| KRI Name | `kri_name` | 34 |
| Description | `description` | 52 |
| Rule for LLM | `rule_for_llm` | 60 |
| Protocol Reference & Quote | `combined_ref` | 90 |
| Severity | `severity` | 12 |

No "Domain" column. No separate "Protocol Reference" or "Supporting Quote" column. `combined_ref` is the single source for the reference column. NDEF KRIs use the same column format.

---

## Phase 5 — Save as v{N}

Final outputs are written to the run directory with the new version label in their filenames:

- `golden_set_<new_version>.json`
- `Extracted_KRIs_<new_version>.xlsx`
- `migration_report.json` (assembled from `decisions.jsonl` + change set + match data + before/after KRI diffs)

The skill prints a final summary:

```
GOLDEN SET UPDATE COMPLETE — <protocol_id> <old_version> → <new_version>

Changes detected:      87 (43 substantive, 31 rephrase, 13 cosmetic)
KRIs unchanged:        234
KRIs edited:           42
KRIs split:             5
KRIs merged:            2
KRIs removed:           9
KRIs added (new):      11

Total v1 KRIs:        312
Total v<new> KRIs:    321

Verbatim verification: 100% pass
Accuracy panel:        100% pass on changed/new subset
Dedup:                 4 cross-domain duplicates removed, 2 kept_despite_similarity
NDEF sweep:            1 KRI moved into NDEF, 0 moved out

Outputs:
  - <out_dir>/golden_set_<new_version>.json
  - <out_dir>/Extracted_KRIs_<new_version>.xlsx
  - <out_dir>/migration_report.json
```

---

## Quality rules (apply at every step)

1. **Provenance is not optional**: every KRI in the v2 Golden Set MUST carry `version_metadata` with `origin_v1_kri_id`, `change_ids`, `disposition`, `fields_changed`. Missing provenance is a pipeline error.
2. **Nothing is silently dropped**: every REMOVED KRI lives in `removed_kris.json` with rationale and v1 reference. Every change unit with no action lives in `migration_report.json` with explicit `"action": "no_action_required"` + reason.
3. **Reuse, don't reimplement**: Phase 3.1/3.2/3.3 and Phase 4 invoke the extractor's existing scripts (`gemini_extract.py`, `step2_6_autojudgment.py`, `step3b_accuracy.py`, `step3d_verify.py`, `step4a_dedup.py`, `step4a_ndef_sweep.py`, `step4a_assemble.py`) — they are not reimplemented here. This skill is orchestration + diff + matching + interactive review; the heavy lifting is the extractor's panels.
4. **Crash-safe**: `decisions.jsonl` is append-only; the working Golden Set is mutated incrementally after each decision. A crashed session resumes by re-reading the change set, skipping decisions already in `decisions.jsonl`, and continuing the loop.
5. **Every change matters**: cosmetic/rephrase changes still flow through the loop and still update KRI text so the Golden Set's `supporting_quote` stays verbatim-aligned with the latest document.
6. **Reference + quote re-binding is deterministic-first**: REANCHOR tries pdfplumber substring match before invoking the panel. The panel is only used when the deterministic search fails.
7. **Match transparency**: every affected-KRI surface to the user shows which layers fired and why. The user can dismiss low-confidence semantic matches with one keystroke.
8. **Inputs are validated before Phase 1**: the pre-flight integrity check (≥9/10 v1 quotes verbatim in old doc) is BLOCKING. A mismatched Golden Set never enters the pipeline.

---

## Reference files

- `references/prompts.md` — LLM prompt templates: amendment-table parser, semantic-kind classifier, semantic-match panel, re-anchor panel.
- `references/methodology.md` — extended methodology notes: the 5-layer matching rationale, the change-classification taxonomy, the interactive-loop UX.
- `scripts/run.py` — orchestrator. Single canonical entry point. Enforces phase order and gating.
- `scripts/amendment_table_parser.py` — Phase 1 Path A (amendment-history table parse).
- `scripts/section_aligned_diff.py` — Phase 1 Path B (section-aligned full-document diff).
- `scripts/change_merger.py` — Phase 1 merger producing `change_set.json` from both paths.
- `scripts/kri_matcher.py` — Phase 2 Layers 1–3 (deterministic match: reference, quote, context window).
- `scripts/kri_embedder.py` — Phase 2 embeddings + shortlist construction for Layer 4.
- `scripts/semantic_match_panel.py` — Phase 2 Layer 4 panel (6-agent semantic match) + Layer 5 inverse audit.
- `scripts/interactive_review.py` — Phase 3 interactive loop driver.
- `scripts/reanchor.py` — Phase 3.1 panel-assisted re-anchor.
- `scripts/regenerate_kri.py` — Phase 3.2 panel-assisted regeneration (invokes extractor scripts).
- `scripts/migration_report.py` — Phase 5 final report assembly.

---

## How to run

### Setup (first time only)
```bash
pip install pdfplumber pymupdf camelot-py[cv] opencv-python-headless openpyxl rapidfuzz --break-system-packages -q
# Ensure protocol-kri-extractor scripts are accessible — Phase 3.2/3.3 and Phase 4 invoke them directly.
```

### Full pipeline command (canonical entry point)
```bash
python /Users/ofir/.claude/skills-repo/amendment-sync/scripts/run.py \
  --old-doc /path/to/protocol_v3.0.pdf \
  --new-doc /path/to/protocol_v4.0.pdf \
  --golden  /path/to/extractor/<protocol_id>/<v3_run>/extracted_kris.json \
  --new-version v4.0 \
  --doc-type protocol \
  --out ~/Downloads/amendment-sync/<protocol_id>/v3.0_to_v4.0/
```

### Resume an interrupted run
```bash
python run.py --old-doc ... --new-doc ... --golden ... --new-version ... --out <same-dir> --resume
```
The orchestrator reads `decisions.jsonl` and `change_set.json` from the existing output directory and resumes the interactive loop where it stopped.

### Modes

- Default (no flag): **interactive** — every change goes through the user.
- `--show-speculative-matches`: include Layer 4 low-confidence (2–3/6) semantic matches in the interactive loop instead of just logging them.
- `--dry-run`: run Phase 1 + Phase 2 only; produce `change_set.json` + `affected_kris.json` but skip the interactive loop. Useful for previewing scope before committing to a session.

---

## Relationship to `protocol-kri-extractor`

This skill is **complementary**, not a replacement. The extractor produces Golden Sets from scratch; this skill migrates them forward across document versions. The two skills share:

- KRI schema (output structure).
- Domain definitions (SOA / ELIG / SAF / END / OPS / NDEF).
- Atomicity rules, domain boundary rules, faithfulness rules, quote anchoring rules.
- Validation scripts (`step3b_accuracy.py`, `step3d_verify.py`, `step4a_dedup.py`, `step4a_ndef_sweep.py`, `step4a_assemble.py`).
- Multi-model panel infrastructure (`gemini_extract.py`, `step2_6_autojudgment.py`).

This skill does NOT modify the extractor's files or behavior. If a rule from the extractor changes, this skill picks it up automatically by virtue of invoking the extractor's scripts at Phase 3.2/3.3/4.
