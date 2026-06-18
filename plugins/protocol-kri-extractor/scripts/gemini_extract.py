"""
Gemini-based KRI extraction — the single-model panel engine (Gemini 3.5 Flash,
thinking-high; Item 1). Calls Gemini API directly (no MCP needed). API key loaded
from ~/.claude/secrets/.

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
            f"Create it with: {{'gemini': {{'api_key': 'YOUR_KEY', 'model': 'gemini-3.5-flash'}}}}"
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

def load_gemini_model(task: str = "extract") -> str:
    """Load preferred Gemini model from secrets file.

    Supports task-specific model selection:
      - task="extract": uses model_extract (for KRI extraction, needs high output volume)
      - task="judge": uses model_judge (for adjudication, needs reasoning quality)

    Falls back to generic "model" key if task-specific key is missing (backward compat).
    """
    with open(SECRETS_PATH) as f:
        secrets = json.load(f)
    gemini = secrets.get("gemini", {})
    # Try task-specific first, fall back to generic "model"
    task_key = f"model_{task}"
    return gemini.get(task_key) or gemini.get("model", "gemini-3.5-flash")


# ── Gemini API wrapper ───────────────────────────────────────────────────────
def call_gemini(prompt: str, system_prompt: str = None, temperature: float = 0.2,
                task: str = "extract") -> str:
    """Call Gemini API and return the text response.

    On Gemini 2.5+, thinking tokens and output tokens are SEPARATE budgets, so the
    model can both reason internally AND produce high-volume output without
    cannibalizing either. Configuration:
    1. task="extract" uses a model tuned for throughput (high output volume)
    2. task="judge" uses a model tuned for reasoning quality
    3. thinking_budget is set generously so reasoning is thorough
    4. max_output_tokens is separate — does not consume thinking tokens
    5. Text extraction skips thought parts explicitly
    """
    from google import genai
    from google.genai import types
    import warnings
    warnings.filterwarnings("ignore")

    client = genai.Client(api_key=load_gemini_key())
    model = load_gemini_model(task=task)

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=65536,
    )
    if system_prompt:
        config.system_instruction = system_prompt

    # On Gemini 2.5+, thinking_budget is a separate pool from output tokens.
    # For extraction: moderate budget is enough (we want reasoning + volume).
    # For judging: larger budget helps (reasoning is the whole point).
    # For non-thinking models (flash-lite, 2.0 flash) — skip thinking_config.
    is_non_thinking = any(tag in model for tag in ["flash-lite", "2.0-flash", "1.5"])
    if not is_non_thinking:
        try:
            budget = 24576  # high thinking for all panels (Item 1: Gemini 3.5 Flash, thinking-high)
            config.thinking_config = types.ThinkingConfig(thinking_budget=budget)
        except Exception:
            pass  # SDK version may not support thinking_config — proceed without it

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    # Extract text from response parts explicitly, skipping thought parts.
    # This handles thinking models where response.text may warn or miss content.
    text_parts = []
    try:
        for part in response.candidates[0].content.parts:
            # Skip thinking/thought parts — only collect actual text output
            is_thought = getattr(part, 'thought', False)
            if is_thought:
                continue
            part_text = getattr(part, 'text', None)
            if part_text:
                text_parts.append(part_text)
    except (IndexError, AttributeError):
        pass

    if text_parts:
        return "\n".join(text_parts)

    # Fallback to response.text if parts iteration failed
    return response.text


def extract_json_from_response(text: str) -> list:
    """Extract JSON array from Gemini response (may have markdown fences, prose, or truncation)."""
    if not text or not text.strip():
        return []

    # Strip all markdown code fences (may have multiple blocks)
    cleaned = text.strip()
    # Remove ```json ... ``` blocks — extract content inside
    fenced = re.findall(r'```(?:json)?\s*\n([\s\S]*?)```', cleaned)
    if fenced:
        # Use the longest fenced block (most likely the JSON)
        cleaned = max(fenced, key=len).strip()
    elif cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:])
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # Attempt 1: direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ["kris", "KRIs", "results", "data"]:
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result]
    except json.JSONDecodeError:
        pass

    # Attempt 2: find JSON array via bracket matching
    # Find the first '[' and last ']' — handles prose before/after
    first_bracket = cleaned.find('[')
    last_bracket = cleaned.rfind(']')
    if first_bracket != -1 and last_bracket > first_bracket:
        candidate = cleaned[first_bracket:last_bracket + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Attempt 3: handle truncated JSON — if the response was cut off,
    # the array may be missing its closing bracket
    if first_bracket != -1 and last_bracket <= first_bracket:
        # Try adding closing brackets
        candidate = cleaned[first_bracket:]
        # Count open braces/brackets
        open_braces = candidate.count('{') - candidate.count('}')
        open_brackets = candidate.count('[') - candidate.count(']')
        candidate += '}' * max(0, open_braces) + ']' * max(0, open_brackets)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Attempt 4: regex for individual JSON objects (last resort)
    objects = re.findall(r'\{[^{}]*"kri_id"[^{}]*\}', cleaned)
    if objects:
        parsed = []
        for obj_str in objects:
            try:
                parsed.append(json.loads(obj_str))
            except json.JSONDecodeError:
                continue
        if parsed:
            return parsed

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
    task: str = "extract",
) -> list:
    """
    Run N Gemini agents with slightly different temperatures for diversity.
    Returns list of (agent_idx, kris_list) tuples.

    Each agent gets the same prompt but different temperature → different extraction.
    This creates genuine diversity across the Gemini agents for adjudication.
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
                task=task,
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


