import streamlit as st
import pandas as pd
import numpy as np
from difflib import get_close_matches
import io
import os
from datetime import datetime
from openpyxl.utils import get_column_letter  # ✅ for Excel-style letters

st.set_page_config(page_title="GC Excel Comparator", layout="wide")

st.title("📊 GC Excel Comparator — Auto-Mapping + Cell-Level Differences + Highlights")

# --- Step 1: Upload Excel Files ---
file1 = st.sidebar.file_uploader("Upload Workbook A", type=["xlsx", "xls"], key="f1")
file2 = st.sidebar.file_uploader("Upload Workbook B", type=["xlsx", "xls"], key="f2")

@st.cache_data
def read_excel_sheets(uploaded_file):
    try:
        df_dict = pd.read_excel(uploaded_file, sheet_name=None, dtype=str, header=0)
        cleaned = {}
        for sheet_name, df in df_dict.items():
            df.columns = [
                c if not str(c).startswith("Unnamed") else f"Unnamed_{i+1}"
                for i, c in enumerate(df.columns)
            ]
            cleaned[sheet_name] = df
        return cleaned
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        return {}

# --- Step 2: Load Workbooks ---
if file1 and file2:
    sheetsA = read_excel_sheets(file1)
    sheetsB = read_excel_sheets(file2)

    file1_name = os.path.splitext(file1.name)[0]
    file2_name = os.path.splitext(file2.name)[0]

    st.success(f"✅ Loaded {len(sheetsA)} sheets from **{file1.name}** and {len(sheetsB)} from **{file2.name}**")

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

    # Build output file name
    base_filename = f"{file1_name}_comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    with pd.ExcelWriter(excel_output, engine="xlsxwriter") as writer:
        workbook = writer.book

        # Define highlight format
        highlight_fmt = workbook.add_format({
            "bg_color": "#FFF59D",  # light yellow
            "font_color": "#000000"
        })

        # We'll write detail sheets first, store their names and summary info
        sheet_summaries = []

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

            # Align row count
            max_rows = max(len(dfA), len(dfB))
            dfA = dfA.reindex(range(max_rows)).fillna("")
            dfB = dfB.reindex(range(max_rows)).fillna("")

            dfA_common = dfA[common_cols].reset_index(drop=True)
            dfB_common = dfB[common_cols].reset_index(drop=True)

            # Compare cell values
            diff_mask = dfA_common.ne(dfB_common)
            changed_cells = np.where(diff_mask)
            num_changes = len(changed_cells[0])

            # --- ✅ Build difference report (Row + Column numbers + Excel letters) ---
            diff_records = []
            for i, j in zip(*changed_cells):
                col_name = common_cols[j]
                try:
                    col_pos = dfA.columns.get_loc(col_name) + 1
                except Exception:
                    col_pos = j + 1  # fallback

                excel_row_num = i + 2
                col_letter = get_column_letter(col_pos)

                diff_records.append({
                    "Row Number": excel_row_num,
                    "Column Number": col_pos,
                    "Column Letter": col_letter,
                    "Column Name": col_name,
                    "Workbook A Value": dfA_common.iat[i, j],
                    "Workbook B Value": dfB_common.iat[i, j]
                })
            diff_df = pd.DataFrame(diff_records)

            # --- Write sheet-wise report ---
            sheet_name_safe = f"{sheetA_name[:28]}_Diff"
            if diff_df.empty:
                pd.DataFrame([{"Status": "No Differences Found"}]).to_excel(writer, index=False, sheet_name=sheet_name_safe)
            else:
                diff_df.to_excel(writer, index=False, sheet_name=sheet_name_safe)
                worksheet = writer.sheets[sheet_name_safe]
                worksheet.set_column("A:G", 25)
                for r in range(1, len(diff_df) + 1):
                    worksheet.set_row(r, None, highlight_fmt)

            # store sheet summary info
            sheet_summaries.append({
                "Sheet A": sheetA_name,
                "Sheet B": sheetB_name,
                "Extra Columns in A": ", ".join(extra_cols_A) if extra_cols_A else "None",
                "Extra Columns in B": ", ".join(extra_cols_B) if extra_cols_B else "None",
                "Row Difference": len(dfA) - len(dfB),
                "Changed Cells": num_changes,
                "Drilldown Sheet": sheet_name_safe
            })

        # --- ✅ Summary Sheet (as FIRST TAB with hyperlinks) ---
        summary_df = pd.DataFrame(sheet_summaries)
        summary_df.insert(0, "Drilldown Link", [
            f'=HYPERLINK("#{s["Drilldown Sheet"]}!A1","Go to Diff")' for _, s in summary_df.iterrows()
        ])

        summary_df.to_excel(writer, index=False, sheet_name="Summary", startrow=0)

        # Move "Summary" sheet to first position
        worksheet_summary = writer.sheets["Summary"]
        worksheet_summary.set_column("A:H", 25)

        # Apply hyperlink formatting
        link_fmt = workbook.add_format({'font_color': 'blue', 'underline': 1})
        for idx in range(1, len(summary_df) + 1):
            worksheet_summary.write_formula(f"A{idx+1}", summary_df.iloc[idx-1, 0], link_fmt)

    # --- Step 5: Display & Download ---
    st.subheader("📋 Comparison Summary")
    st.dataframe(summary_df.drop(columns=["Drilldown Link", "Drilldown Sheet"], errors="ignore"))

    st.download_button(
        label="📥 Download Highlighted Comparison Report",
        data=excel_output.getvalue(),
        file_name=base_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
