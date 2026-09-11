#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox 桌面托盘应用 (Desktop Tray App)

将 SkillBox 包装成一个常驻系统托盘的桌面客户端：
- 内嵌托管 HTTP 服务（后台线程），无需额外的隐藏守护进程；
- 使用系统原生 WebView（pywebview）承载现有 WebUI，观感接近原生客户端；
- 关闭窗口 = 缩到右下角系统托盘，服务继续运行；
- 托盘右键菜单：打开控制台 / 同步更新 / 查看日志 / 退出；
- 单实例保证：已有实例运行时，再次启动只会呼出已存在的窗口。

依赖：pywebview、pystray、Pillow（见 requirements.txt）。
纯 CLI 功能（search / commit）不依赖本模块，由 cli.py 独立提供。
"""

import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
from pathlib import Path

def _resolve_base_dir():
    """数据目录（PID / config / 日志）：源码=项目根；打包=exe 所在目录"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def _resolve_resource_dir():
    """只读资源目录（assets）：源码=项目根；打包=临时解包目录"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent

BASE_DIR = _resolve_base_dir()
RESOURCE_DIR = _resolve_resource_dir()
ICON_PNG = RESOURCE_DIR / "assets" / "icon.png"
ICON_ICO = RESOURCE_DIR / "assets" / "icon.ico"
PID_FILE = BASE_DIR / ".skillbox.pid"

DEFAULT_PORT = 7860
MAX_PORT = 7880

APP_NAME = "SkillBox"
APP_TITLE = "SkillBox - AI 技能管理器"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820


# ============================================================
# Windows 应用标识与窗口图标
# ============================================================

def _set_app_user_model_id():
    """
    设置 Windows AppUserModelID，使任务栏、通知、Alt-Tab 归属显示为 SkillBox，
    而非底层的 python.exe。非 Windows 平台直接跳过。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SkillBox.AI.SkillManager")
    except Exception:
        pass


def _apply_window_icon(window=None):
    """
    尽力为 Windows 主窗口设置 SkillBox 图标（左上角 + 任务栏）。
    优先设置给 pywebview 的窗口句柄；pywebview 各版本句柄位置不一，
    因此做多重探测，全部失败也仅静默忽略（打包 exe 时嵌图标是更可靠的方式）。
    """
    if sys.platform != "win32" or not ICON_ICO.exists():
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        hicon_small = u.LoadImageW(None, str(ICON_ICO), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        hicon_big = u.LoadImageW(None, str(ICON_ICO), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hicon_big:
            return

        # 收集候选顶层窗口句柄（同进程 + 标题匹配）
        EnumWindows = u.EnumWindows
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        my_pid = os.getpid()
        handles = []

        def _cb(hwnd, _):
            pid = ctypes.c_ulong()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == my_pid:
                n = u.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hwnd, buf, n + 1)
                    if "SkillBox" in buf.value:
                        handles.append(hwnd)
            return True

        EnumWindows(CB(_cb), 0)
        for hwnd in handles:
            u.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
            if hicon_small:
                u.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    except Exception:
        pass


# ============================================================
# 依赖探测
# ============================================================

def check_dependencies():
    """
    探测桌面托盘所需的第三方依赖是否就绪。
    返回: (ok: bool, missing: list[str], error: str)
    """
    missing = []
    try:
        import webview  # noqa: F401
    except Exception:
        missing.append("pywebview")
    try:
        import pystray  # noqa: F401
    except Exception:
        missing.append("pystray")
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        missing.append("Pillow")
    return (len(missing) == 0), missing, ""


# ============================================================
# 单实例与现有服务探测
# ============================================================

def _probe_port(port, timeout=0.5):
    """探测指定端口上是否有 SkillBox 服务在监听"""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout)
        return resp.status == 200
    except Exception:
        return False


def find_running_service(base_port=DEFAULT_PORT, max_port=MAX_PORT):
    """
    查找本机已有 SkillBox 服务的监听端口。
    优先读取 PID 文件，其次在端口区间内探测。
    返回: 端口号 int 或 None
    """
    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text(encoding="utf-8").strip()
            if ":" in content:
                _, port = content.split(":")
                if _probe_port(int(port)):
                    return int(port)
        except Exception:
            pass
    for port in range(base_port, max_port):
        if _probe_port(port, timeout=0.3):
            return port
    return None


