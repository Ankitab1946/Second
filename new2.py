import streamlit as st
import pandas as pd
import numpy as np
import io
from difflib import get_close_matches
import matplotlib.pyplot as plt

st.set_page_config(page_title="Financials Comparator", layout="wide")
st.title("📊 Financials.xlsx ↔ Financials_anotherView.xlsx Comparator (Stable Version)")

# ----------------------------------------------------------
# Utility: Remove blank columns safely (no ambiguous booleans)
# ----------------------------------------------------------
def drop_blank_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep_cols = []
    for col in df.columns:
        series = df[col]
        filled = series.fillna("").astype(str).str.strip()
        if not filled.eq("").all():   # ALL empty → drop
            keep_cols.append(col)
    return df.loc[:, keep_cols]


def safe_float(x):
    try:
        return float(x)
    except:
        return None


def safe_strip(s):
    return str(s).strip() if s is not None else ""


# ==========================================================
# Upload Section
# ==========================================================
col1, col2 = st.columns(2)
with col1:
    fin_file = st.file_uploader("Upload Financials.xlsx", type=["xlsx", "xls"])
with col2:
    map_file = st.file_uploader("Upload Financials_anotherView.xlsx", type=["xlsx", "xls"])

if not (fin_file and map_file):
    st.info("Please upload both Excel files to start.")
    st.stop()


# ==========================================================
# Load Financials.xlsx
# ==========================================================
fin_xls = pd.ExcelFile(fin_file)
selected_tab = st.selectbox("Select sheet from Financials.xlsx", fin_xls.sheet_names)

raw_fin = pd.read_excel(fin_file, sheet_name=selected_tab, header=None)

raw_fin = drop_blank_columns(raw_fin)

if raw_fin.shape[1] == 0:
    st.error("No usable columns found in Financials.xlsx after removing blank columns.")
    st.stop()

n_header_rows = min(3, raw_fin.shape[0] - 1)
header_rows = raw_fin.iloc[0:n_header_rows, :]
fin_data = raw_fin.iloc[n_header_rows:, :].reset_index(drop=True)

# Build header arrays
header_arrays = [
    header_rows.iloc[r].fillna("").astype(str).str.strip().tolist()
    for r in range(n_header_rows)
]

# MultiIndex if possible
try:
    if len(header_arrays) > 1:
        fin_cols = pd.MultiIndex.from_arrays(header_arrays)
    else:
        fin_cols = header_arrays[0]
except:
    fin_cols = header_arrays[0]

df_fin = pd.DataFrame(fin_data.values, columns=fin_cols)

# ----------------------------------------------------------
# AUTO DETECT FIRST NON-BLANK COLUMN AS "Section"
# ----------------------------------------------------------
non_empty_cols = []
for c in df_fin.columns:
    filled = df_fin[c].fillna("").astype(str).str.strip()
    if not filled.eq("").all():
        non_empty_cols.append(c)

if len(non_empty_cols) == 0:
    st.error("No non-empty column found to use as Section.")
    st.stop()

section_col = non_empty_cols[0]

df_fin = df_fin.rename(columns={section_col: "Section"})
value_cols = [c for c in df_fin.columns if c != "Section"]

if len(value_cols) == 0:
    st.error("No value columns found after extracting Section.")
    st.stop()

# ----------------------------------------------------------
# SAFELY MELT FINANCIALS
# ----------------------------------------------------------
if isinstance(value_cols[0], tuple):
    rename_map = {col: "||".join([safe_strip(x) for x in col]) for col in value_cols}
    df_tmp = df_fin.rename(columns=rename_map)
    melted_fin = df_tmp.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")

    split_cols = melted_fin["ColKey"].astype(str).str.split("||", expand=True)
    split_cols.columns = [f"Level{i}" for i in range(split_cols.shape[1])]

    melted_fin = pd.concat([melted_fin[["Section", "Value"]], split_cols], axis=1)

else:
    melted_fin = df_fin.melt(id_vars=["Section"], var_name="ColKey", value_name="Value")

melted_fin["Section"] = melted_fin["Section"].fillna("").astype(str).str.strip()


# ==========================================================
# Load Mapping File
# ==========================================================
df_raw = pd.read_excel(map_file, sheet_name="Mapping and populated Data", header=None)

df_raw = drop_blank_columns(df_raw)

if df_raw.shape[0] < 12:
    st.warning("Mapping file appears too small.")

proj_attr_col = 0
gc_attr_col = 1

max_meta_row = min(11, df_raw.shape[0]-1)
meta_rows = list(range(1, max_meta_row+1))
data_rows = list(range(max_meta_row+1, df_raw.shape[0]))

headers = {}
for col in df_raw.columns[2:]:
    keys = df_raw.iloc[meta_rows, proj_attr_col].fillna("").astype(str).str.strip().tolist()
    vals = df_raw.iloc[meta_rows, col].fillna("").astype(str).str.strip().tolist()
    headers[col] = dict(zip(keys, vals))

records = []
for r in data_rows:
    proj = safe_strip(df_raw.iat[r, proj_attr_col]) if proj_attr_col in df_raw.columns else ""
    gc   = safe_strip(df_raw.iat[r, gc_attr_col]) if gc_attr_col in df_raw.columns else ""

    for col in df_raw.columns[2:]:
        val = df_raw.iat[r, col]
        if pd.notna(val) and safe_strip(val) != "":
            record = {"Proj_Attribute": proj, "GC_Attribute": gc, **headers[col], "Value": val}
            records.append(record)

