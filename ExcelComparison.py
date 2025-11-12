import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime

st.set_page_config(page_title="GC Excel Comparator", layout="wide")

HEADER = """
# GC Excel Comparator (Old Version)

Compare two GC Excel templates (all tabs) — structural and value differences — and publish a downloadable Excel & HTML report.
"""
st.markdown(HEADER)

st.sidebar.header("Upload files")
file1 = st.sidebar.file_uploader("Upload FIRST Excel file", type=["xls","xlsx"], key="f1")
file2 = st.sidebar.file_uploader("Upload SECOND Excel file", type=["xls","xlsx"], key="f2")

MAX_DIFFS_DISPLAY = st.sidebar.number_input("Max differences rows to include per sheet", min_value=10, max_value=10000, value=1000, step=10)


@st.cache_data
def read_all_sheets(uploaded_file):
    if uploaded_file is None:
        return {}
    try:
        x = pd.read_excel(uploaded_file, sheet_name=None, dtype=object)
        for k, df in x.items():
            df.columns = df.columns.map(str)
        return x
    except Exception as e:
        st.error(f"Failed to read Excel file: {e}")
        return {}


def df_row_hash(df):
    if df is None or df.shape[0] == 0:
        return pd.Series([], dtype=object)
    s = df.fillna("").astype(str).agg("||".join, axis=1)
    return s


def compare_sheets(df_left, df_right, sheet_name, max_diffs=1000):
    summary = {
        "sheet": sheet_name,
        "left_rows": 0,
        "right_rows": 0,
        "left_cols": 0,
        "right_cols": 0,
        "cols_in_left_only": [],
        "cols_in_right_only": [],
        "num_row_added": 0,
        "num_row_removed": 0,
        "num_cell_changed": 0,
    }

    if df_left is None:
        df_left = pd.DataFrame()
    if df_right is None:
        df_right = pd.DataFrame()

    summary["left_rows"] = df_left.shape[0]
    summary["right_rows"] = df_right.shape[0]
    summary["left_cols"] = df_left.shape[1]
    summary["right_cols"] = df_right.shape[1]

    cols_left = list(df_left.columns)
    cols_right = list(df_right.columns)

    summary["cols_in_left_only"] = [c for c in cols_left if c not in cols_right]
    summary["cols_in_right_only"] = [c for c in cols_right if c not in cols_left]

    all_cols = list(pd.Index(cols_left).union(pd.Index(cols_right)))

    left_hash = df_row_hash(df_left[all_cols].reindex(columns=all_cols, fill_value=np.nan)) if df_left.shape[0] > 0 else pd.Series(dtype=object)
    right_hash = df_row_hash(df_right[all_cols].reindex(columns=all_cols, fill_value=np.nan)) if df_right.shape[0] > 0 else pd.Series(dtype=object)

    left_set = set(left_hash)
    right_set = set(right_hash)

    added_hashes = right_set - left_set
    removed_hashes = left_set - right_set

    summary["num_row_added"] = len(added_hashes)
    summary["num_row_removed"] = len(removed_hashes)

    left_map = {h: i for i, h in enumerate(left_hash)}
    right_map = {h: i for i, h in enumerate(right_hash)}

    records = []
    cell_changes = 0

    common_hashes = left_set.intersection(right_set)
    for h in list(common_hashes):
        li = left_map[h]
        ri = right_map[h]
        left_row = df_left.iloc[[li]].reindex(columns=all_cols, fill_value=np.nan).iloc[0]
        right_row = df_right.iloc[[ri]].reindex(columns=all_cols, fill_value=np.nan).iloc[0]
        for col in all_cols:
            lv = left_row.get(col, np.nan)
            rv = right_row.get(col, np.nan)
            lv_s = "" if pd.isna(lv) else str(lv)
            rv_s = "" if pd.isna(rv) else str(rv)
            if lv_s != rv_s:
                records.append({"row_hash": h, "row_index_left": li, "row_index_right": ri, "col": col, "left_value": lv_s, "right_value": rv_s, "status": "changed"})
                cell_changes += 1
                if cell_changes >= max_diffs:
                    break
        if cell_changes >= max_diffs:
            break

    if cell_changes < max_diffs:
        for h in list(removed_hashes):
            li = left_map[h]
            left_row = df_left.iloc[[li]].reindex(columns=all_cols, fill_value=np.nan)
            records.append({"row_hash": h, "row_index_left": li, "row_index_right": np.nan, "col": "<ROW_REMOVED>", "left_value": " | ".join(left_row.fillna("").astype(str).tolist()), "right_value": "", "status": "left_only"})
            if len(records) >= max_diffs:
                break
    if cell_changes + len(records) < max_diffs:
        for h in list(added_hashes):
            ri = right_map[h]
            right_row = df_right.iloc[[ri]].reindex(columns=all_cols, fill_value=np.nan)
            records.append({"row_hash": h, "row_index_left": np.nan, "row_index_right": ri, "col": "<ROW_ADDED>", "left_value": "", "right_value": " | ".join(right_row.fillna("").astype(str).tolist()), "status": "right_only"})
            if len(records) >= max_diffs:
                break

    summary["num_cell_changed"] = cell_changes

    detail_df = pd.DataFrame.from_records(records)
    return summary, detail_df


