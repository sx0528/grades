import streamlit as st
import pandas as pd
import os
from datetime import datetime
import plotly.express as px
# --- 1. 配置 (新增用户数据文件夹) ---
# 创建一个专门存放用户数据的文件夹
USER_DATA_DIR = "user_data"
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)  # 程序启动时自动创建文件夹
st.set_page_config(page_title="成绩追踪器", layout="wide")
st.title("📈 个人成绩追踪系统")
# --- 2. 用户身份选择 (新增) ---
st.sidebar.header("🔐 用户中心")
user_name = st.sidebar.text_input("请输入你的姓名", value="张三")
if not user_name.strip():
    st.warning("请先在左侧边栏输入你的姓名！")
    st.stop()  # 如果没输入名字，停止运
# --- 3. 数据读取与保存 (修改为基于用户的路径) ---
# 每个用户对应一个 CSV 文件
DATA_FILE = os.path.join(USER_DATA_DIR, f"{user_name.strip()}.csv")
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    else:
        # 如果该用户是第一次使用，创建新表
        return pd.DataFrame(columns=[
            "考试时间", "赋分前总分", "赋分后总分", "班级排名", "年级排名",
            "语文", "数学", "英语", "物理", "化学原始", "化学赋分",
            "生物原始", "生物赋分", "进退步(班)", "进退步(年)"
        ])
def save_data(df):
    df.to_csv(DATA_FILE, index=False)
# --- 4. 主程序 ---
grades_df = load_data()
# --- 5. 输入表单 ---
with st.form("grade_form"):
    st.subheader(f"📝 录入新成绩 (当前用户: {user_name})")
    col1, col2 = st.columns(2)
    with col1:
        exam_date = st.date_input("考试时间", datetime.now())
        raw_total = st.number_input("赋分前总分", min_value=0.0, max_value=1000.0)
        converted_total = st.number_input("赋分后总分", min_value=0.0, max_value=1000.0)
        class_rank = st.number_input("班级排名", min_value=1, step=1)
        grade_rank = st.number_input("年级排名", min_value=1, step=1)
    with col2:
        chinese = st.number_input("语文", min_value=0.0, max_value=150.0)
        math = st.number_input("数学", min_value=0.0, max_value=150.0)
        english = st.number_input("英语", min_value=0.0, max_value=150.0)
        physics = st.number_input("物理", min_value=0.0, max_value=100.0)
        chem_raw = st.number_input("化学(原始分)", min_value=0.0, max_value=100.0)
        chem_conv = st.number_input("化学(赋分后)", min_value=0.0, max_value=100.0)
        bio_raw = st.number_input("生物(原始分)", min_value=0.0, max_value=100.0)
        bio_conv = st.number_input("生物(赋分后)", min_value=0.0, max_value=100.0)
    submitted = st.form_submit_button("💾 提交成绩")
    if submitted:
        # 计算进退步
        last_class_rank = grades_df['班级排名'].iloc[-1] if len(grades_df) > 0 else class_rank
        last_grade_rank = grades_df['年级排名'].iloc[-1] if len(grades_df) > 0 else grade_rank
        progress_class = last_class_rank - class_rank
        progress_grade = last_grade_rank - grade_rank
        new_record = {
            "考试时间": exam_date,
            "赋分前总分": raw_total,
            "赋分后总分": converted_total,
            "班级排名": class_rank,
            "年级排名": grade_rank,
            "语文": chinese, "数学": math, "英语": english, "物理": physics,
            "化学原始": chem_raw, "化学赋分": chem_conv,
            "生物原始": bio_raw, "生物赋分": bio_conv,
            "进退步(班)": progress_class,
            "进退步(年)": progress_grade
        }
        # 拼接新数据
        grades_df = pd.concat([grades_df, pd.DataFrame([new_record])], ignore_index=True)
        save_data(grades_df)  # 保存到该用户的专属文件
        st.success("成绩录入成功！")
        st.rerun()  # 提交后刷新，防止重复提交
