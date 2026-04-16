#!/usr/bin/env python3
"""Compare V7 KRIs against V5 and V6 across all 5 categories.

Strategy:
1. For SOA: IDs were renumbered between versions, so we match semantically
   based on visit+activity topic, not by ID.
2. For non-SOA categories: IDs are stable, match by ID first, then semantic.
3. Judge each pair: EQUIVALENT, SUBSET, SUPERSET, DIVERGENT.
"""
import json
import os
import re

BASE = os.environ.get("KRI_COMPARE_BASE", os.path.expanduser("~/Downloads/protocol Parser"))
CATEGORIES = ["SOA", "ELIG", "SAF", "END", "OPS"]

def load_kris(ver, cat):
    path = os.path.join(BASE, f"output_ENX_{ver}", f"raw_{cat}.json")
    with open(path) as f:
        data = json.load(f)
    if "kris" in data:
        return data["kris"]
    elif isinstance(data, list):
        return data
    else:
        for v in data.values():
            if isinstance(v, list):
                return v
    return []

def get_id(item):
    return item.get("kri_id", item.get("id", ""))

def get_name(item):
    return item.get("kri_name", item.get("name", item.get("sub_category", "")))

def get_rule(item):
    return item.get("rule_for_llm", item.get("rule_to_check", item.get("protocol_text", item.get("description", ""))))

def get_desc(item):
    return item.get("description", item.get("protocol_text", ""))

def normalize(text):
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return t

def extract_visit(kri_id):
    parts = kri_id.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return kri_id

def extract_activity_keywords(item):
    """Extract the core activity topic from name/description, ignoring visit info."""
    name = get_name(item).lower()
    desc = get_desc(item).lower()
    # Remove visit references
    combined = f"{name} {desc}"
    combined = re.sub(r'\b(at |at v\d|at s-?[i]+|at visit \d|at screening [i]+|at uns|v\d|s-?i+|screening [i]+)\b', '', combined)
    combined = re.sub(r'\b(visit \d|day \d+|eos|end of study|unscheduled)\b', '', combined)
    combined = re.sub(r'\s+', ' ', combined).strip()
    return combined

def word_overlap(text_a, text_b):
    words_a = set(text_a.split())
    words_b = set(text_b.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a | words_b), 1)

def semantic_match_score(item_a, item_b):
    """Score semantic similarity between two KRIs."""
    id_a = get_id(item_a)
    id_b = get_id(item_b)

    # Visit prefix match
    visit_a = extract_visit(id_a) if id_a else ""
    visit_b = extract_visit(id_b) if id_b else ""
    visit_match = 1.0 if visit_a and visit_b and visit_a == visit_b else 0.0

    # Activity keywords match (visit-agnostic)
    act_a = extract_activity_keywords(item_a)
    act_b = extract_activity_keywords(item_b)
    act_overlap = word_overlap(normalize(act_a), normalize(act_b))

    # Full name overlap
    name_overlap = word_overlap(normalize(get_name(item_a)), normalize(get_name(item_b)))

    # Rule overlap
    rule_overlap = word_overlap(normalize(get_rule(item_a)), normalize(get_rule(item_b)))

    # For SOA, activity match is most important, plus same visit
    score = visit_match * 0.25 + act_overlap * 0.30 + name_overlap * 0.20 + rule_overlap * 0.25
    return score

