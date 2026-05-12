"""
Step 1E — Alias / Canonical Name Map Builder.

Builds a canonical-name map for visits and procedures so semantically equivalent
labels are recognized as the same across SOA-table, SOA-CROSS, SOA-TEXT, and
other domains.

Spec: SKILL.md "Step 1E — Alias / Canonical Name Map".

Inputs:
    soa_table.json
    Optionally: protocol body text (for body-text aliases — visit-schedule narrative)

Output:
    alias_map.json

Usage:
    python alias_map_builder.py --soa-table soa_table.json --pdf protocol.pdf --out alias_dir/

The deterministic core:
  - Visit aliases: every label in soa_table.json's visits[] that maps to the same canonical
    visit code is an alias. Body-text scan looks for `Day N`, `Week N`, `Visit N` patterns
    that resolve to a known visit's `week` value.
  - Procedure aliases: recognized standardized bundles are mapped to their canonical name
    (e.g., 'Vital signs (BP, HR, temperature)' -> canonical='Vital signs', alias='BP+HR+
    temperature panel'). Other aliases require LLM-driven scanning of protocol body text
    and are out of scope for this deterministic core.

Empty alias map is a valid output (no aliases detected for this protocol).
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

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

CLAUDE_MODEL = "claude-sonnet-4-20250514"


BUNDLE_ALIASES = {
    "Vital signs": ["BP+HR+temperature panel", "BP/HR/Temp", "BP, HR, temperature"],
    "Complete blood count": ["CBC"],
    "Basic metabolic panel": ["BMP"],
    "Comprehensive metabolic panel": ["CMP"],
    "Liver function tests": ["LFTs"],
    "Renal function tests": ["RFTs"],
    "12-lead ECG": ["ECG", "Electrocardiogram"],
    "Lipid panel": ["Lipid profile"],
    "Physical examination": ["Physical exam", "PE"],
}


def build_visit_aliases(soa_table):
    visits = soa_table.get("visits", [])
    out = []
    seen_canonical = set()

    for v in visits:
        vid = v.get("visit_id")
        label = v.get("label", vid)
        week = v.get("week")
        if not vid or vid in seen_canonical:
            continue
        seen_canonical.add(vid)

        aliases = []
        if label and label != vid:
            aliases.append(label)
        # Only attach week-derived aliases (and same-week sibling links) when the
        # week value is a real, non-empty token. Skip empties and trivial values.
        week_str = str(week).strip() if week is not None else ""
        week_truthy = bool(week_str) and week_str.lower() not in {"", "n/a", "na", "none", "null", "—", "-"}
        if week_truthy:
            try:
                week_int = int(week_str)
                aliases.extend([f"Day {week_int * 7}", f"Week {week_int}"])
            except (TypeError, ValueError):
                if week_str.lower() != vid.lower():
                    aliases.append(week_str)
            for v2 in visits:
                if v2.get("visit_id") == vid:
                    continue
                v2_week = str(v2.get("week") or "").strip()
                if not v2_week:
                    continue  # never link visits via empty week
                if v2_week == week_str:
                    other = v2.get("visit_id") or v2.get("label")
                    if other and other != vid:
                        aliases.append(other)

        aliases = list(dict.fromkeys([a for a in aliases if a and a != vid]))
        if aliases:
            out.append({"canonical": vid, "aliases": aliases})

    return out


def build_procedure_aliases(soa_table):
    """Match each row label against the recognized-bundle table.

    A row label like 'Vital signs (BP, HR, temperature)' resolves to canonical
    'Vital signs' with the parenthetical phrase recorded as an alias.
    Other ad-hoc aliases (e.g., short forms used elsewhere in the protocol body)
    require LLM-driven scanning of protocol body text and are recorded as
    placeholders here.
    """
    procedures = soa_table.get("procedures", [])
    out = []

    for p in procedures:
        name = p.get("name", "")
        if not name:
            continue
        m = re.match(r"^([^()]+?)\s*\((.+)\)\s*$", name)
        canonical = m.group(1).strip() if m else name.strip()
        parenthetical = m.group(2).strip() if m else None

        canonical_lower = canonical.lower()
        bundle_match = None
        for bundle_canonical, _ in BUNDLE_ALIASES.items():
            if bundle_canonical.lower() == canonical_lower:
                bundle_match = bundle_canonical
                break
        if bundle_match:
            canonical = bundle_match
            aliases = list(BUNDLE_ALIASES[bundle_match])
            if parenthetical:
                aliases.insert(0, parenthetical)
            aliases = list(dict.fromkeys([a for a in aliases if a]))
            if aliases:
                out.append({"canonical": canonical, "aliases": aliases})
            continue

        if parenthetical and len(parenthetical) >= 3 and parenthetical.lower() not in {"s", "es", "ies", "n/a", "na"}:
            out.append({"canonical": canonical, "aliases": [parenthetical]})

    return out


def build(soa_table):
    return {
        "visits": build_visit_aliases(soa_table),
        "procedures": build_procedure_aliases(soa_table),
    }


def scan_body_text_aliases(pdf_path, alias_map, soa_pages_to_skip=None, client=None):
    """Step 1E body-text alias scan: read protocol body text and ask Claude for additional
    visit/procedure aliases not captured by the deterministic pass.

    Per Step 1E spec: 'Sources scanned: SoA table headers, visit-schedule narrative,
    footnote text, body-text references.' The deterministic pass handles SoA-table sources;
    this LLM pass handles narrative + body-text references.

    Updates alias_map in-place with new aliases. Non-fatal if Anthropic library or pdfplumber
    or API key is unavailable — emits a warning and returns the deterministic map unchanged.
    """
    if not HAS_ANTHROPIC:
        print("  ⚠ alias_map_builder.scan_body: anthropic not installed — skipping body-text alias scan.")
        return alias_map
    if not HAS_PDFPLUMBER:
        print("  ⚠ alias_map_builder.scan_body: pdfplumber not installed — skipping body-text alias scan.")
        return alias_map
    if not pdf_path or not os.path.exists(pdf_path):
        return alias_map
    if client is None:
        try:
            client = anthropic.Anthropic()
        except Exception as e:
            print(f"  ⚠ alias_map_builder.scan_body: anthropic client init failed ({e}) — skipping.")
            return alias_map

    soa_pages_to_skip = set(soa_pages_to_skip or [])
    body_chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                if i in soa_pages_to_skip:
                    continue
                text = page.extract_text() or ""
                if text.strip():
                    body_chunks.append(f"--- p.{i} ---\n{text}")
    except Exception as e:
        print(f"  ⚠ alias_map_builder.scan_body: PDF read failed ({e}) — skipping.")
        return alias_map

    body_text = "\n\n".join(body_chunks)
    if len(body_text) > 80000:
        body_text = body_text[:80000] + "\n[...truncated for prompt size...]"

    visits_known = json.dumps(alias_map.get("visits", []), ensure_ascii=False)
    procs_known = json.dumps(alias_map.get("procedures", []), ensure_ascii=False)

    prompt = (
        "You are scanning a clinical trial protocol body text for additional alias names "
        "of visits and procedures, beyond what was already extracted from the SoA table.\n\n"
        f"VISITS ALREADY KNOWN (canonical → aliases): {visits_known}\n\n"
        f"PROCEDURES ALREADY KNOWN (canonical → aliases): {procs_known}\n\n"
        "PROTOCOL BODY TEXT (excluding SoA table pages):\n"
        f"{body_text}\n\n"
        "Find any additional visit-name or procedure-name aliases used in the body text that are NOT already "
        "in the known list above. Examples of aliases worth recording: short forms (`Vital signs` ≡ `VS`), "
        "alternate visit numberings (`Visit 4` ≡ `V4` ≡ `Day 28`), regional/lab names for the same procedure "
        "(`Hb` ≡ `Hemoglobin`).\n\n"
        "Do NOT invent new canonical names. Only ADD aliases to existing canonicals when the body text uses "
        "an alternate name for one of them. If you find an entirely new procedure/visit not already in the "
        "known list, ignore it — out of scope for this pass.\n\n"
        "Return JSON exactly in this shape (omit empty arrays):\n"
        '{"visits_additions": [{"canonical": "W4", "new_aliases": ["..."]}], '
        '"procedures_additions": [{"canonical": "Vital signs", "new_aliases": ["VS"]}]}\n'
        "Return ONLY the JSON. No markdown fences. No prose."
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        additions = json.loads(text)
    except Exception as e:
        print(f"  ⚠ alias_map_builder.scan_body: LLM call/parse failed ({e}) — skipping body-text aliases.")
        return alias_map

    visit_index = {v["canonical"]: v for v in alias_map.get("visits", [])}
    proc_index = {p["canonical"]: p for p in alias_map.get("procedures", [])}
    added_v, added_p = 0, 0

    def _ok_alias(a, canonical):
        if not a or not isinstance(a, str):
            return False
        a = a.strip()
        if len(a) < 2:
            return False
        if a == canonical or a.lower() == canonical.lower():
            return False
        return True

    for entry in additions.get("visits_additions", []) or []:
        canonical = entry.get("canonical")
        new_aliases = entry.get("new_aliases", []) or []
        if canonical in visit_index:
            existing = set(visit_index[canonical].get("aliases", []))
            fresh = [a.strip() for a in new_aliases if _ok_alias(a, canonical) and a.strip() not in existing]
            if fresh:
                visit_index[canonical]["aliases"] = list(existing) + fresh
                added_v += len(fresh)

    for entry in additions.get("procedures_additions", []) or []:
        canonical = entry.get("canonical")
        new_aliases = entry.get("new_aliases", []) or []
        if canonical in proc_index:
            existing = set(proc_index[canonical].get("aliases", []))
            fresh = [a.strip() for a in new_aliases if _ok_alias(a, canonical) and a.strip() not in existing]
            if fresh:
                proc_index[canonical]["aliases"] = list(existing) + fresh
                added_p += len(fresh)

    print(f"  ✓ body-text alias scan: added {added_v} visit aliases, {added_p} procedure aliases")
    return alias_map


def main():
    ap = argparse.ArgumentParser(description="Step 1E — Alias / Canonical Name Map Builder")
    ap.add_argument("--soa-table", required=True, help="Path to soa_table.json")
    ap.add_argument("--pdf", required=False, help="Path to protocol PDF (enables LLM body-text alias scan when provided)")
    ap.add_argument("--out", required=True, help="Output directory (writes alias_map.json)")
    ap.add_argument("--no-body-scan", action="store_true", help="Skip the LLM body-text alias scan even when PDF is provided")
    args = ap.parse_args()

    with open(args.soa_table) as f:
        soa_table = json.load(f)

    alias_map = build(soa_table)

    if args.pdf and not args.no_body_scan:
        soa_pages = []
        for v in soa_table.get("visits", []):
            pass
        try:
            soa_pages = sorted(set(soa_table.get("pages", []) or []))
        except Exception:
            soa_pages = []
        alias_map = scan_body_text_aliases(args.pdf, alias_map, soa_pages_to_skip=soa_pages)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "alias_map.json")
    backup_path = out_path + ".bak"
    if os.path.exists(out_path):
        with open(out_path) as src, open(backup_path, "w") as dst:
            dst.write(src.read())
    with open(out_path, "w") as f:
        json.dump(alias_map, f, indent=2, ensure_ascii=False)

    print(
        f"\u2713 alias_map_builder: wrote {len(alias_map['visits'])} visit-alias entries "
        f"and {len(alias_map['procedures'])} procedure-alias entries -> {out_path}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
