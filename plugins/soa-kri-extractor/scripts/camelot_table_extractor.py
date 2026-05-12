#!/usr/bin/env python3
"""
Camelot-based Table Extractor for Protocol PDFs.

Uses Camelot (lattice mode) to extract structured tables from protocol PDFs,
producing CSV and JSON output that the LLM can use for KRI generation.

This replaces vision-based table extraction for protocols with well-defined
table lines (lattice tables), giving ~99% structural accuracy.

Usage:
    python camelot_table_extractor.py --pdf protocol.pdf --out output_dir/
    python camelot_table_extractor.py --pdf protocol.pdf --pages 24 --out output_dir/

Dependencies:
    pip install camelot-py[cv] ghostscript --break-system-packages -q
"""

import argparse
import csv
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

try:
    import camelot
except ImportError:
    print("ERROR: camelot-py not installed. Run: pip install camelot-py[cv] --break-system-packages -q")
    sys.exit(1)


def find_soa_tables(pdf_path, page_range=None):
    """Scan PDF pages for large tables that are likely SoA tables.

    Args:
        pdf_path: Path to the protocol PDF
        page_range: Optional "start-end" page range to scan (e.g. "20-35").
                    If None, scans pages 1-60.

    Returns:
        List of dicts with page number, table object, and shape info.
    """
    if page_range:
        start, end = map(int, page_range.split("-"))
    else:
        start, end = 1, 60

    soa_candidates = []

    for page in range(start, end + 1):
        try:
            tables = camelot.read_pdf(pdf_path, pages=str(page), flavor="lattice")
            for i, t in enumerate(tables):
                rows, cols = t.shape
                if cols >= 8:  # SoA tables typically have 8+ columns (visits)
                    soa_candidates.append({
                        "page": page,
                        "table_index": i,
                        "table": t,
                        "rows": rows,
                        "cols": cols,
                        "accuracy": round(t.accuracy, 1),
                    })
        except Exception:
            continue

    # Sort by column count descending — the widest table is most likely the SoA
    soa_candidates.sort(key=lambda x: x["cols"], reverse=True)
    return soa_candidates


def extract_soa_from_page(pdf_path, page_num):
    """Extract the SoA table from a specific page using Camelot lattice mode.

    Args:
        pdf_path: Path to the protocol PDF
        page_num: 1-indexed page number

    Returns:
        camelot Table object, or None if no table found
    """
    tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor="lattice")
    if not tables:
        return None

    # Return the table with the most columns (most likely the SoA)
    best = max(tables, key=lambda t: t.shape[1])
    return best


