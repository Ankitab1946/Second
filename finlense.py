# app.py - Final (supports .xlsx, .xlsm, .xls, .xlsb, .csv, .pdf) with merged-header engine + debug
import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO

# Excel engines / PDF helpers may be optional; imports wrapped where used
try:
    import openpyxl
    from openpyxl import load_workbook
except Exception:
    openpyxl = None

st.set_page_config(page_title="Financial Extractor (All formats)", layout="wide")


# -------------------------
# Utilities
# -------------------------
def to_excel(groups):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for category, tables in groups.items():
            for i, df in enumerate(tables, start=1):
                df.to_excel(writer, index=False, sheet_name=f"{category[:28]}_{i}")
    out.seek(0)
    return out


def dedupe(cols):
    new = []
    cnt = {}
    for c in cols:
        key = "" if c is None else str(c).strip()
        if key not in cnt:
            cnt[key] = 0
            new.append(key)
        else:
            cnt[key] += 1
            new.append(f"{key}_{cnt[key]}")
    return new


# -------------------------
# Merged-parent extraction (openpyxl only)
# -------------------------
def get_merged_parents_openpyxl(ws):
    merged_parent = {}
    col_parent = {}
    for mr in ws.merged_cells.ranges:
        min_row, min_col, max_row, max_col = mr.min_row, mr.min_col, mr.max_row, mr.max_col
        val = ws.cell(row=min_row, column=min_col).value
        if val is None:
            continue
        text = str(val).strip()
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                merged_parent[(r, c)] = text
        # if merge originates on row 2, treat as parent band
        if min_row == 2:
            for c in range(min_col, max_col + 1):
                col_parent[c] = text
    return merged_parent, col_parent


# -------------------------
# Build hierarchical header for Excel (Row2 + Row3)
# Requires openpyxl ws to read merged map; if not available we fallback
# -------------------------
def build_headers_excel(ws, df):
    # df expected with header=None and rows present
    ncols = df.shape[1]
    headers = []

    try:
        merged_parent_map, col_parent_map = get_merged_parents_openpyxl(ws)
    except Exception:
        merged_parent_map, col_parent_map = {}, {}

    for col_idx in range(1, ncols + 1):
        parts = []
        # parent (from merged band in row2)
        parent = col_parent_map.get(col_idx, "")
        if parent and parent.lower() not in ["nan", "none", ""]:
            parts.append(parent)

        # row2 value (index 1)
        r2 = df.iloc[1, col_idx - 1] if df.shape[0] > 1 else ""
        if pd.isna(r2):
            r2v = merged_parent_map.get((2, col_idx), "")
        else:
            r2v = str(r2).strip()
        if r2v and r2v.lower() not in ["nan", "none", ""]:
            if r2v not in parts:
                parts.append(r2v)

        # row3 value (index 2)
        r3 = df.iloc[2, col_idx - 1] if df.shape[0] > 2 else ""
        if pd.isna(r3):
            r3v = merged_parent_map.get((3, col_idx), "")
        else:
            r3v = str(r3).strip()
        if r3v and r3v.lower() not in ["nan", "none", ""]:
            if r3v not in parts:
                parts.append(r3v)

        # collapse dupes keep order
        final = []
        for p in parts:
            if p and p not in final:
                final.append(p)
        headers.append("_".join(final) if final else "")
    return dedupe(headers)


# -------------------------
# Remove narrow columns (openpyxl ws needed)
# -------------------------
def remove_narrow_columns_openpyxl(df, ws, threshold=2):
    try:
        col_letters = [c[0].column_letter for c in ws.columns]
        keep = []
        for idx, letter in enumerate(col_letters):
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
# Clean cell values
# -------------------------
def clean_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().replace("\u00A0", " ").replace(",", "")
    if s.lower() in ["n.a.", "n.a", "na", "-", "--", ""]:
        return pd.NA
    # parentheses -> negative
    if re.fullmatch(r'^\(\s*[\d\.]+\s*\)$', s):
        try:
            return -float(s.strip("()"))
        except:
            return s
    # percent
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except:
            return s
    # numeric
    if re.fullmatch(r'^-?\d+(\.\d+)?$', s):
        try:
            return float(s)
        except:
            return s
    return s


