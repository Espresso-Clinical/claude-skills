#!/usr/bin/env python3
"""
Orchestration entry point for accompanying-doc-kri-extractor.

This script handles the DETERMINISTIC portions of the pipeline:
  - Stage 1 setup (output dir, run_config.json)
  - Consensus tiering inputs (reads 10 raw extraction files, produces candidate clusters)
  - Stage 5 dedup (vs protocol golden set, then intra-document)
  - Stage 6 NDEF sweep (rule-based heuristic)
  - Stage 8 assembly (JSON + Excel)

The LLM-heavy stages (5 Claude extraction agents, 5 Gemini extraction agents,
judge panels, orphan-scan panel, Stage 7 verification panel) are orchestrated by
the top-level Claude instance per SKILL.md — this script does not spawn them.

Subcommands:
  setup                 — Stage 1
  tier                  — Stage 3 mechanical tiering (reads raw_extractions/, writes consensus_report.json)
  dedup-protocol        — Stage 5a
  dedup-intra           — Stage 5b
  ndef                  — Stage 6 rule-based sweep
  assemble              — Stage 8 final output
"""
import argparse, hashlib, json, os, sys, datetime, pathlib, re

DOC_TYPES = {
    "CMP": "Clinical Monitoring Plan",
    "CSMP": "Clinical Study Management Plan",
    "IMP": "IMP Handling Manual",
    "PDHP": "Protocol Deviation Handling Plan",
    "PV_PLAN": "Pharmacovigilance Plan",
    "SAP": "Statistical Analysis Plan",
    "PD_CLASS": "Protocol Deviation Classification Guide",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def dump_json(obj, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def normalize_text(s: str) -> str:
    """Normalize for similarity: lowercase, collapse whitespace, strip punctuation noise."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[\u2018\u2019\u201C\u201D]", "'", s)    # smart quotes → straight
    s = re.sub(r"[\u2013\u2014\u2015]", "-", s)          # all dashes → hyphen
    s = re.sub(r"\s+", " ", s).strip()
    return s


def jaccard_tokens(a: str, b: str) -> float:
    ta = set(normalize_text(a).split())
    tb = set(normalize_text(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def quote_verbatim_match(a: str, b: str) -> bool:
    """True if a's quote is present verbatim (after normalization) inside b's quote, or vice-versa."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def kris_equivalent(k1: dict, k2: dict, jaccard_threshold: float = 0.7) -> bool:
    """Two KRIs are treated as equivalent if either their rules overlap heavily OR quotes match."""
    if quote_verbatim_match(k1.get("supporting_quote", ""), k2.get("supporting_quote", "")):
        return True
    if jaccard_tokens(k1.get("rule_for_llm", ""), k2.get("rule_for_llm", "")) >= jaccard_threshold:
        return True
    return False


# ── Stage 1: Setup ───────────────────────────────────────────────────────────

def cmd_setup(args):
    if args.doc_type not in DOC_TYPES:
        sys.exit(f"ERROR: --doc-type must be one of: {', '.join(DOC_TYPES)}")
    if not os.path.exists(args.pdf):
        sys.exit(f"ERROR: PDF not found: {args.pdf}")
    if not os.path.exists(args.protocol_golden_set):
        sys.exit(f"ERROR: protocol golden set not found: {args.protocol_golden_set}")

    gs = load_json(args.protocol_golden_set)
    if "kris" not in gs:
        sys.exit("ERROR: protocol golden set JSON must have a 'kris' key")

    out_dir = os.path.expanduser(
        f"~/Downloads/extractor/{args.protocol_id}/{args.run_id}/accompanying/{args.doc_type}"
    )
    os.makedirs(os.path.join(out_dir, "raw_extractions"), exist_ok=True)

    config = {
        "doc_type": args.doc_type,
        "doc_type_label": DOC_TYPES[args.doc_type],
        "pdf_path": os.path.abspath(args.pdf),
        "pdf_sha256": sha256_of_file(args.pdf),
        "protocol_golden_set_path": os.path.abspath(args.protocol_golden_set),
        "protocol_golden_set_sha256": sha256_of_file(args.protocol_golden_set),
        "protocol_golden_set_n_kris": len(gs["kris"]),
        "protocol_id": args.protocol_id,
        "run_id": args.run_id,
        "output_dir": out_dir,
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
        "pipeline_version": "0.1.0",
    }
    dump_json(config, os.path.join(out_dir, "run_config.json"))
    print(f"[setup] output dir: {out_dir}")
    print(f"[setup] doc type: {args.doc_type} ({DOC_TYPES[args.doc_type]})")
    print(f"[setup] protocol golden set loaded: {len(gs['kris'])} KRIs")
    print(f"[setup] run_config.json written.")


# ── Stage 3: Mechanical consensus tiering ────────────────────────────────────

def cmd_tier(args):
    out_dir = args.output_dir
    raw_dir = os.path.join(out_dir, "raw_extractions")
    files = sorted(pathlib.Path(raw_dir).glob("*.json"))
    if len(files) != 10:
        sys.exit(f"ERROR: expected 10 raw extraction files, found {len(files)}")

    all_agent_kris = []  # list of (agent_id, kri)
    for p in files:
        data = load_json(str(p))
        agent_id = data.get("agent_id", p.stem)
        for k in data.get("kris", []):
            all_agent_kris.append((agent_id, k))

    # Cluster: for each KRI, find all other KRIs semantically equivalent.
    clusters = []
    used = [False] * len(all_agent_kris)
    for i, (aid_i, k_i) in enumerate(all_agent_kris):
        if used[i]:
            continue
        cluster = [(aid_i, k_i)]
        used[i] = True
        for j in range(i + 1, len(all_agent_kris)):
            if used[j]:
                continue
            aid_j, k_j = all_agent_kris[j]
            if kris_equivalent(k_i, k_j):
                cluster.append((aid_j, k_j))
                used[j] = True
        clusters.append(cluster)

    # Assign tier by unique-agent count in the cluster
    tiered = []
    for idx, cluster in enumerate(clusters):
        unique_agents = {aid for aid, _ in cluster}
        n = len(unique_agents)
        if n >= 7:
            tier = "T1"
        elif n >= 4:
            tier = "T2"
        else:
            tier = "T3"
        # representative KRI: the one whose supporting_quote is longest (proxy for most specific)
        rep = max(cluster, key=lambda x: len(x[1].get("supporting_quote", "") or ""))[1]
        tiered.append({
            "cluster_idx": idx,
            "tier": tier,
            "n_agents": n,
            "agents": sorted(unique_agents),
            "representative_kri": rep,
            "all_variants": [k for _, k in cluster],
        })

    summary = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_raw_inputs": len(all_agent_kris),
        "n_clusters": len(clusters),
        "tier_counts": {
            "T1": sum(1 for t in tiered if t["tier"] == "T1"),
            "T2": sum(1 for t in tiered if t["tier"] == "T2"),
            "T3": sum(1 for t in tiered if t["tier"] == "T3"),
        },
        "clusters": tiered,
    }
    dump_json(summary, os.path.join(out_dir, "consensus_report.json"))
    print(f"[tier] wrote consensus_report.json — {summary['tier_counts']}")


# ── Stage 5a: Dedup vs protocol golden set ───────────────────────────────────

def cmd_dedup_protocol(args):
    cfg = load_json(os.path.join(args.output_dir, "run_config.json"))
    candidates = load_json(args.candidates)    # {"kris": [...]}
    protocol = load_json(cfg["protocol_golden_set_path"])

    dropped = []
    kept = []
    for k in candidates.get("kris", []):
        match = None
        for p in protocol["kris"]:
            # verbatim quote match
            if quote_verbatim_match(k.get("supporting_quote", ""), p.get("supporting_quote", "")):
                match = (p, "quote_verbatim", 1.0)
                break
            j = jaccard_tokens(k.get("rule_for_llm", ""), p.get("rule_for_llm", ""))
            if j >= 0.85:
                match = (p, "rule_jaccard", j)
                break
        if match:
            dropped.append({
                "candidate": k,
                "matched_protocol_kri_id": match[0].get("kri_id"),
                "match_type": match[1],
                "score": match[2],
            })
        else:
            kept.append(k)

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_candidates_in": len(candidates.get("kris", [])),
        "n_dropped": len(dropped),
        "n_kept": len(kept),
        "dropped": dropped,
    }
    dump_json(report, os.path.join(args.output_dir, "protocol_dedup_report.json"))
    dump_json({"kris": kept}, os.path.join(args.output_dir, "after_protocol_dedup.json"))
    print(f"[dedup-protocol] dropped {len(dropped)}, kept {len(kept)}")


