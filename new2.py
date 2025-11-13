import streamlit as st
import pandas as pd
import numpy as np
import io
from difflib import get_close_matches
import matplotlib.pyplot as plt

st.set_page_config(page_title="Financials Comparator", layout="wide")
st.title("📊 Financials.xlsx ↔ Financials_anotherView.xlsx Comparator (Final Version)")

# -----------------------
# Function: Remove blank columns
# -----------------------
def drop_blank_columns(df):
    return df.dropna(axis=1, how="all").loc[:, (df.astype(str).ne("").any())]


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

    # Remove blank columns
    raw_fin = drop_blank_columns(raw_fin)

    fin_headers = raw_fin.iloc[0:3, :]
    fin_data = raw_fin.iloc[3:, :].reset_index(drop=True)

    fin_cols = pd.MultiIndex.from_arrays(fin_headers.values, names=["Category", "Subcategory", "Year"])
    df_fin = pd.DataFrame(fin_data.values, columns=fin_cols)

    df_fin.rename(columns={df_fin.columns[0]: ("Section", "", "")}, inplace=True)

    df_fin = df_fin.loc[:, ~df_fin.columns.duplicated()]

    # Melt data
    melted_fin = df_fin.melt(
        id_vars=[("Section", "", "")],
        var_name=["Category", "Subcategory", "Year"],
        value_name="Value"
    )

    melted_fin.rename(columns={("Section", "", ""): "Section"}, inplace=True)
    for c in ["Section", "Category", "Subcategory", "Year"]:
        melted_fin[c] = melted_fin[c].fillna("").astype(str).str.strip()


    # -----------------------
    # Load Mapping + Data (Financials_anotherView.xlsx)
    # -----------------------
    df_raw = pd.read_excel(map_file, sheet_name="Mapping and populated Data", header=None)

    # Remove blank columns
    df_raw = drop_blank_columns(df_raw)

    proj_attr = df_raw.iloc[:, 0].fillna("").astype(str)
    gc_attr = df_raw.iloc[:, 1].fillna("").astype(str)

    meta_rows = range(1, 11)
    data_rows = range(11, len(df_raw))

    headers = {}
    for col in df_raw.columns[2:]:
        keys = proj_attr.iloc[list(meta_rows)].tolist()
        vals = df_raw.iloc[list(meta_rows), col].fillna("").astype(str).tolist()
        headers[col] = dict(zip(keys, vals))

    records = []
    for row in data_rows:
        proj = df_raw.iloc[row, 0]
        gc = df_raw.iloc[row, 1]
        for col in df_raw.columns[2:]:
            val = df_raw.iloc[row, col]
            if pd.notna(val) and str(val).strip() != "":
                rec = {"Proj_Attribute": proj, "GC_Attribute": gc, **headers[col], "Value": val}
                records.append(rec)

    df_map = pd.DataFrame(records)
    df_map = df_map.applymap(lambda x: str(x).strip() if isinstance(x, str) else x)


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
    # Perform Comparison
    # -----------------------
    if st.button("🔍 Run Comparison"):

        results = []
        unmapped = []

        for _, row in df_map.iterrows():

            attr = row["GC_Attribute"]
            matches = get_close_matches(attr, melted_fin["Section"].unique(), n=1, cutoff=0.7)

            if not matches:
                unmapped.append(attr)
                continue

            attr_match = matches[0]
            fin_val_series = melted_fin[melted_fin["Section"].str.lower() == attr_match.lower()]["Value"]

            if fin_val_series.empty:
                unmapped.append(attr)
                continue

            fin_val = fin_val_series.values[0]
            map_val = row["Value"]

            # Compare values
            try:
                fn = float(fin_val)
                mn = float(map_val)
                diff = abs(fn - mn)
                avg = np.mean([abs(fn), abs(mn)]) or 1
                pct_diff = diff / avg
                match_flag = "✅ Match" if pct_diff <= tol_factor else "❌ Mismatch"
            except:
                match_flag = "✅ Match" if str(fin_val).strip() == str(map_val).strip() else "❌ Mismatch"

            # Apply filters
            cond = (
                (not comp_id or row.get("compID", "").lower() == comp_id.lower()) and
                (not comp_name or row.get("compName", "").lower() == comp_name.lower()) and
                (not cal_year or row.get("CalYear", "").lower() == cal_year.lower()) and
                (not prerios or row.get("PreriosTypeName", "").lower() == prerios.lower()) and
                (not reporting or row.get("ReportingBases", "").lower() == reporting.lower()) and
                (not currency or row.get("Currency", "").lower() == currency.lower())
            )

            if cond:
                results.append({
                    "GC_Attribute": attr,
                    "Proj_Attribute": row["Proj_Attribute"],
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
        # Create Summary
        # -----------------------
        if results:
            df_result = pd.DataFrame(results)

            total = len(df_result)
            matched = (df_result["Comparison"] == "✅ Match").sum()
            mismatched = (df_result["Comparison"] == "❌ Mismatch").sum()
            unmapped_count = len(unmapped)

            # Summary Metrics
            st.subheader("📈 Attribute Summary (After Removing Blank Columns)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Compared", total)
            c2.metric("Matches", matched)
            c3.metric("Mismatches", mismatched)
            c4.metric("Unmapped", unmapped_count)

            # Summary Chart
            fig, ax = plt.subplots()
            ax.bar(["Matched", "Mismatched", "Unmapped"],
                   [matched, mismatched, unmapped_count],
                   color=["green", "red", "gray"])
            ax.set_title("Comparison Summary")
            st.pyplot(fig)

            # -----------------------
            # Filter: All / Mismatches / Matches
            # -----------------------
            st.subheader("🔎 Filter Comparison Results")
            view = st.radio("Select View",
                            ["All Records", "Only Mismatches", "Only Matches"],
                            horizontal=True)

            if view == "Only Mismatches":
                df_view = df_result[df_result["Comparison"] == "❌ Mismatch"]
            elif view == "Only Matches":
                df_view = df_result[df_result["Comparison"] == "✅ Match"]
            else:
                df_view = df_result.copy()

            # Highlight mismatches in red
            def highlight_mismatch(val):
                return "background-color: #ffcccc" if val == "❌ Mismatch" else ""

            st.dataframe(df_view.style.applymap(highlight_mismatch, subset=["Comparison"]))

            # Unmapped list
            if unmapped_count > 0:
                with st.expander("🕵️ Unmapped Attributes"):
                    st.dataframe(pd.DataFrame({"Unmapped_Attributes": list(set(unmapped))}))

            # Excel download
            def to_excel(df1, unmapped_list):
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                    df1.to_excel(writer, index=False, sheet_name="Comparison_Result")
                    pd.DataFrame({"Unmapped_Attributes": list(set(unmapped_list))}).to_excel(
                        writer, index=False, sheet_name="Unmapped_Attributes"
                    )
                return buf.getvalue()

            excel_data = to_excel(df_result, unmapped)

            st.download_button(
                label="⬇️ Download Comparison Report (Excel)",
                data=excel_data,
                file_name="Financials_Comparison_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.warning("No matching data found for the filters applied.")

else:
    st.info("Please upload both Excel files to begin.")