# -------------------------
# Core Excel cleaning using openpyxl when possible
# -------------------------
def clean_excel_table_openxml(df_raw, sheet_name, filepath, debug=False):
    # df_raw: pandas DataFrame with header=None
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df

    # open workbook and ws
    try:
        wb = load_workbook(filepath, data_only=True)
        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
    except Exception as e:
        st.warning(f"openpyxl could not open workbook: {e}")
        ws = None

    if debug:
        st.subheader(f"DEBUG — raw head (first 4 rows) for {sheet_name}")
        st.write(df.head(4))

    # Build headers using row2 + row3 logic
    headers = build_headers_excel(ws, df) if ws is not None else []
    if not headers:
        # fallback: simple join of row2+row3 text
        header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else df.iloc[[1]] if df.shape[0] > 1 else df.iloc[[0]]
        headers = []
        for col_vals in header_block.T.values:
            parts = [str(x).strip() for x in col_vals if str(x).strip() and str(x).strip().lower() not in ["nan", "none"]]
            headers.append("_".join(parts) if parts else "")
        headers = dedupe(headers)

    if debug:
        st.subheader("DEBUG — computed headers")
        st.write(headers[:200])

    # rename first col to Particulars
    if headers:
        headers[0] = "Particulars"

    df.columns = headers
    # remove faux empty header columns
    df = df.loc[:, [c for c in df.columns if str(c).strip() != "" and not str(c).strip().startswith("_")]]

    # drop the first three rows (title + row2/row3)
    df = df.iloc[3:].reset_index(drop=True)

    # remove narrow template columns using ws widths if ws available
    if ws is not None:
        df = remove_narrow_columns_openpyxl(df, ws, threshold=2)

    # clean values
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


