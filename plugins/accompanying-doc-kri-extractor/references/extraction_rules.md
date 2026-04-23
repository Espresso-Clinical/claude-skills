# Universal Extraction Rules

These rules apply to **every** extraction agent (Claude and Gemini, in Stage 2), to every orphan-scan agent (Stage 4), and to every judge (Stages 3, 4, 7). They are document-type agnostic.

---

## 1. Atomicity

Every KRI must be atomic: one verifiable check about one thing in one clinical/operational context. If a single sentence in the document imposes two obligations, split it into two KRIs.

- ✅ "Verify that every temperature excursion was reported to the sponsor within 24 hours of detection."
- ❌ "Verify that temperature excursions and humidity excursions are reported within 24 hours and logged in the accountability log." (3+ KRIs collapsed into one)

If splitting a sentence causes one part to lose its required context, include the context in each split — but still emit separate KRIs.

## 2. Verifiability

Every KRI in the main list must be **deterministically verifiable** by a downstream LLM-based monitoring agent using CRF / eTMF / database data. If the rule contains open-ended judgment language ("as appropriate", "at the Sponsor's discretion", "if clinically indicated"), extract it anyway — it will be moved to `ndef_kris` in Stage 6. Do NOT self-censor at extraction time.

## 3. Verbatim quote rule

- `supporting_quote` is copied **character-for-character** from the PDF page, truncated to ≤30 words. Use `…` if truncation breaks a sentence.
- Do NOT wrap the quote in outer quotes. The string must not start with `"` or end with `"`.
- Do NOT paraphrase. If the exact text is >30 words, pick the most rule-bearing contiguous span.
- Fix OCR noise only when it's obviously an artifact (e.g., a stray `|` between letters from a table border). Preserve original capitalization and punctuation.

## 4. Reference format

`document_reference` = `"<section label or heading>, p.<page>"`.

- Examples: `"Section 4.4.1, p.65"`, `"Appendix B, p.112"`, `"Risk-Based Monitoring Approach, p.12"` (when no numbered section exists).
- Use the **physical page number** of the PDF (the page a reader would open).
- No embedded quote in `document_reference`. The `combined_ref` field is where the quote joins the reference.
- No duplicate page numbers (`p.18, p.18`) — collapse to one.

## 5. `combined_ref`

Always computed: `f'{document_reference} — "{supporting_quote}"'`.

- **Em dash** (`—`, U+2014), not hyphen (`-`).
- Exactly one space on each side of the em dash.
- The embedded quote has outer double quotes here (unlike `supporting_quote`, which does not).

## 6. `rule_for_llm`

- Imperative sentence starting with a verb: "Verify that …", "Confirm that …", "Check that …".
- Contains the exact threshold/value/time window from the document when present ("within 24 hours", "≥80%", "within 14 days", "100% SDV").
- Subject of the check is specific (a site, a subject, a shipment, a visit, an SAE, etc.) — not abstract.
- One sentence; no compound checks ("and", "or" are red flags — split into two KRIs).

## 7. `kri_name`

- Short (3-10 words), descriptive, unique within the document.
- Uses the key noun of the obligation: "Temperature excursion reporting window", "SDV coverage — primary endpoint", "SAE site-to-sponsor reporting window".
- No terminal punctuation.

## 8. `description`

- 1-3 sentences explaining what the KRI is monitoring and why it matters for the trial.
- Written for a human reviewer, not for the downstream LLM.
- May include context from the document but never fabricated content.

## 9. `severity`

Assign one of `critical`, `major`, `minor`:

- **critical** — patient-safety impact, primary-endpoint integrity, regulatory-reporting obligations, SUSAR handling, unblinding, critical IMP handling (wrong subject / wrong dose / expired product), informed consent.
- **major** — secondary endpoints, SDV coverage for key fields, monitoring visit timelines, SAE follow-up, statistical analysis rules, significant deviation classification.
- **minor** — administrative rules, filing deadlines without immediate patient/data impact, descriptive obligations, documentation formatting.

When ambiguous, prefer the higher severity.

## 10. Source page fidelity

- Never cite a page the quote does not appear on. If the quote spans two pages, pick the page where the rule's threshold/action verb sits.
- Section headers often reference a different page than the table where a rule sits — use the page of the rule, not the section header.

## 11. What to extract

Extract any statement that is:

- An obligation (must / shall / is required / will)
- A prohibition (must not / shall not / is prohibited)
- A threshold (numeric, time-based, percentage)
- A classification criterion (what counts as X, what qualifies as Y)
- An escalation rule (to whom, within what window)
- A documentation / record-keeping obligation
- A qualification / training requirement tied to a role
- A reporting requirement (to sponsor, IRB, regulatory)
- A reconciliation / reconciliation-frequency rule

## 12. What NOT to extract

- Background / rationale paragraphs that impose no check
- Definitions sections unless the definition itself imposes a classification obligation
- Contact information, organization charts, distribution lists
- Revision history
- Boilerplate regulatory-framework references (e.g., "ICH E6(R2) applies") — unless the document converts them into a specific site action
- Cross-references to other documents without embedded rules

## 13. When in doubt, extract

False positives are filtered by Stage 3 consensus and Stage 7 verification. Missed rules are not recovered. Over-extract at Stage 2.

## 14. Per-document output format

Emit a single JSON file at your assigned path with this structure:

```json
{
  "agent_id": "claude_2",                  // or "gemini_4", etc.
  "doc_type": "IMP",
  "kris": [
    {
      "kri_name": "...",
      "description": "...",
      "doc_type": "IMP",
      "doc_type_label": "IMP Handling Manual",
      "rule_for_llm": "...",
      "document_reference": "...",
      "supporting_quote": "...",
      "severity": "...",
      "ndef": false                         // always false at extraction time; Stage 6 will re-set
    }
    // … no kri_id at this stage; assigned in Stage 8
  ]
}
```

Do not include commentary, explanation, or preamble in the file — JSON only.

## 15. Failure modes to avoid

- **Fabricated quotes** — quote must exist verbatim on the cited page. If you can't find it, drop the KRI.
- **Invented page numbers** — if uncertain, omit the KRI rather than guess.
- **Paraphrasing in `supporting_quote`** — only verbatim. If the document's wording is awkward, still copy it.
- **Multiple thresholds in one KRI** — split.
- **Forgetting the `doc_type` field** — every KRI must carry it.
- **Wrapping `supporting_quote` in outer quotes** — common bug. The string itself never has outer `"`.
