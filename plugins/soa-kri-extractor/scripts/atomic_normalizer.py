"""
Step 1D — Atomic Normalization of the SoA Grid.

Decomposes compound visit columns and compound procedure rows from the Camelot grid
into atomic (procedure × visit) units. Attaches the topic-relevant footnote fragment
to each unit. Records any per-cell condition.

Spec: SKILL.md "Step 1D — Atomic Normalization of the SoA Grid".

Inputs:
    soa_table.json    (Step 1B-Camelot output)
    footnote_map.json (Step 1C output)

Output:
    soa_atomic_grid.json

Usage:
    python atomic_normalizer.py --soa-table soa_table.json --footnote-map footnote_map.json --out atomic_dir/

Zero LLM calls in the deterministic sub-passes (1D-i, 1D-ii, 1D-iii). 1D-iv (topic
binding) is sentence-aware deterministic when a single sentence in the footnote
mentions the procedure name; falls back to whole-footnote binding with a flag for
human review when topic-binding cannot be done confidently.
"""
import argparse
import json
import os
import re
import sys

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

CLAUDE_MODEL = "claude-sonnet-4-20250514"


RECOGNIZED_BUNDLES = {
    "vital signs",
    "vital sign",
    "blood pressure",
    "complete blood count",
    "cbc",
    "basic metabolic panel",
    "bmp",
    "comprehensive metabolic panel",
    "cmp",
    "full physical examination",
    "physical examination",
    "physical exam",
    "12-lead ecg",
    "ecg",
    "electrocardiogram",
    "lipid panel",
    "lipid profile",
    "liver function tests",
    "lfts",
    "renal function tests",
    "rfts",
    "coagulation panel",
    "coagulation",
    "urinalysis",
}


COND_TOKENS = (
    "if ",
    "when ",
    "only if ",
    "only when ",
    "provided that",
    "unless ",
    "in case of ",
    "in the event of ",
    "if applicable",
    "as needed",
)


def _is_recognized_bundle(label):
    norm = label.strip().lower()
    base = re.sub(r"\s*\(.*?\)\s*", "", norm).strip()
    return norm in RECOGNIZED_BUNDLES or base in RECOGNIZED_BUNDLES


def decompose_visit_label(label):
    """1D-i: enumerate atomic visits from a compound visit-column label.

    Returns (atomic_visits: list[str], compound: bool).
    Atomic visits use the same naming convention as the input. When the label
    cannot be confidently decomposed, returns the original label as a single-
    element list and compound=False.
    """
    if label is None:
        return [], False

    text = label.strip()
    if not text:
        return [], False

    range_pat = re.compile(
        r"^\s*(?:Weeks?\s+|Visits?\s+|Days?\s+)?([WVD]?)\s*(\d+)\s*[\u2013\u2014\-to/]+\s*([WVD]?)\s*(\d+)\s*$",
        re.IGNORECASE,
    )
    m = range_pat.match(text)
    if m:
        prefix1, n1, prefix2, n2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        prefix = (prefix1 or prefix2 or "").upper()
        if not prefix:
            inferred = re.match(r"^\s*(Weeks?|Visits?|Days?)\b", text, re.IGNORECASE)
            if inferred:
                token = inferred.group(1).lower()
                prefix = {"week": "W", "weeks": "W", "visit": "V", "visits": "V", "day": "D", "days": "D"}[token]
            else:
                prefix = "V"
        if n2 < n1:
            n1, n2 = n2, n1
        return [f"{prefix}{n}" for n in range(n1, n2 + 1)], True

    if "," in text or "/" in text:
        parts = re.split(r"[,/]", text)
        items = [p.strip() for p in parts if p.strip()]
        looks_like_visits = all(re.match(r"^[WVD]?\d+$", it, re.IGNORECASE) for it in items)
        if looks_like_visits and len(items) > 1:
            return [it.upper() for it in items], True

    return [text], False


