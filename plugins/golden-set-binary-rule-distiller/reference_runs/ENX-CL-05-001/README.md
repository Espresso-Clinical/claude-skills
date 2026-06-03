# Reference run — ENX-CL-05-001 (first full run of the new design)

These are the **actual driver scripts** used to run the redesigned distiller end-to-end on the ENX-CL-05-001 golden set (335 rules). They are kept as **reference implementations / templates** of the Gemini-panel stages described in `SKILL.md` and `references/panel_review.md` — not generic, parameterized tools. Paths and the protocol ID are hardcoded; adapt them per protocol.

All panels call Gemini 3.5 Flash (high thinking) via `soa-kri-extractor/scripts/gemini_extract.py` → `call_gemini(..., task="judge")`, run in parallel threads with a temperature spread.

| Script | Stage | What it does |
|---|---|---|
| `stage1_2_nominate_defend.py` | 1 + 2 | Keep-biased **Nominate → Defend** filter: a Gemini panel nominates drop candidates (nothing dropped), a second panel defends each candidate, then an inverse-coverage pass. Drops only on a clear majority; escalates near-ties. |
| `stage3_author.py` | 3 | Authors the YAML "Protocol rule" for every survivor (batched, threaded), then YAML-validates each. |
| `stage4_quality_panel.py` | 4 | Gemini quality panel over the authored rules (chunked, 3 reviewers/chunk); consolidates flags at consensus. |
| `finalize_assemble.py` | finalize | Applies fixes, **strips footnote numbers**, assembles the final `*_binary_distilled.xlsx` + dropped-rules audit + changelog (all other columns verbatim). |

**Notes**
- Outputs (the `*.xlsx` golden sets, audit logs, panel JSONs) live under `~/Downloads/extractor/ENX-CL-05-001/` and are intentionally **not** committed — they're protocol deliverables, not skill code.
- `stage1_2_nominate_defend.py` reflects the **current** filter design (keep-biased, family-consistent, majority-drop, escalate near-ties, discretionary-not-defensible). Earlier single-panel filter drivers from the same run were superseded and are not kept here.
- Run result summary: 335 → kept after filter, with the 6 trial-level governance rules defended back by Stage 2; only discretionary/optional procedures dropped. See `SKILL.md` "Lessons" for the failure modes these guardrails prevent.
