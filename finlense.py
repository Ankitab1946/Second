###############################################################
#  FINAL APP.PY (Row1+Row2+Row3 Strict Header Engine)
#  Supports: .xlsx, .xlsm, .xls, .xlsb, .csv, .pdf
#  Updated: width="stretch"
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
# CONFIG
###############################################################

IGNORED_STATUS_WORDS = {
    "restated", "provisional", "unaudited", "reclassified",
    "notes", "revised", "converted", "normalized",
    "audited", "reviewed"
}

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
# HEADER TOKEN VALIDATION (STRICT)
###############################################################

def looks_like_period_or_header_token(token: str) -> bool:
    if not token:
        return False
    t = token.strip().lower()

    if t in IGNORED_STATUS_WORDS:
        return False

    if t in VALID_PARENT_KEYWORDS:
        return True

    # 4-digit year
    if re.fullmatch(r"\d{4}", t):
        return True

    # valid year ranges
    if re.fullmatch(r"\d{4}[\-_–]\d{4}", t):
        return True

    # 1H / 2H / Q1–Q4 / LTM
    if re.fullmatch(r"[12]h", t):
        return True
    if re.fullmatch(r"q[1-4]", t):
        return True
    if t == "ltm":
        return True

    # reject floats, decimals, random numbers
    if re.fullmatch(r"-?\d+\.\d+", t):
        return False
    if t.isdigit():
        return False

    return False


###############################################################
# UTILITIES
###############################################################

def dedupe(cols):
    new = []
    counts = {}
    for c in cols:
        k = "" if c is None else str(c).strip()
        if k not in counts:
            counts[k] = 0
        else:
            counts[k] += 1
            k = f"{k}_{counts[k]}"
        new.append(k)
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
# MERGED CELL MAP
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

            if min_row == 2:
                for c in range(min_col, max_col+1):
                    col_parent_map[c] = val

    except:
        pass

    return merged_parent_map, col_parent_map


###############################################################
# HEADER BUILDER (ROW1 + ROW2 + ROW3)
###############################################################

def build_headers_from_ws(ws, ncols):
    _, col_parent_map = get_merged_maps_ws(ws)
    headers = []

    for col in range(1, ncols+1):
        parts = []

        # ROW 1
        r1 = ws.cell(1, col).value
        if r1:
            r1s = str(r1).strip().lower()
            if looks_like_period_or_header_token(r1s):
                parts.append(r1s)

        # ROW 2 (merged OR value)
        parent = col_parent_map.get(col)
        if parent and looks_like_period_or_header_token(parent):
            parts.append(parent)
        else:
            r2 = ws.cell(2, col).value
            if r2:
                r2s = str(r2).strip().lower()
                if looks_like_period_or_header_token(r2s):
                    parts.append(r2s)

        # ROW 3
        r3 = ws.cell(3, col).value
        if r3:
            r3s = str(r3).strip().lower()
            if looks_like_period_or_header_token(r3s):
                parts.append(r3s)

        # clean duplicates
        final = []
        for p in parts:
            if p not in final:
                final.append(p)

        headers.append("_".join(final) if final else "")

    return dedupe(headers)


###############################################################
# CLEAN CELL VALUES
###############################################################

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

    if re.fullmatch(r"$begin:math:text$\\s*[\\d,\\.]+\\s*$end:math:text$", s):
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
# CLEAN XLSX / XLSM
###############################################################

def clean_openxml_table(df_raw, sheet, filepath, debug):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(how="all").dropna(how="all", axis=1)

    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet]

    headers = build_headers_from_ws(ws, df.shape[1])
    headers[0] = "particulars"
    df.columns = headers

    # remove header rows
    df = df.iloc[3:].reset_index(drop=True)

    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


###############################################################
# CLEAN SIMPLE (XLS / XLSB / CSV)
###############################################################

def clean_simple_table(df_raw):
    df = df_raw.dropna(how="all").dropna(how="all", axis=1)

    header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else df.iloc[[1]]

    headers = []
    for toks in header_block.T.values:
        parts = []
        for v in toks:
            if v:
                s = str(v).strip().lower()
                if looks_like_period_or_header_token(s):
                    parts.append(s)
        headers.append("_".join(parts) if parts else "")

    headers = dedupe(headers)
    headers[0] = "particulars"
    df.columns = headers

    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


###############################################################
# PDF HELPER
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
# CLASSIFICATION
###############################################################

def classify(df):
    t = " ".join(df.columns).lower()
    if any(k in t for k in ["asset", "liabil", "balance", "equity"]):
        return "Balance Sheet"
    if any(k in t for k in ["income", "profit", "revenue", "loss"]):
        return "Income Statement"
    if any(k in t for k in ["cash", "oper", "invest", "financ"]):
        return "Cash Flow Statement"
    return "Other"


###############################################################
# STREAMLIT UI
###############################################################

st.title("📊 Financial Extractor — FINAL (width=stretch applied)")

debug = st.sidebar.checkbox("Debug Mode", False)

uploaded = st.file_uploader(
    "Upload (.xlsx, .xlsm, .xls, .xlsb, .csv, .pdf)",
    type=["xlsx","xlsm","xls","xlsb","csv","pdf"]
)
if not uploaded:
    st.stop()

filepath = f"tmp_{uploaded.name}"
with open(filepath, "wb") as f:
    f.write(uploaded.getbuffer())

ext = os.path.splitext(filepath)[1].lower()
tables = []

###############################################################
# ROUTING BY EXTENSION
###############################################################

# XLSX / XLSM
if ext in [".xlsx", ".xlsm"]:
    xlf = pd.ExcelFile(filepath, engine="openpyxl")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_openxml_table(df_raw, s, filepath, debug))

# XLS
elif ext == ".xls":
    xlf = pd.ExcelFile(filepath, engine="xlrd")
    sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
    for s in sheets:
        df_raw = xlf.parse(s, header=None, dtype=object)
        tables.append(clean_simple_table(df_raw))

# XLSB
elif ext == ".xlsb":
    if pyxlsb:
        xlf = pd.ExcelFile(filepath, engine="pyxlsb")
        sheets = st.multiselect("Select Sheets", xlf.sheet_names, xlf.sheet_names)
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
# DISPLAY TABLES
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
    st.dataframe(df, width="stretch")   # <<<< PATCH APPLIED HERE

    groups[classify(df)].append(df)

###############################################################
# SUMMARY + DOWNLOAD
###############################################################

st.header("Summary")
for k,v in groups.items():
    st.write(f"**{k}** : {len(v)} tables")

st.download_button(
    "📥 Download Extracted Financials",
    data=to_excel(groups),
    file_name="Extracted_Financials.xlsx"
)