# --- 6. 数据可视化 ---
if len(grades_df) > 0:
    # 转换考试时间为datetime格式
    grades_df['考试时间'] = pd.to_datetime(grades_df['考试时间'])
    # 1. 总分趋势图
    st.subheader("📊 总分变化趋势")
    fig1 = px.line(grades_df, x='考试时间', y=['赋分前总分', '赋分后总分'],
                   title='总分变化趋势', markers=True)
    fig1.update_layout(hovermode="x unified", template="plotly_white")
    st.plotly_chart(fig1, use_container_width=True)
    # 2. 排名变化趋势
    st.subheader("🏆 排名变化趋势")
    fig2 = px.line(grades_df, x='考试时间', y=['班级排名', '年级排名'],
                   title='排名变化趋势', markers=True)
    fig2.update_yaxes(autorange="reversed")  # 排名越低越好，所以反转Y轴
    fig2.update_layout(hovermode="x unified", template="plotly_white")
    st.plotly_chart(fig2, use_container_width=True)
    # 3. 各科目成绩对比（最新一次考试）
    st.subheader("📚 最新考试科目对比")
    latest_exam = grades_df.iloc[-1]
    subjects = ['语文', '数学', '英语', '物理', '化学赋分', '生物赋分']
    scores = [latest_exam[subj] for subj in subjects]
    fig3 = px.bar(x=subjects, y=scores, title='最新考试科目成绩',
                  color=subjects, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig3.update_layout(showlegend=False, template="plotly_white")
    st.plotly_chart(fig3, use_container_width=True)
    # 4. 进退步分析
    st.subheader("📈 进退步分析")
    fig4 = px.bar(grades_df, x='考试时间', y=['进退步(班)', '进退步(年)'],
                  title='进退步分析（正数表示进步）', barmode='group')
    fig4.update_layout(template="plotly_white")
    st.plotly_chart(fig4, use_container_width=True)
    # 5. 科目相关性热力图
    st.subheader("🔗 科目相关性分析")
    subject_columns = ['语文', '数学', '英语', '物理', '化学赋分', '生物赋分']
    corr_matrix = grades_df[subject_columns].corr()
    fig5 = px.imshow(corr_matrix, labels=dict(color="相关系数"),
                     x=subject_columns, y=subject_columns,
                     color_continuous_scale='RdBu_r')
    fig5.update_layout(title='科目相关性热力图')
    st.plotly_chart(fig5, use_container_width=True)
    # --- 7. 历史数据管理 (修复了删除无反应的问题) ---
    st.subheader("🗑️ 历史成绩管理")
    # 1. 准备数据用于显示
    display_df = grades_df.copy()
    display_df.insert(0, "选择", False)  # 插入选择列
    # 2. 显示表格
    edited_df = st.data_editor(
        display_df,
        hide_index=False,
        column_config={
            "选择": st.column_config.CheckboxColumn("选择", help="勾选这里以删除该行")
        },
        use_container_width=True,
        key="grades_editor_v5"  # 强制刷新Key
    )
    # 3. 删除按钮逻辑
    if st.button("✅ 删除选中的记录", type="primary"):
        # 获取勾选的行
        selected_rows = edited_df[edited_df["选择"]]
        if not selected_rows.empty:
            # 核心修复：在原始数据中剔除选中的行
            # 这里直接操作 grades_df (它是从 load_data 读进来的)
            new_df = grades_df.drop(selected_rows.index)
            # 关键步骤：保存回该用户的文件
            save_data(new_df)
            # 强制刷新页面
            # 这样 load_data 会重新读取刚刚保存的文件，数据就更新了
            st.success(f"成功删除 {len(selected_rows)} 条记录！")
            st.rerun()
        else:
            st.warning("请先勾选要删除的行！")
else:
    st.info("当前没有历史记录。")