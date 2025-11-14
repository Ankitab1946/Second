import streamlit as st
import pandas as pd
import camelot
import pdfplumber
import tabula
import openpyxl
from openpyxl import load_workbook
import re
import os
from io import BytesIO

st.set_page_config(page_title="Financial Extractor (Final)", layout="wide")

# ============================================================
# Export to Excel
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
    new = []
    count = {}
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c not in count:
            count[c] = 0
            new.append(c)
        else:
            count[c] += 1
            new.append(f"{c}_{count[c]}")
    return new


# ============================================================
# Detect merged parents from Excel (row 2)
# ============================================================
def get_merged_parents(ws):
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

        if min_row == 2:  # Parent band appears in Row2
            for c in range(min_col, max_col + 1):
                col_parent[c] = val

    return merged_parent, col_parent


# ============================================================
# Build FINAL hierarchical headers
# Row1 ignored (title)
# Row2 + Row3 build headers
# ============================================================
def build_final_headers(ws, df):
    ncols = df.shape[1]
    merged_parent_map, col_parent_map = get_merged_parents(ws)

    headers = []

    for col_idx in range(1, ncols + 1):
        parts = []

        # 1. Parent from merged row2 band
        parent = col_parent_map.get(col_idx, "")
        if parent and parent.lower() not in ["nan", "none", ""]:
            parts.append(parent)

        # 2. Row 2 (header level 1)
        r2 = df.iloc[1, col_idx - 1]
        if pd.isna(r2):
            r2v = merged_parent_map.get((2, col_idx), "")
        else:
            r2v = str(r2).strip()

        if r2v and r2v.lower() not in ["nan", "none", ""]:
            if r2v not in parts:
                parts.append(r2v)

        # 3. Row 3 (header level 2)
        r3 = df.iloc[2, col_idx - 1]
        if pd.isna(r3):
            r3v = merged_parent_map.get((3, col_idx), "")
        else:
            r3v = str(r3).strip()

        if r3v and r3v.lower() not in ["nan", "none", ""]:
            if r3v not in parts:
                parts.append(r3v)

        # Remove duplicates and join
        final_parts = []
        for p in parts:
            if p and p not in final_parts:
                final_parts.append(p)

        headers.append("_".join(final_parts) if final_parts else "")

    return dedupe(headers)


# ============================================================
# Remove narrow/hidden columns by width
# ============================================================
def remove_narrow_columns(df, ws):
    try:
        keep = []
        col_letters = [c[0].column_letter for c in ws.columns]

        for idx, letter in enumerate(col_letters):
            dim = ws.column_dimensions.get(letter)
            width = dim.width if dim and dim.width is not None else ws.column_dimensions.defaultColWidth

            if width is None or width > 2:
                keep.append(idx)

        return df.iloc[:, keep]
    except:
        return df


# ============================================================
# Clean numeric values
# ============================================================
def clean_val(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().replace("\u00A0", " ").replace(",", "")

    if s.lower() in ["n.a.", "n.a", "na", "-", "--", ""]:
        return pd.NA

    # (123)
    if re.fullmatch(r"\(\s*[\d\.]+\s*\)", s):
        try:
            return -float(s.strip("()"))
        except:
            return s

    # %
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return s

    # numeric
    try:
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s)
    except:
        pass

    return s


# ============================================================
# Clean Excel table (MAIN FUNCTION)
# ============================================================
def clean_excel_table(df_raw, sheet, filepath, debug=False):
    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet]

    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    # Debug: show raw header rows
    if debug:
        st.subheader(f"🔍 DEBUG — Raw Header Rows (Rows 1–4) for {sheet}")
        st.write(df.head(4))

    # Build final headers (using Row2 + Row3)
    headers = build_final_headers(ws, df)

    if debug:
        st.subheader("🔍 DEBUG — Final Hierarchical Headers")
        st.write(headers)

    # First column = Particulars
    if headers:
        headers[0] = "Particulars"

    df.columns = headers

    # Remove invalid headers
    df = df.loc[:, [c for c in df.columns if c.strip() != "" and not c.startswith("_")]]

    # Remove header rows (Row1 = title, Row2/3 = header)
    df = df.iloc[3:].reset_index(drop=True)

    # Remove narrow template columns
    df = remove_narrow_columns(df, ws)

    # Numeric cleaning
    df = df.applymap(clean_val)
    df = df.dropna(axis=1, how="all")

    return df


