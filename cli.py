#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 统一命令行管理工具 (Unified CLI)
支持服务的后台启停、重启、状态查看、开机自启、全量仓库更新与测试套件执行。
"""

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

def check_alive(port=DEFAULT_PORT):
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.8)
        return resp.status == 200
    except Exception:
        return False

def get_running_info():
    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            if ":" in content:
                pid, port = content.split(":")
                if check_alive(int(port)):
                    return int(pid), int(port)
        except Exception:
            pass
    if check_alive(DEFAULT_PORT):
        return None, DEFAULT_PORT
    return None, None

def clean_pid():
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass

def cmd_start():
    pid, port = get_running_info()
    url = f"http://127.0.0.1:{port or DEFAULT_PORT}"

    if port:
        print(f"[*] SkillBox 服务已在后台运行中 (PID: {pid or '未知'}, 端口: {port})")
        print(f"[*] 正在打开控制台: {url}")
        webbrowser.open(url)
        return 0

    clean_pid()
    print("[*] 正在后台启动 SkillBox 守护服务...")
    python_exe = sys.executable
    pythonw_exe = python_exe.lower().replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe

    app_script = str(BASE_DIR / "app.py")
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
        print(f"[!] 后台启动异常: {e}，正在尝试使用普通进程启动...")
        subprocess.Popen([python_exe, app_script], cwd=str(BASE_DIR))

    # 循环探活
    started = False
    actual_port = DEFAULT_PORT
    for _ in range(20):
        time.sleep(0.2)
        if check_alive(DEFAULT_PORT):
            started = True
            break

    if started:
        print(f"[OK] SkillBox 后台服务已成功就绪: {url}")
        webbrowser.open(url)
        return 0
    else:
        print("[!] 启动未在预期时间内响应，请运行 `skillbox run` 查看前台实时报错日志。")
        return 1

def cmd_stop():
    print("[*] 正在停止 SkillBox 后台服务...")
    pid, port = get_running_info()

    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            if ":" in content:
                p_val, _ = content.split(":")
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", p_val], capture_output=True)
                else:
                    import signal
                    os.kill(int(p_val), signal.SIGTERM)
        except Exception:
            pass
        clean_pid()

    # 兜底：释放端口对应进程
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                'netstat -ano | findstr ":7860" | findstr "LISTENING"',
                shell=True, capture_output=True, text=True
            )
            for line in res.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    target_pid = parts[-1]
                    subprocess.run(["taskkill", "/F", "/PID", target_pid], capture_output=True)
        except Exception:
            pass

    time.sleep(0.5)
    if not check_alive(DEFAULT_PORT):
        print("[OK] SkillBox 服务已成功停止，端口已释放。")
        return 0
    else:
        print("[!] 端口仍被占用，请手动检查任务管理器。")
        return 1

def cmd_restart():
    print("[*] 正在重启 SkillBox 服务...")
    cmd_stop()
    time.sleep(1)
    return cmd_start()

def cmd_status():
    print("=" * 45)
    print("        SkillBox 运行状态报告")
    print("=" * 45)
    pid, port = get_running_info()
    from app import get_autostart_status, __version__
    print(f"当前版本: v{__version__}")
    if port:
        print(f"运行状态: [ RUNNING ] 正在运行")
        print(f"后台 PID: {pid or '已运行 (守护模式)'}")
        print(f"服务端口: {port} (http://127.0.0.1:{port})")
    else:
        print(f"运行状态: [ STOPPED ] 未运行")
        print(f"服务端口: 7860 (空闲)")

    autostart = get_autostart_status()
    print(f"开机自启: {'[ ON ] 已注册开启' if autostart else '[ OFF ] 未开启'}")
    print("=" * 45)
    return 0

def cmd_open():
    pid, port = get_running_info()
    url = f"http://127.0.0.1:{port or DEFAULT_PORT}"
    print(f"[*] 正在打开控制台: {url}")
    webbrowser.open(url)
    return 0

def cmd_run():
    print("[*] 正在前台直接运行 SkillBox 服务 (用于调试查看日志，按 Ctrl+C 退出)...")
    from app import main as app_main
    app_main()

def cmd_update():
    print("[*] 正在触发所有 Git 仓库源增量拉取更新...")
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:7860/api/pull_all", data=b"{}", headers={"Content-Type": "application/json"}),
            timeout=120
        )
        import json
        res = json.loads(resp.read().decode("utf-8"))
        if res.get("ok"):
            print("[OK] 所有 Git 仓库已更新完毕，挂载的软链接实时生效！")
            return 0
        else:
            print(f"[!] 部分仓库更新失败: {res.get('error')}")
            return 1
    except Exception as e:
        print(f"[!] 无法连通服务更新，正在执行直接更新...")
        from app import load_config, pull_single_source
        cfg = load_config()
        for s in cfg.get("sources", []):
            try:
                print(f"  - 正在更新 [{s.get('name')}]...")
                pull_single_source(s)
            except Exception as ex:
                print(f"    [!] 失败: {ex}")
        print("[OK] 本地 Git 缓存已全部拉取完毕！")
        return 0

def cmd_autostart(action):
    from app import set_autostart, get_autostart_status
    if action in ("on", "enable", "true", "1"):
        set_autostart(True)
        print("[OK] 已成功注册 Windows 开机静默自启动！")
    elif action in ("off", "disable", "false", "0"):
        set_autostart(False)
        print("[OK] 已成功取消 Windows 开机自启动。")
    else:
        st = get_autostart_status()
        print(f"当前开机自启状态: {'开启' if st else '关闭'}")
        print("用法: skillbox autostart on / off")
    return 0

def cmd_test():
    import run_tests
    return run_tests.run_all_tests()

def print_help():
    print("""
SkillBox 统一命令行管理工具 (v0.1)

用法:
  skillbox                     直接启动后台服务并打开控制台 (双击同效)
  skillbox start | up          后台静默启动服务并自动弹开浏览器
  skillbox stop  | down        安全停止后台服务并释放端口
  skillbox restart             重启后台服务
  skillbox status              查看当前服务运行状态、PID、端口与开机自启
  skillbox open                在浏览器中打开控制台 (http://127.0.0.1:7860)
  skillbox update              触发所有 Git 仓库源增量拉取更新
  skillbox autostart [on/off]  设置或取消 Windows 开机静默自启动
  skillbox run                 前台直接运行服务 (用于排错调试查看日志)
  skillbox test                运行全量自动化单元测试套件
  skillbox help                显示此帮助说明
""")

def main():
    args = sys.argv[1:]
    if not args:
        # 无参数时：默认等同于 start（双击即可启动）
        return cmd_start()

    cmd = args[0].lower()
    if cmd in ("start", "up"):
        return cmd_start()
    elif cmd in ("stop", "down"):
        return cmd_stop()
    elif cmd in ("restart", "reboot"):
        return cmd_restart()
    elif cmd in ("status", "ps"):
        return cmd_status()
    elif cmd in ("open", "ui", "web"):
        return cmd_open()
    elif cmd in ("update", "pull", "sync"):
        return cmd_update()
    elif cmd in ("run", "dev"):
        return cmd_run()
    elif cmd in ("autostart", "boot"):
        sub = args[1] if len(args) > 1 else "status"
        return cmd_autostart(sub)
    elif cmd in ("test", "tests"):
        return cmd_test()
    elif cmd in ("help", "-h", "--help"):
        print_help()
        return 0
    else:
        print(f"[!] 未知命令: {cmd}")
        print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
