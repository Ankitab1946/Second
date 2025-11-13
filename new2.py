import streamlit as st
import pandas as pd
import numpy as np
import io
from difflib import get_close_matches
import matplotlib.pyplot as plt

st.set_page_config(page_title="Financials Comparator", layout="wide")
st.title("📊 Financials.xlsx ↔ Financials_anotherView.xlsx Comparator (Fixed)")

# -----------------------
# Utilities
# -----------------------
def drop_blank_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop columns that are entirely blank (NaN or empty/whitespace strings).
    Works for mixed dtypes.
    """
    keep_cols = []
    for col in df.columns:
        series = df[col]
        # If all values are NaN -> drop
        if series.isna().all():
            continue
        # If after filling NaN with '' and stripping, all values are empty -> drop
        filled = series.fillna("").astype(str).str.strip()
        if (filled == "").all():
            continue
        keep_cols.append(col)
    return df.loc[:, keep_cols]

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

# -----------------------
# Upload both files
# -----------------------
col1, col2 = st.columns(2)
with col1:
    fin_file = st.file_uploader("Upload Financials.xlsx", type=["xlsx", "xls"])
with col2:
    map_file = st.file_uploader("Upload Financials_anotherView.xlsx", type=["xlsx", "xls"])

if fin_file and map_file:
    # -----------------------
    # Load Financials.xlsx
    # -----------------------
    fin_xls = pd.ExcelFile(fin_file)
    selected_tab = st.selectbox("Select sheet from Financials.xlsx", fin_xls.sheet_names)

    raw_fin = pd.read_excel(fin_file, sheet_name=selected_tab, header=None)

    # Remove blank columns BEFORE building MultiIndex
    raw_fin = drop_blank_columns(raw_fin)

    # Make sure there are at least 1 header row
    if raw_fin.shape[0] < 1:
        st.error("Selected sheet in Financials.xlsx is empty or malformed.")
        st.stop()

    # We assume top 3 rows are header levels if present, otherwise adapt
    n_header_rows = min(3, raw_fin.shape[0] - 1)  # leave at least 1 data row
    header_rows = raw_fin.iloc[0:n_header_rows, :]

    data_start_row = n_header_rows
    fin_data = raw_fin.iloc[data_start_row:, :].reset_index(drop=True)

    # If header_rows has fewer than 3 rows, pad with empty strings so MultiIndex lengths are equal
    # Build arrays for MultiIndex with length = n_header_rows (we will use n_header_rows levels)
    header_arrays = []
    for r in range(n_header_rows):
        header_arrays.append(header_rows.iloc[r, :].fillna("").astype(str).str.strip().tolist())

    # If header_rows < 3, pad arrays to length 3 for consistency (but code will adapt)
    # Use MultiIndex if there are multiple header rows, else single level columns
    try:
        if len(header_arrays) >= 2:
            fin_cols = pd.MultiIndex.from_arrays(header_arrays)
        else:
            fin_cols = header_rows.iloc[0, :].fillna("").astype(str).str.strip().tolist()
    except Exception:
        # Fallback to simple column names
        fin_cols = header_rows.iloc[0, :].fillna("").astype(str).str.strip().tolist()

    # Create df_fin
    df_fin = pd.DataFrame(fin_data.values, columns=fin_cols)

    # Determine the identifier column (vertical labels). Usually the first column is that.
    id_col = df_fin.columns[0]
    # rename id_col to a consistent name for convenience, but keep original columns too
    df_fin = df_fin.rename(columns={id_col: "Section"})

    # Drop duplicate columns if any
    df_fin = df_fin.loc[:, ~df_fin.columns.duplicated()]

    # Now melt. For var_name, we want column level names.
    # If df_fin has MultiIndex columns, pandas will represent them differently;
    # but since we renamed first col to "Section", other columns are variable columns.
    value_columns = [c for c in df_fin.columns if c != "Section"]

    # Build var_name depending on whether columns are tuples (MultiIndex) or strings
    if isinstance(value_columns[0], tuple):
        # convert tuple columns to strings for melt and then split into levels
        # create temporary columns with string representation
        df_fin_cols_str = []
        for col in value_columns:
            # join tuple parts with '||' as delimiter to later split
            joined = "||".join([str(x).strip() for x in col])
            df_fin_cols_str.append(joined)
        # rename columns temporarily
        rename_map = {old: new for old, new in zip(value_columns, df_fin_cols_str)}
        df_fin_temp = df_fin.rename(columns=rename_map)
        melted_fin = df_fin_temp.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")
        # split ColKey back into levels
        split_df = melted_fin["ColKey"].str.split(r"\|\|", expand=True)
        # name the columns Level0, Level1, Level2...
        level_names = [f"Level{i}" for i in range(split_df.shape[1])]
        split_df.columns = level_names
        melted_fin = pd.concat([melted_fin[["Section", "Value"]], split_df], axis=1)
    else:
        # columns are simple strings
        melted_fin = df_fin.melt(id_vars=["Section"], value_name="Value")
        # if header rows existed, try to infer level names from header_rows
        if n_header_rows >= 2:
            # create Level0.. from header arrays
            # For string columns, header_arrays correspond to the original header values; attempt to map
            # Build a DataFrame mapping original column index to header values
            header_map = pd.DataFrame(header_arrays).T
            header_map.columns = [f"Level{i}" for i in range(header_map.shape[1])]
            header_map["ColName"] = header_rows.iloc[0, :].fillna("").astype(str).str.strip().tolist()
            # Now map melted_fin variable column to header_map (best-effort)
            # Since melt already used existing column names, we can join on ColName
            melted_fin = melted_fin.rename(columns={"variable": "ColName"})
            # left join to add levels
            melted_fin = melted_fin.merge(header_map, on="ColName", how="left")
        else:
            # no extra levels
            pass

    # normalize sections and values
    melted_fin["Section"] = melted_fin["Section"].fillna("").astype(str).str.strip()
    melted_fin["Value"] = melted_fin["Value"]

    # -----------------------
    # Load Mapping + Data (Financials_anotherView.xlsx)
    # -----------------------
    df_raw = pd.read_excel(map_file, sheet_name="Mapping and populated Data", header=None)

    # Remove blank columns
    df_raw = drop_blank_columns(df_raw)

    # sanity check
    if df_raw.shape[0] < 12 or df_raw.shape[1] < 3:
        st.warning("Mapping file looks smaller than expected. The app will continue but results may be limited.")

    # project attributes in column 0, GC attribute in column 1, data from column 2 onwards
    proj_attr = df_raw.iloc[:, 0].fillna("").astype(str)
    gc_attr = df_raw.iloc[:, 1].fillna("").astype(str)

    # meta rows (these are row positions that hold compID, compName, etc.)
    # ensure the meta_rows exist
    max_meta_row = min(11, df_raw.shape[0]-1)
    meta_rows = list(range(1, max_meta_row+1))  # 1..max_meta_row inclusive
    data_start_row = 11 if df_raw.shape[0] > 11 else max_meta_row + 1
    data_rows = list(range(data_start_row, df_raw.shape[0]))

    # Build headers mapping for each data column
    headers = {}
    for col in df_raw.columns[2:]:
        keys = df_raw.iloc[meta_rows, 0].fillna("").astype(str).tolist()
        vals = df_raw.iloc[meta_rows, col].fillna("").astype(str).tolist()
        headers[col] = dict(zip(keys, vals))

    records = []
    for row in data_rows:
        if row >= df_raw.shape[0]:
            break
        proj = df_raw.iloc[row, 0] if 0 in df_raw.columns else ""
        gc = df_raw.iloc[row, 1] if 1 in df_raw.columns else ""
        for col in df_raw.columns[2:]:
            val = df_raw.iloc[row, col]
            if pd.notna(val) and str(val).strip() != "":
                rec = {"Proj_Attribute": proj, "GC_Attribute": gc, **headers.get(col, {}), "Value": val}
                records.append(rec)

    df_map = pd.DataFrame(records)
    if df_map.empty:
        st.warning("No mapped records found after processing mapping file. Please check sheet 'Mapping and populated Data'.")
    else:
        # standardize string fields
        for c in df_map.select_dtypes(include=["object"]).columns:
            df_map[c] = df_map[c].astype(str).str.strip()

    # -----------------------
    # Filters
    # -----------------------
    st.subheader("🎯 Comparison Filters")

    colf1, colf2, colf3 = st.columns(3)
    with colf1: comp_id = st.text_input("compID")
    with colf2: comp_name = st.text_input("compName")
    with colf3: cal_year = st.text_input("CalYear")

    colf4, colf5, colf6 = st.columns(3)
    with colf4: prerios = st.text_input("PreriosTypeName")
    with colf5: reporting = st.text_input("ReportingBases")
    with colf6: currency = st.text_input("Currency")

    tol = st.slider("Select numeric comparison tolerance (%)", 0.0, 10.0, 2.0, 0.1)
    tol_factor = tol / 100.0

    # -----------------------
    # Run Comparison
    # -----------------------
    if st.button("🔍 Run Comparison"):
        results = []
        unmapped = []

        # Prepare list of candidate sections from financials (lowercased for matching)
        candidate_sections = melted_fin["Section"].astype(str).unique().tolist()

        for _, row in df_map.iterrows():
            attr = str(row.get("GC_Attribute", "")).strip()
            if not attr:
                continue

            matches = get_close_matches(attr, candidate_sections, n=1, cutoff=0.7)
            if not matches:
                unmapped.append(attr)
                continue

            attr_match = matches[0]
            fin_rows = melted_fin[melted_fin["Section"].str.lower() == attr_match.lower()]

            # if multiple matches for the same Section exist (because of many years/categories),
            # we attempt to pick the record satisfying metadata filters in the mapping file.
            # Build metadata filter dict from mapping row
            meta_filter = {
                "compID": str(row.get("compID", "")).strip().lower(),
                "compName": str(row.get("compName", "")).strip().lower(),
                "CalYear": str(row.get("CalYear", "")).strip().lower(),
                "PreriosTypeName": str(row.get("PreriosTypeName", "")).strip().lower(),
                "ReportingBases": str(row.get("ReportingBases", "")).strip().lower(),
                "Currency": str(row.get("Currency", "")).strip().lower(),
            }

            # If fin_rows contains Level columns (Level0..LevelN), try to match them against meta_filter values
            fin_selected = fin_rows.copy()
            level_cols = [c for c in fin_selected.columns if c.startswith("Level")]
            if level_cols and any(v for v in meta_filter.values()):
                # build boolean mask progressively
                mask = pd.Series([True] * len(fin_selected))
                for lvl in level_cols:
                    # check each meta value against the column level; if it matches any meta, keep.
                    # It's a heuristic: if a level contains compID, compName, etc., it will match.
                    # More advanced mapping logic can be implemented if necessary.
                    lvl_values = fin_selected[lvl].astype(str).str.strip().str.lower()
                    # if comp_id provided in UI, use it to filter
                    if comp_id:
                        mask &= lvl_values.str.contains(str(comp_id).strip().lower(), na=False)
                    if comp_name:
                        mask &= lvl_values.str.contains(str(comp_name).strip().lower(), na=False)
                    if cal_year:
                        mask &= lvl_values.str.contains(str(cal_year).strip().lower(), na=False)
                    if prerios:
                        mask &= lvl_values.str.contains(str(prerios).strip().lower(), na=False)
                    if reporting:
                        mask &= lvl_values.str.contains(str(reporting).strip().lower(), na=False)
                    if currency:
                        mask &= lvl_values.str.contains(str(currency).strip().lower(), na=False)
                # if mask yielded any rows, keep them
                if mask.any():
                    fin_selected = fin_selected[mask]

            # if still multiple rows, take the first (could be refined)
            if fin_selected.empty:
                unmapped.append(attr)
                continue

            fin_val = fin_selected.iloc[0]["Value"]
            map_val = row["Value"]

            # numeric comparison if possible
            fin_num = safe_float(fin_val)
            map_num = safe_float(map_val)
            if fin_num is not None and map_num is not None:
                diff = abs(fin_num - map_num)
                avg = np.mean([abs(fin_num), abs(map_num)]) or 1
                pct_diff = diff / avg
                match_flag = "✅ Match" if pct_diff <= tol_factor else "❌ Mismatch"
            else:
                match_flag = "✅ Match" if str(fin_val).strip() == str(map_val).strip() else "❌ Mismatch"

            # Also apply the UI-level filters (if user entered any) based on the mapping row
            ui_cond = (
                (not comp_id or str(row.get("compID", "")).strip().lower() == comp_id.strip().lower()) and
                (not comp_name or str(row.get("compName", "")).strip().lower() == comp_name.strip().lower()) and
                (not cal_year or str(row.get("CalYear", "")).strip().lower() == cal_year.strip().lower()) and
                (not prerios or str(row.get("PreriosTypeName", "")).strip().lower() == prerios.strip().lower()) and
                (not reporting or str(row.get("ReportingBases", "")).strip().lower() == reporting.strip().lower()) and
                (not currency or str(row.get("Currency", "")).strip().lower() == currency.strip().lower())
            )
            if not ui_cond:
                # skip rows not matching selected UI filters
                continue

            results.append({
                "GC_Attribute": attr,
                "Proj_Attribute": row.get("Proj_Attribute", ""),
                "compID": row.get("compID", ""),
                "compName": row.get("compName", ""),
                "CalYear": row.get("CalYear", ""),
                "PreriosTypeName": row.get("PreriosTypeName", ""),
                "ReportingBases": row.get("ReportingBases", ""),
                "Currency": row.get("Currency", ""),
                "Financials_Value": fin_val,
                "Mapped_Value": map_val,
                "Comparison": match_flag
            })

        # -----------------------
        # Results & Summary
        # -----------------------
        if results:
            df_result = pd.DataFrame(results)
            total = len(df_result)
            matched = (df_result["Comparison"] == "✅ Match").sum()
            mismatched = (df_result["Comparison"] == "❌ Mismatch").sum()
            unmapped_count = len(set(unmapped))

            # Summary
            st.subheader("📈 Attribute Summary")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Compared", total)
            c2.metric("✅ Matches", matched)
            c3.metric("❌ Mismatches", mismatched)
            c4.metric("🕵️ Unmapped", unmapped_count)

            # Chart
            fig, ax = plt.subplots()
            ax.bar(["Matched", "Mismatched", "Unmapped"], [matched, mismatched, unmapped_count], color=["green", "red", "gray"])
            ax.set_ylabel("Count")
            ax.set_title("Attribute Comparison Summary")
            st.pyplot(fig)

            # View filter + highlight
            st.subheader("🔎 View Comparison Results")
            view_opt = st.radio("Select View", ["All Records", "Only Mismatches", "Only Matches"], horizontal=True)
            if view_opt == "Only Mismatches":
                df_view = df_result[df_result["Comparison"] == "❌ Mismatch"]
            elif view_opt == "Only Matches":
                df_view = df_result[df_result["Comparison"] == "✅ Match"]
            else:
                df_view = df_result.copy()

            def highlight_mismatch(val):
                return "background-color: #ffcccc" if val == "❌ Mismatch" else ""

            st.dataframe(df_view.style.applymap(highlight_mismatch, subset=["Comparison"]))

            # Show unmapped
            if unmapped_count > 0:
                with st.expander(f"🕵️ Unmapped Attributes ({unmapped_count})"):
                    st.dataframe(pd.DataFrame({"Unmapped_Attributes": list(set(unmapped))}))

            # Excel download
            def to_excel(df1, unmapped_list):
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                    df1.to_excel(w, index=False, sheet_name="Comparison_Result")
                    pd.DataFrame({"Unmapped_Attributes": list(set(unmapped_list))}).to_excel(w, index=False, sheet_name="Unmapped_Attributes")
                return buf.getvalue()

            excel_out = to_excel(df_result, unmapped)
            st.download_button(label="⬇️ Download Comparison Report (Excel)", data=excel_out,
                               file_name="Financials_Comparison_Report.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No matching data found based on provided filters or mapping results.")
else:
    st.info("Please upload both Excel files to start.")