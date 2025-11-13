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
    writer = pd.ExcelWriter(output, engine='openpyxl')

    for statement, tables in statement_dict.items():
        if len(tables) == 0:
            continue

        for i, df in enumerate(tables, start=1):
            sheet_name = f"{statement[:28]}_{i}"
            df.to_excel(writer, index=False, sheet_name=sheet_name)

    writer.save()
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
#  Clean & Normalize Extracted Tables
# =========================================================
def clean_table(df):
    df.dropna(axis=0, how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)

    if df.empty:
        return df

    # Auto-determine header
    header_row = df.notnull().mean(axis=1).idxmax()

    df.columns = df.iloc[header_row]

    # Deduplicate column names for safety
    df.columns = deduplicate_columns(df.columns)

    df = df[header_row + 1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]

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

        df_raw.dropna(axis=0, how="all", inplace=True)
        df_raw.dropna(axis=1, how="all", inplace=True)

        if df_raw.empty:
            continue

        header_row = df_raw.notnull().mean(axis=1).idxmax()
        df = xl.parse(sheet, header=header_row)

        # Forward fill headers safely
        df.columns = pd.Series(df.columns).fillna(method="ffill")

        # Deduplicate column names
        df.columns = deduplicate_columns(df.columns)

        tables.append(df)

    return tables, xl.sheet_names


# =========================================================
#  Extract All Tables from PDF
# =========================================================
def read_pdf_file(file_path):
    all_tables = []

    # Camelot extraction (digital PDFs)
    try:
        camelot_tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
        for t in camelot_tables:
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    # pdfplumber extraction
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

    # Tabula extraction
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
    Simple keyword-based classifier (can be upgraded to AI version).
    """
    text = " ".join(str(x).lower() for x in df.columns.tolist())
    text += " " + " ".join(
        df.astype(str).fillna("").apply(lambda x: " ".join(x), axis=1).tolist()
    )

    if any(x in text for x in ["balance sheet", "equity", "assets", "liabilities"]):
        return "Balance Sheet"

    if any(x in text for x in ["income", "revenue", "profit", "loss", "p&l"]):
        return "Income Statement"

    if any(x in text for x in ["cash flow", "operating", "investing", "financing"]):
        return "Cash Flow Statement"

    return "Other"


# =========================================================
#  STREAMLIT UI
# =========================================================
st.title("📊 Financial Statement Extractor")
st.write(
    "Uploads PDFs or Excel files, extracts **all tables**, cleans them, "
    "handles **duplicate headers**, allows **sheet selection**, and "
    "classifies the tables into Balance Sheet, Income Statement, Cash Flow, or Other."
)

uploaded_file = st.file_uploader("Upload PDF or Excel file", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    selected_sheets = None

    # Excel sheet selection UI
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        st.subheader("📄 Select sheets to extract:")
        selected_sheets = st.multiselect(
            "Choose one or more sheets",
            options=xl.sheet_names,
            default=xl.sheet_names
        )

        if len(selected_sheets) == 0:
            st.warning("Please select at least one tab.")
            st.stop()

    st.info("⏳ Extracting tables... please wait.")

    # Extract tables
    if ext in [".xlsx", ".xls"]:
        tables, _ = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)

    st.success(f"✔ Extracted {len(tables)} tables!")

    # Classification buckets
    classified_tables = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    # Display and classify all tables
    for idx, df in enumerate(tables, start=1):
        st.markdown(f"### 🔍 Table {idx}")
        st.dataframe(df, use_container_width=True)

        st_type = classify_statement(df)
        classified_tables[st_type].append(df)

    # Summary
    st.markdown("## 📌 Classification Summary")
    for name, group in classified_tables.items():
        st.write(f"**{name}: {len(group)} tables**")

    # Download button
    excel_file = to_excel(classified_tables)

    st.download_button(
        label="📥 Download Extracted & Classified Tables (Excel)",
        data=excel_file,
        file_name="Extracted_Financial_Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )