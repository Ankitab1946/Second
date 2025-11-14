###############################################################
#  FINAL APP.PY (Row1+Row2+Row3 Strict Header Engine)
#  Supports: .xlsx, .xlsm, .xls, .xlsb, .csv, .pdf
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
except:
    openpyxl = None

# Try pyxlsb
try:
    import pyxlsb
except:
    pyxlsb = None

st.set_page_config(page_title="Financial Extractor FINAL", layout="wide")

###############################################################
# CONFIG: Status words to ignore in headers & numeric columns
###############################################################

IGNORED_STATUS_WORDS = {
    "restated", "provisional", "unaudited", "reclassified",
    "notes", "revised", "converted", "normalized",
    "audited", "reviewed"
}

###############################################################
# VALID PARENT KEYWORDS (Row 1 allowed headers)
###############################################################

VALID_PARENT_KEYWORDS = {
    "historical annuals",
    "historical interims",
    "forecasts",
    "cagrars",
    "historical",
    "annual",
    "interim",
    "budget",
    "plan",
    "projection",
    "actuals",
    "ltm"
}

###############################################################
# HEADER TOKEN VALIDATOR
# A+B: Ignore all numeric garbage, accept ONLY 4-digit years,
# ranges, 1H/2H/Q1-Q4/LTM/valid parents
###############################################################

def looks_like_period_or_header_token(token: str) -> bool:
    if not token:
        return False
    t = token.strip().lower()

    # Ignore unacceptable words
    if t in IGNORED_STATUS_WORDS:
        return False

    # Strict parent headers
    if t in VALID_PARENT_KEYWORDS:
        return True

    # Strict year (4 digits)
    if re.fullmatch(r"\d{4}", t):
        return True

    # Strict year range: 2020-2024, 2020_2024, 2020–2024
    if re.fullmatch(r"\d{4}[\-_–]\d{4}", t):
        return True

    # Period tokens: 1H, 2H, Q1–Q4, LTM
    if re.fullmatch(r"[12]h", t):
        return True
    if re.fullmatch(r"q[1-4]", t):
        return True
    if t == "ltm":
        return True

    # Reject all floats/decimals
    if re.fullmatch(r"-?\d+\.\d+", t):
        return False

    # Reject pure integers except 4-digit years
    if t.isdigit():
        return False

    return False


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
                df.to_excel(writer, index=False, sheet_name=f"{cat[:28]}_{i}")
    out.seek(0)
    return out


###############################################################
# Merged Parent Extraction (Excel row 2)
###############################################################

def get_merged_maps_ws(ws):
    merged_parent_map, col_parent_map = {}, {}

    try:
        for rng in ws.merged_cells.ranges:
            min_row, min_col, max_row, max_col = (
                rng.min_row, rng.min_col, rng.max_row, rng.max_col
            )

            val = ws.cell(row=min_row, column=min_col).value
            if val is None:
                continue
            val = str(val).strip().lower()

            for r in range(min_row, max_row+1):
                for c in range(min_col, max_col+1):
                    merged_parent_map[(r, c)] = val

            # Parent band only if merge starts at Row 2
            if min_row == 2:
                for c in range(min_col, max_col+1):
                    col_parent_map[c] = val
    except:
        pass

    return merged_parent_map, col_parent_map


###############################################################
# ROW1 + ROW2 + ROW3 HEADER BUILDER (strict)
###############################################################

def build_headers_from_ws(ws, ncols):
    merged_parent_map, col_parent_map = get_merged_maps_ws(ws)
    headers = []

    for col_idx in range(1, ncols+1):
        parts = []

        # ROW 1
        r1 = ws.cell(row=1, column=col_idx).value
        if r1:
            r1s = str(r1).strip().lower()
            if looks_like_period_or_header_token(r1s):
                parts.append(r1s)

        # ROW 2 (merged parent OR token)
        parent = col_parent_map.get(col_idx)
        if parent and looks_like_period_or_header_token(parent):
            parts.append(parent)
        else:
            r2 = ws.cell(row=2, column=col_idx).value
            if r2:
                r2s = str(r2).strip().lower()
                if looks_like_period_or_header_token(r2s):
                    parts.append(r2s)

        # ROW 3 (period)
        r3 = ws.cell(row=3, column=col_idx).value
        if r3:
            r3s = str(r3).strip().lower()
            if looks_like_period_or_header_token(r3s):
                parts.append(r3s)

        # Remove duplicates
        final = []
        for p in parts:
            if p and p not in final:
                final.append(p)

        headers.append("_".join(final) if final else "")

    return dedupe(headers)


###############################################################
# Clean Cell Values
###############################################################

