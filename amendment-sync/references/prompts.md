# LLM Prompt Templates — amendment-sync

All prompts are protocol-agnostic and document-type-agnostic (protocol, CMP, CSMP, IMP, PDHP, PV, SAP, PD_CLASS). They share a consistent CRA-framed neutral voice — no personas, no preamble, no scoring rubric beyond what is specified here.

---

## P1A — Amendment-History Table Parser

**When**: Phase 1 Path A — parsing the amendment summary at the start of the new document.

**Input**: first 30 pages of text (pdfplumber-extracted) from the new document + any Camelot-extracted tables from those pages.

**Prompt**:
```
You are reading the first 30 pages of a clinical-trial document. Some such
documents contain a structured summary of changes relative to the previous
version. Common headings include: "Amendment History", "Summary of Changes",
"Protocol Amendment Summary", "Document Revision History", "Schedule of
Amendments".

TASK
Locate the amendment summary if one exists. Parse every change row into the
JSON schema below. If no amendment summary exists, return {"found": false}.

For each change row, extract verbatim text — do not paraphrase. Do not invent
section numbers, page numbers, or rationales that are not in the source.

OUTPUT SCHEMA
{
  "found": true | false,
  "summary_location": {"page": N, "heading": "..."},
  "changes": [
    {
      "section_affected": "verbatim, e.g. 'Section 5.4.1 Dose Modification'",
      "change_type": "modified | added | removed | clarified",
      "description": "verbatim description from the table",
      "rationale": "verbatim rationale, or null if not provided",
      "page_in_new_doc": N
    }
  ]
}

RULES
- Do not classify a change as substantive vs cosmetic. That is Phase 1B's job.
- If the document has multiple amendments listed (Amendment 1, Amendment 2,
  ...), include changes from ALL amendments since the prior released version.
  The user-supplied "old version" determines the cutoff.
- If a section_affected is ambiguous (e.g., "throughout"), record it verbatim
  with section_affected: "throughout" — the downstream diff will resolve where.
```

---

## P1B — Diff-Hunk Semantic Classifier

**When**: Phase 1 Path B, Stage 2 — classifying each `difflib` hunk as cosmetic / rephrase / substantive.

**Input**: one diff hunk per call — `old_text`, `new_text`, plus ±200 chars of surrounding context from both versions.

**Prompt**:
```
You are classifying a single text-level difference between two versions of a
clinical-trial document.

INPUT
old_text:    "<verbatim old>"
new_text:    "<verbatim new>"
context_v1:  "<±200 chars old>"
context_v2:  "<±200 chars new>"

TASK
Classify the change as exactly one of:

  cosmetic
    Whitespace, punctuation, capitalization, formatting, page-break artifacts,
    typo fixes that do not change meaning. The semantic content is identical.

  rephrase_no_meaning_change
    The wording changed but the verifiable obligation is identical. Threshold
    numbers, drug names, doses, timing windows, scope, visit IDs, analytes,
    units, and procedural steps are all unchanged. Only the surface wording
    differs (synonym swap, voice change, sentence reorder, definition
    repositioned without redefining).

  substantive
    Any change to: a threshold value, a numeric quantity, a drug name or dose,
    a timing window (e.g., "within 24 hours" → "within 48 hours"), a visit ID
    or scope, an analyte, a procedural step, an eligibility criterion, an
    endpoint definition, a definitional boundary, a reporting obligation, a
    stopping rule, a population scope, a method, or any other content that
    would cause an LLM data-checker to return a different answer on the same
    subject record.

OUTPUT
{
  "semantic_kind": "cosmetic | rephrase_no_meaning_change | substantive",
  "reason": "≤30 words explaining the classification",
  "affected_facts": ["list of specific facts changed, e.g. 'timing window 24h→48h', empty if cosmetic/rephrase"]
}

RULES
- When uncertain between cosmetic and rephrase, choose rephrase.
- When uncertain between rephrase and substantive, choose substantive.
  Bias toward substantive — the cost of an under-classified change (missing a
  real KRI update) is higher than the cost of an over-classified one (an
  unnecessary review the user can dismiss in seconds).
- Do not consider whether the change is "important" or "worth reviewing". Every
  change flows through the interactive loop regardless of classification.
```

---

## P2L4 — Semantic Match Panel (Phase 2 Layer 4)

**When**: Phase 2 — identifying KRIs conceptually affected by a change that Layers 1–3 did not catch.

**Panel**: 6 agents — 3 Claude Sonnet + 3 Gemini 2.5 Pro. Run independently in parallel; consensus on output.

**Input per agent call**: one change unit + a shortlist of ≤30 candidate KRIs (selected by embedding similarity in `kri_embedder.py`).

