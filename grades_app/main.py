import streamlit as st
import pandas as pd
import os
import hashlib
import json
from datetime import datetime
import plotly.express as px
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
def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()
def verify_password(stored_hash, provided_password):
    return stored_hash == get_password_hash(provided_password)
def load_config():
    with open(CONFIG_FILE_PATH, 'r') as f:
        return json.load(f)
def save_config(config):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)
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
    exam_mode = st.sidebar.selectbox("📚 选择高考模式", ["", "3+3", "3+1+2"], index=0)
    if not user_name or not exam_mode:
        st.info("请在左侧边栏填写姓名并选择高考模式。")
        st.stop()
    user_key = f"{user_name}_{exam_mode}"
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
            if verify_password(user_record["password_hash"], pwd):
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
        # 进退步计算 (简单示例)
        if len(df) > 1:
            df["班级进步"] = df["班级排名"].shift(1) - df["班级排名"]
            df["年级进步"] = df["年级排名"].shift(1) - df["年级排名"]
        # 总分趋势
        fig_total = px.line(df, x="考试时间", y=["赋分前总分", "赋分后总分"], markers=True, title="总分趋势")
        st.plotly_chart(fig_total, use_container_width=True)
        # 排名趋势 (越低越好)
        fig_rank = px.line(df, x="考试时间", y=["班级排名", "年级排名"], markers=True, title="排名趋势 (越低越好)")
        fig_rank.update_yaxes(autorange="reversed")  # 排名倒序
        st.plotly_chart(fig_rank, use_container_width=True)
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
# === 6. 程序入口 ===
if __name__ == "__main__":
    authentication()
    subject_setup()
    main_app()
