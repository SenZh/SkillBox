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
    # 仅替换文件名部分，保留路径原始大小写（避免整条路径被 lower() 破坏）
    if python_exe.lower().endswith("python.exe"):
        pythonw_exe = python_exe[:-len("python.exe")] + "pythonw.exe"
    else:
        pythonw_exe = python_exe
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
        try:
            set_autostart(True)
        except Exception as e:
            print(f"[!] 设置开机自启动失败: {e}")
            return 1
        print("[OK] 已成功注册 Windows 开机静默自启动！")
    elif action in ("off", "disable", "false", "0"):
        try:
            set_autostart(False)
        except Exception as e:
            print(f"[!] 取消开机自启动失败: {e}")
            return 1
        print("[OK] 已成功取消 Windows 开机自启动。")
    else:
        st = get_autostart_status()
        print(f"当前开机自启状态: {'开启' if st else '关闭'}")
        print("用法: skillbox autostart on / off")
    return 0

def cmd_resolve(name):
    """定位技能源真身路径与所在 Git 仓库"""
    if not name:
        print("[!] 用法: skillbox resolve <技能名称>")
        return 1
    from app import load_config, resolve_skill
    try:
        cfg = load_config()
        info = resolve_skill(name, cfg)
    except Exception as e:
        print(f"[!] 解析失败: {e}")
        return 1

    print("=" * 60)
    print(f"技能名称 : {info['name']}")
    print(f"源真身路径: {info['true_path']}")
    if info.get("is_builtin"):
        print(f"技能来源 : [ 内置 ] SkillBox 自带技能（随工具版本分发）")
    if info["git_managed"]:
        print(f"Git 管理 : [ YES ] 是")
        print(f"Git 目录 : {info['git_dir']}")
        print(f"相对子路径: {info['sub_dir']}")
        if info.get("git_branch"):
            print(f"目标分支 : {info['git_branch']}")
        elif info.get("is_builtin"):
            print(f"目标分支 : 随 SkillBox 项目仓库管理")
    else:
        print(f"Git 管理 : [ NO ] 未被任何 Git 仓库管理（无法 commit/push）")
        print(f"仓库来源 : {info['source_name']} ({info['source_id']})")
    if info.get("mount_paths"):
        print("挂载位置 :")
        for m in info["mount_paths"]:
            print(f"           - {m}")
    print("=" * 60)
    # 最后单独输出一行纯真身路径，便于 Agent 直接抓取
    print(info["true_path"])
    return 0

def cmd_commit(name, message, push=True):
    """提交并推送技能源真身所在 Git 仓库的变更（白名单提交，仅限该技能目录）"""
    if not name:
        print("[!] 用法: skillbox commit <技能名称> -m \"提交说明\"")
        return 1
    from app import load_config, resolve_skill, git_cmd
    try:
        cfg = load_config()
        info = resolve_skill(name, cfg)
    except Exception as e:
        print(f"[!] 解析失败: {e}")
        return 1

    if not info["git_managed"]:
        print(f"[!] 技能 [{name}] 未被 Git 管理，跳过提交。")
        return 1

    repo_dir = info["git_dir"]
    branch = info["git_branch"]
    pathspec = info["sub_dir"]
    if not pathspec:
        print(f"[!] 技能 [{name}] 相对路径解析失败，拒绝提交（避免误伤其他文件）。")
        return 1

    try:
        git_cmd(["add", "--", pathspec], cwd=repo_dir)
        status = git_cmd(["status", "--porcelain", "--", pathspec], cwd=repo_dir)
        if not status.strip():
            print(f"[*] 技能 [{name}] 目录无变更，无需提交。")
            return 0
        git_cmd(["commit", "-m", message or f"chore(skill): update {name}"], cwd=repo_dir)
        committed_hash = git_cmd(["rev-parse", "--short", "HEAD"], cwd=repo_dir)
        print(f"[OK] 已提交 {committed_hash} (分支: {branch})")
        if push:
            git_cmd(["push", "origin", branch], cwd=repo_dir)
            print(f"[OK] 已推送到 origin/{branch}")
        return 0
    except Exception as e:
        print(f"[!] 提交失败: {e}")
        return 1

def cmd_log(lines_count=50):
    log_file = BASE_DIR / "skillbox.log"
    if not log_file.exists():
        print("[*] 暂无运行日志文件 (skillbox.log)。启动服务后将自动记录日志。")
        return 0
    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        print(f"=== SkillBox 最近运行日志 ({min(len(content), lines_count)} 行) ===")
        for line in content[-lines_count:]:
            print(line)
        print(f"=== 日志文件路径: {log_file} ===")
        return 0
    except Exception as e:
        print(f"[!] 读取日志失败: {e}")
        return 1

def cmd_test():
    import run_tests
    return run_tests.run_all_tests()