# ── Stage 5b: Intra-document dedup ───────────────────────────────────────────

def cmd_dedup_intra(args):
    data = load_json(os.path.join(args.output_dir, "after_protocol_dedup.json"))
    kris = data["kris"]

    used = [False] * len(kris)
    kept = []
    merges = []
    for i, k_i in enumerate(kris):
        if used[i]:
            continue
        cluster_idx = [i]
        used[i] = True
        for j in range(i + 1, len(kris)):
            if used[j]:
                continue
            if kris_equivalent(k_i, kris[j]):
                cluster_idx.append(j)
                used[j] = True
        # pick the survivor: longest rule_for_llm + longest supporting_quote
        survivor_idx = max(cluster_idx,
                           key=lambda x: (len(kris[x].get("rule_for_llm", "") or ""),
                                          len(kris[x].get("supporting_quote", "") or "")))
        kept.append(kris[survivor_idx])
        if len(cluster_idx) > 1:
            merges.append({
                "kept_index": survivor_idx,
                "kept_kri_name": kris[survivor_idx].get("kri_name"),
                "merged_indices": [x for x in cluster_idx if x != survivor_idx],
                "merged_kri_names": [kris[x].get("kri_name") for x in cluster_idx if x != survivor_idx],
            })

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_in": len(kris),
        "n_out": len(kept),
        "merges": merges,
    }
    dump_json(report, os.path.join(args.output_dir, "intra_dedup_report.json"))
    dump_json({"kris": kept}, os.path.join(args.output_dir, "after_intra_dedup.json"))
    print(f"[dedup-intra] in={len(kris)}, out={len(kept)}, merges={len(merges)}")


# ── Stage 6: NDEF candidate pre-screen (regex Pass 6.1 only) ─────────────────
#
# This script implements ONLY Pass 6.1 (regex candidate flagging). The
# definitive classification is done by the 6-judge panel in Pass 6.2 — the
# top-level Claude orchestrator is responsible for that, per SKILL.md Stage 6.
# This script's output is consumed by the panel as the candidate set.
#
# Design principles:
#   - Be liberal on candidate flagging: false-positive candidates are filtered
#     by the panel; missed candidates risk leaving NDEF KRIs in the main list.
#   - Default disposition for non-candidates remains DEFINABLE — the panel
#     samples 10% of non-candidates as a false-negative check.
#   - Triggers cover the protocol skill's NDEF criteria AND user-named
#     classes ("at the discretion of doctor/pharmacist/CRA", "according to
#     clinical need", "best efforts", etc.).
#   - Borderline phrases that often appear next to definable thresholds
#     ("as required", "as necessary" alone) are intentionally NOT triggers —
#     the panel handles them.

NDEF_TRIGGERS = [
    # Discretion language — clear NDEF
    r"\bat (?:the )?(?:sole )?discretion of\b",
    r"\bat the (?:sponsor'?s|investigator'?s|cra'?s|pharmacist'?s|doctor'?s|physician'?s) discretion\b",
    r"\bas deemed (?:appropriate|necessary|fit|required)\b",
    r"\bif deemed (?:appropriate|necessary|fit|required)\b",
    # Investigator clinical judgment
    r"\bin the (?:investigator'?s|physician'?s|doctor'?s|pi'?s) (?:opinion|judgment|judgement)\b",
    r"\bif clinically (?:significant|indicated|relevant|warranted)\b",
    r"\bclinically (?:significant|relevant|indicated)\b",
    r"\bper clinical judg(?:e)?ment\b",
    r"\bclinical(?:ly)? judg(?:e)?ment\b",
    # Undefined time windows
    r"\bas soon as possible\b",
    r"\bin a timely manner\b",
    r"\bpromptly\b",
    r"\bwithout undue delay\b",
    r"\bwithin a reasonable (?:time|period)\b",
    r"\bin due (?:time|course)\b",
    # Undefined effort / quantity
    r"\b(?:reasonable|best|great) effort(?:s)?\b",
    r"\bevery effort\b",
    r"\b(?:adequate|sufficient)(?:ly)?\b",  # standalone — panel filters when modifier
    r"\bappropriate(?:ly)?\b(?!\s+(?:section|table|level\s*\d|procedure|form))",  # standalone
    # "According to / as needed" — when standalone with no concrete trigger
    r"\baccording to clinical need\b",
    r"\baccording to (?:clinical|medical) (?:judg(?:e)?ment|practice)\b",
    r"\bas (?:clinically )?(?:needed|required|indicated)\b",
    r"\bif (?:medically|clinically) (?:needed|required|indicated)\b",
    # "Where feasible / possible / applicable" without a concrete bound
    r"\bwhere (?:feasible|possible|applicable|practical|practicable)\b",
    r"\bwhenever (?:feasible|possible|practical|practicable)\b",
    # Subjective / soft thresholds
    r"\bsubject to\b.*\b(?:judg(?:e)?ment|review|approval|interpretation)\b",
    r"\bshould (?:consider|use (?:their )?judg(?:e)?ment|exercise judg(?:e)?ment)\b",
    r"\bwhen (?:appropriate|necessary|required)\b.*\bjudg(?:e)?ment\b",
    # Per-local-practice (often NDEF; panel decides)
    r"\bper local (?:practice|standard|guidance|sop)\b",
    r"\bper (?:institutional|local) policy\b",
]
NDEF_RES = [re.compile(p, re.IGNORECASE) for p in NDEF_TRIGGERS]


def cmd_ndef(args):
    """Pass 6.1 — regex candidate pre-screen.

    Marks each KRI with `ndef_candidate` (bool) and matched `trigger_phrases`.
    Does NOT set `ndef` (final classification) — that is done by the 6-judge
    panel (Pass 6.2) orchestrated by Claude per SKILL.md Stage 6.
    """
    data = load_json(os.path.join(args.output_dir, "after_intra_dedup.json"))
    kris = data["kris"]

    results = []
    for k in kris:
        combined = " ".join([k.get("rule_for_llm", "") or "", k.get("supporting_quote", "") or ""])
        hits = []
        for pat in NDEF_RES:
            m = pat.search(combined)
            if m:
                hits.append(m.group(0))
        candidate = bool(hits)
        # Pass 6.1 sets candidate flag and trigger phrases ONLY.
        # Final ndef classification is set by Pass 6.2 panel.
        k["ndef_candidate"] = candidate
        k["ndef_trigger_phrases"] = hits
        # ndef remains False until the panel decides.
        if "ndef" not in k:
            k["ndef"] = False
        results.append({
            "kri_name": k.get("kri_name"),
            "ndef_candidate": candidate,
            "trigger_phrases": hits,
        })

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "pass": "6.1 — regex candidate pre-screen",
        "n_kris": len(kris),
        "n_candidates": sum(1 for r in results if r["ndef_candidate"]),
        "note": "Final NDEF classification is set by the Pass 6.2 6-judge panel (orchestrated by Claude per SKILL.md Stage 6). This file is the candidate input for that panel.",
        "per_kri": results,
    }
    dump_json(report, os.path.join(args.output_dir, "ndef_sweep_report.json"))
    dump_json({"kris": kris}, os.path.join(args.output_dir, "after_ndef.json"))
    print(f"[ndef-prescreen] total={len(kris)}, candidates={report['n_candidates']}")
    print(f"[ndef-prescreen] Pass 6.2 (6-judge panel) must run before Stage 7.")


# ── Stage 8: Assemble ────────────────────────────────────────────────────────

