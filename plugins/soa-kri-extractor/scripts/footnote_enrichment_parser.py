"""
footnote_enrichment_parser — Extract structured enrichment from a footnote fragment.

Parses topic-bound footnote text for:
  - analyte / parameter lists (e.g., "will include sodium, potassium, ...")
  - measurement / component lists (e.g., "BP, HR, temperature")
  - methodology (e.g., "supine position", "5-minute rest", "12-lead")
  - timing-within-visit (e.g., "pre-dose", "within 1 hour", "post-injection")
  - conditional applicability (e.g., "if AE", "only if clinically indicated")
  - frequency (e.g., "twice daily", "every 15 minutes")
  - named drugs / agents (e.g., "patients may use acetaminophen and/or metamizole")

Returns a structured dict that the SOA generator injects into the 3-line
SOURCE/CHECK/DEVIATION rule_for_llm.

Protocol-agnostic — uses universal English clinical-protocol phrasing patterns,
no sponsor- or protocol-specific keywords.
"""
import re


# ─── Pattern catalog ──────────────────────────────────────────────────────────

# Phrase that introduces an explicit list. Captures the list items afterwards.
LIST_INTRODUCERS = [
    r"will include the following:?",
    r"will include",
    r"includes the following:?",
    r"includes",
    r"include",
    r"comprises?",
    r"consist(?:s|ing) of",
    r"composed of",
    r"contain(?:s|ing)?",
    r"parameters? (?:will )?include",
    r"analytes? (?:will )?include",
    r"components? (?:will )?include",
    r"measurements? (?:will )?include",
    r"tests? (?:will )?include",
    r"the following.*?(?:will|must) be",
]


METHODOLOGY_PATTERNS = [
    (r"\b(supine position)\b", "supine position"),
    (r"\b(semi-recumbent position)\b", "semi-recumbent position"),
    (r"\b(seated position|sitting position)\b", "seated position"),
    (r"\b(standing position)\b", "standing position"),
    (r"\b(after (?:at least )?(\d+)\s*(?:min(?:ute)?s?|hours?)\s*(?:of\s*)?rest)\b", "{0}"),
    (r"\b(12-lead)\b", "12-lead"),
    (r"\b(in duplicate)\b", "in duplicate"),
    (r"\b(in triplicate)\b", "in triplicate"),
    (r"\b(arm supported)\b", "arm supported"),
    (r"\b(same arm)\b", "same arm consistently"),
    (r"\b(calibrated (?:device|cuff|scale))\b", "{0}"),
    (r"\b(in (?:a )?fasted? state)\b", "fasted state"),
    (r"\b(after fasting for at least \d+ hours?)\b", "{0}"),
]

TIMING_PATTERNS = [
    (r"\b(pre[-\s]?dose|prior to dosing|before dosing|before treatment)\b", "pre-dose"),
    (r"\b(post[-\s]?dose|after dosing|following dosing|after treatment)\b", "post-dose"),
    (r"\b(pre[-\s]?injection|before injection)\b", "pre-injection"),
    (r"\b(post[-\s]?injection|after injection)\b", "post-injection"),
    (r"\b(within (\d+)\s*(?:min(?:ute)?s?|hours?|days?))\b", "{0}"),
    (r"\b(at approximately (\d+)\s*(?:min(?:ute)?s?|hours?)\b)", "{0}"),
    (r"\b(every (\d+)\s*(?:min(?:ute)?s?|hours?))\b", "{0}"),
    (r"\b(twice (?:per\s+)?(?:visit|day|daily))\b", "{0}"),
    (r"\b(thrice (?:per\s+)?(?:visit|day|daily))\b", "{0}"),
    (r"\b(at end of (?:visit|infusion|administration))\b", "{0}"),
]

CONDITIONAL_PATTERNS = [
    (r"\b(if (?:applicable|clinically indicated|clinically necessary))\b", "{0}"),
    (r"\b(only if [^.,;]+)", "{0}"),
    (r"\b(if [^.,;]+ (?:is|are|occurs?|present))\b", "{0}"),
    (r"\b(when [^.,;]+)", "{0}"),
    (r"\b(unless [^.,;]+)", "{0}"),
    (r"\b(in case of [^.,;]+)", "{0}"),
    (r"\b(only in subjects who [^.,;]+)", "{0}"),
    (r"\b(for participants where [^.,;]+)", "{0}"),
    (r"\b(per (?:Sponsor|sponsor) instruction)\b", "per Sponsor instruction"),
]


