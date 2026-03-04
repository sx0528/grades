import streamlit as st
import pandas as pd
import os
import hashlib  # 用于密码加密
import json
from datetime import datetime
import plotly.express as px

# === 1. 配置与初始化 ===
USER_DATA_DIR = "user_data"
CONFIG_FILE_PATH = os.path.join(USER_DATA_DIR, "users_config.json")

# 创建数据目录
if not os.path.exists(USER_DATA_DIR):
    os.makedirs(USER_DATA_DIR)

# 初始化配置文件（如果不存在）
if not os.path.exists(CONFIG_FILE_PATH):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump({"users": {}}, f)

st.set_page_config(page_title="🔐 高考成绩追踪器", layout="wide")
st.title("🎯 个人高考成绩追踪系统")

# === 2. 辅助函数：密码哈希 ===
def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    return stored_hash == get_password_hash(provided_password)

# === 3. 辅助函数：读写全局配置 ===
def load_config():
    with open(CONFIG_FILE_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)

# === 4. 用户身份与隐私管理 (功能 3 & 4) ===
def authentication():
    st.sidebar.header("🔐 身份验证与设置")
    
    # 1. 基础信息输入
    user_name = st.sidebar.text_input("👤 请输入姓名", value=st.session_state.get('temp_name', ''))
    exam_mode = st.sidebar.selectbox("📚 选择高考模式", ["", "3+3", "3+1+2"], index=0)
    
    if not user_name or not exam_mode:
        st.info("请在左侧边栏选择姓名和高考模式。")
        st.stop()
    
    # 2. 生成唯一用户Key (防止重名：功能3)
    user_key = f"{user_name}_{exam_mode}"
    st.session_state['user_key'] = user_key
    st.session_state['temp_name'] = user_name
    st.session_state['exam_mode'] = exam_mode

    config = load_config()
    user_data = config["users"].get(user_key)

    # 3. 新用户注册逻辑
    if user_data is None:
        st.sidebar.info(f"👋 欢迎新用户 {user_name}! 请设置密码。")
        pwd = st.sidebar.text_input("设置密码", type="password", key="reg_pwd")
        pwd2 = st.sidebar.text_input("确认密码", type="password", key="reg_pwd2")
        
        if st.sidebar.button("注册账户"):
            if pwd and pwd == pwd2 and len(pwd) >= 4:
                # 初始化用户配置
                config["users"][user_key] = {
                    "password_hash": get_password_hash(pwd),
                    "subject_config": None, # 等待选科
                    "created_at": datetime.now().isoformat()
                }
                save_config(config)
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.sidebar.error("密码为空、不一致或太短（至少4位）")
                st.stop()

    # 4. 老用户登录逻辑
    else:
        pwd = st.sidebar.text_input("🔑 请输入密码", type="password", key="login_pwd")
        if st.sidebar.button("登录"):
            if verify_password(user_data["password_hash"], pwd):
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.sidebar.error("密码错误")
                st.stop()

        # 如果已登录，检查是否需要选科
        if user_data["subject_config"] is None:
            st.session_state['authenticated'] = True # 强制登录以进行选科

    # 5. 检查登录状态
    if "authenticated" not in st.session_state or not st.session_state.authenticated:
        st.stop()

# === 5. 选科配置模块 (功能 1 & 2) ===
def subject_setup():
    user_key = st.session_state['user_key']
    config = load_config()
    user_data = config["users"][user_key]
    
    # 如果已经有配置，直接返回
    if user_data["subject_config"] is not None:
        return user_data["subject_config"]
    
    # 否则进入选科界面
    st.subheader("⚙️ 科目设置 (仅需设置一次)")
    mode = st.session_state['exam_mode']
    
    if mode == "3+3":
        st.info("请从以下科目中选择 3 门作为你的选考科目：")
        all_subs = ["物理", "化学", "生物", "政治", "历史", "地理"]
        selected = st.multiselect("选择你的科目", all_subs, max_selections=3, key="select_33")
        
        if len(selected) == 3 and st.button("💾 保存我的选科"):
            config["users"][user_key]["subject_config"] = {
                "mode": "3+3",
                "selected_subjects": selected
            }
            save_config(config)
            st.success("选科设置成功！")
            st.rerun()
            
    elif mode == "3+1+2":
        col1, col2 = st.columns(2)
        with col1:
            st.info("首选科目 (1门，无赋分)：")
            primary = st.radio("选择", ["物理", "历史"], key="radio_ph")
        with col2:
            st.info("再选科目 (2门，有赋分)：")
            optional_pool = ["化学", "生物", "政治", "地理"]
            secondary = st.multiselect("选择", optional_pool, max_selections=2, key="select_2")
        
        if len(secondary) == 2 and st.button("💾 保存我的选科"):
            config["users"][user_key]["subject_config"] = {
                "mode": "3+1+2",
                "primary": primary,
                "secondary": secondary
            }
            save_config(config)
            st.success("选科设置成功！")
            st.rerun()
    
    st.stop() # 没选完不继续执行

# === 6. 数据路径管理 ===
def get_user_data_path():
    # 使用 user_key 保证文件名唯一
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

