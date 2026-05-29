"""
Page 1 – Man Hours Overview
"""
import json
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime

# ── Config ───────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MH_DIR = BASE / "uploads" / "manhours"
MH_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()


def get_active_mh_file():
    """Return (path, date_str) for the most recent man hours file."""
    today_file = MH_DIR / f"{TODAY}.xlsx"
    if today_file.exists():
        return today_file, TODAY
    candidates = sorted(MH_DIR.glob("*.xlsx"), reverse=True)
    for c in candidates:
        return c, c.stem
    return None, None


MH_XLSX, MH_DATE = get_active_mh_file()
MH_JSON = MH_DIR / f"{TODAY}_processed.json"


def show_header_logo():
    import base64
    from pathlib import Path as _Path

    logo_path = _Path(__file__).parent.parent / "static" / "logo.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()

        st.markdown(f"""
        <style>
        [data-testid="stHeader"] {{
            background: linear-gradient(90deg, #1565C0 0%, #2196F3 100%);
            padding: 0.5rem 1rem;
        }}
        .header-logo {{
            position: fixed;
            top: 0.5rem;
            right: 1rem;
            height: 80px;
            z-index: 999;
            background: white;
            padding: 0.3rem 0.8rem;
            border-radius: 8px;
        }}
        </style>
        <img src="data:image/png;base64,{logo_b64}" class="header-logo">
        """, unsafe_allow_html=True)


