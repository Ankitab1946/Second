import streamlit as st
import pandas as pd
import numpy as np
from difflib import get_close_matches
import io

st.set_page_config(page_title="GC Excel Comparator", layout="wide")

st.title("📊 GC Excel Comparator — Auto-Mapping + Cell-Level Differences")

# --- Step 1: Upload Excel Files ---
file1 = st.sidebar.file_uploader("Upload Workbook A", type=["xlsx", "xls"], key="f1")
file2 = st.sidebar.file_uploader("Upload Workbook B", type=["xlsx", "xls"], key="f2")

@st.cache_data
def read_excel_sheets(uploaded_file):
    try:
        return pd.read_excel(uploaded_file, sheet_name=None, dtype=str)
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        return {}

# --- Step 2: Load Workbooks ---
if file1 and file2:
    sheetsA = read_excel_sheets(file1)
    sheetsB = read_excel_sheets(file2)
    st.success(f"✅ Loaded {len(sheetsA)} sheets from Workbook A and {len(sheetsB)} from Workbook B")

    # --- Step 3: Auto-Map Sheets ---
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

    st.subheader("🔗 Auto-Mapping of Sheets")
    edited_mapping = st.data_editor(mapping_df, num_rows="dynamic", key="map_editor")

    # --- Step 4: Comparison Logic ---
    if st.button("🚀 Run Comparison"):
        summary_rows = []
        excel_output = io.BytesIO()

        with pd.ExcelWriter(excel_output, engine="xlsxwriter") as writer:
            for _, row in edited_mapping.iterrows():
                if row["Skip Comparison"]:
                    st.info(f"⏭️ Skipping sheet '{row['Workbook A Sheet']}'")
                    continue

                sheetA_name = row["Workbook A Sheet"]
                sheetB_name = row["Workbook B Sheet"]

                if sheetB_name not in sheetsB:
                    st.warning(f"⚠️ Sheet '{sheetB_name}' not found in Workbook B — skipped")
                    continue

                dfA = sheetsA[sheetA_name].fillna("")
                dfB = sheetsB[sheetB_name].fillna("")

                # Align column sets
                common_cols = sorted(list(set(dfA.columns).intersection(set(dfB.columns))))
                extra_cols_A = list(set(dfA.columns) - set(dfB.columns))
                extra_cols_B = list(set(dfB.columns) - set(dfA.columns))

                # Truncate to same row count for cell-by-cell comparison
                min_rows = min(len(dfA), len(dfB))
                dfA_common = dfA[common_cols].head(min_rows).reset_index(drop=True)
                dfB_common = dfB[common_cols].head(min_rows).reset_index(drop=True)

                # Compare cell values
                diff_mask = dfA_common.ne(dfB_common)
                changed_cells = np.where(diff_mask)
                num_changes = len(changed_cells[0])

                # Build diff report
                diff_records = []
                for i, j in zip(*changed_cells):
                    diff_records.append({
                        "Row": i + 1,
                        "Column": common_cols[j],
                        "Value in Workbook A": dfA_common.iat[i, j],
                        "Value in Workbook B": dfB_common.iat[i, j]
                    })
                diff_df = pd.DataFrame(diff_records)

                # Write per-sheet diff to Excel
                sheet_name_safe = f"{sheetA_name[:28]}_Diff"
                if not diff_df.empty:
                    diff_df.to_excel(writer, index=False, sheet_name=sheet_name_safe)
                else:
                    pd.DataFrame([{"Status": "No Differences Found"}]).to_excel(writer, index=False, sheet_name=sheet_name_safe)

                # Collect summary info
                summary_rows.append({
                    "Sheet A": sheetA_name,
                    "Sheet B": sheetB_name,
                    "Extra Columns in A": ", ".join(extra_cols_A) if extra_cols_A else "None",
                    "Extra Columns in B": ", ".join(extra_cols_B) if extra_cols_B else "None",
                    "Row Difference": len(dfA) - len(dfB),
                    "Changed Cells": num_changes
                })

            # --- Summary Sheet ---
            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_excel(writer, index=False, sheet_name="Summary")

        st.subheader("📋 Comparison Summary")
        st.dataframe(summary_df)

        # --- Step 5: Download Report ---
        st.download_button(
            label="📥 Download Detailed Comparison Report",
            data=excel_output.getvalue(),
            file_name=f"GC_Comparison_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("⬆️ Please upload both workbooks to begin.")
