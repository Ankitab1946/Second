import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Financial Excel Hierarchy Explorer", layout="wide")
st.title("📘 Financial Excel Hierarchy Explorer")

uploaded_file = st.file_uploader("Upload Financials Excel", type=["xlsx", "xls"])

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)
    sheet = st.selectbox("Select a Sheet", xls.sheet_names)

    if sheet:
        # Step 1: Read Excel
        raw = pd.read_excel(uploaded_file, sheet_name=sheet, header=None)
        header_rows = raw.iloc[0:3, :]  # first 3 rows = headers
        data_rows = raw.iloc[3:, :].reset_index(drop=True)

        # Step 2: Build MultiIndex columns
        multi_cols = pd.MultiIndex.from_arrays(header_rows.values, names=["Category", "Subcategory", "Year"])
        df = pd.DataFrame(data_rows.values, columns=multi_cols)
        df.rename(columns={df.columns[0]: ("Section", "", "")}, inplace=True)
        df = df.loc[:, ~df.columns.duplicated()]

        st.subheader("📊 Parsed Data Preview")
        st.dataframe(df.head(10))

        # Step 3: Flatten to long format
        melted = df.melt(
            id_vars=[("Section", "", "")],
            var_name=["Category", "Subcategory", "Year"],
            value_name="Value"
        )
        melted.rename(columns={("Section", "", ""): "Section"}, inplace=True)

        # Clean nulls
        for col in ["Section", "Category", "Subcategory", "Year"]:
            melted[col] = melted[col].fillna("").astype(str).str.strip()

        # Step 4: Dropdown selectors (dynamic)
        st.subheader("🎯 Fetch a Specific Data Point")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            section = st.selectbox(
                "Section",
                sorted(melted["Section"].unique()),
                index=None,
                placeholder="Select a Section"
            )
        with col2:
            options_cat = sorted(melted[melted["Section"] == section]["Category"].unique()) if section else []
            category = st.selectbox("Category", options_cat, index=None, placeholder="Select a Category")
        with col3:
            options_sub = sorted(melted[
                (melted["Section"] == section) &
                (melted["Category"] == category)
            ]["Subcategory"].unique()) if category else []
            subcategory = st.selectbox("Subcategory", options_sub, index=None, placeholder="Select a Subcategory")
        with col4:
            options_year = sorted(melted[
                (melted["Section"] == section) &
                (melted["Category"] == category) &
                (melted["Subcategory"] == subcategory)
            ]["Year"].unique()) if subcategory else []
            year = st.selectbox("Year", options_year, index=None, placeholder="Select a Year")

        # Step 5: Value lookup
        if section and category and subcategory and year:
            result = melted[
                (melted["Section"] == section) &
                (melted["Category"] == category) &
                (melted["Subcategory"] == subcategory) &
                (melted["Year"] == year)
            ]
            if not result.empty:
                val = result["Value"].values[0]
                st.success(f"📈 Value for *{section} → {category} → {subcategory} → {year}* = **{val}**")
            else:
                st.warning("No matching data found.")
        else:
            st.info("Please select all levels to fetch a value.")

        # Step 6: Downloadable data
        st.subheader("📥 Download Flattened Data")

        def to_excel(df):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Flattened_Data")
            return buffer.getvalue()

        excel_bytes = to_excel(melted)
        csv_bytes = melted.to_csv(index=False).encode("utf-8")

        colA, colB = st.columns(2)
        with colA:
            st.download_button(
                label="⬇️ Download as Excel",
                data=excel_bytes,
                file_name=f"{sheet}_Flattened.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with colB:
            st.download_button(
                label="⬇️ Download as CSV",
                data=csv_bytes,
                file_name=f"{sheet}_Flattened.csv",
                mime="text/csv"
            )

        # Optional expanded view
        with st.expander("🔍 View Flattened DataFrame"):
            st.dataframe(melted)
else:
    st.info("Please upload your Excel file to begin.")
