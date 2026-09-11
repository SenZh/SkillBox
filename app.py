import os
import sys
import json
import time
import shutil
import threading
import subprocess
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

__version__ = "0.1.0"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
CACHE_BASE_DIR = BASE_DIR / ".skillbox_cache"
BUILTIN_SKILLS_DIR = BASE_DIR / "builtin_skills"
LOG_FILE = BASE_DIR / "skillbox.log"

def log(msg, level="INFO"):
    """记录运行日志并同时输出到标准输出与 skillbox.log 文件"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

DEFAULT_CONFIG = {
    "default_install_to": str(Path.home() / ".agents" / "skills"),
    "sources": [],
    "folder_overrides": {},  # { "business/bind-center": "custom/path" }
    "skill_overrides": {}   # { "skill_name": "custom/path" }
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if "install_to" in saved and "default_install_to" not in saved:
                    saved["default_install_to"] = saved["install_to"]
                if "git_url" in saved and saved.get("git_url") and not saved.get("sources"):
                    saved["sources"] = [{
                        "id": "src-default",
                        "name": "默认仓库",
                        "git_url": saved.get("git_url", ""),
                        "branch": saved.get("branch", "main"),
                        "sub_dir": saved.get("sub_dir", "skills")
                    }]
                cfg.update(saved)
        except Exception:
            pass
    if "sources" not in cfg or not isinstance(cfg["sources"], list):
        cfg["sources"] = []
    # 兼容历史数据：早期创建的仓库源可能缺失 auto_update_interval 字段，
    # 调度器缺省按 0（仅手动）处理，而前端展示缺省按 60 兜底，导致"界面显示已定时但实际不触发"。
    # 此处统一补默认值 60 分钟，保证前后端一致。
    for s in cfg["sources"]:
        if isinstance(s, dict) and "auto_update_interval" not in s:
            s["auto_update_interval"] = 60
    if "folder_overrides" not in cfg or not isinstance(cfg["folder_overrides"], dict):
        cfg["folder_overrides"] = {}
    if "skill_overrides" not in cfg or not isinstance(cfg["skill_overrides"], dict):
        cfg["skill_overrides"] = {}
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

AUTOSTART_APP_NAME = "SkillBox"
AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_autostart_status():
    """获取当前用户 Windows 开机自启动状态"""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            return True
    except WindowsError:
        return False

def set_autostart(enable: bool):
    """注册或注销 Windows 开机静默自启动 (无需管理员权限)

    成功返回 True；失败抛出 RuntimeError（由调用方负责向用户回传真实原因）。
    """
    if sys.platform != "win32":
        raise RuntimeError("当前系统非 Windows，不支持开机自启动")
    import winreg
    # 仅替换文件名部分，保留路径原始大小写（避免整条路径被 lower() 破坏）
    python_exe = sys.executable
    if python_exe.lower().endswith("python.exe"):
        pythonw_exe = python_exe[:-len("python.exe")] + "pythonw.exe"
    else:
        pythonw_exe = python_exe
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe
    app_script = str((BASE_DIR / "app.py").resolve())
    cmd_str = f'"{pythonw_exe}" "{app_script}" --silent'
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, AUTOSTART_APP_NAME, 0, winreg.REG_SZ, cmd_str)
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError as e:
        raise RuntimeError(f"写入注册表失败: {e}")
    return enable

def git_cmd(args, cwd=None):
    creation_flags = 0x08000000 if sys.platform == "win32" else 0
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=creation_flags
    )
    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(err or f"Git command failed: {' '.join(args)}")
    return res.stdout.strip()

def safe_create_link(source_path: Path, target_link: Path):
    """
    创建目录联结或符号链接：
    1. Windows 优先调用原生 _winapi.CreateJunction (完全零子进程，零控制台窗口，纳秒级)
    2. Windows 兜底使用 cmd /c mklink 但带上 CREATE_NO_WINDOW 标志彻底杜绝黑框闪烁
    3. 类 Unix 平台使用 symlink_to
    """
    target_link.parent.mkdir(parents=True, exist_ok=True)
    if target_link.exists():
        return

    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(source_path), str(target_link))
            return
        except Exception:
            pass

        # 兜底：带 CREATE_NO_WINDOW 绝不闪终端黑框
        creation_flags = 0x08000000
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target_link), str(source_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
    else:
        target_link.symlink_to(source_path)

def safe_remove_link(link_path: Path):
    """安全解绑符号链接或 NTFS 目录联结 (Junction)，绝不误删物理源码文件"""
    if not link_path.exists() and not link_path.is_symlink():
        return
    try:
        if sys.platform == "win32":
            # 在 Windows 上，os.rmdir 可以直接、安全地解绑并删除 NTFS Junction (零子进程零闪屏)
            try:
                os.rmdir(link_path)
            except OSError:
                if link_path.is_symlink():
                    link_path.unlink()
                elif link_path.is_file():
                    link_path.unlink()
                else:
                    creation_flags = 0x08000000
                    subprocess.run(
                        ["cmd", "/c", "rmdir", str(link_path)],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creation_flags
                    )
        else:
            if link_path.is_symlink() or link_path.is_file():
                link_path.unlink()
            elif link_path.is_dir():
                shutil.rmtree(link_path)
    except Exception as e:
        print(f"[!] 解除挂载链接失败 {link_path}: {e}", flush=True)

def parse_skill_metadata(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        skill_md = skill_dir / "skill.md"
    if not skill_md.exists():
        return "无描述", []
    try:
        content = skill_md.read_text(encoding="utf-8", errors="ignore")
        in_frontmatter = False
        desc = ""
        tags = []
        for line in content.splitlines():
            line_s = line.strip()
            if line_s == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                if line_s.startswith("description:"):
                    desc = line_s.split("description:", 1)[1].strip().strip('"').strip("'").lstrip(">-").strip()
                elif line_s.startswith("tags:"):
                    raw = line_s.split("tags:", 1)[1].strip()
                    if raw.startswith("[") and raw.endswith("]"):
                        tags = [t.strip().strip('"').strip("'") for t in raw[1:-1].split(",") if t.strip()]
        if not desc:
            for line in content.splitlines():
                l = line.strip()
                if l and not l.startswith("#") and not l.startswith("---"):
                    desc = l[:120] + ("..." if len(l) > 120 else "")
                    break
        return desc or "无描述", tags
    except Exception:
        return "无法读取描述", []

def pull_single_source(src):
    src_id = src["id"]
    git_url = src.get("git_url", "").strip()
    branch = src.get("branch", "main").strip()
    if not git_url:
        raise ValueError(f"仓库 [{src.get('name')}] 未配置 Git URL")

    cache_dir = CACHE_BASE_DIR / src_id
    if not cache_dir.exists() or not (cache_dir / ".git").exists():
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["clone"]
        if branch:
            cmd += ["-b", branch]
        cmd += ["--depth", "1", git_url, str(cache_dir)]
        git_cmd(cmd)
    else:
        git_cmd(["fetch", "origin", branch], cwd=cache_dir)
        git_cmd(["checkout", branch], cwd=cache_dir)
        git_cmd(["pull", "origin", branch], cwd=cache_dir)

    # 记录最新更新时间
    now = time.time()
    src["last_pulled_ts"] = now
    src["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

def auto_update_scheduler():
    """后台常驻守护线程：按各仓库配置的定时频率自动拉取更新"""
    while True:
        try:
            time.sleep(30) # 每 30 秒巡检一次
            cfg = load_config()
            sources = cfg.get("sources", [])
            now = time.time()
            updated_any = False

            for s in sources:
                interval_min = int(s.get("auto_update_interval", 0))
                if interval_min > 0:
                    last_ts = float(s.get("last_pulled_ts", 0))
                    # 达到定时周期触发 pull
                    if now - last_ts >= interval_min * 60:
                        try:
                            print(f"[*] [Auto-Update] 触发仓库 [{s.get('name')}] 自动拉取更新...", flush=True)
                            pull_single_source(s)
                            updated_any = True
                            print(f"[✓] [Auto-Update] 仓库 [{s.get('name')}] 自动更新成功，已挂载软链接实时生效！", flush=True)
                        except Exception as e:
                            print(f"[!] [Auto-Update] 仓库 [{s.get('name')}] 自动更新失败: {e}", flush=True)

            if updated_any:
                save_config(cfg)
        except Exception as e:
            pass

def resolve_skill_install_dir(skill_name, folder_path, cfg):
    """
    自底向上解析某个 Skill 的目标安装路径：
    1. Skill 自身专属路径 (skill_overrides)
    2. 所在目录及逐级向上匹配的祖先目录路径 (folder_overrides，例如 business/bind-center -> business)
    3. 全局默认安装路径 (default_install_to)
    返回: (Path对象, 来源类型 'skill'|'folder'|'default', 路径字符串, 命中的目录键名)
    """
    skill_overrides = cfg.get("skill_overrides", {})
    folder_overrides = cfg.get("folder_overrides", {})
    default_install_to = Path(cfg.get("default_install_to", "")).expanduser()

    # 1. 技能自身专属
    if skill_name in skill_overrides and skill_overrides[skill_name].strip():
        p = skill_overrides[skill_name].strip()
        return (Path(p).expanduser(), "skill", p, skill_name)

    # 2. 目录及祖先目录匹配 (自底向上寻找最精准的目录配置)
    if folder_path:
        parts = [seg for seg in folder_path.strip("/").split("/") if seg]
        candidates = ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]
        for c in candidates:
            if c in folder_overrides and folder_overrides[c].strip():
                fp = folder_overrides[c].strip()
                return (Path(fp).expanduser(), "folder", fp, c)

    # 3. 全局默认路径
    return (default_install_to, "default", str(default_install_to), "")

def is_git_managed(path: Path):
    """
    判断给定路径是否处于 Git 版本管理之下（向上逐级查找 .git 目录/文件）。
    返回: (True, git_root) 或 (False, None)
    """
    try:
        p = Path(path).resolve()
    except Exception:
        p = Path(path)
    cur = p if p.is_dir() else p.parent
    for ancestor in [cur] + list(cur.parents):
        if (ancestor / ".git").exists():
            return True, ancestor
    return False, None

def resolve_skill(skill_name, cfg=None):
    """
    解析单个技能，返回其源真身路径、所在 Git 仓库、分支等确定性信息。
    命中多个同名技能时，优先返回已挂载的那个，其次返回第一个。
    """
    if cfg is None:
        cfg = load_config()

    # 内置技能优先：跟随 SkillBox 工具分发，不依赖用户 Git 仓库
    builtin_dir = BUILTIN_SKILLS_DIR / skill_name
    if builtin_dir.is_dir() and ((builtin_dir / "SKILL.md").exists() or (builtin_dir / "skill.md").exists()):
        true_path = builtin_dir
        managed, git_root = is_git_managed(true_path)
        sub_dir = ""
        if managed and git_root is not None:
            try:
                sub_dir = str(true_path.resolve().relative_to(Path(git_root).resolve())).replace("\\", "/")
            except Exception:
                sub_dir = ""
        default_dir = Path(cfg.get("default_install_to", "")).expanduser()
        mount_paths = []
        mp = default_dir / skill_name
        if mp.exists() or mp.is_symlink():
            mount_paths.append(str(mp))
        return {
            "name": skill_name,
            "true_path": str(true_path),
            "git_managed": managed,
            "git_dir": str(git_root) if (managed and git_root) else "",
            "git_branch": "",
            "sub_dir": sub_dir,
            "source_id": "builtin",
            "source_name": "SkillBox 内置技能",
            "is_builtin": True,
            "mount_paths": mount_paths,
        }

    skills = [s for s in scan_all_skills(cfg) if s["name"] == skill_name]
    if not skills:
        raise ValueError(f"未找到名为 [{skill_name}] 的技能，请检查名称或先拉取仓库源")

    skill = next((s for s in skills if s.get("installed")), skills[0])
    true_path = Path(skill["source_path"])
    managed, git_root = is_git_managed(true_path)
    sub_dir = ""

    src = next((x for x in cfg.get("sources", []) if x.get("id") == skill["source_id"]), None)
    source_branch = (src or {}).get("branch", skill.get("source_branch", "main"))

    if managed and git_root is not None:
        # 计算 git 仓库根与当前技能目录的相对路径（用于白名单提交）
        try:
            sub_dir = str(true_path.resolve().relative_to(Path(git_root).resolve())).replace("\\", "/")
        except Exception:
            sub_dir = ""
        repo_dir = str(git_root)
    else:
        repo_dir = ""

    mount_paths = []
    default_dir = Path(cfg.get("default_install_to", "")).expanduser()
    candidates = {Path(skill["effective_install_to"]).expanduser() / skill_name}
    candidates.add(default_dir / skill_name)
    for d in (candidates | {Path(p).expanduser() / skill_name for p in cfg.get("skill_overrides", {}).values() if p.strip()}):
        try:
            if d.exists() or d.is_symlink():
                mount_paths.append(str(d))
        except Exception:
            pass

    return {
        "name": skill_name,
        "true_path": str(true_path),
        "git_managed": managed,
        "git_dir": repo_dir,
        "git_branch": source_branch,
        "sub_dir": sub_dir,
        "source_id": skill["source_id"],
        "source_name": skill["source_name"],
        "mount_paths": mount_paths,
    }

def scan_builtin_skills():
    """
    扫描 SkillBox 自带的内置技能目录 (builtin_skills/)。
    内置技能跟随工具版本分发，不依赖任何用户 Git 仓库，用于承载工具自身的说明书类 Skill。
    返回: [{name, source_path}, ...]
    """
    result = []
    if not BUILTIN_SKILLS_DIR.exists():
        return result
    for child in sorted(BUILTIN_SKILLS_DIR.iterdir()):
        if child.is_dir() and ((child / "SKILL.md").exists() or (child / "skill.md").exists()):
            result.append({"name": child.name, "source_path": str(child)})
    return result

def install_builtin_skills(cfg=None):
    """
    将内置技能默认挂载到全局默认安装目录根部 (default_install_to/<name>)。
    该操作幂等，每次服务启动时执行，确保内置技能始终可用且不依赖用户勾选。
    """
    if cfg is None:
        cfg = load_config()
    default_dir = Path(cfg.get("default_install_to", "")).expanduser()
    if not str(default_dir):
        return 0
    count = 0
    for skill in scan_builtin_skills():
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
            target_link = default_dir / skill["name"]
            if not target_link.exists():
                safe_create_link(Path(skill["source_path"]), target_link)
                log(f"[Builtin] 已默认挂载内置技能: {skill['name']} -> {target_link}")
                count += 1
        except Exception as e:
            log(f"[Builtin] 内置技能 [{skill['name']}] 挂载失败: {e}", level="ERROR")
    return count

def ensure_cli_installed():
    """
    确保 skillbox 命令已注册到当前用户 PATH（HKCU\\Environment），无需管理员权限。
    服务启动时自动调用：未安装则自动安装，已安装则跳过。幂等且失败不阻断服务启动。
    """
    if sys.platform != "win32":
        return False
    launcher = BASE_DIR / "skillbox.bat"
    if not launcher.exists():
        return False
    bin_dir = str(BASE_DIR)
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
                cur, _ = winreg.QueryValueEx(key, "Path")
                cur = cur or ""
        except FileNotFoundError:
            cur = ""
        parts = [p for p in cur.split(";") if p.strip()]
        if any(p.rstrip("\\").lower() == bin_dir.rstrip("\\").lower() for p in parts):
            return False  # 已安装

        parts.append(bin_dir)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
        # 广播环境变量变更，让新开终端尽快感知
        try:
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
        except Exception:
            pass
        log(f"[CLI] 已自动将 skillbox 命令注册到用户 PATH: {bin_dir}")
        return True
    except Exception as e:
        log(f"[CLI] 自动安装 skillbox 命令失败: {e}", level="ERROR")
        return False

def scan_all_skills(cfg):
    sources = cfg.get("sources", [])
    all_skills = []

    for src in sources:
        src_id = src["id"]
        src_name = src.get("name", "未命名仓库")
        cache_dir = CACHE_BASE_DIR / src_id
        sub_name = src.get("sub_dir", "").strip().strip("/\\")
        sub_dir = (cache_dir / sub_name) if sub_name and sub_name != "." else cache_dir

        if not sub_dir.exists():
            continue

        for root, dirs, files in os.walk(sub_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            p_root = Path(root)
            if (p_root / "SKILL.md").exists() or (p_root / "skill.md").exists():
                skill_name = p_root.name
                rel_path = p_root.relative_to(sub_dir)
                tag = p_root.parent.name if p_root.parent != sub_dir and p_root.parent.name else (sub_dir.name or "root")
                folder_path = str(rel_path.parent).replace("\\", "/") if str(rel_path.parent) != "." else ""
                desc, file_tags = parse_skill_metadata(p_root)

                target_dir, path_src_type, path_str, matched_folder = resolve_skill_install_dir(skill_name, folder_path, cfg)
                target_path = target_dir / skill_name
                installed = target_path.exists()

                all_skills.append({
                    "name": skill_name,
                    "tag": tag,
                    "folder_path": folder_path,
                    "source_id": src_id,
                    "source_name": src_name,
                    "source_branch": src.get("branch", "main"),
                    "source_path": str(p_root),
                    "desc": desc,
                    "custom_install_to": cfg.get("skill_overrides", {}).get(skill_name, "").strip(),
                    "folder_install_to": path_str if path_src_type == "folder" else "",
                    "matched_folder": matched_folder,
                    "effective_install_to": str(target_dir),
                    "path_source_type": path_src_type,
                    "is_custom": path_src_type != "default",
                    "installed": installed
                })

    return all_skills

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SkillBox - AI 技能管理器</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
  <style>
    .modal-backdrop { background: rgba(15, 23, 42, 0.45); backdrop-filter: blur(4px); }
    /* 自定义滚动条 */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
    /* Markdown 预览排版 */
    .prose-preview { font-size: 0.875rem; line-height: 1.7; color: #334155; }
    .prose-preview h1, .prose-preview h2, .prose-preview h3, .prose-preview h4 { font-weight: 700; color: #0f172a; margin: 1.25em 0 0.6em; line-height: 1.3; }
    .prose-preview h1 { font-size: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3em; }
    .prose-preview h2 { font-size: 1.25rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.25em; }
    .prose-preview h3 { font-size: 1.1rem; }
    .prose-preview h4 { font-size: 1rem; }
    .prose-preview p { margin: 0.75em 0; }
    .prose-preview ul, .prose-preview ol { margin: 0.75em 0; padding-left: 1.6em; }
    .prose-preview ul { list-style: disc; }
    .prose-preview ol { list-style: decimal; }
    .prose-preview li { margin: 0.35em 0; }
    .prose-preview li > ul, .prose-preview li > ol { margin: 0.25em 0; }
    .prose-preview a { color: #4f46e5; text-decoration: underline; }
    .prose-preview code { background: #f1f5f9; color: #be185d; padding: 0.15em 0.4em; border-radius: 4px; font-size: 0.85em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .prose-preview pre { background: #0f172a; color: #e2e8f0; padding: 1em; border-radius: 10px; overflow-x: auto; margin: 0.85em 0; }
    .prose-preview pre code { background: transparent; color: inherit; padding: 0; font-size: 0.85em; }
    .prose-preview blockquote { border-left: 3px solid #a5b4fc; background: #f8fafc; padding: 0.5em 1em; margin: 0.85em 0; color: #475569; }
    .prose-preview table { border-collapse: collapse; width: 100%; margin: 0.85em 0; font-size: 0.85em; display: block; overflow-x: auto; }
    .prose-preview th, .prose-preview td { border: 1px solid #e2e8f0; padding: 0.5em 0.75em; text-align: left; }
    .prose-preview th { background: #f8fafc; font-weight: 600; color: #0f172a; }
    .prose-preview tr:nth-child(even) td { background: #fcfcfd; }
    .prose-preview hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.5em 0; }
    .prose-preview img { max-width: 100%; border-radius: 8px; }
    .prose-preview > *:first-child { margin-top: 0; }
    .prose-preview > *:last-child { margin-bottom: 0; }
  </style>
</head>
<body class="bg-[#f8fafc] text-slate-800 min-h-screen font-sans antialiased flex flex-col">
  <!-- Top Navigation Header -->
  <header class="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 shadow-xs">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
      <!-- Logo & Primary Tabs -->
      <div class="flex items-center gap-8 min-w-0">
        <div class="flex items-center gap-2.5 shrink-0 cursor-pointer" onclick="switchPage('skills')">
          <span class="text-2xl">📦</span>
          <span class="font-bold text-lg text-slate-900 tracking-tight">SkillBox</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100 font-mono font-medium">v0.1</span>
        </div>

        <!-- 页面 Tab 切换导航 -->
        <nav class="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200/60">
          <button id="nav-tab-skills" onclick="switchPage('skills')" class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 bg-white text-indigo-600 shadow-xs">
            <span>🗂️</span>
            <span>技能工作区</span>
          </button>
          <button id="nav-tab-settings" onclick="switchPage('settings')" class="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5">
            <span>⚙️</span>
            <span>仓库与配置</span>
            <span id="nav-repo-badge" class="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-200/80 text-slate-600 font-mono">0</span>
          </button>
        </nav>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center gap-2.5 shrink-0">
        <button onclick="pullAllSources()" class="px-3.5 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium rounded-xl border border-slate-200 shadow-xs transition flex items-center gap-1.5 active:scale-98" title="从远程 Git 仓库拉取最新提交并更新本地缓存">
          <span class="text-indigo-600">🔄</span>
          <span>拉取 Git 更新</span>
        </button>
        <button id="btn-sync-action" onclick="syncSelected()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition flex items-center gap-2 active:scale-98" title="将当前勾选的所有 Skill 挂载安装到对应 Agent 目录，并自动解绑未选中的技能">
          <span>💾</span>
          <span>保存并生效挂载</span>
          <span id="selected-counter-badge" class="px-1.5 py-0.2 text-[10px] bg-indigo-500 text-white rounded-full font-mono font-medium">0</span>
        </button>
      </div>
    </div>
  </header>

  <!-- Main Content Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
    <!-- ================= PAGE 1: SKILLS WORKSPACE ================= -->
    <div id="page-skills" class="space-y-4">
      <!-- Toolbar Filter Bar -->
      <div class="bg-white p-3.5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <!-- Search & Selects -->
          <div class="flex items-center gap-2.5 flex-wrap min-w-0">
            <!-- Search -->
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none text-slate-400 text-xs">🔍</span>
              <input id="search-box" oninput="filterSkills()" type="text" placeholder="全局搜索技能、Tag、目录..." class="pl-8 pr-7 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl w-56 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition">
              <button id="btn-clear-search" onclick="clearSearch()" class="absolute inset-y-0 right-0 pr-2.5 flex items-center text-slate-400 hover:text-slate-600 text-xs hidden">✕</button>
            </div>

            <!-- Repo Source Filter -->
            <select id="source-filter" onchange="filterSkills()" class="px-3 py-1.5 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-slate-700 font-medium">
              <option value="all">所有仓库源</option>
            </select>

            <!-- Tag Filter -->
            <select id="tag-filter" onchange="onTagSelectChange()" class="px-3 py-1.5 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-slate-700 font-medium">
              <option value="all">所有 Tag 目录</option>
            </select>

            <!-- Status Filter (过滤显示已挂载技能) -->
            <select id="status-filter" onchange="filterSkills()" class="px-3 py-1.5 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-slate-700 font-medium">
              <option value="all">所有挂载状态</option>
              <option value="installed">✓ 仅已挂载 (Installed)</option>
              <option value="uninstalled">○ 仅未挂载 (Unmounted)</option>
            </select>

            <span id="skill-count" class="text-xs text-slate-400 font-mono shrink-0 ml-1">0 个技能</span>
          </div>

          <!-- View Switcher & Bulk Selection -->
          <div class="flex items-center gap-3 text-xs shrink-0 self-end md:self-auto">
            <div class="inline-flex rounded-xl border border-slate-200 bg-slate-100/60 p-0.5">
              <button id="view-btn-folder" onclick="switchView('folder')" class="px-3 py-1 rounded-lg text-xs font-semibold bg-white text-indigo-600 shadow-xs transition flex items-center gap-1">
                <span>📁</span> 目录树进入
              </button>
              <button id="view-btn-grid" onclick="switchView('grid')" class="px-3 py-1 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1">
                <span>▦</span> 全部平铺
              </button>
            </div>
            <div class="h-4 w-px bg-slate-200"></div>
            <button onclick="selectAll(true)" class="text-indigo-600 hover:text-indigo-800 font-medium">全选</button>
            <span class="text-slate-300">/</span>
            <button onclick="selectAll(false)" class="text-slate-500 hover:text-slate-800 font-medium">清空</button>
          </div>
        </div>

        <!-- Tag Pills (快捷胶囊栏) -->
        <div id="tag-pills-bar" class="flex items-center gap-1.5 flex-wrap text-[11px] pt-2 border-t border-slate-100">
          <!-- 动态注入 -->
        </div>
      </div>

      <!-- Breadcrumb Navigation Bar (在文件树视图或搜索时显示) -->
      <div id="breadcrumb-nav" class="flex items-center justify-between gap-3 px-4 py-2.5 bg-white rounded-2xl border border-slate-200/80 shadow-xs min-w-0">
        <div class="flex items-center gap-1.5 text-xs flex-wrap min-w-0 font-medium" id="breadcrumb-trail">
          <!-- 面包屑节点 -->
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button id="btn-back-parent" onclick="navigateUp()" class="px-3 py-1 bg-slate-100 hover:bg-slate-200/80 text-slate-700 rounded-lg text-xs font-medium transition flex items-center gap-1.5 active:scale-98">
            <span>⬅</span> 返回上一级
          </button>
          <button id="btn-config-current-folder" onclick="openCurrentFolderPathModal()" class="px-3 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-lg text-xs font-medium transition flex items-center gap-1 active:scale-98">
            <span>⚙️</span> 目录专属路径
          </button>
          <button id="btn-select-current-dir" onclick="selectCurrentDirSkills(true)" class="px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg text-xs font-semibold transition active:scale-98">
            全选本目录
          </button>
        </div>
      </div>

      <!-- Skills Explorer View Container -->
      <div id="skills-container" class="space-y-4">
        <!-- 动态生成子文件夹或具体技能卡片 -->
      </div>
    </div>

    <!-- ================= PAGE 2: SETTINGS & REPOSITORIES ================= -->
    <div id="page-settings" class="hidden max-w-4xl mx-auto space-y-6">
      <!-- Section 1: Global Default Path -->
      <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              <span>📁</span> 全局默认安装目录
            </h2>
            <p class="text-xs text-slate-500 mt-1">未单独为具体 Skill 配置专属路径时，所有技能默认通过目录联结（Junction/Symlink）挂载至该目录。</p>
          </div>
          <button onclick="saveDefaultInstallPath()" class="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-xl transition shadow-xs shrink-0">
            保存默认路径
          </button>
        </div>
        <div class="space-y-2">
          <input id="cfg-default-install" type="text" placeholder="如: C:\\Users\\Name\\.agents\\skills" class="w-full px-3.5 py-2.5 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition">
          <div class="flex items-center gap-2 text-[11px] text-slate-400">
            <span>💡 推荐填入你的 Agent 全局技能目录，例如 OpenCode、Claude Code、Cursor 所读取的 skills 文件夹。</span>
          </div>
        </div>
      </div>

      <!-- Section 2: Git Repositories Management -->
      <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-5">
        <div class="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              <span>🌿</span> Git 仓库源管理
            </h2>
            <p class="text-xs text-slate-500 mt-1">纳管企业私有 GitLab、GitHub 或自建 Git 仓库，支持指定具体分支与 Skill 所在的子目录。</p>
          </div>
          <button onclick="openSourceModal()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-xs transition flex items-center gap-1.5 active:scale-98 shrink-0">
            <span>+</span> 添加仓库源
          </button>
        </div>

        <!-- Repositories List Grid -->
        <div id="settings-sources-list" class="space-y-3.5">
          <!-- 动态注入仓库卡片 -->
        </div>
      </div>

      <!-- Section 3: Windows Auto-start on Boot -->
      <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
        <div class="flex items-center justify-between gap-4">
          <div class="space-y-1">
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              <span>🚀</span> Windows 开机静默自启服务
            </h2>
            <p class="text-xs text-slate-500">开机登录 Windows 时自动在后台静默启动 SkillBox 常驻服务（注册于当前用户注册表，无需管理员权限，开机不弹出黑框与浏览器，后台静默自动拉取更新）。</p>
          </div>
          <!-- Toggle Switch -->
          <label class="relative inline-flex items-center cursor-pointer shrink-0">
            <input type="checkbox" id="autostart-toggle" onchange="toggleAutostart(this.checked)" class="sr-only peer">
            <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
          </label>
        </div>
      </div>
    </div>
  </main>

  <!-- Modal 1: Add/Edit Git Source -->
  <div id="source-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-lg rounded-2xl border border-slate-200 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      <div class="px-6 py-4.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <h3 id="modal-title" class="font-bold text-sm text-slate-900">配置 Git 仓库源</h3>
        <button onclick="closeSourceModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
      </div>
      <div class="p-6 space-y-4">
        <input type="hidden" id="modal-src-id">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1.5">仓库名称 (别名)</label>
          <input id="modal-src-name" type="text" placeholder="如: 业务中台技能库" class="w-full px-3.5 py-2 text-xs border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1.5">Git 仓库地址 (HTTP / HTTPS / SSH)</label>
          <input id="modal-src-url" type="text" placeholder="如: git@gitlab.com:org/skills.git" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1.5">指定分支 (Branch)</label>
            <input id="modal-src-branch" type="text" placeholder="如: main、dev、feature/v1" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1.5">Skill 相对子目录</label>
            <input id="modal-src-subdir" type="text" placeholder="如: skills 或 . (根目录)" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
          </div>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1.5">定时自动更新频率 (后台自动 Git Pull)</label>
          <select id="modal-src-interval" class="w-full px-3.5 py-2 text-xs border border-slate-300 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-slate-700 font-medium">
            <option value="0">关闭自动更新 (仅手动更新)</option>
            <option value="30">每 30 分钟自动拉取</option>
            <option value="60" selected>每 1 小时自动拉取 (推荐)</option>
            <option value="360">每 6 小时自动拉取</option>
            <option value="720">每 12 小时自动拉取</option>
            <option value="1440">每 24 小时自动拉取</option>
          </select>
          <p class="text-[11px] text-slate-400 mt-1">更新完成后，由于采用符号链接机制，目标安装目录内的 Skill 代码将全自动实时变为最新版。</p>
        </div>
      </div>
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5">
        <button onclick="closeSourceModal()" class="px-4 py-2 text-xs text-slate-600 hover:bg-slate-200/80 rounded-xl font-medium transition">取消</button>
        <button onclick="saveSourceModal()" class="px-5 py-2 text-xs bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-xs transition">保存并立即拉取</button>
      </div>
    </div>
  </div>

  <!-- Modal 2: Custom Skill Path -->
  <div id="path-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-md rounded-2xl border border-slate-200 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <h3 class="font-bold text-sm text-slate-900">自定义安装目标路径</h3>
        <button onclick="closePathModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
      </div>
      <div class="p-6 space-y-3.5">
        <p class="text-xs text-slate-500 leading-relaxed">
          为技能 <span id="path-modal-skill-name" class="font-bold text-slate-900 font-mono"></span> 指定专属的安装目录（例如特定项目的本地 skills 文件夹）。留空则自动恢复继承全局默认路径。
        </p>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1.5">专属目标目录绝对路径</label>
          <input id="path-modal-input" type="text" placeholder="如: D:\my-project\.opencode\skills" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
        </div>
      </div>
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
        <button onclick="resetSkillPathToDefault()" class="text-xs text-slate-500 hover:text-slate-900 transition underline">恢复为全局默认路径</button>
        <div class="flex items-center gap-2">
          <button onclick="closePathModal()" class="px-3.5 py-2 text-xs text-slate-600 hover:bg-slate-200/80 rounded-xl font-medium transition">取消</button>
          <button onclick="saveSkillPathModal()" class="px-4.5 py-2 text-xs bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-xs transition">确认保存</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal 3: Custom Folder Mount Path -->
  <div id="folder-path-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-md rounded-2xl border border-slate-200 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <h3 class="font-bold text-sm text-slate-900">设置目录专属安装路径</h3>
        <button onclick="closeFolderPathModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
      </div>
      <div class="p-6 space-y-3.5">
        <p class="text-xs text-slate-500 leading-relaxed">
          为目录 <span id="folder-modal-path-name" class="font-bold text-slate-900 font-mono"></span> 下的所有技能统一配置专属安装目录。其子目录与所有技能将自动继承此路径。留空则恢复继承上级或全局默认路径。
        </p>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1.5">目录专属目标绝对路径</label>
          <input id="folder-modal-input" type="text" placeholder="如: D:\projects\my-app\.opencode\skills" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
        </div>
      </div>
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
        <button onclick="resetFolderPathToDefault()" class="text-xs text-slate-500 hover:text-slate-900 transition underline">恢复继承默认</button>
        <div class="flex items-center gap-2">
          <button onclick="closeFolderPathModal()" class="px-3.5 py-2 text-xs text-slate-600 hover:bg-slate-200/80 rounded-xl font-medium transition">取消</button>
          <button onclick="saveFolderPathModal()" class="px-4.5 py-2 text-xs bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-xs transition">确认保存并生效</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal 4: Skill Detail & Content Preview -->
  <div id="skill-detail-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-6xl max-h-[92vh] rounded-2xl border border-slate-200 shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      <!-- Header -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-start justify-between bg-slate-50/70 shrink-0">
        <div class="space-y-1.5 min-w-0 flex-1 pr-4">
          <div class="flex items-center gap-2 flex-wrap">
            <span id="detail-modal-title" class="font-bold text-base text-slate-900 font-mono"></span>
            <span id="detail-modal-status-badge" class="text-[10px] px-2 py-0.5 rounded-full font-semibold"></span>
            <span id="detail-modal-tag-badge" class="text-[10px] px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 font-mono font-medium"></span>
            <span id="detail-modal-source-badge" class="text-[10px] px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-100 font-mono font-medium"></span>
          </div>
          <div class="text-[11px] text-slate-500 font-mono truncate" id="detail-modal-path-info"></div>
        </div>
        <button onclick="closeSkillDetailModal()" class="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
      </div>

      <!-- Body (Scrollable) -->
      <div class="p-6 overflow-y-auto space-y-4.5 flex-1 text-sm">
        <!-- Description Block -->
        <div class="p-4 bg-slate-50/80 rounded-xl border border-slate-200/80 space-y-1.5">
          <div class="font-bold text-slate-800 flex items-center gap-1.5 text-sm">
            <span>📋</span> 功能描述 (Description)
          </div>
          <p id="detail-modal-desc" class="text-slate-600 leading-relaxed break-words text-sm"></p>
        </div>

        <!-- Raw Content / SKILL.md Preview -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-bold text-slate-800 flex items-center gap-1.5 text-sm">
              <span>📄</span> SKILL.md 文档与指令正文 (Content)
            </span>
            <div class="flex items-center gap-3">
              <div class="flex items-center bg-slate-100 rounded-lg p-0.5 border border-slate-200">
                <button id="detail-view-btn-preview" onclick="switchDetailView('preview')" class="px-3 py-1 text-xs font-semibold rounded-md transition bg-white text-indigo-700 shadow-xs">预览</button>
                <button id="detail-view-btn-raw" onclick="switchDetailView('raw')" class="px-3 py-1 text-xs font-semibold rounded-md transition text-slate-500 hover:text-slate-700">源码</button>
              </div>
              <button onclick="copySkillDetailContent()" class="text-indigo-600 hover:text-indigo-800 text-xs font-semibold flex items-center gap-1 hover:underline">
                <span>📋</span> 复制正文
              </button>
            </div>
          </div>
          <div id="detail-modal-preview" class="p-6 bg-white rounded-xl border border-slate-200 overflow-y-auto max-h-[60vh] prose-preview break-words"></div>
          <pre id="detail-modal-content" class="hidden p-5 bg-slate-900 text-slate-100 rounded-xl text-sm font-mono overflow-x-auto max-h-[60vh] whitespace-pre-wrap leading-relaxed select-all border border-slate-800"></pre>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <div class="flex items-center gap-2">
          <button id="detail-modal-toggle-mount-btn" onclick="toggleDetailModalSkillMount()" class="px-4 py-2 rounded-xl text-xs font-semibold shadow-xs transition flex items-center gap-1.5">
            <!-- 动态注入按钮文本 -->
          </button>
        </div>
        <button onclick="closeSkillDetailModal()" class="px-4 py-2 text-xs text-slate-600 hover:bg-slate-200/80 rounded-xl font-medium transition">关闭窗口</button>
      </div>
    </div>
  </div>

  <!-- Floating Toast Notification -->
  <div id="toast" class="fixed bottom-6 right-6 z-50 px-4 py-3 bg-slate-900 text-white text-xs font-medium rounded-2xl shadow-xl border border-slate-700/50 hidden flex items-center gap-2.5 transition-all">
    <span id="toast-icon">✨</span>
    <span id="toast-msg">操作成功</span>
  </div>

  <script>
    let globalConfig = { default_install_to: '', sources: [], skill_overrides: {} };
    let currentSkills = [];
    let currentEditingSkill = '';
    let currentSelectedTag = 'all';
    let currentViewMode = 'folder'; // 'folder' | 'grid'
    let currentNavPath = ''; // 相对路径，'' 为根目录
    let activePage = 'skills'; // 'skills' | 'settings'

    async function init() {
      await loadConfig();
      await loadSkills();
    }

    // Page Switching (单页 Tab 切换)
    function switchPage(page) {
      activePage = page;
      const tabSkills = document.getElementById('nav-tab-skills');
      const tabSettings = document.getElementById('nav-tab-settings');
      const pageSkills = document.getElementById('page-skills');
      const pageSettings = document.getElementById('page-settings');

      if (page === 'skills') {
        tabSkills.className = "px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 bg-white text-indigo-600 shadow-xs";
        tabSettings.className = "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5";
        pageSkills.classList.remove('hidden');
        pageSettings.classList.add('hidden');
      } else {
        tabSettings.className = "px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 bg-white text-indigo-600 shadow-xs";
        tabSkills.className = "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5";
        pageSettings.classList.remove('hidden');
        pageSkills.classList.add('hidden');
      }
    }

    async function loadConfig() {
      const res = await fetch('/api/config');
      globalConfig = await res.json();
      document.getElementById('cfg-default-install').value = globalConfig.default_install_to || '';
      renderSettingsSources(globalConfig.sources || []);
      updateSourceFilterOptions(globalConfig.sources || []);
      document.getElementById('nav-repo-badge').textContent = (globalConfig.sources || []).length;
      await loadAutostartStatus();
    }

    async function loadAutostartStatus() {
      try {
        const res = await fetch('/api/autostart');
        const data = await res.json();
        const toggle = document.getElementById('autostart-toggle');
        if (toggle) {
          toggle.checked = Boolean(data.enabled);
        }
      } catch (e) {}
    }

    async function toggleAutostart(enabled) {
      const toggle = document.getElementById('autostart-toggle');
      try {
        const res = await fetch('/api/autostart', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ enabled })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(data.enabled ? '已成功注册 Windows 开机静默自启！' : '已取消 Windows 开机自启。');
          if (toggle) toggle.checked = Boolean(data.enabled);
        } else {
          if (toggle) toggle.checked = Boolean(data.enabled);
          showToast('设置开机自启失败: ' + (data.error || '未知错误'), true);
        }
      } catch (e) {
        if (toggle) toggle.checked = Boolean(enabled);
        showToast('请求异常: ' + e, true);
      }
    }

    // 渲染「设置页」中的仓库源卡片
    function renderSettingsSources(sources) {
      const el = document.getElementById('settings-sources-list');
      if (!sources || sources.length === 0) {
        el.innerHTML = `
          <div class="py-12 text-center text-xs text-slate-400 bg-slate-50/50 rounded-2xl border border-dashed border-slate-200">
            暂无已配置的 Git 仓库源，请点击右上角「+ 添加仓库源」添加
          </div>
        `;
        return;
      }

      const intervalTextMap = {
        0: '仅手动更新',
        30: '每 30 分钟',
        60: '每 1 小时',
        360: '每 6 小时',
        720: '每 12 小时',
        1440: '每 24 小时'
      };

      el.innerHTML = sources.map(s => {
        const intervalVal = parseInt(s.auto_update_interval || 60);
        const intervalLabel = intervalTextMap[intervalVal] || `每 ${intervalVal} 分钟`;
        const lastUpdated = s.last_updated ? s.last_updated : '尚未更新';

        return `
          <div class="p-4 bg-slate-50/60 hover:bg-white border border-slate-200/80 hover:border-slate-300 rounded-2xl transition shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="min-w-0 flex-1 space-y-1.5">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-sm text-slate-900">${s.name || '未命名'}</span>
                <span class="text-[10px] px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-100 font-mono font-semibold">分支: ${s.branch || 'main'}</span>
                <span class="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 font-mono">子目录: ${s.sub_dir || '.'}</span>
                <span class="text-[10px] px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 font-mono font-medium">🕒 定时更新: ${intervalLabel}</span>
              </div>
              <div class="text-xs text-slate-400 font-mono truncate select-all" title="${s.git_url}">
                ${s.git_url}
              </div>
              <div class="text-[11px] text-slate-400 flex items-center gap-2">
                <span>上次拉取更新: <span class="text-slate-600 font-mono font-medium">${lastUpdated}</span></span>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0 self-end md:self-auto">
              <button onclick="pullSingleSource('${s.id}')" class="px-3 py-1.5 text-xs bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl font-medium transition shadow-2xs flex items-center gap-1 active:scale-98">
                <span>🔄</span> 更新
              </button>
              <button onclick="editSource('${s.id}')" class="px-3 py-1.5 text-xs bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl font-medium transition shadow-2xs flex items-center gap-1 active:scale-98">
                <span>✏️</span> 编辑
              </button>
              <button onclick="deleteSource('${s.id}')" class="px-3 py-1.5 text-xs bg-white hover:bg-rose-50 text-rose-600 border border-slate-200 rounded-xl font-medium transition shadow-2xs flex items-center gap-1 active:scale-98">
                <span>🗑️</span> 移除
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    function updateSourceFilterOptions(sources) {
      const select = document.getElementById('source-filter');
      const val = select.value;
      select.innerHTML = `<option value="all">所有仓库源 (${sources.length})</option>` + sources.map(s => `
        <option value="${s.id}">${s.name} [${s.branch}]</option>
      `).join('');
      if (Array.from(select.options).some(o => o.value === val)) {
        select.value = val;
      }
    }

    function updateTagOptions(skills) {
      const tagCounts = {};
      skills.forEach(s => {
        const t = s.tag || 'root';
        tagCounts[t] = (tagCounts[t] || 0) + 1;
      });

      const sortedTags = Object.keys(tagCounts).sort((a, b) => tagCounts[b] - tagCounts[a]);

      // 1. 下拉菜单
      const select = document.getElementById('tag-filter');
      const curVal = select.value;
      select.innerHTML = `<option value="all">所有 Tag 目录 (${skills.length})</option>` + sortedTags.map(t => `
        <option value="${t}">${t} (${tagCounts[t]})</option>
      `).join('');
      if (sortedTags.includes(curVal)) {
        select.value = curVal;
      } else {
        select.value = 'all';
        currentSelectedTag = 'all';
      }

      // 2. 快捷胶囊栏 (取前 15 个分类)
      const pillsContainer = document.getElementById('tag-pills-bar');
      const topTags = sortedTags.slice(0, 15);
      pillsContainer.innerHTML = `
        <span class="text-slate-400 mr-1 shrink-0 font-medium">快捷过滤:</span>
        <button onclick="selectTag('all')" class="px-2.5 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 ${currentSelectedTag === 'all' ? 'bg-indigo-600 text-white shadow-2xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
          全部 (${skills.length})
        </button>
      ` + topTags.map(t => `
        <button onclick="selectTag('${t}')" class="px-2.5 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 ${currentSelectedTag === t ? 'bg-indigo-600 text-white shadow-2xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
          ${t} <span class="opacity-75">(${tagCounts[t]})</span>
        </button>
      `).join('');
    }

    function onTagSelectChange() {
      currentSelectedTag = document.getElementById('tag-filter').value;
      updateTagPillsHighlight();
      filterSkills();
    }

    function selectTag(tag) {
      currentSelectedTag = tag;
      document.getElementById('tag-filter').value = tag;
      updateTagPillsHighlight();
      filterSkills();
    }

    function updateTagPillsHighlight() {
      document.querySelectorAll('#tag-pills-bar button').forEach(btn => {
        const text = btn.textContent.trim();
        if (currentSelectedTag === 'all' && text.startsWith('全部')) {
          btn.className = "px-2.5 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-indigo-600 text-white shadow-2xs";
        } else if (text.startsWith(currentSelectedTag + ' ') || text === currentSelectedTag) {
          btn.className = "px-2.5 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-indigo-600 text-white shadow-2xs";
        } else {
          btn.className = "px-2.5 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-slate-100 text-slate-600 hover:bg-slate-200";
        }
      });
    }

    function switchView(mode) {
      currentViewMode = mode;
      const btnFolder = document.getElementById('view-btn-folder');
      const btnGrid = document.getElementById('view-btn-grid');
      const breadcrumbNav = document.getElementById('breadcrumb-nav');

      if (mode === 'folder') {
        btnFolder.className = "px-3 py-1 rounded-lg text-xs font-semibold bg-white text-indigo-600 shadow-xs transition flex items-center gap-1";
        btnGrid.className = "px-3 py-1 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1";
        breadcrumbNav.classList.remove('hidden');
      } else {
        btnGrid.className = "px-3 py-1 rounded-lg text-xs font-semibold bg-white text-indigo-600 shadow-xs transition flex items-center gap-1";
        btnFolder.className = "px-3 py-1 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1";
        breadcrumbNav.classList.add('hidden');
      }
      filterSkills();
    }

    // 目录树下钻导航逻辑
    function navigateTo(path) {
      currentNavPath = path.trim().replace(/^\/+|\/+$/g, '');
      const searchBox = document.getElementById('search-box');
      if (searchBox.value) {
        searchBox.value = '';
        document.getElementById('btn-clear-search').classList.add('hidden');
      }
      filterSkills();
    }

    function navigateUp() {
      if (!currentNavPath) return;
      const parts = currentNavPath.split('/');
      parts.pop();
      navigateTo(parts.join('/'));
    }

    function renderBreadcrumbs(isSearchMode, searchKeyword) {
      const trail = document.getElementById('breadcrumb-trail');
      const backBtn = document.getElementById('btn-back-parent');
      const selectCurBtn = document.getElementById('btn-select-current-dir');

      const configCurFolderBtn = document.getElementById('btn-config-current-folder');

      if (isSearchMode) {
        backBtn.classList.remove('hidden');
        selectCurBtn.classList.add('hidden');
        if (configCurFolderBtn) configCurFolderBtn.classList.add('hidden');
        trail.innerHTML = `
          <span class="text-slate-400">🔍 全局搜索匹配:</span>
          <span class="font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md font-mono">"${searchKeyword}"</span>
          <button onclick="clearSearch()" class="text-slate-400 hover:text-slate-700 text-xs ml-2 underline">退出搜索</button>
        `;
        return;
      }

      if (!currentNavPath) {
        backBtn.classList.add('hidden');
        selectCurBtn.classList.add('hidden');
        if (configCurFolderBtn) configCurFolderBtn.classList.add('hidden');
        trail.innerHTML = `
          <span class="font-bold text-slate-900 flex items-center gap-1.5">
            <span>🏠</span> 根目录 (顶级分类目录)
          </span>
        `;
        return;
      }

      backBtn.classList.remove('hidden');
      selectCurBtn.classList.remove('hidden');
      if (configCurFolderBtn) configCurFolderBtn.classList.remove('hidden');

      const parts = currentNavPath.split('/');
      let html = `
        <button onclick="navigateTo('')" class="text-indigo-600 hover:underline flex items-center gap-1 font-semibold">
          <span>🏠</span> 根目录
        </button>
      `;

      let accum = '';
      parts.forEach((p, idx) => {
        accum = accum ? (accum + '/' + p) : p;
        const isLast = (idx === parts.length - 1);
        if (isLast) {
          html += `
            <span class="text-slate-300">/</span>
            <span class="font-bold text-slate-900 font-mono flex items-center gap-1">
              <span>📁</span> ${p}
            </span>
          `;
        } else {
          const pathTarget = accum;
          html += `
            <span class="text-slate-300">/</span>
            <button onclick="navigateTo('${pathTarget}')" class="text-indigo-600 hover:underline font-mono">
              ${p}
            </button>
          `;
        }
      });

      trail.innerHTML = html;
    }

    function clearSearch() {
      document.getElementById('search-box').value = '';
      document.getElementById('btn-clear-search').classList.add('hidden');
      filterSkills();
    }

    let selectedSkills = new Set();

    function updateSelectedCounter() {
      document.getElementById('selected-counter-badge').textContent = selectedSkills.size;
    }

    function toggleSkill(skillName, checked) {
      if (checked) {
        selectedSkills.add(skillName);
      } else {
        selectedSkills.delete(skillName);
      }
      updateSelectedCounter();
    }

    function selectAll(checked) {
      currentSkills.forEach(s => {
        if (checked) selectedSkills.add(s.name);
        else selectedSkills.delete(s.name);
      });
      filterSkills();
      updateSelectedCounter();
    }

    function selectCurrentDirSkills(checked) {
      const prefix = currentNavPath ? (currentNavPath + '/') : '';
      currentSkills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === currentNavPath || fp.startsWith(prefix)) {
          if (checked) selectedSkills.add(s.name);
          else selectedSkills.delete(s.name);
        }
      });
      filterSkills();
      updateSelectedCounter();
    }

    function selectSubFolderSkills(subPath, checked) {
      const prefix = subPath + '/';
      currentSkills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === subPath || fp.startsWith(prefix)) {
          if (checked) selectedSkills.add(s.name);
          else selectedSkills.delete(s.name);
        }
      });
      filterSkills();
      updateSelectedCounter();
    }

    async function loadSkills() {
      const res = await fetch('/api/skills');
      const data = await res.json();
      currentSkills = data.skills || [];
      
      // 首次加载或同步后，将所有已挂载的 skills 记录在 selectedSkills 集合中
      selectedSkills = new Set(currentSkills.filter(s => s.installed).map(s => s.name));
      
      updateTagOptions(currentSkills);
      filterSkills();
      updateSelectedCounter();
    }

    // 单张技能卡片 UI 渲染 (设计优化)
    function renderSingleSkillCard(s, showPathBadge = false) {
      const isChecked = selectedSkills.has(s.name);
      
      let pathBadgeText = '全局默认:';
      let pathBadgeStyle = 'text-slate-400';
      if (s.path_source_type === 'skill') {
        pathBadgeText = '技能专属:';
        pathBadgeStyle = 'text-indigo-600 font-semibold';
      } else if (s.path_source_type === 'folder') {
        pathBadgeText = `目录(${s.matched_folder}):`;
        pathBadgeStyle = 'text-amber-700 font-semibold';
      }

      return `
        <div class="skill-card bg-white p-4 rounded-2xl border ${s.installed ? 'border-indigo-300/80 bg-indigo-50/15' : 'border-slate-200/90'} shadow-xs hover:shadow-md transition-all relative flex flex-col justify-between" data-name="${s.name}" data-desc="${s.desc}" data-source="${s.source_id}">
          <div>
            <!-- Header Row -->
            <div class="flex items-start justify-between gap-2.5 mb-1.5">
              <span class="font-bold text-xs text-slate-900 truncate font-mono cursor-pointer hover:text-indigo-600 hover:underline flex items-center gap-1" onclick="openSkillDetailModal('${s.name}')" title="点击查看详情与文档内容">
                <span>${s.name}</span>
              </span>
              <div class="flex items-center gap-1.5 shrink-0">
                <button onclick="openSkillDetailModal('${s.name}')" class="text-[10px] text-slate-400 hover:text-indigo-600 px-1.5 py-0.5 rounded hover:bg-slate-100 transition" title="查看完整文档正文与参数说明">👁️ 详情</button>
                <span class="text-[10px] px-2 py-0.5 rounded-full font-semibold shrink-0 ${s.installed ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                  ${s.installed ? '✓ 已挂载' : '未挂载'}
                </span>
              </div>
            </div>

            <!-- Tags & Badges -->
            <div class="text-[11px] font-medium mb-2.5 flex items-center gap-1.5 flex-wrap">
              <span class="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-md text-[10px] font-mono border border-indigo-100">🏷️ ${s.source_name}</span>
              <button onclick="selectTag('${s.tag}')" class="bg-amber-50 hover:bg-amber-100 text-amber-800 px-2 py-0.5 rounded-md text-[10px] font-mono border border-amber-200 cursor-pointer transition" title="所属直接目录名: ${s.tag}">📂 ${s.tag}</button>
              ${showPathBadge && s.folder_path ? `<button onclick="navigateTo('${s.folder_path}')" class="bg-slate-100 hover:bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-mono transition" title="进入所在目录">📍 ${s.folder_path}</button>` : ''}
            </div>

            <!-- Description (点击也可展开详情) -->
            <p onclick="openSkillDetailModal('${s.name}')" class="text-xs text-slate-500 line-clamp-2 leading-relaxed mb-3 cursor-pointer hover:text-slate-700 transition" title="点击阅读完整文档内容">${s.desc}</p>
          </div>

          <div>
            <!-- Install Target Info -->
            <div class="p-2 bg-slate-50 rounded-xl border border-slate-100 text-[11px] text-slate-600 mb-3 flex items-center justify-between gap-2">
              <div class="truncate flex items-center gap-1" title="目标挂载路径: ${s.effective_install_to}">
                <span class="${pathBadgeStyle} shrink-0">${pathBadgeText}</span>
                <span class="font-mono text-[10px] text-slate-700 truncate">${s.effective_install_to}</span>
              </div>
              <button onclick="openPathModal('${s.name}')" class="text-indigo-600 hover:text-indigo-800 shrink-0 font-semibold hover:underline">修改</button>
            </div>

            <!-- Action Bar -->
            <div class="pt-2.5 border-t border-slate-100 flex items-center justify-between">
              <label class="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none font-medium">
                <input type="checkbox" onchange="toggleSkill('${s.name}', this.checked)" class="skill-checkbox rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-4 w-4 transition" value="${s.name}" ${isChecked ? 'checked' : ''}>
                <span>启用挂载</span>
              </label>
            </div>
          </div>
        </div>
      `;
    }

    function renderSkills(skills) {
      const container = document.getElementById('skills-container');
      const searchBox = document.getElementById('search-box');
      const q = searchBox.value.trim();
      const isSearching = Boolean(q);

      // 控制清除按钮显示
      document.getElementById('btn-clear-search').classList.toggle('hidden', !isSearching);

      renderBreadcrumbs(isSearching, q);

      document.getElementById('skill-count').textContent = `${skills.length} 个技能`;
      if (skills.length === 0) {
        container.innerHTML = `
          <div class="py-20 text-center text-slate-400 bg-white rounded-2xl border border-dashed border-slate-200">
            未发现符合条件的技能包
          </div>
        `;
        updateSelectedCounter();
        return;
      }

      // 全局平铺视图 或 全局搜索结果视图
      if (currentViewMode === 'grid' || isSearching) {
        container.innerHTML = `
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            ${skills.map(s => renderSingleSkillCard(s, isSearching)).join('')}
          </div>
        `;
        updateSelectedCounter();
        return;
      }

      // 文件树逐层下钻视图 (Folder Hierarchical Drill-down)
      const prefix = currentNavPath ? (currentNavPath + '/') : '';
      const subFolderMap = {};
      const directSkills = [];

      skills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === currentNavPath) {
          directSkills.push(s);
        } else if (fp.startsWith(prefix)) {
          const remainder = fp.substring(prefix.length);
          const firstSegment = remainder.split('/')[0];
          const fullChildPath = prefix + firstSegment;
          if (!subFolderMap[firstSegment]) {
            subFolderMap[firstSegment] = { name: firstSegment, fullPath: fullChildPath, totalSkills: 0, installedCount: 0 };
          }
          subFolderMap[firstSegment].totalSkills += 1;
          if (s.installed) subFolderMap[firstSegment].installedCount += 1;
        }
      });

      const subFolders = Object.values(subFolderMap).sort((a, b) => a.name.localeCompare(b.name));

      let contentHtml = '';

      // 1. 渲染当前层的子文件夹卡片 (点击进入下一级)
      if (subFolders.length > 0) {
        contentHtml += `
          <div>
            <div class="text-xs font-bold text-slate-700 mb-3 flex items-center justify-between">
              <span class="flex items-center gap-1.5">
                <span>📁 子文件夹</span>
                <span class="text-slate-400 font-normal">(${subFolders.length} 个，点击卡片进入下一级)</span>
              </span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3.5 mb-6">
              ${subFolders.map(f => {
                const folderOverride = (globalConfig.folder_overrides || {})[f.fullPath];
                return `
                <div onclick="navigateTo('${f.fullPath}')" class="bg-white hover:bg-indigo-50/40 p-4 rounded-2xl border ${folderOverride ? 'border-amber-300 bg-amber-50/15' : 'border-slate-200/90'} hover:border-indigo-300 shadow-2xs hover:shadow-xs transition cursor-pointer flex flex-col justify-between gap-3 group select-none">
                  <div class="flex items-start justify-between gap-2.5">
                    <div class="flex items-center gap-2.5 min-w-0">
                      <span class="text-3xl group-hover:scale-110 transition-transform shrink-0">📁</span>
                      <div class="min-w-0">
                        <div class="font-bold text-xs text-slate-900 group-hover:text-indigo-600 truncate font-mono">${f.name}</div>
                        <div class="text-[11px] text-slate-400 mt-0.5 truncate">
                          ${f.totalSkills} 个技能 ${f.installedCount > 0 ? `· <span class="text-emerald-600 font-medium">已挂载 ${f.installedCount}</span>` : ''}
                        </div>
                      </div>
                    </div>
                    <span class="text-slate-300 group-hover:text-indigo-500 font-bold text-sm shrink-0 transition">→</span>
                  </div>

                  <!-- 目录专属路径提示与操作 -->
                  <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-2 text-[10px]" onclick="event.stopPropagation()">
                    <button onclick="openFolderPathModal('${f.fullPath}')" class="text-indigo-600 hover:text-indigo-800 hover:underline truncate text-left font-medium" title="${folderOverride ? '已配置专属路径: ' + folderOverride : '点击配置本目录统一安装路径'}">
                      ${folderOverride ? `📍 目录专属: ${folderOverride}` : '⚙️ 设置本目录安装路径'}
                    </button>
                    <button onclick="selectSubFolderSkills('${f.fullPath}', true)" class="text-indigo-600 hover:bg-indigo-50 px-1.5 py-0.5 rounded font-semibold transition shrink-0">全选</button>
                  </div>
                </div>
              `}).join('')}
            </div>
          </div>
        `;
      }

      // 2. 渲染当前目录直属技能
      if (directSkills.length > 0) {
        contentHtml += `
          <div>
            <div class="text-xs font-bold text-slate-700 mb-3 flex items-center justify-between">
              <span class="flex items-center gap-1.5">
                <span>📦 本目录包含技能</span>
                <span class="text-slate-400 font-normal">(${directSkills.length} 个)</span>
              </span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              ${directSkills.map(s => renderSingleSkillCard(s, false)).join('')}
            </div>
          </div>
        `;
      }

      if (subFolders.length === 0 && directSkills.length === 0) {
        contentHtml = `
          <div class="py-20 text-center text-slate-400 bg-white rounded-2xl border border-dashed border-slate-200">
            该目录下暂无技能。点击上方「⬅ 返回上一级」返回。
          </div>
        `;
      }

      container.innerHTML = contentHtml;
      updateSelectedCounter();
    }

    function filterSkills() {
      const q = document.getElementById('search-box').value.toLowerCase().trim();
      const srcFilter = document.getElementById('source-filter').value;
      const tagFilter = currentSelectedTag;
      const statusFilter = (document.getElementById('status-filter') || {}).value || 'all';

      const filtered = currentSkills.filter(s => {
        const matchSearch = !q 
          || s.name.toLowerCase().includes(q) 
          || s.desc.toLowerCase().includes(q) 
          || (s.tag && s.tag.toLowerCase().includes(q))
          || (s.folder_path && s.folder_path.toLowerCase().includes(q));

        const matchSrc = (srcFilter === 'all') || (s.source_id === srcFilter);
        const matchTag = (tagFilter === 'all') || (s.tag === tagFilter);

        let matchStatus = true;
        if (statusFilter === 'installed') matchStatus = s.installed;
        else if (statusFilter === 'uninstalled') matchStatus = !s.installed;

        return matchSearch && matchSrc && matchTag && matchStatus;
      });
      renderSkills(filtered);
    }

    // Toast 浮动轻提示
    function showToast(msg, isError = false) {
      const t = document.getElementById('toast');
      const icon = document.getElementById('toast-icon');
      const text = document.getElementById('toast-msg');
      icon.textContent = isError ? '❌' : '✨';
      text.textContent = msg;
      t.className = `fixed bottom-6 right-6 z-50 px-4 py-3 text-xs font-medium rounded-2xl shadow-xl border flex items-center gap-2.5 transition-all ${isError ? 'bg-rose-900 border-rose-700 text-white' : 'bg-slate-900 border-slate-700 text-white'}`;
      t.classList.remove('hidden');
      setTimeout(() => { t.classList.add('hidden'); }, 3000);
    }

    // Save Default Install Path
    async function saveDefaultInstallPath() {
      const path = document.getElementById('cfg-default-install').value.trim();
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ default_install_to: path })
      });
      const data = await res.json();
      if (data.ok) {
        if (data.migrated > 0) {
          showToast(`默认目录已更新，并自动将 ${data.migrated} 个已安装技能迁移挂载至新目录！`);
        } else {
          showToast('全局默认安装路径已更新保存！');
        }
        await loadConfig();
        await loadSkills();
      }
    }

    // Source Modal Operations
    function openSourceModal(source = null) {
      document.getElementById('modal-src-id').value = source ? source.id : '';
      document.getElementById('modal-src-name').value = source ? source.name : '';
      document.getElementById('modal-src-url').value = source ? source.git_url : '';
      document.getElementById('modal-src-branch').value = source ? source.branch : 'main';
      document.getElementById('modal-src-subdir').value = source ? source.sub_dir : 'skills';
      document.getElementById('modal-src-interval').value = source ? (source.auto_update_interval ?? 60) : '60';
      document.getElementById('modal-title').textContent = source ? '编辑 Git 仓库源' : '添加 Git 仓库源';
      document.getElementById('source-modal').classList.remove('hidden');
    }

    function closeSourceModal() {
      document.getElementById('source-modal').classList.add('hidden');
    }

    function editSource(id) {
      const src = globalConfig.sources.find(s => s.id === id);
      if (src) openSourceModal(src);
    }

    async function saveSourceModal() {
      const id = document.getElementById('modal-src-id').value;
      const existing = globalConfig.sources.find(s => s.id === id) || {};
      const src = {
        ...existing,
        id: id || ('src-' + Date.now()),
        name: document.getElementById('modal-src-name').value.trim() || '未命名仓库',
        git_url: document.getElementById('modal-src-url').value.trim(),
        branch: document.getElementById('modal-src-branch').value.trim() || 'main',
        sub_dir: document.getElementById('modal-src-subdir').value.trim() || 'skills',
        auto_update_interval: parseInt(document.getElementById('modal-src-interval').value || 60)
      };
      if (!src.git_url) {
        alert('请填写 Git 仓库 URL');
        return;
      }
      closeSourceModal();
      showToast(`正在拉取仓库 [${src.name}] 分支 [${src.branch}]，请稍候...`);

      const res = await fetch('/api/sources/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(src)
      });
      const data = await res.json();
      if (data.ok) {
        showToast(`仓库 [${src.name}] 保存并拉取成功！`);
        await loadConfig();
        await loadSkills();
      } else {
        showToast('仓库拉取失败: ' + data.error, true);
      }
    }

    async function deleteSource(id) {
      if (!confirm('确定要移除此 Git 仓库源吗？')) return;
      await fetch('/api/sources/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id })
      });
      showToast('仓库源已移除。');
      await loadConfig();
      await loadSkills();
    }

    async function pullSingleSource(id) {
      showToast(`正在拉取更新...`);
      const res = await fetch('/api/pull', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id })
      });
      const data = await res.json();
      if (data.ok) {
        showToast('仓库拉取更新成功！');
        await loadConfig();
        await loadSkills();
      } else {
        showToast('更新失败: ' + data.error, true);
      }
    }

    async function pullAllSources() {
      showToast('正在批量更新所有 Git 仓库源...');
      const res = await fetch('/api/pull_all', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showToast('所有仓库源均已拉取至最新！');
        await loadConfig();
        await loadSkills();
      } else {
        showToast('拉取存在错误: ' + data.error, true);
      }
    }

    // Modal Operations for Custom Skill Path
    function openPathModal(skillName) {
      currentEditingSkill = skillName;
      const s = currentSkills.find(item => item.name === skillName);
      const currentCustomPath = s ? (s.custom_install_to || '') : '';
      document.getElementById('path-modal-skill-name').textContent = skillName;
      document.getElementById('path-modal-input').value = currentCustomPath;
      document.getElementById('path-modal').classList.remove('hidden');
    }

    function closePathModal() {
      document.getElementById('path-modal').classList.add('hidden');
    }

    async function saveSkillPathModal() {
      const customPath = document.getElementById('path-modal-input').value.trim();
      await fetch('/api/skill/set_path', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ skill_name: currentEditingSkill, install_to: customPath })
      });
      closePathModal();
      showToast(`技能 [${currentEditingSkill}] 专属安装路径已生效。`);
      await loadConfig();
      await loadSkills();
    }

    async function resetSkillPathToDefault() {
      document.getElementById('path-modal-input').value = '';
      await saveSkillPathModal();
    }

    // Modal Operations for Folder Path (目录级挂载)
    let currentEditingFolder = '';

    function openFolderPathModal(folderPath) {
      currentEditingFolder = folderPath.trim().replace(/^\/+|\/+$/g, '');
      const currentOverride = (globalConfig.folder_overrides || {})[currentEditingFolder] || '';
      document.getElementById('folder-modal-path-name').textContent = currentEditingFolder || '根目录';
      document.getElementById('folder-modal-input').value = currentOverride;
      document.getElementById('folder-path-modal').classList.remove('hidden');
    }

    function openCurrentFolderPathModal() {
      if (currentNavPath) {
        openFolderPathModal(currentNavPath);
      }
    }

    function closeFolderPathModal() {
      document.getElementById('folder-path-modal').classList.add('hidden');
    }

    async function saveFolderPathModal() {
      const customPath = document.getElementById('folder-modal-input').value.trim();
      const res = await fetch('/api/folder/set_path', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ folder_path: currentEditingFolder, install_to: customPath })
      });
      const data = await res.json();
      closeFolderPathModal();
      if (data.ok) {
        if (data.migrated > 0) {
          showToast(`目录 [${currentEditingFolder}] 路径已更新，并自动迁移了 ${data.migrated} 个已挂载技能！`);
        } else {
          showToast(`目录 [${currentEditingFolder}] 专属安装路径已生效。`);
        }
        await loadConfig();
        await loadSkills();
      }
    }

    async function resetFolderPathToDefault() {
      document.getElementById('folder-modal-input').value = '';
      await saveFolderPathModal();
    }

    // Modal Operations for Skill Detail & Content
    let currentDetailSkill = null;

    async function openSkillDetailModal(skillName) {
      const s = currentSkills.find(item => item.name === skillName);
      if (!s) return;
      currentDetailSkill = s;

      document.getElementById('detail-modal-title').textContent = s.name;
      document.getElementById('detail-modal-tag-badge').textContent = '📂 ' + s.tag;
      document.getElementById('detail-modal-source-badge').textContent = '🏷️ ' + s.source_name;
      document.getElementById('detail-modal-path-info').textContent = '目标挂载路径: ' + s.effective_install_to;
      document.getElementById('detail-modal-desc').textContent = s.desc || '(暂无功能描述)';

      const statusBadge = document.getElementById('detail-modal-status-badge');
      statusBadge.textContent = s.installed ? '✓ 已挂载' : '未挂载';
      statusBadge.className = s.installed ? 'text-[10px] px-2 py-0.5 rounded-full font-semibold bg-emerald-100 text-emerald-700' : 'text-[10px] px-2 py-0.5 rounded-full font-semibold bg-slate-100 text-slate-500';

      const contentBox = document.getElementById('detail-modal-content');
      const previewBox = document.getElementById('detail-modal-preview');
      contentBox.textContent = '正在加载 SKILL.md 文档正文...';
      previewBox.innerHTML = '<span class="text-slate-400">正在加载 SKILL.md 文档正文...</span>';
      switchDetailView('preview');
      document.getElementById('skill-detail-modal').classList.remove('hidden');

      updateDetailModalMountBtn();

      try {
        const res = await fetch(`/api/skill/detail?path=${encodeURIComponent(s.source_path)}`);
        const data = await res.json();
        if (data.ok) {
          contentBox.textContent = data.content;
          renderDetailMarkdown(data.content);
          if (data.desc) {
            document.getElementById('detail-modal-desc').textContent = data.desc;
          }
        } else {
          const msg = '读取文档失败: ' + (data.error || '未知错误');
          contentBox.textContent = msg;
          previewBox.innerHTML = `<span class="text-rose-500">${msg}</span>`;
        }
      } catch (e) {
        const msg = '网络请求异常: ' + e;
        contentBox.textContent = msg;
        previewBox.innerHTML = `<span class="text-rose-500">${msg}</span>`;
      }
    }

    function renderDetailMarkdown(md) {
      const previewBox = document.getElementById('detail-modal-preview');
      if (typeof marked === 'undefined') {
        previewBox.innerHTML = '<span class="text-rose-500">Markdown 解析库加载失败，请切换至源码查看。</span>';
        return;
      }
      // 剥离文件开头的 YAML frontmatter（--- name/description ---），预览只渲染正文
      const body = String(md || '').replace(/^\s*---\r?\n[\s\S]*?\r?\n---\s*\r?\n?/, '');
      let html = marked.parse(body);
      if (typeof DOMPurify !== 'undefined') {
        html = DOMPurify.sanitize(html);
      }
      previewBox.innerHTML = html;
    }

    function switchDetailView(mode) {
      const previewBox = document.getElementById('detail-modal-preview');
      const contentBox = document.getElementById('detail-modal-content');
      const btnPreview = document.getElementById('detail-view-btn-preview');
      const btnRaw = document.getElementById('detail-view-btn-raw');
      const activeCls = ['bg-white', 'text-indigo-700', 'shadow-xs'];
      const inactiveCls = ['text-slate-500'];
      if (mode === 'raw') {
        previewBox.classList.add('hidden');
        contentBox.classList.remove('hidden');
        btnRaw.classList.add(...activeCls);
        btnRaw.classList.remove(...inactiveCls);
        btnPreview.classList.remove(...activeCls);
        btnPreview.classList.add(...inactiveCls);
      } else {
        contentBox.classList.add('hidden');
        previewBox.classList.remove('hidden');
        btnPreview.classList.add(...activeCls);
        btnPreview.classList.remove(...inactiveCls);
        btnRaw.classList.remove(...activeCls);
        btnRaw.classList.add(...inactiveCls);
      }
    }

    function updateDetailModalMountBtn() {
      if (!currentDetailSkill) return;
      const isSelected = selectedSkills.has(currentDetailSkill.name);
      const btn = document.getElementById('detail-modal-toggle-mount-btn');
      if (isSelected) {
        btn.textContent = '✓ 已选入挂载 (点击取消)';
        btn.className = 'px-4 py-2 rounded-xl text-xs font-semibold shadow-xs transition flex items-center gap-1.5 bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100';
      } else {
        btn.textContent = '+ 加入挂载清单';
        btn.className = 'px-4 py-2 rounded-xl text-xs font-semibold shadow-xs transition flex items-center gap-1.5 bg-indigo-600 text-white hover:bg-indigo-700';
      }
    }

    function toggleDetailModalSkillMount() {
      if (!currentDetailSkill) return;
      const name = currentDetailSkill.name;
      if (selectedSkills.has(name)) {
        selectedSkills.delete(name);
      } else {
        selectedSkills.add(name);
      }
      updateDetailModalMountBtn();
      updateSelectedCounter();
      const cb = document.querySelector(`.skill-checkbox[value="${name}"]`);
      if (cb) cb.checked = selectedSkills.has(name);
    }

    function closeSkillDetailModal() {
      document.getElementById('skill-detail-modal').classList.add('hidden');
      currentDetailSkill = null;
    }

    function copySkillDetailContent() {
      const text = document.getElementById('detail-modal-content').textContent;
      navigator.clipboard.writeText(text).then(() => {
        showToast('SKILL.md 正文内容已复制到剪贴板！');
      }).catch(() => {
        showToast('复制失败，请手动选择复制', true);
      });
    }

    // Sync Selected
    async function syncSelected() {
      const selected = Array.from(selectedSkills);
      showToast('正在执行目录联结挂载同步...');
      const res = await fetch('/api/sync', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ selected })
      });
      const data = await res.json();
      if (data.ok) {
        showToast(`挂载同步完成！当前已成功启用 ${data.installed} 个技能。`);
        await loadSkills();
      } else {
        showToast('挂载同步失败: ' + data.error, true);
      }
    }

    init();
  </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif url.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(load_config()).encode("utf-8"))
        elif url.path == "/api/skills":
            cfg = load_config()
            skills = scan_all_skills(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"skills": skills}).encode("utf-8"))
        elif url.path == "/api/autostart":
            status = get_autostart_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": status, "platform": sys.platform}).encode("utf-8"))
        elif url.path == "/api/resolve":
            from urllib.parse import parse_qs
            params = parse_qs(url.query)
            name = params.get("name", [""])[0].strip()
            try:
                data_resp = {"ok": True, "result": resolve_skill(name)}
            except Exception as e:
                data_resp = {"ok": False, "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data_resp, ensure_ascii=False).encode("utf-8"))
        elif url.path == "/api/logs":
            lines = []
            if LOG_FILE.exists():
                try:
                    all_lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
                    lines = all_lines[-100:]
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"logs": lines}).encode("utf-8"))
        elif url.path == "/api/skill/detail":
            from urllib.parse import parse_qs
            params = parse_qs(url.query)
            target_path = params.get("path", [""])[0]
            p = Path(target_path)
            if p.exists() and p.is_dir():
                md_file = p / "SKILL.md" if (p / "SKILL.md").exists() else (p / "skill.md")
                raw_content = ""
                if md_file.exists():
                    raw_content = md_file.read_text(encoding="utf-8", errors="ignore")
                desc, tags = parse_skill_metadata(p)
                data_resp = {
                    "ok": True,
                    "name": p.name,
                    "desc": desc,
                    "tags": tags,
                    "content": raw_content or "(暂无文档正文内容)"
                }
            else:
                data_resp = {"ok": False, "error": "技能路径不存在"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data_resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        url = urlparse(self.path)
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len > 0 else b'{}'
        data = json.loads(body.decode("utf-8")) if body else {}

        if url.path == "/api/config":
            cfg = load_config()
            old_default = cfg.get("default_install_to", "").strip()
            new_default = data.get("default_install_to", "").strip()
            migrated_count = 0

            # 如果默认目录发生变更，执行已安装软链接的自动迁移重建
            if new_default and old_default and new_default != old_default and Path(old_default).exists():
                try:
                    old_path = Path(old_default).expanduser()
                    new_path = Path(new_default).expanduser()
                    new_path.mkdir(parents=True, exist_ok=True)
                    all_skills = scan_all_skills(cfg)
                    overrides = cfg.get("skill_overrides", {})

                    for s in all_skills:
                        name = s["name"]
                        # 仅迁移没有配置自定义专属路径的技能
                        if not overrides.get(name):
                            old_link = old_path / name
                            if old_link.exists():
                                # 1. 安全卸载旧软链接 (零闪屏)
                                safe_remove_link(old_link)
                                # 2. 在新目录下创建软链接 (原生系统调用零弹窗)
                                new_link = new_path / name
                                source_p = Path(s["source_path"])
                                safe_create_link(source_p, new_link)
                                migrated_count += 1
                except Exception as e:
                    print(f"[!] 迁移软链接异常: {e}", flush=True)

            if "default_install_to" in data:
                cfg["default_install_to"] = new_default
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "migrated": migrated_count}).encode("utf-8"))

        elif url.path == "/api/sources/save":
            cfg = load_config()
            src_id = data.get("id")
            sources = cfg.get("sources", [])

            found = False
            for i, s in enumerate(sources):
                if s["id"] == src_id:
                    sources[i] = data
                    found = True
                    break
            if not found:
                sources.append(data)
            cfg["sources"] = sources
            save_config(cfg)

            try:
                pull_single_source(data)
                # 拉取成功后将最新的 last_updated 和 last_pulled_ts 持久化写入配置
                for i, s in enumerate(sources):
                    if s["id"] == src_id:
                        sources[i] = data
                        break
                cfg["sources"] = sources
                save_config(cfg)
                log(f"[Repo] 仓库源 [{data.get('name')}] 配置保存并首次拉取完成")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "last_updated": data.get("last_updated")}).encode("utf-8"))
            except Exception as e:
                log(f"仓库源首次拉取失败: {e}", level="ERROR")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

        elif url.path == "/api/sources/delete":
            cfg = load_config()
            src_id = data.get("id")
            cfg["sources"] = [s for s in cfg.get("sources", []) if s["id"] != src_id]
            save_config(cfg)
            cache_dir = CACHE_BASE_DIR / src_id
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        elif url.path == "/api/pull":
            cfg = load_config()
            src_id = data.get("id")
            target_src = next((s for s in cfg.get("sources", []) if s["id"] == src_id), None)
            if not target_src:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "未找到指定仓库源"}).encode("utf-8"))
                return
            try:
                pull_single_source(target_src)
                save_config(cfg) # 关键：持久化写入 last_updated 与 last_pulled_ts！
                log(f"[Pull] 仓库 [{target_src.get('name')}] 手动拉取更新成功 (时间: {target_src.get('last_updated')})")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "last_updated": target_src.get("last_updated")}).encode("utf-8"))
            except Exception as e:
                log(f"仓库拉取更新失败: {e}", level="ERROR")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

        elif url.path == "/api/pull_all":
            cfg = load_config()
            sources = cfg.get("sources", [])
            errors = []
            for s in sources:
                try:
                    pull_single_source(s)
                except Exception as e:
                    errors.append(f"[{s.get('name')}] {e}")
            save_config(cfg) # 关键：全量更新后持久化写入所有仓库的更新时间！
            log(f"[PullAll] 全量仓库源拉取更新完成")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if errors:
                self.wfile.write(json.dumps({"ok": False, "error": "部分拉取失败: " + "; ".join(errors)}).encode("utf-8"))
            else:
                self.wfile.write(b'{"ok": true}')

        elif url.path == "/api/skill/set_path":
            cfg = load_config()
            skill_name = data.get("skill_name")
            custom_path = data.get("install_to", "").strip()
            overrides = cfg.get("skill_overrides", {})
            if custom_path:
                overrides[skill_name] = custom_path
            else:
                overrides.pop(skill_name, None)
            cfg["skill_overrides"] = overrides
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        elif url.path == "/api/folder/set_path":
            cfg = load_config()
            folder_path = data.get("folder_path", "").strip().strip("/\\")
            custom_path = data.get("install_to", "").strip()
            folder_overrides = cfg.get("folder_overrides", {})
            old_custom_path = folder_overrides.get(folder_path, "").strip()
            migrated_count = 0

            # 如果目录专属路径改变，自动平滑迁移受影响的已挂载技能
            if old_custom_path != custom_path:
                try:
                    before_skills = scan_all_skills(cfg)
                    if custom_path:
                        folder_overrides[folder_path] = custom_path
                    else:
                        folder_overrides.pop(folder_path, None)
                    cfg["folder_overrides"] = folder_overrides

                    after_skills = scan_all_skills(cfg)
                    after_map = {s["name"]: s for s in after_skills}
                    prefix = (folder_path + "/") if folder_path else ""

                    for s_b in before_skills:
                        name = s_b["name"]
                        fp = s_b.get("folder_path", "")
                        if (fp == folder_path or fp.startswith(prefix)) and not s_b["custom_install_to"]:
                            old_target = Path(s_b["effective_install_to"]) / name
                            s_a = after_map.get(name)
                            if s_a:
                                new_target = Path(s_a["effective_install_to"]) / name
                                if old_target.exists() and old_target != new_target:
                                    safe_remove_link(old_target)
                                    src_p = Path(s_b["source_path"])
                                    safe_create_link(src_p, new_target)
                                    migrated_count += 1
                except Exception as e:
                    print(f"[!] 目录挂载迁移异常: {e}", flush=True)

            if custom_path:
                folder_overrides[folder_path] = custom_path
            else:
                folder_overrides.pop(folder_path, None)
            cfg["folder_overrides"] = folder_overrides
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "migrated": migrated_count}).encode("utf-8"))

        elif url.path == "/api/commit":
            name = (data.get("name") or "").strip()
            message = (data.get("message") or "").strip()
            push = bool(data.get("push", True))
            try:
                if not name:
                    raise ValueError("缺少技能名称参数 name")
                info = resolve_skill(name)
                if not info["git_managed"]:
                    raise ValueError(f"技能 [{name}] 未被 Git 管理，无法提交")
                if not info["sub_dir"]:
                    raise ValueError(f"技能 [{name}] 的相对路径解析失败，拒绝提交以防误伤其他文件")

                repo_dir = info["git_dir"]
                branch = info["git_branch"]
                pathspec = info["sub_dir"]
                # 白名单提交：仅 add 该技能目录，绝不 git add -A
                git_cmd(["add", "--", pathspec], cwd=repo_dir)
                status = git_cmd(["status", "--porcelain", "--", pathspec], cwd=repo_dir)
                if not status.strip():
                    payload = {"ok": True, "committed": False, "reason": "该技能目录没有变更，已跳过提交"}
                else:
                    git_cmd(["commit", "-m", message or f"chore(skill): update {name}"], cwd=repo_dir)
                    committed_hash = git_cmd(["rev-parse", "--short", "HEAD"], cwd=repo_dir)
                    payload = {"ok": True, "committed": True, "hash": committed_hash, "branch": branch}
                    if push:
                        git_cmd(["push", "origin", branch], cwd=repo_dir)
                        payload["pushed"] = True
                    log(f"[Commit] 技能 [{name}] 已提交 {committed_hash} 到 {branch}")
            except Exception as e:
                payload = {"ok": False, "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        elif url.path == "/api/autostart":
            enable = bool(data.get("enabled", False))
            try:
                res = set_autostart(enable)
                # 回读注册表二次校验，确保状态真正落盘
                actual = get_autostart_status()
                if actual != enable:
                    raise RuntimeError("注册表写入后校验不一致")
                payload = {"ok": True, "enabled": actual}
            except Exception as e:
                payload = {"ok": False, "enabled": get_autostart_status(), "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        elif url.path == "/api/sync":
            cfg = load_config()
            selected = set(data.get("selected", []))
            all_skills = scan_all_skills(cfg)
            default_dir = Path(cfg.get("default_install_to", "")).expanduser()

            # 内置技能不属于任何用户仓库，不受勾选集合影响，挂载前先确保其存在
            try:
                install_builtin_skills(cfg)
            except Exception as e:
                log(f"内置技能挂载异常: {e}", level="ERROR")

            # 汇总该项目涉及的所有潜在安装目录，以便在路径变更或取消挂载时彻底安全解绑
            all_possible_target_dirs = {default_dir}
            for fo_val in cfg.get("folder_overrides", {}).values():
                if fo_val.strip():
                    all_possible_target_dirs.add(Path(fo_val.strip()).expanduser())
            for so_val in cfg.get("skill_overrides", {}).values():
                if so_val.strip():
                    all_possible_target_dirs.add(Path(so_val.strip()).expanduser())

            # ===== 安全阀：防止误传精简勾选集合导致批量解绑 =====
            # 统计当前实际已挂载的技能数（排除内置技能）
            builtin_names = {b["name"] for b in scan_builtin_skills()}
            currently_mounted = 0
            for s in all_skills:
                name = s["name"]
                if name in builtin_names:
                    continue
                eff = Path(s["effective_install_to"]).expanduser() / name
                if eff.exists():
                    currently_mounted += 1
            allow_shrink = bool(data.get("allow_shrink", False))
            # 当现有挂载 >= 5 且本次勾选会导致挂载数缩减过半时，拒绝执行（除非显式 allow_shrink）
            if (not allow_shrink and currently_mounted >= 5
                    and len(selected & {s["name"] for s in all_skills}) < currently_mounted / 2):
                payload = {
                    "ok": False,
                    "error": (f"安全阀拦截：当前已挂载 {currently_mounted} 个技能，"
                              f"本次仅勾选 {len(selected)} 个，将导致大批量解绑。"
                              f"如确需如此，请传 allow_shrink=true。")
                }
                log(f"[Safety] 已拦截疑似误操作的批量解绑：已挂载 {currently_mounted}，勾选 {len(selected)}", level="ERROR")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return

            try:
                installed_count = 0
                for s in all_skills:
                    name = s["name"]
                    source_path = Path(s["source_path"])
                    # 精准使用继承自目录或单技能计算出的 effective_install_to！
                    effective_dir = Path(s["effective_install_to"]).expanduser()
                    target_link = effective_dir / name

                    if name in selected:
                        # 1. 如果该技能安装在专有目录（如 infra），清理全局默认目录或历史目录中的旧软链接残留
                        for old_d in all_possible_target_dirs:
                            if old_d != effective_dir:
                                old_link = old_d / name
                                if old_link.exists():
                                    safe_remove_link(old_link)
                                    log(f"[Clean] 清理旧挂载链接: {old_link}")

                        # 2. 挂载到当前精准生效目录 (原生系统调用零弹窗零闪屏)
                        effective_dir.mkdir(parents=True, exist_ok=True)
                        if not target_link.exists():
                            safe_create_link(source_path, target_link)
                            log(f"[Mount] 成功挂载技能: {name} -> {target_link}")
                        installed_count += 1
                    else:
                        # 取消挂载：从所有可能目录中彻底解绑
                        for d in all_possible_target_dirs:
                            al = d / name
                            if al.exists():
                                safe_remove_link(al)
                                log(f"[Unmount] 解除挂载技能: {name} 从 {al}")

                # 内置技能永不受勾选集合影响，卸载循环结束后兜底补挂
                install_builtin_skills(cfg)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "installed": installed_count}).encode("utf-8"))
            except Exception as e:
                log(f"同步挂载异常: {e}", level="ERROR")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

PID_FILE = BASE_DIR / ".skillbox.pid"

def main():
    base_port = 7860
    max_port = 7880
    server = None
    actual_port = base_port

    for port in range(base_port, max_port):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), RequestHandler)
            actual_port = port
            break
        except OSError:
            continue

    if not server:
        print(f"[!] 无法启动服务：端口 {base_port}~{max_port} 均被占用。", flush=True)
        sys.exit(1)

    url = f"http://127.0.0.1:{actual_port}"
    print(f"[*] SkillBox 服务已成功启动: {url}", flush=True)
    print(f"[*] 提示：按 Ctrl+C 可停止服务。", flush=True)

    # 写入当前进程 PID 和实际监听端口
    try:
        PID_FILE.write_text(f"{os.getpid()}:{actual_port}", encoding="utf-8")
    except Exception:
        pass

    # 启动定时自动更新后台守护线程
    threading.Thread(target=auto_update_scheduler, daemon=True).start()

    # 内置技能默认挂载（跟随工具版本，不依赖用户勾选与 Git 仓库）
    try:
        install_builtin_skills()
    except Exception as e:
        print(f"[!] 内置技能挂载异常: {e}", flush=True)

    # 确保 skillbox 命令已注册到用户 PATH（未安装则自动安装）
    try:
        ensure_cli_installed()
    except Exception as e:
        print(f"[!] 命令注册异常: {e}", flush=True)

    is_silent = "--silent" in sys.argv or "--no-browser" in sys.argv
    if not is_silent:
        def delayed_open():
            time.sleep(0.6)
            webbrowser.open(url)
        threading.Thread(target=delayed_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] SkillBox 服务已安全退出。", flush=True)
    finally:
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass

if __name__ == "__main__":
    main()
