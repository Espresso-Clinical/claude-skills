"""
Step 2.5 — Section Obligation Inventory (per-domain)

Builds the COMPLETENESS YARDSTICK used by Step 3A. For each in-scope domain it
reads that domain's mapped section pages (from manifest.section_map, produced by
Step 1A) and enumerates EVERY conduct-constraining statement in those sections
with MAXIMUM RECALL.

Design notes (intentional, see SKILL.md Step 2.5):
  - NO obligation-marker pre-filter. We do NOT restrict to "must / shall /
    prohibited / within-N". We capture obligations, permissions, conditional
    permissions, prohibitions, definitions, timing/threshold rules, methods, and
    governance statements alike. Over-capture is correct here — the user filters
    later, and a missed sentence becomes an undetectable coverage gap.
  - This is the YARDSTICK, not a recovery mechanism. It does not create KRIs and
    does not promote anything. Step 3A consumes {domain}_obligation_inventory.json
    to MEASURE coverage and BLOCK on gaps; the Step 3.5 orphan scan is the
    independent recovery mechanism. The two are complementary, not duplicative.

Output: {domain}_obligation_inventory.json with the exact schema Step 3A reads:
  {
    "_meta": {...},
    "domain": "SAF",
    "obligations": [
      {"sentence": "<verbatim>", "page": 70, "section": "12.1",
       "type": "prohibition", "severity": "MAJOR"}
    ]
  }

Schedule of Activities (SOA) is OUT OF SCOPE for this skill — SOA sections are
tagged out_of_scope_soa in the manifest and are not mapped to a domain, so they
are never read here.
"""

import json, sys, re, os
import pdfplumber
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed

DOMAIN_LABELS = {
    "ELIG": "Eligibility",
    "SAF":  "Safety & Toxicity",
    "END":  "Endpoints & Statistics",
    "OPS":  "Operations & Compliance",
}

SYSTEM_PROMPT = """You are a clinical trial protocol analyst building a COMPLETE
inventory of every conduct-constraining statement in a protocol section.
You always return a valid JSON array. No markdown fences, no prose, no extra text."""


# ─── PDF helpers (self-contained, consistent with the other step scripts) ─────

def extract_pages_text(pdf, page_nums: list) -> str:
    total = len(pdf.pages)
    parts = []
    for n in page_nums:
        if 1 <= n <= total:
            text = pdf.pages[n - 1].extract_text() or ""
            if text.strip():
                parts.append(f"[PAGE {n}]\n{text}")
    return "\n\n".join(parts)


def section_page_range(section: dict, total_pages: int) -> list:
    pa = section.get("pages_approx") or [None, None]
    start, end = pa[0], pa[1]
    if not start:
        return []
    start = int(start)
    end = int(end) if end else min(start + 15, total_pages)
    return [p for p in range(start, end + 1) if 1 <= p <= total_pages]


# ─── Robust JSON parsing (compact; mirrors step2_extract behavior) ────────────

def _safe_json_array(raw: str):
    def _try(text):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "obligations" in obj:
                obj = obj["obligations"]
            return obj if isinstance(obj, list) else None
        except (json.JSONDecodeError, TypeError):
            return None

    parsed = _try(raw)
    if parsed is not None:
        return parsed
    cleaned = raw.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    m = re.search(r"\[[\s\S]*\]", cleaned)
    if m:
        cleaned = m.group(0)
    parsed = _try(cleaned)
    return parsed if parsed is not None else []


VALID_TYPES = {"obligation", "permission", "prohibition", "condition",
               "definition", "timing", "threshold", "method", "governance", "other"}
VALID_SEV = {"CRITICAL", "MAJOR", "MODERATE", "MINOR"}


def _build_prompt(domain: str, section_number: str, section_title: str, section_text: str) -> str:
    return f"""You are inventorying EVERY conduct-constraining statement in ONE section of a
clinical trial protocol, for the {domain} ({DOMAIN_LABELS.get(domain, domain)}) domain.

Capture with MAXIMUM RECALL. List every sentence that imposes, permits, conditions,
defines, prohibits, requires, schedules, times, or otherwise constrains how the trial
is conducted or how a subject / site / sponsor must behave, including:
  - obligations and requirements (whether or not they use "must" / "shall")
  - PERMISSIONS and conditional permissions ("X is permitted if ...", "X is allowed when ...")
  - prohibitions and restrictions
  - definitions and definitional boundaries ("X is defined as ...", "X does not include ...")
  - timing / window rules and schedules
  - thresholds and dose / limit triggers
  - methods / how-to-perform statements
  - governance / oversight / documentation rules
  - sponsor- or investigator-decision conditionals

CRITICAL: Do NOT pre-filter by keyword. Do NOT skip a sentence because it lacks
"must" / "shall". A permission with a condition (e.g. "permitted if the dosage is
stable") IS a constraint — capture it. When in doubt, INCLUDE it. Exclude ONLY pure
narrative/background prose, cross-references, and boilerplate that constrain nothing.

If one sentence carries several independent constraints (e.g. "prohibited prior to AND
during the study"), emit one entry PER independent constraint, each quoting the relevant
clause.

Return a JSON array; one entry per captured statement:
[
  {{
    "sentence": "verbatim text copied exactly from the section (one sentence or clause)",
    "page": <integer page number where it appears, from the [PAGE N] markers>,
    "type": "obligation | permission | prohibition | condition | definition | timing | threshold | method | governance | other",
    "severity": "CRITICAL | MAJOR | MODERATE | MINOR"
  }}
]

SECTION: {section_number} — {section_title}

--- SECTION TEXT (with [PAGE N] markers) ---
{section_text}
--- END ---

Return ONLY the JSON array, starting with [ and ending with ]."""


