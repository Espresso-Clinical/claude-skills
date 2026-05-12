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

    if any(_is_recognized_bundle(p) for p in parts):
        if all(_is_recognized_bundle(p) or len(p.split()) <= 5 for p in parts):
            return parts, True, False
        return [text], False, True

    if all(len(p.split()) <= 6 for p in parts):
        return parts, True, False

    return [text], False, True


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


def normalize(soa_table, footnote_map):
    """Run the four 1D sub-passes against the loaded JSON inputs."""
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
                    for atomic_visit in atomic_visits:
                        if cell_fn_text_concat:
                            binding = bind_footnote_fragment(cell_fn_text_concat, atomic_proc, atomic_visit)
                        else:
                            binding = {"fragment": "", "confidence": "none"}
                        unit_seq += 1
                        atomic_units.append({
                            "unit_id": f"SOA-ATOM-{unit_seq:04d}",
                            "procedure_atomic": atomic_proc,
                            "procedure_compound_origin": proc_name if p_compound else None,
                            "visit_atomic": atomic_visit,
                            "visit_aliases": [],
                            "visit_compound_origin": vid if vid != atomic_visit else None,
                            "footnote_numbers": effective_fn,
                            "footnote_fragment": binding["fragment"],
                            "footnote_binding_confidence": binding["confidence"],
                            "condition": condition,
                        })

    return {
        "atomic_units": atomic_units,
        "compound_rows_split": compound_rows_split,
        "compound_columns_split": compound_columns_split,
        "review_queue": review_queue,
        "summary": {
            "total_atomic_units": len(atomic_units),
            "compound_rows": len(compound_rows_split),
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
    args = ap.parse_args()

    with open(args.soa_table) as f:
        soa_table = json.load(f)
    with open(args.footnote_map) as f:
        footnote_map = json.load(f)

    grid = normalize(soa_table, footnote_map)

    if not args.no_refine:
        grid = refine_low_confidence_bindings(grid, footnote_map)

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
        f"{grid['summary']['compound_columns']} compound columns, "
        f"{grid['summary']['review_queue_size']} review queue) -> {out_path}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