def clean_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()

    if s.lower() in IGNORED_STATUS_WORDS:
        return pd.NA

    # % values
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return s

    # (123) → -123
    if re.fullmatch(r"\(\s*[\d,\.]+\s*\)", s):
        try:
            return -float(s.strip("()").replace(",", ""))
        except:
            return s

    # 1,234 → 1234
    s_clean = s.replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", s_clean):
        try:
            return float(s_clean)
        except:
            return s

    return s


###############################################################
# CLEAN EXCEL (OPENXML: .xlsx/.xlsm)
###############################################################

def clean_openxml_table(df_raw, sheet, filepath, debug):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)

    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet]

    if debug:
        st.subheader(f"DEBUG — Raw top rows ({sheet})")
        st.write(df.head(4))

    headers = build_headers_from_ws(ws, df.shape[1])

    if debug:
        st.subheader("DEBUG — Computed Headers")
        st.write(headers)

    headers[0] = "particulars"
    df.columns = headers

    # Drop header rows 1–3
    df = df.iloc[3:].reset_index(drop=True)

    # Clean values
    df = df.applymap(clean_cell)

    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


###############################################################
# XLS / XLSB / CSV — simplified header logic fallback
###############################################################

def clean_simple_table(df_raw):
    df = df_raw.dropna(how="all", axis=0).dropna(how="all", axis=1)

    header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else df.iloc[[1]]

    headers = []
    for tokens in header_block.T.values:
        p = []
        for v in tokens:
            if v:
                s = str(v).strip().lower()
                if looks_like_period_or_header_token(s):
                    p.append(s)
        headers.append("_".join(p) if p else "")

    headers = dedupe(headers)
    headers[0] = "particulars"
    df.columns = headers

    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


###############################################################
# PDF Extraction
###############################################################

def extract_pdf_tables(path):
    tables = []

    try:
        import camelot
        t = camelot.read_pdf(path, pages="all", flavor="lattice")
        for tb in t:
            tables.append(tb.df)
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

    return tables


###############################################################
# Classification
###############################################################

def classify(df):
    t = " ".join(str(c).lower() for c in df.columns)
    if any(k in t for k in ["balance", "asset", "equity", "liabil"]):
        return "Balance Sheet"
    if any(k in t for k in ["revenue", "income", "profit", "loss"]):
        return "Income Statement"
    if any(k in t for k in ["cash", "oper", "invest", "financ"]):
        return "Cash Flow Statement"
    return "Other"


###############################################################
# STREAMLIT INTERFACE
###############################################################

st.title("📊 Financial Extractor — FINAL VERSION (Strict Header Model)")

debug_mode = st.sidebar.checkbox("Enable Debug Mode", False)

uploaded = st.file_uploader(
    "Upload your financial file",
    type=["xlsx","xlsm","xls","xlsb","csv","pdf"]
)
if not uploaded:
    st.stop()

filepath = f"temp_{uploaded.name}"
with open(filepath, "wb") as f:
    f.write(uploaded.getbuffer())

ext = os.path.splitext(filepath)[1].lower()
tables = []

###############################################################
# ROUTING BASED ON EXTENSION
###############################################################

# XLSX / XLSM
if ext in [".xlsx", ".xlsm"]:
    xlf = pd.ExcelFile(filepath, engine="openpyxl")
    sheets = st.multiselect("Select sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_openxml_table(df_raw, s, filepath, debug_mode))

# XLS
elif ext == ".xls":
    xlf = pd.ExcelFile(filepath, engine="xlrd")
    sheets = st.multiselect("Select sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_simple_table(df_raw))

# XLSB
elif ext == ".xlsb":
    if pyxlsb:
        xlf = pd.ExcelFile(filepath, engine="pyxlsb")
        sheets = st.multiselect("Select sheets", xlf.sheet_names, xlf.sheet_names)
        for s in sheets:
            df_raw = pd.read_excel(filepath, sheet_name=s, header=None, engine="pyxlsb", dtype=object)
            tables.append(clean_simple_table(df_raw))

# CSV
elif ext == ".csv":
    df_raw = pd.read_csv(filepath, header=None)
    tables.append(clean_simple_table(df_raw))

# PDF
elif ext == ".pdf":
    for df_raw in extract_pdf_tables(filepath):
        tables.append(clean_simple_table(df_raw))

###############################################################
# DISPLAY OUTPUT
###############################################################

tables = [t for t in tables if not t.empty]
st.success(f"Extracted {len(tables)} table(s).")

groups = {
    "Balance Sheet": [],
    "Income Statement": [],
    "Cash Flow Statement": [],
    "Other": []
}

for i, df in enumerate(tables, 1):
    st.subheader(f"Extracted Table {i}")
    st.dataframe(df, width=None)

    groups[classify(df)].append(df)

st.header("Summary")
for k,v in groups.items():
    st.write(f"**{k}** : {len(v)} tables")

st.download_button(
    "📥 Download Extracted Financials",
    data=to_excel(groups),
    file_name="Extracted_Financials.xlsx"
)