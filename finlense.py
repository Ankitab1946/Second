import streamlit as st
import pandas as pd
import camelot
import pdfplumber
import tabula
import openpyxl
import os
from io import BytesIO

st.set_page_config(page_title="Financial Statement Extractor", layout="wide")

# =====================================================================
# UTIL: Excel Export
# =====================================================================
def to_excel(statement_dict):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for statement, tables in statement_dict.items():
            if len(tables) == 0:
                continue
            for i, df in enumerate(tables, start=1):
                df.to_excel(writer, index=False,
                            sheet_name=f"{statement[:28]}_{i}")

    output.seek(0)
    return output


# =====================================================================
# UTIL: Deduplicate Headers
# =====================================================================
def deduplicate_columns(columns):
    new_cols, count = [], {}
    for col in columns:
        col = str(col).strip()
        if col not in count:
            count[col] = 0
            new_cols.append(col)
        else:
            count[col] += 1
            new_cols.append(f"{col}_{count[col]}")
    return new_cols


# =====================================================================
# DETECT HEADER ROW (Smarter Financial Logic)
# =====================================================================
def detect_header_row(df):
    header_keywords = [
        "particular", "description", "item", "notes", "note",
        "assets", "liabilities", "equity", "year", "fy",
        "statement", "amount", "total"
    ]

    best_row = None
    best_score = -999999

    for idx, row in df.iterrows():
        row_text = " ".join(str(x).lower() for x in row.values)

        # Skip numeric-heavy rows
        numeric_ratio = row.apply(
            lambda x: str(x).replace(".", "", 1).isdigit()).mean()
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


# =====================================================================
# REMOVE HIDDEN / BLANK / GHOST COLUMNS
# =====================================================================
def remove_hidden_columns(df, sheet_name=None, file_path=None):
    if sheet_name is None or file_path is None:
        return df  # For PDFs skip hidden logic

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb[sheet_name]

        # find visible columns from Excel metadata
        visible_cols = []
        for col_cells in ws.columns:
            col_letter = col_cells[0].column_letter
            if ws.column_dimensions[col_letter].hidden is False:
                visible_cols.append(col_letter)

        # restrict df to visible column count
        df = df.iloc[:, :len(visible_cols)]
        return df

    except Exception:
        return df


# =====================================================================
# CLEAN TABLE (NEW VERSION)
# =====================================================================
def clean_table(df, sheet_name=None, file_path=None):
    # Remove plain blanks & whitespace
    df = df.replace(["", " ", "  ", "   ", "\t", "\n"], pd.NA)

    # remove empty rows/columns
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")

    if df.empty:
        return df

    # Detect header row
    header_row = detect_header_row(df)

    df.columns = df.iloc[header_row]
    df.columns = deduplicate_columns(df.columns)
    df.columns = [str(c).strip() for c in df.columns]

    # Remove columns whose header is empty or NaN
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns.astype(str).str.strip() != ""]

    # Slice data rows
    df = df[header_row + 1:].reset_index(drop=True)

    # Clean again
    df = df.replace(["", " ", "  ", "   ", "\t", "\n"], pd.NA)

    # remove columns where ALL values are blank-like
    df = df.dropna(axis=1, how="all")

    # Remove hidden columns from Excel
    df = remove_hidden_columns(df, sheet_name=sheet_name, file_path=file_path)

    # Final drop of empty columns
    df = df.dropna(axis=1, how="all")

    return df


# =====================================================================
# EXCEL EXTRACTOR
# =====================================================================
def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []

    sheets_to_read = selected_sheets if selected_sheets else xl.sheet_names

    for sheet in sheets_to_read:
        df_raw = xl.parse(sheet, header=None)

        df_raw.replace(["", " ", "  ", "   ", "\t"], pd.NA, inplace=True)
        df_raw.dropna(axis=0, how="all", inplace=True)
        df_raw.dropna(axis=1, how="all", inplace=True)

        if df_raw.empty:
            continue

        df = clean_table(df_raw, sheet_name=sheet, file_path=file_path)

        if not df.empty:
            tables.append(df)

    return tables


# =====================================================================
# PDF EXTRACTOR
# =====================================================================
def read_pdf_file(file_path):
    all_tables = []

    # Camelot
    try:
        camelot_tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
        for t in camelot_tables:
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    # pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    df = clean_table(pd.DataFrame(table))
                    if not df.empty:
                        all_tables.append(df)
    except:
        pass

    # Tabula
    try:
        tab_tables = tabula.read_pdf(file_path, pages="all", multiple_tables=True)
        for t in tab_tables:
            df = clean_table(t)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    return all_tables


# =====================================================================
# CLASSIFY FINANCIAL TABLES
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
st.write(
    "This tool extracts ALL financial tables, removes hidden columns, "
    "cleans blank/ghost columns, auto-detects headers, deduplicates columns, "
    "and classifies each table into Balance Sheet / Income Statement / Cash Flow."
)

uploaded_file = st.file_uploader("Upload PDF or Excel", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    selected_sheets = None

    # Allow Excel tab selection
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        st.subheader("📄 Select Excel sheets to extract:")
        selected_sheets = st.multiselect(
            "Choose sheets:",
            options=xl.sheet_names,
            default=xl.sheet_names
        )

        if not selected_sheets:
            st.warning("Select at least one sheet.")
            st.stop()

    st.info("⏳ Extracting and cleaning tables...")

    if ext in [".xlsx", ".xls"]:
        tables = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)

    st.success(f"✔ Extracted {len(tables)} clean tables")

    classified = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    # Display & classify
    for i, df in enumerate(tables, start=1):
        st.subheader(f"🔍 Table {i}")
        st.dataframe(df, use_container_width=True)

        t = classify_statement(df)
        classified[t].append(df)

    # Summary
    st.markdown("## 📌 Classification Summary")
    for k, v in classified.items():
        st.write(f"**{k}: {len(v)} table(s)**")

    # Download Excel
    excel_file = to_excel(classified)
    st.download_button(
        "📥 Download Extracted Tables (Excel)",
        data=excel_file,
        file_name="Financial_Statements_Extracted.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
