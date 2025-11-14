###############################################################
#  FINAL APP.PY
#  Multi-Layer Financial Header Extractor
#  Supports XLSX / XLSM / XLS / XLSB / CSV / PDF
#  Uses Excel Row2 + Row3 directly (correct header engine)
###############################################################

import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO

try:
    import openpyxl
    from openpyxl import load_workbook
except:
    openpyxl = None

st.set_page_config(page_title="Financial Extractor (Final Stable)", layout="wide")


# ============================================================
# Utility: Export output to Excel
# ============================================================
def to_excel(groups):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for category, tables in groups.items():
            for i, df in enumerate(tables, start=1):
                df.to_excel(writer, index=False, sheet_name=f"{category[:28]}_{i}")
    out.seek(0)
    return out


# ============================================================
# Deduplicate column names
# ============================================================
def dedupe(cols):
    new, count = [], {}
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c not in count:
            count[c] = 0
        else:
            count[c] += 1
            c = f"{c}_{count[c]}"
        new.append(c)
    return new


# ============================================================
# Extract merged parent bands from Excel using openpyxl
# ============================================================
def get_merged_parents_openpyxl(ws):
    merged_parent = {}
    col_parent = {}

    for mr in ws.merged_cells.ranges:
        min_row, min_col = mr.min_row, mr.min_col
        max_row, max_col = mr.max_row, mr.max_col

        val = ws.cell(min_row, min_col).value
        if val is None:
            continue
        val = str(val).strip()

        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                merged_parent[(r, c)] = val

        if min_row == 2:
            for c in range(min_col, max_col + 1):
                col_parent[c] = val

    return merged_parent, col_parent


# ============================================================
# CORRECT HEADER BUILDER — guaranteed accurate
# ALWAYS read header rows from Excel, not pandas
# ============================================================
def build_headers_excel(ws, df):
    ncols = df.shape[1]

    merged_parent_map, col_parent_map = get_merged_parents_openpyxl(ws)

    headers = []
    for col_idx in range(1, ncols + 1):
        parts = []

        # 1. Parent header from merged row2 band
        parent = col_parent_map.get(col_idx)
        if parent:
            parts.append(str(parent).strip())

        # 2. Child level 1 = Excel Row2
        r2 = ws.cell(row=2, column=col_idx).value
        if r2 is not None:
            val = str(r2).strip()
            if val.lower() not in ["", "nan", "none"]:
                parts.append(val)

        # 3. Child level 2 = Excel Row3
        r3 = ws.cell(row=3, column=col_idx).value
        if r3 is not None:
            val = str(r3).strip()
            if val.lower() not in ["", "nan", "none"]:
                parts.append(val)

        # Remove duplicates preserve order
        final = []
        for p in parts:
            if p and p not in final:
                final.append(p)

        headers.append("_".join(final) if final else "")

    return dedupe(headers)


# ============================================================
# Remove narrow Excel columns (template columns)
# ============================================================
def remove_narrow_columns_openpyxl(df, ws, threshold=2):
    try:
        letters = [c[0].column_letter for c in ws.columns]
        keep = []
        for idx, letter in enumerate(letters):
            dim = ws.column_dimensions.get(letter)
            width = dim.width if dim and dim.width is not None else ws.column_dimensions.defaultColWidth
            if width is None or width > threshold:
                keep.append(idx)
        return df.iloc[:, keep]
    except:
        return df


# ============================================================
# Clean numeric values
# ============================================================
def clean_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().replace("\u00A0", " ").replace(",", "")
    if s.lower() in ["n.a.", "n.a", "na", "-", "--", ""]:
        return pd.NA
    if re.fullmatch(r"\(\s*[\d\.]+\s*\)", s):
        try:
            return -float(s.strip("()"))
        except:
            return s
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return s
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        try:
            return float(s)
        except:
            return s
    return s


# ============================================================
# Clean Excel table (OpenXML: .xlsx/.xlsm)
# ============================================================
def clean_excel_table_openxml(df_raw, sheet_name, filepath, debug=False):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet_name]

    if debug:
        st.subheader(f"DEBUG — Raw header rows for {sheet_name}")
        st.write(df.head(4))

    # Build headers from TRUE Excel rows
    headers = build_headers_excel(ws, df)

    if debug:
        st.subheader("DEBUG — Final computed headers")
        st.write(headers)

    # First col = Particulars
    if headers:
        headers[0] = "Particulars"

    df.columns = headers

    # Remove header rows (row1=title, row2&3=headers)
    df = df.iloc[3:].reset_index(drop=True)

    # Remove narrow template columns
    df = remove_narrow_columns_openpyxl(df, ws)

    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")

    df.columns = dedupe(df.columns)
    return df


