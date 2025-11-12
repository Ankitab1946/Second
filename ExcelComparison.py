import streamlit as st
import pandas as pd
import numpy as np
from difflib import get_close_matches
import io
import os
from datetime import datetime
from openpyxl.utils import get_column_letter  # ✅ for Excel-style letters

st.set_page_config(page_title="GC Excel Comparator", layout="wide")

st.title("📊 GC Excel Comparator — Auto-Mapping + Selective Run + Cell-Level Differences + Highlights")

# --- Step 1: Upload Excel Files ---
file1 = st.sidebar.file_uploader("Upload Workbook A", type=["xlsx", "xls"], key="f1")
file2 = st.sidebar.file_uploader("Upload Workbook B", type=["xlsx", "xls"], key="f2")

@st.cache_data
def read_excel_sheets(uploaded_file):
    """Read all sheets from an uploaded Excel file into a dictionary of DataFrames."""
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

    # --- Step 4: Selective Sheet Comparison ---
    st.subheader("🧩 Select Tabs for Comparison")

    # Filter out skipped ones
    available_sheets = edited_mapping.loc[~edited_mapping["Skip Comparison"], "Workbook A Sheet"].tolist()

    # --- Select All / Deselect All toggle ---
    col1, col2 = st.columns([0.15, 0.85])
    with col1:
        toggle_all = st.checkbox("Select All", value=True, key="select_all_toggle")

    if toggle_all:
        selected_sheets = st.multiselect(
            "✅ Choose sheets to compare",
            options=available_sheets,
            default=available_sheets,
            help="Only selected sheets will be compared"
        )
    else:
        selected_sheets = st.multiselect(
            "✅ Choose sheets to compare",
            options=available_sheets,
            default=[],
            help="Only selected sheets will be compared"
        )

    # --- Step 5: Run Comparison ---
    if st.button("🚀 Run Comparison"):
        if not selected_sheets:
            st.warning("⚠️ Please select at least one sheet to compare.")
        else:
            summary_rows = []
            diff_frames = {}
            excel_output = io.BytesIO()

            base_filename = f"{file1_name}_comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

            # --- Compute diffs in memory ---
            for _, row in edited_mapping.iterrows():
                sheetA_name = row["Workbook A Sheet"]
                sheetB_name = row["Workbook B Sheet"]

                # ✅ Skip if not selected
                if sheetA_name not in selected_sheets:
                    st.info(f"⏭️ Skipping sheet '{sheetA_name}'")
                    continue

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

                # Build difference DataFrame
                diff_records = []
                for i, j in zip(*changed_cells):
                    col_name = common_cols[j]
                    try:
                        col_pos = dfA.columns.get_loc(col_name) + 1
                    except Exception:
                        col_pos = j + 1
                    excel_row_num = i + 2  # header is row 1
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

                # Sanitize sheet name
                def sanitize_sheet_name(name):
                    invalid = ['\\', '/', '*', '[', ']', ':', '?']
                    for ch in invalid:
                        name = name.replace(ch, "_")
                    name = name.strip()
                    if len(name) == 0:
                        name = "Sheet"
                    if len(name) > 28:
                        name = name[:28]
                    return name

                sheet_name_safe = sanitize_sheet_name(f"{sheetA_name}_Diff")
                base_safe = sheet_name_safe
                idx = 1
                while sheet_name_safe in diff_frames:
                    sheet_name_safe = f"{base_safe[:25]}_{idx}"
                    idx += 1

                diff_frames[sheet_name_safe] = diff_df

                summary_rows.append({
                    "Sheet A": sheetA_name,
                    "Sheet B": sheetB_name,
                    "Extra Columns in A": ", ".join(sorted(extra_cols_A)) if extra_cols_A else "None",
                    "Extra Columns in B": ", ".join(sorted(extra_cols_B)) if extra_cols_B else "None",
                    "Row Difference": len(dfA) - len(dfB),
                    "Changed Cells": num_changes,
                    "Drilldown Sheet": sheet_name_safe
                })

            # --- Write Excel file: Summary first, then details ---
            with pd.ExcelWriter(excel_output, engine="xlsxwriter") as writer:
                workbook = writer.book
                link_fmt = workbook.add_format({'font_color': 'blue', 'underline': 1})
                highlight_fmt = workbook.add_format({"bg_color": "#FFF59D", "font_color": "#000000"})

                summary_df_full = pd.DataFrame(summary_rows)
                display_cols = ["Sheet A", "Sheet B", "Extra Columns in A", "Extra Columns in B", "Row Difference", "Changed Cells"]
                summary_display = summary_df_full[display_cols]

                # Write summary
                summary_display.to_excel(writer, sheet_name="Summary", index=False, startcol=1)
                worksheet_summary = writer.sheets["Summary"]
                worksheet_summary.set_column(0, 0, 18)
                worksheet_summary.set_column(1, len(display_cols), 25)
                worksheet_summary.write(0, 0, "Drilldown")

                # Add "Go to Diff" hyperlinks
                for idx, rec in enumerate(summary_df_full.itertuples(index=False), start=1):
                    drill_sheet = getattr(rec, "Drilldown Sheet", summary_df_full.iloc[idx-1]["Drilldown Sheet"])
                    formula = f'=HYPERLINK("#\'{drill_sheet}\'!A1","Go to Diff")'
                    worksheet_summary.write_formula(idx, 0, formula, link_fmt)

                # --- Write detail sheets ---
                for sheet_name_safe, diff_df in diff_frames.items():
                    if diff_df is None or diff_df.empty:
                        pd.DataFrame([{"Status": "No Differences Found"}]).to_excel(writer, index=False, sheet_name=sheet_name_safe)
                    else:
                        diff_df.to_excel(writer, index=False, sheet_name=sheet_name_safe, startrow=2)
                        worksheet = writer.sheets[sheet_name_safe]

                        # Add "Back to Summary" link
                        back_link = '=HYPERLINK("#Summary!A1","Back to Summary")'
                        worksheet.write_formula(0, 0, back_link, link_fmt)

                        worksheet.set_column(0, diff_df.shape[1]-1, 20)
                        for r in range(3, len(diff_df) + 3):
                            worksheet.set_row(r, None, highlight_fmt)

            excel_output.seek(0)

            # --- Display summary and download button ---
            st.subheader("📋 Comparison Summary")
            st.dataframe(pd.DataFrame(summary_rows).drop(columns=["Drilldown Sheet"], errors="ignore"))

            st.download_button(
                label="📥 Download Highlighted Comparison Report",
                data=excel_output.getvalue(),
                file_name=base_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