def _extract_section(client, domain, section, pdf, total_pages):
    """One high-recall LLM pass over a single section. Returns (obligations, tokens)."""
    pages = section_page_range(section, total_pages)
    if not pages:
        return [], 0
    section_text = extract_pages_text(pdf, pages)
    if not section_text.strip():
        return [], 0
    section_number = str(section.get("section_number") or "")
    section_title = section.get("title") or ""

    prompt = _build_prompt(domain, section_number, section_title, section_text)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    items = _safe_json_array(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sentence = (it.get("sentence") or "").strip().strip('"').strip()
        if not sentence:
            continue
        typ = (it.get("type") or "other").strip().lower()
        if typ not in VALID_TYPES:
            typ = "other"
        sev = (it.get("severity") or "MODERATE").strip().upper()
        if sev not in VALID_SEV:
            sev = "MODERATE"
        page = it.get("page")
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = pages[0]
        out.append({
            "sentence": sentence,
            "page": page,
            "section": section_number,
            "type": typ,
            "severity": sev,
        })
    return out, tokens


def run_obligation_inventory_for_domain(out_dir: str, domain: str, pdf_path: str,
                                        manifest_path: str = None) -> bool:
    """Build {domain}_obligation_inventory.json for one in-scope domain."""
    manifest_path = manifest_path or os.path.join(out_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    protocol_id = manifest.get("protocol_id", "UNKNOWN")
    sections = manifest.get("section_map", {}).get(domain, [])

    out_path = os.path.join(out_dir, f"{domain}_obligation_inventory.json")

    if not sections:
        # No mapped sections — write an explicit empty inventory (Fix #1 should
        # prevent this for substantive domains; the empty file keeps Step 3A's
        # contract intact and makes the absence auditable).
        payload = {
            "_meta": {"step": "2.5", "domain": domain, "protocol_id": protocol_id,
                      "sections_scanned": 0, "obligations_found": 0, "tokens_used": 0,
                      "note": "no sections mapped to this domain"},
            "domain": domain,
            "obligations": [],
        }
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"  {domain}: 0 sections mapped — wrote empty inventory")
        return True

    client = anthropic.Anthropic()
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        obligations = []
        total_tokens = 0

        def _worker(section):
            try:
                return _extract_section(client, domain, section, pdf, total_pages)
            except Exception as e:
                print(f"    section {section.get('section_number')} ERROR: {e}")
                return [], 0

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(_worker, s): s for s in sections}
            for fut in as_completed(futures):
                items, tokens = fut.result()
                obligations.extend(items)
                total_tokens += tokens

    payload = {
        "_meta": {"step": "2.5", "domain": domain, "protocol_id": protocol_id,
                  "sections_scanned": len(sections),
                  "obligations_found": len(obligations),
                  "tokens_used": total_tokens},
        "domain": domain,
        "obligations": obligations,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  {domain}: {len(obligations)} constraint statements across "
          f"{len(sections)} sections → {os.path.basename(out_path)} ({total_tokens} tokens)")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step 2.5 — Section obligation inventory (per-domain)")
    parser.add_argument("--pdf", required=True, help="Path to protocol PDF")
    parser.add_argument("--dir", required=True, help="Run directory (must contain manifest.json)")
    parser.add_argument("--cats", default=None, help="Comma-separated domains (default: ELIG,SAF,END,OPS)")
    args = parser.parse_args()

    cats = [c.strip() for c in args.cats.split(",")] if args.cats else ["ELIG", "SAF", "END", "OPS"]
    manifest_path = os.path.join(args.dir, "manifest.json")
    print(f"\n{'='*55}\nStep 2.5 — Obligation inventory ({', '.join(cats)})")
    for cat in cats:
        run_obligation_inventory_for_domain(args.dir, cat, args.pdf, manifest_path)
