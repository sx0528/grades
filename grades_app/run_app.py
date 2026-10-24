"""PyInstaller 打包入口：在进程内启动 Streamlit 并自动打开浏览器。

开发时仍用 `streamlit run main.py`；本脚本仅供打包使用。
"""
import os
import sys
import threading
import webbrowser

APP_PORT = 8501
APP_URL = f"http://localhost:{APP_PORT}"


def open_browser():
    try:
        webbrowser.open(APP_URL)
    except Exception:
        pass


def main():
    if getattr(sys, "frozen", False):
        # 打包后：main.py 解包在 _MEIPASS；数据目录定位到 exe 旁边
        base_dir = sys._MEIPASS
        os.chdir(os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(base_dir)
    app_path = os.path.join(base_dir, "main.py")

    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_PORT"] = str(APP_PORT)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port", str(APP_PORT),
        "--server.headless", "true",
        "--global.developmentMode", "false",
        "--browser.gatherUsageStats", "false",
    ]
    threading.Timer(2.5, open_browser).start()
    stcli.main()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