# ── Multi-turn extraction with native PDF ingestion ──────────────────────────
#
# Background: The original run_gemini_extraction() passes the entire domain
# prompt (pre-extracted text) in a single API call. On large domains (SAF 33KB,
# END 36KB, OPS 75KB), the model self-limits its output and produces far fewer
# KRIs (validation on APT.DFI.001, single-shot method: ELIG 14, SAF 14,
# END 16, OPS 13 per agent).
#
# The multi-turn approach yields far more (ELIG 46, SAF 37, END 42,
# OPS 75) by giving each Gemini agent two capabilities:
#   1. Native PDF ingestion — upload the PDF file and let Gemini read it
#      directly (sees actual tables, footnotes, layout — not pdfplumber text)
#   2. Focused sub-area turns — guide the model through each sub-section of
#      the domain sequentially (e.g., OPS = IP/Blinding/Procedures/Docs/etc.)
#      so it extracts exhaustively instead of making one broad pass and stopping
#
# Used ONLY for Phase 2 domain extraction of ELIG/SAF/END/OPS. SOA is
# OUT OF SCOPE for this skill (handled by `soa-kri-extractor`). Every turn
# prompt below is appended with the SOA exclusion methodology block via
# `_apply_soa_guardrail()` so the agent skips any SOA-flavored content it
# encounters in its assigned section.

# Per-domain sub-area turn templates. Each tuple is (turn_name, turn_prompt).
SUB_AREA_TURNS = {
    "ELIG": [
        ("Inclusion criteria",
         "Read Section 4.1 (Inclusion Criteria) of the PDF. Extract a KRI for EVERY inclusion criterion AND every sub-criterion (e.g. a criterion with sub-parts a, b, c; a sub-part with items i-v). Use prefix ELIG-INC-NNN. Extract every criterion regardless of whether the wording is qualitative or quantitative — capture the criterion's exact requirement in the description, as faithfully as the protocol allows."),
        ("Exclusion criteria",
         "Read Section 4.2 (Exclusion Criteria). Extract a KRI for EVERY exclusion criterion AND every sub-criterion. Use prefix ELIG-EXC-NNN. Output only NEW KRIs not produced in turn 1."),
    ],
    "SAF": [
        ("AE/SAE reporting",
         "Read Section 8 (AE Definitions and Reporting). Extract every SAF KRI about: AE collection windows, AE CRF entry timelines, SAE reporting timelines, SAE follow-up rules, SUSAR reporting (7-day fatal, 15-day non-fatal), IRB reporting. Use prefix SAF-AE or SAF-SAE."),
        ("Stopping rules & IP discontinuation",
         "Read Section 9 (Subject Withdrawal and Stopping). Extract every KRI about: IP discontinuation triggers (related SAE, Grade 3+ AE, Grade 3 lab, hypersensitivity, pregnancy), study pause triggers, DMC review. Use prefix SAF-STOP. Output only NEW KRIs."),
        ("Solicited AEs & infusion monitoring",
         "Read the Solicited AEs section (typically Section 6.2x). Extract every KRI about: each solicited AE listed (e.g. malaise, arthralgia, fever, chills, skin rash, anorexia, nausea, vomiting), timing of collection, body temperature monitoring, local reactions, infusion reaction management. Use prefix SAF-SOL. Output only NEW KRIs."),
        ("DILI thresholds",
         "Extract every KRI about DILI/Hy's law thresholds from the relevant sections: ALT/AST multipliers of ULN, bilirubin thresholds, INR thresholds, symptom-triggered workup, Hy's law case follow-up. Use prefix SAF-DILI. Output only NEW KRIs."),
        ("Causality & pregnancy",
         "Extract every KRI about: causality assessment, AE severity grading (CTCAE), AE intensity categories, AE outcome categories, pregnancy reporting (timeline, outcome follow-up, miscarriage/abnormality as SAE), contraception compliance. Output only NEW KRIs."),
    ],
    "END": [
        ("Primary + key secondary endpoints",
         "Read the Objectives/Endpoints section (typically Section 2). Extract a KRI for the Primary endpoint and EACH key secondary endpoint SEPARATELY. Use prefix END-PRI and END-SEC. Severity: critical."),
        ("Secondary clinical endpoints (efficacy)",
         "Extract a KRI for EACH secondary clinical efficacy endpoint SEPARATELY (ulcer healing, time-to-event endpoints, composite components, percentage thresholds, biomarker changes). Use END-UH / END-IR / END-SEC as appropriate. Severity: major. Output only NEW KRIs."),
        ("Biomarker & analyte endpoints",
         "Extract a KRI for EACH biomarker analyte or laboratory endpoint SEPARATELY — do not combine multiple analytes into one KRI. Each analyte × each measurement type = one KRI. Use prefix END-BIO. Output only NEW KRIs."),
        ("Exploratory endpoints",
         "Extract a KRI for EACH exploratory endpoint SEPARATELY. Use prefix END-EXP. Severity: minor. Output only NEW KRIs."),
        ("Governance",
         "Read the Statistical Considerations section and DMC section. Extract a KRI for EACH analysis population separately (ITT, FAS, Per Protocol, Safety, etc.), sample size justification, reduced enrollment options, interim analysis rules, DMC composition/meetings, final analysis, alpha spending. Use prefixes GOV-POP, GOV-SS, GOV-DMC, GOV-INT. Output only NEW KRIs."),
    ],
    "OPS": [
        ("IP Handling & Administration",
         "Read the Study Treatments section (typically Section 7). Extract every OPS KRI about: IP packaging, labeling, shipment, storage conditions, handling, IV dose preparation (dilution, volume, rate, duration), topical dose preparation (volume calc, gauze impregnation, dressing layers), administration sequence, accountability, return/destruction."),
        ("Blinding & Unblinding",
         "Extract every OPS KRI about blinding: double-blind maintenance, indistinguishable containers, subject-number-only labeling, unblinded pharmacist role, emergency unblinding procedures, randomization list custody. Output only NEW KRIs."),
        ("Randomization & Study Design",
         "Read the Study Design section. Extract every OPS KRI about randomization: ratio, IVRS/IWRS system, stratification, enrollment caps. Also study oversight rules. Output only NEW KRIs."),
        ("Procedure Methodology",
         "Read the Study Procedures section (typically Section 6). Extract every OPS KRI about procedure methodology: vital signs technique, imaging/photography standardization, ulcer measurement technique (ruler, swab depth), culture technique, lab processing times, any physical assessment methodology, circulation measurement, wound cleansing, debridement methodology. Output only NEW KRIs."),
        ("Documentation & Regulatory",
         "Read the Data Handling, Monitoring, Ethics, and Regulatory sections. Extract every OPS KRI about: source data access, CRF requirements, protocol deviation documentation, record retention, IRB approval, GCP/Helsinki compliance, monitoring log, informed consent storage, DMC meeting frequency, amendment process. Output only NEW KRIs."),
        ("Appendices",
         "Read all appendices in the PDF. Extract every operational rule from each appendix (e.g. culture collection procedure, SOC guidelines, biopsy procedures, DILI workup steps). Output only NEW KRIs."),
    ],
}


