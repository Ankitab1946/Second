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

        # Add each table into a separate sheet within the statement group
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

    header_row = df.notnull().mean(axis=1).idxmax()
    df.columns = df.iloc[header_row]
    df = df[header_row + 1:]

    df.reset_index(drop=True, inplace=True)
    df.columns = [str(c).strip() for c in df.columns]

    return df


# ---------------------------------------------------------
# Extract all tables from EXCEL
# ---------------------------------------------------------
def read_excel_file(file_path):
    xl = pd.ExcelFile(file_path)
    tables = []

    for sheet in xl.sheet_names:
        df_raw = xl.parse(sheet, header=None)

        df_raw.dropna(axis=0, how='all', inplace=True)
        df_raw.dropna(axis=1, how='all', inplace=True)

        if df_raw.empty:
            continue

        header_row = df_raw.notnull().mean(axis=1).idxmax()
        df = xl.parse(sheet, header=header_row)

        df.columns = df.columns.fillna(method='ffill')

        tables.append(df)

    return tables


# ---------------------------------------------------------
# Extract all tables from PDF
# ---------------------------------------------------------
def read_pdf_file(file_path):
    all_tables = []

    # Method 1 — Camelot (best for digital PDFs)
    try:
        camelot_tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
        for t in camelot_tables:
            df = clean_table(t.df)
            if not df.empty:
                all_tables.append(df)
    except:
        pass

    # Method 2 — pdfplumber (works for images & text)
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                raw_tables = page.extract_tables()
                for table in raw_tables:
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
# Auto-classify each table into statement type
# ---------------------------------------------------------
def classify_statement(df):
    text = " ".join(str(x).lower() for x in df.columns.tolist())
    text += " " + " ".join(df.astype(str).fillna("").apply(lambda x: " ".join(x), axis=1).tolist())

    if any(keyword in text for keyword in ["balance sheet", "equity", "assets", "liabilities", "net worth"]):
        return "Balance Sheet"

    if any(keyword in text for keyword in ["income", "revenue", "profit", "loss", "p&l", "statement of operations"]):
        return "Income Statement"

    if any(keyword in text for keyword in ["cash flow", "operating", "investing", "financing"]):
        return "Cash Flow Statement"

    return "Other"


# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.title("📊 Financial Statement Extractor (Multi-Table Detection)")
st.write("Upload Annual Reports (PDF/Excel). Extract ALL tables and classify them into: **Balance Sheet**, **Income Statement**, **Cash Flow Statement**, or Others.**")

uploaded_file = st.file_uploader("Upload PDF or Excel", type=["pdf", "xlsx", "xls"])

if uploaded_file:
    file_path = f"temp_{uploaded_file.name}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    ext = os.path.splitext(file_path)[1].lower()

    st.info("⏳ Extracting tables... please wait.")

    # Extract ALL tables
    if ext in [".xlsx", ".xls"]:
        tables = read_excel_file(file_path)
    else:
        tables = read_pdf_file(file_path)

    st.success(f"✔ Extracted {len(tables)} tables!")

    # Prepare buckets
    classified_tables = {
        "Balance Sheet": [],
        "Income Statement": [],
        "Cash Flow Statement": [],
        "Other": []
    }

    # Classify each table
    for idx, df in enumerate(tables, start=1):
        st.markdown(f"### 🔍 Table {idx}")
        st.dataframe(df, use_container_width=True)

        st_type = classify_statement(df)
        classified_tables[st_type].append(df)

    # Show grouping summary
    st.markdown("## 📌 Classified Summary")
    for k, v in classified_tables.items():
        st.write(f"**{k}**: {len(v)} tables")

    # Download button
    excel_file = to_excel(classified_tables)

    st.download_button(
        label="📥 Download All Extracted & Classified Statements (Excel)",
        data=excel_file,
        file_name="Extracted_Financial_Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )