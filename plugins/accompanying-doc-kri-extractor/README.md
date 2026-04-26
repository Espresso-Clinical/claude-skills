# Accompanying Document KRI Extractor

Extracts Key Risk Indicators (KRIs) from clinical-trial documents that **accompany** a protocol — and which do not share the protocol's domain structure (no SoA, no eligibility section, etc.). Produces a per-document golden set, deduplicated against the protocol's own golden set so nothing is re-extracted.

## Supported document types

| ID | Full name |
|----|-----------|
| CMP | Clinical Monitoring Plan |
| CSMP | Clinical Study Management Plan |
| IMP | IMP Handling Manual |
| PDHP | Protocol Deviation Handling Plan |
| PV_PLAN | Pharmacovigilance Plan |
| SAP | Statistical Analysis Plan |
| PD_CLASS | Protocol Deviation Classification Guide |

At activation, the skill requires (or asks for) the document type. It does **not** auto-detect.

## Pipeline (8 stages)

1. Setup & confirm (doc type, protocol golden set)
2. Parallel 10-agent extraction (5 Claude + 5 Gemini, page-by-page)
3. Consensus tiering (T1 auto / T2 auto-judgment panel / T3 promotion pipeline)
4. Orphan scan (page-by-page, 4-agent panel)
5. Deduplication — first against the protocol golden set, then intra-document
6. NDEF sweep (non-deterministic rules → separate section)
7. Final verification (5-judge cross-model panel; blocking gate)
8. Assemble golden set + Excel

## Inputs

- Accompanying-document PDF
- Protocol golden set JSON (from `protocol-kri-extractor` — same trial)
- Document type ID (one of the seven above)

## Output

```
~/Downloads/extractor/<protocol_id>/<run_id>/accompanying/<doc_type>/
  accompanying_golden_set.json   # { "kris": [...], "ndef_kris": [...] }
  Accompanying_KRIs.xlsx
  + per-stage reports
```

## Requirements

- `google-genai`, `pdfplumber`, `openpyxl` Python packages
- Gemini API key at `~/.claude/secrets/protocol-kri-extractor.json` (reused from the protocol skill)

## Important

- **No cross-document dedup.** If the same rule appears in the IMP Manual and the CMP, it appears in both output files (each is consumed independently by its owning function).
- **The protocol golden set is treated as ground truth.** Matches against it are dropped from the accompanying-document output — never re-judged.
- Every stage is mandatory. Nothing is skipped for speed or cost.
