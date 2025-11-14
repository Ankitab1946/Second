# app.py - Final (single-file)
# Supports: .xlsx, .xlsm, .xls, .xlsb, .csv, .pdf
# Robust header engine: uses Excel Row2 + Row3 (openpyxl) and merged parents

import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO

# optional imports
try:
    import openpyxl
    from openpyxl import load_workbook
except Exception:
    openpyxl = None

# For .xlsb support (pyxlsb engine)
try:
    import pyxlsb  # noqa: F401
except Exception:
    pyxlsb = None

st.set_page_config(page_title="Financial Extractor (Final v2)", layout="wide")

# -------------------------
# Configuration: ignore words that must NOT be headers or numeric values
# -------------------------
IGNORED_STATUS_WORDS = {
    "restated",
    "provisional",
    "unaudited",
    "reclassified",
    "notes",
    "revised",
    "converted",
    "normalized",
    "unaudited/unauthorised"
}

# small helper to check if a token is a likely period/year/valid header fragment
def looks_like_period_or_header_token(token: str) -> bool:
    if not token:
        return False
    t = token.strip().lower()
    if t in IGNORED_STATUS_WORDS:
        return False
    # year e.g., 2020
    if re.fullmatch(r"\d{4}", t):
        return True
    # year range 2020-2024 or 2020_2024 or 2020–2024
    if re.search(r"\d{4}[\-_–]\d{4}", t):
        return True
    # 1H, 2H, Q1, Q2
    if re.fullmatch(r"\d{1,2}h", t) or re.fullmatch(r"q\d", t):
        return True
    # LTM, CAGR, CAGRARS, Forecasts, Historical etc. allow broad words
    if any(k in t for k in ["ltm", "cagr", "cagrars", "forecast", "forecasted", "histor", "annual", "interim", "budget", "variation", "variance"]):
        return True
    # percent or numeric (rare in header)
    if re.fullmatch(r"-?\d+(\.\d+)?%?", t):
        return True
    # fallback: if token is short alpha word (like "FY", "FY20")
    if len(t) <= 6 and re.fullmatch(r"[a-z0-9_]+", t):
        return True
    return False

# -------------------------
# Utilities
# -------------------------
def to_excel(groups):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for category, tables in groups.items():
            for i, df in enumerate(tables, start=1):
                sheet = f"{category[:28]}_{i}"
                try:
                    df.to_excel(writer, index=False, sheet_name=sheet)
                except Exception:
                    # fallback to safe sheet name
                    df.to_excel(writer, index=False, sheet_name=f"Sheet_{i}")
    out.seek(0)
    return out

def dedupe(cols):
    new = []
    counts = {}
    for c in cols:
        key = "" if c is None else str(c).strip()
        if key not in counts:
            counts[key] = 0
            new.append(key)
        else:
            counts[key] += 1
            new.append(f"{key}_{counts[key]}")
    return new

# -------------------------
# openpyxl merged-parent extraction (Row2 parents)
# -------------------------
def get_merged_maps_ws(ws):
    merged_parent = {}   # (row, col) -> top-left merged value
    col_parent = {}      # col -> parent (if merge starts at row 2)
    try:
        for rng in ws.merged_cells.ranges:
            min_row, min_col, max_row, max_col = rng.min_row, rng.min_col, rng.max_row, rng.max_col
            top_val = ws.cell(row=min_row, column=min_col).value
            if top_val is None:
                continue
            top_val = str(top_val).strip()
            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    merged_parent[(r, c)] = top_val
            # if merged block originates on row 2 treat as parent band
            if min_row == 2:
                for c in range(min_col, max_col + 1):
                    col_parent[c] = top_val
    except Exception:
        # if ws has no merged ranges or openpyxl weirdness, return empties
        return {}, {}
    return merged_parent, col_parent

