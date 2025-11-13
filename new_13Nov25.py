import streamlit as st
import pandas as pd
import openpyxl
import io

st.set_page_config(page_title="Financial Excel Flattener", layout="wide")

# ----------------------------------------------------
# Core function: Load Excel + Flatten Headers
# ----------------------------------------------------
def load_excel_flatten(file, sheet_name=0):
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb[sheet_name] if isinstance(sheet_name, str) else wb.worksheets[sheet_name]

    max_row = ws.max_row
    max_col = ws.max_column

    grid = [[None for _ in range(max_col)] for _ in range(max_row)]

    # fill normal cells
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            grid[r-1][c-1] = ws.cell(r, c).value

    # expand merged cells
    for merged in ws.merged_cells.ranges:
        min_row, min_col, max_row_m, max_col_m = merged.bounds
        top_left_val = grid[min_row-1][min_col-1]
        for r in range(min_row, max_row_m + 1):
            for c in range(min_col, max_col_m + 1):
                grid[r-1][c-1] = top_left_val

    df = pd.DataFrame(grid)

    # forward-fill header area
    df = df.ffill(axis=0)  # vertical
    df = df.ffill(axis=1)  # horizontal

    # detect header depth (first numeric row = start of data)
    header_row = df.applymap(lambda x: isinstance(x, (int, float))).any(axis=1).idxmax()

    header_block = df.iloc[:header_row]

    # flatten header labels
    flat_headers = (
        header_block.astype(str)
        .replace("nan", "")
        .apply(lambda col: [c for c in col if c != ""])
        .apply(lambda parts: "_".join(parts))
    )

    df.columns = flat_headers

    flat_df = df.iloc[header_row:].reset_index(drop=True)

    return flat_df


# ----------------------------------------------------
# Streamlit UI
# ----------------------------------------------------
st.title("📊 Financial Excel Flattener")
st.write(
    """
    Upload **any messy financial Excel** containing:
    - 📌 Merged cells  
    - 📌 Multi-level headers  
    - 📌 Horizontal + vertical headers  
    - 📌 Financial statement structures  
      
    This tool will **flatten & clean** the data for analysis or further mapping.
    """
)

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])

if uploaded_file:
    st.success("File uploaded successfully!")

    # list sheet names
    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
    sheet_names = wb.sheetnames

    sheet = st.selectbox("Select Sheet to Flatten", sheet_names)

    if st.button("Flatten Data"):
        with st.spinner("Flattening... Please wait..."):
            df_flat = load_excel_flatten(uploaded_file, sheet)

        st.subheader("📄 Flattened Output Preview")
        st.dataframe(df_flat, use_container_width=True)

        # download as Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_flat.to_excel(writer, index=False, sheet_name="Flattened")

        st.download_button(
            label="📥 Download Flattened Excel",
            data=output.getvalue(),
            file_name="flattened_financials.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("Please upload an Excel file to begin.")