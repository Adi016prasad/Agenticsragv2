from bs4 import BeautifulSoup
from typing import List, Dict


def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 1


def parse_complex_html_table(html_content: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table')
    if not table:
        return []

    rows = table.find_all('tr')
    grid = []
    occupied = set()  # Tracks (row, col) indices taken by rowspans/colspans
    header_row_indices = []

    # ---------------------------------------------------------
    # STEP 1: Build the true 2D Grid resolving all Spans
    # ---------------------------------------------------------
    for r_idx, row in enumerate(rows):
        while len(grid) <= r_idx:
            grid.append([])

        cells = row.find_all(['th', 'td'])

        is_thead = row.parent.name == 'thead'
        if is_thead or (cells and all(cell.name == 'th' for cell in cells)):
            header_row_indices.append(r_idx)

        c_idx = 0
        for cell in cells:
            while (r_idx, c_idx) in occupied:
                c_idx += 1

            text = cell.get_text(strip=True)
            rowspan = safe_int(cell.get('rowspan', 1))
            colspan = safe_int(cell.get('colspan', 1))

            for i in range(rowspan):
                for j in range(colspan):
                    occupied.add((r_idx + i, c_idx + j))
                    while len(grid) <= r_idx + i:
                        grid.append([])
                    while len(grid[r_idx + i]) <= c_idx + j:
                        grid[r_idx + i].append("")
                    grid[r_idx + i][c_idx + j] = text

            c_idx += colspan

    if not header_row_indices and grid:
        header_row_indices = [0]

    # ---------------------------------------------------------
    # STEP 2: Clean malformed empty columns (Trailing HTML tags)
    # ---------------------------------------------------------
    num_cols = max(len(r) for r in grid) if grid else 0
    valid_cols = []
    for c in range(num_cols):
        if any(c < len(row) and row[c] != "" for row in grid):
            valid_cols.append(c)

    cleaned_grid = [[row[c] if c < len(row) else "" for c in valid_cols] for row in grid]
    if not cleaned_grid:
        return []

    # ---------------------------------------------------------
    # STEP 3: Flatten Multi-Row Headers & Map Data
    # ---------------------------------------------------------
    header_limit = max(header_row_indices) + 1 if header_row_indices else 1
    flat_headers = []

    for c in range(len(valid_cols)):
        col_header_parts = []
        for r in range(header_limit):
            part = cleaned_grid[r][c]
            if part and (not col_header_parts or col_header_parts[-1] != part):
                col_header_parts.append(part)
        flat_headers.append(" - ".join(col_header_parts) if col_header_parts else f"Column_{c}")

    transformed_data = []
    for r in range(header_limit, len(cleaned_grid)):
        row_dict = {}
        for c, header in enumerate(flat_headers):
            row_dict[header] = cleaned_grid[r][c]
        transformed_data.append(row_dict)

    return transformed_data