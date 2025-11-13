import streamlit as st
import pandas as pd
import camelot
import pdfplumber
import tabula
import os
from io import BytesIO

st.set_page_config(page_title="Financial Statement Extractor", layout="wide")

# =========================================================
#  Utility: Create downloadable Excel with all tables
# =========================================================
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


# =========================================================
#  Deduplicate Column Names (Safe for Pandas 2.x+)
# =========================================================
def deduplicate_columns(columns):
    """
    Convert duplicate column names:
    ['Trust Fund', 'Trust Fund'] →
    ['Trust Fund', 'Trust Fund_1']
    """
    new_cols = []
    count = {}

    for col in columns:
        col = str(col).strip()

        if col not in count:
            count[col] = 0
            new_cols.append(col)
        else:
            count[col] += 1
            new_cols.append(f"{col}_{count[col]}")

    return new_cols


# =========================================================
#  INTELLIGENT HEADER DETECTION FOR FINANCIAL TABLES
# =========================================================
def detect_header_row(df):
    """
    Detects header row by:
    - Avoiding rows with high numeric ratio (data rows)
    - Preferring rows with header keywords
    - Considering fullness as a fallback
    """

    header_keywords = [
        "particular", "description", "item", "notes",
        "note", "assets", "liabilities", "equity",
        "year", "fy", "statement", "amount", "total"
    ]

    best_row = None
    best_score = -999999

    for idx, row in df.iterrows():
        row_text = " ".join(str(x).lower() for x in row.values)

        # Skip numeric-heavy rows → data rows
        numeric_ratio = row.apply(lambda x: str(x).replace(".", "", 1).isdigit()).mean()
        if numeric_ratio > 0.5:
            continue

        # Score header keywords
        score = sum(1 for kw in header_keywords if kw in row_text)

        # Bonus for non-null count
        score += row.notnull().sum()

        if score > best_score:
            best_score = score
            best_row = idx

    # Fallback to fullness method
    if best_row is None:
        best_row = df.notnull().mean(axis=1).idxmax()

    return best_row


# =========================================================
#  Clean & Normalize Extracted Tables + Remove NaN columns
# =========================================================
def clean_table(df):
    # Remove completely empty rows/columns first
    df.dropna(axis=0, how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)

    if df.empty:
        return df

    # NEW intelligent header detection
    header_row = detect_header_row(df)

    df.columns = df.iloc[header_row]
    df.columns = deduplicate_columns(df.columns)
    df.columns = [str(c).strip() for c in df.columns]

    # Remove NaN columns (global request)
    df = df.dropna(axis=1, how="all")

    # Get data rows
    df = df[header_row + 1:].reset_index(drop=True)

    # Remove NaN columns again after slicing
    df = df.dropna(axis=1, how="all")

    return df


# =========================================================
#  Extract All Tables from Excel (with sheet selection)
# =========================================================
def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []

    sheets_to_read = selected_sheets if selected_sheets else xl.sheet_names

    for sheet in sheets_to_read:
        df_raw = xl.parse(sheet, header=None)

        # Pre-clean
        df_raw.dropna(axis=0, how="all", inplace=True)
        df_raw.dropna(axis=1, how="all", inplace=True)

        if df_raw.empty:
            continue

        # Clean the table
        df = clean_table(df_raw)
        if not df.empty:
            tables.append(df)

    return tables, xl.sheet_names


# =========================================================
#  Extract All Tables from PDF
# =========================================================
def read_pdf_file(file_path):
    all_tables = []

    # Camelot (digital PDFs)
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
                extracted = page.extract_tables()
                for table in extracted:
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


# =========================================================
#  Classify Financial Statements
# =========================================================
def classify_statement(df):
    """
    Simple keyword-based classifier (fast & effective for financial tables).
    """
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


# =========================================================
#  STREAMLIT UI
# =========================================================
st.title("📊 Intelligent Financial Statement Extractor (PDF / Excel)")
st.write(
    "Extract **all tables**, detect real headers intelligently, "
    "remove empty NaN columns, fix duplicate headers, allow sheet selection, "
    "and classify tables into Balance Sheet, Income Statement, Cash Flow, or Other."
)

uploaded_file = st.file_uploader("Upload PDF or Excel file", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()
    selected_sheets = None

    # Excel → sheet selection UI
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        st.subheader("📄 Select tabs to extract:")
        selected_sheets = st.multiselect(
            "Choose one or more sheets",
            options=xl.sheet_names,
            default=xl.sheet_names
        )

        if not selected_sheets:
            st.warning("Please select at least one tab.")
            st.stop()

    st.info("⏳ Extracting tables using intelligent header detection...")

    # Extract tables
    if ext in [".xlsx", ".xls"]:
        tables, _ = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)

    st.success(f"✔ Extracted {len(tables)} tables successfully")

    # Classification containers
    classified_tables = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    # Display & classify tables
    for idx, df in enumerate(tables, start=1):
        st.subheader(f"🔍 Table {idx}")
        st.dataframe(df, use_container_width=True)

        st_type = classify_statement(df)
        classified_tables[st_type].append(df)

    # Summary
    st.markdown("## 📌 Classification Summary")
    for k, v in classified_tables.items():
        st.write(f"**{k}: {len(v)} table(s)**")

    # Download
    excel_file = to_excel(classified_tables)
    st.download_button(
        label="📥 Download Extracted & Classified Tables (Excel)",
        data=excel_file,
        file_name="Financial_Statements_Extracted.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
