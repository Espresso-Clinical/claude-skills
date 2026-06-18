"""
soa_generator — Step 9: Deterministic SOA KRI generator.

Reads soa_atomic_grid.json + alias_map.json + footnote_map.json + soa_table.json +
ontology.json and emits one KRI per atomic unit, plus check-in KRIs per visit,
plus SOA-CROSS rules from ontology, plus orphan-footnote sweep.

Every KRI has the full 13-field schema with the mandatory 3-line
SOURCE/CHECK/DEVIATION rule_for_llm and footnote-derived analyte/parameter lists
embedded directly into the rule.

ZERO LLM calls in this script — everything is computed from deterministic inputs.

Output: raw_SOA.json (procedure-major ordered).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from footnote_enrichment_parser import parse_enrichment
from severity_rubric import derive_severity, derive_deviation_level
from bundle_component_table import get_bundle_components


CATEGORY_LABEL = "Schedule of Activities"


def _visit_display(visit_id, visits_by_id):
    """Return 'V2 (Week 2)' style display name from visit metadata."""
    v = visits_by_id.get(visit_id)
    if not v:
        return visit_id
    label = (v.get("label") or "").strip()
    week = (v.get("week") or "")
    week_str = str(week).strip()
    if visit_id == "SCR":
        return "screening (SCR)"
    if visit_id == "D1_PRE":
        return "Day 1 pre-treatment (D1_PRE)"
    if visit_id == "D1_POST":
        return "Day 1 post-treatment (D1_POST)"
    if visit_id == "UNS":
        return "Unscheduled (UNS)"
    if week_str and re.match(r"^Week\s*\d+", week_str, re.IGNORECASE):
        return f"{visit_id} ({week_str})"
    if label and label != visit_id:
        return f"{visit_id} ({label})"
    return visit_id


# S3 — strip a visit-defining window from a PROCEDURE name. Applied to procedure
# KRI names only: check-in names keep their window, and the procedure's own
# footnote-defined timing stays in the rule body (not the name).
_PROC_WINDOW_RE = re.compile(
    r"\s*\([^()]*(?:\b(?:days?|weeks?)\s*\d+|±\s*\d+\s*day|\bbi-?weekly\b|\bschedule\b)[^()]*\)"
    r"|\s*±\s*\d+\s*days?\b"
    r"|\s*\b(?:days?|weeks?)\s*\d+\s*[-–—]\s*\d+\b",
    re.IGNORECASE,
)


def _strip_visit_window(name):
    """Remove a visit window (e.g. '(Day 12-16)', '± 1 day', 'Day 26-30') from a
    procedure name. No-op when the name has no window."""
    if not name:
        return name
    out = _PROC_WINDOW_RE.sub("", name)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" -–—")


# S7 — §7.2 pre-IP-administration sequencing.
_IP_ADMIN_RE = re.compile(
    r"\b(ip administration|investigational product administ|study (?:drug|treatment) administ"
    r"|injection|dosing|administration of (?:ip|study))\b", re.IGNORECASE)
# Items that do NOT take a generic pre-dose clause at a treatment visit: continuous
# capture, post-dose, the dose itself, and already-time-anchored items.
# No outer \b...\b so prefix terms match plurals ("vital sign" → "Vital signs");
# abbreviations keep their own boundaries.
_PRE_DOSE_EXCLUDE_RE = re.compile(
    r"(\bAEs?\b|\bSAEs?\b|adverse event|concomitant medication|rescue medication"
    r"|\bNRS\b|diar|daily recording|weekly recording|pain recording|washout"
    r"|supervision|post[-\s]?injection|post[-\s]?dose|vital sign"
    r"|\bMRI\b|ultrasound|doppler|imaging|x[-\s]?ray|check[-\s]?in"
    r"|ip administration|injection|study treatment|dosing)", re.IGNORECASE)
# Safety blood labs → two-part pre-dose (draw + review before IP); others → single clause.
_PRE_DOSE_LAB_RE = re.compile(
    r"(biochemistr|coagulation|blood count|\bcbc\b|h[ae]matolog|chemistry|safety lab)",
    re.IGNORECASE)


def _treatment_visits(grid):
    """visit_ids that have an IP-administration row in the grid (= treatment visits, §7.2)."""
    tv = set()
    for u in grid.get("atomic_units", []) or []:
        if _IP_ADMIN_RE.search(u.get("procedure_atomic") or ""):
            v = u.get("visit_atomic")
            if v:
                tv.add(v)
    return tv


def _build_protocol_reference(footnote_numbers, page_range_str, soa_label="Schedule of Activities"):
    """Construct 'Schedule of Activities, Footnote N, Footnote M, p.X-p.Y'."""
    if not footnote_numbers:
        return f"{soa_label}, {page_range_str}"
    fns = ", ".join(f"Footnote {n}" for n in sorted(set(footnote_numbers)))
    return f"{soa_label}, {fns}, {page_range_str}"


def _build_supporting_quote(footnote_fragment, procedure_name):
    """Topic-bound supporting_quote. Strip outer quotes per Quality Rule 11."""
    q = (footnote_fragment or "").strip()
    # Strip outer quotes if any
    if q.startswith('"') and q.endswith('"') and len(q) >= 2:
        q = q[1:-1]
    q = q.lstrip('"').rstrip('"').strip()
    if not q:
        q = procedure_name or ""
    return q


def _build_combined_ref(protocol_reference, supporting_quote):
    return f'{protocol_reference} — "{supporting_quote}"'


def _build_rule_for_llm_procedure(procedure, visit_display, enrichment, condition):
    """Build the 3-line SOURCE/CHECK/DEVIATION for a standard procedure × visit KRI."""
    analyte_list = enrichment.get("analyte_list") or []
    list_type = enrichment.get("list_type") or "items"
    methodology = enrichment.get("methodology")
    timing = enrichment.get("timing_within_visit")
    conditionality = enrichment.get("conditionality") or condition

    # Named drugs/agents (S2) — surfaced in SOURCE so they are not lost. The final
    # rule wording is (re)authored downstream by the Distiller, so this is kept light.
    named_drugs = enrichment.get("named_drugs") or []
    drug_src = ""
    if named_drugs:
        label = {"prohibited": "Prohibited", "rescue": "Permitted rescue",
                 "permitted": "Permitted"}.get(enrichment.get("drug_context"), "Named")
        drug_src = f" {label} medications: {', '.join(named_drugs)}."

    # SOURCE
    source = f"The {procedure} record at the {visit_display} visit, per subject."
    if analyte_list:
        source += f" Required {list_type}: {', '.join(analyte_list)}."
    source += drug_src

    # CHECK
    check = f"{procedure} was performed and dated at {visit_display} per the Schedule of Activities."
    if analyte_list:
        check = (f"{procedure} was performed and dated at {visit_display} per the Schedule of "
                 f"Activities AND the record contains values for all {len(analyte_list)} "
                 f"required {list_type}: {', '.join(analyte_list)}.")
    if methodology:
        check = check.rstrip(".") + f". Methodology: {methodology}."
    if timing:
        check = check.rstrip(".") + f". Timing: {timing}."
    if conditionality:
        check = f"If {conditionality}: {check}"

    # DEVIATION
    deviation = (f"For an active subject expected to attend {visit_display}, "
                 f"no {procedure} record exists at that visit, or the record is undated.")
    if analyte_list:
        deviation = (f"For an active subject expected to attend {visit_display}, "
                     f"no {procedure} record exists at that visit, the record is undated, "
                     f"OR any of the {len(analyte_list)} required {list_type} "
                     f"({', '.join(analyte_list)}) is missing from the record.")
    if methodology:
        deviation = deviation.rstrip(".") + f". OR methodology requirements ({methodology}) were not met."
    if conditionality:
        deviation = (f"If {conditionality}: {deviation}")

    return f"SOURCE: {source}\nCHECK: {check}\nDEVIATION: {deviation}"


def _build_rule_for_llm_checkin(visit_id, visit_label, week_offset_days, window_days,
                                   reference_visit="randomization (Day 1)"):
    """Build SOURCE/CHECK/DEVIATION for a check-in KRI with explicit date-math."""
    visit_display = f"{visit_id} ({visit_label})" if visit_label and visit_label != visit_id else visit_id
    source = (f"The {visit_display} visit date and the {reference_visit} date, per subject.")

    if visit_id == "SCR":
        # Screening = within N days BEFORE randomization
        n = window_days if window_days else 30
        check = f"Screening occurred within {n} days before randomization (i.e., 0 ≤ Day 1 − {visit_id} date ≤ {n} days)."
        deviation = (f"For a randomized subject, screening occurred more than {n} days before "
                     f"randomization, or screening date is missing.")
    elif visit_id == "D1_PRE":
        check = f"D1_PRE occurred on the randomization date (Day 1), prior to first treatment administration."
        deviation = (f"For a randomized subject, the D1_PRE visit date does not equal the "
                     f"randomization date, or the D1_PRE record was created after first dose.")
    elif visit_id == "D1_POST":
        check = f"D1_POST occurred on the same calendar day as Day 1 treatment, after the treatment was administered."
        deviation = (f"For a treated subject, the D1_POST visit date is not the Day 1 date, or "
                     f"the recorded timing is before the treatment administration timestamp.")
    elif visit_id == "UNS":
        check = (f"Unscheduled visit ({visit_id}) occurred for a protocol-defined reason "
                 f"(early termination, safety concern, or confirmation of clinical event) and is documented as unscheduled.")
        deviation = (f"For a subject, an unscheduled visit was conducted without protocol-defined "
                     f"justification, or the unscheduled designation is missing from the record.")
    else:
        # Standard treatment / follow-up visit with ± window
        n = window_days if window_days is not None else 3
        offset = week_offset_days if week_offset_days is not None else None
        if offset is not None:
            check = f"{visit_id} ({visit_label}) visit date is within ±{n} days of (Day 1 + {offset} days)."
        else:
            check = f"{visit_id} ({visit_label}) visit date is within the protocol-specified ±{n}-day window relative to {reference_visit}."
        deviation = (f"For an active subject, the {visit_id} visit date is outside this window, "
                     f"or the visit date is missing.")

    return f"SOURCE: {source}\nCHECK: {check}\nDEVIATION: {deviation}"


def _parse_week_offset(week_str):
    """Return day offset from 'Week N' or 'Day N' or week-string. None if not parseable."""
    if not week_str:
        return None
    s = str(week_str).strip()
    m = re.search(r"Week\s*(\d+)", s, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r"Day\s*(-?\d+)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def generate(grid_path, alias_path, footnote_map_path, soa_table_path,
             ontology_path, manifest_path, out_path):
    """Generate raw_SOA.json from deterministic inputs."""
    with open(grid_path) as f:
        grid = json.load(f)
    with open(footnote_map_path) as f:
        fn_map = json.load(f)
    with open(soa_table_path) as f:
        soa_table = json.load(f)
    with open(ontology_path) as f:
        ontology = json.load(f)
    with open(manifest_path) as f:
        manifest = json.load(f)
    alias_map = {}
    if os.path.exists(alias_path):
        with open(alias_path) as f:
            alias_map = json.load(f)

    # Page range for protocol_reference — actual Camelot table pages
    table_pages = sorted(soa_table.get("pages") or [])
    if not table_pages:
        # fallback to manifest section_map.SOA
        for s in (manifest.get("section_map", {}).get("SOA") or []):
            pa = s.get("pages_approx") or []
            if len(pa) == 2:
                table_pages = list(range(int(pa[0]), int(pa[1]) + 1))
                break
    if table_pages:
        page_range_str = f"p.{table_pages[0]}-p.{table_pages[-1]}" if len(table_pages) > 1 else f"p.{table_pages[0]}"
    else:
        page_range_str = "p.?-p.?"

    fn_texts = (fn_map.get("footnote_texts") or {})
    visits_by_id = {v["visit_id"]: v for v in (soa_table.get("visits") or [])}

    # Group atomic units by procedure for procedure-major ordering
    units_by_proc = {}
    for u in grid.get("atomic_units", []):
        proc = u.get("procedure_atomic") or "?"
        units_by_proc.setdefault(proc, []).append(u)

    # Order visits within each procedure by column_index
    def _visit_sort_key(unit):
        v = visits_by_id.get(unit.get("visit_atomic"))
        return v.get("column_index", 999) if v else 999

    kris = []
    seq = 0

    # S7 — treatment visits (have an IP-administration row); each pre-dose assessment
    # there must be performed before the injection (§7.2).
    treatment_visits = _treatment_visits(grid)

    # ── Pass 1 — Atomic-grid procedure × visit KRIs (procedure-major) ─────────
    for proc in sorted(units_by_proc.keys()):
        units = sorted(units_by_proc[proc], key=_visit_sort_key)
        # Detect recognized bundle and pull components
        bundle_canon, bundle_components = get_bundle_components(proc)
        # S3 — window-free name for all DISPLAY fields (name, description, quote,
        # rule body). Lookups (bundle/severity/enrichment hint) keep the raw label.
        proc_display = _strip_visit_window(proc)

        for unit in units:
            visit_id = unit.get("visit_atomic") or "V?"
            visit_display = _visit_display(visit_id, visits_by_id)
            fn_nums = unit.get("footnote_numbers") or []
            fragment = (unit.get("footnote_fragment") or "").strip()
            condition = (unit.get("condition") or "").strip()

            # Parse footnote enrichment from the topic-bound fragment
            enrichment = parse_enrichment(fragment, procedure_name=proc)

            # If this is a recognized bundle and the footnote didn't already provide
            # an analyte list, inject the bundle components
            if not enrichment.get("analyte_list") and bundle_components:
                enrichment["analyte_list"] = bundle_components
                enrichment["list_type"] = "components"

            seq += 1
            protocol_reference = _build_protocol_reference(fn_nums, page_range_str)
            supporting_quote = _build_supporting_quote(fragment, proc_display)
            combined_ref = _build_combined_ref(protocol_reference, supporting_quote)
            additional_footnotes = None
            if fn_nums:
                parts = []
                for n in fn_nums:
                    t = (fn_texts.get(str(n)) or "").strip()
                    if t:
                        parts.append(f"Footnote {n}: {t}")
                if parts:
                    additional_footnotes = " | ".join(parts)

            rule_for_llm = _build_rule_for_llm_procedure(proc_display, visit_display, enrichment, condition or None)

            description = f"Verifies that {proc_display} was performed at the {visit_id} visit per the Schedule of Activities table."
            if enrichment.get("analyte_list"):
                description += f" The record must include the required {enrichment['list_type']} per the protocol footnote."
            if enrichment.get("methodology"):
                description += f" Methodology requirements per protocol: {enrichment['methodology']}."

            severity = derive_severity(proc, atomic_unit=unit, ontology=ontology, kri_source="atomic_grid")
            deviation_level = derive_deviation_level(proc, kri_source="atomic_grid")

            # S7 — §7.2 pre-IP sequencing: tag pre-dose assessments at treatment visits
            # (additive). Excludes continuous / post-dose / dose-itself / already-anchored
            # items. The Distiller authors the binary order check (needs EDC order).
            pre_dose = (visit_id in treatment_visits) and not _PRE_DOSE_EXCLUDE_RE.search(proc)
            if pre_dose:
                description += " Per §7.2, this assessment must be performed prior to IP administration."

            kri = {
                "kri_id": f"SOA-{visit_id}-{seq:03d}",
                "kri_name": f"{visit_id} - {proc_display}",
                "description": description,
                "category_id": "SOA",
                "category_label": CATEGORY_LABEL,
                "rule_for_llm": rule_for_llm,
                "protocol_reference": protocol_reference,
                "supporting_quote": supporting_quote,
                "combined_ref": combined_ref,
                "additional_footnotes": additional_footnotes,
                "severity": severity,
                "deviation_level": deviation_level,
                "agent_count": 10,
                "_source": "atomic_grid",
                "_atomic_unit_id": unit.get("unit_id"),
                "_visit_aliases": unit.get("visit_aliases", []),
            }
            if pre_dose:
                kri["pre_dose_required"] = True
                kri["pre_dose_basis"] = "§7.2 — performed prior to IP administration at this treatment visit"
                kri["pre_dose_kind"] = "two_part_lab" if _PRE_DOSE_LAB_RE.search(proc) else "single"
            kris.append(kri)

    # ── Pass 2 — Check-in KRIs (one per atomic visit) ─────────────────────────
    atomic_visits = sorted({u.get("visit_atomic") for u in grid.get("atomic_units", []) if u.get("visit_atomic")},
                           key=lambda v: (visits_by_id.get(v, {}).get("column_index") or 999))
    checkin_seq = 0
    for visit_id in atomic_visits:
        v = visits_by_id.get(visit_id, {})
        label = v.get("label") or visit_id
        week_str = v.get("week") or ""
        offset_days = _parse_week_offset(week_str)

        # Default window: ±3 days (typical for Phase 2/3 short-window visits)
        window_days = 3
        if visit_id == "SCR":
            window_days = 30  # screening is "within 30 days before randomization"
        elif visit_id in ("D1_PRE", "D1_POST"):
            window_days = 0
        elif offset_days and offset_days >= 26 * 7:
            window_days = 7 * 4  # follow-up at ≥6 months → ±4 weeks

        rule = _build_rule_for_llm_checkin(visit_id, label, offset_days, window_days)

        # KRI Name format: include window for clarity
        if visit_id == "SCR":
            kri_name = f"SCR - Day -{window_days} to Day 0 - Check-in"
        elif visit_id == "D1_PRE":
            kri_name = "D1_PRE - Day 1 only, pre-treatment - Check-in"
        elif visit_id == "D1_POST":
            kri_name = "D1_POST - Day 1 only, post-treatment - Check-in"
        elif visit_id == "UNS":
            kri_name = "UNS - Unscheduled - Check-in"
        else:
            if offset_days is not None:
                kri_name = f"{visit_id} - Day {offset_days} ±{window_days} days - Check-in"
            else:
                kri_name = f"{visit_id} - Check-in within window"

        description_map = {
            "SCR": f"Verifies that the screening (SCR) visit occurred within {window_days} days before randomization (Day 1).",
            "D1_PRE": "Verifies that the Day 1 pre-treatment (D1_PRE) visit occurred on the randomization date, prior to first treatment administration.",
            "D1_POST": "Verifies that the Day 1 post-treatment (D1_POST) visit occurred on the Day 1 treatment date, after study-treatment administration.",
            "UNS": "Verifies that any unscheduled (UNS) visit has a protocol-defined justification documented.",
        }
        description = description_map.get(visit_id,
            f"Verifies that the {visit_id} visit occurred {f'on Day {offset_days}, ' if offset_days else ''}within the ±{window_days}-day window relative to randomization.")

        checkin_seq += 1
        protocol_reference = f"Schedule of Activities, {page_range_str}"
        supporting_quote = f"{visit_id} visit per the Schedule of Activities"
        combined_ref = _build_combined_ref(protocol_reference, supporting_quote)
        kris.append({
            "kri_id": f"SOA-CHECKIN-{visit_id}-{checkin_seq:03d}",
            "kri_name": kri_name,
            "description": description,
            "category_id": "SOA",
            "category_label": CATEGORY_LABEL,
            "rule_for_llm": rule,
            "protocol_reference": protocol_reference,
            "supporting_quote": supporting_quote,
            "combined_ref": combined_ref,
            "additional_footnotes": None,
            "severity": "major",
            "deviation_level": "subject",
            "agent_count": 10,
            "_source": "checkin",
        })

    # ── Pass 3 — Cross-visit rules from ontology.cross_visit_rules ────────────
    # S6: distribute each rule into the specific per-visit rows it applies to — no
    # umbrella. S5 exception: a cross-rule whose content is cross-domain
    # (washout / restriction / stopping / prior-exposure) is kept as ONE SOA-CROSS
    # row so the cross_domain_router routes it to its home domain instead.
    from cross_domain_router import classify_text
    cross_rules = ontology.get("cross_visit_rules") or []
    all_visit_ids = list(visits_by_id.keys())
    cross_seq = 0
    for cr in cross_rules:
        rule_text = cr if isinstance(cr, str) else (cr.get("rule") or cr.get("text") or "")
        rule_text = rule_text.strip()
        if not rule_text:
            continue
        quote = rule_text[:200]

        if classify_text(rule_text)[0]:
            # Cross-domain → keep ONE SOA-CROSS umbrella for S5 to route out (not distributed).
            cross_seq += 1
            rule = (f"SOURCE: Per subject: {rule_text[:80]}... relative to the protocol-defined reference points.\n"
                    f"CHECK: {rule_text}\n"
                    f"DEVIATION: Any subject-level event/data violating the rule as stated.")
            kris.append({
                "kri_id": f"SOA-CROSS-{cross_seq:03d}",
                "kri_name": f"All visits - {quote[:60]}",
                "description": f"Cross-domain rule surfaced in SOA (pending route-out): {rule_text[:200]}",
                "category_id": "SOA", "category_label": CATEGORY_LABEL,
                "rule_for_llm": rule,
                "protocol_reference": f"Schedule of Activities, {page_range_str}",
                "supporting_quote": quote,
                "combined_ref": f'Schedule of Activities, {page_range_str} — "{quote}"',
                "additional_footnotes": None, "severity": "major",
                "deviation_level": "subject", "agent_count": 10, "_source": "cross_visit",
            })
            continue

        # S6 — distribute into the visit(s) it applies to (default: all atomic visits).
        applies = cr.get("applies_to_visits") if isinstance(cr, dict) else None
        if isinstance(applies, str):
            applies = all_visit_ids if applies.strip().lower() == "all" else [applies]
        targets = [v for v in (applies or []) if v in visits_by_id] or all_visit_ids
        label = (cr.get("label") if isinstance(cr, dict) else None) or rule_text[:50]
        label = _strip_visit_window(str(label)).strip()
        for vid in targets:
            vdisp = _visit_display(vid, visits_by_id)
            seq += 1
            rule = (f"SOURCE: Per subject: the obligation '{rule_text[:80]}...' as it applies at the {vdisp} visit.\n"
                    f"CHECK: At {vdisp}: {rule_text}\n"
                    f"DEVIATION: At {vdisp}, any subject-level data violating the rule as stated.")
            kris.append({
                "kri_id": f"SOA-{vid}-{seq:03d}",
                "kri_name": f"{vid} - {label}",
                "description": f"Per-visit distribution of a cross-visit SOA rule at {vdisp}: {rule_text[:160]}",
                "category_id": "SOA", "category_label": CATEGORY_LABEL,
                "rule_for_llm": rule,
                "protocol_reference": f"Schedule of Activities, {page_range_str}",
                "supporting_quote": quote,
                "combined_ref": f'Schedule of Activities, {page_range_str} — "{quote}"',
                "additional_footnotes": None, "severity": "major",
                "deviation_level": "subject", "agent_count": 10, "_source": "cross_visit_distributed",
            })

    # ── Pass 4 — Orphan-footnote sweep ────────────────────────────────────────
    orphan_fns = (fn_map.get("validation", {}) or {}).get("orphan_in_text") or []
    for i, n in enumerate(orphan_fns, 1):
        text = (fn_texts.get(str(n)) or "").strip()
        if not text:
            continue
        quote = text[:200]
        rule = (f"SOURCE: Per subject: the obligation described in Footnote {n} of the Schedule of Activities.\n"
                f"CHECK: {text[:300]}\n"
                f"DEVIATION: Any subject-level event/data failing the Footnote {n} obligation.")
        kris.append({
            "kri_id": f"SOA-ORPHAN-FOOTNOTE-{i:03d}",
            "kri_name": f"Footnote {n} - {quote[:50]}",
            "description": (f"Verifies obligation from Footnote {n} which is unanchored to any "
                            f"specific cell in the SoA table. Content: {text[:200]}"),
            "category_id": "SOA",
            "category_label": CATEGORY_LABEL,
            "rule_for_llm": rule,
            "protocol_reference": f"Schedule of Activities, Footnote {n}, {page_range_str}",
            "supporting_quote": quote,
            "combined_ref": f'Schedule of Activities, Footnote {n}, {page_range_str} — "{quote}"',
            "additional_footnotes": f"Footnote {n}: {text}",
            "severity": derive_severity(text, kri_source="orphan_footnote"),
            "deviation_level": "subject",
            "agent_count": 10,
            "_source": "orphan_footnote",
        })

    # Write output
    out = {
        "_meta": {
            "step": "9",
            "category": "SOA",
            "kri_count": len(kris),
            "by_source": {
                "atomic_grid": sum(1 for k in kris if k.get("_source") == "atomic_grid"),
                "checkin": sum(1 for k in kris if k.get("_source") == "checkin"),
                "cross_visit": sum(1 for k in kris if k.get("_source") == "cross_visit"),
                "orphan_footnote": sum(1 for k in kris if k.get("_source") == "orphan_footnote"),
            },
            "generator": "soa_generator.py — deterministic atomic-grid driven, SOURCE/CHECK/DEVIATION format with footnote enrichment, procedure-major ordering",
        },
        "kris": kris,
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"✓ soa_generator: wrote {len(kris)} KRIs to {out_path}")
    print(f"  By source: {out['_meta']['by_source']}")


def main():
    ap = argparse.ArgumentParser(description="Step 9 — Deterministic SOA KRI generator")
    ap.add_argument("--out", required=True, help="Run output directory")
    args = ap.parse_args()
    od = args.out
    generate(
        grid_path=os.path.join(od, "soa_atomic_grid.json"),
        alias_path=os.path.join(od, "alias_map.json"),
        footnote_map_path=os.path.join(od, "footnote_map.json"),
        soa_table_path=os.path.join(od, "soa_table.json"),
        ontology_path=os.path.join(od, "ontology.json"),
        manifest_path=os.path.join(od, "manifest.json"),
        out_path=os.path.join(od, "raw_SOA.json"),
    )


if __name__ == "__main__":
    sys.exit(main())
