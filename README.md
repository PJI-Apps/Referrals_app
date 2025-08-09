# Referral Sources Tracker (Streamlit)

This app lets you upload monthly referral lists, append them to a master dataset (stored as CSV), and view a Referral Source × Month pivot.
New referral sources appear automatically, with zeros for months they did not refer.

## Quick Start (Local)
1. Install Python 3.10 or 3.11.
2. Create and activate a virtual environment (recommended).
3. Install deps: `pip install -r requirements.txt`
4. Run: `streamlit run referrals_app.py`
5. Open the URL shown in the terminal.

## Deploy to Streamlit Community Cloud (Free)
1. Push `referrals_app.py` and `requirements.txt` to a new GitHub repo.
2. Go to https://streamlit.io/cloud, click **New app**, and select your repo.
3. Set the entrypoint to `referrals_app.py`.
4. Click **Deploy**.

## Using the App
- Upload your monthly export (Excel or CSV).
- Map the **Referred Person**, **Referral Source**, and the **Month** (either pick one month for all rows or use a date column).
- Click **Append to Master**.
- Sort referral sources alphabetically or by a chosen month.
- Download the pivot and master as CSV or a combined Excel file.
