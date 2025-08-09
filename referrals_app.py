
import io
import os
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Referral Sources Tracker", layout="wide")

st.title("📈 Referral Sources Tracker")

st.markdown("""
Upload your monthly referral export, map the columns, and click **Append to Master**.  
The app will build a **Referral Source × Month** table. New sources automatically appear with 0 in prior months.
""")

# Storage paths (Streamlit Cloud persists files within the app repo; locally, this is relative folder)
DATA_DIR = "data"
MASTER_PATH = os.path.join(DATA_DIR, "referrals.parquet")

os.makedirs(DATA_DIR, exist_ok=True)

# --- Utilities ---
def load_master():
    if os.path.exists(MASTER_PATH):
        return pd.read_parquet(MASTER_PATH)
    return pd.DataFrame(columns=["referred_person", "referral_source", "month"])

def save_master(df):
    df.to_parquet(MASTER_PATH, index=False)

def normalize_month(val):
    """Return YYYY-MM string for month input that may be a date, string, or pandas Timestamp."""
    if pd.isna(val):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.strftime("%Y-%m")
    s = str(val).strip()
    # Try parse a variety of common formats
    for fmt in ("%Y-%m", "%Y/%m", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m")
        except Exception:
            pass
    # If it's like "Aug-2025" or "2025 Aug"
    try:
        return pd.to_datetime(s, errors="coerce").strftime("%Y-%m")
    except Exception:
        return None

# --- Sidebar: Master data controls ---
with st.sidebar:
    st.subheader("Master Data")
    master = load_master()
    st.caption(f"Records in master: **{len(master):,}**")
    if st.button("🔄 Clear master data"):
        save_master(pd.DataFrame(columns=["referred_person", "referral_source", "month"]))
        st.success("Master cleared.")
        master = load_master()

# --- File upload section ---
st.header("1) Upload Monthly List")
uploaded = st.file_uploader("Drop an Excel/CSV file", type=["xlsx", "xls", "csv"])

if uploaded is not None:
    # Try to read all sheets or the single CSV
    if uploaded.name.lower().endswith(".csv"):
        candidates = {"CSV": pd.read_csv(uploaded)}
    else:
        xl = pd.ExcelFile(uploaded)
        candidates = {s: xl.parse(s) for s in xl.sheet_names}

    sheet = st.selectbox("Choose a sheet", list(candidates.keys()))
    data = candidates[sheet].copy()

    st.write("Preview:")
    st.dataframe(data.head(20), use_container_width=True)

    # Column mapping
    st.subheader("Map your columns")
    cols = list(data.columns)
    ref_person_col = st.selectbox("Column with **Referred Person Name**", cols, index=0 if cols else None)
    source_col = st.selectbox("Column with **Referral Source**", cols, index=1 if len(cols) > 1 else 0)
    month_mode = st.radio("How do you want to set the **Month** for these rows?", ["Pick a month for all rows", "Use a column from the file"], horizontal=True)

    if month_mode == "Pick a month for all rows":
        month_pick = st.date_input("Pick any date in the referral month")
        chosen_month = pd.Timestamp(month_pick).strftime("%Y-%m") if month_pick else None
    else:
        month_col = st.selectbox("Column containing the month/date", cols, index=2 if len(cols) > 2 else 0)
        # Show a quick conversion preview
        tmp = data[month_col].head(10).apply(normalize_month)
        st.caption("Conversion preview (first 10 rows): " + ", ".join([str(x) for x in tmp.tolist()]))

    # Build a normalized frame
    if st.button("➕ Append to Master"):
        df_new = pd.DataFrame({
            "referred_person": data[ref_person_col].astype(str).str.strip(),
            "referral_source": data[source_col].astype(str).str.strip()
        })
        if month_mode == "Pick a month for all rows":
            df_new["month"] = chosen_month
        else:
            df_new["month"] = data[month_col].apply(normalize_month)

        # Drop rows missing critical fields
        before = len(df_new)
        df_new = df_new.dropna(subset=["referral_source", "month"])
        df_new = df_new[df_new["referral_source"] != ""]
        after = len(df_new)

        # Append and save
        master = load_master()
        master = pd.concat([master, df_new], ignore_index=True)
        save_master(master)
        st.success(f"Appended {after} rows (dropped {before - after} incomplete rows).")

st.header("2) Explore & Download Results")
master = load_master()

if len(master) == 0:
    st.info("Upload at least one monthly file to see results.")
else:
    # Build pivot: counts per source per month
    pivot = (
        master
        .groupby(["referral_source", "month"], dropna=False)
        .size()
        .reset_index(name="count")
        .pivot(index="referral_source", columns="month", values="count")
        .fillna(0)
        .astype(int)
        .sort_index()
    )

    # Ensure all months are sorted chronological
    if len(pivot.columns):
        cols_sorted = sorted(pivot.columns, key=lambda s: (s is None, s))
        pivot = pivot[cols_sorted]

    # Sorting controls
    st.subheader("Sorting")
    months = ["(Alphabetical)"] + list(pivot.columns)
    sort_choice = st.selectbox("Sort referral sources by:", months, index=0)
    ascending = st.checkbox("Ascending", value=False)

    if sort_choice == "(Alphabetical)":
        pivot_view = pivot.sort_index(ascending=ascending)
    else:
        # Sort by the selected month column (nonexistent values default to 0)
        pivot_view = pivot.sort_values(by=sort_choice, ascending=ascending)

    st.subheader("Referral Counts by Source × Month")
    st.dataframe(pivot_view, use_container_width=True)

    # Totals row
    totals = pd.DataFrame([pivot_view.sum(axis=0)], index=["TOTALS"])
    st.write("**Monthly totals across all sources:**")
    st.dataframe(totals, use_container_width=True)

    # Downloads
    def to_excel_bytes(pivot_df, master_df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            pivot_df.to_excel(writer, sheet_name="Pivot")
            master_df.to_excel(writer, sheet_name="Master", index=False)
        return output.getvalue()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "⬇️ Download Pivot (CSV)",
            data=pivot_view.to_csv().encode("utf-8"),
            file_name="referral_pivot.csv",
            mime="text/csv"
        )
    with col2:
        st.download_button(
            "⬇️ Download Master (CSV)",
            data=master.to_csv(index=False).encode("utf-8"),
            file_name="referrals_master.csv",
            mime="text/csv"
        )
    with col3:
        excel_bytes = to_excel_bytes(pivot_view, master)
        st.download_button(
            "⬇️ Download Excel (Pivot+Master)",
            data=excel_bytes,
            file_name="referrals_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

st.caption("Tip: Deploy this on Streamlit Community Cloud to share with your team and update monthly.")
