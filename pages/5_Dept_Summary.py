"""
Page 5 – Department Summary
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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


st.set_page_config(page_title="Dept Summary – Takealot Warehouse Ops", page_icon="📋", layout="wide")
show_header_logo()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Takealot Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_ds")
            if st.button("Login", key="admin_login_ds"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_ds"):
            st.session_state["admin_logged_in"] = False
            st.rerun()

        st.markdown("### 📤 Upload Reports")
        for dk in DEPT_CONFIG.keys():
            display_name, _ = DEPT_CONFIG[dk]
            uploaded_files = st.file_uploader(
                f"{display_name}",
                type=["csv"],
                key=f"ds_upload_{dk}",
                accept_multiple_files=True,
            )
            if uploaded_files:
                for f in uploaded_files:
                    ts = datetime.now().strftime("%H-%M-%S")
                    dest = TODAY_DT_DIR / f"{ts}_{dk}.csv"
                    dest.write_bytes(f.read())
                st.success(f"{len(uploaded_files)} file(s) saved ✅")


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def build_hourly_summary(df: pd.DataFrame, units_col: str) -> pd.DataFrame:
    """Build per-hour aggregated summary table."""
    df = df.copy()
    df["Hour"] = pd.to_numeric(df["Hour"], errors="coerce")
    df = df.dropna(subset=["Hour"])
    df["Hour"] = df["Hour"].astype(int)
    if units_col in df.columns:
        df[units_col] = pd.to_numeric(df[units_col], errors="coerce").fillna(0)
    else:
        df[units_col] = 0
    if "Dead Time (Mins)" in df.columns:
        df["Dead Time (Mins)"] = pd.to_numeric(df["Dead Time (Mins)"], errors="coerce").fillna(0)
    else:
        df["Dead Time (Mins)"] = 0

    summary = (
        df.groupby("Hour")
        .agg(
            Total_QTY=(units_col, "sum"),
            Total_Dead_Time=("Dead Time (Mins)", "sum"),
            Employee_Count=("Username", "nunique"),
        )
        .reset_index()
        .sort_values("Hour")
    )
    summary["Avg Dead Time / Employee"] = (
        summary["Total_Dead_Time"] / summary["Employee_Count"].replace(0, 1)
    ).round(1)
    summary = summary.rename(columns={
        "Total_QTY": "Total QTY",
        "Total_Dead_Time": "Total Dead Time (Mins)",
        "Employee_Count": "Employees",
    })
    return summary[["Hour", "Employees", "Total QTY", "Total Dead Time (Mins)", "Avg Dead Time / Employee"]]


def make_dual_axis_chart(summary: pd.DataFrame, dept_name: str) -> go.Figure:
    """Dual-axis line chart: QTY on left, Dead Time on right."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=summary["Hour"],
        y=summary["Total QTY"],
        name="Total QTY",
        mode="lines+markers",
        line=dict(color="#2980b9", width=2),
        yaxis="y1",
    ))

    fig.add_trace(go.Scatter(
        x=summary["Hour"],
        y=summary["Total Dead Time (Mins)"],
        name="Dead Time (Mins)",
        mode="lines+markers",
        line=dict(color="#e74c3c", width=2, dash="dot"),
        yaxis="y2",
    ))

    fig.update_layout(
        title=f"{dept_name} – Hourly QTY vs Dead Time",
        xaxis=dict(title="Hour", tickmode="linear"),
        yaxis=dict(title=dict(text="Total QTY", font=dict(color="#2980b9"))),
        yaxis2=dict(
            title=dict(text="Dead Time (Mins)", font=dict(color="#e74c3c")),
            overlaying="y",
            side="right",
        ),
        legend=dict(x=0.01, y=0.99),
        template="plotly_dark",
        height=350,
    )
    return fig


# ── Main UI ───────────────────────────────────────────────────────────────────

st.title("📋 Department Summary")
st.caption(f"Date: {TODAY} — Hourly aggregated view per department")

if active_dt_date and active_dt_date != TODAY:
    st.caption(f"📂 Using data from {active_dt_date}")

# ── Load all dept data ────────────────────────────────────────────────────────
dept_raw_data = {}
dept_summaries = {}

for dk, (display_name, units_col) in DEPT_CONFIG.items():
    df_raw = load_dept_data(dk)
    if df_raw is None or df_raw.empty:
        continue
    dept_raw_data[dk] = (display_name, units_col, df_raw)
    summary = build_hourly_summary(df_raw, units_col)
    dept_summaries[dk] = (display_name, summary)

# ── Grand summary table (per department) ─────────────────────────────────────
if dept_summaries:
    dept_rows = []
    for dk, (display_name, summary) in dept_summaries.items():
        _, units_col, df_raw = dept_raw_data[dk]
        dept_rows.append({
            "Department": display_name,
            "Employees": int(df_raw["Username"].nunique()) if "Username" in df_raw.columns else 0,
            "Total QTY": int(summary["Total QTY"].sum()),
            "Total Dead Time (Mins)": int(summary["Total Dead Time (Mins)"].sum()),
        })
    dept_grand_df = pd.DataFrame(dept_rows)
    st.subheader("📊 Summary by Department")
    st.dataframe(dept_grand_df, hide_index=True, use_container_width=True)

    st.divider()
else:
    st.info("📭 No deadtime data uploaded yet. Use the sidebar uploaders (Admin login required).")
    st.stop()

# ── Per-department expandable sections ────────────────────────────────────────
for dk, (display_name, summary) in dept_summaries.items():
    with st.expander(f"📦 {display_name}", expanded=True):
        st.dataframe(summary, use_container_width=True, hide_index=True)
        fig = make_dual_axis_chart(summary, display_name)
        st.plotly_chart(fig, use_container_width=True)
