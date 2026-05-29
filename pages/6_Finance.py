"""
Page 6 – Finance vs Volumes
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

# ── Config ───────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MH_DIR = BASE / "uploads" / "manhours"
DT_DIR = BASE / "uploads" / "deadtime"
TODAY = date.today().isoformat()

st.set_page_config(page_title="Finance – Takealot Warehouse Ops", page_icon="💰", layout="wide")


# ── Logo / Header ─────────────────────────────────────────────────────────────
def show_header_logo():
    import base64
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


show_header_logo()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏭 Takealot Ops")
    st.caption(f"📅 {date.today().strftime('%A, %d %B %Y')}")
    st.divider()

    if not st.session_state.get("admin_logged_in"):
        with st.sidebar.expander("🔐 Admin Login", expanded=False):
            pwd = st.text_input("Password", type="password", key="fin_pwd")
            if st.button("Login", key="fin_login"):
                if pwd == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("Wrong password")
    else:
        st.sidebar.success("✅ Admin logged in")
        if st.sidebar.button("Logout", key="fin_logout"):
            st.session_state["admin_logged_in"] = False
            st.rerun()


# ── Hourly rate logic ─────────────────────────────────────────────────────────
def get_hourly_rate(occupation, department):
    """Return hourly rate in Rands based on occupation and department."""
    occ = str(occupation).strip()
    dept = str(department).strip()

    # Tier 1: R51.29
    tier1_occupations = [
        "Unloader", "Unloaders", "Receiver", "Receivers",
        "Putaway Filers", "Putaway Grid Sorter", "Putaways Admin", "Putaway Admin",
        "Picker", "Packer", "Dispatch Assistant",
    ]
    if any(t in occ for t in tier1_occupations):
        return 51.29

    # Dispatch Runners: R40.22
    if "Dispatch Runner" in occ or "Dispatch Runners" in occ:
        return 40.22

    # Dispatch Admin: R64.70
    if "Dispatch" in occ and "Admin" in occ:
        return 64.70

    # Dispatch Team Leader: R81.74
    if "Dispatch Team Leader" in occ:
        return 81.74

    # Department-based rates
    if "Inventory" in dept:
        return 67.94

    if "DC Support" in dept or "Support" in dept:
        return 77.38

    # MHE: R58.88
    if "MHE" in occ or "HL Driver" in occ or "Forklift" in occ:
        return 58.88

    # Rest of Inbound/Outbound: R64.70
    if "Inbound" in dept or "Outbound" in dept:
        return 64.70

    # Default fallback
    return 64.70


def get_work_hours(department):
    """Return standard work hours. Inbound = 8, rest = 10.5."""
    if "Inbound" in str(department):
        return 8.0
    return 10.5


# ── File helpers ──────────────────────────────────────────────────────────────
def get_active_mh_file():
    today_file = MH_DIR / f"{TODAY}.xlsx"
    if today_file.exists():
        return today_file, TODAY
    files = sorted(MH_DIR.glob("*.xlsx"), reverse=True)
    return (files[0], files[0].stem) if files else (None, None)


def get_active_dt_dir():
    today_dir = DT_DIR / TODAY
    if today_dir.exists() and list(today_dir.glob("*.csv")):
        return today_dir, TODAY
    dirs = sorted(
        [d for d in DT_DIR.iterdir() if d.is_dir() and list(d.glob("*.csv"))],
        reverse=True,
    )
    return (dirs[0], dirs[0].name) if dirs else (None, None)


# ── Load man hours ────────────────────────────────────────────────────────────
mh_file, mh_date = get_active_mh_file()
if not mh_file:
    st.warning("No Man Hours data found. Upload on Man Hours page first.")
    st.stop()

df = pd.read_excel(mh_file, header=9, engine="openpyxl")
df = df.dropna(subset=["Cust-Oracle Username"])

in_cols = [c for c in df.columns if str(c) == "In" or str(c).startswith("In.")]
df["Present"] = df[in_cols[0]].notna() if in_cols else False

present_df = df[df["Present"] == True].copy()

# Calculate labor cost per employee
present_df["Hourly_Rate"] = present_df.apply(
    lambda row: get_hourly_rate(
        row.get("Occupation", ""), row.get("Department", "")
    ),
    axis=1,
)
present_df["Work_Hours"] = present_df["Department"].apply(get_work_hours)
present_df["Labor_Cost"] = present_df["Hourly_Rate"] * present_df["Work_Hours"]

# Username column normalisation (handle different possible column names)
username_col = "Cust-Oracle Username"
if username_col not in present_df.columns:
    for candidate in ["Username", "Employee", "Name"]:
        if candidate in present_df.columns:
            username_col = candidate
            break


def categorize_dept(dept):
    d = str(dept)
    if "Inbound" in d:
        return "Inbound"
    elif "Outbound" in d:
        return "Outbound"
    elif "Inventory" in d:
        return "Inventory"
    elif "Dispatch" in d:
        return "Dispatch"
    return "Other"


present_df["Dept_Category"] = present_df["Department"].apply(categorize_dept)

# ── Load deadtime volumes ─────────────────────────────────────────────────────
dt_dir, dt_date = get_active_dt_dir()
volumes = {"receiving": 0, "putaway": 0, "picking": 0, "packing": 0}

if dt_dir:
    recv_files = list(dt_dir.glob("*_receiving.csv"))
    if recv_files:
        recv_df = pd.concat([pd.read_csv(f) for f in recv_files], ignore_index=True)
        volumes["receiving"] = int(
            pd.to_numeric(recv_df.get("Total Received", pd.Series(dtype=float)), errors="coerce").sum()
        )

    put_files = list(dt_dir.glob("*_putaway.csv"))
    if put_files:
        put_df = pd.concat([pd.read_csv(f) for f in put_files], ignore_index=True)
        volumes["putaway"] = int(
            pd.to_numeric(put_df.get("Total Units Filed", pd.Series(dtype=float)), errors="coerce").sum()
        )

    pick_files = list(dt_dir.glob("*_picking.csv"))
    if pick_files:
        pick_df = pd.concat([pd.read_csv(f) for f in pick_files], ignore_index=True)
        volumes["picking"] = int(
            pd.to_numeric(pick_df.get("Total Picked", pd.Series(dtype=float)), errors="coerce").sum()
        )

    pack_files = list(dt_dir.glob("*_packing.csv"))
    if pack_files:
        pack_df = pd.concat([pd.read_csv(f) for f in pack_files], ignore_index=True)
        volumes["packing"] = int(
            pd.to_numeric(pack_df.get("Packed QTY", pd.Series(dtype=float)), errors="coerce").sum()
        )

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("💰 Finance vs Volumes")
st.caption(
    f"Man Hours: {mh_date} | Volumes: {dt_date if dt_dir else 'No data'}"
)

total_present = len(present_df)
total_labor_cost = present_df["Labor_Cost"].sum()
total_received = volumes["receiving"]
total_packed = volumes["packing"]
total_picked = volumes["picking"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("👤 Present Employees", f"{total_present:,}")
m2.metric("💵 Total Labor Cost", f"R {total_labor_cost:,.2f}")
m3.metric("📦 Units Received", f"{total_received:,}")
m4.metric("📦 Units Packed", f"{total_packed:,}")

st.divider()

# ── Inbound vs Outbound ───────────────────────────────────────────────────────
st.subheader("📊 Cost vs Volume Breakdown")

inbound_df = present_df[present_df["Dept_Category"] == "Inbound"]
outbound_df = present_df[present_df["Dept_Category"] == "Outbound"]

inbound_cost = inbound_df["Labor_Cost"].sum()
outbound_cost = outbound_df["Labor_Cost"].sum()
inbound_headcount = len(inbound_df)
outbound_headcount = len(outbound_df)

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📥 Inbound")
    st.metric("Headcount", inbound_headcount)
    st.metric("Labor Cost", f"R {inbound_cost:,.2f}")
    st.metric("Receiving Volume", f"{total_received:,}")
    if total_received > 0:
        cost_per_unit = inbound_cost / total_received
        st.metric("Cost per Unit Received", f"R {cost_per_unit:.2f}")
    else:
        st.info("No receiving volume data")

with col2:
    st.markdown("#### 📤 Outbound")
    st.metric("Headcount", outbound_headcount)
    st.metric("Labor Cost", f"R {outbound_cost:,.2f}")
    st.metric("Picking Volume", f"{total_picked:,}")
    st.metric("Packing Volume", f"{total_packed:,}")
    total_outbound_volume = total_picked + total_packed
    if total_outbound_volume > 0:
        cost_per_unit = outbound_cost / total_outbound_volume
        st.metric("Cost per Unit (Pick+Pack)", f"R {cost_per_unit:.2f}")
    else:
        st.info("No outbound volume data")

st.divider()

# ── Detailed breakdown table ──────────────────────────────────────────────────
st.subheader("💼 Labor Cost by Department")

dept_summary = (
    present_df.groupby("Dept_Category")
    .agg(
        Employees=(username_col, "count"),
        Total_Labor_Cost=("Labor_Cost", "sum"),
        Avg_Hourly_Rate=("Hourly_Rate", "mean"),
    )
    .reset_index()
)
dept_summary["Total_Labor_Cost"] = dept_summary["Total_Labor_Cost"].apply(
    lambda x: f"R {x:,.2f}"
)
dept_summary["Avg_Hourly_Rate"] = dept_summary["Avg_Hourly_Rate"].apply(
    lambda x: f"R {x:.2f}"
)
dept_summary = dept_summary.rename(columns={"Dept_Category": "Department"})
st.dataframe(dept_summary, use_container_width=True, hide_index=True)