# -------------------------
# Legacy .xls handler using xlrd (no merged width read)
# -------------------------
def clean_excel_table_legacy(df_raw, sheet_name, filepath, debug=False):
    # df_raw header=None
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df

    # We do not have merged cell map here reliably — use row2+row3 values to build headers
    header_block = df.iloc[[1, 2]] if df.shape[0] > 2 else (df.iloc[[1]] if df.shape[0] > 1 else df.iloc[[0]])
    headers = []
    for col_vals in header_block.T.values:
        parts = [str(x).strip() for x in col_vals if str(x).strip() and str(x).strip().lower() not in ["nan", "none"]]
        headers.append("_".join(parts) if parts else "")
    headers = dedupe(headers)
    if headers:
        headers[0] = "Particulars"
    df.columns = headers
    df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]]
    df = df.iloc[3:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    df.columns = dedupe(df.columns)
    return df


# -------------------------
# .xlsb handler using pyxlsb via pandas (no openpyxl merged maps)
# -------------------------
def read_xlsb_sheets(filepath):
    # return dict sheet_name -> DataFrame (header=None)
    try:
        # pandas supports engine='pyxlsb' to list sheets via ExcelFile
        xlf = pd.ExcelFile(filepath, engine="pyxlsb")
        sheets = xlf.sheet_names
    except Exception:
        return {}
    out = {}
    for s in sheets:
        try:
            df = pd.read_excel(filepath, sheet_name=s, header=None, engine="pyxlsb", dtype=object)
            out[s] = df
        except Exception:
            continue
    return out


# -------------------------
# PDF cleaning helper (simple)
# -------------------------
def clean_pdf_table(df_raw, debug=False):
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df
    header_rows = 1 if df.shape[0] > 0 else 0
    header_block = df.iloc[0].astype(str).str.strip()
    headers = dedupe(list(header_block))
    df.columns = headers
    df = df.iloc[1:].reset_index(drop=True)
    df = df.applymap(clean_cell)
    df = df.dropna(axis=1, how="all")
    return df


# -------------------------
# Classify simple
# -------------------------
def classify(df):
    text = " ".join([str(c).lower() for c in df.columns])
    if any(k in text for k in ["balance", "asset", "liability", "equity"]):
        return "Balance Sheet"
    if any(k in text for k in ["income", "revenue", "profit", "loss"]):
        return "Income Statement"
    if any(k in text for k in ["cash", "operating", "financing", "investing"]):
        return "Cash Flow Statement"
    return "Other"


# -------------------------
# Streamlit UI
# -------------------------
st.title("Financial Statement Extractor — All formats (Final)")
debug_mode = st.sidebar.checkbox("Enable Debug Mode (Light)", value=False)

uploaded = st.file_uploader("Upload file (.xlsx, .xlsm, .xls, .xlsb, .csv, .pdf)", type=["xlsx", "xlsm", "xls", "xlsb", "csv", "pdf"])
if not uploaded:
    st.info("Upload a file to begin (supported: xlsx, xlsm, xls, xlsb, csv, pdf).")
    st.stop()

# save uploaded to temp path
filepath = f"temp_{uploaded.name}"
with open(filepath, "wb") as f:
    f.write(uploaded.getbuffer())

ext = os.path.splitext(filepath)[1].lower()

# robust type selection
if ext in [".xlsx", ".xlsm"]:
    file_type = "openxml"
elif ext == ".xls":
    file_type = "legacy_xls"
elif ext == ".xlsb":
    file_type = "xlsb"
elif ext == ".csv":
    file_type = "csv"
elif ext == ".pdf":
    file_type = "pdf"
else:
    st.error(f"Unsupported file type: {ext}")
    st.stop()

tables = []

# ---------- openxml: .xlsx / .xlsm (best support)
if file_type == "openxml":
    if openpyxl is None:
        st.error("openpyxl is required to read .xlsx/.xlsm. Install with `pip install openpyxl`.")
        st.stop()
    try:
        xlf = pd.ExcelFile(filepath, engine="openpyxl")
    except Exception as e:
        st.error(f"Failed to open as .xlsx/.xlsm: {e}")
        st.stop()

    selected = st.multiselect("Select sheets", options=xlf.sheet_names, default=xlf.sheet_names)
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()

    for sheet in selected:
        try:
            df_raw = xlf.parse(sheet, header=None, dtype=object)
        except Exception as e:
            st.warning(f"Failed to parse sheet {sheet}: {e}")
            continue
        cleaned = clean_excel_table_openxml(df_raw, sheet, filepath, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

# ---------- legacy .xls
elif file_type == "legacy_xls":
    try:
        xlf = pd.ExcelFile(filepath, engine="xlrd")
    except Exception as e:
        st.error(f"xlrd is required to read .xls. Install with `pip install xlrd` and ensure file is valid. Error: {e}")
        st.stop()
    selected = st.multiselect("Select sheets", options=xlf.sheet_names, default=xlf.sheet_names)
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()
    for sheet in selected:
        try:
            df_raw = xlf.parse(sheet, header=None, dtype=object)
        except Exception as e:
            st.warning(f"Failed to parse sheet {sheet}: {e}")
            continue
        cleaned = clean_excel_table_legacy(df_raw, sheet, filepath, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

# ---------- xlsb
elif file_type == "xlsb":
    # pyxlsb engine for pandas
    try:
        # list sheets
        xlsb_map = read_xlsb_sheets(filepath)
        if not xlsb_map:
            st.error("Failed to read .xlsb. Ensure pyxlsb is installed: pip install pyxlsb")
            st.stop()
    except Exception as e:
        st.error(f"Failed to read .xlsb: {e}")
        st.stop()

    sheet_names = list(xlsb_map.keys())
    selected = st.multiselect("Select sheets", options=sheet_names, default=sheet_names)
    if not selected:
        st.warning("Select at least one sheet.")
        st.stop()

    for sheet in selected:
        df_raw = xlsb_map.get(sheet)
        # fallback cleaning (no merged/width info available)
        if df_raw is None:
            continue
        # use legacy style builder (row2+row3) without openpyxl
        cleaned = clean_excel_table_legacy(df_raw, sheet, filepath, debug=debug_mode)
        if not cleaned.empty:
            tables.append(cleaned)

# ---------- csv
elif file_type == "csv":
    try:
        df = pd.read_csv(filepath, dtype=object)
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")
        st.stop()
    # convert to header=None style: prefix columns to emulate positions
    df_raw = df.copy()
    # If header exists, encourage user: but we will treat first 3 rows as title+row2+row3 heuristically
    # Ensure there are at least 3 rows; if not, fallback simple parsing
    if df_raw.shape[0] >= 3:
        # set header None by resetting index and treating first rows as raw
        df_raw = pd.read_csv(filepath, header=None, dtype=object)
        cleaned = clean_excel_table_legacy(df_raw, "csv", filepath, debug=debug_mode)
    else:
        cleaned = df_raw.applymap(clean_cell)
    if not cleaned.empty:
        tables.append(cleaned)

# ---------- pdf
elif file_type == "pdf":
    extracted = []
    # camelot
    try:
        import camelot
        c = camelot.read_pdf(filepath, pages="all", flavor="lattice")
        for t in c:
            extracted.append(t.df)
    except Exception:
        pass
    # pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for p in pdf.pages:
                for tbl in p.extract_tables():
                    extracted.append(pd.DataFrame(tbl))
    except Exception:
        pass
    # tabula
    try:
        import tabula
        tbs = tabula.read_pdf(filepath, pages="all", multiple_tables=True)
        for t in tbs:
            extracted.append(t)
    except Exception:
        pass

    for df_raw in extracted:
        try:
            cleaned = clean_pdf_table(df_raw, debug=debug_mode)
            if not cleaned.empty:
                tables.append(cleaned)
        except Exception:
            continue

# Results & UI
st.success(f"Extracted {len(tables)} table(s)")

groups = {"Balance Sheet": [], "Income Statement": [], "Cash Flow Statement": [], "Other": []}
for i, df in enumerate(tables, start=1):
    st.subheader(f"Table {i}")
    st.dataframe(df, use_container_width=True)
    cat = classify(df)
    groups[cat].append(df)

st.header("Summary")
for k, v in groups.items():
    st.write(f"**{k}: {len(v)} tables**")

st.download_button("📥 Download Extracted Tables", data=to_excel(groups), file_name="extracted_financials.xlsx")