def _get_user_path():
    """读取当前用户 PATH（非进程 PATH），保持原始字符串"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "Path")
            return val or ""
    except FileNotFoundError:
        return ""
    except Exception as e:
        raise RuntimeError(f"读取用户 PATH 失败: {e}")

def _set_user_path(new_path):
    """写入当前用户 PATH（HKCU\\Environment），无需管理员权限，并广播环境变更"""
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
    except OSError as e:
        raise RuntimeError(f"写入用户 PATH 失败: {e}")
    # 广播 WM_SETTINGCHANGE，让新开的终端尽快感知（部分终端需重开）
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None
        )
    except Exception:
        pass

def cmd_install():
    """将 SkillBox 命令注册到当前用户 PATH，使全局任意终端可直接调用 skillbox"""
    if sys.platform != "win32":
        print("[!] 当前仅支持 Windows 一键安装命令。macOS/Linux 请手动将 skillbox 脚本加入 PATH。")
        return 1

    bin_dir = str(BASE_DIR)
    launcher = BASE_DIR / "skillbox.bat"
    if not launcher.exists():
        print(f"[!] 未找到启动器 {launcher}，无法安装。")
        return 1

    try:
        cur = _get_user_path()
        parts = [p for p in cur.split(";") if p.strip()]
        if any(p.rstrip("\\").lower() == bin_dir.rstrip("\\").lower() for p in parts):
            print(f"[*] 已安装：{bin_dir} 已在用户 PATH 中，无需重复安装。")
            print("[*] 若当前终端仍无法识别 skillbox，请重开一个终端窗口。")
            return 0
        parts.append(bin_dir)
        _set_user_path(";".join(parts))
        print(f"[OK] 已将 {bin_dir} 写入当前用户 PATH。")
        print("[*] 请【重开一个终端窗口】后执行 `skillbox help` 验证。")
        return 0
    except Exception as e:
        print(f"[!] 安装失败: {e}")
        return 1

def cmd_uninstall():
    """从当前用户 PATH 中移除 SkillBox 命令"""
    if sys.platform != "win32":
        print("[!] 当前仅支持 Windows。")
        return 1
    bin_dir = str(BASE_DIR)
    try:
        cur = _get_user_path()
        parts = [p for p in cur.split(";") if p.strip()]
        new_parts = [p for p in parts if p.rstrip("\\").lower() != bin_dir.rstrip("\\").lower()]
        if len(new_parts) == len(parts):
            print(f"[*] 未安装：{bin_dir} 不在用户 PATH 中。")
            return 0
        _set_user_path(";".join(new_parts))
        print(f"[OK] 已从当前用户 PATH 中移除 {bin_dir}。")
        print("[*] 请【重开一个终端窗口】使变更生效。")
        return 0
    except Exception as e:
        print(f"[!] 卸载失败: {e}")
        return 1

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
  skillbox resolve <name>      定位技能源真身路径及其 Git 目录（未被 Git 管理会明确提示）
  skillbox commit <name> [-m s] 提交并推送该技能源仓库变更（仅提交该技能目录，白名单安全提交）
  skillbox autostart [on/off]  设置或取消 Windows 开机静默自启动
  skillbox run                 前台直接运行服务 (用于排错调试查看日志)
  skillbox log [N]             查看后台最近 N 行运行日志 (默认 50 行)
  skillbox test                运行全量自动化单元测试套件
  skillbox install             将 skillbox 命令注册到用户 PATH（安装后全局可用，需重开终端）
  skillbox uninstall           从用户 PATH 中移除 skillbox 命令
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
    elif cmd in ("log", "logs"):
        count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
        return cmd_log(count)
    elif cmd in ("update", "pull", "sync"):
        return cmd_update()
    elif cmd in ("resolve", "where", "locate"):
        return cmd_resolve(args[1] if len(args) > 1 else "")
    elif cmd == "commit":
        sub_args = args[1:]
        msg = ""
        no_push = False
        positional = []
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-m", "--message"):
                msg = sub_args[i + 1] if i + 1 < len(sub_args) else ""
                i += 2
                continue
            if a in ("--no-push", "--local"):
                no_push = True
            else:
                positional.append(a)
            i += 1
        return cmd_commit(positional[0] if positional else "", msg, push=not no_push)
    elif cmd in ("run", "dev"):
        return cmd_run()
    elif cmd in ("autostart", "boot"):
        sub = args[1] if len(args) > 1 else "status"
        return cmd_autostart(sub)
    elif cmd in ("test", "tests"):
        return cmd_test()
    elif cmd in ("install", "setup"):
        return cmd_install()
    elif cmd in ("uninstall", "remove"):
        return cmd_uninstall()
    elif cmd in ("help", "-h", "--help"):
        print_help()
        return 0
    else:
        print(f"[!] 未知命令: {cmd}")
        print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
