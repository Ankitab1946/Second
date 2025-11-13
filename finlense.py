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
            if len(tables) == 0:
                continue
            for i, df in enumerate(tables, start=1):
                sheet_name = f"{statement[:28]}_{i}"
                df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output


# =====================================================================
# CLEAN DUPLICATE COLUMN NAMES
# =====================================================================
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


# =====================================================================
# HEADER DETECTION LOGIC
# =====================================================================
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

        # skip numeric-heavy rows
        numeric_ratio = row.apply(
            lambda x: str(x).replace(",", "").replace(" ", "")
            .replace("\u00A0", "").replace(".", "", 1)
            .lstrip("-").isdigit()
        ).mean()

        if numeric_ratio > 0.5:
            continue

        # score keywords + non-null cells
        score = sum(1 for kw in header_keywords if kw in row_text)
        score += row.notnull().sum()

        if score > best_score:
            best_score = score
            best_row = idx

    if best_row is None:
        best_row = df.notnull().mean(axis=1).idxmax()

    return best_row


# =====================================================================
# REMOVE EXCEL HIDDEN/NARROW-WIDTH COLUMNS
# =====================================================================
def remove_blank_width_columns(df, sheet_name, file_path):
    if sheet_name is None or file_path is None:
        return df

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb[sheet_name]

        # get column letters in order
        col_letters = [col[0].column_letter for col in ws.columns]
        keep_indices = []

        for i, col_letter in enumerate(col_letters):
            dim = ws.column_dimensions.get(col_letter)
            width = None

            if dim and dim.width is not None:
                width = dim.width
            else:
                width = ws.column_dimensions.defaultColWidth

            # remove narrow / blank columns (width <= 2)
            if width and width > 2:
                keep_indices.append(i)

        if keep_indices:
            df = df.iloc[:, keep_indices]
        return df
    except:
        return df


# =====================================================================
# CLEAN NUMERIC CELLS (%, parentheses, n.a.)
# =====================================================================
def clean_numeric_value(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    s = s.replace("\u00A0", "").replace(",", "")

    # convert (123) -> -123
    if re.fullmatch(r"\(\s*[\d\.]+\s*\)", s):
        s = "-" + s.strip("()")

    # convert percentages
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except:
            return pd.NA

    # "n.a", "na", "-" treated as NA
    if s.lower() in ["n.a.", "na", "n.a", "-", ""]:
        return pd.NA

    try:
        return float(s)
    except:
        return x


# =====================================================================
# CLEAN TABLE (CORE FUNCTION)
# =====================================================================
def clean_table(df, sheet_name=None, file_path=None):
    # remove whitespace-like garbage
    df = df.replace(["", " ", "\t", "\n", "\r", "\x00", "—", "–", "−"], pd.NA)

    # drop fully empty rows/columns
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")

    if df.empty:
        return df

    # detect header
    header_row = detect_header_row(df)
    raw_headers = df.iloc[header_row].fillna("").astype(str).str.strip()

    # remove nan-looking headers
    cleaned_headers = [
        "" if re.fullmatch(r"(nan|nan_\d*|none)?", h, re.IGNORECASE) else h
        for h in raw_headers
    ]

    df.columns = deduplicate_columns(cleaned_headers)

    # remove columns with blank header
    df = df.loc[:, [c for c in df.columns if c.strip() != ""]]

    # slice data rows
    df = df[(header_row + 1):].reset_index(drop=True)

    # normalize cells
    df = df.applymap(lambda x: pd.NA if pd.isna(x) or str(x).strip() in ["", "NaN"] else x)

    # drop empty columns again
    df = df.dropna(axis=1, how="all")

    # remove blank-width Excel columns
    df = remove_blank_width_columns(df, sheet_name, file_path)

    # last cleanup
    df = df.dropna(axis=1, how="all")

    # clean numeric cells (% + numbers)
    df = df.applymap(clean_numeric_value)

    # drop all-empty columns
    df = df.dropna(axis=1, how="all")

    return df


# =====================================================================
# EXCEL READER
# =====================================================================
def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []
    sheets_to_read = selected_sheets if selected_sheets else xl.sheet_names

    for sheet in sheets_to_read:
        df_raw = xl.parse(sheet, header=None, dtype=object)
        df_raw = df_raw.replace(["", " ", "\t", "\n"], pd.NA)
        df_raw = df_raw.dropna(axis=0, how="all")
        df_raw = df_raw.dropna(axis=1, how="all")

        if df_raw.empty:
            continue

        df = clean_table(df_raw, sheet_name=sheet, file_path=file_path)

        if not df.empty:
            tables.append(df)

    return tables


# =====================================================================
# PDF READER
# =====================================================================
def read_pdf_file(file_path):
    all_tables = []

    # Camelot
    try:
        tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
        for t in tables:
            df = clean_table(t.df)
            if not df.empty: all_tables.append(df)
    except:
        pass

    # pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for tb in page.extract_tables():
                    df = clean_table(pd.DataFrame(tb))
                    if not df.empty: all_tables.append(df)
    except:
        pass

    # Tabula
    try:
        tables = tabula.read_pdf(file_path, pages="all", multiple_tables=True)
        for t in tables:
            df = clean_table(t)
            if not df.empty: all_tables.append(df)
    except:
        pass

    return all_tables


# =====================================================================
# CLASSIFY STATEMENT
# =====================================================================
def classify_statement(df):
    text = " ".join(str(x).lower() for x in df.columns.tolist())
    text += " " + " ".join(
        df.astype(str).fillna("").apply(lambda x: " ".join(x), axis=1).tolist()
    )

    if any(x in text for x in ["balance sheet", "assets", "liabilities", "equity"]):
        return "Balance Sheet"
    if any(x in text for x in ["income", "revenue", "profit", "loss", "p&l"]):
        return "Income Statement"
    if any(x in text for x in ["cash flow", "operating", "investing", "financing"]):
        return "Cash Flow Statement"
    return "Other"


# =====================================================================
# STREAMLIT UI
# =====================================================================
st.title("📊 Intelligent Financial Statement Extractor (PDF / Excel)")
st.write("""
This version removes **all blank-width Excel columns**, extracts **all tables**, 
cleans headers, converts % and (123) formats, and classifies tables.
""")

uploaded_file = st.file_uploader("Upload PDF or Excel", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    selected_sheets = None
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        st.subheader("Select Excel Sheets:")
        selected_sheets = st.multiselect(
            "Sheets",
            options=xl.sheet_names,
            default=xl.sheet_names
        )
        if not selected_sheets:
            st.warning("Please select at least one sheet")
            st.stop()

    st.info("Extracting tables... please wait")

    if ext in [".xlsx", ".xls"]:
        tables = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)

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
    for k, v in classified.items():
        st.write(f"**{k}: {len(v)} tables**")

    excel_file = to_excel(classified)
    st.download_button(
        "📥 Download Extracted Tables (Excel)",
        data=excel_file,
        file_name="Extracted_Financial_Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