def parse_soa_table(table):
    """Parse a Camelot table into a structured SoA matrix.

    Automatically detects:
    - Header rows (visit IDs, week numbers)
    - Procedure rows (with footnote numbers stripped)
    - X marks in cells

    Args:
        table: Camelot Table object

    Returns:
        dict with:
            - visits: ordered list of visit dicts {id, label, week, column_index}
            - procedures: ordered list of procedure dicts {name, footnote, visits_present}
            - matrix: dict mapping (procedure, visit_id) -> "X" or ""
            - raw_df: the pandas DataFrame
    """
    df = table.df

    # --- Detect header rows ---
    # Strategy: find the row with "Visit Type" / "VISITS" / visit identifiers,
    # and the row with "Visit Window" / "Week" / timing information.
    visit_row_idx = None
    window_row_idx = None
    epoch_row_idx = None
    header_end_idx = 0

    for idx in range(min(6, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[idx]]
        row_text = " ".join(row_vals).lower()
        # Count unique non-empty values (epoch rows have few unique values like "Screening","Treatment")
        unique_nonempty = len(set(v for v in row_vals[1:] if v.strip()))

        # Detect visit identifier row (numbers or specific visit names)
        numeric_count = sum(1 for v in row_vals[1:] if v.strip().isdigit())
        has_specific_visits = any(
            re.search(r"visit\s*(type|\d)|s-[iv]+|v\d|uns|treatment\s*#", v, re.I)
            for v in row_vals
        )

        # Epoch rows have very few unique values (2-3: Screening, Treatment, Follow Up)
        is_epoch_row = (unique_nonempty <= 4 and any(
            kw in row_text for kw in ["screening", "treatment", "follow up", "run in", "run-in"]
        ))

        if is_epoch_row:
            epoch_row_idx = idx
            header_end_idx = max(header_end_idx, idx + 1)
        elif numeric_count >= 5 or has_specific_visits:
            visit_row_idx = idx
            header_end_idx = max(header_end_idx, idx + 1)
        elif "window" in row_text or "week" in row_text or re.search(r"day\s*[-\d]", row_text):
            window_row_idx = idx
            header_end_idx = max(header_end_idx, idx + 1)

    if visit_row_idx is None:
        # Fallback: row 1 is usually the visit row (row 0 is epoch)
        visit_row_idx = 1
        header_end_idx = max(header_end_idx, 3)

    # Find first procedure row (skip any remaining header-like rows)
    for idx in range(header_end_idx, min(header_end_idx + 5, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[idx]]
        first_cell = row_vals[0].lower()
        # If the first cell looks like a section header or is empty, skip
        if first_cell and not any(kw in first_cell for kw in [
            "visit", "week", "window", "day", "study period", "screening",
            "treatment", "follow", "run in"
        ]):
            header_end_idx = idx
            break

    # --- Build visit mapping ---
    visits = []
    visit_row = df.iloc[visit_row_idx]
    epoch_row = df.iloc[epoch_row_idx] if epoch_row_idx is not None else None

    # Get window row if available
    windows = {}
    if window_row_idx is not None:
        for i in range(1, len(df.iloc[window_row_idx])):
            w = str(df.iloc[window_row_idx][i]).strip().replace("\n", " ")
            if w:
                windows[i] = w

    # Build a per-column "best header value" by combining content from ALL header
    # rows (rows 0 through header_end_idx). Many SoA tables split visit names
    # across multiple rows — e.g., epoch row "Treatment and Follow-up" on row 0,
    # window row "Week2" on row 1, visit-code row "2-11" on row 2 — AND for the
    # earlier columns the visit *name* itself (Screening, Day 1 Pre-dose) sits
    # on row 0 with row 2 empty. Single-row reading misses those columns.
    def _combined_header(col):
        parts = []
        seen = set()
        for r in range(0, max(header_end_idx, visit_row_idx + 1, (epoch_row_idx or 0) + 1, (window_row_idx or 0) + 1)):
            if r >= len(df):
                break
            v = str(df.iloc[r][col]).strip().replace("\n", " ")
            if v and v not in seen:
                parts.append(v)
                seen.add(v)
        return " ".join(parts).strip()

    for col_idx in range(1, len(visit_row)):
        primary_val = str(visit_row[col_idx]).strip().replace("\n", " ")
        # If the primary visit-row cell is empty for this column, fall back to
        # the combined header content from all header rows. This catches the
        # multi-row-header pattern above without breaking single-row tables.
        if not primary_val:
            combined = _combined_header(col_idx)
            # Strip out epoch keywords that aren't visit names (so "Screening Treatment and Follow-up"
            # → "Screening")
            for kw in ["Treatment and Follow-up", "Treatment and Follow up", "Extended F/U",
                       "Follow-up", "Follow up", "Treatment", "Run-in", "Run in"]:
                if kw in combined and combined.replace(kw, "").strip():
                    combined = combined.replace(kw, "").strip()
            raw_val = combined
        else:
            raw_val = primary_val
        epoch_val = str(epoch_row[col_idx]).strip() if epoch_row is not None else ""

        # Determine visit ID from various naming conventions
        visit_id = None
        label = raw_val

        # Strip trailing footnote-number suffixes that survive in some PDFs (e.g., "Screening1", "Unsch3")
        # — the footnote number is metadata, not part of the visit name.
        clean_val = re.sub(r"(\D)(\d{1,2})$", r"\1", raw_val).strip()

        # Check for EDC/EOS
        if re.search(r"EDC|EOS|end.of.study|early.discont", raw_val, re.I):
            visit_id = "EDC_EOS"
            label = "EDC/EOS"
        # Screening visit (e.g., "Screening", "Screening1", "Screening visit")
        elif re.match(r"^screening\b", clean_val, re.I):
            visit_id = "SCR"
            label = "Screening"
        # Day-N Pre-dose / Post-dose / Predose / Postdose
        elif re.search(r"\bday\s*(\d+)\b", clean_val, re.I):
            day_match = re.search(r"\bday\s*(\d+)\b", clean_val, re.I)
            day_num = day_match.group(1)
            timing = ""
            if re.search(r"pre[\s\-]?dose", clean_val, re.I):
                timing = "PRE"
            elif re.search(r"post[\s\-]?dose", clean_val, re.I):
                timing = "POST"
            visit_id = f"D{day_num}_{timing}" if timing else f"D{day_num}"
            label = clean_val
        # Check for numeric visit IDs (0, 1, 2, ... 20)
        elif raw_val.isdigit():
            vn = int(raw_val)
            visit_id = f"V{vn}"
            # Enrich label from epoch/header context
            header_val = str(df.iloc[0][col_idx]).strip() if len(df) > 0 else ""
            if "Pre" in header_val:
                label = f"V{vn} (Pre-screening)"
            elif "Scr" in header_val:
                label = f"V{vn} (Screening)"
            elif "Run" in header_val:
                label = f"V{vn} (Run-in)"
            else:
                label = f"V{vn}"
        # Check for named visits: "S-I", "S-II", "Visit 1", "V1", "UNS"
        elif re.search(r"S-I\b|S-II\b|S[-\s]?1\b|S[-\s]?2\b", raw_val, re.I):
            # Screening visits
            si_match = re.search(r"S[-\s]?(I{1,2}|\d)", raw_val, re.I)
            if si_match:
                num = si_match.group(1).upper()
                visit_id = f"S-{num}" if "I" in num else f"S-{'I' * int(num)}"
            else:
                visit_id = f"S_{col_idx}"
            label = raw_val
        elif re.search(r"Visit\s*(\d+)|V(\d+)|Treatment\s*#?\s*(\d+)", raw_val, re.I):
            match = re.search(r"Visit\s*(\d+)|V(\d+)|Treatment\s*#?\s*(\d+)", raw_val, re.I)
            num = match.group(1) or match.group(2) or match.group(3)
            visit_id = f"V{num}"
            label = raw_val
        elif re.search(r"UNS|unscheduled", raw_val, re.I):
            visit_id = "UNS"
            label = "Unscheduled Visit"
        elif re.search(r"\d+\s*month", raw_val, re.I):
            # "3 months", "6 months", "12 months"
            month_match = re.search(r"(\d+)\s*month", raw_val, re.I)
            if month_match:
                months = month_match.group(1)
                # Map to visit number if possible
                visit_id = f"V_{months}m"
                label = raw_val
        elif raw_val and not raw_val.isspace():
            # Fallback: use cleaned column value as visit ID
            visit_id = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_val)[:20]
            label = raw_val

        if visit_id is None:
            continue

        window = windows.get(col_idx, "")
        epoch = epoch_val if epoch_val else ""

        visits.append({
            "visit_id": visit_id,
            "label": label.replace("\n", " "),
            "week": window,
            "epoch": epoch,
            "column_index": col_idx,
        })

    # --- Parse procedure rows ---
    procedures = []
    matrix = {}
    data_start = header_end_idx

    for row_idx in range(data_start, len(df)):
        raw_proc = str(df.iloc[row_idx][0]).strip()
        raw_proc = raw_proc.replace("\n", " ").strip()

        # Skip empty rows and section headers like "Laboratory"
        if not raw_proc:
            continue

        # Extract trailing footnote numbers (e.g., "Informed Consents1" → fn [1])
        # Handles: single (3), multi-digit (10), compound (3,14), dot-separated (13·14)
        footnote_match = re.search(r"((?:\d+[,·])*\d+)\s*$", raw_proc)
        footnote_nums_raw = footnote_match.group(1) if footnote_match else None
        footnote_num = footnote_nums_raw  # preserve raw for downstream use
        if footnote_nums_raw:
            proc_name = raw_proc[:footnote_match.start()].strip()
            # Safety: if stripping leaves empty, keep original (e.g., "Phase 2" → "2" is not a footnote)
            if not proc_name:
                proc_name = raw_proc
                footnote_num = None
        else:
            proc_name = raw_proc

        # Parse each cell — match X/S marks with optional trailing footnote numbers
        # "X" → mark, "X10" → mark + fn[10], "X13,14" → mark + fn[13,14]
        has_any_x = False
        visits_present = []
        cell_footnotes_map = {}  # visit_id → list of footnote numbers from cell
        for visit in visits:
            cell = str(df.iloc[row_idx][visit["column_index"]]).strip()
            cell_upper = cell.upper().replace('\n', ' ').strip()
            cell_match = re.match(r'^([XS])\s*([\d,·\s]*)$', cell_upper, re.I)
            if cell_match:
                has_any_x = True
                visits_present.append(visit["visit_id"])
                matrix[(proc_name, visit["visit_id"])] = "X"
                # Extract cell-level footnote numbers
                fn_str = cell_match.group(2).strip()
                if fn_str:
                    fn_parts = re.split(r'[,·\s]+', fn_str)
                    cell_fns = [int(p) for p in fn_parts if p.isdigit()]
                    cell_footnotes_map[visit["visit_id"]] = cell_fns
            elif cell_upper == "X" or cell_upper == "S":
                has_any_x = True
                visits_present.append(visit["visit_id"])
                matrix[(proc_name, visit["visit_id"])] = cell_upper
            else:
                matrix[(proc_name, visit["visit_id"])] = ""

        if not has_any_x:
            continue  # Skip rows with no X marks (section headers)

        procedures.append({
            "name": proc_name,
            "footnote_number": footnote_num,
            "visits_present": visits_present,
            "visit_count": len(visits_present),
            "cell_footnotes": cell_footnotes_map,  # {visit_id: [fn_nums]}
        })

    return {
        "visits": visits,
        "procedures": procedures,
        "matrix": {f"{k[0]}|{k[1]}": v for k, v in matrix.items()},
        "total_procedures": len(procedures),
        "total_visits": len(visits),
        "total_x_cells": sum(1 for v in matrix.values() if v == "X"),
        "accuracy": round(table.accuracy, 1),
    }


def export_to_csv(parsed, out_path):
    """Export parsed SoA to a CSV file matching the original table format.

    Args:
        parsed: Output from parse_soa_table()
        out_path: Path to write the CSV
    """
    visit_ids = [v["visit_id"] for v in parsed["visits"]]
    visit_labels = [v["label"] for v in parsed["visits"]]
    weeks = [v["week"] for v in parsed["visits"]]

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        # Header rows
        writer.writerow(["Study Period"] + visit_labels)
        writer.writerow(["VISITS"] + visit_ids)
        writer.writerow(["Week"] + weeks)

        # Procedure rows
        for proc in parsed["procedures"]:
            row = [proc["name"]]
            for vid in visit_ids:
                key = f"{proc['name']}|{vid}"
                row.append("X" if parsed["matrix"].get(key) == "X" else "")
            writer.writerow(row)


def export_to_json(parsed, out_path):
    """Export parsed SoA to a JSON file for LLM consumption.

    The JSON format is designed for easy KRI generation:
    - Each visit lists its required procedures
    - Each procedure lists its required visits

    Args:
        parsed: Output from parse_soa_table()
        out_path: Path to write the JSON
    """
    # Build visit-centric view
    visit_procedures = {}
    for visit in parsed["visits"]:
        vid = visit["visit_id"]
        procs = []
        for proc in parsed["procedures"]:
            if vid in proc["visits_present"]:
                procs.append(proc["name"])
        visit_procedures[vid] = {
            "visit_id": vid,
            "label": visit["label"],
            "week": visit["week"],
            "procedure_count": len(procs),
            "procedures": procs,
        }

    output = {
        "source": "camelot-lattice-extraction",
        "accuracy": parsed["accuracy"],
        "total_visits": parsed["total_visits"],
        "total_procedures": parsed["total_procedures"],
        "total_x_cells": parsed["total_x_cells"],
        # `pages` records the actual PDF pages the SoA table was extracted from.
        # Downstream steps (1C footnote_mapper, 1D atomic_normalizer, Step 2 SOA
        # generator) use this to derive the table's page range and scan only the
        # right pages for footnote text — preventing body-section pages from
        # being mis-scanned as "footnote pages".
        "pages": parsed.get("pages") or [],
        "visits": parsed["visits"],
        "procedures": parsed["procedures"],
        "visit_procedures": visit_procedures,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def merge_multipage_tables(tables_by_page):
    """Merge SoA tables that span multiple PDF pages.

    Many protocols split the SoA across 2-3 pages. Each page has the same
    column headers (visits) but different procedure rows. This function
    detects matching column structures and merges procedure rows.

    Args:
        tables_by_page: List of (page_num, camelot_table) tuples

    Returns:
        Single merged parsed dict (same format as parse_soa_table output)
    """
    if len(tables_by_page) <= 1:
        return parse_soa_table(tables_by_page[0][1])

    # Parse all tables
    parsed_tables = []
    for page_num, table in tables_by_page:
        p = parse_soa_table(table)
        p["page"] = page_num
        parsed_tables.append(p)

    # Use the first table's visits as canonical (all pages should have same columns)
    base = parsed_tables[0]
    merged_visits = base["visits"]
    visit_ids = [v["visit_id"] for v in merged_visits]

    # Merge procedures from all pages, deduplicating by name
    seen_procs = set()
    merged_procs = []
    merged_matrix = {}

    for pt in parsed_tables:
        for proc in pt["procedures"]:
            name = proc["name"]
            if name in seen_procs:
                continue
            seen_procs.add(name)
            merged_procs.append(proc)
            for vid in visit_ids:
                key = f"{name}|{vid}"
                val = pt["matrix"].get(key, "")
                merged_matrix[key] = val

    total_x = sum(1 for v in merged_matrix.values() if v == "X")
    avg_accuracy = sum(t.accuracy for _, t in tables_by_page) / len(tables_by_page)

    return {
        "visits": merged_visits,
        "procedures": merged_procs,
        "matrix": merged_matrix,
        "total_procedures": len(merged_procs),
        "total_visits": len(merged_visits),
        "total_x_cells": total_x,
        "accuracy": round(avg_accuracy, 1),
        "pages": [p for p, _ in tables_by_page],
    }


def run_extraction(pdf_path, out_dir, pages=None):
    """Run the full Camelot extraction pipeline.

    Handles both single-page and multi-page SoA tables. When multiple pages
    are specified (or auto-detected), tables with the same column structure
    are merged into a single SoA matrix.

    Args:
        pdf_path: Path to the protocol PDF
        out_dir: Output directory
        pages: Optional specific page number(s) to extract from (comma-separated).
               If None, auto-detects SoA table pages.

    Returns:
        dict with extraction results and file paths
    """
    os.makedirs(out_dir, exist_ok=True)

    if pages:
        # Extract from specific page(s)
        page_list = [int(p) for p in str(pages).split(",")]
    else:
        # Auto-detect: find all pages with wide tables (8+ columns)
        candidates = find_soa_tables(pdf_path)
        if not candidates:
            print("ERROR: No tables found in the PDF.")
            return None

        # Group candidates by column count — SoA pages share the same column structure
        max_cols = candidates[0]["cols"]
        page_list = sorted(set(
            c["page"] for c in candidates
            if c["cols"] >= max_cols - 1  # Allow 1 col difference for tolerance
        ))
        print(f"Auto-detected SoA pages: {page_list} (max {max_cols} columns)")

    # Extract tables from all pages
    tables_by_page = []
    for p in page_list:
        t = extract_soa_from_page(pdf_path, p)
        if t:
            tables_by_page.append((p, t))
            print(f"  Page {p}: {t.shape[0]}r × {t.shape[1]}c, accuracy: {t.accuracy:.1f}%")

    if not tables_by_page:
        print("ERROR: No tables found in the specified pages.")
        return None

    # Single page or multi-page?
    if len(tables_by_page) == 1:
        page, table = tables_by_page[0]
        print(f"\nSingle-page SoA on page {page}: {table.shape[0]}r × {table.shape[1]}c")
        parsed = parse_soa_table(table)
        # Single-page parse does not record pages; set it explicitly so downstream
        # consumers always have a reliable source-of-truth list.
        parsed.setdefault("pages", [page])
    else:
        print(f"\nMulti-page SoA across {len(tables_by_page)} pages — merging...")
        parsed = merge_multipage_tables(tables_by_page)
        page = parsed.get("pages", [t[0] for t in tables_by_page])

    # Export
    csv_path = os.path.join(out_dir, "soa_table.csv")
    json_path = os.path.join(out_dir, "soa_table.json")

    export_to_csv(parsed, csv_path)
    export_to_json(parsed, json_path)

    print(f"\nExtraction Summary:")
    print(f"  Procedures: {parsed['total_procedures']}")
    print(f"  Visits: {parsed['total_visits']}")
    print(f"  X cells: {parsed['total_x_cells']}")
    print(f"  Accuracy: {parsed['accuracy']}%")
    print(f"\nOutput files:")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")

    return {
        "page": page,
        "parsed": parsed,
        "csv_path": csv_path,
        "json_path": json_path,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract SoA tables from protocol PDFs using Camelot")
    parser.add_argument("--pdf", required=True, help="Path to the protocol PDF")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--pages", help="Specific page number(s) to extract (comma-separated)")
    args = parser.parse_args()

    result = run_extraction(args.pdf, args.out, args.pages)
    if result:
        print(f"\nDone! SoA table extracted from page {result['page']}")
    else:
        print("Failed to extract SoA table.")
        sys.exit(1)
