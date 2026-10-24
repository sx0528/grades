"""教师工作台：班级成绩一键导入、班级分析、学生报告。"""
import os
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from common import load_config, save_config, parse_dates

TEACHER_DATA_DIR = "teacher_data"
# 教师成绩表中不属于科目分数的列
RESERVED_COLS = {"姓名", "学号", "考试时间", "考试类型", "总分",
                 "班级排名", "年级排名", "赋分前总分", "赋分后总分"}
# 常见科目默认满分，未列出的按 100
DEFAULT_FULL_MARKS = {"语文": 150, "数学": 150, "英语": 150}
EXAM_TYPES = ["月考", "期中", "期末", "模拟考", "其他"]


def full_marks(subject):
    return DEFAULT_FULL_MARKS.get(subject, 100)


def _grades_path(teacher_key):
    return os.path.join(TEACHER_DATA_DIR, teacher_key, "grades.csv")


def _load_grades(teacher_key):
    path = _grades_path(teacher_key)
    if os.path.exists(path):
        # 姓名强制按字符串读：纯数字姓名（如班级学号）否则会变成 int 导致拼接/筛选异常
        df = pd.read_csv(path, dtype={"姓名": str})
        if "姓名" in df.columns:
            df["姓名"] = df["姓名"].fillna("").astype(str).str.strip()
            df = df[df["姓名"] != ""]
        if "考试时间" in df.columns:
            df["考试时间"] = parse_dates(df["考试时间"])
        return df
    return pd.DataFrame()


def _save_grades(teacher_key, df):
    os.makedirs(os.path.join(TEACHER_DATA_DIR, teacher_key), exist_ok=True)
    df.to_csv(_grades_path(teacher_key), index=False)


def _get_teacher_config(teacher_key):
    config = load_config()
    cfg = config["users"].get(teacher_key, {}).get("teacher_config")
    if cfg is None:
        cfg = {"class_name": "", "subjects": ["语文", "数学", "英语"], "students": []}
    return cfg


def _save_teacher_config(teacher_key, cfg):
    config = load_config()
    config["users"].setdefault(teacher_key, {})["teacher_config"] = cfg
    save_config(config)


def _exam_label(df):
    """按时间顺序生成 '2026-10-01 期中' 形式的场次标签，返回 (df 排序副本, 标签列表)"""
    df = df.sort_values(["考试时间", "考试类型"]).reset_index(drop=True)
    labels = (df["考试时间"].dt.strftime("%Y-%m-%d") + " " + df["考试类型"].fillna("未标记")).tolist()
    return df, labels


# ================= 班级设置 =================
def _render_setup(teacher_key, cfg):
    with st.form("setup_form"):
        class_name = st.text_input("班级名称", value=cfg.get("class_name", ""))
        subjects = st.multiselect(
            "统计科目（导入文件中的新科目列会自动加入）",
            ["语文", "数学", "英语", "物理", "化学", "生物", "政治", "历史", "地理"],
            default=cfg.get("subjects", ["语文", "数学", "英语"]))
        students_text = st.text_area(
            "学生名单（一行一个姓名，用于核对未交成绩的学生）",
            value="\n".join(cfg.get("students", [])), height=120)
        if st.form_submit_button("💾 保存班级设置"):
            cfg["class_name"] = class_name.strip()
            cfg["subjects"] = subjects
            cfg["students"] = [s.strip() for s in students_text.splitlines() if s.strip()]
            _save_teacher_config(teacher_key, cfg)
            st.success("班级设置已保存！")
            st.rerun()
    st.caption("提示：语数英满分按 150、其余科目按 100 计算及格率/优秀率。")