st.set_page_config(page_title="Man Hours – Warehouse Ops", page_icon="👷", layout="wide")
show_header_logo()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Warehouse Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_mh")
            if st.button("Login", key="admin_login_mh"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_mh"):
            st.session_state["admin_logged_in"] = False
            st.rerun()

        st.markdown("### 📤 Upload Man Hours")
        today_xlsx = MH_DIR / f"{TODAY}.xlsx"
        uploaded = st.file_uploader(
            "Upload today's Auto Man Hours .xlsx file",
            type=["xlsx"],
            key="mh_upload",
            help="This file should be uploaded once per day.",
        )
        if uploaded:
            with open(today_xlsx, "wb") as f:
                f.write(uploaded.read())
            st.success("Saved ✅")
            st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────────────

TIER_COLORS = {
    "Trainee": "#EF5350",      # Red
    "Signed Off": "#FF9800",    # Orange
    "Competent": "#1565C0",     # Blue (matching primary)
    "Master": "#4CAF50",        # Green
}


def parse_service(yrs_mths: str) -> float:
    """Return total weeks from 'X Years / Y Months' string."""
    try:
        parts = str(yrs_mths).replace("Years", "").replace("Year", "").replace("Months", "").replace("Month", "").split("/")
        years = int(parts[0].strip()) if parts[0].strip().isdigit() or parts[0].strip().lstrip('-').isdigit() else 0
        months = int(parts[1].strip()) if len(parts) > 1 and (parts[1].strip().isdigit() or parts[1].strip().lstrip('-').isdigit()) else 0
        total_months = years * 12 + months
        return total_months * 4.33
    except Exception:
        return 0.0


def weeks_to_tier(weeks: float) -> str:
    if weeks < 2:
        return "Trainee"
    elif weeks < 4:
        return "Signed Off"
    elif weeks < 8:
        return "Competent"
    else:
        return "Master"


def load_manhours(xlsx_path: Path) -> pd.DataFrame:
    """
    Parse Auto Man Hours xlsx (header at row index 9).
    Returns a cleaned DataFrame with employee info + man hrs.
    """
    df = pd.read_excel(xlsx_path, header=9, engine="openpyxl")
    df.columns = df.columns.str.strip()

    keep_meta = [
        "Site", "Hire Date", "Rehire Date",
        "Years of Service (Yrs/Mths)", "Company Name",
        "Cust-Emp Nr", "Cust-Oracle Username",
        "Name Surname", "Class", "Department", "Occupation",
    ]
    keep_meta = [c for c in keep_meta if c in df.columns]
    df = df.dropna(subset=["Cust-Oracle Username"])

    man_hrs_cols = [c for c in df.columns if str(c).startswith("Man Hrs")]
    today_mh_col = man_hrs_cols[0] if man_hrs_cols else None

    in_cols = [c for c in df.columns if str(c) == "In" or str(c).startswith("In.")]

    result = df[keep_meta].copy()
    if today_mh_col:
        result["Today_Man_Hrs"] = pd.to_numeric(df[today_mh_col], errors="coerce").fillna(0)
    else:
        result["Today_Man_Hrs"] = 0

    if in_cols:
        result["Present"] = df[in_cols[0]].notna()
    else:
        result["Present"] = result["Today_Man_Hrs"] > 0

    result["Service_Weeks"] = result["Years of Service (Yrs/Mths)"].apply(parse_service)
    result["Skill_Tier"] = result["Service_Weeks"].apply(weeks_to_tier)

    result = result.rename(columns={
        "Years of Service (Yrs/Mths)": "Service",
        "Company Name": "Company",
        "Cust-Oracle Username": "Username",
    })
    return result


def save_processed_json(df: pd.DataFrame):
    """Save processed employee lookup as JSON."""
    lookup = {}
    for _, row in df.iterrows():
        username = str(row.get("Username", "")).strip()
        if not username:
            continue
        full = str(row.get("Name Surname", "")).strip()
        parts = full.rsplit(" ", 1)
        name = parts[0] if len(parts) > 1 else full
        surname = parts[1] if len(parts) > 1 else ""
        lookup[username] = {
            "full_name": full,
            "name": name,
            "surname": surname,
            "department": str(row.get("Department", "")),
            "occupation": str(row.get("Occupation", "")),
            "company": str(row.get("Company", "")),
            "service": str(row.get("Service", "")),
            "skill_tier": row.get("Skill_Tier", "Trainee"),
        }
    MH_JSON.write_text(json.dumps(lookup, indent=2))


def color_tier(tier):
    color = TIER_COLORS.get(tier, "#888")
    return f"color: {color}; font-weight: bold"


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("👷 Man Hours Overview")
st.caption(f"Date: {TODAY}")

if MH_XLSX and MH_XLSX.exists():
    st.success("✅ Man Hours loaded")
    if MH_DATE != TODAY:
        st.caption(f"📂 Using data from {MH_DATE}")
else:
    st.info("⬆️ Upload Man Hours in the sidebar (Admin login required)")

if MH_XLSX and MH_XLSX.exists():
    try:
        df = load_manhours(MH_XLSX)
        save_processed_json(df)
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        st.stop()
else:
    st.stop()

st.divider()

# ── Summary Cards ────────────────────────────────────────────────────────────
st.subheader("📊 Workforce Summary")

total_present = int(df["Present"].sum())
total_absent = len(df) - total_present
trainees = int((df["Skill_Tier"] == "Trainee").sum())
signed_off = int((df["Skill_Tier"] == "Signed Off").sum())
competent = int((df["Skill_Tier"] == "Competent").sum())
masters = int((df["Skill_Tier"] == "Master").sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("✅ Present", total_present)
c2.metric("❌ Absent", total_absent)
c3.metric("🔴 Trainees", trainees)
c4.metric("🟠 Signed Off", signed_off)
c5.metric("🔵 Competent", competent)
c6.metric("🟢 Masters", masters)

# ── Company Breakdown (Present employees only) ────────────────────────────────
st.subheader("📊 Present Employees by Company")

with st.expander("View Company Breakdown", expanded=True):
    # Filter to present employees only
    present_df = df[df["Present"] == True]
    companies = sorted(present_df["Company"].dropna().unique().tolist())
    for company_name in companies:
        cdf = present_df[present_df["Company"] == company_name]
        c_present = int(cdf["Present"].sum())
        c_trainees = int((cdf["Skill_Tier"] == "Trainee").sum())
        c_signed_off = int((cdf["Skill_Tier"] == "Signed Off").sum())
        c_competent = int((cdf["Skill_Tier"] == "Competent").sum())
        c_masters = int((cdf["Skill_Tier"] == "Master").sum())

        st.markdown(f"**{company_name}**")
        cols = st.columns(5)
        cols[0].metric("✅ Present", c_present)
        cols[1].metric("🔴 Trainees", c_trainees)
        cols[2].metric("🟠 Signed Off", c_signed_off)
        cols[3].metric("🔵 Competent", c_competent)
        cols[4].metric("🟢 Masters", c_masters)

st.divider()

# ── Employee Table ───────────────────────────────────────────────────────────
st.subheader("👥 Employee Details")

# Inline filters (horizontal row)
col_f1, col_f2 = st.columns(2)
with col_f1:
    depts = ["All"] + sorted(df["Department"].dropna().unique().tolist())
    dept_filter = st.selectbox("Filter by Department", depts)
with col_f2:
    tiers = ["All", "Trainee", "Signed Off", "Competent", "Master"]
    tier_filter = st.selectbox("Filter by Skill Tier", tiers)

display = df.copy()
if dept_filter != "All":
    display = display[display["Department"] == dept_filter]
if tier_filter != "All":
    display = display[display["Skill_Tier"] == tier_filter]

show_cols = [
    "Name Surname", "Department", "Occupation", "Company",
    "Service", "Skill_Tier", "Today_Man_Hrs", "Present",
]
show_cols = [c for c in show_cols if c in display.columns]
display_out = display[show_cols].rename(columns={
    "Name Surname": "Name & Surname",
    "Skill_Tier": "Skill Tier",
    "Today_Man_Hrs": "Today's Man Hrs",
})


def highlight_tier(val):
    return color_tier(val)


styled = display_out.style.map(highlight_tier, subset=["Skill Tier"])
st.dataframe(styled, use_container_width=True, height=450)

st.caption(f"Showing {len(display_out)} of {len(df)} employees")

# ── Skill Tier by Agency — Operational Roles ─────────────────────────────────
st.subheader("📊 Skill Tier by Agency — Operational Roles (Present Today)")

OPERATIONAL_OCCUPATIONS = [
    # Picking
    "Picker", "Picking Trainee",
    # Packing
    "Packer", "Packing Trainee",
    # Putaway
    "Putaway Filers", "Putaway Grid Sorter", "Putaways Admin", "Putaway Admin", "Filing Trainee",
    # Receiving
    "Receivers", "Receiving Trainee", "Unloaders",
]

TIER_ORDER = ["Trainee", "Signed Off", "Competent", "Master"]

ops_df = df[df["Present"] == True].copy()
ops_df = ops_df[ops_df["Occupation"].isin(OPERATIONAL_OCCUPATIONS)]

n_ops = len(ops_df)
k_agencies = ops_df["Company"].nunique()

st.caption(f"Showing {n_ops} present operational employees across {k_agencies} agencies")

if ops_df.empty:
    st.info("No operational employees present today matching the selected occupations.")
else:
    tier_pivot = (
        ops_df.groupby(["Company", "Skill_Tier"])
        .size()
        .reset_index(name="Count")
        .pivot(index="Company", columns="Skill_Tier", values="Count")
        .fillna(0)
        .astype(int)
    )
    # Ensure all tier columns exist in order
    for tier in TIER_ORDER:
        if tier not in tier_pivot.columns:
            tier_pivot[tier] = 0
    tier_pivot = tier_pivot[TIER_ORDER]
    tier_pivot["Total"] = tier_pivot.sum(axis=1)
    st.dataframe(tier_pivot, use_container_width=True, hide_index=False)