SHORT_ACRONYM_OK = {
    "esr", "crp", "cbc", "ecg", "ekg", "bmp", "cmp", "lfts", "rfts",
    "bp", "hr", "rr", "spo2", "pe", "vs", "wbc", "rbc", "plt", "hgb",
    "ast", "alt", "ggt", "alp", "bun", "ldl", "hdl", "tg", "tc", "ana",
    "ck", "tsh", "t4", "t3", "psa", "ada", "pk", "pcsk9",
}

# Single-word fragments that should NEVER stand alone as a procedure name even
# if the splitter produces them — these are conjunctions, prepositions, or
# adjectives that need a noun head to make sense.
NON_PROCEDURE_FRAGMENTS = {
    "prior", "both", "either", "neither", "and", "or", "after", "before",
    "during", "with", "without", "the", "a", "an", "any", "all", "some",
    "to", "include", "including", "such", "as", "for", "in", "of", "on",
    "by", "from", "at", "is", "are", "was", "were",
}

ILLUSTRATIVE_MARKERS = re.compile(
    r"\b(such as|including|to include|for example|e\.g\.|i\.e\.)\b",
    re.IGNORECASE,
)


def decompose_procedure_label(label):
    """1D-ii: enumerate atomic procedures from a compound row label.

    Returns (atomic_procedures: list[str], compound: bool, review_needed: bool).

    Rules:
      - Recognized standardized bundles (e.g., 'Vital signs') are NOT split.
      - Parenthetical content is masked before splitting so phrases like
        '(depth and surface area)' are NOT broken apart.
      - Splits ONLY on commas and ' and ' / ' or '. Slashes are kept (clinical
        doublets like 'signs/symptoms' are single concepts).
      - If illustrative markers ('such as', 'including', 'to include', 'e.g.',
        'i.e.', 'for example') are present, the label stays whole.
      - Leading 'and '/'or ' is stripped from each item.
      - Any resulting single-word fragment that isn't a known acronym sends the
        whole label to the review queue rather than producing a bad split.
    """
    if label is None:
        return [], False, False
    text = label.strip()
    if not text:
        return [], False, False

    if _is_recognized_bundle(text):
        return [text], False, False

    if ILLUSTRATIVE_MARKERS.search(text):
        return [text], False, False

    parens = re.findall(r"\([^)]*\)|\[[^\]]*\]", text)
    masked = text
    for i, p in enumerate(parens):
        masked = masked.replace(p, f"__PAREN{i}__", 1)

    sep_pat = re.compile(r"\s*,\s*|\s+and\s+|\s+or\s+", re.IGNORECASE)
    raw_parts = [p.strip() for p in sep_pat.split(masked) if p.strip()]

    def _restore(s):
        for i, paren in enumerate(parens):
            s = s.replace(f"__PAREN{i}__", paren)
        return s

    parts = []
    for p in raw_parts:
        p = re.sub(r"^(and|or)\s+", "", p, flags=re.IGNORECASE).strip()
        p = _restore(p).strip()
        if p:
            parts.append(p)

    if len(parts) <= 1:
        return [text], False, False

    def _looks_like_fragment(p):
        words = p.split()
        if len(words) >= 2:
            # Multi-word: only fragmenty if it starts with a non-procedure
            # token like 'to include bone culture' or 'and antibiotic ...'
            return words[0].lower() in NON_PROCEDURE_FRAGMENTS
        # Single word
        low = p.lower()
        if low in SHORT_ACRONYM_OK:
            return False
        if low in NON_PROCEDURE_FRAGMENTS:
            return True
        # A single word ≥7 chars (e.g. 'hematology', 'chemistry', 'urinalysis')
        # is a plausible procedure name; accept it.
        return len(p) < 7

    if any(_looks_like_fragment(p) for p in parts):
        return [text], False, True

    # Fix 5: detect continuation-phrase splits caused by descriptive "and"
    # connectors. In compound *procedure* lists every fragment is a standalone
    # clinical action — it ends with a procedure-type word ("testing",
    # "assessments", "hematology", "medications", …). When non-first fragments
    # end with a purely descriptive noun ("disease", "characteristics",
    # "information", "data") the original is a single compound title, not a
    # list of distinct procedures. Example: "Demographic and baseline disease
    # and study ulcer characteristics" → fragments end in "disease" and
    # "characteristics" → keep whole. This check is applied only when there
    # is no comma in the label (comma-separated labels are always valid lists).
    NON_PROCEDURE_TAIL = {
        "characteristics", "disease", "information", "data", "details",
        "background", "status", "profile", "findings",
    }
    has_comma = "," in text
    if not has_comma:
        bad_tail = any(
            p.split()[-1].lower() in NON_PROCEDURE_TAIL
            for p in parts[1:] if p.split()
        )
        if bad_tail:
            return [text], False, True

    if any(_is_recognized_bundle(p) for p in parts):
        if all(_is_recognized_bundle(p) or len(p.split()) <= 5 for p in parts):
            return parts, True, False
        return [text], False, True

    if all(len(p.split()) <= 6 for p in parts):
        return parts, True, False

    return [text], False, True


