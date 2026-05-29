"""
Page 3 – Top & Bottom Performers by Department
"""
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import date

# ── Config ───────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MH_DIR = BASE / "uploads" / "manhours"
DT_DIR = BASE / "uploads" / "deadtime"
SNAP_DIR = BASE / "snapshots"

TODAY = date.today().isoformat()
SNAP_FILE = SNAP_DIR / f"{TODAY}_final.csv"


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

st.set_page_config(page_title="Performers – Warehouse Ops", page_icon="🏆", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Warehouse Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_perf")
            if st.button("Login", key="admin_login_perf"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_perf"):
            st.session_state["admin_logged_in"] = False
            st.rerun()


# ── Dept config ───────────────────────────────────────────────────────────────
DEPT_CONFIG = {
    "picking": ("Picking", "Total Picked"),
    "packing": ("Packing", "Packed QTY"),
    "putaway": ("Putaway", "Total Units Filed"),
    "receiving": ("Receiving", "Total Received"),
}

TIER_COLORS = {
    "Trainee": "#e74c3c",
    "Signed Off": "#e67e22",
    "Competent": "#2980b9",
    "Master": "#27ae60",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

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


def enrich_with_employee(df: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    def get_attr(u, a):
        return lookup.get(str(u), {}).get(a, "Unknown")
    df = df.copy()
    df["Full Name"] = df["Username"].apply(lambda u: get_attr(u, "full_name"))
    df["Department"] = df["Username"].apply(lambda u: get_attr(u, "department"))
    df["Occupation"] = df["Username"].apply(lambda u: get_attr(u, "occupation"))
    df["Skill Tier"] = df["Username"].apply(lambda u: get_attr(u, "skill_tier"))
    return df


def compute_performer_stats(df: pd.DataFrame, units_col: str) -> pd.DataFrame:
    df = df.copy()
    df[units_col] = pd.to_numeric(df.get(units_col, 0), errors="coerce").fillna(0)
    df["Dead Time (Mins)"] = pd.to_numeric(df.get("Dead Time (Mins)", 0), errors="coerce").fillna(0)

    per_user = (
        df.groupby(["Username", "Full Name", "Occupation", "Skill Tier"])
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
    per_user = per_user.sort_values("Avg Units/Hour", ascending=False).reset_index(drop=True)
    per_user["Rank"] = per_user.index + 1
    return per_user


def dept_section(dept_key: str, lookup: dict):
    display_name, units_col = DEPT_CONFIG[dept_key]

    df_raw = load_dept_data(dept_key)
    if df_raw is None or df_raw.empty:
        st.info(f"No data for {display_name} yet.")
        return None

    df = enrich_with_employee(df_raw, lookup)
    stats = compute_performer_stats(df, units_col)

    if stats.empty:
        st.info("No performer data available.")
        return stats

    top5 = stats.head(5)
    bottom5 = stats[stats["Avg Units/Hour"] > 0].tail(5).sort_values("Avg Units/Hour")

    col_display = ["Rank", "Full Name", "Occupation", "Skill Tier", "Avg Units/Hour", "Total_Dead_Time"]
    col_display = [c for c in col_display if c in stats.columns]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 🥇 Top 5 Performers")
        st.dataframe(
            top5[col_display].rename(columns={"Total_Dead_Time": "Total Dead Time (Mins)"}),
            use_container_width=True,
            hide_index=True,
        )
    with col2:
        st.markdown("##### ⬇️ Bottom 5 Performers")
        st.dataframe(
            bottom5[col_display].rename(columns={"Total_Dead_Time": "Total Dead Time (Mins)"}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("##### 📊 All Performers Ranked")
    fig = px.bar(
        stats,
        x="Full Name",
        y="Avg Units/Hour",
        color="Skill Tier",
        title=f"{display_name} – Avg {units_col}/Hour per Employee",
        color_discrete_map={
            "Trainee": "#e74c3c",
            "Signed Off": "#e67e22",
            "Competent": "#2980b9",
            "Master": "#27ae60",
            "Unknown": "#888",
        },
        template="plotly_dark",
        labels={"Full Name": "Employee"},
    )
    fig.update_layout(xaxis_tickangle=-45, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    return stats


# ── Main UI ───────────────────────────────────────────────────────────────────

st.title("🏆 Top & Bottom Performers")
st.caption(f"Date: {TODAY} — Ranked by average units/hour")

if active_dt_date and active_dt_date != TODAY:
    st.caption(f"📂 Using data from {active_dt_date}")

lookup = load_employee_lookup()
if not lookup:
    st.warning("⚠️ No employee data found. Upload on the Man Hours page first.")

any_data = active_dt_dir is not None and any(active_dt_dir.glob("*.csv"))
if not any_data:
    st.info("📭 No deadtime reports uploaded yet. Upload on the Deadtime Report page.")
    st.stop()

# ── Overall Cross-Department Leaderboard ─────────────────────────────────────
st.subheader("🌐 Overall Cross-Department Leaderboard")

all_stats = []
for dk, (dname, ucol) in DEPT_CONFIG.items():
    df_raw = load_dept_data(dk)
    if df_raw is not None and not df_raw.empty:
        df = enrich_with_employee(df_raw, lookup)
        df[ucol] = pd.to_numeric(df.get(ucol, 0), errors="coerce").fillna(0)
        df["Dead Time (Mins)"] = pd.to_numeric(df.get("Dead Time (Mins)", 0), errors="coerce").fillna(0)
        per_user = (
            df.groupby(["Username", "Full Name", "Occupation", "Skill Tier"])
            .agg(
                Total_Units=(ucol, "sum"),
                Hours_Worked=("Hour", "nunique"),
                Total_Dead_Time=("Dead Time (Mins)", "sum"),
            )
            .reset_index()
        )
        per_user["Avg Units/Hour"] = (
            per_user["Total_Units"] / per_user["Hours_Worked"].replace(0, 1)
        ).round(2)
        per_user["Dept"] = dname
        all_stats.append(per_user)

if all_stats:
    overall = pd.concat(all_stats, ignore_index=True).sort_values("Avg Units/Hour", ascending=False).reset_index(drop=True)
    overall["Overall Rank"] = overall.index + 1
    overview_cols = ["Overall Rank", "Full Name", "Dept", "Occupation", "Skill Tier", "Avg Units/Hour", "Total_Dead_Time"]
    overview_cols = [c for c in overview_cols if c in overall.columns]
    st.dataframe(
        overall[overview_cols].rename(columns={"Total_Dead_Time": "Total Dead Time (Mins)"}),
        use_container_width=True,
        hide_index=True,
        height=300,
    )

    fig_overall = px.bar(
        overall.head(20),
        x="Full Name",
        y="Avg Units/Hour",
        color="Dept",
        title="Top 20 Cross-Department Performers",
        template="plotly_dark",
        labels={"Full Name": "Employee"},
    )
    fig_overall.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_overall, use_container_width=True)
else:
    st.info("No data available for leaderboard.")

st.divider()

# ── Per-Department Expandable Sections ───────────────────────────────────────
st.subheader("📂 Per-Department Performance")

for dk, (display_name, units_col) in DEPT_CONFIG.items():
    with st.expander(f"📦 {display_name}", expanded=False):
        dept_section(dk, lookup)