# ================= 批量导入 =================
def _build_template(cfg):
    rows = []
    for i, name in enumerate(["张三", "李四", "王五"]):
        row = {"姓名": name, "考试时间": "2026-10-01", "考试类型": "月考"}
        for sub in cfg.get("subjects", ["语文", "数学", "英语"]):
            row[sub] = 100 + i * 10 if sub in DEFAULT_FULL_MARKS else 70 + i * 5
        row["班级排名"] = i + 1
        rows.append(row)
    buf = BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _parse_upload(uploaded, cfg):
    """解析上传文件 → (标准化 DataFrame 或 None, 新增科目列表, 警告列表)"""
    try:
        if uploaded.name.lower().endswith(".csv"):
            df_in = pd.read_csv(uploaded)
        else:
            df_in = pd.read_excel(uploaded)
    except Exception as e:
        return None, [], [f"文件读取失败：{e}"]
    df_in.columns = [str(c).strip() for c in df_in.columns]
    if "姓名" not in df_in.columns:
        return None, [], ["缺少「姓名」列，无法导入。请下载模板参照格式填写。"]

    warnings, skipped = [], []
    # 识别科目列：保留列之外的、至少有一个可解析为数字的列
    subject_cols = []
    for c in df_in.columns:
        if c in RESERVED_COLS:
            continue
        if pd.to_numeric(df_in[c], errors="coerce").notna().any():
            subject_cols.append(c)
    new_subjects = [c for c in subject_cols if c not in cfg.get("subjects", [])]

    records = []
    for idx, row in df_in.iterrows():
        name = str(row.get("姓名", "") or "").strip()
        if not name or name.lower() == "nan":
            skipped.append(idx + 2)  # Excel 行号从 1 起，含表头
            continue
        rec = {"姓名": name}
        exam_time = row.get("考试时间")
        rec["考试时间"] = pd.to_datetime(exam_time, errors="coerce") if pd.notna(exam_time) \
            else pd.Timestamp(datetime.now().date())
        rec["考试类型"] = str(row.get("考试类型") or "").strip() or "未标记"
        score_sum = 0.0
        for c in subject_cols:
            val = pd.to_numeric(pd.Series([row.get(c)]), errors="coerce").iloc[0]
            if pd.isna(val) and pd.notna(row.get(c)) and str(row.get(c)).strip():
                warnings.append(f"第 {idx + 2} 行「{c}」的值“{row.get(c)}”不是数字，按缺考处理")
            rec[c] = val
            if pd.notna(val):
                score_sum += float(val)
        rec["总分"] = pd.to_numeric(pd.Series([row.get("总分")]), errors="coerce").iloc[0] \
            if pd.notna(row.get("总分")) else score_sum
        for rank_col in ("班级排名", "年级排名"):
            if rank_col in df_in.columns:
                rec[rank_col] = pd.to_numeric(pd.Series([row.get(rank_col)]), errors="coerce").iloc[0]
        records.append(rec)

    if not records:
        return None, new_subjects, warnings + ["没有找到有效数据行（缺少姓名）。"]
    if skipped:
        warnings.append(f"以下 Excel 行缺少姓名被跳过：第 {', '.join(map(str, skipped))} 行")

    ordered = (["姓名", "考试时间", "考试类型"]
               + subject_cols + ["总分"]
               + [c for c in ("班级排名", "年级排名") if c in df_in.columns])
    return pd.DataFrame(records).reindex(columns=ordered), new_subjects, warnings


