# -*- coding: utf-8 -*-
"""端到端功能测试：学生端 + 教师端（streamlit.testing AppTest，隔离临时目录）。"""
import json
import os
import shutil
import sys
import tempfile

import pandas as pd

# --- 隔离环境：临时 cwd，避免污染真实 user_data ---
TMP = tempfile.mkdtemp(prefix="gt_test_")
os.chdir(TMP)
sys.path.insert(0, r"D:\grades\grades_app")
os.makedirs("user_data")
with open("user_data/users_config.json", "w", encoding="utf-8") as f:
    json.dump({"users": {}}, f)

from streamlit.testing.v1 import AppTest  # noqa: E402

MAIN = r"D:\grades\grades_app\main.py"
PASS = []


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    PASS.append(msg)


# ================= 教师端流程 =================
at = AppTest.from_file(MAIN, default_timeout=120)
at.run()
check(not at.exception, "启动无异常")
check(any("请输入姓名" in t.label for t in at.sidebar.text_input), "初始显示姓名输入")

at.sidebar.radio[0].set_value("教师")
at.sidebar.text_input[0].set_value("王老师")
at.run()
check(not at.exception, "教师新用户进入注册页")

at.sidebar.text_input(key="reg_pwd").set_value("abcd1234")
at.sidebar.text_input(key="reg_pwd2").set_value("abcd1234")
at.sidebar.button[0].click()  # 注册账户
at.run()
check(not at.exception, "教师注册无异常（修复后不再 NameError）")
check(at.session_state["authenticated"] is True, "教师注册后自动登录")
check(at.session_state["user_key"] == "王老师_教师", "教师 user_key 正确")
check(any("教师工作台" in h.value for h in at.header), "教师工作台渲染")

# 保存班级设置
setup_ti = [t for t in at.text_input if t.label == "班级名称"]
check(bool(setup_ti), "班级设置表单渲染")
setup_ti[0].set_value("高三(2)班")
at.button[0].click()  # 保存班级设置（表单内 submit 是 button 元素）
at.run()
check(not at.exception, "班级设置保存成功")

# 预置两名学生、两个场次的成绩（含缺考 NaN 场景）
grades = pd.DataFrame([
    {"姓名": "张三", "考试时间": "2026-09-01", "考试类型": "月考", "语文": 110, "数学": 120, "英语": 105, "总分": 335, "班级排名": 2},
    {"姓名": "李四", "考试时间": "2026-09-01", "考试类型": "月考", "语文": 95, "数学": 100, "英语": 98, "总分": 293, "班级排名": 1},
    {"姓名": "张三", "考试时间": "2026-10-01", "考试类型": "期中", "语文": 118, "数学": None, "英语": 112, "总分": 230},
    {"姓名": "李四", "考试时间": "2026-10-01", "考试类型": "期中", "语文": 102, "数学": 115, "英语": 104, "总分": 321, "班级排名": 1},
])
os.makedirs("teacher_data/王老师_教师", exist_ok=True)
grades.to_csv("teacher_data/王老师_教师/grades.csv", index=False, encoding="utf-8")
at.run()
check(not at.exception, "载入班级数据无异常（含缺考记录）")

check(any("总分排名" in m.value for m in at.markdown), "班级分析：总分排名渲染")
check(len(at.dataframe) >= 2, "班级分析：排名表与统计表渲染")
check(any("进退步榜" in m.value for m in at.markdown), "班级分析：进退步榜渲染（两个场次）")

# 学生报告
sel = [s for s in at.selectbox if s.label == "选择学生"]
check(bool(sel), "学生报告：学生选择框渲染")
sel[0].set_value("张三")
at.run()
check(not at.exception, "学生报告（张三）无异常")
check(any("与班级对比" in m.value for m in at.markdown), "学生报告：班级对比渲染")
check(len(at.get("plotly_chart")) >= 1, "学生报告：趋势/雷达图渲染")

# ================= 学生端流程 =================
st2 = AppTest.from_file(MAIN, default_timeout=120)
st2.run()
st2.sidebar.radio[0].set_value("学生")
st2.sidebar.text_input[0].set_value("李明")
st2.sidebar.selectbox[0].set_value("3+1+2")
st2.run()
check(not at.exception, "学生新用户进入注册页")

st2.sidebar.text_input(key="reg_pwd").set_value("abcd1234")
st2.sidebar.text_input(key="reg_pwd2").set_value("abcd1234")
st2.sidebar.button[0].click()
st2.run()
check(st2.session_state["user_key"] == "李明_3+1+2", "学生注册成功")

# 选科：首选物理 + 化学/生物
ms = [m for m in st2.multiselect if m.label == "选择"]
check(bool(ms), "选科页渲染")
ms[0].set_value(["化学", "生物"])
st2.run()
save_btn = [b for b in st2.button if "保存选科" in (b.label or "")]
check(bool(save_btn), "保存选科按钮出现")
save_btn[0].click()
st2.run()
check(not st2.exception, "选科保存并进入主界面")
check(any("录入成绩" in s.value for s in st2.subheader), "录入表单渲染")

# 表单录入成绩
ni = {n.label: n for n in st2.number_input}
for label, val in [("赋分前总分", 600), ("赋分后总分", 615), ("班级排名", 10),
                   ("年级排名", 200), ("语文", 110), ("数学", 120), ("英语", 115),
                   ("物理 (首选)", 80), ("化学 (原始分)", 75), ("化学 (赋分后)", 82),
                   ("生物 (原始分)", 70), ("生物 (赋分后)", 78)]:
    ni[label].set_value(float(val))
submit = [b for b in st2.button if "提交成绩" in (b.label or "")]
check(bool(submit), "提交按钮渲染")
submit[0].click()
st2.run()
check(not st2.exception, "成绩录入成功")

# 验证数据落盘
saved = pd.read_csv("user_data/李明_3+1+2.csv")
check(len(saved) == 1 and abs(saved["赋分后总分"].iloc[0] - 615) < 1e-6, "成绩 CSV 落盘正确")

# 预置第二条记录 → 验证环比卡片与雷达图
second = saved.iloc[0].copy()
second["考试时间"] = "2026-11-01"
second["赋分后总分"] = 630
second["年级排名"] = 180
pd.concat([saved, pd.DataFrame([second])], ignore_index=True).to_csv(
    "user_data/李明_3+1+2.csv", index=False, encoding="utf-8")
st2.run()
check(not st2.exception, "两次成绩分析渲染无异常")
check(any("与上次考试对比" in m.value for m in st2.markdown), "环比卡片渲染")
check(any("学科雷达图" in m.value for m in st2.markdown), "雷达图渲染")
check(any("赋分等级" in m.value for m in st2.markdown), "赋分等级渲染")
check(any(m.delta == "+15" for m in st2.metric), "环比数值正确（总分 +15）")

# 老用户再次登录
st3 = AppTest.from_file(MAIN, default_timeout=120)
st3.run()
st3.sidebar.radio[0].set_value("学生")
st3.sidebar.text_input[0].set_value("李明")
st3.sidebar.selectbox[0].set_value("3+1+2")
st3.run()
st3.sidebar.text_input(key="login_pwd").set_value("abcd1234")
st3.sidebar.button[0].click()
st3.run()
check(st3.session_state["authenticated"] is True, "老用户登录成功")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n=== 全部 {len(PASS)} 项测试通过 ===")
for p in PASS:
    print(" ✓", p)
