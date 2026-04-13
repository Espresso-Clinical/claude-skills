"""
Gemini-based KRI extraction — runs as competing agent alongside Claude agents.
Calls Gemini API directly (no MCP needed). API key loaded from ~/.claude/secrets/.

Usage (called by the skill, not directly):
  from gemini_extract import run_gemini_extraction
  results = run_gemini_extraction(domain, prompt, pdf_text, n_agents=5)

Or standalone:
  python gemini_extract.py --domain END --pdf /path/to/protocol.pdf --pages 46-48 --out /path/to/output/
"""
import json, os, sys, re, time, argparse, pathlib

# ── Secrets loading ──────────────────────────────────────────────────────────
SECRETS_PATH = os.path.expanduser("~/.claude/secrets/protocol-kri-extractor.json")

def load_gemini_key() -> str:
    """Load Gemini API key from secrets file. Never hardcoded, never in skill dir."""
    if not os.path.exists(SECRETS_PATH):
        raise FileNotFoundError(
            f"Secrets file not found: {SECRETS_PATH}\n"
            f"Create it with: {{'gemini': {{'api_key': 'YOUR_KEY', 'model': 'gemini-2.5-pro-preview-05-06'}}}}"
        )
    with open(SECRETS_PATH) as f:
        secrets = json.load(f)
    key = secrets.get("gemini", {}).get("api_key", "")
    if not key or key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise ValueError(
            f"Gemini API key not set in {SECRETS_PATH}\n"
            f"Edit the file and replace PASTE_YOUR_GEMINI_API_KEY_HERE with your actual key."
        )
    return key

def load_gemini_model() -> str:
    """Load preferred Gemini model from secrets file."""
    with open(SECRETS_PATH) as f:
        secrets = json.load(f)
    return secrets.get("gemini", {}).get("model", "gemini-2.5-pro-preview-05-06")


# ── Gemini API wrapper ───────────────────────────────────────────────────────
def call_gemini(prompt: str, system_prompt: str = None, temperature: float = 0.2) -> str:
    """Call Gemini API and return the text response."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_gemini_key())
    model = load_gemini_model()

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=16384,
    )
    if system_prompt:
        config.system_instruction = system_prompt

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text


def extract_json_from_response(text: str) -> list:
    """Extract JSON array from Gemini response (may have markdown fences)."""
    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (```json or ```)
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # Try common wrapper keys
            for key in ["kris", "KRIs", "results"]:
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result]
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return []


# ── Multi-agent extraction ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a clinical trial protocol expert and CRA (Clinical Research Associate).
You extract information from protocol documents with precision and faithfulness.
You always return valid JSON with no markdown fences, no prose, no extra text.
Every KRI must be ATOMIC — one verifiable check about one thing at one time point.
Never combine multiple endpoints, analytes, procedures, or time points into one KRI."""


def run_gemini_extraction(
    domain: str,
    extraction_prompt: str,
    n_agents: int = 5,
    temperature_spread: tuple = (0.1, 0.2, 0.3, 0.15, 0.25),
) -> list:
    """
    Run N Gemini agents with slightly different temperatures for diversity.
    Returns list of (agent_idx, kris_list) tuples.

    Each agent gets the same prompt but different temperature → different extraction.
    This creates genuine diversity for adjudication against Claude agents.
    """
    if len(temperature_spread) < n_agents:
        temperature_spread = tuple(
            0.1 + (i * 0.05) for i in range(n_agents)
        )

    results = []
    for i in range(n_agents):
        temp = temperature_spread[i]
        print(f"  Gemini agent {i+1}/{n_agents} (temp={temp})...", end=" ", flush=True)

        try:
            response = call_gemini(
                prompt=extraction_prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=temp,
            )
            kris = extract_json_from_response(response)
            print(f"{len(kris)} KRIs")
            results.append((i + 1, kris))

            # Save raw response for audit
            # Small delay between calls to respect rate limits
            if i < n_agents - 1:
                time.sleep(2)

        except Exception as e:
            print(f"ERROR: {e}")
            results.append((i + 1, []))

    return results


def save_gemini_results(results: list, out_dir: str, domain: str):
    """Save each Gemini agent's output to a separate file for adjudication."""
    os.makedirs(out_dir, exist_ok=True)
    for agent_idx, kris in results:
        path = os.path.join(out_dir, f"gemini_agent{agent_idx}_{domain.lower()}.json")
        with open(path, "w") as f:
            json.dump(kris, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {path} ({len(kris)} KRIs)")


# ── Standalone CLI ───────────────────────────────────────────────────────────
def read_pdf_pages(pdf_path: str, page_range: str) -> str:
    """Extract text from specified PDF pages. page_range: '46-48' or '120-135'."""
    import pdfplumber

    pages_text = []
    # Parse range
    if "-" in page_range:
        start, end = page_range.split("-")
        page_nums = list(range(int(start), int(end) + 1))
    else:
        page_nums = [int(p.strip()) for p in page_range.split(",")]

    with pdfplumber.open(pdf_path) as pdf:
        for pg in page_nums:
            if 1 <= pg <= len(pdf.pages):
                text = pdf.pages[pg - 1].extract_text() or ""
                pages_text.append(f"--- PAGE {pg} ---\n{text}")

    return "\n\n".join(pages_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini KRI extraction")
    parser.add_argument("--domain", required=True, help="Domain: SOA, ELIG, SAF, END, OPS, NDEF")
    parser.add_argument("--pdf", required=True, help="Path to protocol PDF")
    parser.add_argument("--pages", required=True, help="Page range: '46-48' or '120,124,125'")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--agents", type=int, default=5, help="Number of Gemini agents (default: 5)")
    parser.add_argument("--prompt-file", help="Optional: path to extraction prompt text file")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Gemini KRI Extraction — {args.domain} domain")
    print(f"Model: {load_gemini_model()}")
    print(f"Agents: {args.agents}")
    print(f"{'='*60}\n")

    # Read PDF text
    pdf_text = read_pdf_pages(args.pdf, args.pages)
    print(f"Extracted {len(pdf_text)} chars from pages {args.pages}\n")

    # Build prompt
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file) as f:
            prompt = f.read()
    else:
        prompt = f"""Extract {args.domain} KRIs from this protocol section.

PROTOCOL TEXT:
{pdf_text}

Return ONLY a JSON array of KRI objects. Each KRI must have:
- kri_id, kri_name, description, rule_for_llm, protocol_reference, supporting_quote, severity
Every KRI must be ATOMIC — one check per KRI. Never combine multiple items.
"""

    # Run extraction
    results = run_gemini_extraction(args.domain, prompt, n_agents=args.agents)

    # Save
    save_gemini_results(results, args.out, args.domain)

    total = sum(len(kris) for _, kris in results)
    print(f"\nDone. {total} total KRIs across {args.agents} agents.")
