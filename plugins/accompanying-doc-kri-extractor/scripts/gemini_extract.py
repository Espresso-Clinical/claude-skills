#!/usr/bin/env python3
"""
Gemini extraction agent — one call produces one agent's KRI list for the document.

Run this script 5 times in parallel (different --seed / --agent-id values) to
produce the 5 Gemini outputs required by Stage 2.

The 5 Claude sub-agent extractions are launched by the top-level Claude via the
Agent tool — see SKILL.md. This script handles ONLY the Gemini half.

Usage:
  python gemini_extract.py \
      --pdf /path/to/doc.pdf \
      --doc-type IMP \
      --skill-root /path/to/accompanying-doc-kri-extractor \
      --output /path/to/raw_extractions/gemini_1.json \
      --agent-id gemini_1 \
      --seed 1

Secrets: reuses ~/.claude/secrets/protocol-kri-extractor.json (same trial infra).
"""
import argparse, json, os, re, sys, time, pathlib

SECRETS_PATH = os.path.expanduser("~/.claude/secrets/protocol-kri-extractor.json")

DOC_TYPE_LABELS = {
    "CMP": "Clinical Monitoring Plan",
    "CSMP": "Clinical Study Management Plan",
    "IMP": "IMP Handling Manual",
    "PDHP": "Protocol Deviation Handling Plan",
    "PV_PLAN": "Pharmacovigilance Plan",
    "SAP": "Statistical Analysis Plan",
    "PD_CLASS": "Protocol Deviation Classification Guide",
}


def load_gemini_key() -> str:
    if not os.path.exists(SECRETS_PATH):
        raise FileNotFoundError(
            f"Secrets file not found: {SECRETS_PATH}\n"
            f"Create it with: {{'gemini': {{'api_key': 'YOUR_KEY', 'model': 'gemini-2.5-pro'}}}}"
        )
    with open(SECRETS_PATH) as f:
        secrets = json.load(f)
    key = secrets.get("gemini", {}).get("api_key", "")
    if not key or "PASTE_YOUR" in key:
        raise ValueError(f"Gemini API key not set in {SECRETS_PATH}")
    return key


def load_gemini_model(task: str = "extract") -> str:
    with open(SECRETS_PATH) as f:
        secrets = json.load(f)
    g = secrets.get("gemini", {})
    return g.get(f"model_{task}") or g.get("model", "gemini-2.5-pro")


def call_gemini(prompt: str, system_prompt: str, seed: int = 1) -> str:
    from google import genai
    from google.genai import types
    import warnings
    warnings.filterwarnings("ignore")

    client = genai.Client(api_key=load_gemini_key())
    model = load_gemini_model(task="extract")

    config = types.GenerateContentConfig(
        temperature=0.2 + (seed % 5) * 0.05,   # slight jitter per agent
        max_output_tokens=65536,
        system_instruction=system_prompt,
    )
    is_non_thinking = any(tag in model for tag in ["flash-lite", "2.0-flash", "1.5"])
    if not is_non_thinking:
        try:
            config.thinking_config = types.ThinkingConfig(thinking_budget=16384)
        except Exception:
            pass

    response = client.models.generate_content(
        model=model, contents=prompt, config=config,
    )
    text_parts = []
    try:
        for part in response.candidates[0].content.parts:
            if getattr(part, "thought", False):
                continue
            t = getattr(part, "text", None)
            if t:
                text_parts.append(t)
    except (IndexError, AttributeError):
        pass
    return "\n".join(text_parts) if text_parts else response.text


def extract_json_list(text: str) -> list:
    if not text or not text.strip():
        return []
    cleaned = text.strip()
    fenced = re.findall(r"```(?:json)?\s*\n([\s\S]*?)```", cleaned)
    if fenced:
        cleaned = max(fenced, key=len).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for k in ("kris", "KRIs", "results", "data"):
                if k in obj and isinstance(obj[k], list):
                    return obj[k]
            return [obj]
    except json.JSONDecodeError:
        pass
    first = cleaned.find("[")
    last = cleaned.rfind("]")
    if first != -1 and last > first:
        try:
            return json.loads(cleaned[first:last + 1])
        except json.JSONDecodeError:
            pass
    return []


def read_pdf_text(pdf_path: str) -> str:
    """Return document text with page markers: === PAGE <n> === blocks."""
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber is required. pip install pdfplumber")
    blocks = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            blocks.append(f"=== PAGE {i} ===\n{t}")
    return "\n\n".join(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--doc-type", required=True)
    ap.add_argument("--skill-root", required=True,
                    help="Directory containing references/ (doc_type_briefs.md, extraction_rules.md)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    if args.doc_type not in DOC_TYPE_LABELS:
        sys.exit(f"Unknown doc-type: {args.doc_type}")

    refs_dir = pathlib.Path(args.skill_root) / "references"
    briefs = (refs_dir / "doc_type_briefs.md").read_text()
    rules = (refs_dir / "extraction_rules.md").read_text()

    # Isolate this doc-type's brief
    heading = f"## {args.doc_type}"
    start = briefs.find(heading)
    if start == -1:
        sys.exit(f"No brief found in doc_type_briefs.md for {args.doc_type}")
    # next "## " after this heading
    next_h = briefs.find("\n## ", start + len(heading))
    doc_brief = briefs[start:next_h] if next_h != -1 else briefs[start:]

    pdf_text = read_pdf_text(args.pdf)

    system = (
        "You are a clinical-trial KRI extraction agent. You follow the extraction "
        "rules exactly and output ONLY valid JSON (a single JSON array of KRI objects, "
        "no prose, no markdown fences). The examples in the document-type brief are "
        "illustrative, not exhaustive — extract EVERY rule, obligation, threshold, "
        "timeline, classification criterion, reporting requirement, handling "
        "procedure, or monitoring obligation present in the document, even if it "
        "does not match the examples."
    )
    prompt = f"""
You are agent `{args.agent_id}`. Seed={args.seed}. Document type: {args.doc_type} ({DOC_TYPE_LABELS[args.doc_type]}).

===== EXTRACTION RULES =====
{rules}

===== DOCUMENT-TYPE BRIEF =====
{doc_brief}

===== DOCUMENT TEXT (page-separated) =====
{pdf_text}

===== OUTPUT =====
Return a JSON array (and ONLY a JSON array) of KRI objects per the schema in the
extraction rules. No kri_id field. Every supporting_quote must be verbatim from
the cited page.
""".strip()

    text = call_gemini(prompt, system, seed=args.seed)
    kris = extract_json_list(text)

    # Light schema hygiene
    for k in kris:
        k["doc_type"] = args.doc_type
        k["doc_type_label"] = DOC_TYPE_LABELS[args.doc_type]
        # Strip outer quotes from supporting_quote
        sq = k.get("supporting_quote", "") or ""
        sq = sq.strip()
        if len(sq) >= 2 and sq.startswith('"') and sq.endswith('"'):
            sq = sq[1:-1].strip()
        k["supporting_quote"] = sq
        k["ndef"] = False

    out = {
        "agent_id": args.agent_id,
        "doc_type": args.doc_type,
        "seed": args.seed,
        "n_kris": len(kris),
        "kris": kris,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[{args.agent_id}] wrote {len(kris)} KRIs → {args.output}")


if __name__ == "__main__":
    main()
