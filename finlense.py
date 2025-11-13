import streamlit as st
import pandas as pd
import camelot
import pdfplumber
import tabula
import os
from io import BytesIO

st.set_page_config(page_title="Financial Statement Extractor", layout="wide")

# ---------------------------------------------------------
# Utility: Convert grouped tables into downloadable Excel
# ---------------------------------------------------------
def to_excel(statement_dict):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')

    for statement, tables in statement_dict.items():
        if len(tables) == 0:
            continue

        # Each table becomes its own sheet
        for i, df in enumerate(tables, start=1):
            sheet_name = f"{statement[:28]}_{i}"
            df.to_excel(writer, index=False, sheet_name=sheet_name)

    writer.save()
    output.seek(0)
    return output


# ---------------------------------------------------------
# Clean extracted tables
# ---------------------------------------------------------
def clean_table(df):
    df.dropna(axis=0, how='all', inplace=True)
    df.dropna(axis=1, how='all', inplace=True)

    if df.empty:
        return df

    # Auto detect header row
    header_row = df.notnull().mean(axis=1).idxmax()

    df.columns = df.iloc[header_row]
    df = df[header_row + 1:]

    df.reset_index(drop=True, inplace=True)
    df.columns = [str(c).strip() for c in df.columns]

    return df


# ---------------------------------------------------------
# Extract ALL tables from Excel with sheet selection
# ---------------------------------------------------------
def read_excel_file(file_path, selected_sheets=None):
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    tables = []

    sheets_to_read = selected_sheets if selected_sheets else xl.sheet_names

    for sheet in sheets_to_read:
        df_raw = xl.parse(sheet, header=None)

        df_raw.dropna(axis=0, how='all', inplace=True)
        df_raw.dropna(axis=1, how='all', inplace=True)

        if df_raw.empty:
            continue

        header_row = df_raw.notnull().mean(axis=1).idxmax()
        df = xl.parse(sheet, header=header_row)

        # FIX: fillna for header must be done via Series
        df.columns = pd.Series(df.columns).fillna(method="ffill")

        tables.append(df)

    return tables, xl.sheet_names


# ---------------------------------------------------------
# Extract ALL tables from PDF
# ---------------------------------------------------------
def read_pdf_file(file_path):
    all_tables = []

    # Method 1 — Camelot for digital PDFs
    try:
        camelot_tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
        for t in camelot_tables:
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    # Method 2 — pdfplumber
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

    # Method 3 — Tabula
    try:
        tab_tables = tabula.read_pdf(file_path, pages="all", multiple_tables=True)
        for t in tab_tables:
            df = clean_table(t)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    return all_tables


# ---------------------------------------------------------
# Classify table by financial statement type
# ---------------------------------------------------------
def classify_statement(df):
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


# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.title("📊 Financial Statement Extractor (Multi-Table + Sheet Selection)")
st.write(
    "Upload PDF or Excel files. This app extracts **ALL tables**, cleans them, and classifies them into "
    "**Balance Sheet**, **Income Statement**, **Cash Flow Statement**, or **Other**."
)

uploaded_file = st.file_uploader("Upload PDF or Excel", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    selected_sheets = None

    # Excel: show sheet selection
    if ext in [".xlsx", ".xls"]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        st.subheader("📄 Select sheets to extract:")
        selected_sheets = st.multiselect(
            "Choose sheet(s)",
            options=xl.sheet_names,
            default=xl.sheet_names
        )

        if len(selected_sheets) == 0:
            st.warning("Please select at least one sheet to continue.")
            st.stop()

    st.info("⏳ Extracting and classifying tables...")

    # Extract tables
    if ext in [".xlsx", ".xls"]:
        tables, all_sheets = read_excel_file(file_path, selected_sheets)
    else:
        tables = read_pdf_file(file_path)

    st.success(f"✔ Extracted {len(tables)} tables!")

    # Prepare classification buckets
    classified_tables = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    # Show tables and classify
    for idx, df in enumerate(tables, start=1):
        st.markdown(f"### 🔍 Table {idx}")
        st.dataframe(df, use_container_width=True)

        st_type = classify_statement(df)
        classified_tables[st_type].append(df)

    # Summary
    st.markdown("## 📌 Classification Summary")
    for k, v in classified_tables.items():
        st.write(f"**{k}**: {len(v)} tables detected")

    # Download button
    excel_file = to_excel(classified_tables)

    st.download_button(
        label="📥 Download All Classified Tables (Excel)",
        data=excel_file,
        file_name="Extracted_Financial_Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )