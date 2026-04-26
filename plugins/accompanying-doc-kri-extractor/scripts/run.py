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


# ── Stage 6: NDEF rule-based sweep ───────────────────────────────────────────

NDEF_TRIGGERS = [
    r"\bas appropriate\b",
    r"\bas necessary\b",
    r"\bwhere (?:feasible|possible|applicable)\b",
    r"\bat the (?:sponsor'?s|investigator'?s|sponsor's|sponsor) discretion\b",
    r"\bat the discretion of\b",
    r"\bshould (?:consider|use (?:their )?judg[e]?ment|exercise judg[e]?ment)\b",
    r"\bif clinically indicated\b",
    r"\bas (?:clinically )?indicated\b",
    r"\bsubject to\b.*\b(?:judgment|review|approval)\b",
    r"\bif deemed\b",
    r"\bas (?:deemed|determined) (?:appropriate|necessary)\b",
    r"\bwhen (?:appropriate|necessary|required)\b.*\bjudg[e]?ment\b",
    r"\bper local (?:practice|standard|guidance)\b",
    r"\bper (?:institutional|local) policy\b",
]
NDEF_RES = [re.compile(p, re.IGNORECASE) for p in NDEF_TRIGGERS]


def cmd_ndef(args):
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
        ndef = bool(hits)
        k["ndef"] = ndef
        results.append({
            "kri_name": k.get("kri_name"),
            "ndef": ndef,
            "trigger_phrases": hits,
        })

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_kris": len(kris),
        "n_ndef": sum(1 for r in results if r["ndef"]),
        "per_kri": results,
    }
    dump_json(report, os.path.join(args.output_dir, "ndef_sweep_report.json"))
    dump_json({"kris": kris}, os.path.join(args.output_dir, "after_ndef.json"))
    print(f"[ndef] total={len(kris)}, ndef={report['n_ndef']}")


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

    # Excel
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "KRIs"
        header = ["KRI ID", "KRI Name", "Description", "Doc Type",
                  "Rule for LLM", "Document Reference & Quote", "Severity", "NDEF"]
        ws.append(header)
        for k in main_kris:
            ws.append([k.get("kri_id"), k.get("kri_name"), k.get("description"),
                       k.get("doc_type"), k.get("rule_for_llm"),
                       k.get("combined_ref"), k.get("severity"),
                       "No"])

        ws2 = wb.create_sheet("NDEF")
        ws2.append(header)
        for k in ndef_kris:
            ws2.append([k.get("kri_id"), k.get("kri_name"), k.get("description"),
                        k.get("doc_type"), k.get("rule_for_llm"),
                        k.get("combined_ref"), k.get("severity"),
                        "Yes"])

        # Dropped-vs-protocol sheet (optional if file exists)
        prot_dedup_path = os.path.join(args.output_dir, "protocol_dedup_report.json")
        if os.path.exists(prot_dedup_path):
            rep = load_json(prot_dedup_path)
            ws3 = wb.create_sheet("Dropped (vs protocol)")
            ws3.append(["Candidate KRI Name", "Matched Protocol KRI ID", "Match Type", "Score",
                        "Candidate Rule", "Candidate Quote"])
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