# ─── 1D-ii-b: footnote-driven umbrella decomposition ─────────────────────────
# A generic "umbrella" assessment/lab row hides its real sub-tests in the
# footnotes (the label is a category, not a specific test). The pattern below is
# only a deterministic GATE deciding whether to invoke the LLM enumeration — it is
# never the final decision, so it stays fully protocol-agnostic.
GENERIC_UMBRELLA_PATTERNS = re.compile(
    r"\b("
    r"laborator(?:y|ies)|labs?|"
    r"(?:clinical|central|local|safety)\s+(?:laborator(?:y|ies)|labs?|bloods?)|"
    r"laboratory\s+(?:tests?|assessments?|evaluations?|parameters?|panels?|samples?)|"
    r"blood\s+tests?|blood\s*work|bloods?|"
    r"safety\s+bloods?"
    r")\b",
    re.IGNORECASE,
)


def is_generic_umbrella_label(label):
    """Deterministic gate for 1D-ii-b: does this row label look like a generic
    category that may hide ≥2 named tests in its footnotes? Recognized panels
    (CBC, CMP, Vital signs, …) are specific, never umbrellas. Returns True only to
    decide whether to call the LLM enumeration — not the final split decision."""
    if not label:
        return False
    if _is_recognized_bundle(label):
        return False
    return bool(GENERIC_UMBRELLA_PATTERNS.search(label))


