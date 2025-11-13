import streamlit as st
import pandas as pd
import numpy as np
import io
from difflib import get_close_matches
import matplotlib.pyplot as plt

st.set_page_config(page_title="Financials Comparator", layout="wide")
st.title("📊 Financials.xlsx ↔ Financials_anotherView.xlsx Comparator (Robust Fix)")

# -----------------------
# Utilities (robust)
# -----------------------
def drop_blank_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns that are entirely blank (NaN or empty/whitespace strings)."""
    keep_cols = []
    for col in df.columns:
        series = df[col]
        # treat non-serries gracefully
        filled = series.fillna("").astype(str).map(lambda x: x.strip())
        if not filled.eq("").all():
            keep_cols.append(col)
    return df.loc[:, keep_cols]

def safe_strip_series(s):
    """Return a Series of stripped strings; works if input is Series or scalar fallback."""
    if isinstance(s, pd.Series):
        return s.fillna("").astype(str).map(lambda x: x.strip())
    else:
        return str(s).strip()

def safe_float(x):
    try:
        return float(x)
    except:
        return None

# -----------------------
# Upload section
# -----------------------
col1, col2 = st.columns(2)
with col1:
    fin_file = st.file_uploader("Upload Financials.xlsx", type=["xlsx", "xls"])
with col2:
    map_file = st.file_uploader("Upload Financials_anotherView.xlsx", type=["xlsx", "xls"])

if not (fin_file and map_file):
    st.info("Please upload both Excel files to start.")
    st.stop()

# -----------------------
# Load Financials.xlsx
# -----------------------
fin_xls = pd.ExcelFile(fin_file)
selected_tab = st.selectbox("Select sheet from Financials.xlsx", fin_xls.sheet_names)

raw_fin = pd.read_excel(fin_file, sheet_name=selected_tab, header=None)

# Remove blank columns early
raw_fin = drop_blank_columns(raw_fin)

if raw_fin.shape[1] == 0:
    st.error("Financials.xlsx: All columns are blank after cleanup.")
    st.stop()

# Determine header rows (best-effort up to 3)
n_header_rows = min(3, raw_fin.shape[0] - 1)  # ensure at least 1 data row
header_rows = raw_fin.iloc[0:n_header_rows, :].copy()
data_start = n_header_rows
fin_data = raw_fin.iloc[data_start:, :].reset_index(drop=True)

# Build header arrays safely (list of lists)
header_arrays = []
for r in range(n_header_rows):
    row_series = header_rows.iloc[r, :].fillna("").astype(str).map(lambda x: x.strip())
    header_arrays.append(row_series.tolist())

# Try to create MultiIndex columns; fallback to simple names
try:
    if len(header_arrays) > 1:
        fin_cols = pd.MultiIndex.from_arrays(header_arrays)
    else:
        fin_cols = header_arrays[0]
except Exception:
    fin_cols = header_arrays[0] if header_arrays else list(range(fin_data.shape[1]))

df_fin = pd.DataFrame(fin_data.values, columns=fin_cols)

# -----------------------
# Detect the real Section column: first column with any non-empty values
# -----------------------
non_empty_cols = []
for c in df_fin.columns:
    series = df_fin[c].fillna("").astype(str).map(lambda x: x.strip())
    if not series.eq("").all():
        non_empty_cols.append(c)

if not non_empty_cols:
    st.error("Financials.xlsx: Could not find any non-empty column to use as Section.")
    st.stop()

section_col = non_empty_cols[0]
# Rename to 'Section' (handle both tuple and string names)
df_fin = df_fin.rename(columns={section_col: "Section"})

# Build the list of value columns (everything except Section)
value_cols = [c for c in df_fin.columns if c != "Section"]
if not value_cols:
    st.error("No value columns found in Financials.xlsx after Section detection.")
    st.stop()

# -----------------------
# Melt Financials into long format safely
# -----------------------
if isinstance(value_cols[0], tuple):
    # convert tuple columns to unique string keys for melt, then split back
    rename_map = {old: "||".join([str(x) if x is not None else "" for x in old]) for old in value_cols}
    df_tmp = df_fin.rename(columns=rename_map)
    melted_fin = df_tmp.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")
    # split ColKey into level columns
    split_cols = melted_fin["ColKey"].str.split("||", expand=True)
    split_cols = split_cols.fillna("").astype(str).applymap(lambda x: x.strip())
    split_cols.columns = [f"Level{i}" for i in range(split_cols.shape[1])]
    melted_fin = pd.concat([melted_fin[["Section", "Value"]].reset_index(drop=True), split_cols.reset_index(drop=True)], axis=1)
else:
    # simple columns (strings)
    df_fin = df_fin.rename(columns={c: safe_strip_series(df_fin[c]).name if False else c for c in df_fin.columns})
    melted_fin = df_fin.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")
    # ensure ColKey is string and stripped
    melted_fin["ColKey"] = melted_fin["ColKey"].astype(str).map(lambda x: x.strip())

# Normalize Section and Value
melted_fin["Section"] = melted_fin["Section"].fillna("").astype(str).map(lambda x: x.strip())
# Value left as-is (may be numeric or string)

# -----------------------
# Load mapping file (Financials_anotherView.xlsx)
# -----------------------
df_raw = pd.read_excel(map_file, sheet_name="Mapping and populated Data", header=None)

# Clean blank columns
df_raw = drop_blank_columns(df_raw)

# Basic sanity
if df_raw.shape[1] < 3 or df_raw.shape[0] < 5:
    st.warning("Mapping sheet looks smaller than expected — proceed with caution.")

# proj attr in col 0, gc attr in col 1, data from col 2 onwards.
proj_attr_col = 0
gc_attr_col = 1

# Determine max meta rows (the rows holding compID, compName etc.)
max_meta_row = min(11, df_raw.shape[0] - 1)
meta_rows = list(range(1, max_meta_row + 1))
data_start_row = max_meta_row + 1 if df_raw.shape[0] > max_meta_row + 1 else max_meta_row + 1
data_rows = list(range(data_start_row, df_raw.shape[0]))

# Build headers mapping per column index (col >=2)
headers = {}
for col in df_raw.columns[2:]:
    # keys: values in column 0 for each meta row
    keys = df_raw.iloc[meta_rows, proj_attr_col].fillna("").astype(str).map(lambda x: x.strip()).tolist()
    vals = df_raw.iloc[meta_rows, col].fillna("").astype(str).map(lambda x: x.strip()).tolist()
    headers[col] = dict(zip(keys, vals))

records = []
for r in data_rows:
    if r >= df_raw.shape[0]:
        continue
    proj = df_raw.iat[r, proj_attr_col] if proj_attr_col in df_raw.columns else ""
    gc = df_raw.iat[r, gc_attr_col] if gc_attr_col in df_raw.columns else ""
    for col in df_raw.columns[2:]:
        val = df_raw.iat[r, col]
        if pd.notna(val) and str(val).strip() != "":
            rec = {"Proj_Attribute": str(proj).strip(), "GC_Attribute": str(gc).strip(), **headers.get(col, {}), "Value": val}
            records.append(rec)

df_map = pd.DataFrame(records)
if not df_map.empty:
    # strip string columns
    obj_cols = df_map.select_dtypes(include=["object"]).columns
    for c in obj_cols:
        df_map[c] = df_map[c].astype(str).map(lambda x: x.strip())

# -----------------------
# UI Filters
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
# Run comparison
# -----------------------
if st.button("🔍 Run Comparison"):
    if df_map.empty:
        st.warning("No mapped records (df_map is empty). Check mapping file.")
        st.stop()

    results = []
    unmapped = []
    candidate_sections = melted_fin["Section"].astype(str).unique().tolist()

    for _, row in df_map.iterrows():
        attr = str(row.get("GC_Attribute", "")).strip()
        if not attr:
            continue

        # fuzzy match against candidate_sections
        matches = get_close_matches(attr, candidate_sections, n=1, cutoff=0.7)
        if not matches:
            unmapped.append(attr)
            continue

        matched_section = matches[0]
        fin_rows = melted_fin[melted_fin["Section"].str.lower() == matched_section.lower()]

        # try to further filter fin_rows using UI filters if Level columns exist
        level_cols = [c for c in fin_rows.columns if str(c).startswith("Level")]
        if (len(level_cols) > 0) and any([comp_id, comp_name, cal_year, prerios, reporting, currency]):
            mask = pd.Series([True] * len(fin_rows), index=fin_rows.index)
            for lvl in level_cols:
                lvl_vals = fin_rows[lvl].fillna("").astype(str).map(lambda x: x.strip().lower())
                if comp_id:
                    mask &= lvl_vals.str.contains(comp_id.strip().lower(), na=False) | mask
                if comp_name:
                    mask &= lvl_vals.str.contains(comp_name.strip().lower(), na=False) | mask
                if cal_year:
                    mask &= lvl_vals.str.contains(cal_year.strip().lower(), na=False) | mask
                if prerios:
                    mask &= lvl_vals.str.contains(prerios.strip().lower(), na=False) | mask
                if reporting:
                    mask &= lvl_vals.str.contains(reporting.strip().lower(), na=False) | mask
                if currency:
                    mask &= lvl_vals.str.contains(currency.strip().lower(), na=False) | mask
            fin_rows = fin_rows[mask]

        if fin_rows.empty:
            # fallback to first available row for that section
            fin_rows = melted_fin[melted_fin["Section"].str.lower() == matched_section.lower()]
            if fin_rows.empty:
                unmapped.append(attr)
                continue

        fin_val = fin_rows.iloc[0]["Value"]
        map_val = row["Value"]

        fn = safe_float(fin_val)
        mn = safe_float(map_val)
        if fn is not None and mn is not None:
            diff = abs(fn - mn)
            avg = np.mean([abs(fn), abs(mn)]) or 1
            pct_diff = diff / avg
            match_flag = "✅ Match" if pct_diff <= tol_factor else "❌ Mismatch"
        else:
            match_flag = "✅ Match" if str(fin_val).strip() == str(map_val).strip() else "❌ Mismatch"

        # UI-level filters applied to mapping metadata
        ui_cond = (
            (not comp_id or str(row.get("compID", "")).strip().lower() == comp_id.strip().lower()) and
            (not comp_name or str(row.get("compName", "")).strip().lower() == comp_name.strip().lower()) and
            (not cal_year or str(row.get("CalYear", "")).strip().lower() == cal_year.strip().lower()) and
            (not prerios or str(row.get("PreriosTypeName", "")).strip().lower() == prerios.strip().lower()) and
            (not reporting or str(row.get("ReportingBases", "")).strip().lower() == reporting.strip().lower()) and
            (not currency or str(row.get("Currency", "")).strip().lower() == currency.strip().lower())
        )
        if not ui_cond:
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
    # Results
    # -----------------------
    if not results:
        st.warning("No comparable records found for given filters/mapping.")
        st.stop()

    df_result = pd.DataFrame(results)
    total = len(df_result)
    matched = (df_result["Comparison"] == "✅ Match").sum()
    mismatched = (df_result["Comparison"] == "❌ Mismatch").sum()
    unmapped_count = len(set(unmapped))

    # Summary metrics
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

    # View filter and highlight
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

    # Unmapped list
    if unmapped_count > 0:
        with st.expander(f"🕵️ Unmapped Attributes ({unmapped_count})"):
            st.dataframe(pd.DataFrame({"Unmapped_Attributes": list(set(unmapped))}))

    # Excel export
    def to_excel(df1, unmapped_list):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df1.to_excel(writer, index=False, sheet_name="Comparison_Result")
            pd.DataFrame({"Unmapped_Attributes": list(set(unmapped_list))}).to_excel(writer, index=False, sheet_name="Unmapped_Attributes")
        return buf.getvalue()

    excel_out = to_excel(df_result, unmapped)
    st.download_button(label="⬇️ Download Comparison Report (Excel)", data=excel_out,
                       file_name="Financials_Comparison_Report.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")