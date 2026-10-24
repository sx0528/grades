import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from common import (CONFIG_FILE_PATH, load_config, save_config,
                    get_password_hash, verify_password, upgrade_password_hash,
                    parse_dates, GRADE_ICONS, score_to_grade)
# === 1. 配置与初始化 ===
USER_DATA_DIR = "user_data"
CONFIG_FILE_PATH = os.path.join(USER_DATA_DIR, "users_config.json")
# 创建数据目录
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)
# 初始化配置文件
if not os.path.exists(CONFIG_FILE_PATH):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump({"users": {}}, f)
st.set_page_config(page_title="🔐 高考成绩追踪器", layout="wide")
st.title("🎯 个人高考成绩追踪系统")
# === 2. 辅助函数 ===
def get_user_data_path():
    return os.path.join(USER_DATA_DIR, f"{st.session_state['user_key']}.csv")
def load_user_data():
    path = get_user_data_path()
    if os.path.exists(path):
        return pd.read_csv(path)
    else:
        return pd.DataFrame()
def save_user_data(df):
    path = get_user_data_path()
    df.to_csv(path, index=False)
def get_subject_cols(subject_config):
    """返回 [(科目名, CSV列名)]，选科取赋分后成绩，首选科目为原始列"""
    mode = subject_config["mode"]
    result = []
    if mode == "3+3":
        result = [(sub, f"{sub}_赋分") for sub in subject_config["selected"]]
    elif mode == "3+1+2":
        result = [(subject_config["primary"], subject_config["primary"])]
        result += [(sub, f"{sub}_赋分") for sub in subject_config["secondary"]]
    return result

def check_data_quality(df, subject_cols):
    """数据完整性检查，返回问题描述列表"""
    issues = []
    core_cols = ["考试时间", "语文", "数学", "英语", "赋分前总分",
                 "赋分后总分", "班级排名", "年级排名"]
    for col in dict.fromkeys(core_cols + [c for _, c in subject_cols]):
        if col in df.columns:
            na_idx = df[df[col].isna()].index.tolist()
            if na_idx:
                issues.append(f"「{col}」存在缺失值：第 {', '.join(str(i + 1) for i in na_idx)} 条记录")
    limits = {"语文": 150, "数学": 150, "英语": 150, "赋分后总分": 750}
    for col, mx in limits.items():
        if col in df.columns and (df[col] > mx).any():
            bad = df[df[col] > mx].index.tolist()
            issues.append(f"「{col}」超过满分 {mx}：第 {', '.join(str(i + 1) for i in bad)} 条记录，请核对")
    for _, col in subject_cols:
        if col in df.columns and (df[col] > 100).any():
            bad = df[df[col] > 100].index.tolist()
            issues.append(f"「{col}」超过 100 分：第 {', '.join(str(i + 1) for i in bad)} 条记录，请核对")
    return issues
# === 3. 身份验证与用户管理 ===
def authentication():
    st.sidebar.header("🔐 身份验证")
    if 'user_key' not in st.session_state:
        st.session_state['user_key'] = None
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    if 'temp_name' not in st.session_state:
        st.session_state['temp_name'] = ""
    user_name = st.sidebar.text_input("👤 请输入姓名", value=st.session_state['temp_name'])
    role = st.sidebar.radio("身份", ["学生", "教师"], key="role")
    if role == "学生":
        exam_mode = st.sidebar.selectbox("📚 选择高考模式", ["", "3+3", "3+1+2"], index=0)
        if not user_name or not exam_mode:
            st.info("请在左侧边栏填写姓名并选择高考模式。")
            st.stop()
        user_key = f"{user_name}_{exam_mode}"
    else:
        if not user_name:
            st.info("请在左侧边栏填写姓名。")
            st.stop()
        user_key = f"{user_name}_教师"
        exam_mode = "教师"
    st.session_state['user_key'] = user_key
    st.session_state['temp_name'] = user_name
    st.session_state['exam_mode'] = exam_mode
    config = load_config()
    user_record = config["users"].get(user_key)
    # 新用户注册
    if user_record is None:
        st.sidebar.info(f"👋 新用户 detected，请设置密码:")
        pwd = st.sidebar.text_input("设置密码", type="password", key="reg_pwd")
        pwd2 = st.sidebar.text_input("确认密码", type="password", key="reg_pwd2")
        if st.sidebar.button("注册账户"):
            if pwd and pwd == pwd2 and len(pwd) >= 4:
                config["users"][user_key] = {
                    "password_hash": get_password_hash(pwd),
                    "subject_config": None
                }
                save_config(config)
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.sidebar.error("密码为空、不一致或太短")
                st.stop()
        st.stop()
    # 老用户登录
    else:
        pwd = st.sidebar.text_input("🔑 请输入密码", type="password", key="login_pwd")
        if st.sidebar.button("登录"):
            ok, is_legacy = verify_password(user_record["password_hash"], pwd)
            if ok:
                if is_legacy:
                    upgrade_password_hash(user_key, pwd)  # 旧哈希自动升级为 PBKDF2
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.sidebar.error("密码错误")
                st.stop()

        if not st.session_state['authenticated']:
            st.stop()
