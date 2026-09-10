import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".skillbox.pid"
DEFAULT_PORT = 7860

def check_server_alive(port=DEFAULT_PORT):
    """通过 HTTP 请求探测服务是否存活"""
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.8)
        return resp.status == 200
    except Exception:
        return False

def clean_stale_pid():
    """清理僵尸 PID 文件"""
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass

def main():
    port = DEFAULT_PORT
    is_running = False

    # 1. 检查是否存在 PID 文件并真实探活
    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            if ":" in content:
                _, p_str = content.split(":")
                port = int(p_str)
            if check_server_alive(port):
                is_running = True
            else:
                clean_stale_pid()
        except Exception:
            clean_stale_pid()

    # 兜底：如果端口真实通了，也视为已运行
    if not is_running and check_server_alive(DEFAULT_PORT):
        is_running = True
        port = DEFAULT_PORT

    url = f"http://127.0.0.1:{port}"

    if is_running:
        print(f"[*] SkillBox 已在后台运行，正在为你打开控制台: {url}")
        webbrowser.open(url)
        time.sleep(1)
        return 0

    # 2. 启动后台静默进程
    print(f"[*] 正在启动 SkillBox 后台服务...")
    python_exe = sys.executable
    pythonw_exe = python_exe.lower().replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe

    app_script = str(BASE_DIR / "app.py")

    # Windows 下使用 DETACHED_PROCESS 彻底脱离控制台
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = 0x00000008 | 0x00000200 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen(
            [pythonw_exe, app_script],
            cwd=str(BASE_DIR),
            creationflags=creation_flags
        )
    except Exception as e:
        print(f"[!] 后台启动失败: {e}")
        print("[*] 正在尝试前台启动...")
        subprocess.Popen([python_exe, app_script], cwd=str(BASE_DIR))

    # 3. 循环探活确认启动成功
    started = False
    for _ in range(20):
        time.sleep(0.2)
        if check_server_alive(port):
            started = True
            break

    if started:
        print(f"[OK] SkillBox 服务已成功在后台启动: {url}")
        webbrowser.open(url)
        time.sleep(1)
        return 0
    else:
        print(f"[!] 启动未能在预期时间内响应，请运行 python app.py 查看终端输出")
        return 1

if __name__ == "__main__":
    sys.exit(main())