def cmd_assemble(args):
    cfg = load_json(os.path.join(args.output_dir, "run_config.json"))
    data = load_json(os.path.join(args.output_dir, "after_ndef.json"))
    kris = data["kris"]

    main_kris = [k for k in kris if not k.get("ndef", False)]
    ndef_kris = [k for k in kris if k.get("ndef", False)]

    # Assign IDs in combined order (main first, then ndef)
    doc_type = cfg["doc_type"]
    seq = 1
    for group in (main_kris, ndef_kris):
        for k in group:
            k["kri_id"] = f"{doc_type}-{seq:03d}"
            # Recompute combined_ref defensively
            dr = (k.get("document_reference") or "").strip()
            sq = (k.get("supporting_quote") or "").strip().strip('"')
            k["supporting_quote"] = sq
            k["combined_ref"] = f'{dr} — "{sq}"' if dr and sq else ""
            k["doc_type"] = doc_type
            k["doc_type_label"] = cfg["doc_type_label"]
            seq += 1

    out = {
        "meta": {
            "doc_type": doc_type,
            "doc_type_label": cfg["doc_type_label"],
            "protocol_id": cfg["protocol_id"],
            "run_id": cfg["run_id"],
            "protocol_golden_set_sha256": cfg["protocol_golden_set_sha256"],
            "pdf_sha256": cfg["pdf_sha256"],
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "n_kris": len(main_kris),
            "n_ndef_kris": len(ndef_kris),
        },
        "kris": main_kris,
        "ndef_kris": ndef_kris,
    }
    dump_json(out, os.path.join(args.output_dir, "accompanying_golden_set.json"))

    # Excel — column structure mirrors the protocol-kri-extractor skill:
    #   KRI ID | Category | KRI Name | Description | Rule for LLM | Document Reference & Quote
    # NDEF KRIs appear as a second table on the SAME sheet, below the main
    # table (separated by a blank row + a "Non-Definable KRIs" header row).
    # Severity is preserved in JSON only — it is NOT a column in the Excel,
    # matching the protocol skill's column set.
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = Workbook()
        ws = wb.active
        ws.title = "KRIs"

        HEADER = ["KRI ID", "Category", "KRI Name", "Description",
                  "Rule for LLM", "Document Reference & Quote"]

        def kri_row(k):
            return [k.get("kri_id"), k.get("doc_type_label"), k.get("kri_name"),
                    k.get("description"), k.get("rule_for_llm"), k.get("combined_ref")]

        bold = Font(bold=True, color="FFFFFF")
        fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        ndef_fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        wrap = Alignment(wrap_text=True, vertical="top")

        # ── Main table ────────────────────────────────────────────────────────
        ws.append(HEADER)
        for c in range(1, len(HEADER) + 1):
            ws.cell(1, c).font = bold
            ws.cell(1, c).fill = fill
            ws.cell(1, c).alignment = Alignment(horizontal="center", wrap_text=True)
        for k in main_kris:
            ws.append(kri_row(k))

        # ── Spacer + NDEF sub-table on same sheet ────────────────────────────
        if ndef_kris:
            ws.append([])  # blank row
            label_row = ws.max_row + 1
            ws.cell(label_row, 1, "Non-Definable KRIs").font = Font(bold=True, color="FFFFFF", size=12)
            ws.cell(label_row, 1).fill = ndef_fill
            ws.merge_cells(start_row=label_row, start_column=1,
                           end_row=label_row, end_column=len(HEADER))
            ws.append(HEADER)
            sub_header_row = ws.max_row
            for c in range(1, len(HEADER) + 1):
                ws.cell(sub_header_row, c).font = bold
                ws.cell(sub_header_row, c).fill = ndef_fill
                ws.cell(sub_header_row, c).alignment = Alignment(horizontal="center", wrap_text=True)
            for k in ndef_kris:
                ws.append(kri_row(k))

        # Apply wrap to all data rows + reasonable column widths
        for col_letter, width in zip("ABCDEF", [12, 22, 28, 60, 60, 50]):
            ws.column_dimensions[col_letter].width = width
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap

        # ── Dropped-vs-protocol sheet (audit trail of Stage 5a) ──────────────
        prot_dedup_path = os.path.join(args.output_dir, "protocol_dedup_report.json")
        if os.path.exists(prot_dedup_path):
            rep = load_json(prot_dedup_path)
            ws3 = wb.create_sheet("Dropped (vs protocol)")
            ws3.append(["Candidate KRI Name", "Matched Protocol KRI ID", "Match Type", "Score",
                        "Candidate Rule", "Candidate Quote"])
            for c in range(1, 7):
                ws3.cell(1, c).font = bold
                ws3.cell(1, c).fill = fill
            for row in rep.get("dropped", []):
                c = row["candidate"]
                ws3.append([c.get("kri_name"), row.get("matched_protocol_kri_id"),
                            row.get("match_type"), row.get("score"),
                            c.get("rule_for_llm"), c.get("supporting_quote")])

        xlsx_path = os.path.join(args.output_dir, "Accompanying_KRIs.xlsx")
        wb.save(xlsx_path)
        print(f"[assemble] Excel: {xlsx_path}")
    except ImportError:
        print("[assemble] WARNING: openpyxl not installed; skipping Excel output.")

    print(f"[assemble] golden set: {len(main_kris)} KRIs + {len(ndef_kris)} NDEF")
    print(f"[assemble] output dir: {args.output_dir}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Accompanying-doc KRI extractor orchestration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup")
    s.add_argument("--pdf", required=True)
    s.add_argument("--doc-type", required=True)
    s.add_argument("--protocol-golden-set", required=True)
    s.add_argument("--protocol-id", required=True)
    s.add_argument("--run-id", required=True)
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("tier")
    s.add_argument("--output-dir", required=True)
    s.set_defaults(func=cmd_tier)

    s = sub.add_parser("dedup-protocol")
    s.add_argument("--output-dir", required=True)
    s.add_argument("--candidates", required=True, help="JSON with {'kris': [...]} of the post-tiering/orphan candidate set")
    s.set_defaults(func=cmd_dedup_protocol)

    s = sub.add_parser("dedup-intra")
    s.add_argument("--output-dir", required=True)
    s.set_defaults(func=cmd_dedup_intra)

    s = sub.add_parser("ndef")
    s.add_argument("--output-dir", required=True)
    s.set_defaults(func=cmd_ndef)

    s = sub.add_parser("assemble")
    s.add_argument("--output-dir", required=True)
    s.set_defaults(func=cmd_assemble)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