# -------------------------
# Header builder: uses Excel row2 & row3 directly (openpyxl)
# -------------------------
def build_headers_from_ws(ws, ncols):
    merged_parent_map, col_parent_map = get_merged_maps_ws(ws)
    headers = []
    for col_idx in range(1, ncols + 1):
        parts = []
        # Parent band (from merged region in row2)
        parent = col_parent_map.get(col_idx, "")
        if parent and isinstance(parent, str):
            parent_token = parent.strip()
            if parent_token and parent_token.lower() not in IGNORED_STATUS_WORDS:
                parts.append(parent_token)

        # Row2 exact cell from Excel
        try:
            r2_val = ws.cell(row=2, column=col_idx).value
        except Exception:
            r2_val = None
        if r2_val is not None:
            r2s = str(r2_val).strip()
            if r2s and r2s.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(r2s):
                if r2s not in parts:
                    parts.append(r2s)

        # Row3 exact cell from Excel
        try:
            r3_val = ws.cell(row=3, column=col_idx).value
        except Exception:
            r3_val = None
        if r3_val is not None:
            r3s = str(r3_val).strip()
            if r3s and r3s.lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(r3s):
                if r3s not in parts:
                    parts.append(r3s)

        # final join preserving order and uniqueness
        final = []
        for p in parts:
            if p and p not in final:
                final.append(p)
        headers.append("_".join(final) if final else "")
    return dedupe(headers)

# -------------------------
# Remove narrow columns by width (openpyxl)
# -------------------------
def remove_narrow_columns(df, ws, threshold=2):
    try:
        letters = [c[0].column_letter for c in ws.columns]
        keep = []
        for idx, letter in enumerate(letters):
            dim = ws.column_dimensions.get(letter)
            width = dim.width if (dim and dim.width is not None) else getattr(ws.column_dimensions, "defaultColWidth", None)
            if width is None or width > threshold:
                keep.append(idx)
        if keep:
            return df.iloc[:, keep]
    except Exception:
        pass
    return df

# -------------------------
# Clean cells - ignore status words in numeric columns
# -------------------------
def clean_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if not s:
        return pd.NA
    low = s.lower()
    # treat ignored statuses as NA (prevents mixing text in numeric columns)
    if low in IGNORED_STATUS_WORDS:
        return pd.NA
    # percentages
    if low.endswith('%'):
        try:
            return float(low[:-1].replace(",","").strip()) / 100.0
        except:
            return s
    # parentheses negative
    if re.fullmatch(r"^\(\s*[\d,\.]+\s*\)$", s):
        try:
            return -float(s.strip("()").replace(",",""))
        except:
            return s
    # plain numeric with optional commas
    s_clean = s.replace(",","")
    if re.fullmatch(r"^-?\d+(\.\d+)?$", s_clean):
        try:
            return float(s_clean)
        except:
            return s
    return s

# -------------------------
# Core Excel (.xlsx/.xlsm) cleaning using openpyxl for header/merged info
# df_raw expected header=None
# -------------------------
def clean_openxml_table(df_raw, sheet_name, filepath, debug=False):
    # normalize empty tokens
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df

    # open workbook and sheet
    try:
        wb = load_workbook(filepath, data_only=True)
        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
    except Exception as e:
        # fallback to simple header builder using df
        ws = None

    if debug:
        st.subheader(f"DEBUG: Raw top rows (sheet={sheet_name})")
        try:
            st.write(df.head(4))
        except Exception:
            pass

    # Build headers using true Excel row2 & row3 when ws is available
    if ws is not None:
        ncols = df.shape[1]
        headers = build_headers_from_ws(ws, ncols)
    else:
        # fallback: join df.iloc[1] + df.iloc[2] if present
        header_block = df.iloc[[1,2]] if df.shape[0] > 2 else (df.iloc[[1]] if df.shape[0] > 1 else df.iloc[[0]])
        headers = []
        for col_vals in header_block.T.values:
            parts = [str(v).strip() for v in col_vals if str(v).strip() and str(v).strip().lower() not in IGNORED_STATUS_WORDS]
            headers.append("_".join(parts) if parts else "")
        headers = dedupe(headers)

    if debug:
        st.subheader("DEBUG: Computed headers")
        st.write(headers[:300])

    # assign headers - ensure first column is Particulars (title column)
    if headers:
        headers[0] = "Particulars"
    df.columns = headers

    # drop header rows (Row1 title + Row2/Row3 headers)
    # we used Excel rows directly; pandas row indexes may not be exactly Excel row numbers
    # df_raw had header=None: df rows correspond to Excel rows starting at 1
    # thus drop first 3 rows
    df = df.iloc[3:].reset_index(drop=True)

    # remove narrow columns based on Excel widths (if ws available)
    if ws is not None:
        df = remove_narrow_columns(df, ws, threshold=2)

    # clean values (map status words to NA, convert numeric)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df