def build_reports(dict_left, dict_right, max_diffs_per_sheet=1000):
    all_sheets = sorted(set(list(dict_left.keys()) + list(dict_right.keys())))
    summaries = []
    detail_frames = {}

    for s in all_sheets:
        df_l = dict_left.get(s)
        df_r = dict_right.get(s)
        summ, detail = compare_sheets(df_l, df_r, s, max_diffs=max_diffs_per_sheet)
        summaries.append(summ)
        detail_frames[s] = detail

    summary_df = pd.DataFrame(summaries)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        for s, df in detail_frames.items():
            sheet_name_safe = s[:31] if s else 'Sheet'
            try:
                if df is None or df.shape[0] == 0:
                    pd.DataFrame([{'note': 'No differences detected'}]).to_excel(writer, sheet_name=sheet_name_safe, index=False)
                else:
                    df.to_excel(writer, sheet_name=sheet_name_safe, index=False)
            except Exception as e:
                pd.DataFrame([{'error': str(e)}]).to_excel(writer, sheet_name=sheet_name_safe[:28], index=False)
        writer.save()
    excel_buffer.seek(0)

    html_parts = []
    html_parts.append(f"<h1>GC Excel Comparator Report</h1>")
    html_parts.append(f"<p>Generated: {datetime.utcnow().isoformat()} UTC</p>")
    html_parts.append(summary_df.to_html(index=False, classes='summary'))
    for s, df in detail_frames.items():
        html_parts.append(f"<h2>Sheet: {s}</h2>")
        if df is None or df.shape[0] == 0:
            html_parts.append("<p>No differences detected</p>")
        else:
            html_parts.append(df.head(1000).to_html(index=False, classes='detail'))
    html_report = "\n".join(html_parts)
    html_full = f"<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Arial,Helvetica,sans-serif}} table.summary, table.detail{{border-collapse:collapse;width:100%}} table.summary th, table.summary td, table.detail th, table.detail td{{border:1px solid #ccc;padding:6px;text-align:left;font-size:12px}} h1{{color:#222}} h2{{color:#444}}</style></head><body>{html_report}</body></html>"

    return excel_buffer, html_full, summary_df, detail_frames


if file1 is not None and file2 is not None:
    with st.spinner("Reading files..."):
        left_sheets = read_all_sheets(file1)
        right_sheets = read_all_sheets(file2)

    st.success("Files loaded")
    st.write(f"**Left file:** {getattr(file1, 'name', 'uploaded1')} — {len(left_sheets)} sheets")
    st.write(f"**Right file:** {getattr(file2, 'name', 'uploaded2')} — {len(right_sheets)} sheets")

    if st.button("Run comparison"):
        with st.spinner("Comparing sheets — this may take a minute for large files..."):
            excel_buf, html_report, summary_df, detail_frames = build_reports(left_sheets, right_sheets, MAX_DIFFS_DISPLAY)
        st.success("Comparison finished")

        st.subheader("Summary")
        st.dataframe(summary_df)

        sheet_choice = st.selectbox("Select sheet to view details", options=list(detail_frames.keys()))
        if sheet_choice:
            df_detail = detail_frames.get(sheet_choice)
            if df_detail is None or df_detail.shape[0] == 0:
                st.info("No differences detected for this sheet")
            else:
                st.write(f"Showing up to {MAX_DIFFS_DISPLAY} differences for sheet: {sheet_choice}")
                st.dataframe(df_detail)

        st.download_button("Download Excel report (.xlsx)", data=excel_buf.getvalue(), file_name=f"GC_Comparison_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        st.download_button("Download HTML report (.html)", data=html_report, file_name=f"GC_Comparison_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html", mime='text/html')

else:
    st.info("Upload two Excel files (left = older / baseline, right = newer / changed) to start the comparison.")
    st.caption("Designed for GC templates: compares all tabs, structural and value diffs, produces Excel + HTML reports.")

st.markdown("---")
st.caption("Made for GC Excel comparison — classic version without mapping.")
