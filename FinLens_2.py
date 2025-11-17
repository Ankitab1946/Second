import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="Financials Flattener — FINAL", layout="wide")

# ============================================================
# Helpers
# ============================================================

def safe_cell_value(ws, row, col):
    v = ws.cell(row=row, column=col).value
    return "" if v is None else str(v).strip()


def clean_header_text(h):
    if h is None:
        return ""
    h = str(h).replace("#REF!", "")
    while "__" in h:
        h = h.replace("__", "_")
    return h.strip("_ ").strip()


def make_unique(headers):
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
    """Detect light-blue parent rows."""
    try:
        fg = cell.fill.fgColor
        if fg is None:
            return False
        rgb = fg.rgb
        if rgb:
            rgb = rgb.upper().replace("0X", "").replace("FF", "")
            blue_shades = ["DCE6F1", "DBEEF3", "C6D9F1", "EAF3FF", "DBECFF"]
            return any(rgb.endswith(s) for s in blue_shades)
    except:
        return False
    return False


def is_row_hidden(ws, row):
    return ws.row_dimensions[row].hidden


def is_col_hidden(ws, col):
    col_letter = get_column_letter(col)
    return ws.column_dimensions[col_letter].hidden


# ============================================================
# Header Extractor (3-Level Horizontal)
# ============================================================

def extract_flattened_header(ws, header_rows=3):
    max_cols = ws.max_column
    header_matrix = [["" for _ in range(max_cols)] for _ in range(header_rows)]

    # Read row 1-3
    for r in range(1, header_rows + 1):
        for c in range(1, max_cols + 1):
            header_matrix[r - 1][c - 1] = safe_cell_value(ws, r, c)

    # Propagate merged cell values (ONLY within row1–row3)
    for merge in ws.merged_cells.ranges:
        if merge.min_row > header_rows:
            continue
        val = safe_cell_value(ws, merge.min_row, merge.min_col)
        for r in range(max(1, merge.min_row), min(header_rows, merge.max_row) + 1):
            for c in range(merge.min_col, merge.max_col + 1):
                if 1 <= c <= max_cols:
                    header_matrix[r - 1][c - 1] = val

    # Build final headers
    final_headers = []
    for col in range(max_cols):
        h1 = header_matrix[0][col].strip()
        h2 = header_matrix[1][col].strip()
        h3 = header_matrix[2][col].strip()

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

    # Clean & unique
    cleaned = [clean_header_text(h) for h in final_headers]
    cleaned = [(h if h else f"Column_{i+1}") for i, h in enumerate(cleaned)]
    cleaned = make_unique(cleaned)

    return cleaned


# ============================================================
# Build DataFrame from Visible Rows/Columns Only
# ============================================================

def build_dataframe_from_ws(ws, headers, start_row=4):
    max_cols = ws.max_column
    max_row = ws.max_row

    visible_cols = [c for c in range(1, max_cols + 1) if not is_col_hidden(ws, c)]

    data = []
    for r in range(start_row, max_row + 1):
        if is_row_hidden(ws, r):
            continue
        row_vals = [ws.cell(row=r, column=c).value for c in visible_cols]
        data.append(row_vals)

    visible_headers = [headers[c - 1] for c in visible_cols]
    df = pd.DataFrame(data, columns=visible_headers)

    return df


# ============================================================
# Vertical Hierarchy Builder (Parent → Child → %Change)
# ============================================================

def build_vertical_labels(df, ws, data_start_row=4):
    labels = []
    parent = ""
    last_child = ""

    for idx in range(len(df)):
        excel_row = data_start_row + idx

        if is_row_hidden(ws, excel_row):
            labels.append("")
            continue

        text = safe_cell_value(ws, excel_row, 1).strip()
        if text.lower() in ["", "forecast based on research"]:
            labels.append("")
            continue

        cell = ws.cell(row=excel_row, column=1)
        is_blue = is_fill_blue(cell)

        # 1) Parent
        if is_blue:
            parent = text
            last_child = ""
            labels.append(parent)
            continue

        # 2) Grandchild
        low = text.lower()
        if "%change" in low or low.endswith("%"):
            if parent and last_child:
                labels.append(f"{parent}_{last_child}_%Change")
            elif last_child:
                labels.append(f"{last_child}_%Change")
            else:
                labels.append("%Change")
            continue

        # 3) Child
        last_child = text
        if parent:
            labels.append(f"{parent}_{text}")
        else:
            labels.append(text)

    return labels


# ============================================================
# STREAMLIT UI
# ============================================================

st.title("📊 FINAL Financials Flattener (Horizontal + Vertical + Hidden Skip)")

uploaded = st.file_uploader("Upload Financials Excel (.xlsx)", type=["xlsx"])

if uploaded:
    wb = openpyxl.load_workbook(uploaded, data_only=True)
    sheet_name = st.selectbox("Select Sheet", wb.sheetnames)

    if sheet_name:
        ws = wb[sheet_name]
        st.success(f"Sheet Loaded: {sheet_name}")

        # -------------------- HEADER --------------------
        st.subheader("🔹 Extracting 3-Level Horizontal Headers…")
        headers = extract_flattened_header(ws)
        st.write(headers)

        # -------------------- DATA -----------------------
        st.subheader("🔹 Reading Visible Rows & Columns…")
        df = build_dataframe_from_ws(ws, headers, start_row=4)

        # -------------------- VERTICAL --------------------
        st.subheader("🔹 Building Vertical Hierarchy (Parent → Child → %Change)…")
        vertical_labels = build_vertical_labels(df, ws, data_start_row=4)
        df.insert(0, "Final_Row_Label", vertical_labels)

        # -------------------- PREVIEW ---------------------
        st.subheader("📌 Preview (first 30 rows)")
        st.dataframe(df.head(30), use_container_width=True)

        # -------------------- DOWNLOAD ---------------------
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Flattened")

        st.download_button(
            "⬇️ Download Flattened Excel",
            output.getvalue(),
            "Flattened_Financials_Final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