def enumerate_footnote_named_tests(proc_name, fn_nums, fn_texts, client=None):
    """1D-ii-b (LLM-assisted, option A): for a gated umbrella row, return the
    distinct named tests its footnotes enumerate, each tagged with its defining
    footnote(s), plus the shared timing/acceptability footnotes.

    Returns a dict {"is_umbrella": bool, "tests": [{"test_name", "component_footnotes"}],
    "shared_footnotes": [..]} or None when no LLM is available. is_umbrella is True
    only when ≥2 distinct tests are named; a footnote that merely lists the analytes
    of ONE test yields is_umbrella=False (row stays whole)."""
    fn_nums = [n for n in (fn_nums or []) if fn_texts.get(str(n))]
    if len(fn_nums) < 1:
        return {"is_umbrella": False, "tests": [], "shared_footnotes": []}
    if not HAS_ANTHROPIC:
        return None
    if client is None:
        try:
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"  ⚠ atomic_normalizer.umbrella: client init failed ({e}) — skipping.")
            return None

    numbered = "\n".join(f"Footnote {n}: {fn_texts.get(str(n), '')}" for n in fn_nums)
    prompt = (
        "You are normalizing a clinical-trial Schedule of Activities row.\n\n"
        f'Row label: "{proc_name}"\n'
        f"Footnotes attached to this row:\n{numbered}\n\n"
        "A row is an UMBRELLA when its label is a generic category (e.g. \"laboratory tests\", "
        "\"safety labs\", \"blood tests\") and its footnotes enumerate TWO OR MORE DISTINCT named "
        "tests/panels (e.g. a biochemistry panel, a blood count, a coagulation panel).\n\n"
        "Return STRICT JSON only, no preamble:\n"
        '{"is_umbrella": true|false, '
        '"tests": [{"test_name": "<distinct named test>", "component_footnotes": [<int>]}], '
        '"shared_footnotes": [<int>]}\n\n'
        "Rules:\n"
        "- tests must have >=2 entries, else is_umbrella=false and tests=[].\n"
        "- Use test names exactly as the footnotes/label name them; do NOT invent tests.\n"
        "- A footnote that only lists the analytes of ONE test is NOT an umbrella.\n"
        "- component_footnotes = the footnote(s) defining that test's analytes/components.\n"
        "- shared_footnotes = timing/window/acceptability notes not specific to one test."
    )
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (response.content[0].text or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {"is_umbrella": False, "tests": [], "shared_footnotes": []}
        data = json.loads(m.group(0))
        tests = [t for t in data.get("tests", []) if t.get("test_name")]
        if not data.get("is_umbrella") or len(tests) < 2:
            return {"is_umbrella": False, "tests": [], "shared_footnotes": []}
        return {
            "is_umbrella": True,
            "tests": tests,
            "shared_footnotes": data.get("shared_footnotes", []) or [],
        }
    except Exception as e:
        print(f"  ⚠ atomic_normalizer.umbrella: enumeration failed for '{proc_name}': {e}")
        return {"is_umbrella": False, "tests": [], "shared_footnotes": []}


def extract_condition(footnote_text):
    """1D-iii: extract structured conditionality from footnote text."""
    if not footnote_text:
        return None
    norm = footnote_text.strip().lower()
    for token in COND_TOKENS:
        idx = norm.find(token)
        if idx >= 0:
            sent = re.split(r"(?<=[.!?])\s+", footnote_text)
            for s in sent:
                if token.strip() in s.lower():
                    return s.strip()
            return footnote_text.strip()
    return None


def split_footnote_sentences(footnote_text):
    if not footnote_text:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", footnote_text.strip()) if s.strip()]


def bind_footnote_fragment(footnote_text, procedure_atomic, visit_atomic):
    """1D-iv: bind the topic-relevant fragment of a footnote to one atomic unit.

    Deterministic strategy:
      1. Sentence-tokenize the footnote.
      2. Score each sentence for procedure-name overlap (case-insensitive substring match on
         the procedure's distinctive tokens) and for visit-code mention.
      3. If exactly one sentence mentions the procedure (or one of its tokens), bind that sentence.
      4. If the footnote is single-sentence or under 2 sentences, bind the whole text.
      5. Otherwise mark `binding_confidence: "low"` and bind the whole text — flag for human/LLM review.
    """
    sentences = split_footnote_sentences(footnote_text)
    if not sentences:
        return {"fragment": "", "confidence": "none"}
    if len(sentences) <= 1:
        return {"fragment": sentences[0], "confidence": "high"}

    proc_tokens = [t.lower() for t in re.split(r"\W+", procedure_atomic or "") if len(t) >= 4]
    matches = []
    for s in sentences:
        s_low = s.lower()
        score = sum(1 for tok in proc_tokens if tok in s_low)
        if visit_atomic and visit_atomic.lower() in s_low:
            score += 1
        matches.append((score, s))

    matches.sort(reverse=True, key=lambda x: x[0])
    if matches and matches[0][0] >= 1 and (len(matches) == 1 or matches[0][0] > matches[1][0]):
        return {"fragment": matches[0][1], "confidence": "high"}

    return {"fragment": footnote_text.strip(), "confidence": "low"}


def refine_low_confidence_bindings(grid, footnote_map, client=None):
    """1D-iv LLM refinement pass for atomic units with footnote_binding_confidence == 'low'.

    The deterministic sentence-matcher in bind_footnote_fragment() falls back to whole-
    footnote text when it cannot identify a single topic-relevant sentence. Per Step 1D-iv
    spec ('multi-topic footnotes are never copied whole into an atomic unit'), those low-
    confidence units must be refined with an LLM that reads the full footnote and selects
    the topic-relevant sentence(s) for the specific (procedure × visit).

    Updates units in-place. Sets confidence to 'high-llm' on success or leaves 'low' on
    failure (so downstream code can still flag them). Non-fatal if Anthropic library or
    API key is unavailable — emits a warning and leaves units as-is.
    """
    if not HAS_ANTHROPIC:
        print("  ⚠ atomic_normalizer.refine: anthropic library not installed — skipping LLM refinement.")
        return grid
    if client is None:
        try:
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"  ⚠ atomic_normalizer.refine: anthropic client init failed ({e}) — skipping LLM refinement.")
            return grid

    fn_texts = footnote_map.get("footnote_texts", {}) or {}
    low_conf_units = [u for u in grid["atomic_units"] if u.get("footnote_binding_confidence") == "low"]
    if not low_conf_units:
        return grid

    print(f"  → LLM-refining {len(low_conf_units)} low-confidence topic bindings...")
    refined_count = 0

    for unit in low_conf_units:
        fn_nums = unit.get("footnote_numbers", []) or []
        full_fn_text = "\n\n".join(
            f"Footnote {n}: {fn_texts.get(str(n), '')}"
            for n in fn_nums if fn_texts.get(str(n))
        ).strip()
        if not full_fn_text:
            continue

        prompt = (
            f"You are extracting the topic-relevant fragment from a protocol footnote for a specific clinical "
            f"procedure × visit pair.\n\n"
            f"PROCEDURE: {unit.get('procedure_atomic')}\n"
            f"VISIT: {unit.get('visit_atomic')}\n"
            f"CONDITION ON THIS UNIT (if any): {unit.get('condition') or 'none'}\n\n"
            f"FULL FOOTNOTE TEXT (may cover multiple topics):\n{full_fn_text}\n\n"
            f"Return ONLY the verbatim sentence(s) from the footnote that pertain to THIS specific procedure × visit. "
            f"If the footnote has only one topic, return the whole footnote. "
            f"If multiple sentences cover this topic, concatenate them in original order. "
            f"Never paraphrase — copy verbatim. No preamble, no explanation, no quotes around the answer.\n\n"
            f"Topic-relevant fragment:"
        )
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            fragment = (response.content[0].text or "").strip()
            if fragment.startswith('"') and fragment.endswith('"'):
                fragment = fragment[1:-1]
            if fragment and fragment in full_fn_text:
                unit["footnote_fragment"] = fragment
                unit["footnote_binding_confidence"] = "high-llm"
                refined_count += 1
            elif fragment:
                unit["footnote_fragment"] = fragment
                unit["footnote_binding_confidence"] = "high-llm-paraphrase"
                refined_count += 1
        except Exception as e:
            print(f"    ⚠ refinement failed for {unit.get('unit_id')}: {e}")

    print(f"  ✓ LLM-refined {refined_count}/{len(low_conf_units)} low-confidence bindings")
    return grid