# === 4. 选科配置 ===
def subject_setup():
    user_key = st.session_state['user_key']
    config = load_config()
    user_record = config["users"][user_key]
    if user_record["subject_config"] is not None:
        return user_record["subject_config"]
    st.subheader("⚙️ 科目设置 (仅需一次)")
    mode = st.session_state['exam_mode']
    if mode == "3+3":
        st.info("请从以下科目中选择 3 门：")
        options = ["物理", "化学", "生物", "政治", "历史", "地理"]
        selected = st.multiselect("选择科目", options, max_selections=3)
        if len(selected) == 3 and st.button("💾 保存选科"):
            config["users"][user_key]["subject_config"] = {
                "mode": "3+3",
                "selected": selected
            }
            save_config(config)
            st.success("设置成功！")
            st.rerun()
    elif mode == "3+1+2":
        col1, col2 = st.columns(2)
        with col1:
            st.info("首选科目 (1门)：")
            primary = st.radio("选择", ["物理", "历史"], key="ph")
        with col2:
            st.info("再选科目 (2门)：")
            options = ["化学", "生物", "政治", "地理"]
            secondary = st.multiselect("选择", options, max_selections=2)
        if len(secondary) == 2 and st.button("💾 保存选科"):
            config["users"][user_key]["subject_config"] = {
                "mode": "3+1+2",
                "primary": primary,
                "secondary": secondary
            }
            save_config(config)
            st.success("设置成功！")
            st.rerun()
    st.stop()
# === 5. 主程序逻辑 ===
def main_app():
    user_key = st.session_state['user_key']
    config = load_config()
    subject_config = config["users"][user_key]["subject_config"]
    st.sidebar.success(f"你好，{st.session_state['temp_name']}")
    # --- 录入表单 ---
    with st.form("grade_form"):
        st.subheader("📝 录入成绩")
        col1, col2 = st.columns(2)
        with col1:
            exam_date = st.date_input("考试时间", datetime.now())
            exam_type = st.selectbox("考试类型", ["月考", "期中", "期末", "模拟考", "其他"], index=0)
            raw_total = st.number_input("赋分前总分", 0.0, 1000.0, step=0.5)
            converted_total = st.number_input("赋分后总分", 0.0, 1000.0, step=0.5)
            class_rank = st.number_input("班级排名", 1, 1000, step=1)
            grade_rank = st.number_input("年级排名", 1, 10000, step=1)
        with col2:
            st.markdown("#### 主科成绩")
            chinese = st.number_input("语文", 0.0, 150.0, step=0.5)
            math = st.number_input("数学", 0.0, 150.0, step=0.5)
            english = st.number_input("英语", 0.0, 150.0, step=0.5)
            st.markdown("#### 选科成绩")
            # 动态生成输入框
            input_data = {}
            if subject_config["mode"] == "3+3":
                for sub in subject_config["selected"]:
                    raw = st.number_input(f"{sub} (原始分)", 0.0, 100.0, step=0.5, key=f"raw_{sub}")
                    conv = st.number_input(f"{sub} (赋分后)", 0.0, 100.0, step=0.5, key=f"conv_{sub}")
                    input_data[f"{sub}_原始"] = raw
                    input_data[f"{sub}_赋分"] = conv
            elif subject_config["mode"] == "3+1+2":
                # 首选科目
                ph_sub = subject_config["primary"]
                ph_score = st.number_input(f"{ph_sub} (首选)", 0.0, 100.0, step=0.5, key=f"ph_{ph_sub}")
                input_data[ph_sub] = ph_score
                # 再选科目
                for sub in subject_config["secondary"]:
                    raw = st.number_input(f"{sub} (原始分)", 0.0, 100.0, step=0.5, key=f"raw_{sub}")
                    conv = st.number_input(f"{sub} (赋分后)", 0.0, 100.0, step=0.5, key=f"conv_{sub}")
                    input_data[f"{sub}_原始"] = raw
                    input_data[f"{sub}_赋分"] = conv
        submit = st.form_submit_button("💾 提交成绩")
        if submit:
            # 构建数据字典
            new_record = {
                "考试时间": exam_date,
                "考试类型": exam_type,
                "语文": chinese,
                "数学": math,
                "英语": english,
                "赋分前总分": raw_total,
                "赋分后总分": converted_total,
                "班级排名": class_rank,
                "年级排名": grade_rank,
                **input_data
            }
            # 保存到CSV
            df = load_user_data()
            new_df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
            save_user_data(new_df)
            st.success("录入成功！")
            st.rerun()
    # --- 数据展示与分析 ---
    df = load_user_data()
    if not df.empty:
        st.divider()
        st.subheader("📊 数据分析")
        df = df.sort_values("考试时间").reset_index(drop=True)
        df["考试时间"] = parse_dates(df["考试时间"])
        if "考试类型" not in df.columns:
            df["考试类型"] = "未标记"
        df["考试类型"] = df["考试类型"].fillna("未标记")
        subject_cols = get_subject_cols(subject_config)
        target_config = config["users"][user_key].get("target_config") or {}
        size_config = config["users"][user_key].get("size_config") or {}
        last = df.iloc[-1]

        # --- 数据完整性提醒 ---
        quality_issues = check_data_quality(df, subject_cols)
        if quality_issues:
            with st.expander(f"⚠️ 数据完整性提醒（{len(quality_issues)} 项待核对）", expanded=len(quality_issues) <= 2):
                for msg in quality_issues:
                    st.warning(msg)

        # --- 环比分析卡片 ---
        if len(df) > 1:
            prev = df.iloc[-2]
            st.markdown("##### ⚡ 与上次考试对比")
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "赋分后总分",
                f"{last['赋分后总分']:g}",
                f"{last['赋分后总分'] - prev['赋分后总分']:+g}",
            )
            c2.metric("年级排名", f"{int(last['年级排名'])}",
                      f"{int(prev['年级排名'] - last['年级排名']):+d} 名")
            c3.metric("班级排名", f"{int(last['班级排名'])}",
                      f"{int(prev['班级排名'] - last['班级排名']):+d} 名")
            if subject_cols:
                changes = [
                    f"{name} {last[col] - prev[col]:+g}"
                    for name, col in subject_cols
                    if col in df.columns and last[col] != prev[col]
                ]
                if changes:
                    st.caption("单科变化：" + "，".join(changes))

        # --- 位次百分位 ---
        if size_config.get("grade_size") or size_config.get("class_size"):
            pct_parts = []
            if size_config.get("grade_size"):
                pct_parts.append(f"年级：前 {last['年级排名'] / size_config['grade_size'] * 100:.1f}%")
            if size_config.get("class_size"):
                pct_parts.append(f"班级：前 {last['班级排名'] / size_config['class_size'] * 100:.1f}%")
            st.caption("📐 位次百分位（最近一次考试）：" + "，".join(pct_parts))

        # --- 学科雷达图 ---
        if subject_cols:
            st.markdown("##### 🕸️ 学科雷达图")
            cats = [name for name, _ in subject_cols]
            latest_vals = [last[col] if col in df.columns else 0 for _, col in subject_cols]
            avg_vals = [df[col].mean() if col in df.columns else 0 for _, col in subject_cols]
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=latest_vals, theta=cats, fill="toself", name="最近一次"))
            fig_radar.add_trace(go.Scatterpolar(
                r=avg_vals, theta=cats, fill="toself", name="历次平均",
                line=dict(dash="dash")))
            tgt_subjects = target_config.get("subjects", {})
            tgt_vals = [tgt_subjects.get(name, 0) or None for name in cats]
            if any(v is not None for v in tgt_vals):
                fig_radar.add_trace(go.Scatterpolar(
                    r=tgt_vals, theta=cats, name="目标分",
                    line=dict(dash="dot", color="red")))
            rmax = max(
                [100] + [v for v in latest_vals + avg_vals if v] +
                [v for v in tgt_vals if v]
            ) * 1.05
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(range=[0, rmax], visible=True)),
                showlegend=True, height=420)
            st.plotly_chart(fig_radar, use_container_width=True)

        # --- 赋分等级（最近一次） ---
        if subject_cols:
            grade_parts = []
            for name, col in subject_cols:
                if col not in df.columns:
                    continue
                g = score_to_grade(last[col])
                if not g:
                    continue
                delta = ""
                if len(df) > 1:
                    gp = score_to_grade(df.iloc[-2][col])
                    if gp and g != gp:
                        delta = f"（{'↑' if g < gp else '↓'}，上次 {gp}）"  # 字母序越靠前等级越高
                grade_parts.append(f"{GRADE_ICONS[g]} {name} {g}{delta}")
            if grade_parts:
                st.markdown("##### 🏅 赋分等级（最近一次考试）")
                st.markdown("　".join(grade_parts))

        # --- 目标设置与差距分析 ---
        with st.expander("🎯 目标设置（保存后用于差距分析）", expanded=not bool(target_config)):
            with st.form("target_form"):
                t_total = st.number_input(
                    "目标总分（赋分后）", 0.0, 1000.0,
                    value=float(target_config.get("total", 0)), step=0.5)
                tsubs = {}
                if subject_cols:
                    st.caption("各科目标分（选填，0 表示不设目标；选科按赋分后计算）")
                    t_cols = st.columns(3)
                    for i, (name, _) in enumerate(subject_cols):
                        with t_cols[i % 3]:
                            tsubs[name] = st.number_input(
                                name, 0.0, 150.0,
                                value=float(tgt_subjects.get(name, 0)),
                                step=0.5, key=f"tgt_{name}")
                if st.form_submit_button("💾 保存目标"):
                    config["users"][user_key]["target_config"] = {
                        "total": t_total,
                        "subjects": {k: v for k, v in tsubs.items() if v > 0}
                        if subject_cols else {}
                    }
                    save_config(config)
                    st.success("目标已保存！")
                    st.rerun()
        if target_config:
            st.markdown("##### 🎯 差距分析（最近一次考试 vs 目标）")
            gap_rows = []
            for name, col in subject_cols:
                tgt = tgt_subjects.get(name, 0)
                if tgt > 0 and col in df.columns:
                    gap_rows.append({"科目": name, "最近成绩": last[col],
                                     "目标分": tgt, "差距": last[col] - tgt})
            if target_config.get("total", 0) > 0:
                t_total = target_config["total"]
                gap_rows.append({"科目": "总分", "最近成绩": last["赋分后总分"],
                                 "目标分": t_total, "差距": last["赋分后总分"] - t_total})
            if gap_rows:
                st.dataframe(pd.DataFrame(gap_rows), hide_index=True,
                             use_container_width=True)
            else:
                st.info("尚未设置任何目标分。")

        # --- 排名基准设置 ---
        with st.expander("📐 排名基准设置（班级/年级人数，填 0 表示不设置）"):
            with st.form("size_form"):
                s1, s2 = st.columns(2)
                cls_size = s1.number_input("班级人数", 0, 200,
                                           value=int(size_config.get("class_size") or 0))
                grd_size = s2.number_input("年级人数", 0, 5000,
                                           value=int(size_config.get("grade_size") or 0))
                if st.form_submit_button("💾 保存基准"):
                    config["users"][user_key]["size_config"] = {
                        "class_size": int(cls_size) if cls_size > 0 else None,
                        "grade_size": int(grd_size) if grd_size > 0 else None,
                    }
                    save_config(config)
                    st.success("基准已保存！")
                    st.rerun()

        # --- 趋势图 ---
        chart_df = df
        all_types = df["考试类型"].unique().tolist()
        if all_types != ["未标记"]:
            sel_types = st.multiselect("筛选考试类型", all_types, default=all_types, key="type_filter")
            if sel_types and len(sel_types) < len(all_types):
                chart_df = df[df["考试类型"].isin(sel_types)]
                if chart_df.empty:
                    chart_df = df
                    st.caption("所选类型无数据，已显示全部记录。")
        fig_total = px.line(chart_df, x="考试时间", y=["赋分前总分", "赋分后总分"], markers=True, title="总分趋势")
        st.plotly_chart(fig_total, use_container_width=True)
        # 排名趋势 (越低越好)
        fig_rank = px.line(chart_df, x="考试时间", y=["班级排名", "年级排名"], markers=True, title="排名趋势 (越低越好)")
        fig_rank.update_yaxes(autorange="reversed")  # 排名倒序
        st.plotly_chart(fig_rank, use_container_width=True)
        # 位次百分位趋势 (越低越好)
        if size_config.get("grade_size"):
            pct_series = chart_df["年级排名"] / size_config["grade_size"] * 100
            fig_pct = px.line(x=chart_df["考试时间"], y=pct_series, markers=True,
                              title="年级位次百分位趋势（%，越低越好）",
                              labels={"x": "考试时间", "y": "位次百分位 (%)"})
            st.plotly_chart(fig_pct, use_container_width=True)
        # --- 历史记录管理 ---
        st.subheader("🗑️ 管理历史记录")
        data_to_edit = df.copy()
        data_to_edit.insert(0, "Delete", False)
        edited = st.data_editor(
            data_to_edit,
            column_config={"Delete": st.column_config.CheckboxColumn("删除?")},
            hide_index=False,
            use_container_width=True
        )
        if st.button("清理选中行"):
            df_filtered = df[~edited["Delete"]]
            save_user_data(df_filtered)
            st.success("清理完成！")
            st.rerun()
    else:
        st.info("暂无数据，请录入成绩。")

    # --- Excel 导入 / 导出（数据为空时也可导入） ---
    st.divider()
    st.subheader("📁 数据导入 / 导出")
    if not df.empty:
        buf = BytesIO()
        df.to_excel(buf, index=False)
        st.download_button(
            "⬇️ 导出全部数据 (Excel)", data=buf.getvalue(),
            file_name=f"{st.session_state['user_key']}_成绩.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded = st.file_uploader(
        "⬆️ 导入 Excel/CSV（必需列：考试时间、语文、数学、英语、赋分前总分、赋分后总分、班级排名、年级排名）",
        type=["xlsx", "xls", "csv"])
    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                new_df = pd.read_csv(uploaded)
            else:
                new_df = pd.read_excel(uploaded)
        except Exception as e:
            st.error(f"文件读取失败：{e}")
        else:
            required = ["考试时间", "语文", "数学", "英语", "赋分前总分",
                        "赋分后总分", "班级排名", "年级排名"]
            missing = [c for c in required if c not in new_df.columns]
            if missing:
                st.error(f"导入失败，缺少必需列：{'、'.join(missing)}")
            else:
                if "考试类型" not in new_df.columns:
                    new_df["考试类型"] = "未标记"
                merged = pd.concat([df, new_df], ignore_index=True)
                merged["考试时间"] = parse_dates(merged["考试时间"])
                dropped = int(merged["考试时间"].isna().sum())
                merged = merged.dropna(subset=["考试时间"])
                save_user_data(merged)
                st.success(f"导入成功，共 {len(new_df)} 条记录"
                           + (f"，剔除无法识别日期的 {dropped} 条" if dropped else ""))
                st.rerun()
# === 6. 程序入口 ===
if __name__ == "__main__":
    authentication()
    if str(st.session_state.get('user_key', '')).endswith("_教师"):
        import teacher
        teacher.run_teacher_app()
    else:
        subject_setup()
        main_app()
