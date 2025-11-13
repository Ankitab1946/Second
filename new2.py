import streamlit as st
import pandas as pd
import numpy as np
import io
from difflib import get_close_matches
import matplotlib.pyplot as plt

st.set_page_config(page_title="Financials Comparator", layout="wide")
st.title("📊 Financials.xlsx ↔ Financials_anotherView.xlsx Comparator (FINAL-STABLE)")

# ----------------------------------------------------------
# ✔ FIXED: Drop blank columns (Series-safe, no ambiguity)
# ----------------------------------------------------------
def drop_blank_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep_cols = []
    for col in df.columns:
        series = df[col].fillna("").astype(str).str.strip()
        # keep if ANY non-empty cell exists
        if series.ne("").any():
            keep_cols.append(col)
    return df[keep_cols]


# ----------------------------------------------------------
# Utility
# ----------------------------------------------------------
def safe_float(x):
    try:
        return float(x)
    except:
        return None


# =================================================================
#                     FILE UPLOAD SECTION
# =================================================================
col1, col2 = st.columns(2)
with col1:
    fin_file = st.file_uploader("Upload Financials.xlsx", type=["xlsx", "xls"])
with col2:
    map_file = st.file_uploader("Upload Financials_anotherView.xlsx", type=["xlsx", "xls"])

if not (fin_file and map_file):
    st.info("Please upload both Excel files to begin.")
    st.stop()


# =================================================================
#                 LOAD Financials.xlsx (FIRST FILE)
# =================================================================
fin_xls = pd.ExcelFile(fin_file)
selected_tab = st.selectbox("Select sheet from Financials.xlsx", fin_xls.sheet_names)

raw_fin = pd.read_excel(fin_file, sheet_name=selected_tab, header=None)

# Remove blank columns
raw_fin = drop_blank_columns(raw_fin)

if raw_fin.shape[1] == 0:
    st.error("Financials.xlsx contains no usable columns after cleanup.")
    st.stop()

# Determine header rows (up to 3)
n_header_rows = min(3, raw_fin.shape[0] - 1)
header_rows = raw_fin.iloc[0:n_header_rows].fillna("").astype(str).applymap(lambda x: x.strip())

# Data rows
fin_data = raw_fin.iloc[n_header_rows:].reset_index(drop=True)

# Build header arrays
header_arrays = [header_rows.iloc[i].tolist() for i in range(n_header_rows)]

# Create MultiIndex or single-level columns
try:
    if len(header_arrays) > 1:
        fin_cols = pd.MultiIndex.from_arrays(header_arrays)
    else:
        fin_cols = header_arrays[0]
except:
    fin_cols = header_arrays[0]

df_fin = pd.DataFrame(fin_data.values, columns=fin_cols)

# ----------------------------------------------------------
# ✔ FIX: Auto-detect first non-empty column as "Section"
# ----------------------------------------------------------
non_empty_cols = []
for c in df_fin.columns:
    series = df_fin[c].fillna("").astype(str).str.strip()
    if series.ne("").any():
        non_empty_cols.append(c)

if not non_empty_cols:
    st.error("Financials.xlsx: Could not identify Section column.")
    st.stop()

section_col = non_empty_cols[0]
df_fin = df_fin.rename(columns={section_col: "Section"})

value_cols = [c for c in df_fin.columns if c != "Section"]


# ----------------------------------------------------------
# Melt df_fin → melted_fin (MultiIndex-safe)
# ----------------------------------------------------------
if isinstance(value_cols[0], tuple):
    rename_map = {old: "||".join([str(x) for x in old]) for old in value_cols}
    df_tmp = df_fin.rename(columns=rename_map)
    melted = df_tmp.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")

    split_cols = melted["ColKey"].str.split("||", expand=True)
    split_cols.columns = [f"Level{i}" for i in range(split_cols.shape[1])]

    melted_fin = pd.concat([melted[["Section", "Value"]], split_cols], axis=1)

else:
    melted_fin = df_fin.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")

melted_fin["Section"] = melted_fin["Section"].astype(str).str.strip()


# =================================================================
#             LOAD Financials_anotherView.xlsx (SECOND FILE)
# =================================================================
df_raw = pd.read_excel(map_file, sheet_name="Mapping and populated Data", header=None)
df_raw = drop_blank_columns(df_raw)

proj_attr_col = 0
gc_attr_col = 1

max_meta_row = min(11, df_raw.shape[0] - 1)
meta_rows = list(range(1, max_meta_row + 1))
data_rows = list(range(max_meta_row + 1, df_raw.shape[0]))

