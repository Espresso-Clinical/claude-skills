# Stage 7 — Final Verification Checks (C1–C5)

This file is the contract for the Stage 7 verification panel. Every judge (3 Claude + 2 Gemini) runs all 5 checks independently on every surviving KRI — including KRIs in `ndef_kris`.

---

## Panel composition

- 3 Claude sub-agents, spawned with `subagent_type="general-purpose"`, each given the document text + the full KRI record + the ruleset below.
- 2 Gemini judge calls (use `task="judge"` model).
- All judges run in parallel.

---

## Per-KRI input to each judge

```json
{
  "kri": { ... full KRI record ... },
  "document_pages": { "17": "...", "18": "...", ... },
  "doc_type_brief": "... from doc_type_briefs.md ...",
  "ruleset": "... this file ..."
}
```

Judges must only use the document text provided. They must not invent or infer content.

---

## The 5 checks

### C1 — Reference accuracy

- Does `document_reference` point to a real section/heading of the document?
- Does the cited page number exist in the PDF?
- Does the section label match the document's actual structure at that page (±1 page for heading/content split)?

**Verdict criteria:**
- PASS — all three conditions met.
- FAIL — page does not exist, or the cited section is not anywhere near the content.
- FLAG — ambiguous (e.g., cross-referenced section; page is +/- 2 off from heading).

### C2 — Verbatim accuracy

- Does `supporting_quote` appear verbatim on the cited page?
- Normalization allowed: whitespace collapsing, soft-hyphen removal, straight vs curly quotes, en-dash vs em-dash in the quote body.
- Normalization **not** allowed: word changes, reordering, substitution.

**Verdict criteria:**
- PASS — quote present verbatim (after allowed normalization).
- FAIL — any word changed, dropped, or reordered; quote absent on cited page.
- FLAG — quote is present on an adjacent page (off-by-one).

### C3 — Rule correctness

- Is `rule_for_llm` a deterministic, checkable instruction that a downstream LLM monitoring agent could run against trial data?
- Does it accurately reflect the obligation described by `supporting_quote`? (No over-broadening; no under-broadening.)
- Is it atomic (one check, one thing, one context)?

**Exception:** KRIs in `ndef_kris` are exempt from the "deterministic" requirement but still evaluated for "accurately reflects the quote" and "atomic".

**Verdict criteria:**
- PASS — deterministic, faithful, atomic.
- FAIL — rule is non-deterministic AND the KRI is NOT in `ndef_kris`; rule contradicts the quote; rule is compound (multiple checks).
- FLAG — rule is faithful but borderline atomic, or faithful but slightly broader/narrower than the quote.

### C4 — Description fidelity

- Does `description` accurately reflect what the KRI is monitoring and why it matters?
- No contradiction with `rule_for_llm` or `supporting_quote`.
- No fabricated context (no information not present in the document).

**Verdict criteria:**
- PASS — faithful and non-fabricating.
- FAIL — contradicts the rule or quote; invents clinical context.
- FLAG — correct but overly generic ("This KRI monitors an important obligation").

### C5 — Schema / field compliance

Checks (all must hold):
- `supporting_quote` does not start with `"` or end with `"`.
- `combined_ref` exactly equals `f'{document_reference} — "{supporting_quote}"'` (em dash `—`, single spaces).
- `document_reference` has no embedded quote.
- `severity` ∈ {critical, major, minor}.
- `doc_type` matches the run's confirmed type.
- No duplicate page numbers in `document_reference`.
- No trailing whitespace in any text field.
- `kri_name` has no terminal punctuation.
- All required fields present and non-empty.
- `ndef` is a boolean.

**Verdict criteria:**
- PASS — all conditions hold.
- FAIL — any condition fails. FAILs on C5 are auto-correctable (see below).

---

## Per-judge verdict format

Each judge emits:

```json
{
  "judge_id": "claude_2" | "gemini_1" | ...,
  "kri_idx": 47,
  "verdicts": {
    "C1": { "verdict": "PASS|FAIL|FLAG", "reason": "..." },
    "C2": { "verdict": "PASS|FAIL|FLAG", "reason": "..." },
    "C3": { "verdict": "PASS|FAIL|FLAG", "reason": "..." },
    "C4": { "verdict": "PASS|FAIL|FLAG", "reason": "..." },
    "C5": { "verdict": "PASS|FAIL|FLAG", "reason": "..." }
  }
}
```

Reasons are one sentence max.

---

## Consensus adjudication per KRI

For each check, tally the 5 judges:

- **5 PASS** → PASS.
- **≥1 FAIL, no contradiction** → FAIL.
- **Mixed / FLAG** → FLAG (needs adjudication).

Apply the disposition table:

| Check | Outcome | Disposition |
|-------|---------|-------------|
| C1    | FAIL    | Drop the KRI. Log to `verification_report.json` with reason. |
| C1    | FLAG    | Surface to user. |
| C2    | FAIL    | Drop the KRI. |
| C2    | FLAG    | Surface to user (likely off-by-one page; user can fix the reference). |
| C3    | FAIL (deterministic) | Surface to user; may be fixable by rewording `rule_for_llm`. |
| C3    | FAIL (non-deterministic + not in NDEF) | Move to `ndef_kris` (Stage 6 missed it). |
| C3    | FLAG    | Surface to user. |
| C4    | FAIL    | Surface to user. |
| C4    | FLAG    | Auto-correct by regenerating description (single Claude call) OR surface to user. |
| C5    | FAIL    | **Auto-correct** (normalize whitespace, strip outer quotes, fix em dash, re-compute `combined_ref`) and re-verify. If still failing, surface to user. |

---

## Blocking gate

Stage 8 (assemble) **cannot start** until:

- Every retained KRI is 5/5 PASS across C1–C5 (after auto-corrections).
- Every FLAG has a user decision (retain / drop / edit).
- Every FAIL has either been resolved (auto-correction succeeded) or the KRI has been dropped.

The Compliance Monitor enforces this gate. `verification_report.json` must contain the final state of every KRI — 100% of records must have a final disposition.

---

## Output — `verification_report.json`

```json
{
  "generated_at": "...",
  "n_kris_evaluated": 87,
  "results": [
    {
      "kri_idx": 0,
      "kri_name": "...",
      "panel_verdicts": { "C1": "PASS", "C2": "PASS", "C3": "PASS", "C4": "PASS", "C5": "PASS" },
      "judge_raw": [ ... 5 judge records ... ],
      "disposition": "retained",                   // retained | dropped | autocorrected | user_flag
      "autocorrect_log": null,                     // or diff of changes
      "user_decision": null                         // set when disposition == user_flag
    }
  ],
  "summary": {
    "retained": 81,
    "dropped": 2,
    "autocorrected": 3,
    "user_flags_resolved": 1
  }
}
```