# -------------------------
# Simple cleaning (fallback) for .xls/.xlsb/.csv where we don't have full openpyxl
# Treat first three rows as [title,row2,row3]
# -------------------------
def clean_simple_table(df_raw, source_label="sheet", debug=False):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df
    header_block = df.iloc[[1,2]] if df.shape[0] > 2 else (df.iloc[[1]] if df.shape[0] > 1 else df.iloc[[0]])
    headers = []
    for col_vals in header_block.T.values:
        parts = [str(v).strip() for v in col_vals if str(v).strip() and str(v).strip().lower() not in IGNORED_STATUS_WORDS and looks_like_period_or_header_token(str(v).strip())]
        headers.append("_".join(parts) if parts else "")
    headers = dedupe(headers)
    if headers:
        headers[0] = "Particulars"
    df.columns = headers
    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    if debug:
        st.subheader(f"DEBUG: simple cleaned headers ({source_label})")
        st.write(df.columns.tolist()[:200])
    return df

# -------------------------
# Read .xlsb using pandas + pyxlsb (best-effort)
# -------------------------
def read_xlsb_all_sheets(filepath):
    try:
        xlf = pd.ExcelFile(filepath, engine="pyxlsb")
        sheets = xlf.sheet_names
    except Exception:
        return {}
    out = {}
    for s in sheets:
        try:
            df = pd.read_excel(filepath, sheet_name=s, engine="pyxlsb", header=None, dtype=object)
            out[s] = df
        except Exception:
            continue
    return out

# -------------------------
# PDF cleaning helpers (camelot/pdfplumber/tabula)
# -------------------------
def extract_tables_from_pdf(filepath):
    tables = []
    # camelot lattice (best for ruled tables)
    try:
        import camelot
        ct = camelot.read_pdf(filepath, pages="all", flavor="lattice")
        for t in ct:
            tables.append(t.df)
    except Exception:
        pass
    # pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for p in pdf.pages:
                for tbl in p.extract_tables():
                    if tbl:
                        tables.append(pd.DataFrame(tbl))
    except Exception:
        pass
    # tabula (fallback)
    try:
        import tabula
        tbs = tabula.read_pdf(filepath, pages="all", multiple_tables=True)
        for t in tbs:
            if isinstance(t, pd.DataFrame):
                tables.append(t)
    except Exception:
        pass
    return tables

# -------------------------
# classification simple
# -------------------------
def classify(df):
    t = " ".join([str(c).lower() for c in df.columns])
    if any(k in t for k in ["balance", "asset", "liabil", "equity"]):
        return "Balance Sheet"
    if any(k in t for k in ["income", "revenue", "profit", "loss", "sales"]):
        return "Income Statement"
    if any(k in t for k in ["cash", "operat", "invest", "financ"]):
        return "Cash Flow Statement"
    return "Other"

# -------------------------
# Streamlit UI
# -------------------------
st.title("Financial Statement Extractor — Final (Header-stable)")

debug_mode = st.sidebar.checkbox("Enable Debug Mode (Light)", value=False)

