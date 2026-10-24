"""学生端与教师端共用的工具：认证、配置读写、日期与等级映射。"""
import hashlib
import hmac
import json
import os

import pandas as pd

CONFIG_FILE_PATH = os.path.join("user_data", "users_config.json")
PBKDF2_ITERATIONS = 260_000


def get_password_hash(password):
    """PBKDF2-SHA256 + 随机盐，格式：pbkdf2_sha256$迭代次数$盐$哈希"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(stored_hash, provided_password):
    """兼容旧的无盐 SHA256 哈希；返回 (是否通过, 是否为旧格式)"""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iters, salt_hex, dk_hex = stored_hash.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256", provided_password.encode(), bytes.fromhex(salt_hex), int(iters))
            return hmac.compare_digest(dk.hex(), dk_hex), False
        except (ValueError, TypeError):
            return False, False
    legacy_ok = hmac.compare_digest(
        stored_hash, hashlib.sha256(provided_password.encode()).hexdigest())
    return legacy_ok, legacy_ok  # 旧格式且验证通过 → 调用方应升级哈希


def upgrade_password_hash(user_key, new_password):
    """将旧格式哈希升级为 PBKDF2"""
    config = load_config()
    if user_key in config["users"]:
        config["users"][user_key]["password_hash"] = get_password_hash(new_password)
        save_config(config)


def load_config():
    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def parse_dates(series):
    """宽容解析日期：兼容 ISO（2026-10-24）与斜杠（2026/10/24）格式"""
    dt = pd.to_datetime(series, errors="coerce")
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], format="%Y/%m/%d", errors="coerce")
    return dt


GRADE_BANDS = [(86, 100, "A"), (71, 85, "B"), (56, 70, "C"), (41, 55, "D"), (30, 40, "E")]
GRADE_ICONS = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "E": "🔴"}


def score_to_grade(score):
    """3+1+2 赋分等级映射 (A~E)，返回空串表示无法映射"""
    if pd.isna(score):
        return ""
    for lo, hi, g in GRADE_BANDS:
        if lo <= score <= hi:
            return g
    return ""