headers = {}
for col in df_raw.columns[2:]:
    keys = df_raw.iloc[meta_rows, proj_attr_col].fillna("").astype(str).str.strip().tolist()
    vals = df_raw.iloc[meta_rows, col].fillna("").astype(str).str.strip().tolist()
    headers[col] = dict(zip(keys, vals))

records = []
for r in data_rows:
    if r >= df_raw.shape[0]:
        break
    proj = str(df_raw.iat[r, proj_attr_col]).strip()
    gc = str(df_raw.iat[r, gc_attr_col]).strip()

    for col in df_raw.columns[2:]:
        val = df_raw.iat[r, col]
        if pd.notna(val) and str(val).strip() != "":
            rec = {"Proj_Attribute": proj, "GC_Attribute": gc, **headers[col], "Value": val}
            records.append(rec)

df_map = pd.DataFrame(records)
if not df_map.empty:
    for c in df_map.select_dtypes(include=["object"]).columns:
        df_map[c] = df_map[c].astype(str).str.strip()


# =================================================================
#                         FILTER SECTION
# =================================================================
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


# =================================================================
#                        RUN COMPARISON
# =================================================================
if st.button("🔍 Run Comparison"):

    results = []
    unmapped = []

    candidate_sections = melted_fin["Section"].unique().tolist()

    for _, row in df_map.iterrows():

        attr = row["GC_Attribute"]
        matches = get_close_matches(attr, candidate_sections, n=1, cutoff=0.7)

        if not matches:
            unmapped.append(attr)
            continue

        matched_sec = matches[0]
        fin_rows = melted_fin[melted_fin["Section"].str.lower() == matched_sec.lower()]

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
            pct = diff / avg
            match_flag = "✅ Match" if pct <= tol_factor else "❌ Mismatch"
        else:
            match_flag = "✅ Match" if str(fin_val).strip() == str(map_val).strip() else "❌ Mismatch"

        # Apply UI metadata filters (mapping file metadata only)
        cond = (
            (not comp_id or str(row.get("compID", "")).lower() == comp_id.lower()) and
            (not comp_name or str(row.get("compName", "")).lower() == comp_name.lower()) and
            (not cal_year or str(row.get("CalYear", "")).lower() == cal_year.lower()) and
            (not prerios or str(row.get("PreriosTypeName", "")).lower() == prerios.lower()) and
            (not reporting or str(row.get("ReportingBases", "")).lower() == reporting.lower()) and
            (not currency or str(row.get("Currency", "")).lower() == currency.lower())
        )
        if not cond:
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


    # =================================================================
    #                    SUMMARY + TABLE + EXPORT
    # =================================================================
    if not results:
        st.warning("No matching comparison results found.")
        st.stop()

    df_result = pd.DataFrame(results)

    total = len(df_result)
    matched = (df_result["Comparison"] == "✅ Match").sum()
    mismatched = (df_result["Comparison"] == "❌ Mismatch").sum()
    unmapped_count = len(set(unmapped))

    st.subheader("📊 Summary Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Compared", total)
    c2.metric("Matches", matched)
    c3.metric("Mismatches", mismatched)
    c4.metric("Unmapped", unmapped_count)

    fig, ax = plt.subplots()
    ax.bar(["Matched", "Mismatched", "Unmapped"], [matched, mismatched, unmapped_count], color=["green", "red", "gray"])
    ax.set_title("Comparison Summary")
    st.pyplot(fig)

    # View filter
    st.subheader("🔍 Filter Comparison Results")
    view_choice = st.radio("View", ["All Records", "Only Matches", "Only Mismatches"], horizontal=True)

    if view_choice == "Only Matches":
        df_view = df_result[df_result["Comparison"] == "✅ Match"]
    elif view_choice == "Only Mismatches":
        df_view = df_result[df_result["Comparison"] == "❌ Mismatch"]
    else:
        df_view = df_result.copy()

    # Highlight mismatches
    def highlight(val):
        return "background-color: #ffcccc" if val == "❌ Mismatch" else ""

    st.dataframe(df_view.style.applymap(highlight, subset=["Comparison"]))

    # Unmapped list
    if unmapped_count > 0:
        with st.expander("🕵️ Unmapped Attributes"):
            st.dataframe(pd.DataFrame({"Unmapped_Attributes": list(set(unmapped))}))

    # Excel download
    def to_excel(df1, unmapped_list):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df1.to_excel(writer, index=False, sheet_name="Comparison_Result")
            pd.DataFrame({"Unmapped_Attributes": list(set(unmapped_list))}).to_excel(writer, index=False, sheet_name="Unmapped_Attributes")
        return buf.getvalue()

    st.download_button(
        label="⬇️ Download Comparison Excel",
        data=to_excel(df_result, unmapped),
        file_name="Financials_Comparison_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )