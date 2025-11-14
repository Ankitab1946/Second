###############################################################
#  FINAL app.py (Row 1 included in header)
#  Supports: .xlsx, .xlsm, .xls, .xlsb, .csv, .pdf
#  Header Model: Row1 + Row2 + Row3 (Merged-aware)
###############################################################

import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO

# Try openpyxl
try:
    import openpyxl
    from openpyxl import load_workbook
except ImportError:
    openpyxl = None

# Try pyxlsb
try:
    import pyxlsb
except ImportError:
    pyxlsb = None

st.set_page_config(page_title="Financial Extractor – Final (Row1 Included)", layout="wide")

###############################################################
# Configuration
###############################################################

IGNORED_STATUS_WORDS = {
    "restated",
    "provisional",
    "unaudited",
    "reclassified",
    "notes",
    "revised",
    "converted",
    "normalized",
    "audited",
    "reviewed"
}

def looks_like_period_or_header_token(token: str) -> bool:
    """Check if a value is valid for header concatenation."""
    if not token:
        return False

    t = token.strip().lower()
    if t in IGNORED_STATUS_WORDS:
        return False

    # Year (2020)
    if re.fullmatch(r"\d{4}", t):
        return True

    # Year ranges: 2020-2024, 2020_2024, 2020–2024
    if re.search(r"\d{4}[\-_–]\d{4}", t):
        return True

    # 1H, 2H, Q1, Q2
    if re.fullmatch(r"\d{1,2}h", t) or re.fullmatch(r"q\d", t):
        return True

    # Financial header words
    if any(k in t for k in [
        "histor", "annual", "interim", "forecast", "budget",
        "cagr", "cagrars", "variation", "lts", "ltm"
    ]):
        return True

    return True  # accept everything else unless ignored


###############################################################
# Utilities
###############################################################

def dedupe(cols):
    new = []
    counts = {}
    for c in cols:
        key = "" if c is None else str(c).strip()
        if key not in counts:
            counts[key] = 0
        else:
            counts[key] += 1
            key = f"{key}_{counts[key]}"
        new.append(key)
    return new


def to_excel(groups):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for cat, tablist in groups.items():
            for i, df in enumerate(tablist, 1):
                sheet = f"{cat[:28]}_{i}"
                df.to_excel(writer, index=False, sheet_name=sheet)
    out.seek(0)
    return out


###############################################################
# Merged Cells Detection (openpyxl)
###############################################################

def get_merged_maps_ws(ws):
    merged_parent_map = {}
    col_parent_map = {}

    try:
        for rng in ws.merged_cells.ranges:
            min_row, min_col, max_row, max_col = rng.min_row, rng.min_col, rng.max_row, rng.max_col
            top_val = ws.cell(row=min_row, column=min_col).value
            if top_val is None:
                continue
            top_val = str(top_val).strip()

            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    merged_parent_map[(r, c)] = top_val

            if min_row == 2:
                for c in range(min_col, max_col + 1):
                    col_parent_map[c] = top_val
    except Exception:
        return {}, {}

    return merged_parent_map, col_parent_map


###############################################################
# 🔥 FINAL HEADER BUILDER — Row1 + Row2 + Row3
###############################################################

def build_headers_from_ws(ws, ncols):
    merged_parent_map, col_parent_map = get_merged_maps_ws(ws)
    headers = []

    for col_idx in range(1, ncols + 1):
        parts = []

        # -------------------------
        # Row 1 (Always Included)
        # -------------------------
        r1 = ws.cell(row=1, column=col_idx).value
        if r1 is not None:
            r1s = str(r1).strip()
            if r1s and r1s.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(r1s):
                parts.append(r1s)

        # -------------------------
        # Row 2 (Merged parent band OR direct value)
        # -------------------------
        parent = col_parent_map.get(col_idx)
        if parent:
            p = parent.strip()
            if p.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(p):
                parts.append(p)
        else:
            r2 = ws.cell(row=2, column=col_idx).value
            if r2 is not None:
                r2s = str(r2).strip()
                if r2s and r2s.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(r2s):
                    parts.append(r2s)

        # -------------------------
        # Row 3 (child period)
        # -------------------------
        r3 = ws.cell(row=3, column=col_idx).value
        if r3 is not None:
            r3s = str(r3).strip()
            if r3s and r3s.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(r3s):
                parts.append(r3s)

        # Remove duplicates
        final = []
        for p in parts:
            if p and p not in final:
                final.append(p)

        headers.append("_".join(final) if final else "")

    return dedupe(headers)


###############################################################
# Cleaning Utilities
###############################################################

def remove_narrow_columns(df, ws, threshold=2):
    try:
        letters = [c[0].column_letter for c in ws.columns]
        keep = []
        for idx, ltr in enumerate(letters):
            dim = ws.column_dimensions.get(ltr)
            width = dim.width if (dim and dim.width is not None) else ws.column_dimensions.defaultColWidth
            if width is None or width > threshold:
                keep.append(idx)
        return df.iloc[:, keep]
    except:
        return df