def normalize(soa_table, footnote_map, client=None):
    """Run the 1D sub-passes against the loaded JSON inputs.

    `client` (optional) enables the LLM-assisted 1D-ii-b umbrella-row split; when
    None that pass is skipped and gated rows are flagged to the review queue."""
    visits = soa_table.get("visits", [])
    procedures = soa_table.get("procedures", [])
    fn_texts = footnote_map.get("footnote_texts", {})
    proc_fn = footnote_map.get("procedure_footnotes", {})

    visit_decomp = {}
    compound_columns_split = []
    for v in visits:
        vid = v.get("visit_id") or v.get("label", "")
        label_for_decomp = v.get("label", vid)
        atomic, compound = decompose_visit_label(label_for_decomp)
        if compound:
            atomic = atomic if atomic else [vid]
            compound_columns_split.append({"original_label": label_for_decomp, "split_into": atomic})
        else:
            atomic = [vid]
        visit_decomp[vid] = atomic

    atomic_units = []
    compound_rows_split = []
    umbrella_rows_split = []
    review_queue = []
    unit_seq = 0

    for proc in procedures:
        proc_name = proc.get("name", "")
        atomic_procs, p_compound, p_review = decompose_procedure_label(proc_name)
        if p_compound:
            compound_rows_split.append({"original_label": proc_name, "split_into": atomic_procs})
        if p_review:
            review_queue.append({"row_label": proc_name, "reason": "ambiguous compound — review required"})

        cell_fn = proc.get("cell_footnotes", {}) or {}

        # 1D-ii-b: footnote-driven umbrella decomposition. Gate deterministically,
        # then ask the LLM to enumerate the distinct named tests the footnotes carry.
        # umbrella_child_fn maps each child test → its own footnote numbers (component
        # + shared timing), so each child cites and enumerates only its own slice.
        umbrella_child_fn = None
        if (not p_compound) and len(atomic_procs) == 1 and is_generic_umbrella_label(proc_name):
            if client is None:
                # LLM disabled (--no-umbrella-split) or unavailable: never call out,
                # keep the row whole and flag it so a human can split it.
                review_queue.append({
                    "row_label": proc_name,
                    "reason": "possible umbrella lab row — LLM enumeration disabled/unavailable",
                })
            else:
                row_fn_nums = list(dict.fromkeys(
                    (proc_fn.get(proc_name, {}).get("procedure_level", []) or [])
                    + [n for cell in cell_fn.values() for n in (cell or [])]
                ))
                enum = enumerate_footnote_named_tests(proc_name, row_fn_nums, fn_texts, client)
                if enum and enum.get("is_umbrella") and len(enum.get("tests", [])) >= 2:
                    shared = enum.get("shared_footnotes", []) or []
                    umbrella_child_fn = {
                        t["test_name"]: list(dict.fromkeys((t.get("component_footnotes", []) or []) + shared))
                        for t in enum["tests"]
                    }
                    atomic_procs = list(umbrella_child_fn.keys())
                    umbrella_rows_split.append({"original_label": proc_name, "split_into": atomic_procs})

        # Set of canonical visit IDs known from the table — used to normalize
        # split components like '12' → 'V12' when the canonical form exists.
        known_vids = {v.get("visit_id") for v in visits if v.get("visit_id")}
        for raw_vid in proc.get("visits_present", []):
            # Camelot may join multi-column visit IDs with '__' (e.g., '2-11__12__13'
            # when one X mark spans columns 2-11, 12, and 13). Split back into
            # the individual visit codes before atomic decomposition.
            split_vids_raw = [v for v in str(raw_vid).split("__") if v]
            split_vids = []
            for sv in split_vids_raw:
                # Normalize bare numerics like '12' to 'V12' if the canonical exists
                if re.match(r"^\d+$", sv) and f"V{sv}" in known_vids:
                    split_vids.append(f"V{sv}")
                else:
                    split_vids.append(sv)
            for vid in split_vids:
                atomic_visits = visit_decomp.get(vid, None)
                if atomic_visits is None:
                    # vid wasn't in the visits[] list — decompose on the fly
                    decomposed, _ = decompose_visit_label(vid)
                    atomic_visits = decomposed if decomposed else [vid]

                # Footnote refs use the raw_vid key from soa_table (Camelot stores them
                # against the joined key); fall back to the split vid if not found.
                cell_fn_nums = cell_fn.get(raw_vid, cell_fn.get(vid, [])) or []
                proc_level_fn = proc_fn.get(proc_name, {}).get("procedure_level", []) or []
                effective_fn = list(dict.fromkeys(cell_fn_nums + proc_level_fn))
                cell_fn_text_concat = " ".join(fn_texts.get(str(n), "") for n in effective_fn).strip()
                condition = extract_condition(cell_fn_text_concat) if cell_fn_text_concat else None

                for atomic_proc in atomic_procs:
                    # Umbrella children carry their own footnote slice (component +
                    # shared timing); all other units use the cell-level footnotes.
                    if umbrella_child_fn is not None:
                        eff_fn = umbrella_child_fn.get(atomic_proc, effective_fn)
                        fn_text_concat = " ".join(fn_texts.get(str(n), "") for n in eff_fn).strip()
                        cond = extract_condition(fn_text_concat) if fn_text_concat else None
                    else:
                        eff_fn = effective_fn
                        fn_text_concat = cell_fn_text_concat
                        cond = condition
                    for atomic_visit in atomic_visits:
                        if fn_text_concat:
                            binding = bind_footnote_fragment(fn_text_concat, atomic_proc, atomic_visit)
                        else:
                            binding = {"fragment": "", "confidence": "none"}
                        unit_seq += 1
                        atomic_units.append({
                            "unit_id": f"SOA-ATOM-{unit_seq:04d}",
                            "procedure_atomic": atomic_proc,
                            "procedure_compound_origin": proc_name if p_compound else None,
                            "umbrella_origin": proc_name if umbrella_child_fn is not None else None,
                            "visit_atomic": atomic_visit,
                            "visit_aliases": [],
                            "visit_compound_origin": vid if vid != atomic_visit else None,
                            "footnote_numbers": eff_fn,
                            "footnote_fragment": binding["fragment"],
                            "footnote_binding_confidence": binding["confidence"],
                            "condition": cond,
                        })

    return {
        "atomic_units": atomic_units,
        "compound_rows_split": compound_rows_split,
        "umbrella_rows_split": umbrella_rows_split,
        "compound_columns_split": compound_columns_split,
        "review_queue": review_queue,
        "summary": {
            "total_atomic_units": len(atomic_units),
            "compound_rows": len(compound_rows_split),
            "umbrella_rows": len(umbrella_rows_split),
            "compound_columns": len(compound_columns_split),
            "review_queue_size": len(review_queue),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Step 1D — SoA Atomic Normalizer")
    ap.add_argument("--soa-table", required=True, help="Path to soa_table.json")
    ap.add_argument("--footnote-map", required=True, help="Path to footnote_map.json")
    ap.add_argument("--out", required=True, help="Output directory (writes soa_atomic_grid.json)")
    ap.add_argument("--no-refine", action="store_true", help="Skip the LLM refinement pass for low-confidence topic bindings (default: refine when anthropic is available)")
    ap.add_argument("--no-umbrella-split", action="store_true", help="Skip the LLM-assisted 1D-ii-b umbrella-row split (default: split when anthropic is available)")
    args = ap.parse_args()

    with open(args.soa_table) as f:
        soa_table = json.load(f)
    with open(args.footnote_map) as f:
        footnote_map = json.load(f)

    client = None
    if HAS_ANTHROPIC and not (args.no_refine and args.no_umbrella_split):
        try:
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"  ⚠ atomic_normalizer: anthropic client init failed ({e}) — running deterministic-only.")
            client = None

    grid = normalize(soa_table, footnote_map, client=None if args.no_umbrella_split else client)

    if not args.no_refine:
        grid = refine_low_confidence_bindings(grid, footnote_map, client=client)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "soa_atomic_grid.json")
    backup_path = out_path + ".bak"
    if os.path.exists(out_path):
        with open(out_path) as src, open(backup_path, "w") as dst:
            dst.write(src.read())
    with open(out_path, "w") as f:
        json.dump(grid, f, indent=2, ensure_ascii=False)

    print(
        f"\u2713 atomic_normalizer: wrote {grid['summary']['total_atomic_units']} atomic units "
        f"({grid['summary']['compound_rows']} compound rows, "
        f"{grid['summary']['umbrella_rows']} umbrella rows split, "
        f"{grid['summary']['compound_columns']} compound columns, "
        f"{grid['summary']['review_queue_size']} review queue) -> {out_path}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
