#!/usr/bin/env python3
"""
Vision Table Extractor with Column Boundary Detection
Extracts tables from protocol PDF page images using pixel-level column detection.

Usage:
    python vision_table_extractor.py --pdf protocol.pdf --pages 22,23,24 --out output_dir/
"""

import fitz  # pymupdf
import json
import os
import sys
from collections import defaultdict


def extract_page_as_image(pdf_path, page_num, out_dir, dpi=300, crop=None):
    """Convert a single PDF page (or cropped region) to a high-res PNG image.

    Args:
        pdf_path: Path to the PDF file
        page_num: 1-indexed page number
        out_dir: Directory to save the PNG
        dpi: Resolution (300 for normal pages, 450 for SoA/table pages)
        crop: Optional crop region as "left", "right", or None for full page.
              "left" crops to the left 55% of the page (overlapping center).
              "right" crops to the right 55% of the page (overlapping center).

    Returns:
        Path to the saved PNG image
    """
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    page = doc[page_num - 1]  # 0-indexed

    if crop in ("left", "right"):
        # Get page dimensions and create clip rectangle
        rect = page.rect
        mid_x = rect.width * 0.55  # 55% overlap ensures center columns appear in both halves
        if crop == "left":
            clip = fitz.Rect(rect.x0, rect.y0, rect.x0 + mid_x, rect.y1)
        else:  # right
            clip = fitz.Rect(rect.x1 - mid_x, rect.y0, rect.x1, rect.y1)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        suffix = f"_{crop}"
    else:
        pix = page.get_pixmap(matrix=mat)
        suffix = ""

    img_path = os.path.join(out_dir, f"page_{page_num:03d}{suffix}.png")
    pix.save(img_path)
    doc.close()
    return img_path


def detect_table_lines(pdf_path, page_num):
    """
    Use pymupdf to detect horizontal and vertical lines that form table boundaries.
    Returns column boundaries (x-coordinates) and row boundaries (y-coordinates).
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    
    # Get all drawings (lines, rectangles) on the page
    drawings = page.get_drawings()
    
    vertical_lines = []
    horizontal_lines = []
    
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":  # line
                p1, p2 = item[1], item[2]
                # Vertical line: same x, different y
                if abs(p1.x - p2.x) < 2:
                    vertical_lines.append(p1.x)
                # Horizontal line: same y, different x
                elif abs(p1.y - p2.y) < 2:
                    horizontal_lines.append(p1.y)
            elif item[0] == "re":  # rectangle
                rect = item[1]
                vertical_lines.extend([rect.x0, rect.x1])
                horizontal_lines.extend([rect.y0, rect.y1])
    
    doc.close()
    
    # Cluster nearby lines (within 3 points)
    def cluster(values, threshold=3):
        if not values:
            return []
        sorted_vals = sorted(set(values))
        clusters = [[sorted_vals[0]]]
        for v in sorted_vals[1:]:
            if v - clusters[-1][-1] <= threshold:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [sum(c)/len(c) for c in clusters]
    
    col_boundaries = cluster(vertical_lines)
    row_boundaries = cluster(horizontal_lines)
    
    return col_boundaries, row_boundaries


def extract_text_with_positions(pdf_path, page_num):
    """
    Extract text with bounding box positions from a PDF page.
    Returns list of (text, x0, y0, x1, y1) tuples.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    
    blocks = page.get_text("dict")["blocks"]
    text_items = []
    
    for block in blocks:
        if block.get("type") != 0:  # text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"].strip()
                if text:
                    bbox = span["bbox"]
                    text_items.append({
                        "text": text,
                        "x0": bbox[0],
                        "y0": bbox[1],
                        "x1": bbox[2],
                        "y1": bbox[3],
                        "font_size": span.get("size", 0),
                        "is_superscript": span.get("size", 12) < 8
                    })
    
    doc.close()
    return text_items


def map_text_to_columns(text_items, col_boundaries):
    """
    Given text items with x-positions and column boundaries,
    assign each text item to its correct column.
    """
    if len(col_boundaries) < 2:
        return {}
    
    # Build column ranges from boundaries
    columns = []
    for i in range(len(col_boundaries) - 1):
        columns.append({
            "left": col_boundaries[i],
            "right": col_boundaries[i + 1],
            "center": (col_boundaries[i] + col_boundaries[i + 1]) / 2
        })
    
    # Assign each text item to a column based on its center x-position
    assignments = defaultdict(list)
    for item in text_items:
        center_x = (item["x0"] + item["x1"]) / 2
        best_col = None
        best_dist = float("inf")
        for ci, col in enumerate(columns):
            if col["left"] <= center_x <= col["right"]:
                best_col = ci
                break
            dist = min(abs(center_x - col["left"]), abs(center_x - col["right"]))
            if dist < best_dist:
                best_dist = dist
                best_col = ci
        if best_col is not None:
            assignments[best_col].append(item)
    
    return columns, assignments