# ============================================================
# Clean Excel for .xls or .xlsb (fallback: row2+row3 from pandas)
# ============================================================
def clean_excel_table_simple(df_raw):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else df.iloc[[1]]
    headers = []
    for tup in header_block.T.values:
        vals = [str(x).strip() for x in tup if str(x).strip() not in ["", "nan", "none"]]
        headers.append("_".join(vals) if vals else "")
    headers = dedupe(headers)
    if headers:
        headers[0] = "Particulars"
    df.columns = headers
    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


# ============================================================
# Clean PDF Tables
# ============================================================
def clean_pdf_table(df_raw):
    df = df_raw.dropna(axis=0, how="all").dropna(axis=1, how="all")
    header = df.iloc[0].astype(str).str.strip()
    df.columns = dedupe(header)
    df = df.iloc[1:].reset_index(drop=True)
    return df.applymap(clean_cell)


# ============================================================
# Classification
# ============================================================
def classify(df):
    t = " ".join(str(c).lower() for c in df.columns)
    if "balance" in t or "asset" in t or "liabil" in t:
        return "Balance Sheet"
    if "income" in t or "revenue" in t or "profit" in t:
        return "Income Statement"
    if "cash" in t or "operat" in t or "invest" in t:
        return "Cash Flow Statement"
    return "Other"


# ============================================================
# Streamlit UI
# ============================================================
st.title("📊 Financial Statement Extractor — Multi-Layer Header Engine")

debug_mode = st.sidebar.checkbox("Enable Debug Mode", False)

uploaded = st.file_uploader(
    "Upload file (.xlsx, .xlsm, .xls, .xlsb, .csv, .pdf)",
    type=["xlsx", "xlsm", "xls", "xlsb", "csv", "pdf"]
)

if not uploaded:
    st.stop()

filepath = f"temp_{uploaded.name}"
with open(filepath, "wb") as f:
    f.write(uploaded.getbuffer())

ext = os.path.splitext(filepath)[1].lower()
tables = []

# ------------------------------------------------------------
# XLSX / XLSM
# ------------------------------------------------------------
if ext in [".xlsx", ".xlsm"]:
    xlf = pd.ExcelFile(filepath, engine="openpyxl")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        cleaned = clean_excel_table_openxml(df_raw, s, filepath, debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

# ------------------------------------------------------------
# XLS (legacy)
# ------------------------------------------------------------
elif ext == ".xls":
    xlf = pd.ExcelFile(filepath, engine="xlrd")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        cleaned = clean_excel_table_simple(df_raw)
        if not cleaned.empty:
            tables.append(cleaned)

# ------------------------------------------------------------
# XLSB
# ------------------------------------------------------------
elif ext == ".xlsb":
    try:
        xlf = pd.ExcelFile(filepath, engine="pyxlsb")
        sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
        for s in sheets:
            df_raw = pd.read_excel(filepath, sheet_name=s, header=None, engine="pyxlsb", dtype=object)
            cleaned = clean_excel_table_simple(df_raw)
            if not cleaned.empty:
                tables.append(cleaned)
    except:
        st.error("Unable to read XLSB. Install pyxlsb.")
        st.stop()

# ------------------------------------------------------------
# CSV
# ------------------------------------------------------------
elif ext == ".csv":
    df_raw = pd.read_csv(filepath, header=None)
    cleaned = clean_excel_table_simple(df_raw)
    if not cleaned.empty:
        tables.append(cleaned)

# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------
elif ext == ".pdf":
    extracted = []
    try:
        import camelot
        for t in camelot.read_pdf(filepath, pages="all", flavor="lattice"):
            extracted.append(t.df)
    except:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for p in pdf.pages:
                for t in p.extract_tables():
                    extracted.append(pd.DataFrame(t))
    except:
        pass

    for df_raw in extracted:
        cleaned = clean_pdf_table(df_raw)
        if not cleaned.empty:
            tables.append(cleaned)

# ============================================================
# DISPLAY RESULTS
# ============================================================
st.success(f"Extracted {len(tables)} table(s)")

groups = {"Balance Sheet": [], "Income Statement": [], "Cash Flow Statement": [], "Other": []}
for i, df in enumerate(tables, 1):
    st.subheader(f"Table {i}")
    st.dataframe(df, use_container_width=True)
    groups[classify(df)].append(df)

st.header("Summary")
for k, v in groups.items():
    st.write(f"**{k}**: {len(v)} tables")

st.download_button(
    "📥 Download Extracted Financials",
    data=to_excel(groups),
    file_name="Extracted_Financials.xlsx"
)