def judge_relationship(item_old, item_new):
    """Judge: EQUIVALENT, SUBSET (V7 less specific), SUPERSET (V7 adds detail), DIVERGENT."""
    name_old = normalize(get_name(item_old))
    name_new = normalize(get_name(item_new))
    rule_old = normalize(get_rule(item_old))
    rule_new = normalize(get_rule(item_new))

    # Check if the activities are about the same thing first
    act_old = normalize(extract_activity_keywords(item_old))
    act_new = normalize(extract_activity_keywords(item_new))
    act_sim = word_overlap(act_old, act_new)

    # Check visit match
    id_old = get_id(item_old)
    id_new = get_id(item_new)
    visit_old = extract_visit(id_old) if id_old else ""
    visit_new = extract_visit(id_new) if id_new else ""
    same_visit = visit_old == visit_new

    # If activities are very different and different visit, divergent
    if act_sim < 0.20:
        return "DIVERGENT"

    words_old = set(rule_old.split())
    words_new = set(rule_new.split())
    if not words_old or not words_new:
        return "DIVERGENT"

    overlap = len(words_old & words_new)
    old_coverage = overlap / len(words_old)
    new_coverage = overlap / len(words_new)

    # Both well covered by overlap = equivalent
    if old_coverage > 0.50 and new_coverage > 0.50:
        return "EQUIVALENT"
    # Old is well covered by new (new contains old's info + more) = V7 superset
    elif old_coverage > 0.45 and new_coverage < 0.40:
        return "SUPERSET"
    # New is well covered by old (old contains new's info + more) = V7 subset
    elif new_coverage > 0.45 and old_coverage < 0.40:
        return "SUBSET"
    else:
        # Names are similar? Probably equivalent with rewording.
        name_sim = word_overlap(name_old, name_new)
        if name_sim > 0.4 or act_sim > 0.35:
            # Same activity, likely just reworded
            if len(words_new) > len(words_old) * 1.4:
                return "SUPERSET"
            elif len(words_old) > len(words_new) * 1.4:
                return "SUBSET"
            else:
                return "EQUIVALENT"
        # Same visit and moderate activity overlap
        if same_visit and act_sim > 0.25:
            return "EQUIVALENT"
        return "DIVERGENT"

def compare_soa(old_ver, old_items, new_items):
    """SOA comparison: IDs may be renumbered, so match semantically.
    Strategy: for each old item, find best semantic match in new items.
    Use Hungarian-like greedy matching with score threshold."""
    pairs = []
    matched_old = set()
    matched_new = set()

    # Build all pairwise scores
    scores = []
    for i, o_item in enumerate(old_items):
        for j, n_item in enumerate(new_items):
            score = semantic_match_score(o_item, n_item)
            if score >= 0.30:
                scores.append((score, i, j))

    # Greedy match: highest scores first
    scores.sort(reverse=True)
    for score, i, j in scores:
        if i in matched_old or j in matched_new:
            continue
        o_item = old_items[i]
        n_item = new_items[j]
        oid = get_id(o_item)
        nid = get_id(n_item)
        judgment = judge_relationship(o_item, n_item)

        match_type = "exact_id" if oid == nid else "semantic"
        pair = {
            f"{old_ver}_id": oid,
            f"{old_ver}_name": get_name(o_item),
            "v7_id": nid,
            "v7_name": get_name(n_item),
            "match_type": match_type,
            "match_score": round(score, 3),
            "judgment": judgment
        }
        pairs.append(pair)
        matched_old.add(i)
        matched_new.add(j)

    missing = []
    for i, item in enumerate(old_items):
        if i not in matched_old:
            missing.append({
                f"{old_ver}_id": get_id(item),
                f"{old_ver}_name": get_name(item),
                "description": get_desc(item)[:200]
            })

    extra = []
    for j, item in enumerate(new_items):
        if j not in matched_new:
            extra.append({
                "v7_id": get_id(item),
                "v7_name": get_name(item),
                "description": get_desc(item)[:200]
            })

    judgments = [p["judgment"] for p in pairs]
    summary = {
        "equivalent": judgments.count("EQUIVALENT"),
        "subset": judgments.count("SUBSET"),
        "superset": judgments.count("SUPERSET"),
        "divergent": judgments.count("DIVERGENT"),
        "missing_from_v7": len(missing),
        "extra_in_v7": len(extra)
    }

    return {
        f"{old_ver}_count": len(old_items),
        "v7_count": len(new_items),
        "summary": summary,
        "pairs": pairs,
        "missing": missing,
        "extra": extra
    }

