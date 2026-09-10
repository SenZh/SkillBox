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

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "git_url": "",
    "branch": "main",
    "sub_dir": "skills",
    "install_to": str(Path.home() / ".agents" / "skills"),
    "cache_dir": str(BASE_DIR / ".skillbox_cache")
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def git_cmd(args, cwd=None):
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )
    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(err or f"Git command failed: {' '.join(args)}")
    return res.stdout.strip()

def parse_skill_desc(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        skill_md = skill_dir / "skill.md"
    if not skill_md.exists():
        return "无描述"
    try:
        content = skill_md.read_text(encoding="utf-8", errors="ignore")
        in_frontmatter = False
        desc = ""
        for line in content.splitlines():
            line_s = line.strip()
            if line_s == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter and line_s.startswith("description:"):
                desc = line_s.split("description:", 1)[1].strip().strip('"').strip("'")
                break
        if not desc:
            for line in content.splitlines():
                l = line.strip()
                if l and not l.startswith("#") and not l.startswith("---"):
                    desc = l[:120] + ("..." if len(l) > 120 else "")
                    break
        return desc or "无描述"
    except Exception:
        return "无法读取描述"

def scan_skills(cfg):
    cache = Path(cfg["cache_dir"])
    sub_name = cfg.get("sub_dir", "").strip().strip("/\\")
    sub_dir = (cache / sub_name) if sub_name and sub_name != "." else cache
    if not sub_dir.exists():
        return []

    install_to = Path(cfg["install_to"]).expanduser()
    installed = set()
    if install_to.exists():
        for p in install_to.iterdir():
            if p.is_dir() or p.is_symlink():
                installed.add(p.name)

    results = []
    for item in sorted(sub_dir.iterdir()):
        if item.is_dir() and ((item / "SKILL.md").exists() or (item / "skill.md").exists()):
            results.append({
                "name": item.name,
                "desc": parse_skill_desc(item),
                "installed": item.name in installed
            })
    return results

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SkillBox - AI 技能管理器</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen">
  <div class="max-w-6xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8 pb-4 border-b border-slate-200">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <span>📦</span> SkillBox
        </h1>
        <p class="text-sm text-slate-500 mt-1">支持自定义 Git 仓库与分支 · 符号链接秒级同步 · 自动更新</p>
      </div>
      <div class="flex items-center gap-3">
        <button id="btn-pull" onclick="pullRepo()" class="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-medium rounded-lg transition border border-indigo-200 flex items-center gap-1.5 shadow-sm">
          <span>🔄</span> 拉取/更新分支
        </button>
        <button id="btn-sync" onclick="syncSelected()" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg shadow-sm transition flex items-center gap-1.5">
          <span>⚡</span> 应用同步
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left: Settings -->
      <div class="lg:col-span-1 bg-white p-6 rounded-xl border border-slate-200 shadow-sm h-fit">
        <h2 class="text-base font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100 flex items-center justify-between">
          <span>⚙️ 仓库配置</span>
          <span id="current-branch-tag" class="text-xs font-normal text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100">分支未指定</span>
        </h2>
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Git 仓库地址 (HTTP/SSH)</label>
            <input id="cfg-git-url" type="text" placeholder="如: git@gitlab.com:org/skills.git" class="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Git 分支 (Branch)</label>
            <input id="cfg-branch" type="text" placeholder="如: main、dev、feature/v1" class="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">仓库内 Skill 子目录 (Subdirectory)</label>
            <input id="cfg-sub-dir" type="text" placeholder="如: skills 或 . (根目录)" class="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">目标安装目录 (Install To)</label>
            <input id="cfg-install-to" type="text" placeholder="如: ~/.agents/skills" class="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
          <button onclick="saveConfigAndRefresh()" class="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white text-xs font-medium rounded-md transition shadow-sm">
            保存当前配置
          </button>
        </div>
        <div id="status-box" class="mt-4 p-3 bg-slate-50 border border-slate-200 rounded-md text-xs text-slate-600 hidden break-words leading-relaxed"></div>
      </div>

      <!-- Right: Skills List -->
      <div class="lg:col-span-2">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-2">
            <input id="search-box" oninput="filterSkills()" type="text" placeholder="搜索技能名称或描述..." class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg w-64 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <span id="skill-count" class="text-xs text-slate-500">共 0 个技能</span>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <button onclick="selectAll(true)" class="text-indigo-600 hover:underline">全选</button>
            <span class="text-slate-300">|</span>
            <button onclick="selectAll(false)" class="text-indigo-600 hover:underline">清空</button>
          </div>
        </div>

        <div id="skills-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="col-span-2 py-16 text-center text-slate-400 bg-white rounded-xl border border-dashed border-slate-300">
            请先配置 Git 仓库及分支，并点击右上角「拉取/更新分支」
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentSkills = [];

    async function init() {
      const res = await fetch('/api/config');
      const cfg = await res.json();
      document.getElementById('cfg-git-url').value = cfg.git_url || '';
      document.getElementById('cfg-branch').value = cfg.branch || 'main';
      document.getElementById('cfg-sub-dir').value = cfg.sub_dir || 'skills';
      document.getElementById('cfg-install-to').value = cfg.install_to || '';
      updateBranchTag(cfg.branch);
      loadSkills();
    }

    function updateBranchTag(branch) {
      const tag = document.getElementById('current-branch-tag');
      if (branch) {
        tag.textContent = '分支: ' + branch;
      } else {
        tag.textContent = '分支未指定';
      }
    }

    async function loadSkills() {
      const res = await fetch('/api/skills');
      const data = await res.json();
      currentSkills = data.skills || [];
      renderSkills(currentSkills);
    }

    function renderSkills(skills) {
      const grid = document.getElementById('skills-grid');
      document.getElementById('skill-count').textContent = `共 ${skills.length} 个技能`;
      if (skills.length === 0) {
        grid.innerHTML = `<div class="col-span-2 py-16 text-center text-slate-400 bg-white rounded-xl border border-dashed border-slate-300">未扫描到包含 SKILL.md 的技能目录</div>`;
        return;
      }
      grid.innerHTML = skills.map(s => `
        <div class="skill-card bg-white p-4 rounded-xl border ${s.installed ? 'border-indigo-300 bg-indigo-50/20' : 'border-slate-200'} shadow-sm hover:shadow transition relative flex flex-col justify-between" data-name="${s.name}" data-desc="${s.desc}">
          <div>
            <div class="flex items-start justify-between gap-2 mb-2">
              <span class="font-semibold text-sm text-slate-900 truncate" title="${s.name}">${s.name}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0 ${s.installed ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                ${s.installed ? '已安装' : '未安装'}
              </span>
            </div>
            <p class="text-xs text-slate-500 line-clamp-3 leading-relaxed" title="${s.desc}">${s.desc}</p>
          </div>
          <div class="mt-4 pt-2 border-t border-slate-100 flex items-center justify-between">
            <label class="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
              <input type="checkbox" class="skill-checkbox rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-4 w-4" value="${s.name}" ${s.installed ? 'checked' : ''}>
              <span>启用并挂载</span>
            </label>
          </div>
        </div>
      `).join('');
    }

    function filterSkills() {
      const q = document.getElementById('search-box').value.toLowerCase();
      const filtered = currentSkills.filter(s => s.name.toLowerCase().includes(q) || s.desc.toLowerCase().includes(q));
      renderSkills(filtered);
    }

    function selectAll(checked) {
      document.querySelectorAll('.skill-checkbox').forEach(cb => cb.checked = checked);
    }

    function showStatus(msg, isError = false) {
      const box = document.getElementById('status-box');
      box.textContent = msg;
      box.className = `mt-4 p-3 rounded-md text-xs ${isError ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'}`;
      box.classList.remove('hidden');
    }

    async function saveConfigAndRefresh() {
      const cfg = {
        git_url: document.getElementById('cfg-git-url').value.trim(),
        branch: document.getElementById('cfg-branch').value.trim(),
        sub_dir: document.getElementById('cfg-sub-dir').value.trim(),
        install_to: document.getElementById('cfg-install-to').value.trim()
      };
      await fetch('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cfg) });
      updateBranchTag(cfg.branch);
      showStatus('配置已保存！');
    }

    async function pullRepo() {
      await saveConfigAndRefresh();
      showStatus('正在拉取/更新远程仓库指定分支，请稍候...');
      const res = await fetch('/api/pull', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showStatus('仓库分支拉取成功！已刷新技能列表。');
        loadSkills();
      } else {
        showStatus('拉取失败: ' + data.error, true);
      }
    }

    async function syncSelected() {
      const selected = Array.from(document.querySelectorAll('.skill-checkbox:checked')).map(c => c.value);
      showStatus('正在应用符号链接同步...');
      const res = await fetch('/api/sync', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ selected })
      });
      const data = await res.json();
      if (data.ok) {
        showStatus(`同步完成！当前安装目录已启用 ${data.installed} 个技能。`);
        loadSkills();
      } else {
        showStatus('同步失败: ' + data.error, true);
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
            skills = scan_skills(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"skills": skills}).encode("utf-8"))
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
            cfg.update(data)
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        elif url.path == "/api/pull":
            cfg = load_config()
            cache = Path(cfg["cache_dir"])
            git_url = cfg.get("git_url", "").strip()
            branch = cfg.get("branch", "main").strip()

            if not git_url:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "请先配置 Git 仓库地址"}).encode("utf-8"))
                return

            try:
                if not cache.exists() or not (cache / ".git").exists():
                    if cache.exists():
                        shutil.rmtree(cache)
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cmd = ["clone"]
                    if branch:
                        cmd += ["-b", branch]
                    cmd += ["--depth", "1", git_url, str(cache)]
                    git_cmd(cmd)
                else:
                    git_cmd(["fetch", "origin", branch], cwd=cache)
                    git_cmd(["checkout", branch], cwd=cache)
                    git_cmd(["pull", "origin", branch], cwd=cache)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

        elif url.path == "/api/sync":
            cfg = load_config()
            selected = set(data.get("selected", []))
            cache = Path(cfg["cache_dir"])
            sub_name = cfg.get("sub_dir", "").strip().strip("/\\")
            sub_dir = (cache / sub_name) if sub_name and sub_name != "." else cache
            install_to = Path(cfg["install_to"]).expanduser()
            install_to.mkdir(parents=True, exist_ok=True)

            try:
                available = {item.name: item for item in sub_dir.iterdir() if item.is_dir()} if sub_dir.exists() else {}
                existing = {p.name: p for p in install_to.iterdir() if p.is_dir() or p.is_symlink()}

                # 卸载未勾选的
                for name, path in existing.items():
                    if name in available and name not in selected:
                        if path.is_symlink():
                            path.unlink()
                        elif path.is_dir():
                            if sys.platform == "win32":
                                subprocess.run(["cmd", "/c", "rmdir", str(path)], check=True)
                            else:
                                shutil.rmtree(path)

                # 挂载勾选的
                installed_count = 0
                for name in selected:
                    if name in available:
                        target = install_to / name
                        source = available[name]
                        if not target.exists():
                            if sys.platform == "win32":
                                subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(source)], check=True, stdout=subprocess.DEVNULL)
                            else:
                                target.symlink_to(source)
                        installed_count += 1

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "installed": installed_count}).encode("utf-8"))
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

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

    def delayed_open():
        time.sleep(0.6)
        webbrowser.open(url)

    threading.Thread(target=delayed_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] SkillBox 服务已安全退出。", flush=True)

if __name__ == "__main__":
    main()