def _port_in_use(host, port):
    """检测本机某端口是否已被占用（用于选端口时跳过）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


# ============================================================
# 跨进程单实例锁
# ============================================================

_SINGLETON_MUTEX_NAME = "Global\\SkillBoxDesktopApp_Singleton_9F2A"
_singleton_handle = None  # 保持引用，进程存活期间不可释放


def acquire_single_instance():
    """
    尝试获取跨进程单实例锁。
    - Windows：命名互斥体（CreateMutexW），已存在则返回 None
    - macOS/Linux：对用户目录下锁文件加 flock，已锁定则返回 None
    返回：成功获取的锁句柄（需保持引用）；失败返回 None。
    """
    global _singleton_handle
    try:
        if sys.platform == "win32":
            import ctypes
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, _SINGLETON_MUTEX_NAME)
            if not handle:
                return None
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return None
            _singleton_handle = handle
            return handle
        else:
            import fcntl
            lock_path = BASE_DIR / ".skillbox.lock"
            lock_file = open(str(lock_path), "w")
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                return None
            _singleton_handle = lock_file
            return lock_file
    except Exception:
        # 加锁机制异常时放行（宁可多开，也不要因锁失败而无法启动）
        return True


def activate_running_instance(timeout=3.0):
    """
    通知已运行的实例呼出其主窗口（供重复启动时唤醒使用）。
    返回 True 表示成功唤醒已运行实例。
    """
    import json
    import urllib.request
    port = find_running_service()
    if not port:
        return False
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/activate",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8")).get("ok", False)
    except Exception:
        return False


# ============================================================
# 桌面托盘应用
# ============================================================

class SkillBoxDesktopApp:
    def __init__(self, port=None, startup=False):
        self.port = port
        self.url = f"http://127.0.0.1:{port}" if port else ""
        self.server = None
        self.owns_server = False
        self.window = None
        self.tray = None
        self._tray_thread = None
        self._quitting = False
        self._lock = threading.RLock()
        # startup=True 表示由「开机自启」拉起：窗口不弹出，静默进入系统托盘
        self._startup = startup

    # ---------- 服务生命周期 ----------

    def _ensure_cli(self):
        """启动时自动检测 skillbox 命令是否已注册，未安装则自动安装（幂等、静默失败）"""
        try:
            from app import ensure_cli_installed
            installed = ensure_cli_installed()
            if installed:
                print("[*] 已自动完成 skillbox 命令注册（新开终端即可使用）。", flush=True)
        except Exception as e:
            print(f"[*] skillbox 命令自检跳过: {e}", flush=True)

    def _start_embedded_server(self):
        """在后台线程启动内嵌 HTTP 服务；端口被占用时复用已有服务"""
        self._ensure_cli()
        existing = find_running_service()
        if existing:
            self.port = existing
            self.url = f"http://127.0.0.1:{existing}"
            self.owns_server = False
            return True

        from app import start_server
        server, actual_port = start_server()
        if not server:
            return False

        self.server = server
        self.port = actual_port
        self.url = f"http://127.0.0.1:{actual_port}"
        self.owns_server = True

        threading.Thread(
            target=server.serve_forever,
            name="skillbox-http",
            daemon=True,
        ).start()
        return True

    def _stop_embedded_server(self):
        if self.owns_server and self.server:
            from app import stop_server
            stop_server(self.server)
            self.server = None
            self.owns_server = False

    # ---------- 窗口与托盘动作（线程安全） ----------

    def show_window(self):
        """呼出并聚焦主窗口"""
        with self._lock:
            try:
                if self.window is not None:
                    self.window.show()
                    self.window.restore()
                    return
            except Exception:
                pass
        # 窗口尚未创建（极早期点击），直接以浏览器兜底打开
        if self.url:
            webbrowser.open(self.url)

    def _open_in_browser(self):
        if self.url:
            webbrowser.open(self.url)

    def trigger_update(self):
        """触发所有 Git 仓库增量拉取（优先走本地 HTTP API，回退直接调用）"""
        import json
        import urllib.request
        try:
            req = urllib.request.Request(
                f"{self.url}/api/pull_all",
                data=b"{}",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("ok"):
                self._notify("SkillBox", "所有 Git 仓库已更新完毕，挂载实时生效！")
            else:
                self._notify("SkillBox", f"部分仓库更新失败: {res.get('error')}")
        except Exception as e:
            self._notify("SkillBox", f"更新失败: {e}")

    def open_log(self):
        log_file = BASE_DIR / "skillbox.log"
        try:
            if not log_file.exists():
                self._notify("SkillBox", "暂无运行日志文件。")
                return
            if sys.platform == "win32":
                os.startfile(str(log_file))  # noqa: SIM115
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(log_file)])
            else:
                subprocess.Popen(["xdg-open", str(log_file)])
        except Exception as e:
            self._notify("SkillBox", f"无法打开日志: {e}")

    def open_data_dir(self):
        try:
            if sys.platform == "win32":
                os.startfile(str(BASE_DIR))  # noqa: SIM115
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(BASE_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(BASE_DIR)])
        except Exception:
            pass

    def _notify(self, title, message):
        """通过托盘气泡发送系统通知（失败静默）"""
        try:
            if self.tray is not None and hasattr(self.tray, "notify"):
                self.tray.notify(message, title)
        except Exception:
            pass

    def quit_app(self):
        """退出整个托盘应用：停服务、处理 PID 文件、结束进程"""
        with self._lock:
            if self._quitting:
                return
            self._quitting = True
        try:
            self._stop_embedded_server()
        except Exception:
            pass
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            pass
        # 强制结束自身进程，确保托盘图标与线程彻底退出
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)

    # ---------- 托盘菜单 ----------

    def _build_tray_image(self):
        from PIL import Image
        icon_path = ICON_ICO if (sys.platform == "win32" and ICON_ICO.exists()) else ICON_PNG
        if icon_path.exists():
            try:
                return Image.open(str(icon_path))
            except Exception:
                pass
        # 兜底：生成一个纯色方块图标
        return Image.new("RGBA", (64, 64), (56, 132, 255, 255))

    def _run_tray(self):
        import pystray
        from pystray import MenuItem as Item, Menu

        menu = Menu(
            Item("打开控制台", lambda: self.show_window(), default=True),
            Item("在浏览器中打开", lambda: self._open_in_browser()),
            Menu.SEPARATOR,
            Item("同步更新技能", lambda: self.trigger_update()),
            Item("查看运行日志", lambda: self.open_log()),
            Item("打开程序目录", lambda: self.open_data_dir()),
            Menu.SEPARATOR,
            Item("退出 SkillBox", lambda: self.quit_app()),
        )
        self.tray = pystray.Icon(
            name=APP_NAME,
            icon=self._build_tray_image(),
            title=APP_TITLE,
            menu=menu,
        )
        try:
            self.tray.run()
        except Exception:
            pass

    # ---------- 窗口关闭事件 ----------

    def _on_closing(self):
        """关闭窗口时：静默隐藏而非退出，缩到系统托盘继续运行（不弹任何提示）"""
        if self._quitting:
            return True
        try:
            if self.window is not None:
                self.window.hide()
        except Exception:
            pass
        return False  # 阻止默认关闭销毁行为

    # ---------- 主入口 ----------

    def run(self):
        import webview

        _set_app_user_model_id()

        # ===== 单实例保证：已有实例在运行则唤醒它并退出本进程 =====
        lock = acquire_single_instance()
        if lock is None:
            # 稍作重试，容忍「上一实例刚启动、服务尚未就绪」的竞态
            for _ in range(10):
                if activate_running_instance():
                    break
                time.sleep(0.3)
            print("[*] SkillBox 已在运行，已呼出已有窗口并退出本次启动。", flush=True)
            return 0

        if not self._start_embedded_server():
            print("[!] 无法启动 SkillBox 服务，桌面应用退出。", flush=True)
            return 1

        print(f"[*] SkillBox 桌面应用已启动，服务地址: {self.url}", flush=True)

        # 托盘图标运行在独立线程；主线程留给 pywebview 窗口
        self._tray_thread = threading.Thread(target=self._run_tray, name="skillbox-tray")
        self._tray_thread.daemon = True
        self._tray_thread.start()

        # 稍等托盘就绪，避免窗口关闭时托盘图标尚未出现
        time.sleep(0.3)

        self.window = webview.create_window(
            APP_TITLE,
            url=self.url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(900, 600),
            hidden=self._startup,   # 开机自启时静默进托盘，不弹出窗口
            confirm_close=False,
        )
        self.window.events.closing += self._on_closing

        # 注册单实例唤醒回调：重复启动时由 /api/activate 触发，呼出并聚焦本窗口
        try:
            import app as _app
            _app.ACTIVATE_CALLBACK["fn"] = self.show_window
        except Exception:
            pass

        # 窗口出现后异步补齐左上角图标（不阻塞 webview 主循环）
        threading.Thread(target=self._apply_icon_later, daemon=True).start()

        try:
            webview.start()
        except Exception as e:
            print(f"[!] WebView 启动失败: {e}", flush=True)
            return 1
        finally:
            # webview.start() 返回意味着窗口循环结束（退出流程）
            self.quit_app()
        return 0

    def _apply_icon_later(self):
        """等待 winforms 窗口真正创建后再设置图标（多重尝试，静默失败）"""
        for _ in range(20):
            time.sleep(0.3)
            _apply_window_icon()
            if self._quitting:
                return


def run_desktop(port=None, startup=False):
    """对外入口：检查依赖并启动桌面托盘应用"""
    ok, missing, _ = check_dependencies()
    if not ok:
        print(
            "[!] 缺少桌面托盘应用所需依赖: " + ", ".join(missing) + "\n"
            "    请执行安装:  pip install -r requirements.txt\n"
            "    （源码运行需上述依赖；使用打包好的 SkillBox.exe 无需安装）",
            flush=True,
        )
        return 1
    app = SkillBoxDesktopApp(port=port, startup=startup)
    return app.run()


if __name__ == "__main__":
    _startup = "--startup" in sys.argv
    sys.exit(run_desktop(startup=_startup))
