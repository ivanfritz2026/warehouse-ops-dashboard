"""
Page 2 – Deadtime & Productivity Report
"""
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import date, datetime

# ── Config ───────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MH_DIR = BASE / "uploads" / "manhours"
DT_DIR = BASE / "uploads" / "deadtime"
SNAP_DIR = BASE / "snapshots"
for d in [DT_DIR, SNAP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()
TODAY_DT_DIR = DT_DIR / TODAY
TODAY_DT_DIR.mkdir(parents=True, exist_ok=True)

DEPT_CONFIG = {
    "picking": ("Picking", "Total Picked", "picking_rates_con_picking_dead.csv"),
    "packing": ("Packing", "Packed QTY", "packing_rates_packing_dead.csv"),
    "putaway": ("Putaway", "Total Units Filed", "putaway_rates_putaway_dead.csv"),
    "receiving": ("Receiving", "Total Received", "receiving_rates_receiving_dead.csv"),
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


active_dt_dir, active_dt_date = get_active_dt_dir()
mh_json_path = get_active_mh_json()
SNAP_FILE = SNAP_DIR / f"{TODAY}_final.csv"

st.set_page_config(page_title="Deadtime Report – Warehouse Ops", page_icon="⏱️", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Warehouse Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_dt")
            if st.button("Login", key="admin_login_dt"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_dt"):
            st.session_state["admin_logged_in"] = False
            st.rerun()

        st.markdown("### 📤 Upload Reports")
        dept_keys = list(DEPT_CONFIG.keys())
        for dk in dept_keys:
            display_name, units_col, _ = DEPT_CONFIG[dk]
            uploaded = st.file_uploader(
                f"{display_name}",
                type=["csv"],
                key=f"dt_upload_{dk}",
                accept_multiple_files=True,
            )
            if uploaded:
                for f in uploaded:
                    ts = datetime.now().strftime("%H-%M-%S")
                    dest = TODAY_DT_DIR / f"{ts}_{dk}.csv"
                    dest.write_bytes(f.read())
                st.success(f"{len(uploaded)} file(s) saved ✅")


# ── Helpers ──────────────────────────────────────────────────────────────────

TIER_COLORS = {
    "Trainee": "#e74c3c",
    "Signed Off": "#e67e22",
    "Competent": "#2980b9",
    "Master": "#27ae60",
}


def load_employee_lookup() -> dict:
    if mh_json_path and mh_json_path.exists():
        return json.loads(mh_json_path.read_text())
    return {}


def load_dept_data(dept_key: str) -> pd.DataFrame | None:
    """Load all CSVs for dept from active directory."""
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
    df = pd.concat(dfs, ignore_index=True)
    return df


def enrich_with_employee(df: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    """Add Name, Department, Occupation, Skill Tier from employee lookup."""
    def get_attr(username, attr):
        return lookup.get(str(username), {}).get(attr, "Unknown")

    df = df.copy()
    df["Full Name"] = df["Username"].apply(lambda u: get_attr(u, "full_name"))
    df["Department"] = df["Username"].apply(lambda u: get_attr(u, "department"))
    df["Occupation"] = df["Username"].apply(lambda u: get_attr(u, "occupation"))
    df["Skill Tier"] = df["Username"].apply(lambda u: get_attr(u, "skill_tier"))
    return df


def compute_avg_units(df: pd.DataFrame, units_col: str) -> pd.DataFrame:
    """Add Avg Units/Hour column."""
    df = df.copy()
    df[units_col] = pd.to_numeric(df.get(units_col, 0), errors="coerce").fillna(0)
    df["Dead Time (Mins)"] = pd.to_numeric(df.get("Dead Time (Mins)", 0), errors="coerce").fillna(0)
    per_user = (
        df.groupby("Username")
        .agg(
            Total_Units=(units_col, "sum"),
            Hours_Worked=("Hour", "nunique"),
            Total_Dead_Time=("Dead Time (Mins)", "sum"),
        )
        .reset_index()
    )
    per_user["Avg Units/Hour"] = (
        per_user["Total_Units"] / per_user["Hours_Worked"].replace(0, 1)
    ).round(2)
    return per_user


def color_tier_val(val):
    color = TIER_COLORS.get(val, "#888")
    return f"color: {color}; font-weight: bold"


# ── Main UI ───────────────────────────────────────────────────────────────────

st.title("⏱️ Deadtime & Productivity Report")
st.caption(f"Date: {TODAY}")

if active_dt_date and active_dt_date != TODAY:
    st.caption(f"📂 Using data from {active_dt_date}")

lookup = load_employee_lookup()
if not lookup:
    st.warning("⚠️ No Man Hours data found. Upload on the Man Hours page to enrich deadtime data with employee info.")

dept_keys = list(DEPT_CONFIG.keys())
tab_labels = [DEPT_CONFIG[k][0] for k in dept_keys]
tabs = st.tabs([f"📦 {t}" for t in tab_labels])

all_dept_dfs = {}

for tab, dk in zip(tabs, dept_keys):
    display_name, units_col, _ = DEPT_CONFIG[dk]

    with tab:
        df_raw = load_dept_data(dk)
        if df_raw is None or df_raw.empty:
            st.info(f"No {display_name} data uploaded yet. Use the sidebar uploader.")
            continue

        df = enrich_with_employee(df_raw, lookup)
        df[units_col] = pd.to_numeric(df.get(units_col, 0), errors="coerce").fillna(0)
        df["Dead Time (Mins)"] = pd.to_numeric(df.get("Dead Time (Mins)", 0), errors="coerce").fillna(0)

        all_dept_dfs[dk] = df

        hours_available = sorted(df["Hour"].dropna().unique().tolist())
        hour_options = ["All Hours"] + [str(int(h)) if isinstance(h, float) else str(h) for h in hours_available]
        selected_hour = st.selectbox(f"Filter by Hour ({display_name})", hour_options, key=f"hour_{dk}")

        if selected_hour != "All Hours":
            try:
                df_filtered = df[df["Hour"] == int(selected_hour)]
            except ValueError:
                df_filtered = df[df["Hour"].astype(str) == selected_hour]
        else:
            df_filtered = df

        st.markdown(f"#### 📊 {display_name} Summary")
        m1, m2, m3 = st.columns(3)
        total_dt = df_filtered["Dead Time (Mins)"].sum()
        avg_dt = df_filtered.groupby("Username")["Dead Time (Mins)"].sum().mean()
        per_user_agg = compute_avg_units(df_filtered, units_col)
        avg_uph = per_user_agg["Avg Units/Hour"].mean()

        m1.metric("Total Dead Time (Mins)", f"{total_dt:.0f}")
        m2.metric("Avg Dead Time / Employee (Mins)", f"{avg_dt:.1f}" if pd.notna(avg_dt) else "0.0")
        m3.metric(f"Avg {units_col}/Hour", f"{avg_uph:.1f}" if pd.notna(avg_uph) else "0.0")

        st.markdown("#### 👥 Employee Detail")
        detail_cols = ["Username", "Full Name", "Occupation", "Skill Tier", "Hour", units_col, "Dead Time (Mins)"]
        detail_cols = [c for c in detail_cols if c in df_filtered.columns]
        display_df = df_filtered[detail_cols].sort_values("Username")

        styled = display_df.style.map(color_tier_val, subset=["Skill Tier"] if "Skill Tier" in display_df.columns else [])
        st.dataframe(styled, use_container_width=True, height=350)

        st.markdown("#### 📉 Dead Time per Employee")
        chart_df = (
            df_filtered.groupby(["Username", "Full Name"])["Dead Time (Mins)"]
            .sum()
            .reset_index()
            .sort_values("Dead Time (Mins)", ascending=False)
        )
        chart_df["Label"] = chart_df["Full Name"].where(
            chart_df["Full Name"] != "Unknown", chart_df["Username"]
        )
        fig = px.bar(
            chart_df,
            x="Label",
            y="Dead Time (Mins)",
            title=f"{display_name} – Dead Time per Employee (Hour: {selected_hour})",
            color="Dead Time (Mins)",
            color_continuous_scale="Reds",
            labels={"Label": "Employee"},
            template="plotly_dark",
        )
        fig.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── End-of-Day Snapshot ───────────────────────────────────────────────────────
st.subheader("💾 End-of-Day Snapshot")
if st.button("📸 Save End-of-Day Snapshot", type="primary"):
    if not all_dept_dfs:
        st.warning("No deadtime data loaded yet.")
    else:
        combined = []
        for dk, df_dept in all_dept_dfs.items():
            display_name, units_col, _ = DEPT_CONFIG[dk]
            df_dept = df_dept.copy()
            df_dept["Dept_Key"] = dk
            df_dept["Dept_Name"] = display_name
            df_dept["Units_Col"] = units_col
            df_dept["Units"] = pd.to_numeric(df_dept.get(units_col, 0), errors="coerce").fillna(0)
            combined.append(df_dept)
        snap_df = pd.concat(combined, ignore_index=True)
        snap_df.to_csv(SNAP_FILE, index=False)
        st.success(f"Snapshot saved to `{SNAP_FILE.name}`")

if SNAP_FILE.exists():
    st.caption(f"Last snapshot: {SNAP_FILE.stat().st_mtime and datetime.fromtimestamp(SNAP_FILE.stat().st_mtime).strftime('%H:%M:%S')}")
