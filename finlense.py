import streamlit as st
import pandas as pd
import camelot
import pdfplumber
import tabula
import openpyxl
import os
import re
from io import BytesIO

st.set_page_config(page_title="Financial Statement Extractor", layout="wide")

# =====================================================================
# EXPORT TO EXCEL
# =====================================================================
def to_excel(statement_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for statement, tables in statement_dict.items():
            for i, df in enumerate(tables, start=1):
                df.to_excel(writer, index=False, sheet_name=f"{statement[:28]}_{i}")
    output.seek(0)
    return output


# =====================================================================
# DEDUPLICATE COLUMNS
# =====================================================================
def deduplicate_columns(cols):
    new_cols, count = [], {}
    for col in cols:
        col = str(col).strip()
        if col not in count:
            count[col] = 0
            new_cols.append(col)
        else:
            count[col] += 1
            new_cols.append(f"{col}_{count[col]}")
    return new_cols


# =====================================================================
# DETECT MULTI-ROW HEADERS
# =====================================================================
def detect_multirow_header(df):
    header_rows = []
    for idx, row in df.iterrows():
        non_empty_ratio = row.notna().mean()
        numeric_ratio = row.apply(
            lambda x: str(x).replace(",", "").replace(".", "", 1)
            .lstrip("-").isdigit()
        ).mean()

        # header rows are text-heavy
        if non_empty_ratio >= 0.3 and numeric_ratio < 0.5:
            header_rows.append(idx)
        else:
            break
    return header_rows if header_rows else [0]


# =====================================================================
# READ EXCEL MERGED CELLS → PARENT HEADERS
# =====================================================================
def get_excel_merged_header_map(sheet):
    parent_map = {}
    for merged in sheet.merged_cells.ranges:
        min_col = merged.min_col
        max_col = merged.max_col
        row = merged.min_row
        value = sheet.cell(row=row, column=min_col).value
        if not value:
            continue
        value = str(value).strip()

        for col in range(min_col, max_col + 1):
            parent_map[col] = value

    return parent_map


# =====================================================================
# BUILD MULTI-LAYER HEADER
# =====================================================================
def build_multirow_header(df, sheet_name, file_path, header_rows):
    """
    Deep merge all header layers:
    Example stacked rows:
       Historical Interims
       1H
       2024
    Output → Historical Interims_1H_2024
    """

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb[sheet_name]

    merged_map = get_excel_merged_header_map(ws)

    header_block = df.iloc[header_rows].astype(str).fillna("").applymap(lambda x: x.strip())

    final_headers = []

    # iterate column-wise
    for col_idx, col_vals in enumerate(header_block.T.values, start=1):
        parts = []

        # 1) Parent (from merged Excel cells)
        parent = merged_map.get(col_idx, "")
        if parent and parent.lower() != "nan":
            parts.append(parent)

        # 2) Child & grandchild values from header rows
        for v in col_vals:
            if v not in ["", "nan", "none", None]:
                parts.append(v)

        final_headers.append("_".join(parts) if parts else "")

    return deduplicate_columns(final_headers)


# =====================================================================
# REMOVE BLANK-WIDTH & HIDDEN COLUMNS (Based on Excel)
# =====================================================================
def remove_blank_width_columns(df, sheet_name, file_path):
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb[sheet_name]
        col_letters = [col[0].column_letter for col in ws.columns]

        keep = []
        for idx, col_letter in enumerate(col_letters):
            dim = ws.column_dimensions.get(col_letter)
            width = dim.width if dim and dim.width is not None else ws.column_dimensions.defaultColWidth

            # blank-width column threshold
            if width and width > 2:
                keep.append(idx)

        return df.iloc[:, keep]
    except:
        return df


# =====================================================================
# CLEAN NUMERIC CEll
# =====================================================================
def clean_numeric_value(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().replace("\u00A0", "").replace(",", "")

    # (123) → -123
    if re.fullmatch(r"\(\s*[\d\.]+\s*\)", s):
        return float("-" + s.strip("()"))

    # percentages
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return pd.NA

    if s.lower() in ["n.a.", "n.a", "na", "-", ""]:
        return pd.NA

    try:
        return float(s)
    except:
        return x


# =====================================================================
# CLEAN TABLE
# =====================================================================
def clean_table(df, sheet_name=None, file_path=None):
    df = df.replace(["", " ", "\t", "\n", "\r", "\x00", "—", "–"], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    if df.empty:
        return df

    header_rows = detect_multirow_header(df)

    merged_header = build_multirow_header(df, sheet_name, file_path, header_rows)
    df.columns = merged_header

    df = df.loc[:, [c for c in df.columns if c.strip() != ""]]

    df = df.iloc[max(header_rows) + 1:].reset_index(drop=True)

    df = df.applymap(lambda x: pd.NA if pd.isna(x) or str(x).strip() == "" else x)

    df = df.dropna(axis=1, how="all")

    df = remove_blank_width_columns(df, sheet_name, file_path)

    df = df.applymap(clean_numeric_value)

    df = df.dropna(axis=1, how="all")
    return df


# =====================================================================
# READ EXCEL
# =====================================================================
def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []

    for sheet in (selected_sheets or xl.sheet_names):
        df_raw = xl.parse(sheet, header=None, dtype=object)
        df_raw = df_raw.replace(["", " ", "\t", "\n"], pd.NA)
        df_raw = df_raw.dropna(axis=0, how="all").dropna(axis=1, how="all")

        if not df_raw.empty:
            df = clean_table(df_raw, sheet_name=sheet, file_path=file_path)
            if not df.empty:
                tables.append(df)

    return tables


# =====================================================================
# READ PDF
# =====================================================================
def read_pdf_file(file_path):
    all_tables = []
    try:
        for t in camelot.read_pdf(file_path, pages="all", flavor="lattice"):
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for tb in page.extract_tables():
                    df = clean_table(pd.DataFrame(tb))
                    if not df.empty:
                        all_tables.append(df)
    except:
        pass

    try:
        for t in tabula.read_pdf(file_path, pages="all", multiple_tables=True):
            df = clean_table(t)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    return all_tables


# =====================================================================
# CLASSIFY TABLE
# =====================================================================
def classify_statement(df):
    text = " ".join(str(x).lower() for x in df.columns)
    text += " " + " ".join(df.astype(str).fillna("").apply(lambda r: " ".join(r), axis=1))

    if any(k in text for k in ["balance sheet", "assets", "liabilities", "equity"]):
        return "Balance Sheet"
    if any(k in text for k in ["income", "profit", "loss", "revenue"]):
        return "Income Statement"
    if any(k in text for k in ["cash flow", "operating", "investing", "financing"]):
        return "Cash Flow Statement"
    return "Other"


# =====================================================================
# STREAMLIT UI
# =====================================================================
st.title("📊 Advanced Financial Extractor (Multi-Layer Headers + Merged Cells)")
st.write("This version fully supports **multi-row hierarchical headers**, **merged Excel headers**, and cleans all values.")

uploaded_file = st.file_uploader("Upload Excel or PDF", type=["xlsx", "xls", "pdf"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    selected_sheets = None
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        st.subheader("Select Sheets")
        selected_sheets = st.multiselect("Sheets:", xl.sheet_names, xl.sheet_names)

        if not selected_sheets:
            st.warning("Select at least 1 sheet.")
            st.stop()

    st.info("Extracting tables...")

    tables = (
        read_excel_file(file_path, selected_sheets)
        if ext in [".xlsx", ".xls"]
        else read_pdf_file(file_path)
    )

    st.success(f"Extracted {len(tables)} table(s)")

    classified = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    for i, df in enumerate(tables, start=1):
        st.subheader(f"Table {i}")
        st.dataframe(df, use_container_width=True)

        classified[classify_statement(df)].append(df)

    st.markdown("## Summary")
    for name, group in classified.items():
        st.write(f"**{name}: {len(group)} table(s)**")

    excel_file = to_excel(classified)

    st.download_button(
        "📥 Download Extracted Tables",
        data=excel_file,
        file_name="Extracted_Financial_Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
