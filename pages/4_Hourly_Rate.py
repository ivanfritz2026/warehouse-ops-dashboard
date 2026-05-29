"""
Page 4 – Hourly Rate Detail
"""
import json
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime

# ── Config ───────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MH_DIR = BASE / "uploads" / "manhours"
DT_DIR = BASE / "uploads" / "deadtime"
DT_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()
TODAY_DT_DIR = DT_DIR / TODAY
TODAY_DT_DIR.mkdir(parents=True, exist_ok=True)

DEPT_CONFIG = {
    "picking": ("Picking", "Total Picked"),
    "packing": ("Packing", "Packed QTY"),
    "putaway": ("Putaway", "Total Units Filed"),
    "receiving": ("Receiving", "Total Received"),
}

TIER_COLORS = {
    "Trainee": "#EF5350",      # Red
    "Signed Off": "#FF9800",    # Orange
    "Competent": "#1565C0",     # Blue (matching primary)
    "Master": "#4CAF50",        # Green
}


def get_active_mh_json():
    """Return path to the most recent processed MH JSON."""
    today_json = MH_DIR / f"{TODAY}_processed.json"
    if today_json.exists():
        return today_json
    candidates = sorted(MH_DIR.glob("*_processed.json"), reverse=True)
    for c in candidates:
        return c
    return None


def get_active_dt_dir():
    """Return (path, date_str) for the most recent deadtime folder with CSVs."""
    today_dir = DT_DIR / TODAY
    if today_dir.exists() and any(today_dir.glob("*.csv")):
        return today_dir, TODAY
    candidates = sorted(
        [d for d in DT_DIR.iterdir() if d.is_dir() and any(d.glob("*.csv"))],
        reverse=True,
    )
    for c in candidates:
        return c, c.name
    return None, None


mh_json_path = get_active_mh_json()
active_dt_dir, active_dt_date = get_active_dt_dir()