# ─── Named drugs / agents (S2) ───────────────────────────────────────────────
# Cues that introduce a list of NAMED drugs/agents, each with the regulatory
# context it implies. Drug names are captured generically (NO hardcoded drug
# lexicon), so this stays protocol-agnostic. Extraction fires only when one of
# these cues is present — which is also the materiality guard: an incidental drug
# mention with no permitted/prohibited/rescue framing is NOT pulled into the rule.
DRUG_CUES = [
    (r"patients?\s+may\s+(?:use|take|receive)\b", "permitted"),
    (r"\bmay\s+(?:use|take|receive)\b", "permitted"),
    (r"rescue\s+medications?\s*(?:are|include)?\s*:?", "rescue"),
    (r"permitted\s+(?:medications?|drugs?|treatments?)\s*(?:are|include)?\s*:?", "permitted"),
    (r"allowed\s+(?:medications?|drugs?)\s*(?:are|include)?\s*:?", "permitted"),
    (r"prohibited\s+(?:medications?|drugs?|treatments?)\s*(?:are|include)?\s*:?", "prohibited"),
    (r"(?:must|should)\s+not\s+(?:use|take|be\s+used|receive)\b", "prohibited"),
    (r"\bnot\s+permitted\b", "prohibited"),
]

# Generic class words that are never specific drug names — dropped from results.
NON_DRUG_GENERIC = {
    "pain", "medication", "medications", "drug", "drugs", "analgesic",
    "analgesics", "analgesic medication", "analgesic medications", "therapy",
    "therapies", "treatment", "treatments", "agent", "agents", "them", "it",
    "long-acting analgesic medications", "long-acting analgesic medication",
    "long acting analgesic medications", "any", "other", "such", "the",
}