**Prompt**:
```
You are assessing which KRIs from a Golden Set are conceptually affected by a
specific change between two versions of a clinical-trial document.

CHANGE
change_id:    "<CHG-NNN>"
section_v1:   "<section>"
section_v2:   "<section>"
old_text:     "<verbatim>"
new_text:     "<verbatim>"
semantic_kind: "<cosmetic | rephrase_no_meaning_change | substantive>"

CANDIDATE KRIs (shortlist by embedding similarity, ≤30 items)
[ {kri_id, category, kri_name, rule_for_llm, description, supporting_quote, protocol_reference}, ... ]

TASK
For each candidate KRI, decide whether it is conceptually affected by this
change — even if the KRI's reference or quote does not directly overlap the
changed text. Conceptual links include:

  - Shared defined term (the change modifies a term that the KRI uses)
  - Cross-section dependency (the KRI's rule depends on content in the changed
    section even if its cited reference is elsewhere)
  - Terminology rename (the change renames a term the KRI uses)
  - Related threshold or scope (the change modifies a value or scope the KRI
    references)
  - Visit / procedure scope dependency (the change adjusts which visits or
    procedures a rule applies to, and this KRI cites one of them)

EXCLUDE links that are merely topical co-mention. "Both mention LDL-C" is not a
conceptual link unless the change actually modifies content the KRI's rule
depends on.

OUTPUT
{
  "affected": [
    {"kri_id": "...", "reason": "≤25 words explaining the conceptual link"}
  ]
}

RULES
- Be specific in the reason. Vague reasons like "related to topic" are rejected
  at aggregation time.
- If no KRIs are affected, return {"affected": []}.
- Do not return KRIs not in the candidate shortlist.
```

**Aggregation**: a KRI is included in `affected_kris.json` based on agent count per the consensus table in `SKILL.md` Phase 2 Layer 4.

---

## P2L5 — Inverse Coverage Audit (Phase 2 Layer 5)

**When**: Phase 2 — for each change unit that produced zero matched KRIs across Layers 1–4, decide whether the change introduces a new obligation requiring a new KRI in v2.

**Input**: one change unit + full v2 section text + the full v1 Golden Set (compact form: `kri_id` + `rule_for_llm` + `category` only — small enough to fit).

**Prompt**:
```
A change between two document versions produced zero matched KRIs in the
Golden Set across all deterministic and semantic matching layers. Decide
whether this is correct (no KRI is needed) or whether v2 introduces a new
obligation requiring a new KRI.

CHANGE
<same fields as P2L4>

V2 SECTION CONTEXT
"<verbatim v2 section text>"

V1 GOLDEN SET (compact form for reference)
[ {kri_id, category, rule_for_llm}, ... ]

TASK
Decide one of:

  requires_new_kri
    The change introduces a verifiable obligation that v1 did not cover and
    that no existing KRI captures. Phase 4 will generate a new KRI for this
    content via scoped panel extraction.

  no_action_required
    The change is genuinely not KRI-relevant — e.g., a typo fix in an
    introductory paragraph, a clarification of a non-obligation sentence, a
    reformatting change in a non-rule section.

OUTPUT
{
  "decision": "requires_new_kri | no_action_required",
  "reason": "≤30 words explaining the decision",
  "proposed_domain": "SOA | ELIG | SAF | END | OPS | null"
}

RULES
- Apply the extractor's Domain Boundary Rules when proposing a domain.
- If decision is no_action_required, proposed_domain is null.
```

---

## P3.1 — Re-Anchor Panel

**When**: Phase 3.1 — a REANCHOR decision whose v1 `supporting_quote` no longer matches verbatim in the v2 section text.

**Panel**: 3 agents — 2 Claude Sonnet + 1 Gemini 2.5 Pro.

**Input per agent call**: v1 KRI (full record) + v2 section text + the KRI's `rule_for_llm`.

**Prompt**:
```
The supporting_quote of a v1 KRI no longer matches verbatim in the new
document version. The KRI's content is unchanged — only the surface wording of
the cited section has been edited. Find the verbatim v2 substring that
anchors the same obligation.

V1 KRI
{full v1 KRI record}

V2 SECTION TEXT
"<verbatim v2 section text>"

TASK
Return the verbatim substring (≤30 words) from V2 SECTION TEXT that anchors
the same obligation as the v1 supporting_quote. The substring must:

  - Be a verbatim substring of V2 SECTION TEXT (character-for-character).
  - Anchor the same obligation the v1 quote anchored (no scope drift, no
    threshold drift, no scope expansion or narrowing).
  - Not start or end with a double-quote character.
  - Be ≤30 words.

If no v2 substring satisfies all of the above, return NO_MATCH.

OUTPUT
{
  "v2_quote": "verbatim substring | null",
  "v2_page": N,
  "decision": "FOUND | NO_MATCH",
  "reason_if_no_match": "≤30 words"
}
```

---

## P3.2 — KRI Regeneration

Phase 3.2 (EDIT_PANEL, SPLIT, MERGE) and Phase 3.3 (NEW) **reuse the protocol-kri-extractor's Phase 2 panel infrastructure directly**. There is no separate prompt here. The skill invokes:

- `scripts/gemini_extract.py::run_gemini_extraction_multi_turn` for the Gemini half of the panel.
- The Claude Agent subagent pattern for the Claude half.
- `scripts/step2_6_autojudgment.py` for tier consensus + auto-judgment.

Scope is restricted to the v2 section affected by the change. The panel produces full KRI records per the extractor's schema. The interactive review then accepts / edits / rejects the proposals.

This reuse is intentional: every quality rule from the extractor (atomicity, domain boundaries, faithfulness, quote anchoring, SOA reference rules) applies automatically because the same scripts run with the same prompts.

---

## Tone, style, and consistency

- No personas. No "you are an expert in..." preambles.
- Output is JSON only when a schema is specified — no surrounding prose.
- Reasons are ≤25–30 words. Verbose reasoning is rejected.
- Verbatim text is verbatim — no smart quotes, no whitespace normalization, no truncation.
- All prompts are protocol-agnostic and document-type-agnostic — they MUST NOT reference specific protocol names, sponsors, therapeutic areas, or visit conventions.