def show_header_logo():
    import base64
    from pathlib import Path
    logo_path = Path(__file__).parent / "static" / "logo.png"
    # For pages subfolder, go up one level
    if not logo_path.exists():
        logo_path = Path(__file__).parent.parent / "static" / "logo.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""
        <style>
        [data-testid="stHeader"] {{
            background: linear-gradient(90deg, #1565C0 0%, #2196F3 100%);
        }}
        .logo-left {{
            position: fixed;
            top: 4px;
            left: 4rem;
            height: 52px;
            z-index: 9999;
            border-radius: 6px;
            padding: 2px 8px;
            background: transparent;
        }}
        </style>
        <img src="data:image/png;base64,{logo_b64}" class="logo-left">
        """, unsafe_allow_html=True)


st.set_page_config(page_title="Hourly Rate – Takealot Warehouse Ops", page_icon="⏱️", layout="wide")
show_header_logo()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Takealot Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_hr")
            if st.button("Login", key="admin_login_hr"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_hr"):
            st.session_state["admin_logged_in"] = False
            st.rerun()

        st.markdown("### 📤 Upload Reports")
        for dk in DEPT_CONFIG.keys():
            display_name, _ = DEPT_CONFIG[dk]
            uploaded_files = st.file_uploader(
                f"{display_name}",
                type=["csv"],
                key=f"hr_upload_{dk}",
                accept_multiple_files=True,
            )
            if uploaded_files:
                for f in uploaded_files:
                    ts = datetime.now().strftime("%H-%M-%S")
                    dest = TODAY_DT_DIR / f"{ts}_{dk}.csv"
                    dest.write_bytes(f.read())
                st.success(f"{len(uploaded_files)} file(s) saved ✅")


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_employee_lookup() -> dict:
    if mh_json_path and mh_json_path.exists():
        return json.loads(mh_json_path.read_text())
    return {}


def load_dept_data(dept_key: str) -> pd.DataFrame | None:
    if active_dt_dir is None:
        return None
    files = sorted(active_dt_dir.glob(f"*_{dept_key}.csv"))
    if not files:
        return None
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception:
            pass
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def color_tier_val(val):
    color = TIER_COLORS.get(val, "#888")
    return f"color: {color}; font-weight: bold"


# ── Main UI ───────────────────────────────────────────────────────────────────

st.title("⏱️ Hourly Rate Detail")
st.caption(f"Date: {TODAY}")

if active_dt_date and active_dt_date != TODAY:
    st.caption(f"📂 Using data from {active_dt_date}")

# ── Load employee lookup ──────────────────────────────────────────────────────
lookup = load_employee_lookup()

# ── Build unified table from all dept data ────────────────────────────────────
all_frames = []
for dk, (display_name, units_col) in DEPT_CONFIG.items():
    df_raw = load_dept_data(dk)
    if df_raw is None or df_raw.empty:
        continue
    df_raw = df_raw.copy()
    if units_col in df_raw.columns:
        df_raw["Units"] = pd.to_numeric(df_raw[units_col], errors="coerce").fillna(0)
    else:
        df_raw["Units"] = 0
    if "Dead Time (Mins)" in df_raw.columns:
        df_raw["Dead Time (Mins)"] = pd.to_numeric(df_raw["Dead Time (Mins)"], errors="coerce").fillna(0)
    else:
        df_raw["Dead Time (Mins)"] = 0
    df_raw["Dept_Key"] = dk
    df_raw["Dept_Display"] = display_name
    all_frames.append(df_raw[["Username", "Hour", "Units", "Dead Time (Mins)", "Dept_Key", "Dept_Display"]])

if not all_frames:
    st.info("📭 No deadtime data uploaded yet. Use the sidebar uploaders (Admin login required).")
    st.stop()

combined = pd.concat(all_frames, ignore_index=True)
combined["Hour"] = pd.to_numeric(combined["Hour"], errors="coerce")
combined = combined.dropna(subset=["Hour"])
combined["Hour"] = combined["Hour"].astype(int)

# ── Pivot: username × hour → units ───────────────────────────────────────────
hour_pivot = (
    combined.groupby(["Username", "Hour"])["Units"]
    .sum()
    .reset_index()
    .pivot(index="Username", columns="Hour", values="Units")
    .fillna(0)
    .reset_index()
)

hour_cols_raw = [c for c in hour_pivot.columns if c != "Username"]
hour_rename = {h: f"Hr {h}" for h in hour_cols_raw}
hour_pivot = hour_pivot.rename(columns=hour_rename)
hr_cols = [f"Hr {h}" for h in sorted(hour_cols_raw)]

# ── Cast hour columns to int ──────────────────────────────────────────────────
hour_pivot[hr_cols] = hour_pivot[hr_cols].astype(int)

# ── Dead time per user ────────────────────────────────────────────────────────
dead_time_per_user = (
    combined.groupby("Username")["Dead Time (Mins)"]
    .sum()
    .reset_index()
    .rename(columns={"Dead Time (Mins)": "Total Dead Time (Mins)"})
)

# ── Merge with employee lookup ────────────────────────────────────────────────
def get_attr(username, attr):
    return lookup.get(str(username), {}).get(attr, "Unknown")

result = hour_pivot.merge(dead_time_per_user, on="Username", how="left")
result["Total Dead Time (Mins)"] = result["Total Dead Time (Mins)"].fillna(0).astype(int)

result["Name"] = result["Username"].apply(lambda u: get_attr(u, "name"))
result["Surname"] = result["Username"].apply(lambda u: get_attr(u, "surname"))
result["Occupation"] = result["Username"].apply(lambda u: get_attr(u, "occupation"))
result["Department"] = result["Username"].apply(lambda u: get_attr(u, "department"))
result["Company"] = result["Username"].apply(lambda u: get_attr(u, "company"))
result["Tier"] = result["Username"].apply(lambda u: get_attr(u, "skill_tier"))

# ── Inline filters (4 columns: Dept, Occupation, Company, Tier) ──────────────
f1, f2, f3, f4 = st.columns(4)

with f1:
    all_depts = sorted(result["Department"].dropna().unique().tolist())
    dept_filter = st.selectbox("Department", ["All"] + all_depts, key="hr_dept")

# Apply dept filter before populating occupation options
result_after_dept = result.copy()
if dept_filter != "All":
    result_after_dept = result_after_dept[result_after_dept["Department"] == dept_filter]

with f2:
    all_occs = sorted(result_after_dept["Occupation"].dropna().unique().tolist())
    occ_filter = st.selectbox("Occupation", ["All"] + all_occs, key="hr_occ")

with f3:
    all_companies = sorted(result["Company"].dropna().unique().tolist())
    company_filter = st.selectbox("Company", ["All"] + all_companies, key="hr_company")

with f4:
    all_tiers = ["All", "Trainee", "Signed Off", "Competent", "Master"]
    tier_filter = st.selectbox("Tier", all_tiers, key="hr_tier")

# ── Apply filters ─────────────────────────────────────────────────────────────
display = result.copy()
if dept_filter != "All":
    display = display[display["Department"] == dept_filter]
if occ_filter != "All":
    display = display[display["Occupation"] == occ_filter]
if company_filter != "All":
    display = display[display["Company"] == company_filter]
if tier_filter != "All":
    display = display[display["Tier"] == tier_filter]

# ── Summary metrics ───────────────────────────────────────────────────────────
total_employees = len(display)
total_units = int(display[hr_cols].sum().sum())
total_dead_time = int(display["Total Dead Time (Mins)"].sum())

m1, m2, m3 = st.columns(3)
m1.metric("👤 Total Employees", total_employees)
m2.metric("📦 Total Units Produced", f"{total_units:,}")
m3.metric("⏱️ Total Dead Time (Mins)", f"{total_dead_time:,}")

st.divider()

# ── Build ordered display columns ─────────────────────────────────────────────
meta_cols = ["Username", "Name", "Surname", "Occupation", "Department", "Company", "Tier", "Total Dead Time (Mins)"]
display_cols = meta_cols + hr_cols
display_out = display[display_cols].reset_index(drop=True)

# Cast all hour columns and dead time to int
display_out[hr_cols] = display_out[hr_cols].astype(int)
display_out["Total Dead Time (Mins)"] = display_out["Total Dead Time (Mins)"].astype(int)

# ── Totals row above main table ───────────────────────────────────────────────
totals_data = {
    "Username": ["** TOTAL **"],
    "Name": [""],
    "Surname": [""],
    "Occupation": [""],
    "Department": [""],
    "Company": [""],
    "Tier": [""],
    "Total Dead Time (Mins)": [int(display_out["Total Dead Time (Mins)"].sum())],
}
for hc in hr_cols:
    totals_data[hc] = [int(display_out[hc].sum())]

totals_df = pd.DataFrame(totals_data)
st.markdown("**📊 Totals**")
st.dataframe(
    totals_df,
    use_container_width=True,
    hide_index=True,
    height=60,
)

# ── Main table ────────────────────────────────────────────────────────────────
styled = display_out.style.map(color_tier_val, subset=["Tier"])
st.dataframe(styled, use_container_width=True)

st.divider()

# ── Summary by Department ─────────────────────────────────────────────────────
st.subheader("📊 Summary by Department & Agency")

# Per-Department summary
st.markdown("**By Department**")
if hr_cols:
    dept_units = display.groupby("Department")[hr_cols].sum().sum(axis=1).astype(int)
else:
    dept_units = pd.Series(dtype=int)

dept_summary = (
    display.groupby("Department")
    .agg(
        Employees=("Username", "count"),
        Total_Dead_Time=("Total Dead Time (Mins)", "sum"),
    )
    .reset_index()
)
dept_summary["Total Units"] = dept_units.values if len(dept_units) > 0 else 0
dept_summary["Total Dead Time (Mins)"] = dept_summary["Total_Dead_Time"].astype(int)
dept_summary["Total Units"] = dept_summary["Total Units"].astype(int)
dept_summary_display = dept_summary[["Department", "Employees", "Total Units", "Total Dead Time (Mins)"]].reset_index(drop=True)
st.dataframe(dept_summary_display, hide_index=True, use_container_width=True)

# Per-Agency (Company) summary
st.markdown("**By Agency (Company)**")
company_summary = (
    display.groupby("Company")
    .apply(lambda g: pd.Series({
        "Employees": len(g),
        "Total Units": int(g[hr_cols].sum().sum()) if hr_cols else 0,
        "Total Dead Time (Mins)": int(g["Total Dead Time (Mins)"].sum()),
    }))
    .reset_index()
)
st.dataframe(company_summary, hide_index=True, use_container_width=True)
