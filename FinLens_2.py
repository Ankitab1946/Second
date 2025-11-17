import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO

st.set_page_config(page_title="Financials Header & Row Flattener — FINAL", layout="wide")

# ===========================================================
# HELPERS
# ===========================================================

def safe_cell_value(ws, row, col):
    v = ws.cell(row=row, column=col).value
    return "" if v is None else str(v).strip()


def clean_header_text(h):
    """
    Removes #REF!, whitespace, double underscores, leading/trailing underscores.
    """
    if h is None:
        return ""
    h = str(h)
    h = h.replace("#REF!", "")
    while "__" in h:
        h = h.replace("__", "_")
    return h.strip("_ ").strip()


def make_unique(headers):
    """Ensure no duplicate column names remain."""
    seen = {}
    out = []
    for h in headers:
        h = h or "Column"
        if h not in seen:
            seen[h] = 0
            out.append(h)
        else:
            seen[h] += 1
            out.append(f"{h}_{seen[h]}")
    return out


def is_fill_blue(cell):
    """
    Detects if a cell is light blue based on its fill color.
    Handles multiple hex formats.
    """
    try:
        fg = cell.fill.fgColor
        if fg is None:
            return False
        rgb = fg.rgb
        if rgb:
            rgb = rgb.upper().replace("0X", "").replace("FF", "")
            blue_suffixes = ["DCE6F1", "DBEEF3", "C6D9F1", "EAF3FF", "DBECFF"]
            return any(rgb.endswith(s) for s in blue_suffixes)
        return False
    except:
        return False


# ===========================================================
# STEP 1 — READ & FLATTEN HEADER
# ===========================================================

def extract_flattened_header(ws, header_rows=3):
    max_cols = ws.max_column

    # Initialize empty header matrix
    header_matrix = [["" for _ in range(max_cols)] for _ in range(header_rows)]

    # Fill matrix with row 1–3 values
    for r in range(1, header_rows + 1):
        for c in range(1, max_cols + 1):
            header_matrix[r - 1][c - 1] = safe_cell_value(ws, r, c)

    # Propagate merged cells only within row 1–3
    for merge in ws.merged_cells.ranges:
        if merge.min_row > header_rows:
            continue
        val = safe_cell_value(ws, merge.min_row, merge.min_col)
        for r in range(max(1, merge.min_row), min(header_rows, merge.max_row) + 1):
            for c in range(merge.min_col, merge.max_col + 1):
                if 1 <= c <= max_cols:
                    header_matrix[r - 1][c - 1] = val

    # Combine header levels
    final_headers = []
    for col in range(max_cols):
        h1 = header_matrix[0][col].strip()
        h2 = header_matrix[1][col].strip()
        h3 = header_matrix[2][col].strip()

        # Special A1+A2+A3 rule
        if col == 0:
            h = "_".join([x for x in (h1, h2, h3) if x])
            final_headers.append(h if h else f"Column_{col+1}")
            continue

        if h1.lower() == "comments":
            final_headers.append("Comments")
            continue

        parts = [p for p in (h1, h2, h3) if p]
        h = "_".join(parts).strip("_")
        final_headers.append(h if h else f"Column_{col+1}")

    # Clean
    cleaned = [clean_header_text(h) for h in final_headers]

    # Replace blanks
    cleaned = [(h if h else f"Column_{i+1}") for i, h in enumerate(cleaned)]

    # Enforce uniqueness
    cleaned = make_unique(cleaned)

    return cleaned


# ===========================================================
# STEP 2 — BUILD DATAFRAME FROM SHEET
# ===========================================================

def build_dataframe_from_ws(ws, headers, start_row=4):
    max_cols = ws.max_column
    max_row = ws.max_row
    data = []

    for r in range(start_row, max_row + 1):
        row_vals = []
        for c in range(1, max_cols + 1):
            v = ws.cell(row=r, column=c).value
            row_vals.append(v)
        data.append(row_vals)

    df = pd.DataFrame(data, columns=headers)
    return df


# ===========================================================
# STEP 3 — BUILD VERTICAL HIERARCHY (PARENT / CHILD)
# ===========================================================

def build_vertical_labels(df, ws, data_start_row=4):
    parent_map = {}
    last_parent = ""

    for idx in range(len(df)):
        excel_row = data_start_row + idx
        text = safe_cell_value(ws, excel_row, 1)

        if text.lower() in ["", "forecast based on research"]:
            parent_map[idx] = last_parent
            continue

        cell = ws.cell(row=excel_row, column=1)

        if is_fill_blue(cell):
            last_parent = text
            parent_map[idx] = text
        else:
            parent_map[idx] = last_parent

    final_labels = []
    for idx in range(len(df)):
        text = safe_cell_value(ws, data_start_row + idx, 1)
        parent = parent_map.get(idx, "")

        if text.lower() in ["", "forecast based on research"]:
            final_labels.append("")
            continue

        low = text.lower()
        if "%change" in low or "% change" in low or low.endswith("%"):
            prev_child = ""
            for j in range(idx - 1, -1, -1):
                cand = safe_cell_value(ws, data_start_row + j, 1)
                if cand.strip():
                    prev_child = cand
                    break
            if parent and prev_child:
                final_labels.append(f"{parent}_{prev_child}_%Change")
            elif prev_child:
                final_labels.append(f"{prev_child}_%Change")
            else:
                final_labels.append("%Change")
        else:
            final_labels.append(f"{parent}_{text}" if parent else text)

    return final_labels


# ===========================================================
# STREAMLIT UI
# ===========================================================

st.title("📊 FINAL: Financials Header & Row Flattener")

uploaded = st.file_uploader("Upload Financials Excel", type=["xlsx"])

if uploaded:
    wb = openpyxl.load_workbook(uploaded, data_only=True)
    sheets = wb.sheetnames

    sheet_name = st.selectbox("Select Sheet", sheets)

    if sheet_name:
        ws = wb[sheet_name]
        st.success(f"Loaded: {sheet_name}")

        st.subheader("Extracting & Cleaning Headers...")
        headers = extract_flattened_header(ws)
        st.write(headers)

        df = build_dataframe_from_ws(ws, headers, start_row=4)

        st.subheader("Building Vertical Hierarchy...")
        vertical_labels = build_vertical_labels(df, ws, data_start_row=4)
        df.insert(0, "Final_Row_Label", vertical_labels)

        st.subheader("Flattened Output Preview")
        st.dataframe(df.head(30), use_container_width=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Flattened")

        st.download_button(
            "⬇️ Download Flattened Excel",
            output.getvalue(),
            "Flattened_Financials_Final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
