# Protocol KRI Extractor

Extracts Key Risk Indicators (KRIs) from clinical trial protocol PDFs and assembles them into structured JSON for CRA monitoring agents.

## Pipeline

1. **Discover** — Read cover/TOC, map sections to 5 categories (SOA, ELIG, SAF, END, OPS). Extract SoA table structure.
2. **Extract** — One LLM call per category, producing structured KRIs with exact values, references, and footnotes.
3. **Validate** — Three passes: completeness, accuracy (sample 20 KRIs), consistency across visits.
4. **Assemble** — Merge all categories into `extracted_kris.json`. Optional golden set comparison.

## Categories

| ID | Label | Covers |
|----|-------|--------|
| SOA | Schedule of Activities | Visit schedule, procedures, footnotes, windows |
| ELIG | Eligibility | Inclusion/exclusion criteria |
| SAF | Safety & Toxicity | AE/SAE reporting, stopping rules, emergency protocols |
| END | Endpoints & Statistics | Objectives, endpoints, analysis sets, statistical methods |
| OPS | Operations & Compliance | IMP handling, blinding, records, regulatory |

## Requirements

- `pdfplumber` Python package
- LLM access (Gemini or similar)
- Protocol PDF file

## Usage

Invoke with `/protocol-kri-extractor` or describe what you need:
- "Extract KRIs from this protocol PDF"
- "Parse this clinical trial protocol"
- "Generate monitoring rules from the protocol"