def build_soa_grid(pdf_path, soa_pages, header_row_y_range=None):
    """
    Build a complete SoA procedure × visit grid using column boundary detection.
    
    Args:
        pdf_path: Path to protocol PDF
        soa_pages: List of 1-indexed page numbers containing the SoA table
        header_row_y_range: Optional (y_min, y_max) for the header row
    
    Returns:
        dict with columns, procedures, and cell mappings
    """
    all_col_boundaries = []
    all_row_boundaries = []
    all_text_items = []
    
    for page_num in soa_pages:
        cols, rows = detect_table_lines(pdf_path, page_num)
        text_items = extract_text_with_positions(pdf_path, page_num)
        
        # Tag items with their page
        for item in text_items:
            item["page"] = page_num
        
        all_col_boundaries.extend(cols)
        all_row_boundaries.extend(rows)
        all_text_items.extend(text_items)
    
    # Use the most common column boundary pattern (from page with most lines)
    result = {
        "source": "column-boundary-detection",
        "soa_pages": soa_pages,
        "column_count": len(set(round(x, 1) for x in all_col_boundaries)),
        "text_items_count": len(all_text_items),
        "column_boundaries": sorted(set(round(x, 1) for x in all_col_boundaries)),
        "row_boundaries_count": len(set(round(y, 1) for y in all_row_boundaries))
    }
    
    return result


def extract_soa_multipass(pdf_path, soa_pages, out_dir, dpi=450):
    """Extract SoA table pages using 3-pass vision: full, left-half, right-half.

    For each SoA page, generates 3 images at the specified DPI:
      - Full page (page_NNN.png)
      - Left 55% crop (page_NNN_left.png)
      - Right 55% crop (page_NNN_right.png)

    The 10% center overlap (55%+55%=110%) ensures columns near the middle
    appear in both halves, allowing the merge step to cross-validate.

    Args:
        pdf_path: Path to the protocol PDF
        soa_pages: List of 1-indexed page numbers containing SoA tables
        out_dir: Output directory for images
        dpi: Resolution for SoA pages (default 450, higher than normal 300)

    Returns:
        dict mapping page_num -> {"full": path, "left": path, "right": path}
    """
    img_dir = os.path.join(out_dir, "page_images")
    os.makedirs(img_dir, exist_ok=True)

    result = {}
    for page_num in soa_pages:
        paths = {
            "full":  extract_page_as_image(pdf_path, page_num, img_dir, dpi=dpi, crop=None),
            "left":  extract_page_as_image(pdf_path, page_num, img_dir, dpi=dpi, crop="left"),
            "right": extract_page_as_image(pdf_path, page_num, img_dir, dpi=dpi, crop="right"),
        }
        result[page_num] = paths
    return result


def merge_multipass_results(full_table, left_table, right_table):
    """Merge procedure×visit grids from full, left-half, and right-half vision passes.

    Merge strategy — majority voting with conflict resolution:
    1. For each procedure × visit cell, collect votes from all 3 passes.
    2. If 2 or 3 passes agree the cell has an X → mark as X.
    3. If 2 or 3 passes agree the cell is empty → mark as empty.
    4. If only 1 pass says X (tie-breaker):
       - If the cell is in the LEFT region (first 45% of columns), trust the left-half pass.
       - If the cell is in the RIGHT region (last 45% of columns), trust the right-half pass.
       - If the cell is in the CENTER overlap (middle 10%), trust the full-page pass.
    5. Log all conflicts in the returned audit trail.

    Args:
        full_table: dict {"columns": [...], "procedures": {name: {visit: mark}}}
        left_table: same structure, from left-half crop
        right_table: same structure, from right-half crop

    Returns:
        (merged_table, conflicts_log)
    """
    # Use full_table columns as the canonical column list
    columns = full_table.get("columns", [])
    n_cols = len(columns)
    if n_cols == 0:
        return full_table, []

    # Define regions: left=first 45%, right=last 45%, center=middle 10%
    left_boundary = int(n_cols * 0.45)
    right_boundary = int(n_cols * 0.55)

    # Collect all procedure names from all 3 passes
    all_procs = set()
    for tbl in [full_table, left_table, right_table]:
        all_procs.update(tbl.get("procedures", {}).keys())

    merged_procedures = {}
    conflicts = []

    for proc in sorted(all_procs):
        merged_row = {}
        full_row = full_table.get("procedures", {}).get(proc, {})
        left_row = left_table.get("procedures", {}).get(proc, {})
        right_row = right_table.get("procedures", {}).get(proc, {})

        for ci, col in enumerate(columns):
            # Normalize: any non-empty value = has mark, empty/missing = no mark
            full_val = full_row.get(col, "")
            left_val = left_row.get(col, "")
            right_val = right_row.get(col, "")

            votes_yes = sum(1 for v in [full_val, left_val, right_val] if v)
            votes_no = 3 - votes_yes

            if votes_yes >= 2:
                # Majority says X — use the most detailed value (with footnotes)
                best = max([full_val, left_val, right_val], key=lambda v: len(v) if v else 0)
                merged_row[col] = best
            elif votes_no >= 2:
                # Majority says empty — leave empty
                pass
            else:
                # Tie: 1 yes, 2 no — use region-based trust
                if ci < left_boundary:
                    trusted = left_val  # Trust left-half for left columns
                    trusted_source = "left_half"
                elif ci >= right_boundary:
                    trusted = right_val  # Trust right-half for right columns
                    trusted_source = "right_half"
                else:
                    trusted = full_val  # Trust full for center columns
                    trusted_source = "full_page"

                if trusted:
                    merged_row[col] = trusted

                conflicts.append({
                    "procedure": proc,
                    "column": col,
                    "column_index": ci,
                    "full_says": full_val or "(empty)",
                    "left_says": left_val or "(empty)",
                    "right_says": right_val or "(empty)",
                    "resolved_to": trusted or "(empty)",
                    "trusted_source": trusted_source,
                    "region": "left" if ci < left_boundary else ("right" if ci >= right_boundary else "center")
                })

        if merged_row:
            merged_procedures[proc] = merged_row

    merged_table = {
        "source": "multi-pass-vision-merge (full + left_half + right_half)",
        "dpi": 450,
        "columns": columns,
        "procedures": merged_procedures
    }

    return merged_table, conflicts


def detect_contiguous_gaps(ontology):
    """Heuristic 10: Contiguous Coverage Gap Detection.

    For each procedure with marks at 5+ visits, check for suspicious "holes"
    in a mostly-contiguous visit sequence. Clinical procedures rarely skip
    arbitrary intermediate visits while being present at both neighbors.

    Args:
        ontology: dict with "visits" and "procedures" arrays

    Returns:
        list of gap findings, each with procedure, missing visits, and evidence
    """
    # Build ordered visit list from ontology
    visits = ontology.get("visits", [])
    visit_ids = [v["visit_id"] for v in visits]
    visit_index = {vid: i for i, vid in enumerate(visit_ids)}

    findings = []

    for proc in ontology.get("procedures", []):
        required = proc.get("required_at", [])
        if len(required) < 5:
            continue  # Only check procedures with 5+ visits

        # Get sorted indices of visits where this procedure is required
        indices = sorted([visit_index[v] for v in required if v in visit_index])
        if len(indices) < 5:
            continue

        # Find gaps: visits between first and last required visit that are missing
        first_idx, last_idx = indices[0], indices[-1]
        present_set = set(indices)
        missing_indices = [i for i in range(first_idx, last_idx + 1) if i not in present_set]

        if not missing_indices:
            continue

        # Calculate gap ratio: what fraction of the range is missing?
        range_size = last_idx - first_idx + 1
        gap_ratio = len(missing_indices) / range_size

        # Flag if >15% of range is missing (suspicious for a mostly-contiguous procedure)
        if gap_ratio > 0.15 and len(missing_indices) >= 2:
            missing_visit_ids = [visit_ids[i] for i in missing_indices]
            present_visit_ids = [visit_ids[i] for i in indices]

            findings.append({
                "heuristic": "CONTIGUOUS_COVERAGE_GAP",
                "heuristic_number": 10,
                "procedure": proc.get("canonical_name", proc.get("procedure_id", "unknown")),
                "procedure_id": proc.get("procedure_id", ""),
                "present_at": present_visit_ids,
                "missing_at": missing_visit_ids,
                "range": f"{visit_ids[first_idx]} to {visit_ids[last_idx]}",
                "gap_ratio": round(gap_ratio, 2),
                "total_in_range": range_size,
                "total_present": len(indices),
                "total_missing": len(missing_indices),
                "severity": "CRITICAL" if gap_ratio > 0.3 else "MODERATE",
                "evidence": (
                    f"Procedure '{proc.get('canonical_name', '')}' is required at "
                    f"{len(indices)} visits spanning {visit_ids[first_idx]}-{visit_ids[last_idx]}, "
                    f"but {len(missing_indices)} intermediate visits are missing ({gap_ratio:.0%} gap). "
                    f"Clinical procedures rarely skip arbitrary visits in a contiguous sequence."
                ),
                "recommendation": (
                    f"Re-read SoA table columns for visits {missing_visit_ids} at higher resolution. "
                    f"If the procedure has X marks at those visits, add them to required_at."
                )
            })

    return findings


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pages", required=True, help="Comma-separated page numbers")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    pages = [int(p) for p in args.pages.split(",")]
    os.makedirs(args.out, exist_ok=True)
    
    result = build_soa_grid(args.pdf, pages)
    
    out_path = os.path.join(args.out, "column_detection.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"Column detection complete: {out_path}")
    print(f"  Columns: {result['column_count']}")
    print(f"  Text items: {result['text_items_count']}")
