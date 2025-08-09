import io
import os
import calendar
import pandas as pd
import streamlit as st
from datetime import date, datetime

# ---------- Helpers for year/month selection ----------
def list_years(master_df):
    if master_df.empty:
        return []
    return sorted({str(m)[:4] for m in master_df["month"].dropna()})

def months_in_year(year, through_month=None):
    """Return ['YYYY-01', ...] up to through_month (1–12). If None, full year."""
    ym = []
    last = through_month or 12
    for mm in range(1, last + 1):
        ym.append(f"{year}-{mm:02d}")
    return ym

# ---------- Page ----------
st.set_page_config(
    page_title="Referral Sources Tracker",
    page_icon="assets/firm_logo.png",  # favicon/tab icon
    layout="wide",
)

st.title("📈 Referral Sources Tracker")
st.markdown("""
Upload your monthly referral export, map the columns, and click **Append to Master**.  
The app will build a **Referral Source × Month** table. New sources automatically appear with **0** in prior months.
""")

# ---------- Storage paths ----------
DATA_DIR = "data"
MASTER_PATH = os.path.join(DATA_DIR, "referrals_master.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- Utilities ----------
def load_master():
    if os.path.exists(MASTER_PATH):
        try:
            return pd.read_csv(MASTER_PATH)
        except Exception:
            return pd.DataFrame(columns=["referred_person", "referral_source", "month"])
    return pd.DataFrame(columns=["referred_person", "referral_source", "month"])

def save_master(df):
    df.to_csv(MASTER_PATH, index=False)

def normalize_month(val):
    """Return YYYY-MM string for month input that may be a date, string, or pandas Timestamp."""
    if pd.isna(val):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.strftime("%Y-%m")
    s = str(val).strip()
    for fmt in ("%Y-%m", "%Y/%m", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m")
        except Exception:
            pass
    try:
        parsed = pd.to_datetime(s, errors="coerce")
        return parsed.strftime("%Y-%m") if not pd.isna(parsed) else None
    except Exception:
        return None

# ---------- Sidebar ----------
with st.sidebar:
    st.subheader("Master Data")
    master = load_master()
    st.caption(f"Records in master: **{len(master):,}**")
    if st.button("🔄 Clear master data"):
        save_master(pd.DataFrame(columns=["referred_person", "referral_source", "month"]))
        st.success("Master cleared.")
        master = load_master()

    # Show logo in sidebar
    st.image("assets/firm_logo.png", use_column_width=True)
    st.markdown("---")

# ---------- Upload section ----------
st.header("1) Upload Monthly List")
uploaded = st.file_uploader("Drop an Excel/CSV file", type=["xlsx", "xls", "csv"])

if uploaded is not None:
    # Read file
    if uploaded.name.lower().endswith(".csv"):
        candidates = {"CSV": pd.read_csv(uploaded)}
    else:
        xl = pd.ExcelFile(uploaded)
        candidates = {s: xl.parse(s) for s in xl.sheet_names}

    # Choose sheet
    sheet = st.selectbox("Choose a sheet", list(candidates.keys()))
    data = candidates[sheet].copy()

    st.write("Preview:")
    st.dataframe(data.head(20), use_container_width=True)

    # Column mapping
    st.subheader("Map your columns")
    cols = list(data.columns)
    ref_person_col = st.selectbox("Column with **Referred Person Name**", cols, index=0 if cols else None)
    source_col = st.selectbox("Column with **Referral Source**", cols, index=1 if len(cols) > 1 else 0)

    # How to set month
    month_mode = st.radio(
        "How do you want to set the **Month** for these rows?",
        ["Pick a month for all rows", "Use a column from the file"],
        horizontal=True
    )

    # --- Month selection (Month + Year dropdowns) ---
    if month_mode == "Pick a month for all rows":
        current = date.today()
        # You can adjust the year range to your needs
        year_options = list(range(current.year + 1, current.year - 6, -1))  # e.g., [2026, 2025, 2024, ...]
        col_m, col_y = st.columns(2)
        month_num = col_m.selectbox(
            "Month",
            list(range(1, 13)),
            index=current.month - 1,
            format_func=lambda m: calendar.month_name[m]
        )
        year_num = col_y.selectbox(
            "Year",
            year_options,
            index=year_options.index(current.year)
        )
        chosen_month = f"{year_num}-{month_num:02d}"
    else:
        month_col = st.selectbox("Column containing the month/date", cols, index=2 if len(cols) > 2 else 0)
        tmp = data[month_col].head(10).apply(normalize_month)
        st.caption("Conversion preview (first 10 rows): " + ", ".join([str(x) for x in tmp.tolist()]))

    # Append button
    if st.button("➕ Append to Master"):
        df_new = pd.DataFrame({
            "referred_person": data[ref_person_col].astype(str).str.strip(),
            "referral_source": data[source_col].astype(str).str.strip()
        })
        if month_mode == "Pick a month for all rows":
            df_new["month"] = chosen_month
        else:
            df_new["month"] = data[month_col].apply(normalize_month)

        before = len(df_new)
        df_new = df_new.dropna(subset=["referral_source", "month"])
        df_new = df_new[df_new["referral_source"] != ""]
        after = len(df_new)

        master = load_master()
        master = pd.concat([master, df_new], ignore_index=True)
        save_master(master)
        st.success(f"Appended {after} rows (dropped {before - after} incomplete rows).")

# ---------- Explore & Download ----------
st.header("2) Explore & Download Results")
master = load_master()

if len(master) == 0:
    st.info("Upload at least one monthly file to see results.")
else:
    # Year filter + YTD (YTD ends at latest month with DATA, not today)
    years = list_years(master)
    latest_year = years[-1] if years else None

    col_y1, col_y2 = st.columns([2, 1])
    with col_y1:
        year_choice = st.selectbox("Select year", years, index=years.index(latest_year))
    with col_y2:
        use_ytd = st.checkbox("Use Year-to-Date (ends at latest month with data)", value=True)

    # Filter to selected year
    year_mask = master["month"].str.startswith(year_choice)
    master_year = master[year_mask].copy()

    # Determine YTD cutoff based on data
    cutoff_month = None
    if use_ytd:
        months_for_year = (
            master.loc[master["month"].str.startswith(year_choice), "month"]
            .str[-2:].astype(int).sort_values()
        )
        cutoff_month = int(months_for_year.iloc[-1]) if len(months_for_year) else 12
        master_year = master_year[master_year["month"].str[-2:].astype(int) <= cutoff_month]

    if master_year.empty:
        st.info("No data for the selected year/period yet.")
    else:
        # Build pivot for the selected period
        pivot = (
            master_year
            .groupby(["referral_source", "month"], dropna=False)
            .size()
            .reset_index(name="count")
            .pivot(index="referral_source", columns="month", values="count")
            .fillna(0)
            .astype(int)
            .sort_index()
        )

        # Ensure columns cover all months in the period (zero-fill)
        full_months = months_in_year(year_choice, cutoff_month)
        for m in full_months:
            if m not in pivot.columns:
                pivot[m] = 0
        pivot = pivot[full_months]  # Jan..(cutoff)

        # Sorting controls
        st.subheader("Sorting")
        months = ["(Alphabetical)"] + list(pivot.columns)
        sort_choice = st.selectbox("Sort referral sources by:", months, index=0)
        ascending = st.checkbox("Ascending", value=False)

        if sort_choice == "(Alphabetical)":
            pivot_view = pivot.sort_index(ascending=ascending)
        else:
            pivot_view = pivot.sort_values(by=sort_choice, ascending=ascending)

        # Main table
        title_suffix = f"{year_choice}{' (YTD)' if use_ytd else ''}"
        st.subheader(f"Referral Counts by Source × Month — {title_suffix}")
        st.dataframe(pivot_view, use_container_width=True)

        # Monthly totals row
        totals = pd.DataFrame([pivot_view.sum(axis=0)], index=["TOTALS"])
        st.write("**Monthly totals across all sources:**")
        st.dataframe(totals, use_container_width=True)

        # Average per referral source across the shown months (includes zeros)
        st.subheader(f"Average referrals per source — {title_suffix}")
        avg_per_source = pivot[full_months].mean(axis=1).to_frame(name="avg_referrals_per_month")
        avg_per_source_sorted = avg_per_source.sort_values("avg_referrals_per_month", ascending=False)
        st.dataframe(avg_per_source_sorted, use_container_width=True)

        # Downloads (filtered to current year/period)
        def to_excel_bytes(pivot_df, master_df, averages_df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                pivot_df.to_excel(writer, sheet_name="Pivot")
                master_df.to_excel(writer, sheet_name="Master (filtered)", index=False)
                averages_df.to_excel(writer, sheet_name="Averages", index=True)
            return output.getvalue()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                "⬇️ Download Pivot (CSV)",
                data=pivot_view.to_csv().encode("utf-8"),
                file_name=f"referral_pivot_{year_choice}{'_YTD' if use_ytd else ''}.csv",
                mime="text/csv"
            )
        with col2:
            st.download_button(
                "⬇️ Download Master (CSV)",
                data=master_year.to_csv(index=False).encode("utf-8"),
                file_name=f"referrals_master_{year_choice}{'_YTD' if use_ytd else ''}.csv",
                mime="text/csv"
            )
        with col3:
            excel_bytes = to_excel_bytes(pivot_view, master_year, avg_per_source_sorted)
            st.download_button(
                "⬇️ Download Excel (Pivot+Master+Averages)",
                data=excel_bytes,
                file_name=f"referrals_report_{year_choice}{'_YTD' if use_ytd else ''}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

st.caption("Tip: Deploy this on Streamlit Community Cloud to share with your team and update monthly.")
