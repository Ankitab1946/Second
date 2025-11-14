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


st.set_page_config(page_title="Financial Statement Extractor (Final)", layout="wide")


# ============================================================
# Utility: Export to Excel
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
# Utility: Deduplicate Columns
# ============================================================
def dedupe(cols):
    new = []
    count = {}
    for c in cols:
        c = str(c).strip()
        if c not in count:
            count[c] = 0
            new.append(c)
        else:
            count[c] += 1
            new.append(f"{c}_{count[c]}")
    return new


# ============================================================
# Detect & extract merged parent from row 2
# ============================================================
def get_merged_parents(ws):
    merged_parent = {}
    for mr in ws.merged_cells.ranges:
        min_row, min_col = mr.min_row, mr.min_col
        max_row, max_col = mr.max_row, mr.max_col
        top_val = ws.cell(min_row, min_col).value
        if top_val is None:
            continue
        top_val = str(top_val).strip()

        # Fill parent for entire merged block
        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                merged_parent[(r, c)] = top_val

    # Build a per-column parent (only row2 matters)
    col_parent = {}
    for (r, c), val in merged_parent.items():
        if r == 2:  # Row2 parent
            col_parent[c] = val

    return merged_parent, col_parent


# ============================================================
# Build Final Header = Parent(Row2 merged) + Row2 + Row3
# ============================================================
def build_final_headers(ws, df):
    ncols = df.shape[1]

    # Load merged-cell structure
    merged_parent_map, col_parent_map = get_merged_parents(ws)

    headers = []

    for col_idx in range(1, ncols + 1):
        parts = []

        # 1. ALWAYS include Parent from merged range (if exists)
        parent = col_parent_map.get(col_idx, "")
        if parent and parent.lower() not in ["nan", "none", ""]:
            parts.append(parent)

        # 2. Row 2 value (header level 1)
        r2 = df.iloc[1, col_idx - 1] if df.shape[0] > 1 else ""
        if pd.isna(r2):
            # Check merged_parent_map for row2
            r2v = merged_parent_map.get((2, col_idx), "")
        else:
            r2v = str(r2).strip()

        if r2v and r2v.lower() not in ["nan", "none", ""]:
            if r2v not in parts:
                parts.append(r2v)

        # 3. Row 3 value (header level 2)
        r3 = df.iloc[2, col_idx - 1] if df.shape[0] > 2 else ""
        if pd.isna(r3):
            r3v = merged_parent_map.get((3, col_idx), "")
        else:
            r3v = str(r3).strip()

        if r3v and r3v.lower() not in ["nan", "none", ""]:
            if r3v not in parts:
                parts.append(r3v)

        # Remove duplicates fully, keep order
        final = [p for i, p in enumerate(parts) if p and p not in parts[:i]]

        headers.append("_".join(final) if final else "")

    return dedupe(headers)


# ============================================================
# Remove narrow-width columns (Excel templates)
# ============================================================
def remove_narrow_columns(df, ws):
    try:
        keep = []
        letters = [c[0].column_letter for c in ws.columns]
        for idx, col_letter in enumerate(letters):
            dim = ws.column_dimensions.get(col_letter)
            width = dim.width if dim and dim.width is not None else ws.column_dimensions.defaultColWidth

            if width is None or width > 2:  # remove blank template columns
                keep.append(idx)
        return df.iloc[:, keep]
    except:
        return df


# ============================================================
# Clean numeric values: %, (123), commas, n.a.
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

    # percent
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return s

    # numeric?
    try:
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s)
    except:
        pass

    return s


# ============================================================
# Clean Excel Table (FINAL LOGIC)
# ============================================================
def clean_excel_table(df_raw, sheet_name, filepath, debug=False):
    wb = load_workbook(filepath, data_only=True)
    ws = wb[sheet_name]

    # Remove blank rows/cols
    df = df_raw.replace(["", " ", None], pd.NA)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    # === DEBUG: Show raw header block ===
    if debug:
        st.subheader(f"🔍 DEBUG: Raw Header Block (Rows 1-4) — {sheet_name}")
        st.write(df.head(4))

    # BUILD FINAL HEADERS (always rows 2 and 3)
    final_headers = build_final_headers(ws, df)

    if debug:
        st.subheader("🔍 DEBUG: Final Merged Headers")
        st.write(final_headers)

    # Rename first column to Particulars
    if final_headers:
        final_headers[0] = "Particulars"

    # Apply
    df.columns = final_headers

    # Drop blank/ghost/_ columns
    df = df.loc[:, [c for c in df.columns if c.strip() != "" and not c.startswith("_")]]

    # Drop header rows (Row1 = title, Row2+3 = headers)
    df = df.iloc[3:].reset_index(drop=True)

    # Remove narrow template columns
    df = remove_narrow_columns(df, ws)

    # Clean numeric values
    df = df.applymap(clean_val)

    # Final cleanup
    df = df.dropna(axis=1, how="all")

    return df


# ============================================================
# PDF extractor (simple headers)
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
# Classification (simple keyword)
# ============================================================
def classify(df):
    text = " ".join(str(c).lower() for c in df.columns)
    if any(k in text for k in ["balance", "asset", "liability", "equity"]):
        return "Balance Sheet"
    if "revenue" in text or "income" in text or "profit" in text:
        return "Income Statement"
    if "cash" in text or "operating" in text or "financing" in text:
        return "Cash Flow Statement"
    return "Other"


# ============================================================
# STREAMLIT UI
# ============================================================
st.title("📊 Final Financial Statement Extractor (Merged Header Engine)")

debug_mode = st.sidebar.checkbox("Enable Debug Mode", value=False)

uploaded = st.file_uploader("Upload Excel/PDF", type=["xlsx", "xls", "pdf"])

if uploaded:
    filepath = f"temp_{uploaded.name}"
    with open(filepath, "wb") as f:
        f.write(uploaded.getbuffer())

    ext = os.path.splitext(filepath)[1].lower()

    tables = []

    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(filepath, engine="openpyxl")

        selected = st.multiselect("Select Sheets", xl.sheet_names, xl.sheet_names)

        for sheet in selected:
            df_raw = xl.parse(sheet, header=None, dtype=object)
            cleaned = clean_excel_table(df_raw, sheet, filepath, debug=debug_mode)
            if not cleaned.empty:
                tables.append(cleaned)

    else:
        tables = read_pdf_file(filepath)

    st.success(f"Extracted {len(tables)} tables")

    groups = {"Balance Sheet": [], "Income Statement": [],
              "Cash Flow Statement": [], "Other": []}

    for i, df in enumerate(tables, start=1):
        st.subheader(f"Table {i}")
        st.dataframe(df, use_container_width=True)

        groups[classify(df)].append(df)

    # Summary
    st.header("Summary")
    for k, v in groups.items():
        st.write(f"**{k}: {len(v)} tables**")

    download = to_excel(groups)
    st.download_button("📥 Download Extracted Tables",
                       data=download,
                       file_name="Extracted_Financials.xlsx")