def _split_drugs(s):
    """Split a drug list, keeping 'a/b' synonym pairs and '(synonym)' parentheticals
    intact while splitting on commas, ' and ', ' or ', and ' and/or '."""
    s = re.sub(r"\s+and/or\s+", "|SEP|", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*,\s*", "|SEP|", s)
    s = re.sub(r"\s+and\s+|\s+or\s+", "|SEP|", s, flags=re.IGNORECASE)
    out, seen = [], set()
    for p in s.split("|SEP|"):
        it = p.strip().strip(".;").strip()
        it = re.sub(r"^(?:and|or)\s+", "", it, flags=re.IGNORECASE).strip()
        low = it.lower()
        if not it or low in NON_DRUG_GENERIC or len(low) < 3:
            continue
        if low not in seen:
            seen.add(low)
            out.append(it)
    return out


def _extract_named_drugs(text):
    """Return (drugs:list, context:str) for a footnote that names specific drugs
    under a permitted/prohibited/rescue cue, else (None, None)."""
    if not text:
        return None, None
    for cue, context in DRUG_CUES:
        m = re.search(cue, text, re.IGNORECASE)
        if not m:
            continue
        after = text[m.end():].lstrip(": ").strip()
        # Truncate at sentence end or a trailing purpose / transition phrase.
        cut = re.search(r"\.\s|\bfor\s+pain\b|\bfor\s+the\b|;|\bduring\b|\bup\s+to\b",
                        after, re.IGNORECASE)
        drugs = _split_drugs(after[:cut.start()] if cut else after)
        if drugs:
            # A permitted set that the footnote also frames as "rescue" → label rescue.
            if context == "permitted" and re.search(r"\brescue\b", text, re.IGNORECASE):
                context = "rescue"
            return drugs, context
    return None, None


def _split_list(s):
    """Split a list string like 'a, b, c, and d' or 'a; b; c' into items."""
    # Drop trailing 'and' / 'or'
    s = re.sub(r",?\s+(?:and|or)\s+", ", ", s)
    parts = re.split(r"\s*[,;]\s*", s)
    items = [p.strip().rstrip('.') for p in parts if p.strip()]
    # Drop empty / very short items
    items = [it for it in items if len(it) >= 2 and not it.lower() in {"and", "or"}]
    # Drop trailing parenthetical closures that got separated
    items = [re.sub(r"^\)+|\(+$", "", it).strip() for it in items]
    items = [it for it in items if it]
    return items


def _extract_list_after(text, introducer):
    """Find the list after `introducer` phrase, terminated by sentence-end or
    transition phrase. Returns (list_items, raw_list_string) or (None, None).
    """
    pat = re.compile(introducer, re.IGNORECASE)
    m = pat.search(text)
    if not m:
        return None, None
    after = text[m.end():].lstrip(': ').strip()
    # Take up to the next sentence-end or major transition
    end_match = re.search(r"\.\s+[A-Z]|\.\s*$|\;\s+[A-Z][^.]*?(?:will|must|may|shall)\b", after)
    list_str = after[:end_match.start()] if end_match else after
    list_str = list_str.strip().rstrip(".")
    items = _split_list(list_str)
    if not items or len(items) < 2:
        return None, None
    return items, list_str


def parse_enrichment(footnote_text, procedure_name=None):
    """Parse a topic-bound footnote fragment for SOURCE/CHECK/DEVIATION enrichment.

    Returns dict:
      {
        "analyte_list": [...] | None,       # parameters / analytes / components
        "list_type": "analytes" | "parameters" | "measurements" | "components" | "tests",
        "methodology": "supine position; 5-minute rest" | None,
        "timing_within_visit": "pre-dose" | None,
        "conditionality": "if AE reported" | None,
        "frequency": "twice per visit" | None,
        "named_drugs": [...] | None,           # specific drugs named in the footnote
        "drug_context": "permitted"|"prohibited"|"rescue" | None,
        "raw_list_string": "<original list text>" | None,
      }
    """
    if not footnote_text:
        return _empty_enrichment()

    text = footnote_text.strip()

    # Try each list introducer; the most specific phrasing wins
    list_items = None
    list_type = "items"
    raw_list = None
    for introducer in LIST_INTRODUCERS:
        items, raw = _extract_list_after(text, introducer)
        if items:
            list_items = items
            raw_list = raw
            # Infer list type from the introducer / context
            low_intro = introducer.lower()
            if "analyte" in low_intro:
                list_type = "analytes"
            elif "parameter" in low_intro:
                list_type = "parameters"
            elif "measurement" in low_intro:
                list_type = "measurements"
            elif "component" in low_intro:
                list_type = "components"
            elif "test" in low_intro:
                list_type = "tests"
            elif procedure_name and procedure_name.lower() in {"blood chemistry", "biochemistry"}:
                list_type = "analytes"
            elif procedure_name and "hematology" in procedure_name.lower():
                list_type = "parameters"
            elif procedure_name and procedure_name.lower() in {"vital signs", "vital signs including weight"}:
                list_type = "measurements"
            break

    # Methodology
    methodology_bits = []
    for pat, fmt in METHODOLOGY_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            value = fmt.format(*m.groups()) if "{0}" in fmt else fmt
            methodology_bits.append(value)
    methodology = "; ".join(methodology_bits) if methodology_bits else None

    # Timing
    timing_bits = []
    for pat, fmt in TIMING_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            value = fmt.format(*m.groups()) if "{0}" in fmt else fmt
            timing_bits.append(value)
    timing = "; ".join(timing_bits) if timing_bits else None

    # Conditionality
    cond_bits = []
    for pat, fmt in CONDITIONAL_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            value = fmt.format(*m.groups()) if "{0}" in fmt else fmt
            cond_bits.append(value)
    conditionality = "; ".join(cond_bits) if cond_bits else None

    # Frequency
    frequency = None
    fm = re.search(r"\b((?:twice|three times|every \d+\s*\w+)\s*(?:per\s+)?(?:visit|day|hour|infusion))\b",
                   text, re.IGNORECASE)
    if fm:
        frequency = fm.group(1)

    # Named drugs / agents (permitted / prohibited / rescue)
    named_drugs, drug_context = _extract_named_drugs(text)

    return {
        "analyte_list": list_items,
        "list_type": list_type,
        "methodology": methodology,
        "timing_within_visit": timing,
        "conditionality": conditionality,
        "frequency": frequency,
        "named_drugs": named_drugs,
        "drug_context": drug_context,
        "raw_list_string": raw_list,
    }


def _empty_enrichment():
    return {
        "analyte_list": None, "list_type": "items",
        "methodology": None, "timing_within_visit": None,
        "conditionality": None, "frequency": None,
        "named_drugs": None, "drug_context": None,
        "raw_list_string": None,
    }


# ─── Self-test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        ("Blood chemistry",
         "Blood chemistry parameters will include sodium, potassium, chloride, "
         "bicarbonate, blood urea nitrogen, creatinine, glucose, calcium, AST, "
         "ALT, alkaline phosphatase, bilirubin, total protein, and albumin."),
        ("Vital signs",
         "Vital signs will be measured in the supine position after at least "
         "5 minutes of rest, pre-dose."),
        ("Ulcer culture",
         "To be performed as described in Appendix A at each visit in which "
         "the ulcer is not healed and is amenable to culture."),
        ("Pregnancy test",
         "To be performed in females of childbearing potential only."),
        ("Daily recording of rescue medication",
         "Pain and associated rescue medication will be recorded daily over 7-10 days within the "
         "Screening period. Patients may use acetaminophen and/or metamizole (dipyrone) for pain."),
    ]
    for proc, fn in samples:
        print(f"\n=== {proc} ===")
        enr = parse_enrichment(fn, procedure_name=proc)
        for k, v in enr.items():
            if v:
                print(f"  {k}: {v}")