uploaded = st.file_uploader("Upload file (.xlsx, .xlsm, .xls, .xlsb, .csv, .pdf)", type=["xlsx", "xlsm", "xls", "xlsb", "csv", "pdf"])
if not uploaded:
    st.info("Upload a file to begin.")
    st.stop()

# Save uploaded file
tmp_path = f"temp_{uploaded.name}"
with open(tmp_path, "wb") as f:
    f.write(uploaded.getbuffer())

ext = os.path.splitext(tmp_path)[1].lower()
tables = []

# strict type dispatch
if ext in [".xlsx", ".xlsm"]:
    # require openpyxl
    if openpyxl is None:
        st.error("openpyxl is required to read .xlsx/.xlsm. Install: pip install openpyxl")
        st.stop()
    try:
        xlf = pd.ExcelFile(tmp_path, engine="openpyxl")
    except Exception as e:
        st.error(f"Failed to open .xlsx/.xlsm: {e}")
        st.stop()
    selected = st.multiselect("Select sheets", xlf.sheet_names, xlf.sheet_names)
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()
    for sheet in selected:
        try:
            df_raw = xlf.parse(sheet, header=None, dtype=object)
        except Exception as e:
            st.warning(f"Failed to parse sheet {sheet}: {e}")
            continue
        cleaned = clean_openxml_table(df_raw, sheet, tmp_path, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

elif ext == ".xls":
    try:
        xlf = pd.ExcelFile(tmp_path, engine="xlrd")
    except Exception as e:
        st.error(f"xlrd is required to read .xls. Install: pip install xlrd. Error: {e}")
        st.stop()
    selected = st.multiselect("Select sheets", xlf.sheet_names, xlf.sheet_names)
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()
    for sheet in selected:
        try:
            df_raw = xlf.parse(sheet, header=None, dtype=object)
        except Exception as e:
            st.warning(f"Failed to parse sheet {sheet}: {e}")
            continue
        cleaned = clean_simple_table(df_raw, source_label=sheet, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

elif ext == ".xlsb":
    if pyxlsb is None:
        st.error("pyxlsb is required to read .xlsb. Install: pip install pyxlsb")
        st.stop()
    xlsb_map = read_xlsb_all_sheets(tmp_path)
    if not xlsb_map:
        st.error("No sheets found in .xlsb or failed to read .xlsb.")
        st.stop()
    selected = st.multiselect("Select sheets", list(xlsb_map.keys()), list(xlsb_map.keys()))
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()
    for sheet in selected:
        df_raw = xlsb_map.get(sheet)
        if df_raw is None:
            continue
        cleaned = clean_simple_table(df_raw, source_label=sheet, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

elif ext == ".csv":
    try:
        # read raw to see header-like rows; treat as header-less (header=None)
        df_raw = pd.read_csv(tmp_path, header=None, dtype=object)
        cleaned = clean_simple_table(df_raw, source_label="csv", debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")
        st.stop()

elif ext == ".pdf":
    extracted = extract_tables_from_pdf(tmp_path)
    if not extracted:
        st.warning("No tables found in PDF or PDF extraction failed.")
    for df_raw in extracted:
        try:
            cleaned = clean_pdf_table(df_raw, debug=debug_mode)
            if not cleaned.empty:
                tables.append(cleaned)
        except Exception:
            continue

st.success(f"Extracted {len(tables)} table(s)")

groups = {"Balance Sheet": [], "Income Statement": [], "Cash Flow Statement": [], "Other": []}
for i, df in enumerate(tables, start=1):
    st.subheader(f"Table {i}")
    st.dataframe(df, use_container_width=True)
    groups[classify(df)].append(df)

st.header("Summary")
for k, v in groups.items():
    st.write(f"**{k}: {len(v)} tables**")

st.download_button("📥 Download Extracted Tables", data=to_excel(groups), file_name="extracted_financials.xlsx")