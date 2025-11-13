# app.py — updated to fix ArrowTypeError, numeric coercion, and lingering NaN columns
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


def to_excel(statement_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for statement, tables in statement_dict.items():
            if len(tables) == 0:
                continue
            for i, df in enumerate(tables, start=1):
                df.to_excel(writer, index=False, sheet_name=f"{statement[:28]}_{i}")
    output.seek(0)
    return output


def deduplicate_columns(columns):
    new_cols, count = [], {}
    for col in columns:
        col = "" if col is None else str(col).strip()
        if col not in count:
            count[col] = 0
            new_cols.append(col)
        else:
            count[col] += 1
            new_cols.append(f"{col}_{count[col]}")
    return new_cols


def detect_header_row(df):
    header_keywords = [
        "particular", "description", "item", "notes", "note",
        "assets", "liabilities", "equity", "year", "fy",
        "statement", "amount", "total", "revenue", "income", "cash"
    ]
    best_row = None
    best_score = -999999
    for idx, row in df.iterrows():
        row_text = " ".join(str(x).lower() for x in row.values if pd.notna(x))
        # Skip numeric-heavy rows
        numeric_ratio = row.apply(lambda x: str(x).replace(".", "", 1).replace(",", "", 1).lstrip("-").isdigit()).mean()
        if numeric_ratio > 0.5:
            continue
        score = sum(1 for kw in header_keywords if kw in row_text)
        score += row.notnull().sum()
        if score > best_score:
            best_score = score
            best_row = idx
    if best_row is None:
        best_row = df.notnull().mean(axis=1).idxmax()
    return best_row


def remove_hidden_columns(df, sheet_name=None, file_path=None):
    if sheet_name is None or file_path is None:
        return df
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        if sheet_name not in wb.sheetnames:
            return df
        ws = wb[sheet_name]
        visible_count = 0
        for col_cells in ws.columns:
            # get letter
            col_letter = col_cells[0].column_letter
            dim = ws.column_dimensions.get(col_letter)
            hidden = False
            if dim is not None:
                # hidden may be None, False, or True
                hidden = bool(dim.hidden)
            if not hidden:
                visible_count += 1
        # limit to visible_count columns (if df has more columns than visible_count)
        if visible_count > 0 and df.shape[1] > visible_count:
            df = df.iloc[:, :visible_count]
        return df
    except Exception:
        return df


# Normalize text cells: strip, replace NBSP, remove weird chars
_nbsp = "\u00A0"
def normalize_text_cell(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if _nbsp in s:
        s = s.replace(_nbsp, " ")
    # collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    # treat empty-like strings as NA
    if s == "" or s.lower() in ["nan", "none", "-"]:
        return pd.NA
    return s


def clean_numeric_text(s):
    # Convert strings like '(1,234)' -> -1234, '1,234' -> 1234, remove spaces and NBSP
    if pd.isna(s):
        return pd.NA
    s = str(s).strip()
    s = s.replace(_nbsp, "")
    s = s.replace(",", "")
    s = s.replace(" ", "")
    # parentheses -> negative
    if re.match(r'^\(.*\)$', s):
        s = "-" + s.replace("(", "").replace(")", "")
    # remove any currency symbols or non-digit prefix/suffix
    s = re.sub(r'[^\d\.\-eE]', '', s)
    if s == "" or s in ["-", ".", "-.", "+"]:
        return pd.NA
    return s


def coerce_numeric_columns(df):
    # If header looks like a year (e.g., '2020') or purely numeric, attempt coercion
    year_re = re.compile(r'^\d{4}$')
    new_df = df.copy()
    for col in df.columns:
        col_str = str(col).strip()
        # attempt numeric coercion if:
        # - header is year-like, OR
        # - a majority of column values look numeric after cleaning
        sample = df[col].dropna().astype(str).head(20).tolist()
        cleaned_sample = [clean_numeric_text(x) for x in sample]
        numeric_count = sum(1 for x in cleaned_sample if x is not pd.NA and re.match(r'^-?\d+(\.\d+)?([eE][-+]?\d+)?$', str(x)))
        if year_re.match(col_str) or (len(sample) > 0 and numeric_count / max(1, len(sample)) > 0.5):
            # perform cleaning and coercion
            new_series = df[col].astype(object).apply(clean_numeric_text)
            new_series = pd.to_numeric(new_series, errors='coerce')
            new_df[col] = new_series
    return new_df


def clean_table(df, sheet_name=None, file_path=None):
    # convert common blank tokens to NA
    df = df.replace(["", " ", "  ", "\t", "\n", "—", "–", "−"], pd.NA)
    # drop fully empty rows/cols
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    if df.empty:
        return df
    # ensure all cells are strings for header detection
    df_headdetect = df.copy().astype(object)
    header_row = detect_header_row(df_headdetect)
    # if header_row out of bounds, fallback safe
    if header_row is None or header_row < 0 or header_row >= len(df):
        header_row = df.notnull().mean(axis=1).idxmax()
    raw_headers = df.iloc[header_row].apply(normalize_text_cell).tolist()
    # replace None/NA with blank string for header processing
    raw_headers = ["" if h is pd.NA or h is None else str(h) for h in raw_headers]
    # set headers
    df.columns = raw_headers
    # drop columns whose header is blank or 'nan' variants
    header_names = [str(h).strip() for h in df.columns.tolist()]
    cleaned_header_names = []
    for h in header_names:
        if h.strip() == "" or re.match(r'^(nan)(_*\d*)?$', h.strip(), flags=re.IGNORECASE):
            cleaned_header_names.append("")  # placeholder
        else:
            cleaned_header_names.append(h)
    df.columns = cleaned_header_names
    # remove truly blank-named columns
    non_blank_cols = [i for i, h in enumerate(df.columns) if str(h).strip() != ""]
    if len(non_blank_cols) == 0:
        # nothing sensible, keep original but dedupe
        df.columns = deduplicate_columns(df.columns)
    else:
        df = df.iloc[:, non_blank_cols]
        df.columns = deduplicate_columns(df.columns)
    # slice data rows after header
    try:
        df = df[header_row + 1:].reset_index(drop=True)
    except Exception:
        df = df.reset_index(drop=True)
    # normalize text cells
    df = df.applymap(normalize_text_cell)
    # drop columns that are still all-NA or all-empty-like
    df = df.dropna(axis=1, how="all")
    # remove hidden columns (Excel)
    df = remove_hidden_columns(df, sheet_name=sheet_name, file_path=file_path)
    # final cleanup of columns that have names like 'nan' after dedupe
    col_keep = [c for c in df.columns if str(c).strip() != "" and not re.match(r'^(nan)(_*\d*)?$', str(c).strip(), flags=re.IGNORECASE)]
    df = df.loc[:, col_keep]
    # coerce numeric columns (years or numeric-looking columns)
    df = coerce_numeric_columns(df)
    # drop columns that are completely empty after coercion
    df = df.dropna(axis=1, how="all")
    return df


def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []
    sheets_to_read = selected_sheets if selected_sheets else xl.sheet_names
    for sheet in sheets_to_read:
        df_raw = xl.parse(sheet, header=None, dtype=object)
        # replace and drop empties
        df_raw = df_raw.replace(["", " ", "\t", "\n"], pd.NA)
        df_raw = df_raw.dropna(axis=0, how="all")
        df_raw = df_raw.dropna(axis=1, how="all")
        if df_raw.empty:
            continue
        df = clean_table(df_raw, sheet_name=sheet, file_path=file_path)
        if not df.empty:
            tables.append(df)
    return tables


def read_pdf_file(file_path):
    all_tables = []
    # camelot
    try:
        camelot_tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
        for t in camelot_tables:
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except Exception:
        pass
    # pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    df = clean_table(pd.DataFrame(table))
                    if not df.empty:
                        all_tables.append(df)
    except Exception:
        pass
    # tabula
    try:
        tab_tables = tabula.read_pdf(file_path, pages="all", multiple_tables=True)
        for t in tab_tables:
            df = clean_table(t)
            if not df.empty:
                all_tables.append(df)
    except Exception:
        pass
    return all_tables


def classify_statement(df):
    text = " ".join(str(x).lower() for x in df.columns.tolist())
    text += " " + " ".join(df.astype(str).fillna("").apply(lambda x: " ".join(x), axis=1).tolist())
    if any(x in text for x in ["balance sheet", "assets", "liabilities", "equity"]):
        return "Balance Sheet"
    if any(x in text for x in ["income", "revenue", "profit", "loss", "p&l"]):
        return "Income Statement"
    if any(x in text for x in ["cash flow", "operating", "investing", "financing"]):
        return "Cash Flow Statement"
    return "Other"


# ---------- Streamlit UI ----------
st.title("📊 Financial Statement Extractor — robust numeric & hidden-col cleanup")
st.write("Uploads Excel/PDF and extracts cleaned tables (removes hidden/ghost columns, coerces number columns).")

uploaded_file = st.file_uploader("Upload PDF or Excel", type=["pdf", "xlsx", "xls"])
if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    ext = os.path.splitext(file_path)[1].lower()
    selected_sheets = None
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        st.subheader("Select sheets to extract")
        selected_sheets = st.multiselect("Choose sheets", options=xl.sheet_names, default=xl.sheet_names)
        if not selected_sheets:
            st.warning("Select at least one sheet")
            st.stop()
    st.info("Extracting and cleaning tables...")
    if ext in [".xlsx", ".xls"]:
        tables = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)
    st.success(f"Extracted {len(tables)} tables")
    classified = {"Balance Sheet": [], "Income Statement": [], "Cash Flow Statement": [], "Other": []}
    for i, df in enumerate(tables, start=1):
        st.subheader(f"Table {i}")
        st.dataframe(df, use_container_width=True)
        classified[classify_statement(df)].append(df)
    st.markdown("## Summary")
    for k, v in classified.items():
        st.write(f"**{k}: {len(v)} tables**")
    excel_file = to_excel(classified)
    st.download_button("Download Extracted Tables (Excel)", data=excel_file,
                       file_name="Financial_Statements_Extracted.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