def _render_import(teacher_key, cfg):
    st.markdown("把全班成绩 Excel/CSV 一次导入：**一行 = 一个学生一次考试**。"
                "科目列自动识别，缺「总分」列时自动按各科求和；同名学生同日期的记录会被新数据覆盖。")
    st.download_button("⬇️ 下载导入模板", data=_build_template(cfg),
                       file_name="成绩导入模板.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded = st.file_uploader("上传全班成绩文件", type=["xlsx", "xls", "csv"], key="t_upload")
    if uploaded is None:
        return
    std_df, new_subjects, warnings = _parse_upload(uploaded, cfg)
    if std_df is None:
        for w in warnings:
            st.error(w)
        return
    for w in warnings:
        st.warning(w)
    st.success(f"解析成功：{std_df['姓名'].nunique()} 名学生，共 {len(std_df)} 条成绩记录。")
    st.dataframe(std_df, hide_index=True, use_container_width=True)
    if new_subjects:
        st.info(f"检测到新科目列：{'、'.join(new_subjects)}，确认导入后将自动加入统计科目。")
    if st.button(f"✅ 确认导入（{len(std_df)} 条）", type="primary"):
        existing = _load_grades(teacher_key)
        merged = pd.concat([existing, std_df], ignore_index=True) if not existing.empty else std_df
        # 统一列集合并去重：同一学生同一天保留最新
        merged = merged.reindex(columns=sorted(set(merged.columns),
                                               key=lambda c: (c not in ("姓名", "考试时间", "考试类型", "总分"), c)))
        merged = merged.drop_duplicates(subset=["姓名", "考试时间"], keep="last")
        merged = merged.sort_values(["考试时间", "姓名"]).reset_index(drop=True)
        _save_grades(teacher_key, merged)
        if new_subjects:
            cfg["subjects"] = cfg.get("subjects", []) + new_subjects
            _save_teacher_config(teacher_key, cfg)
        st.success(f"导入完成！班级现有 {merged['姓名'].nunique()} 名学生、"
                   f"{merged['考试时间'].nunique()} 个考试场次。")
        st.rerun()
    st.divider()
    df = _load_grades(teacher_key)
    if not df.empty:
        buf = BytesIO()
        df.to_excel(buf, index=False)
        st.download_button("⬇️ 导出全班成绩 (Excel)", data=buf.getvalue(),
                           file_name=f"{cfg.get('class_name') or teacher_key}_全班成绩.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ================= 单条录入 =================
def _render_manual_entry(teacher_key, cfg):
    df = _load_grades(teacher_key)
    known_students = sorted(set(df["姓名"].tolist()) if not df.empty else set())
    subjects = cfg.get("subjects", ["语文", "数学", "英语"])
    if not subjects:
        st.info("请先在「班级设置」中选择统计科目。")
        return
    with st.form("manual_entry_form"):
        cols = st.columns(3)
        name = cols[0].text_input("学生姓名")
        exam_date = cols[1].date_input("考试时间", datetime.now(), key="t_date")
        exam_type = cols[2].selectbox("考试类型", EXAM_TYPES, key="t_type")
        st.markdown("#### 各科成绩")
        scores = {}
        s_cols = st.columns(max(1, min(len(subjects), 6)))
        for i, sub in enumerate(subjects):
            with s_cols[i % len(s_cols)]:
                scores[sub] = st.number_input(f"{sub}（满分 {full_marks(sub)}）",
                                              0.0, float(full_marks(sub)), step=0.5,
                                              key=f"t_score_{sub}")
        rank_cols = st.columns(2)
        class_rank = rank_cols[0].number_input("班级排名（选填，0 跳过）", 0, 200, 0)
        grade_rank = rank_cols[1].number_input("年级排名（选填，0 跳过）", 0, 5000, 0)
        if st.form_submit_button("💾 保存该条成绩"):
            if not name.strip():
                st.error("请填写学生姓名。")
            else:
                rec = {"姓名": name.strip(), "考试时间": pd.Timestamp(exam_date),
                       "考试类型": exam_type, **scores,
                       "总分": sum(v for v in scores.values() if pd.notna(v))}
                if class_rank > 0:
                    rec["班级排名"] = float(class_rank)
                if grade_rank > 0:
                    rec["年级排名"] = float(grade_rank)
                existing = _load_grades(teacher_key)
                merged = pd.concat([existing, pd.DataFrame([rec])], ignore_index=True) \
                    if not existing.empty else pd.DataFrame([rec])
                merged = merged.drop_duplicates(subset=["姓名", "考试时间"], keep="last")
                _save_grades(teacher_key, merged)
                st.success(f"{name.strip()} 的成绩已保存！")
                st.rerun()
    if known_students:
        st.caption(f"已录入过的学生：{'、'.join(known_students)}")


# ================= 班级分析 =================
def _subject_stats(exam_df, subjects):
    rows = []
    for sub in subjects:
        s = pd.to_numeric(exam_df[sub], errors="coerce").dropna()
        if s.empty:
            continue
        fm = full_marks(sub)
        rows.append({"科目": sub, "平均分": round(s.mean(), 1),
                     "最高分": s.max(), "最低分": s.min(),
                     "及格率": f"{(s >= fm * 0.6).mean() * 100:.0f}%",
                     "优秀率": f"{(s >= fm * 0.85).mean() * 100:.0f}%"})
    return pd.DataFrame(rows)


def _render_analysis(teacher_key, cfg):
    df = _load_grades(teacher_key)
    if df.empty:
        st.info("暂无班级数据，请先在「批量导入」上传成绩。")
        return
    subjects = [s for s in cfg.get("subjects", []) if s in df.columns]
    df, labels = _exam_label(df)
    unique_labels = list(dict.fromkeys(labels))
    sel_label = st.selectbox("选择考试场次", unique_labels, index=len(unique_labels) - 1)
    sel_date, sel_type = pd.Timestamp(sel_label[:10]), sel_label[11:]
    exam_df = df[(df["考试时间"] == sel_date) & (df["考试类型"].fillna("未标记") == sel_type)]

    # --- 总分排名表 ---
    st.markdown("##### 🏆 总分排名")
    rank_cols = ["姓名"] + subjects + ["总分"] + \
        [c for c in ("班级排名", "年级排名") if c in exam_df.columns]
    rank_df = exam_df[rank_cols].sort_values("总分", ascending=False).reset_index(drop=True)
    rank_df.insert(0, "名次", range(1, len(rank_df) + 1))
    st.dataframe(rank_df, hide_index=True, use_container_width=True)

    # --- 科目统计 ---
    if subjects:
        st.markdown("##### 📈 各科统计")
        st.dataframe(_subject_stats(exam_df, subjects), hide_index=True, use_container_width=True)

        dist_sub = st.selectbox("查看单科分数分布", subjects, key="dist_sub")
        scores = pd.to_numeric(exam_df[dist_sub], errors="coerce").dropna()
        if not scores.empty:
            fig_hist = px.histogram(x=scores, nbins=12,
                                    title=f"{dist_sub} 分数分布",
                                    labels={"x": f"{dist_sub}分数", "y": "人数"})
            st.plotly_chart(fig_hist, use_container_width=True)

    # --- 平均分趋势 ---
    if len(unique_labels) > 1:
        st.markdown("##### 📉 班级平均分趋势")
        trend_rows = []
        for lab in unique_labels:
            d, t = pd.Timestamp(lab[:10]), lab[11:]
            sub_df = df[(df["考试时间"] == d) & (df["考试类型"].fillna("未标记") == t)]
            row = {"场次": lab, "总分": round(pd.to_numeric(sub_df["总分"], errors="coerce").mean(), 1)}
            for sub in subjects:
                row[sub] = round(pd.to_numeric(sub_df[sub], errors="coerce").mean(), 1)
            trend_rows.append(row)
        trend_df = pd.DataFrame(trend_rows)
        st.dataframe(trend_df, hide_index=True, use_container_width=True)
        fig_trend = px.line(trend_df, x="场次", y=["总分"] + subjects, markers=True,
                            title="各科班级平均分趋势")
        st.plotly_chart(fig_trend, use_container_width=True)

    # --- 进退步榜 ---
    if len(unique_labels) > 1:
        st.markdown("##### 🚀 进退步榜（最近两次考试总分变化）")
        prev_label, last_label = unique_labels[-2], unique_labels[-1]

        def total_by_name(lab):
            d, t = pd.Timestamp(lab[:10]), lab[11:]
            sub_df = df[(df["考试时间"] == d) & (df["考试类型"].fillna("未标记") == t)]
            return pd.to_numeric(sub_df.set_index("姓名")["总分"], errors="coerce")

        delta = (total_by_name(last_label) - total_by_name(prev_label)).dropna()
        delta = delta.sort_values(ascending=False)
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"进步前 5（{prev_label} → {last_label}）")
            up = delta.head(5).reset_index()
            up.columns = ["姓名", "总分变化"]
            st.dataframe(up, hide_index=True, use_container_width=True)
        with c2:
            st.caption("退步前 5（需重点关注）")
            down = delta.tail(5).sort_values().reset_index()
            down.columns = ["姓名", "总分变化"]
            st.dataframe(down, hide_index=True, use_container_width=True)


# ================= 学生报告 =================
def _render_student_report(teacher_key, cfg):
    df = _load_grades(teacher_key)
    if df.empty:
        st.info("暂无班级数据，请先在「批量导入」上传成绩。")
        return
    subjects = [s for s in cfg.get("subjects", []) if s in df.columns]
    students = sorted(df["姓名"].dropna().unique().tolist())
    name = st.selectbox("选择学生", students)
    sdf = df[df["姓名"] == name].sort_values("考试时间").reset_index(drop=True)
    last, prev = sdf.iloc[-1], (sdf.iloc[-2] if len(sdf) > 1 else None)

    # 环比卡片
    if prev is not None:
        c1, c2 = st.columns(2)
        c1.metric("总分（最近一次）", f"{last['总分']:g}",
                  f"{last['总分'] - prev['总分']:+g}")
        if "班级排名" in sdf.columns and pd.notna(last.get("班级排名")) and pd.notna(prev.get("班级排名")):
            c2.metric("班级排名", f"{int(last['班级排名'])}",
                      f"{int(prev['班级排名'] - last['班级排名']):+d} 名")

    # 单科趋势
    if subjects:
        y_cols = [c for c in ["总分"] + subjects if c in sdf.columns]
        fig = px.line(sdf, x="考试时间", y=y_cols, markers=True,
                      title=f"{name} 各科成绩趋势")
        st.plotly_chart(fig, use_container_width=True)

        # 雷达图：最新一次 vs 班级平均
        df_all, labels = _exam_label(df)
        last_date, last_type = last["考试时间"], (last["考试类型"] if pd.notna(last.get("考试类型")) else "未标记")
        exam_df = df_all[(df_all["考试时间"] == last_date)
                         & (df_all["考试类型"].fillna("未标记") == last_type)]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=[last[s] if pd.notna(last.get(s)) else 0 for s in subjects],
            theta=subjects, fill="toself", name=name))
        fig_radar.add_trace(go.Scatterpolar(
            r=[pd.to_numeric(exam_df[s], errors="coerce").mean() for s in subjects],
            theta=subjects, fill="toself", name="班级平均",
            line=dict(dash="dash")))
        rmax = max(100, *[last[s] for s in subjects if pd.notna(last.get(s))],
                   *[pd.to_numeric(exam_df[s], errors="coerce").max() for s in subjects]) * 1.05
        fig_radar.update_layout(polar=dict(radialaxis=dict(range=[0, rmax], visible=True)),
                                showlegend=True, height=380,
                                title=f"{name} vs 班级平均（{last_date.date()} {last_type}）")
        st.plotly_chart(fig_radar, use_container_width=True)

        # 班级对比表
        cmp_rows = []
        rank_total = None
        if "总分" in exam_df.columns:
            ranked = exam_df.sort_values("总分", ascending=False)["姓名"].tolist()
            if name in ranked:
                rank_total = ranked.index(name) + 1
        for sub in subjects:
            sub_scores = pd.to_numeric(exam_df[sub], errors="coerce").dropna()
            mine = last[sub] if pd.notna(last.get(sub)) else None
            if mine is None:
                continue
            cmp_rows.append({"科目": sub, "本人": mine,
                             "班级平均": round(sub_scores.mean(), 1),
                             "差值": round(mine - sub_scores.mean(), 1),
                             "班级名次": int((sub_scores > mine).sum()) + 1})
        if cmp_rows:
            st.markdown("##### ⚖️ 与班级对比（最近一次考试）"
                        + (f"｜总分全班第 {rank_total} 名" if rank_total else ""))
            st.dataframe(pd.DataFrame(cmp_rows), hide_index=True, use_container_width=True)

    # 个人成绩导出
    buf = BytesIO()
    sdf.to_excel(buf, index=False)
    st.download_button(f"⬇️ 导出 {name} 的成绩单", data=buf.getvalue(),
                       file_name=f"{name}_成绩单.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ================= 入口 =================
def run_teacher_app():
    teacher_key = st.session_state['user_key']
    cfg = _get_teacher_config(teacher_key)
    st.divider()
    title = f"🏫 教师工作台{(' — ' + cfg['class_name']) if cfg.get('class_name') else ''}"
    st.header(title)

    tab_setup, tab_import, tab_entry, tab_analysis, tab_student = st.tabs(
        ["⚙️ 班级设置", "📥 批量导入", "📝 单条录入", "📊 班级分析", "🔍 学生报告"])
    with tab_setup:
        _render_setup(teacher_key, cfg)
    with tab_import:
        _render_import(teacher_key, cfg)
    with tab_entry:
        _render_manual_entry(teacher_key, cfg)
    with tab_analysis:
        _render_analysis(teacher_key, cfg)
    with tab_student:
        _render_student_report(teacher_key, cfg)
