---
name: rule-deviation-mapper-resolve
description: >
  Refines an existing clinical-trial Golden Set so its rules catch the real,
  protocol-grounded deviations they are supposed to — driven by a
  deviation-to-rule mapping (the "Extend (partial)" and "No match" tabs). Use
  this skill whenever the user has a Golden Set (KRI rules with a "Rule for
  LLM" column) PLUS a deviation mapping file showing which deviations a rule
  partially covers ("Extend (partial)") or no rule covers ("No match"), and
  wants the rules improved/expanded so they capture the correct deviations.
  The protocol PDF is the ONLY source of truth: the skill never bends a rule
  to fit a deviation that the protocol does not ground; the mapping is a
  diagnostic to verify coverage, not a to-do list. Works family-by-family
  (one procedure across all its visits), editing ONLY the "Rule for LLM" cell
  of existing rules; for "No match" it may also author NEW rules in the exact
  Golden-Set format, but only where the protocol grounds them. Every family
  follows a mandatory ritual: read all cited deviation rows + the governing
  protocol text, propose the fix, show a traceability table (each cited line
  -> rule + clause, with totals of mapped vs not-mapped and the rule IDs being
  corrected), get explicit approval, then apply in place and save. Trigger on:
  "fix the golden set against the deviations", "extend partial tab", "no match
  tab", "deviation coverage", "make the rules catch these deviations", "map
  deviations to rules".
---

# rule-deviation-mapper-resolve — Make Golden-Set rules catch the right deviations

## Ultimate Goal

Take a **Golden Set** of monitoring rules and a **deviation→rule mapping**, and improve each rule's `Rule for LLM` so it catches the **real, protocol-grounded** deviations it is supposed to — **comprehensively and durably**, not narrowly fitted to the specific incidents. The deliverable is the **same Golden Set file**, edited in place, where every relevant rule now covers the protocol-grounded deviations for its procedure, and every deviation that is *not* protocol-grounded is consciously left uncovered with a recorded reason.

This skill is **interactive and family-by-family**. It never re-extracts from scratch; it surgically improves existing rules (and, in the "No match" phase, may author new rules — only when the protocol grounds them).

---

## ⚠️ META-RULES — never violate, additive only

Every refinement to this skill is **additive** — it adds to what is here, never removes/weakens it. The following rules are **BLOCKING** and apply to every run:

1. **The protocol is the ONLY source of truth.** A sponsor-logged deviation that the protocol does not ground is **irrelevant** — we do **not** change or add a rule to match it. We never distort/bend a rule to absorb a deviation. The mapping exists to *verify that rules catch the correct (protocol-grounded) deviations* — nothing more. Sponsors make mistakes; the protocol decides.
2. **Edit scope (Phase 1 + Track A): the `Rule for LLM` cell ONLY.** Never touch any other column. Never touch a rule that is not relevant. Never delete or add a rule. (Authoring NEW rules is permitted **only** in Phase 2 / Track B, and only in the exact existing Golden-Set format.)
3. **Stay in the existing `Rule for LLM` format.** Use only keys already present in the schema (`intent / applies_to / evidence_expected / acceptance{timing, required, conditional, trigger, pass, preferred, override} / deviation / provenance`). Never invent new sub-keys. Do not omit existing important content; do not distort the format.
4. **Expand, don't narrow.** Write rules broad/comprehensive enough to catch *future* deviations of the same type. Do not over-fit ("hang") the wording on the specific cited incidents.
5. **Mandatory pre-edit ritual — automatic, every family (do NOT wait to be asked):** before any edit, show the **traceability table** + the **list of rule IDs being corrected** + **ask for explicit approval**. Only edit after approval. (Full ritual in `## The mandatory ritual`.)
6. **Save in place + confirm.** After approval and edit: overwrite the same file (no backup copies/renames), keep the wrapped/readable view, and explicitly say **"saved to the file."** The next family builds on the just-saved file.

See `references/core_principles.md` for the full rationale and the complete "what to leave uncovered" catalogue.

---

## Inputs (confirm these before starting)
- **Golden Set** xlsx — sheets per domain (e.g. SOA / ELIG / SAF / OPS). The editable field is the **`Rule for LLM`** cell.
- **Deviation→rule mapping** xlsx — tabs `Matched`, `Extend (partial)`, `No match`. Columns include `deviation_ref, site, subject, client_category, severity, description`, and (for partial) `rule_id, rule_name, modification_suggestion, alternates, confidence, rationale`.
- **Protocol PDF** — the source of truth. Read targeted page ranges per family.

**Line-number convention:** when the user cites mapping "lines", they mean **spreadsheet rows, header = row 1, first deviation = row 2**. Read back each row's `deviation_ref` so alignment is confirmed.

---

## Phase 1 — "Extend (partial)" : refine existing rules, family by family

The user names a **procedure family** (`rule_name`) + the mapping **line numbers**. Then:

1. **Read every cited row in full** (all columns — not just description/suggestion/rationale).
2. **Inventory** every Golden-Set rule for that procedure across **all visits** (the cited ones AND the transverse siblings that weren't flagged). Read their current `Rule for LLM`.
3. **Read the protocol** section/footnote(s) that govern the procedure; extract the real requirement(s).
4. **Diagnose gaps** — cluster the cited deviations by **underlying principle** (not the incident).
   - **Fix-size calibration:** if N deviations fail for the **same** reason → one small, targeted addition catches them all. If they fail for **different** reasons → a comprehensive, multi-clause expansion. Match the fix to the spread of reasons.
5. **Ground each facet** against the protocol; classify grounded vs not (see `references/grounding_criteria.md`).
6. **Apply transversally:** every rule for the procedure (all visits) gets the same correction — even visits not in the mapping. Preserve analyte/component lists, conditionals (ESD discretion, "applies only if…"), and triggers.
7. **Parity + retrofit:** if this family is the same *type* as families already done (e.g. central-lab panels), bring it to full parity; if a new facet also applies to an *earlier* family, retrofit that earlier family too (surface it and ask).
8. Run the **mandatory ritual** (below) → apply → save → confirm.

A facet may be **protocol-justified even if it covers zero cited deviations** (e.g. parity/consistency). That is legitimate — say so explicitly (the edit is justified by the protocol, not by a deviation).

---

## Phase 2 — "No match" : re-map, then Track A / Track B

The "No match" mapping ran on an **older** Golden Set, so its labels are stale. Do NOT trust them.

1. **Re-map every No-match deviation against the CURRENT Golden Set** (post Phase-1 edits + any new domains). Verify by reading the actual candidate rule's `deviation` clause — never eyeball.
2. **Three buckets:**
   - **already covered** by an existing rule / new domain → **no action** (note it).
   - **covered by our Phase-1 edits** → **no action** (it only sat in No-match because the facet didn't exist when the mapper ran).
   - **genuinely uncovered** → work it.
3. **Split the uncovered:**
   - **Track A** — extend an existing rule with a missing facet (`Rule for LLM` only; same as Phase 1).
   - **Track B** — author a **NEW rule**, in the **exact existing Golden-Set format** (all columns), placed in the correct domain sheet (operational/governance → OPS).
4. **Track B per theme — grounding-check FIRST.** If the protocol does not ground it (CMP-level, eCOA-vendor, lab-manual, admin-letter, etc.) → **do NOT author**; record it as correctly uncovered and say where it would legitimately come from.
5. **Don't over-engineer.** If a principle already lives in the rules and only marginal edge-cases slip through, leaving them uncovered is the right call over a redundant rule.

New-rule authoring details (ID numbering, category, severity, deviation level, format) are in `references/format_and_output.md`.

---

## The mandatory ritual (every family/theme, before editing)

Produce, automatically:

1. **Grounding summary** — the protocol section/footnote and the exact quote that grounds each facet; flag any facet that is NOT grounded and will be left out.
2. **Traceability table** — one row per cited deviation line → the rule + the specific clause that now covers it; mark any line **left uncaught** with the reason. Include **totals: X will be mapped / Y will not.**
3. **Rule IDs being corrected** — list them explicitly, split into **cited** (in the mapping) and **corresponding transverse** (same procedure, other visits, not cited).
4. **Ask for explicit approval.** Do not edit until the user approves. If the protocol is ambiguous or the only way to catch a line is *stricter than the protocol*, present it as an **explicit choice with a recommendation** — never decide alone.

Then: apply (`Rule for LLM` cell only, or new full-format row in Track B) → **save in place** → say **"saved to the file."**

---

## Reference files
- `references/core_principles.md` — full meta-rules, the protocol-only doctrine, and the complete "leave uncovered" catalogue.
- `references/grounding_criteria.md` — groundable vs not (incl. incorporation-by-reference / "per the manual"), and the decision-point escalation rule.
- `references/facet_templates.md` — reusable facet templates (central-lab panels, eCOA scales, rater qualification, assessment-yields-usable-result, quantity/reconciliation, ordering, population guard, conditionals).
- `references/format_and_output.md` — `Rule for LLM` format rules, traceability-table format, save-in-place conventions, and NEW-rule authoring (Track B) format.

## Scripts (optional helpers)
- `scripts/edit_rule_for_llm.py` — open the Golden-Set xlsx, edit ONLY the `Rule for LLM` cell of given KRI IDs, keep wrap/readable view, save in place.
- `scripts/add_new_rule.py` — append a new full-format rule row to a domain sheet (Track B), copying formatting from the previous row.