def clean_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s.lower() in IGNORED_STATUS_WORDS:
        return pd.NA
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return s
    if re.fullmatch(r"\(\s*[\d,\.]+\s*\)", s):
        try:
            return -float(s.strip("()").replace(",", ""))
        except:
            return s
    s_clean = s.replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", s_clean):
        try:
            return float(s_clean)
        except:
            return s
    return s


###############################################################
# CLEAN EXCEL (.xlsx/.xlsm) USING OPENPYXL
###############################################################

def clean_openxml_table(df_raw, sheet, filepath, debug):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet]

    if debug:
        st.subheader(f"DEBUG — Raw header rows ({sheet})")
        st.write(df.head(4))

    headers = build_headers_from_ws(ws, df.shape[1])

    if debug:
        st.subheader("DEBUG — Computed Headers (Row1+Row2+Row3)")
        st.write(headers)

    # Assign headers
    headers[0] = "Particulars"
    df.columns = headers

    # Drop header rows (1,2,3)
    df = df.iloc[3:].reset_index(drop=True)

    df = remove_narrow_columns(df, ws)

    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")

    df.columns = dedupe(df.columns)
    return df


###############################################################
# SIMPLE CLEANER FOR XLS / XLSB / CSV
###############################################################

def clean_simple_table(df_raw):
    df = df_raw.replace(["", None, " "], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else df.iloc[[1]]

    headers = []
    for vlist in header_block.T.values:
        toks = []
        for v in vlist:
            if v is None:
                continue
            s = str(v).strip()
            if s.lower() in IGNORED_STATUS_WORDS:
                continue
            if looks_like_period_or_header_token(s):
                toks.append(s)
        headers.append("_".join(toks) if toks else "")

    headers = dedupe(headers)
    headers[0] = "Particulars"
    df.columns = headers

    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


###############################################################
# PDF Handlers
###############################################################

def extract_tables_pdf(path):
    tables = []

    try:
        import camelot
        ct = camelot.read_pdf(path, pages="all", flavor="lattice")
        for t in ct:
            tables.append(t.df)
    except:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                for tb in p.extract_tables():
                    tables.append(pd.DataFrame(tb))
    except:
        pass

    try:
        import tabula
        tbs = tabula.read_pdf(path, pages="all", multiple_tables=True)
        for t in tbs:
            if isinstance(t, pd.DataFrame):
                tables.append(t)
    except:
        pass

    return tables


###############################################################
# Classification
###############################################################

def classify(df):
    t = " ".join(str(c).lower() for c in df.columns)
    if any(k in t for k in ["asset", "liabil", "equity", "balance"]):
        return "Balance Sheet"
    if any(k in t for k in ["income", "revenue", "profit", "loss"]):
        return "Income Statement"
    if any(k in t for k in ["cash", "oper", "invest", "financ"]):
        return "Cash Flow Statement"
    return "Other"


###############################################################
# STREAMLIT UI
###############################################################

st.title("📊 Financial Statement Extractor — FINAL (Row 1 Included)")

debug_mode = st.sidebar.checkbox("Enable Debug Mode (Light)", False)

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

###############################################################
# ROUTES BY EXTENSION
###############################################################

# XLSX / XLSM
if ext in [".xlsx", ".xlsm"]:
    xlf = pd.ExcelFile(filepath, engine="openpyxl")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_openxml_table(df_raw, s, filepath, debug_mode))

# XLS
elif ext == ".xls":
    xlf = pd.ExcelFile(filepath, engine="xlrd")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_simple_table(df_raw))

# XLSB
elif ext == ".xlsb":
    if pyxlsb is None:
        st.error("Install pyxlsb")
        st.stop()
    xlf = pd.ExcelFile(filepath, engine="pyxlsb")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = pd.read_excel(filepath, sheet_name=s, header=None, engine="pyxlsb", dtype=object)
        tables.append(clean_simple_table(df_raw))

# CSV
elif ext == ".csv":
    df_raw = pd.read_csv(filepath, header=None, dtype=object)
    tables.append(clean_simple_table(df_raw))

# PDF
elif ext == ".pdf":
    for df_raw in extract_tables_pdf(filepath):
        tables.append(clean_simple_table(df_raw))

###############################################################
# DISPLAY RESULTS
###############################################################

tables = [t for t in tables if not t.empty]

st.success(f"Extracted {len(tables)} table(s).")

groups = {
    "Balance Sheet": [],
    "Income Statement": [],
    "Cash Flow Statement": [],
    "Other": [],
}

for i, df in enumerate(tables, 1):
    st.subheader(f"Table {i}")
    st.dataframe(df, use_container_width=True)

    cat = classify(df)
    groups[cat].append(df)

st.header("Summary")
for k, v in groups.items():
    st.write(f"**{k}**: {len(v)} tables")

st.download_button(
    "📥 Download Extracted Data",
    data=to_excel(groups),
    file_name="Extracted_Financials.xlsx"
)