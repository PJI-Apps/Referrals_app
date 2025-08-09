import io
import os
import calendar
import pandas as pd
import streamlit as st
import yaml
import streamlit_authenticator as stauth
from datetime import date, datetime

# =========================
# 🔐 AUTHENTICATION (YAML in Secrets)
# =========================
# In Streamlit Cloud → Settings → Secrets (TOML) add:
#
# [auth_config]
# config = """
# credentials:
#   usernames:
#     kelly:
#       name: Kelly Graham
#       email: kgraham@pjilaw.com
#       password: "$2b$12$...."  # bcrypt hash
# cookie:
#   name: referrals_app_cookie
#   key: "LONG_RANDOM_STRING_32+CHARS"
#   expiry_days: 30
# preauthorized:
#   emails:
#     - kgraham@pjilaw.com
# """
#
st.set_page_config(page_title="Referral Sources Tracker",
                   page_icon="assets/firm_logo.png",
                   layout="wide")

# Load config from secrets and gate the app
try:
    config = yaml.safe_load(st.secrets["auth_config"]["config"])

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
        config.get("preauthorized", {}).get("emails", []),
    )

    fields = {"Form name": "Login", "Username": "Username", "Password": "Password"}
    name, auth_status, username = authenticator.login(fields=fields, location="main")


    if auth_status is False:
        st.error("Username/password is incorrect")
        st.stop()
    elif auth_status is None:
        st.warning("Please enter your username and password")
        st.stop()
    else:
        with st.sidebar:
            authenticator.logout("Logout", "sidebar")
            st.caption(f"Signed in as **{name}**")
except Exception as e:
    st.error("Authentication is not configured correctly. Check your **Secrets**.")
    st.exception(e)
    st.stop()

# =========================
# App helpers / utilities
# =========================
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
            df = pd.read_csv(MASTER_PATH)
            # Ensure required columns exist
            for col in ["referred_person", "referral_source", "month"]:
                if col not in df.columns:
                    df[col] = pd.Series(dtype="object")
            # Optional column for rollback
            if "batch_id" not in df.columns:
                df["batch_id"] = pd.NA
            # Coerce month to YYYY-MM strings
            df["month"] = df["month"].astype(str).str.slice(0, 7)
            return df[["referred_person", "referral_source", "month", "batch_id"]]
        except Exception:
            pass
    # Empty master
    return pd.DataFrame(columns=["referred_person", "referral_source", "month", "batch_id"])

def save_master(df):
    # Save a stable column order
    cols = ["referred_person", "referral_source", "month", "batch_id"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df[cols].to_csv(MASTER_PATH, index=False)

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

    # Undo (delete) a past upload by batch_id
    batches = master.dropna(subset=["batch_id"])
    if len(batches):
        st.markdown("**Undo a past upload (batch):**")
        agg = (batches
               .groupby("batch_id")
               .agg(rows=("referred_person", "size"),
                    months=("month", lambda s: ", ".join(sorted(pd.Series(s).dropna().unique())[:6]))))
        agg = agg.sort_index(ascending=False)
        batch_labels = [f"{idx} • {row.rows} rows • {row.months}" for idx, row in agg.iterrows()]
        batch_ids = list(agg.index)
        sel_label = st.selectbox("Select batch to delete", batch_labels, key="sel_batch") if len(batch_labels) else None
        if sel_label:
            sel_id = batch_ids[batch_labels.index(sel_label)]
            if st.button("🗑 Delete selected batch", key="delete_batch_btn"):
                master = master[~(master["batch_id"] == sel_id)]
                save_master(master)
                st.success(f"Deleted batch {sel_id}.")
                st.stop()

    # Clear all (nuclear option)
    if st.button("🧹 Clear ALL master data"):
        save_master(pd.DataFrame(columns=["referred_person", "referral_source", "month", "batch_id"]))
        st.success("Master cleared.")
        st.stop()

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
        year_options = list(range(current.year + 1, current.year - 6, -1))  # [next year .. current-5]
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

        # Drop blanks / bad
        before = len(df_new)
        df_new = df_new.dropna(subset=["referral_source", "month"])
        df_new = df_new[df_new["referral_source"] != ""]
        after = len(df_new)

        # Tag this upload as a batch for rollback
        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
        df_new["batch_id"] = batch_id

        master = load_master()
        master = pd.concat([master, df_new], ignore_index=True)
        save_master(master)
        st.success(f"Appended {after} rows (dropped {before - after} incomplete rows). Batch ID: {batch_id}")

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
                data=master_year.drop(columns=["batch_id"], errors="ignore").to_csv(index=False).encode("utf-8"),
                file_name=f"referrals_master_{year_choice}{'_YTD' if use_ytd else ''}.csv",
                mime="text/csv"
            )
        with col3:
            excel_bytes = to_excel_bytes(
                pivot_view,
                master_year.drop(columns=["batch_id"], errors="ignore"),
                avg_per_source_sorted
            )
            st.download_button(
                "⬇️ Download Excel (Pivot+Master+Averages)",
                data=excel_bytes,
                file_name=f"referrals_report_{year_choice}{'_YTD' if use_ytd else ''}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ---------- Row editor (surgical deletes) ----------
st.header("3) Edit / Delete Specific Rows")
master = load_master()

if len(master) == 0:
    st.info("No data yet.")
else:
    # Filters
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        months_all = sorted([m for m in master["month"].dropna().unique()])
        month_filter = st.selectbox("Month", ["(All)"] + months_all, index=0)
    with col_f2:
        sources_all = sorted([s for s in master["referral_source"].dropna().unique()])
        source_filter = st.multiselect("Referral source(s)", sources_all, default=[])
    with col_f3:
        person_query = st.text_input("Filter by referred person (contains)", value="")

    # Build mask
    mask = pd.Series(True, index=master.index)
    if month_filter != "(All)":
        mask &= master["month"] == month_filter
    if source_filter:
        mask &= master["referral_source"].isin(source_filter)
    if person_query.strip():
        mask &= master["referred_person"].astype(str).str.contains(person_query.strip(), case=False, na=False)

    edit_df = master.loc[mask].copy()
    if edit_df.empty:
        st.info("No rows match your filters.")
    else:
        # Use index as hidden row-id and add a checkbox column
        edit_df = edit_df.assign(**{"Delete?": False})
        edited = st.data_editor(
            edit_df,
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            column_config={
                "referred_person": st.column_config.TextColumn("Referred person", disabled=True),
                "referral_source": st.column_config.TextColumn("Referral source", disabled=True),
                "month": st.column_config.TextColumn("Month (YYYY-MM)", disabled=True),
                "batch_id": st.column_config.TextColumn("Batch ID", disabled=True),
                "Delete?": st.column_config.CheckboxColumn("Delete?")
            },
            key="row_editor"
        )

        col_d1, col_d2 = st.columns([1, 4])
        with col_d1:
            if st.button("🗑 Delete checked rows", type="secondary"):
                # Build a per-row boolean mask; fill NAs as False just in case
                delete_mask = edited["Delete?"].fillna(False).astype(bool)

                # Get the original row indices corresponding to the checked rows
                to_delete_idx = edited.index[delete_mask]

            if len(to_delete_idx) == 0:
                st.warning("No rows were checked for deletion.")
            else:
                master2 = master.drop(index=to_delete_idx, errors="ignore")
                save_master(master2)
                st.success(f"Deleted {len(to_delete_idx)} row(s).")
                st.stop()

        with col_d2:
            st.caption("Tip: narrow the list using filters, tick **Delete?**, then click the button.")
