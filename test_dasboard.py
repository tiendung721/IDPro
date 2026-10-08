
import re
import numpy as np
import pandas as pd
import openpyxl
import streamlit as st
import plotly.express as px
from datetime import date

st.set_page_config(page_title="Báo cáo công việc 2025", layout="wide")

# -----------------------------
# Styling (dashboard-like cards)
# -----------------------------
st.markdown(
    """
    <style>
    .kpi-card{
        background: #ffffff;
        border: 1px solid #e6e6e6;
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        height: 100%;
    }
    .kpi-title{
        font-size: 0.85rem;
        color: #444;
        margin-bottom: 6px;
        font-weight: 600;
    }
    .kpi-value{
        font-size: 1.8rem;
        font-weight: 800;
        line-height: 1.1;
        color: #0b5;
        margin-bottom: 2px;
    }
    .kpi-sub{
        font-size: 0.8rem;
        color: #666;
    }
    .block{
        background: #ffffff;
        border: 1px solid #e6e6e6;
        border-radius: 14px;
        padding: 10px 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .block h3{
        margin: 0.2rem 0 0.6rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Data parsing utilities
# -----------------------------
def _extract_kilns(note: str):
    if not isinstance(note, str):
        return []
    return re.findall(r"Lò\s*\d+", note)

def _classify_task(task: str):
    t = (task or "").lower()
    if any(k in t for k in ["sự cố", "kẹt", "hỏng", "đứt", "mất tín hiệu", "cháy", "vỡ", "lỗi"]):
        return "Sự cố/Khắc phục"
    if any(k in t for k in ["bảo dưỡng", "vệ sinh", "thí nghiệm", "kiểm tra", "hiệu chỉnh"]):
        return "Bảo dưỡng/Vệ sinh"
    if any(k in t for k in ["thi công", "lắp", "chế tạo", "cải tạo", "kéo cáp", "làm tủ", "sửa chữa"]):
        return "Thi công/Cải tạo"
    if any(k in t for k in ["hỗ trợ", "mồi", "vận hành"]):
        return "Hỗ trợ vận hành"
    return "Khác"

def _extract_people(task: str):
    """Heuristic: lấy tên sau dấu ':' rồi split theo , - ;"""
    if not isinstance(task, str) or ":" not in task:
        return []
    after = task.split(":", 1)[1]
    after = re.sub(r"\(.*?\)", "", after)
    parts = re.split(r"[,;\-]", after)
    people = [p.strip() for p in parts if p.strip()]
    # lọc tokens không giống tên người
    filtered = []
    for p in people:
        pl = p.lower()
        if any(k in pl for k in ["lò", "silo", "kw", "mất", "hỏng", "bt", "m "]):
            continue
        filtered.append(p)
    return filtered

def _sheet_to_df(ws):
    data = []
    for r in ws.iter_rows(values_only=True):
        data.append(list(r[:4]))
    return pd.DataFrame(data, columns=["A", "B", "C", "D"])

def _parse_month(ws, month_number: int):
    df = _sheet_to_df(ws)

    # Maintenance header row
    hdr_idx = df.index[(df["A"] == "Ngày") & df["B"].astype(str).str.contains("Mô tả", na=False)]
    if len(hdr_idx) == 0:
        raise ValueError("Không tìm thấy bảng công việc (header 'Ngày').")
    start = int(hdr_idx[0]) + 1

    # End before project summary
    end_candidates = df.index[df["A"].astype(str).str.contains("Tổng hợp", na=False)]
    end = int(end_candidates[0]) if len(end_candidates) > 0 else len(df)

    maint = df.loc[start : end - 1, ["A", "B", "C", "D"]].copy()
    maint.columns = ["Day", "Task", "Downtime_h", "Note"]
    maint = maint.dropna(subset=["Task"], how="all")

    maint["Day"] = maint["Day"].ffill()
    maint["Day"] = pd.to_numeric(maint["Day"], errors="coerce")
    maint = maint[~maint["Day"].isna()]
    maint["Day"] = maint["Day"].astype(int)

    maint["Downtime_h"] = pd.to_numeric(maint["Downtime_h"], errors="coerce").fillna(0.0)
    maint["Task"] = maint["Task"].astype(str).str.strip()
    maint["Note"] = maint["Note"].astype(str).replace("None", np.nan)

    maint["Month"] = month_number
    maint["Date"] = pd.to_datetime(
        [date(2025, month_number, int(d)) for d in maint["Day"]],
        errors="coerce",
    )
    maint["Category"] = maint["Task"].apply(_classify_task)
    maint["Kilns"] = maint["Note"].apply(_extract_kilns)
    maint["People"] = maint["Task"].apply(_extract_people)

    # Projects table (optional)
    projects = pd.DataFrame()
    proj_title_idx = df.index[df["A"].astype(str).str.contains("Tổng hợp các dự án", na=False)]
    if len(proj_title_idx) > 0:
        # locate header
        phdr = df.index[(df["B"] == "Dự án") & (df["C"].astype(str).str.contains("Tiến độ", na=False))]
        phdr = phdr[phdr > proj_title_idx[0]]
        pstart = int(phdr[0]) + 1 if len(phdr) > 0 else int(proj_title_idx[0]) + 2

        pend_candidates = df.index[df["A"].astype(str).str.contains("2.Kế hoạch", na=False)]
        pend = int(pend_candidates[0]) if len(pend_candidates) > 0 else len(df)

        p = df.loc[pstart : pend - 1, ["B", "C", "D"]].copy()
        p.columns = ["Project", "Progress", "Note"]
        p = p.dropna(subset=["Project"], how="all")
        p = p[p["Project"].notna()]
        p["Project"] = p["Project"].astype(str).str.strip()

        def norm_progress(x):
            if isinstance(x, str):
                xs = x.strip().lower()
                if "hoàn thành" in xs:
                    return 1.0
                try:
                    return float(xs.replace(",", "."))
                except Exception:
                    return np.nan
            try:
                return float(x)
            except Exception:
                return np.nan

        p["Progress"] = p["Progress"].apply(norm_progress)
        p["Month"] = month_number
        projects = p

    # Plan table (optional)
    plan = pd.DataFrame()
    plan_title_idx = df.index[df["A"].astype(str).str.contains("2.Kế hoạch", na=False)]
    if len(plan_title_idx) > 0:
        hdr = df.index[(df["B"] == "Dự án") & (df["C"].astype(str).str.contains("Mục tiêu", na=False))]
        hdr = hdr[hdr > plan_title_idx[0]]
        start_plan = int(hdr[0]) + 1 if len(hdr) > 0 else int(plan_title_idx[0]) + 2

        p2 = df.loc[start_plan:, ["B", "C", "D"]].copy()
        p2.columns = ["PlanItem", "Target", "Note"]
        p2 = p2.dropna(subset=["PlanItem"], how="all")
        p2 = p2[p2["PlanItem"].notna()]
        p2["PlanItem"] = p2["PlanItem"].astype(str).str.strip()
        p2["Target"] = pd.to_numeric(p2["Target"], errors="coerce")
        p2["Month"] = month_number
        plan = p2

    return maint, projects, plan

@st.cache_data(show_spinner=False)
def load_data(xlsx_path: str):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    months = []
    projects = []
    plans = []

    for sh in wb.sheetnames:
        m = re.findall(r"(\d+)", sh)
        if not m:
            continue
        month_number = int(m[0])
        maint, proj, plan = _parse_month(wb[sh], month_number)
        months.append(maint)
        if len(proj) > 0:
            projects.append(proj)
        if len(plan) > 0:
            plans.append(plan)

    maint_all = pd.concat(months, ignore_index=True) if months else pd.DataFrame()
    proj_all = pd.concat(projects, ignore_index=True) if projects else pd.DataFrame()
    plan_all = pd.concat(plans, ignore_index=True) if plans else pd.DataFrame()
    return maint_all, proj_all, plan_all

# -----------------------------
# Load
# -----------------------------
XLSX_PATH = "data\\2025_Báo_cáo_công việc.xlsx"  # đặt file cùng thư mục với app.py
maint, projects, plans = load_data(XLSX_PATH)

# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.title("BÁO CÁO CÔNG VIỆC 2025")

page = st.sidebar.radio(
    "Chọn trang",
    [
        "Transaction Performance (Tổng quan)",
        "Customer Behavior & Segment (Nhân sự/Phân nhóm)",
        "Channel Strategy (Theo Lò/Địa bàn)",
        "Transaction Type & Monetization (Loại công việc)",
        "Risk & Sustainability Diagnostic (Rủi ro/Chất lượng)",
    ],
)

available_months = sorted(maint["Month"].dropna().unique().tolist()) if len(maint) else []
sel_months = st.sidebar.multiselect("Tháng", options=available_months, default=available_months)

available_cats = sorted(maint["Category"].dropna().unique().tolist()) if len(maint) else []
sel_cats = st.sidebar.multiselect("Nhóm công việc", options=available_cats, default=available_cats)

# Kiln filter from exploded list
kiln_series = maint["Kilns"].explode() if len(maint) else pd.Series([], dtype=str)
available_kilns = sorted(kiln_series.dropna().unique().tolist())
sel_kilns = st.sidebar.multiselect("Lò", options=available_kilns, default=available_kilns)

# Filtered dataset
df = maint.copy()
if len(df):
    df = df[df["Month"].isin(sel_months)]
    df = df[df["Category"].isin(sel_cats)]
    if len(sel_kilns) > 0:
        df = df[df["Kilns"].apply(lambda ks: any(k in sel_kilns for k in (ks or [])) if isinstance(ks, list) else False)]

# -----------------------------
# Helpers for dashboard blocks
# -----------------------------
def kpi(title, value, sub=""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def section(title):
    st.markdown(f"### {title}")

# -----------------------------
# Compute KPI
# -----------------------------
if len(df):
    total_tasks = len(df)
    total_downtime = float(df["Downtime_h"].sum())
    avg_downtime = float(df["Downtime_h"].mean()) if total_tasks else 0.0

    unique_days = df["Date"].nunique()
    unique_kilns = df["Kilns"].explode().dropna().nunique()
    unique_people = df["People"].explode().dropna().nunique()
else:
    total_tasks = total_downtime = avg_downtime = unique_days = unique_kilns = unique_people = 0

# -----------------------------
# Header
# -----------------------------
st.title("BÁO CÁO CÔNG VIỆC (Dashboard-style)")
st.caption("Nguồn: Excel nội bộ | Năm 2025 | Bộ phận: Điện cơ tự động hóa (theo file)")

# -----------------------------
# KPI row
# -----------------------------
c1, c2, c3, c4 = st.columns(4)
with c1: kpi("Tổng số công việc", f"{total_tasks:,}".replace(",", "."),
             f"Số ngày có phát sinh: {unique_days}")
with c2: kpi("Tổng thời gian dừng lò (h)", f"{total_downtime:,.1f}".replace(",", "."),
             "Tổng downtime theo bộ lọc")
with c3: kpi("Downtime trung bình / công việc (h)", f"{avg_downtime:,.2f}".replace(",", "."),
             "0 = không dừng lò / hoặc chưa ghi")
with c4: kpi("Số lò / nhân sự liên quan", f"{unique_kilns} / {unique_people}",
             "Ước tính theo ghi chú & mô tả")

st.markdown("")

# -----------------------------
# Pages
# -----------------------------
if not len(maint):
    st.warning("Không tải được dữ liệu. Hãy đặt file Excel cùng thư mục với app.py và kiểm tra tên file.")
    st.stop()

if not len(df):
    st.info("Không có dữ liệu phù hợp với bộ lọc hiện tại.")
    st.stop()

# Common pre-aggregations
df_day = df.groupby(["Date"], as_index=False).agg(
    tasks=("Task", "count"),
    downtime=("Downtime_h", "sum"),
)
df_day["Month"] = df_day["Date"].dt.month

df_cat = df.groupby("Category", as_index=False).agg(
    tasks=("Task", "count"),
    downtime=("Downtime_h", "sum"),
).sort_values("downtime", ascending=False)

kiln_expl = df[["Task", "Downtime_h", "Kilns"]].explode("Kilns")
df_kiln = kiln_expl.dropna(subset=["Kilns"]).groupby("Kilns", as_index=False).agg(
    tasks=("Task", "count"),
    downtime=("Downtime_h", "sum"),
).sort_values("downtime", ascending=False)

people_expl = df[["Task", "Downtime_h", "People"]].explode("People")
df_people = people_expl.dropna(subset=["People"]).groupby("People", as_index=False).agg(
    tasks=("Task", "count"),
    downtime=("Downtime_h", "sum"),
).sort_values("downtime", ascending=False)

top_tasks = df.sort_values("Downtime_h", ascending=False).head(15)[
    ["Date", "Task", "Downtime_h", "Note", "Category"]
]

if page.startswith("Transaction Performance"):
    left, right = st.columns(2)

    with left:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Công việc & Downtime theo thời gian")
        fig = px.line(df_day, x="Date", y="downtime", markers=True, title=None)
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(df_day, x="Date", y="tasks", title=None)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Top công việc gây downtime cao")
        st.dataframe(top_tasks, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Cơ cấu downtime theo nhóm công việc")
    fig3 = px.pie(df_cat, values="downtime", names="Category", hole=0.55)
    st.plotly_chart(fig3, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("Customer Behavior"):
    left, right = st.columns([1.2, 1])

    with left:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Phân bổ khối lượng theo nhân sự (ước tính)")
        fig = px.bar(df_people.head(20), x="downtime", y="People", orientation="h", title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Lưu ý: tên nhân sự được tách heuristic từ phần sau dấu ':' trong mô tả.")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Số công việc theo nhân sự")
        fig2 = px.bar(df_people.head(20), x="tasks", y="People", orientation="h", title=None)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Bảng chi tiết theo nhân sự")
    st.dataframe(df_people, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("Channel Strategy"):
    left, right = st.columns(2)

    with left:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Downtime theo Lò")
        if len(df_kiln):
            fig = px.bar(df_kiln, x="downtime", y="Kilns", orientation="h", title=None)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Không có ghi chú Lò trong dữ liệu đã lọc.")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Số công việc theo Lò")
        if len(df_kiln):
            fig2 = px.bar(df_kiln, x="tasks", y="Kilns", orientation="h", title=None)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Không có ghi chú Lò trong dữ liệu đã lọc.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Heatmap Downtime: Ngày x Nhóm công việc")
    heat = df.pivot_table(index="Day", columns="Category", values="Downtime_h", aggfunc="sum", fill_value=0)
    heat = heat.reset_index().melt(id_vars="Day", var_name="Category", value_name="Downtime_h")
    fig3 = px.density_heatmap(heat, x="Category", y="Day", z="Downtime_h", histfunc="sum", title=None)
    st.plotly_chart(fig3, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("Transaction Type"):
    left, right = st.columns(2)

    with left:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Cơ cấu số lượng công việc theo nhóm")
        fig = px.bar(df_cat.sort_values("tasks", ascending=False), x="Category", y="tasks", title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="block">', unsafe_allow_html=True)
        st.subheader("Cơ cấu downtime theo nhóm")
        fig2 = px.bar(df_cat, x="Category", y="downtime", title=None)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Bảng nhóm công việc")
    st.dataframe(df_cat, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Projects & plans (if available)
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Tổng hợp dự án & kế hoạch (nếu có trong file)")
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Dự án trong tháng (tiến độ)**")
        proj = projects.copy()
        if len(proj):
            proj = proj[proj["Month"].isin(sel_months)]
            proj = proj.sort_values("Progress", ascending=False)
            figp = px.bar(proj, x="Progress", y="Project", orientation="h", title=None, range_x=[0, 1])
            st.plotly_chart(figp, use_container_width=True)
            st.dataframe(proj, use_container_width=True, hide_index=True)
        else:
            st.info("Không tìm thấy bảng 'Tổng hợp các dự án' trong tháng đã chọn.")

    with colB:
        st.markdown("**Kế hoạch tháng sau (mục tiêu tiến độ)**")
        pl = plans.copy()
        if len(pl):
            pl = pl[pl["Month"].isin(sel_months)]
            figq = px.bar(pl.sort_values("Target", ascending=False), x="Target", y="PlanItem", orientation="h", title=None, range_x=[0, 1])
            st.plotly_chart(figq, use_container_width=True)
            st.dataframe(pl, use_container_width=True, hide_index=True)
        else:
            st.info("Không tìm thấy bảng 'Kế hoạch' trong tháng đã chọn.")
    st.markdown("</div>", unsafe_allow_html=True)

else:  # Risk & Sustainability
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Cảnh báo nhanh (anomaly-style)")

    # Thresholds
    p90 = np.percentile(df_day["downtime"], 90) if len(df_day) else 0
    heavy_days = df_day[df_day["downtime"] >= p90].sort_values("downtime", ascending=False)

    col1, col2, col3 = st.columns(3)
    with col1:
        kpi("Ngưỡng ngày downtime cao (P90)", f"{p90:,.1f}h".replace(",", "."), "Top 10% ngày có downtime lớn")
    with col2:
        worst_day = heavy_days.iloc[0] if len(heavy_days) else None
        kpi("Ngày downtime cao nhất", "-" if worst_day is None else worst_day["Date"].strftime("%Y-%m-%d"),
            "-" if worst_day is None else f"{worst_day['downtime']:.1f}h".replace(",", "."))
    with col3:
        if len(df_kiln):
            worst_k = df_kiln.iloc[0]
            kpi("Lò downtime cao nhất", str(worst_k["Kilns"]), f"{worst_k['downtime']:.1f}h".replace(",", "."))
        else:
            kpi("Lò downtime cao nhất", "-", "Không đủ dữ liệu Lò")

    st.markdown("**Danh sách ngày cần chú ý (top downtime)**")
    st.dataframe(heavy_days.head(20), use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Chất lượng dữ liệu ghi nhận")
    missing_note = df["Note"].isna().mean()
    zero_downtime = (df["Downtime_h"] == 0).mean()
    colA, colB, colC = st.columns(3)
    with colA: kpi("Tỷ lệ thiếu ghi chú (Note)", f"{missing_note*100:.1f}%", "Gợi ý: chuẩn hóa ghi chú Lò/địa bàn")
    with colB: kpi("Tỷ lệ downtime = 0", f"{zero_downtime*100:.1f}%", "Có thể là không dừng lò hoặc chưa ghi")
    with colC: kpi("Số công việc không phân loại", f"{(df['Category']=='Khác').sum():,}".replace(",", "."),
                   "Gợi ý: mở rộng từ khóa phân loại")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.caption("Gợi ý: đặt file Excel cùng thư mục với app.py (hoặc sửa biến XLSX_PATH).")
