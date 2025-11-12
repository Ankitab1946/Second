import streamlit as st
import pandas as pd
from difflib import get_close_matches

st.set_page_config(page_title="GC Excel Comparator", layout="wide")

st.title("📊 GC Excel Comparator with Auto-Mapping and Skip Option")

# --- Step 1: File Upload ---
file1 = st.sidebar.file_uploader("Upload Workbook A", type=["xlsx", "xls"], key="f1")
file2 = st.sidebar.file_uploader("Upload Workbook B", type=["xlsx", "xls"], key="f2")

@st.cache_data
def read_excel_sheets(uploaded_file):
    try:
        return pd.read_excel(uploaded_file, sheet_name=None, dtype=str)
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        return {}

# --- Step 2: Read Sheets ---
if file1 and file2:
    sheetsA = read_excel_sheets(file1)
    sheetsB = read_excel_sheets(file2)

    st.success(f"✅ Loaded {len(sheetsA)} sheets from Workbook A and {len(sheetsB)} from Workbook B")

    # --- Step 3: Auto Map Sheet Names ---
    mapping_data = []
    for sheetA in sheetsA.keys():
        best_match = get_close_matches(sheetA, sheetsB.keys(), n=1, cutoff=0.6)
        mapped_to = best_match[0] if best_match else None
        mapping_data.append({
            "Workbook A Sheet": sheetA,
            "Workbook B Sheet": mapped_to if mapped_to else "❌ No Match Found",
            "Skip Comparison": False
        })

    mapping_df = pd.DataFrame(mapping_data)

    st.subheader("🔗 Sheet Auto-Mapping")
    edited_mapping = st.data_editor(mapping_df, num_rows="dynamic", key="map_editor")

    # --- Step 4: Run Comparison ---
    if st.button("Run Comparison"):
        results_summary = []
        for _, row in edited_mapping.iterrows():
            if row["Skip Comparison"]:
                st.info(f"⏭️ Skipping sheet '{row['Workbook A Sheet']}'")
                continue

            sheetA = row["Workbook A Sheet"]
            sheetB = row["Workbook B Sheet"]

            if sheetB not in sheetsB:
                st.warning(f"⚠️ Sheet '{sheetB}' not found in Workbook B — skipped")
                continue

            dfA = sheetsA.get(sheetA)
            dfB = sheetsB.get(sheetB)

            # Compare structure
            diff_cols = set(dfA.columns) ^ set(dfB.columns)
            diff_rows = len(dfA) - len(dfB)

            results_summary.append({
                "Sheet A": sheetA,
                "Sheet B": sheetB,
                "Extra Columns": ", ".join(diff_cols) if diff_cols else "None",
                "Row Difference": diff_rows
            })

        result_df = pd.DataFrame(results_summary)
        st.subheader("📋 Comparison Summary")
        st.dataframe(result_df)

        # --- Step 5: Download Report ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Summary")
        st.download_button(
            "📥 Download Comparison Report",
            data=output.getvalue(),
            file_name="comparison_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("⬆️ Please upload both workbooks to begin.")
