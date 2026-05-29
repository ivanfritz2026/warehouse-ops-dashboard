"""
Warehouse Ops Dashboard – Home / Landing Page
"""
import streamlit as st
from pathlib import Path
from datetime import date, datetime

# ── Directory bootstrap ──────────────────────────────────────────────────────
BASE = Path(__file__).parent / "data"
for d in [
    BASE / "uploads" / "manhours",
    BASE / "uploads" / "deadtime",
    BASE / "snapshots",
]:
    d.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()
MH_DIR = BASE / "uploads" / "manhours"
MH_XLSX = MH_DIR / f"{TODAY}.xlsx"
DT_DIR = BASE / "uploads" / "deadtime"
TODAY_DT_DIR = DT_DIR / TODAY
TODAY_DT_DIR.mkdir(parents=True, exist_ok=True)

DEPT_CONFIG = {
    "picking": "Picking",
    "packing": "Packing",
    "putaway": "Putaway",
    "receiving": "Receiving",
}


def get_active_mh_file():
    """Return (path, date_str) for the most recent man hours file."""
    today_file = MH_DIR / f"{TODAY}.xlsx"
    if today_file.exists():
        return today_file, TODAY
    candidates = sorted(MH_DIR.glob("*.xlsx"), reverse=True)
    for c in candidates:
        return c, c.stem
    return None, None


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


# ── Page config ──────────────────────────────────────────────────────────────

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


st.set_page_config(
    page_title="Takealot Warehouse Ops Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)
show_header_logo()


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Takealot Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    # ── Admin upload gate ─────────────────────────────────────────────────────
    if not st.session_state.get("admin_logged_in"):
        with st.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="admin_pwd_home")
            if st.button("Login", key="admin_login_home"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.success("✅ Admin logged in")
        if st.button("Logout", key="admin_logout_home"):
            st.session_state["admin_logged_in"] = False
            st.rerun()

        st.markdown("### 📋 Man Hours Report")
        mh_uploaded = st.file_uploader(
            "Upload Auto Man Hours (.xlsx)",
            type=["xlsx"],
            key="home_mh_upload",
        )
        if mh_uploaded:
            with open(MH_XLSX, "wb") as f:
                f.write(mh_uploaded.read())
            st.success("Man Hours saved ✅")

        st.divider()
        st.markdown("### 📦 Deadtime Reports")
        for dk, display_name in DEPT_CONFIG.items():
            dt_uploaded = st.file_uploader(
                f"{display_name}",
                type=["csv"],
                key=f"home_dt_{dk}",
                accept_multiple_files=True,
            )
            if dt_uploaded:
                for f in dt_uploaded:
                    ts = datetime.now().strftime("%H-%M-%S")
                    dest = TODAY_DT_DIR / f"{ts}_{dk}.csv"
                    dest.write_bytes(f.read())
                st.success(f"{display_name}: {len(dt_uploaded)} file(s) saved ✅")


# ── Top navigation bar ────────────────────────────────────────────────────────
def top_nav():
    pages = [
        ("🏠 Home",         "app"),
        ("👷 Man Hours",    "1_Man_Hours"),
        ("⏱️ Deadtime",    "2_Deadtime_Report"),
        ("🏆 Performers",  "3_Performers"),
        ("📊 Hourly Rate", "4_Hourly_Rate"),
        ("📋 Dept Summary","5_Dept_Summary"),
        ("💰 Finance",      "6_Finance"),
    ]
    cols = st.columns(len(pages))
    for col, (label, page_name) in zip(cols, pages):
        col.page_link(f"pages/{page_name}.py" if page_name != "app" else "app.py", label=label)
    st.divider()


top_nav()

# ── Home content ─────────────────────────────────────────────────────────────
st.title("🏭 Takealot Warehouse Ops Dashboard")
st.subheader("Welcome! Use the navigation bar above or sidebar to navigate between pages.")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.info(
        "### 👷 Man Hours\n"
        "Upload the daily Auto Man Hours report to see workforce summaries, "
        "attendance, and skill-tier breakdowns.",
        icon="📋",
    )
with col2:
    st.info(
        "### ⏱️ Deadtime Report\n"
        "Upload hourly deadtime CSVs for Picking, Packing, Putaway, and "
        "Receiving to track productivity in real time.",
        icon="📊",
    )
with col3:
    st.info(
        "### 🏆 Performers\n"
        "View the Top & Bottom performers per department, ranked by average "
        "units per hour across all deadtime uploads.",
        icon="🥇",
    )

col4, col5 = st.columns(2)
with col4:
    st.info(
        "### ⏱️ Hourly Rate\n"
        "Per-employee per-hour production log merged with employee info.",
        icon="📊",
    )
with col5:
    st.info(
        "### 📋 Department Summary\n"
        "Hourly summary table per department with dual-axis charts.",
        icon="📋",
    )

st.divider()

# Quick data-status summary
active_mh, active_mh_date = get_active_mh_file()
active_dt_dir, active_dt_date = get_active_dt_dir()
snap_file = BASE / "snapshots" / f"{TODAY}_final.csv"

st.markdown("### 📁 Data Status")
c1, c2, c3 = st.columns(3)
with c1:
    if active_mh:
        st.success(f"Man Hours: {active_mh_date} ✅")
    else:
        st.warning("No Man Hours file yet")
with c2:
    if active_dt_dir:
        count = len(list(active_dt_dir.glob("*.csv")))
        st.success(f"{count} deadtime file(s): {active_dt_date} ✅")
    else:
        st.warning("No deadtime files yet")
with c3:
    if snap_file.exists():
        st.success("End-of-Day snapshot saved ✅")
    else:
        st.warning("No snapshot saved yet")