# === 7. 动态表单与主逻辑 ===
def main_app():
    user_key = st.session_state['user_key']
    user_name = st.session_state['temp_name']
    config = load_config()
    subject_config = config["users"][user_key]["subject_config"]
    
    st.sidebar.success(f"你好，{user_name} 👋")
    
    # --- 7.1 动态生成录入表单 (功能 1) ---
    with st.form("dynamic_grade_form"):
        st.subheader(f"📝 录入新成绩")
        
        col1, col2 = st.columns(2)
        with col1:
            exam_date = st.date_input("考试时间", datetime.now())
            raw_total = st.number_input("赋分前总分", 0.0, 1000.0, step=0.5)
            converted_total = st.number_input("赋分后总分", 0.0, 1000.0, step=0.5)
            class_rank = st.number_input("班级排名", 1, 1000, step=1)
            grade_rank = st.number_input("年级排名", 1, 10000, step=1)
        
        with col2:
            st.markdown("### 主科成绩")
            chinese = st.number_input("语文", 0.0, 150.0, step=0.5)
            math = st.number_input("数学", 0.0, 150.0, step=0.5)
            english = st.number_input("英语", 0.0, 150.0, step=0.5)
            
            # --- 动态渲染选科输入框 ---
            st.markdown("### 选科成绩")
            
            # 3+3 模式逻辑
            if subject_config["mode"] == "3+3":
                for sub in subject_config["selected_subjects"]:
                    raw = st.number_input(f"{sub} (原始分)", 0.0, 100.0, step=0.5, key=f"raw_{sub}")
                    conv = st.number_input(f"{sub} (赋分后)", 0.0, 100.0, step=0.5, key=f"conv_{sub}")
                    # 存储逻辑需要在提交时处理，这里只负责显示
                
            # 3+1+2 模式逻辑
            elif subject_config["mode"] == "3+1+2":
                # 首选科目 (无赋分)
                ph_sub = subject_config["primary"]
                ph_score = st.number_input(f"{ph_sub} (首选)", 0.0, 100.0, step=0.5, key=f"ph_{ph_sub}")
                
                # 再选科目 (有赋分)
                for sub in subject_config["secondary"]:
                    raw = st.number_input(f"{sub} (原始分)", 0.0, 100.0, step=0.5, key=f"raw_{sub}")
                    conv = st.number_input(f"{sub} (赋分后)", 0.0, 100.0, step=0.5, key=f"conv_{sub}")
        
        submitted = st.form_submit_button("💾 提交成绩")
        
        if submitted:
            # --- 数据处理逻辑 (拼接所有数据) ---
            new_record = {
                "考试时间": exam_date,
                "语文": chinese,
                "数学": math,
                "英语": english,
                "赋分前总分": raw_total,
                "赋分后总分": converted_total,
                "班级排名": class_rank,
                "年级排名": grade_rank
            }
            
            # 动态添加选科成绩到记录中
            if subject_config["mode"] == "3+3":
                for sub in subject_config["selected_subjects"]:
                    # 这里Key的命名需要符合你后续的读取逻辑
                    new_record[f"{sub}_原始"] = st.session_state[f"raw_{sub}"]
                    new_record[f"{sub}_赋分"] = st.session_state[f"conv_{sub}"]
                    
            elif subject_config["mode"] == "3+1+2":
                # 添加首选科目
                new_record[subject_config["primary"]] = st.session_state[f"ph_{subject_config['primary']}"]
                # 添加再选科目
                for sub in subject_config["secondary"]:
                    new_record[f"{sub}_原始"] = st.session_state[f"raw_{sub}"]
                    new_record[f"{sub}_赋分"] = st.session_state[f"conv_{sub}"]
            
            # --- 保存逻辑 ---
            df = load_user_data()
            # 计算进退步 (这里需要根据实际列名调整)
            # ... (此处保留你原有的进退步计算逻辑，需根据动态列名做适配) ...
            
            new_df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
            save_user_data(new_df)
            st.success("成绩录入成功！")
            st.rerun()

    # === 8. 数据可视化 (示例，需根据动态列调整) ===
    df = load_user_data()
    if not df.empty:
        st.divider()
        st.subheader("📊 数据分析")
        
        # 这里需要动态获取科目列来画图
        # 由于逻辑复杂，建议先打印列名调试
        st.write("已录入数据预览：", df.head())
        
        # --- 历史记录管理 (修复版) ---
        st.subheader("🗑️ 历史记录管理")
        data_to_edit = df.copy()
        data_to_edit.insert(0, "Delete", False)
        
        edited = st.data_editor(
            data_to_edit,
            column_config={"Delete": st.column_config.CheckboxColumn("删除?")},
            hide_index=False
        )
        
        if st.button("清理选中行"):
            df_filtered = df[~edited["Delete"]]
            save_user_data(df_filtered)
            st.success("清理完成！")
            st.rerun()

    else:
        st.info("暂无历史数据，请先录入成绩。")

# === 9. 程序入口 ===
if __name__ == "__main__":
    # 运行验证 -> 选科 -> 主程序
    authentication()
    subject_config = subject_setup() # 如果没有选科会在这里阻塞
    main_app()