df_map = pd.DataFrame(records)
if not df_map.empty:
    for c in df_map.columns:
        df_map[c] = df_map[c].astype(str).map(lambda x: x.strip())

# ==========================================================
# UI Filter Inputs
# ==========================================================
st.subheader("🎯 Comparison Filters")
colf1, colf2, colf3 = st.columns(3)
with colf1: comp_id = safe_strip(st.text_input("compID"))
with colf2: comp_name = safe_strip(st.text_input("compName"))
with colf3: cal_year = safe_strip(st.text_input("CalYear"))

colf4, colf5, colf6 = st.columns(3)
with colf4: prerios = safe_strip(st.text_input("PreriosTypeName"))
with colf5: reporting = safe_strip(st.text_input("ReportingBases"))
with colf6: currency = safe_strip(st.text_input("Currency"))

tol = st.slider("Select numeric comparison tolerance (%)", 0.0, 10.0, 2.0, 0.1)
tol_factor = tol / 100.0

# ==========================================================
# RUN COMPARISON
# ==========================================================
if st.button("🔍 Run Comparison"):

    results = []
    unmapped = []

    sections_list = melted_fin["Section"].dropna().astype(str).str.lower().tolist()

    for idx, row in df_map.iterrows():
        attr = safe_strip(row.get("GC_Attribute", ""))

        # fuzzy matching
        matches = get_close_matches(attr.lower(), sections_list, n=1, cutoff=0.7)
        if not matches:
            unmapped.append(attr)
            continue

        matched_section_lower = matches[0]
        fin_rows = melted_fin[melted_fin["Section"].str.lower() == matched_section_lower]

        if fin_rows.empty:
            unmapped.append(attr)
            continue

        # pick first
        fin_val = fin_rows.iloc[0]["Value"]
        map_val = row["Value"]

        # numeric compare
        fn = safe_float(fin_val)
        mn = safe_float(map_val)

        if fn is not None and mn is not None:
            diff = abs(fn - mn)
            avg = np.mean([abs(fn), abs(mn)]) or 1
            pct = diff / avg
            match_flag = "✅ Match" if pct <= tol_factor else "❌ Mismatch"
        else:
            match_flag = "✅ Match" if safe_strip(fin_val) == safe_strip(map_val) else "❌ Mismatch"

        # apply user filters
        if comp_id and safe_strip(row.get("compID","")).lower() != comp_id.lower():
            continue
        if comp_name and safe_strip(row.get("compName","")).lower() != comp_name.lower():
            continue
        if cal_year and safe_strip(row.get("CalYear","")).lower() != cal_year.lower():
            continue
        if prerios and safe_strip(row.get("PreriosTypeName","")).lower() != prerios.lower():
            continue
        if reporting and safe_strip(row.get("ReportingBases","")).lower() != reporting.lower():
            continue
        if currency and safe_strip(row.get("Currency","")).lower() != currency.lower():
            continue

        results.append({
            "GC_Attribute": attr,
            "Proj_Attribute": row.get("Proj_Attribute",""),
            "compID": row.get("compID",""),
            "compName": row.get("compName",""),
            "CalYear": row.get("CalYear",""),
            "PreriosTypeName": row.get("PreriosTypeName",""),
            "ReportingBases": row.get("ReportingBases",""),
            "Currency": row.get("Currency",""),
            "Financials_Value": fin_val,
            "Mapped_Value": map_val,
            "Comparison": match_flag
        })

    # ==========================================================
    # DISPLAY RESULTS
    # ==========================================================
    if not results:
        st.warning("No comparable records found.")
        st.stop()

    df_result = pd.DataFrame(results)

    total = len(df_result)
    matched = (df_result["Comparison"] == "✅ Match").sum()
    mismatched = (df_result["Comparison"] == "❌ Mismatch").sum()
    unmapped_count = len(set(unmapped))

    st.subheader("📈 Attribute Summary")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Compared", total)
    c2.metric("Matches", matched)
    c3.metric("Mismatches", mismatched)
    c4.metric("Unmapped", unmapped_count)

    # Chart
    fig, ax = plt.subplots()
    ax.bar(["Matched", "Mismatched", "Unmapped"],
           [matched, mismatched, unmapped_count],
           color=["green","red","gray"])
    ax.set_ylabel("Count")
    st.pyplot(fig)

    # View Filter
    st.subheader("🔎 Filter Comparison Results")
    view = st.radio("Select View", ["All Records", "Only Mismatches", "Only Matches"], horizontal=True)

    if view == "Only Mismatches":
        df_view = df_result[df_result["Comparison"] == "❌ Mismatch"]
    elif view == "Only Matches":
        df_view = df_result[df_result["Comparison"] == "✅ Match"]
    else:
        df_view = df_result.copy()

    def highlight(val):
        return "background-color:#ffb3b3" if val=="❌ Mismatch" else ""

    st.dataframe(df_view.style.applymap(highlight, subset=["Comparison"]))

    if unmapped_count > 0:
        with st.expander("🕵️ Unmapped Attributes"):
            st.dataframe(pd.DataFrame({"Unmapped": list(set(unmapped))}))

    # Export
    def to_excel(df1, unmapped_list):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df1.to_excel(writer, index=False, sheet_name="Comparison")
            pd.DataFrame({"Unmapped": list(set(unmapped_list))}).to_excel(
                writer, index=False, sheet_name="Unmapped")
        return buf.getvalue()

    st.download_button(
        "⬇ Download Report", 
        data=to_excel(df_result, unmapped),
        file_name="Financials_Comparison_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )