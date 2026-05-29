"""Reconstruct tabular rows from OCR word boxes via y-coordinate clustering."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from finunderwrite.parser.ocr.tesseract_wrapper import OcrLine

Y_CLUSTER_TOLERANCE = 12.0


def reconstruct_table_from_ocr(lines: list[OcrLine]) -> pd.DataFrame:
    """Cluster OCR tokens into rows and infer columns by x-position."""
    if not lines:
        return pd.DataFrame()

    by_page: dict[int, list[OcrLine]] = defaultdict(list)
    for line in lines:
        by_page[line.page].append(line)

    all_rows: list[list[str]] = []
    header: list[str] | None = None

    for page in sorted(by_page):
        page_lines = by_page[page]
        rows = _cluster_into_rows(page_lines)
        if not rows:
            continue
        if header is None:
            header = rows[0]
            all_rows.extend(rows[1:])
        else:
            if _looks_like_header(rows[0], header):
                all_rows.extend(rows[1:])
            else:
                all_rows.extend(rows)

    if header is None:
        return pd.DataFrame()

    width = len(header)
    normalized: list[list[str]] = []
    for row in all_rows:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            row = row[: width - 1] + [" ".join(row[width - 1 :])]
        normalized.append(row)

    return pd.DataFrame(normalized, columns=header)


def _cluster_into_rows(lines: list[OcrLine]) -> list[list[str]]:
    sorted_lines = sorted(lines, key=lambda ln: (ln.y, ln.x))
    clusters: list[list[OcrLine]] = []
    current: list[OcrLine] = []
    current_y: float | None = None

    for ln in sorted_lines:
        if current_y is None or abs(ln.y - current_y) <= Y_CLUSTER_TOLERANCE:
            current.append(ln)
            current_y = ln.y if current_y is None else sum(t.y for t in current) / len(current)
        else:
            clusters.append(current)
            current = [ln]
            current_y = ln.y
    if current:
        clusters.append(current)

    rows: list[list[str]] = []
    for cluster in clusters:
        cluster.sort(key=lambda ln: ln.x)
        rows.append([ln.text for ln in cluster])
    return rows


def _looks_like_header(row: list[str], header: list[str]) -> bool:
    row_l = [r.lower() for r in row]
    header_l = [h.lower() for h in header]
    matches = sum(1 for a, b in zip(row_l, header_l, strict=False) if a == b)
    return matches >= max(2, len(header) // 2)