def compare_standard(old_ver, old_items, new_items):
    """Non-SOA comparison: IDs are stable, match by ID first, then semantic."""
    pairs = []
    matched_old = set()
    matched_new = set()

    old_by_id = {get_id(item): item for item in old_items}
    new_by_id = {get_id(item): item for item in new_items}

    for oid, o_item in old_by_id.items():
        if oid in new_by_id:
            n_item = new_by_id[oid]
            judgment = judge_relationship(o_item, n_item)
            pairs.append({
                f"{old_ver}_id": oid,
                f"{old_ver}_name": get_name(o_item),
                "v7_id": oid,
                "v7_name": get_name(n_item),
                "match_type": "exact_id",
                "judgment": judgment
            })
            matched_old.add(oid)
            matched_new.add(oid)

    # Semantic matching for unmatched
    unmatched_old = [item for item in old_items if get_id(item) not in matched_old]
    unmatched_new = [item for item in new_items if get_id(item) not in matched_new]

    for o_item in unmatched_old:
        best_score = 0
        best_match = None
        for n_item in unmatched_new:
            nid = get_id(n_item)
            if nid in matched_new:
                continue
            score = semantic_match_score(o_item, n_item)
            if score > best_score:
                best_score = score
                best_match = n_item

        if best_match and best_score >= 0.35:
            nid = get_id(best_match)
            judgment = judge_relationship(o_item, best_match)
            pairs.append({
                f"{old_ver}_id": get_id(o_item),
                f"{old_ver}_name": get_name(o_item),
                "v7_id": nid,
                "v7_name": get_name(best_match),
                "match_type": "semantic",
                "match_score": round(best_score, 3),
                "judgment": judgment
            })
            matched_old.add(get_id(o_item))
            matched_new.add(nid)

    missing = []
    for item in old_items:
        oid = get_id(item)
        if oid not in matched_old:
            missing.append({
                f"{old_ver}_id": oid,
                f"{old_ver}_name": get_name(item),
                "description": get_desc(item)[:200]
            })

    extra = []
    for item in new_items:
        nid = get_id(item)
        if nid not in matched_new:
            extra.append({
                "v7_id": nid,
                "v7_name": get_name(item),
                "description": get_desc(item)[:200]
            })

    judgments = [p["judgment"] for p in pairs]
    summary = {
        "equivalent": judgments.count("EQUIVALENT"),
        "subset": judgments.count("SUBSET"),
        "superset": judgments.count("SUPERSET"),
        "divergent": judgments.count("DIVERGENT"),
        "missing_from_v7": len(missing),
        "extra_in_v7": len(extra)
    }

    return {
        f"{old_ver}_count": len(old_items),
        "v7_count": len(new_items),
        "summary": summary,
        "pairs": pairs,
        "missing": missing,
        "extra": extra
    }

def main():
    for cat in CATEGORIES:
        print(f"\n=== Processing {cat} ===")
        v7_items = load_kris("v7", cat)

        for old_ver in ["v5", "v6"]:
            old_items = load_kris(old_ver, cat)

            if cat == "SOA":
                result = compare_soa(old_ver, old_items, v7_items)
            else:
                result = compare_standard(old_ver, old_items, v7_items)

            out_path = os.path.join(BASE, "output_ENX_v7", f"{old_ver}v7_comparison_{cat}.json")
            with open(out_path, 'w') as f:
                json.dump(result, f, indent=2)

            s = result["summary"]
            print(f"  {old_ver} vs v7 [{cat}]: {old_ver}={result[f'{old_ver}_count']}, v7={result['v7_count']}")
            print(f"    eq={s['equivalent']}, sub={s['subset']}, sup={s['superset']}, div={s['divergent']}, miss={s['missing_from_v7']}, extra={s['extra_in_v7']}")

if __name__ == "__main__":
    main()