def run_gemini_extraction_multi_turn(
    domain: str,
    pdf_path: str,
    n_agents: int = 5,
    temperature_spread: tuple = (0.1, 0.2, 0.3, 0.15, 0.25),
    sub_area_turns: list = None,
) -> list:
    """Multi-turn Gemini extraction with native PDF ingestion.

    Each of the N agents opens a chat session with the PDF attached, then runs
    the domain's sub-area turns sequentially (e.g., for OPS: IP handling →
    Blinding → Randomization → Procedures → Docs → Appendices). Each turn
    focuses the model on a specific sub-area of the protocol, forcing exhaustive
    extraction within that scope.

    Args:
        domain: "ELIG", "SAF", "END", or "OPS" (the 4 in-scope domains).
                SOA is OUT OF SCOPE for this skill — handled by `soa-kri-extractor`.
        pdf_path: Absolute path to the protocol PDF file
        n_agents: Number of parallel agents (default 5)
        temperature_spread: Per-agent temperatures for diversity
        sub_area_turns: Optional override list of (name, prompt) tuples.
                        If None, uses SUB_AREA_TURNS[domain].

    Returns:
        List of (agent_idx, kris_list) tuples — same format as run_gemini_extraction.

    NOTE: This is the preferred method for Phase 2 domain extraction of
    ELIG/SAF/END/OPS. The original run_gemini_extraction() is kept for
    backward compatibility and other uses (single-shot, no PDF).
    """
    from google import genai
    from google.genai import types
    import warnings
    warnings.filterwarnings("ignore")

    if sub_area_turns is None:
        sub_area_turns = SUB_AREA_TURNS.get(domain)
        if not sub_area_turns:
            raise ValueError(
                f"No sub_area_turns template for domain '{domain}'. "
                f"Supported: {list(SUB_AREA_TURNS.keys())}. "
                f"Pass sub_area_turns=... explicitly or use run_gemini_extraction() instead."
            )

    if len(temperature_spread) < n_agents:
        temperature_spread = tuple(0.1 + (i * 0.05) for i in range(n_agents))

    # Upload PDF once — reused across all agents
    client = genai.Client(api_key=load_gemini_key())
    print(f"  Uploading PDF {os.path.basename(pdf_path)}...")
    pdf_file = client.files.upload(file=pdf_path)
    while pdf_file.state.name != "ACTIVE":
        time.sleep(1)
        pdf_file = client.files.get(name=pdf_file.name)
    print(f"  PDF ready: {pdf_file.name}")

    model = load_gemini_model(task="extract")

    # JSON schema reminder appended to each turn so the model keeps format consistent
    schema_hint = (
        'Return ONLY a JSON array. No markdown fences, no prose. Schema per KRI: '
        '{"kri_id","kri_name","description":"2-3 sentences stating the verifiable '
        'requirement WITH its exact specifics (drug names, doses, thresholds, timing '
        'windows, analytes, population/visit scope, conditions) copied faithfully from '
        'the protocol — NOT a Verify-that instruction","category_id","category_label",'
        '"protocol_reference":"Section N, p.N","supporting_quote":'
        '"verbatim <=30 words (no outer double quotes)","combined_ref":'
        '"Section N, p.N — \\"quote\\"","additional_footnotes":null or footnote text,'
        '"severity":"critical|major|minor"}. Each KRI must be ATOMIC — one verifiable '
        'check about one thing. Use EXACT values from the protocol (thresholds, times, doses). '
        'ATOMIZATION OF COMPOUND CLAUSES (split ONLY when BOTH preconditions hold): '
        '(1) each sub-condition can actually FAIL for some real subject (reject always-true '
        'clauses like "male or female" covering all humans), AND (2) it is a TRUE ENUMERATION '
        'of distinct testable conditions, NOT illustrative examples under an umbrella term '
        '(phrasing like "any X (such as A, B, C)" or "X including Y" means A/B/C/Y are '
        'examples — keep ONE KRI and put examples in the description field). '
        'SPLIT examples: "NASH or HBsAg or HCV or other liver disease" → 4 KRIs (distinct '
        'lab tests); "HBOT or CTP within 30 days" → 2 KRIs (distinct interventions); '
        '"ALT or AST >3×ULN and/or bilirubin >1.5×ULN" → 3 KRIs (distinct lab values). '
        'DO NOT SPLIT: "Males or females >=18 to <85" → no sex KRI (always TRUE); "any '
        'medication (such as biological response modifiers, steroids) causing immunosuppression" '
        '→ ONE KRI with examples in description; "surface area >=1 cm² and <=40 cm²" → ONE '
        'KRI (single data field, one range check). When in doubt, keep combined.'
    )

    results = []
    for i in range(n_agents):
        temp = temperature_spread[i]
        print(f"  Gemini agent {i+1}/{n_agents} (temp={temp}) — {len(sub_area_turns)} turns...")

        try:
            config = types.GenerateContentConfig(
                temperature=temp,
                max_output_tokens=65536,
                system_instruction=SYSTEM_PROMPT,
            )
            # Enable thinking for non-flash models (separate budget in Gemini 2.5+)
            is_non_thinking = any(tag in model for tag in ["flash-lite", "2.0-flash", "1.5"])
            if not is_non_thinking:
                try:
                    config.thinking_config = types.ThinkingConfig(thinking_budget=24576)
                except Exception:
                    pass

            chat = client.chats.create(model=model, config=config)

            agent_kris = []
            for turn_idx, (turn_name, turn_prompt) in enumerate(sub_area_turns):
                full_prompt = f"{turn_prompt}\n\n{schema_hint}"
                # Attach PDF on turn 1; subsequent turns inherit chat context
                msg = [pdf_file, full_prompt] if turn_idx == 0 else full_prompt
                try:
                    response = chat.send_message(msg)
                    # Extract text from response parts, skipping thought parts
                    text_parts = []
                    for part in response.candidates[0].content.parts:
                        if getattr(part, 'thought', False):
                            continue
                        pt = getattr(part, 'text', None)
                        if pt:
                            text_parts.append(pt)
                    text = "\n".join(text_parts) if text_parts else (response.text or "")
                    turn_kris = extract_json_from_response(text)
                    agent_kris.extend(turn_kris)
                    print(f"    Turn {turn_idx+1} ({turn_name}): +{len(turn_kris)} KRIs")
                except Exception as te:
                    print(f"    Turn {turn_idx+1} ({turn_name}): ERROR {te}")

            print(f"    Agent {i+1} total: {len(agent_kris)} KRIs")
            results.append((i + 1, agent_kris))

            # Small delay between agents to respect rate limits
            if i < n_agents - 1:
                time.sleep(2)

        except Exception as e:
            print(f"  Agent {i+1} ERROR: {e}")
            results.append((i + 1, []))

    return results


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
    parser.add_argument("--domain", required=True, help="Domain: ELIG, SAF, END, or OPS (the 4 in-scope domains). SOA is out of scope — handled by `soa-kri-extractor`.")
    parser.add_argument("--pdf", required=True, help="Path to protocol PDF")
    parser.add_argument("--pages", required=True, help="Page range: '46-48' or '120,124,125'")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--agents", type=int, default=5, help="Number of Gemini agents (default: 5)")
    parser.add_argument("--prompt-file", help="Optional: path to extraction prompt text file")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Gemini KRI Extraction — {args.domain} domain")
    print("Model: [configured]")
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
- kri_id, kri_name, description, protocol_reference, supporting_quote, severity
Every KRI must be ATOMIC — one check per KRI. Never combine multiple items.
"""

    # Run extraction
    results = run_gemini_extraction(args.domain, prompt, n_agents=args.agents)

    # Save
    save_gemini_results(results, args.out, args.domain)

    total = sum(len(kris) for _, kris in results)
    print(f"\nDone. {total} total KRIs across {args.agents} agents.")