# ============================================================
# PDF cleaner
# ============================================================
def clean_pdf_table(df_raw):
    df = df_raw.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df
    header = df.iloc[0].astype(str).str.strip()
    df.columns = dedupe(header)
    df = df.iloc[1:].reset_index(drop=True)
    return df.applymap(clean_val)


# ============================================================
# Simple classifier
# ============================================================
def classify(df):
    text = " ".join(str(c).lower() for c in df.columns)
    if any(k in text for k in ["balance", "asset", "liability", "equity"]):
        return "Balance Sheet"
    if any(k in text for k in ["income", "revenue", "profit", "loss"]):
        return "Income Statement"
    if any(k in text for k in ["cash", "operating", "financing", "investing"]):
        return "Cash Flow Statement"
    return "Other"


# ============================================================
# Streamlit UI
# ============================================================
st.title("📊 Final Financial Statement Extractor (Multi-Layer Merged Header Engine)")

debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=False)

uploaded = st.file_uploader("Upload Excel or PDF", type=["xlsx", "xls", "pdf"])

if uploaded:
    filepath = f"temp_{uploaded.name}"
    with open(filepath, "wb") as f:
        f.write(uploaded.getbuffer())

    # ============================================================
    # BADZIPFILE FIX — STRICT FILE-TYPE VALIDATION
    # ============================================================
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".xlsx":
        file_type = "excel_xlsx"
    elif ext == ".xls":
        file_type = "excel_xls"
    elif ext == ".pdf":
        file_type = "pdf"
    else:
        st.error("❌ Unsupported file type. Allowed: .xlsx, .xls, .pdf")
        st.stop()

    tables = []

    # ============================
    # Excel (.xlsx)
    # ============================
    if file_type == "excel_xlsx":
        xl = pd.ExcelFile(filepath, engine="openpyxl")
        selected = st.multiselect("Select Sheets", xl.sheet_names, xl.sheet_names)

        for sheet in selected:
            df_raw = xl.parse(sheet, header=None, dtype=object)
            cleaned = clean_excel_table(df_raw, sheet, filepath, debug=debug_mode)
            if not cleaned.empty:
                tables.append(cleaned)

    # ============================
    # Excel (.xls)
    # ============================
    elif file_type == "excel_xls":
        xl = pd.ExcelFile(filepath, engine="xlrd")
        selected = st.multiselect("Select Sheets", xl.sheet_names, xl.sheet_names)

        for sheet in selected:
            df_raw = xl.parse(sheet, header=None, dtype=object)
            cleaned = clean_excel_table(df_raw, sheet, filepath, debug=debug_mode)
            if not cleaned.empty:
                tables.append(cleaned)

    # ============================
    # PDF extraction
    # ============================
    elif file_type == "pdf":
        extracted = []

        try:
            tables_camelot = camelot.read_pdf(filepath, pages="all", flavor="lattice")
            for t in tables_camelot:
                extracted.append(t.df)
        except:
            pass

        try:
            with pdfplumber.open(filepath) as pdf:
                for p in pdf.pages:
                    for tb in p.extract_tables():
                        extracted.append(pd.DataFrame(tb))
        except:
            pass

        try:
            tbs = tabula.read_pdf(filepath, pages="all", multiple_tables=True)
            extracted.extend(tbs)
        except:
            pass

        for df_raw in extracted:
            df_clean = clean_pdf_table(df_raw)
            if not df_clean.empty:
                tables.append(df_clean)

    st.success(f"Extracted {len(tables)} table(s)")

    groups = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    for i, df in enumerate(tables, start=1):
        st.subheader(f"Table {i}")
        st.dataframe(df, use_container_width=True)
        groups[classify(df)].append(df)

    st.header("Summary")
    for k, v in groups.items():
        st.write(f"**{k}: {len(v)} tables**")

    st.download_button(
        "📥 Download Extracted Financials",
        data=to_excel(groups),
        file_name="Extracted_Financials.xlsx"
    )