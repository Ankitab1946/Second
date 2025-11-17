import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO

st.set_page_config(page_title="Financials Header & Row Flattener", layout="wide")

# ==========================================================
# FUNCTION 1: READ + FLATTEN HEADER (HORIZONTAL)
# ==========================================================
def extract_flattened_header(ws):
    max_cols = ws.max_column
    
    # Read 3 header rows
    header_matrix = []
    for r in range(1, 4):
        row_vals = []
        for c in range(1, max_cols + 1):
            cell = ws.cell(row=r, column=c)
            row_vals.append("" if cell.value is None else str(cell.value).strip())
        header_matrix.append(row_vals)

    # Fill merged cells into header_matrix
    for merge_range in ws.merged_cells.ranges:
        min_col, min_row = merge_range.min_col, merge_range.min_row
        val = ws.cell(min_row, min_col).value
        for r in range(merge_range.min_row, merge_range.max_row + 1):
            for c in range(merge_range.min_col, merge_range.max_col + 1):
                header_matrix[r-1][c-1] = "" if val is None else str(val)

    # FINAL flattening
    final_headers = []
    for col in range(max_cols):
        h1 = header_matrix[0][col].strip()
        h2 = header_matrix[1][col].strip()
        h3 = header_matrix[2][col].strip()

        # Special Rule: A1 + A2 + A3 combined
        if col == 0:
            final_headers.append("_".join([h1, h2, h3]).strip("_"))
            continue

        parts = []
        if h1 and h1.lower() != "comments":
            parts.append(h1)
        if h2:
            parts.append(h2)
        if h3:
            parts.append(h3)

        final_headers.append("_".join(parts).strip("_"))

    return final_headers


# ==========================================================
# FUNCTION 2: BUILD VERTICAL HIERARCHY (BLUE ROW LOGIC)
# ==========================================================
def build_vertical_hierarchy(df, ws):
    parent_map = {}
    last_parent = ""

    for idx, row in df.iterrows():
        label = str(row.iloc[0]).strip()

        if label.lower() in ["", "forecast based on research"]:
            parent_map[idx] = {"parent": last_parent}
            continue

        excel_row = idx + 4  # because data starts after row 3
        cell = ws.cell(row=excel_row, column=1)

        fill = cell.fill
        fg = fill.fgColor.rgb if fill and fill.fgColor and fill.fgColor.rgb else None

        # Detect Blue Parent Row
        is_blue = fg and fg.startswith("FF") and fg.endswith(("DCE6F1", "DBEEF3", "C6D9F1"))

        if is_blue:
            last_parent = label
            parent_map[idx] = {"parent": label}
        else:
            parent_map[idx] = {"parent": last_parent}

    # BUILD FINAL LABEL
    final_labels = []

    for idx, row in df.iterrows():
        parent = parent_map[idx]["parent"]
        main = str(row.iloc[0]).strip()

        if main.lower() in ["", "forecast based on research"]:
            final_labels.append("")
            continue

        # Grandchild logic → %Change
        if "%Change" in main or "% change" in main.lower():
            child = str(df.iloc[idx - 1, 0]).strip()
            final_labels.append(f"{parent}_{child}_%Change")
        else:
            final_labels.append(f"{parent}_{main}")

    return final_labels


# ==========================================================
# MAIN STREAMLIT UI
# ==========================================================
st.title("📊 Financials Header & Row Flattener")

uploaded = st.file_uploader("Upload Financials.xlsx", type=["xlsx"])

if uploaded:
    wb = openpyxl.load_workbook(uploaded, data_only=True)
    sheets = wb.sheetnames

    sheet_name = st.selectbox("Select a sheet", sheets)

    if sheet_name:
        ws = wb[sheet_name]

        st.success("Sheet loaded successfully!")

        # HEADER PROCESSING
        st.subheader("Step 1 → Flattening Header (Horizontal)")
        headers = extract_flattened_header(ws)
        st.write(headers)

        # LOAD FULL DATA INTO PANDAS
        df = pd.DataFrame(ws.values)
        df.columns = headers
        df = df.iloc[3:].reset_index(drop=True)

        # ROW HIERARCHY PROCESSING
        st.subheader("Step 2 → Processing Rows (Vertical Hierarchy)")
        vertical_labels = build_vertical_hierarchy(df, ws)

        df.insert(0, "Final_Row_Label", vertical_labels)

        st.subheader("Flattened Output")
        st.dataframe(df, use_container_width=True)

        # DOWNLOAD BUTTON
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Flattened")

        st.download_button(
            label="⬇️ Download Flattened Excel",
            data=output.getvalue(),
            file_name="Flattened_Financials.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
