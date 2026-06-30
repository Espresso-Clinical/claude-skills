# Format & Output Conventions

## `Rule for LLM` format (do not deviate)
The cell is a YAML-ish block. Use ONLY these keys (the ones already present in the Golden Set):
```
intent: "..."
applies_to: "..."
evidence_expected: "..."
acceptance:
  timing: "..."
  required: "..."          # most facets fold in here
  conditional: "..."       # carve-outs / "applies only if"
  trigger: "..."           # e.g. "an Unscheduled visit exists"
  pass: "..."              # explicit pass condition (optional, if rule already uses it)
  preferred: "..."         # e.g. "completed electronically" (optional, if rule already uses it)
  override: "..."          # e.g. documented medical-monitor waiver (optional)
deviation: "..."           # the failure modes; ALL facets must surface here
provenance: "..."          # protocol section/footnote + page
```
- **Never invent new sub-keys.** If a rule lacks `required`, you may add `required` (it is a standard key) — but do not add non-standard keys.
- **Fold facets into `required` AND `deviation`** — a facet that's only in `required` won't be caught; the engine reads `deviation`.
- Keep `provenance` pointing at the protocol section/footnote that grounds the facets (this is inside the `Rule for LLM`, so editing it is allowed; the separate "Protocol Reference & Quote" column is NOT to be touched).

## Traceability table (shown before every edit)
Markdown table, one row per cited deviation line:
| Line | Visit/subject | Failure (the principle) | Caught by (rule + clause) / or NOT caught + reason |
Then: **Totals — X will be mapped · Y will not.**
And a separate explicit list: **Rule IDs being corrected** = *cited* (in the mapping) + *transverse* (same procedure, other visits, not cited).

## Applying edits (in place)
- Edit the `Rule for LLM` cell only (Phase 1 / Track A). Preserve `wrap_text=True`, vertical `top`; let row height auto-fit.
- **Save in place** — same filename, same location, overwrite. No backup copies, no long-named variants.
- After saving, say **"saved to the file."**
- The next family/theme reads the just-saved file.

## NEW rules (Track B only)
Author a full row in the correct domain sheet (operational/governance → OPS). Fill **all** columns:
- **KRI ID** — next sequential ID in that domain (e.g. OPS72 after OPS71).
- **Category** — match an existing category in that domain.
- **KRI Name** — short, specific.
- **Description** — plain-language statement of the obligation (mirrors the protocol).
- **Rule for LLM** — same format as above (`intent / applies_to / evidence_expected / acceptance / deviation / provenance`).
- **Protocol Reference & Quote** — the section/appendix + a verbatim quote that grounds it.
- **Severity** — match the family/domain convention (e.g. major).
- **Deviation Level** — subject / site / trial, whichever fits.
- Copy cell formatting from the previous row (alignment/font/border/fill) so the new row matches.
- Only author if the protocol grounds it (see `grounding_criteria.md`). If not grounded → do not author; record it as correctly uncovered.

## Implementation notes (openpyxl)
- Find the `Rule for LLM` column by header name, not a fixed index (sheets may have extra columns).
- In Python source, avoid backslash-escaped quotes inside f-strings (use double-quoted strings for values containing apostrophes).
- When appending to an existing `required`/`deviation` string, insert before the closing quote and fix punctuation (avoid `.;`).
