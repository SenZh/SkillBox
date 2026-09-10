import os
import sys
import json
import time
import uuid
import shutil
import threading
import subprocess
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
CACHE_BASE_DIR = BASE_DIR / ".skillbox_cache"

DEFAULT_CONFIG = {
    "default_install_to": str(Path.home() / ".agents" / "skills"),
    "sources": [],
    "skill_overrides": {}  # { "skill_name": "custom/path" }
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                # 兼容旧配置
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
    if "skill_overrides" not in cfg or not isinstance(cfg["skill_overrides"], dict):
        cfg["skill_overrides"] = {}
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

def scan_all_skills(cfg):
    sources = cfg.get("sources", [])
    default_install_to = Path(cfg.get("default_install_to", "")).expanduser()
    overrides = cfg.get("skill_overrides", {})

    all_skills = []

    for src in sources:
        src_id = src["id"]
        src_name = src.get("name", "未命名仓库")
        cache_dir = CACHE_BASE_DIR / src_id
        sub_name = src.get("sub_dir", "").strip().strip("/\\")
        sub_dir = (cache_dir / sub_name) if sub_name and sub_name != "." else cache_dir

        if not sub_dir.exists():
            continue

        # 深度递归扫描所有包含 SKILL.md 或 skill.md 的目录
        for root, dirs, files in os.walk(sub_dir):
            # 过滤掉隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            p_root = Path(root)
            if (p_root / "SKILL.md").exists() or (p_root / "skill.md").exists():
                skill_name = p_root.name
                rel_path = p_root.relative_to(sub_dir)
                
                # 按照用户要求：tag 按照 skill 所属目录名计算 (例如 A/B/C 下，tag=C)
                tag = p_root.parent.name if p_root.parent != sub_dir and p_root.parent.name else (sub_dir.name or "root")
                folder_path = str(rel_path.parent).replace("\\", "/") if str(rel_path.parent) != "." else ""
                desc, file_tags = parse_skill_metadata(p_root)

                custom_path = overrides.get(skill_name, "").strip()
                target_install_dir = Path(custom_path).expanduser() if custom_path else default_install_to
                target_path = target_install_dir / skill_name
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
                    "custom_install_to": custom_path,
                    "effective_install_to": str(target_install_dir),
                    "is_custom": bool(custom_path),
                    "installed": installed
                })

    return all_skills

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SkillBox - AI 技能管理器</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .modal-backdrop { background: rgba(15, 23, 42, 0.4); backdrop-filter: blur(2px); }
  </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen">
  <div class="max-w-7xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8 pb-4 border-b border-slate-200">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <span>📦</span> SkillBox
        </h1>
        <p class="text-sm text-slate-500 mt-1">多 Git 仓库与独立分支 · 默认/专属自定义路径 · 目录联结秒级挂载</p>
      </div>
      <div class="flex items-center gap-3">
        <button onclick="pullAllSources()" class="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-medium rounded-lg transition border border-indigo-200 flex items-center gap-1.5 shadow-sm">
          <span>🔄</span> 全部拉取/更新
        </button>
        <button onclick="syncSelected()" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg shadow-sm transition flex items-center gap-1.5">
          <span>⚡</span> 应用同步
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <!-- Left Column: Config & Sources -->
      <div class="lg:col-span-4 space-y-6 min-w-0">
        <!-- 1. Default Install Path Card -->
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <h2 class="text-sm font-semibold text-slate-900 mb-3 flex items-center justify-between">
            <span>📁 全局默认安装目录</span>
            <span class="text-[10px] text-slate-400 font-normal">未单独配置的 Skill 均装在此处</span>
          </h2>
          <div class="space-y-3">
            <input id="cfg-default-install" type="text" placeholder="如: C:\\Users\\...\\.agents\\skills" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <button onclick="saveDefaultInstallPath()" class="w-full py-1.5 bg-slate-800 hover:bg-slate-900 text-white text-xs font-medium rounded-md transition shadow-sm">
              保存默认路径
            </button>
          </div>
        </div>

        <!-- 2. Git Sources Management -->
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm min-w-0">
          <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
            <h2 class="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <span>🌿 Git 仓库源列表</span>
              <span id="sources-count" class="text-xs text-slate-400 font-normal">(0)</span>
            </h2>
            <button onclick="openSourceModal()" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-md shadow-sm transition flex items-center gap-1">
              <span>+</span> 添加仓库
            </button>
          </div>

          <div id="sources-list" class="space-y-2.5 min-w-0">
            <div class="py-8 text-center text-xs text-slate-400">暂无 Git 仓库，请点击上方按钮添加</div>
          </div>
        </div>

        <div id="status-box" class="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 hidden break-words leading-relaxed"></div>
      </div>

      <!-- Right Column: Skills Explorer -->
      <div class="lg:col-span-8 min-w-0">
        <!-- Top Toolbar -->
        <div class="space-y-3 mb-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex items-center gap-2 flex-wrap min-w-0">
              <input id="search-box" oninput="filterSkills()" type="text" placeholder="搜索技能名称、简介、标签..." class="px-3 py-1.5 text-xs border border-slate-300 rounded-lg w-44 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <select id="source-filter" onchange="filterSkills()" class="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="all">所有仓库源</option>
              </select>
              <select id="tag-filter" onchange="onTagSelectChange()" class="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="all">所有 Tag / 所属目录</option>
              </select>
              <span id="skill-count" class="text-xs text-slate-500 shrink-0">共 0 个技能</span>
            </div>

            <!-- View Switcher & Actions -->
            <div class="flex items-center gap-2 text-xs shrink-0">
              <!-- 视图切换 -->
              <div class="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-2xs">
                <button id="view-btn-folder" onclick="switchView('folder')" class="px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 text-white shadow-2xs transition flex items-center gap-1">
                  <span>📁</span> 目录树浏览
                </button>
                <button id="view-btn-grid" onclick="switchView('grid')" class="px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1">
                  <span>▦</span> 平铺所有
                </button>
              </div>
              <span class="text-slate-300">|</span>
              <button onclick="selectAll(true)" class="text-indigo-600 hover:underline">全选</button>
              <span class="text-slate-300">|</span>
              <button onclick="selectAll(false)" class="text-indigo-600 hover:underline">清空</button>
            </div>
          </div>

          <!-- Tag Pills 快捷标签过滤栏 -->
          <div id="tag-pills-bar" class="flex items-center gap-1.5 flex-wrap text-[11px] pt-1 border-t border-slate-100">
            <!-- 动态填充 -->
          </div>
        </div>

        <!-- Breadcrumb Navigation Bar (像文件管理器一样逐层进入) -->
        <div id="breadcrumb-nav" class="flex items-center justify-between gap-2 p-2.5 bg-white rounded-xl border border-slate-200 shadow-2xs mb-4 min-w-0">
          <div class="flex items-center gap-1.5 text-xs flex-wrap min-w-0" id="breadcrumb-trail">
            <!-- 动态面包屑 -->
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button id="btn-back-parent" onclick="navigateUp()" class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-xs font-medium transition flex items-center gap-1">
              <span>⬅</span> 返回上一级
            </button>
            <button id="btn-select-current-dir" onclick="selectCurrentDirSkills(true)" class="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-md text-xs font-medium transition">
              全选本级
            </button>
          </div>
        </div>

        <!-- Skills Container (Dynamic Sub-folders & Skills) -->
        <div id="skills-container" class="space-y-4">
          <div class="py-16 text-center text-slate-400 bg-white rounded-xl border border-dashed border-slate-300">
            暂无扫描到的技能，请先在左侧添加 Git 仓库源并点击「拉取/更新」
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal 1: Add/Edit Git Source -->
  <div id="source-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-md rounded-xl border border-slate-200 shadow-xl overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 id="modal-title" class="font-semibold text-sm text-slate-900">添加 Git 仓库源</h3>
        <button onclick="closeSourceModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
      </div>
      <div class="p-5 space-y-3.5">
        <input type="hidden" id="modal-src-id">
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">仓库名称 (别名)</label>
          <input id="modal-src-name" type="text" placeholder="如: 业务中台技能库" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">Git 仓库地址 (HTTP/SSH/GitLab)</label>
          <input id="modal-src-url" type="text" placeholder="如: git@gitlab.com:org/skills.git" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-medium text-slate-600 mb-1">Git 分支 (Branch)</label>
            <input id="modal-src-branch" type="text" placeholder="如: main、dev" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 mb-1">Skill 子目录</label>
            <input id="modal-src-subdir" type="text" placeholder="如: skills 或 ." class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
          </div>
        </div>
      </div>
      <div class="px-5 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2">
        <button onclick="closeSourceModal()" class="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200 rounded-md transition">取消</button>
        <button onclick="saveSourceModal()" class="px-4 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white rounded-md font-medium shadow-sm transition">保存并立即拉取</button>
      </div>
    </div>
  </div>

  <!-- Modal 2: Custom Skill Path -->
  <div id="path-modal" class="fixed inset-0 modal-backdrop hidden flex items-center justify-center p-4 z-50">
    <div class="bg-white w-full max-w-md rounded-xl border border-slate-200 shadow-xl overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 class="font-semibold text-sm text-slate-900">自定义安装路径</h3>
        <button onclick="closePathModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
      </div>
      <div class="p-5 space-y-3">
        <p class="text-xs text-slate-500 leading-relaxed">
          为技能 <span id="path-modal-skill-name" class="font-semibold text-slate-800"></span> 指定单独的安装目录。留空则恢复继承全局默认路径。
        </p>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">专属安装目标目录</label>
          <input id="path-modal-input" type="text" placeholder="如: D:\\ws\\my-app\\.opencode\\skills" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
        </div>
      </div>
      <div class="px-5 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
        <button onclick="resetSkillPathToDefault()" class="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-800 transition underline">恢复为默认路径</button>
        <div class="flex items-center gap-2">
          <button onclick="closePathModal()" class="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200 rounded-md transition">取消</button>
          <button onclick="saveSkillPathModal()" class="px-4 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white rounded-md font-medium shadow-sm transition">确认保存</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    let globalConfig = { default_install_to: '', sources: [], skill_overrides: {} };
    let currentSkills = [];
    let currentEditingSkill = '';
    let currentSelectedTag = 'all';
    let currentViewMode = 'folder'; // 'folder' (逐层进入) | 'grid' (平铺)
    let currentNavPath = ''; // 当前所在相对路径，'' 表示根目录

    async function init() {
      await loadConfig();
      await loadSkills();
    }

    async function loadConfig() {
      const res = await fetch('/api/config');
      globalConfig = await res.json();
      document.getElementById('cfg-default-install').value = globalConfig.default_install_to || '';
      renderSources(globalConfig.sources || []);
      updateSourceFilterOptions(globalConfig.sources || []);
    }

    function renderSources(sources) {
      const el = document.getElementById('sources-list');
      document.getElementById('sources-count').textContent = `(${sources.length})`;
      if (sources.length === 0) {
        el.innerHTML = `<div class="py-8 text-center text-xs text-slate-400">暂无 Git 仓库，请点击上方按钮添加</div>`;
        return;
      }
      el.innerHTML = sources.map(s => `
        <div class="p-3 bg-slate-50 hover:bg-slate-100/80 border border-slate-200 rounded-lg transition flex flex-col justify-between gap-2 min-w-0 overflow-hidden w-full">
          <div class="flex items-start justify-between gap-2 min-w-0 w-full">
            <div class="min-w-0 flex-1 overflow-hidden">
              <div class="font-semibold text-xs text-slate-900 flex items-center gap-1.5 min-w-0">
                <span class="truncate">${s.name || '未命名'}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100 font-mono shrink-0">${s.branch || 'main'}</span>
              </div>
              <div class="text-[11px] text-slate-400 font-mono truncate block w-full mt-1 select-all" title="${s.git_url}">${s.git_url}</div>
              <div class="text-[10px] text-slate-500 mt-1 truncate">子目录: <span class="font-mono text-slate-700">${s.sub_dir || '.'}</span></div>
            </div>
          </div>
          <div class="flex items-center justify-end gap-1.5 pt-2 border-t border-slate-200/60 text-xs shrink-0">
            <button onclick="pullSingleSource('${s.id}')" class="px-2 py-0.5 text-[11px] bg-white hover:bg-indigo-50 text-indigo-600 border border-slate-200 rounded transition">🔄 更新</button>
            <button onclick="editSource('${s.id}')" class="px-2 py-0.5 text-[11px] bg-white hover:bg-slate-200 text-slate-600 border border-slate-200 rounded transition">✏️ 编辑</button>
            <button onclick="deleteSource('${s.id}')" class="px-2 py-0.5 text-[11px] bg-white hover:bg-rose-50 text-rose-600 border border-slate-200 rounded transition">🗑️ 删除</button>
          </div>
        </div>
      `).join('');
    }

    function updateSourceFilterOptions(sources) {
      const select = document.getElementById('source-filter');
      const val = select.value;
      select.innerHTML = `<option value="all">所有仓库源</option>` + sources.map(s => `
        <option value="${s.id}">${s.name} (${s.branch})</option>
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

      // 1. 更新下拉选择框
      const select = document.getElementById('tag-filter');
      const curVal = select.value;
      select.innerHTML = `<option value="all">所有 Tag / 所属目录 (${skills.length})</option>` + sortedTags.map(t => `
        <option value="${t}">${t} (${tagCounts[t]})</option>
      `).join('');
      if (sortedTags.includes(curVal)) {
        select.value = curVal;
      } else {
        select.value = 'all';
        currentSelectedTag = 'all';
      }

      // 2. 渲染快捷胶囊栏
      const pillsContainer = document.getElementById('tag-pills-bar');
      const topTags = sortedTags.slice(0, 16);
      pillsContainer.innerHTML = `
        <span class="text-slate-400 mr-1 shrink-0">Tag 过滤:</span>
        <button onclick="selectTag('all')" class="px-2 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 ${currentSelectedTag === 'all' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
          全部 (${skills.length})
        </button>
      ` + topTags.map(t => `
        <button onclick="selectTag('${t}')" class="px-2 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 ${currentSelectedTag === t ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">
          ${t} <span class="opacity-70">(${tagCounts[t]})</span>
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
          btn.className = "px-2 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-indigo-600 text-white shadow-xs";
        } else if (text.startsWith(currentSelectedTag + ' ') || text === currentSelectedTag) {
          btn.className = "px-2 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-indigo-600 text-white shadow-xs";
        } else {
          btn.className = "px-2 py-0.5 rounded-full text-[10px] font-medium transition shrink-0 bg-slate-100 text-slate-600 hover:bg-slate-200";
        }
      });
    }

    function switchView(mode) {
      currentViewMode = mode;
      const btnFolder = document.getElementById('view-btn-folder');
      const btnGrid = document.getElementById('view-btn-grid');
      const breadcrumbNav = document.getElementById('breadcrumb-nav');

      if (mode === 'folder') {
        btnFolder.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 text-white shadow-2xs transition flex items-center gap-1";
        btnGrid.className = "px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1";
        breadcrumbNav.classList.remove('hidden');
      } else {
        btnGrid.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 text-white shadow-2xs transition flex items-center gap-1";
        btnFolder.className = "px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 hover:text-slate-900 transition flex items-center gap-1";
        breadcrumbNav.classList.add('hidden');
      }
      filterSkills();
    }

    // 目录树下钻与导航
    function navigateTo(path) {
      currentNavPath = path.trim().replace(/^\\/+|\\/+$/g, '');
      // 清空单次搜索以便聚焦在当前目录
      const searchBox = document.getElementById('search-box');
      if (searchBox.value) {
        searchBox.value = '';
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

      if (isSearchMode) {
        backBtn.classList.remove('hidden');
        selectCurBtn.classList.add('hidden');
        trail.innerHTML = `
          <span class="text-slate-400">🔍 全局搜索:</span>
          <span class="font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded font-mono">"${searchKeyword}"</span>
          <button onclick="clearSearch()" class="text-slate-400 hover:text-slate-600 text-xs ml-2 underline">退出搜索</button>
        `;
        return;
      }

      if (!currentNavPath) {
        backBtn.classList.add('hidden');
        selectCurBtn.classList.add('hidden');
        trail.innerHTML = `
          <span class="font-semibold text-slate-800 flex items-center gap-1">
            <span>🏠</span> 根目录 (所有顶级分类)
          </span>
        `;
        return;
      }

      backBtn.classList.remove('hidden');
      selectCurBtn.classList.remove('hidden');

      const parts = currentNavPath.split('/');
      let html = `
        <button onclick="navigateTo('')" class="text-indigo-600 hover:underline flex items-center gap-1 font-medium">
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
            <span class="font-semibold text-slate-800 font-mono flex items-center gap-1">
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
      filterSkills();
    }

    function selectCurrentDirSkills(checked) {
      // 勾选当前路径下的全部技能（含子孙技能）
      const prefix = currentNavPath ? (currentNavPath + '/') : '';
      const checkboxes = document.querySelectorAll('.skill-checkbox');
      currentSkills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === currentNavPath || fp.startsWith(prefix)) {
          const cb = document.querySelector(`.skill-checkbox[value="${s.name}"]`);
          if (cb) cb.checked = checked;
        }
      });
    }

    function selectSubFolderSkills(subPath, checked) {
      const prefix = subPath + '/';
      currentSkills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === subPath || fp.startsWith(prefix)) {
          const cb = document.querySelector(`.skill-checkbox[value="${s.name}"]`);
          if (cb) cb.checked = checked;
        }
      });
    }

    async function loadSkills() {
      const res = await fetch('/api/skills');
      const data = await res.json();
      currentSkills = data.skills || [];
      updateTagOptions(currentSkills);
      filterSkills();
    }

    function renderSingleSkillCard(s, showPathBadge = false) {
      return `
        <div class="skill-card bg-white p-3.5 rounded-xl border ${s.installed ? 'border-indigo-300 bg-indigo-50/15' : 'border-slate-200'} shadow-2xs hover:shadow-xs transition relative flex flex-col justify-between" data-name="${s.name}" data-desc="${s.desc}" data-source="${s.source_id}">
          <div>
            <div class="flex items-start justify-between gap-2 mb-1">
              <span class="font-semibold text-xs text-slate-900 truncate" title="${s.name}">${s.name}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0 ${s.installed ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                ${s.installed ? '已挂载' : '未安装'}
              </span>
            </div>
            <div class="text-[11px] text-indigo-600 font-medium mb-2 flex items-center gap-1.5 flex-wrap">
              <span class="bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded text-[10px] font-mono border border-indigo-100">🏷️ ${s.source_name}</span>
              <button onclick="selectTag('${s.tag}')" class="bg-amber-50 hover:bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded text-[10px] font-mono border border-amber-200 cursor-pointer transition" title="所属直接目录名: ${s.tag}">🏷️ ${s.tag}</button>
              ${showPathBadge && s.folder_path ? `<button onclick="navigateTo('${s.folder_path}')" class="bg-slate-100 hover:bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-mono transition" title="点击进入此所在目录">📂 ${s.folder_path}</button>` : ''}
            </div>
            <p class="text-[11px] text-slate-500 line-clamp-2 leading-relaxed mb-3" title="${s.desc}">${s.desc}</p>
          </div>
          <div>
            <!-- Install Target Info -->
            <div class="p-1.5 bg-slate-50 rounded-lg border border-slate-100 text-[10px] text-slate-600 mb-2.5 flex items-center justify-between gap-2">
              <div class="truncate flex items-center gap-1" title="目标路径: ${s.effective_install_to}">
                <span class="text-slate-400 shrink-0">${s.is_custom ? '专属:' : '默认:'}</span>
                <span class="font-mono text-slate-700 truncate">${s.effective_install_to}</span>
              </div>
              <button onclick="openPathModal('${s.name}', '${s.custom_install_to || ''}')" class="text-indigo-600 hover:text-indigo-800 shrink-0 font-medium hover:underline">修改</button>
            </div>
            <!-- Action Bar -->
            <div class="pt-2 border-t border-slate-100 flex items-center justify-between">
              <label class="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer select-none">
                <input type="checkbox" class="skill-checkbox rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5" value="${s.name}" ${s.installed ? 'checked' : ''}>
                <span class="text-xs">启用并安装</span>
              </label>
            </div>
          </div>
        </div>
      `;
    }

    function renderSkills(skills) {
      const container = document.getElementById('skills-container');
      const q = document.getElementById('search-box').value.trim();
      const isSearching = Boolean(q);

      renderBreadcrumbs(isSearching, q);

      document.getElementById('skill-count').textContent = `共 ${skills.length} 个技能`;
      if (skills.length === 0) {
        container.innerHTML = `<div class="py-16 text-center text-slate-400 bg-white rounded-xl border border-dashed border-slate-300">未扫描到匹配条件的技能包</div>`;
        return;
      }

      // 如果处于全局平铺模式，或者正在全局搜索中：平铺展示
      if (currentViewMode === 'grid' || isSearching) {
        container.innerHTML = `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${skills.map(s => renderSingleSkillCard(s, isSearching)).join('')}
          </div>
        `;
        return;
      }

      // 核心交互：像文件树一样一层一层进入 (Folder Hierarchical Explorer)
      // 计算当前 currentNavPath 层的直接子文件夹 与 直接归属技能
      const prefix = currentNavPath ? (currentNavPath + '/') : '';
      const subFolderMap = {}; // { subDirName: { fullPath: '...', totalSkills: N, installedCount: N } }
      const directSkills = [];

      skills.forEach(s => {
        const fp = s.folder_path || '';
        if (fp === currentNavPath) {
          // 直接属于当前层的技能
          directSkills.append ? directSkills.append(s) : directSkills.push(s);
        } else if (fp.startsWith(prefix)) {
          // 属于当前层的子目录
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

      // 1. 渲染当前层的子文件夹列表（点击进入下一层）
      if (subFolders.length > 0) {
        contentHtml += `
          <div>
            <div class="text-xs font-semibold text-slate-700 mb-2.5 flex items-center justify-between">
              <span class="flex items-center gap-1">
                <span>📁 子目录列表</span>
                <span class="text-slate-400 font-normal">(${subFolders.length} 个子文件夹，点击可进入下一级)</span>
              </span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 mb-6">
              ${subFolders.map(f => `
                <div onclick="navigateTo('${f.fullPath}')" class="bg-white hover:bg-indigo-50/50 p-3.5 rounded-xl border border-slate-200 hover:border-indigo-300 shadow-2xs transition cursor-pointer flex items-center justify-between group select-none">
                  <div class="flex items-center gap-2.5 min-w-0">
                    <span class="text-2xl group-hover:scale-110 transition-transform shrink-0">📁</span>
                    <div class="min-w-0">
                      <div class="font-semibold text-xs text-slate-900 group-hover:text-indigo-600 truncate font-mono">${f.name}</div>
                      <div class="text-[10px] text-slate-400 mt-0.5 truncate">
                        ${f.totalSkills} 个技能 ${f.installedCount > 0 ? `· <span class="text-emerald-600 font-medium">已挂载 ${f.installedCount}</span>` : ''}
                      </div>
                    </div>
                  </div>
                  <div class="flex items-center gap-1.5 shrink-0" onclick="event.stopPropagation()">
                    <button onclick="selectSubFolderSkills('${f.fullPath}', true)" class="text-[10px] text-indigo-600 hover:bg-indigo-50 px-1.5 py-0.5 rounded transition" title="全选此目录下全部技能">全选</button>
                    <span class="text-slate-300 group-hover:text-indigo-500 font-bold text-xs ml-1">→</span>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      // 2. 渲染当前层包含的直属技能
      if (directSkills.length > 0) {
        contentHtml += `
          <div>
            <div class="text-xs font-semibold text-slate-700 mb-2.5 flex items-center justify-between">
              <span class="flex items-center gap-1">
                <span>📦 本级目录技能</span>
                <span class="text-slate-400 font-normal">(${directSkills.length} 个)</span>
              </span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              ${directSkills.map(s => renderSingleSkillCard(s, false)).join('')}
            </div>
          </div>
        `;
      }

      if (subFolders.length === 0 && directSkills.length === 0) {
        contentHtml = `
          <div class="py-16 text-center text-slate-400 bg-white rounded-xl border border-dashed border-slate-300">
            此目录下暂无技能。点击上方「⬅ 返回上一级」返回。
          </div>
        `;
      }

      container.innerHTML = contentHtml;
    }

    function filterSkills() {
      const q = document.getElementById('search-box').value.toLowerCase().trim();
      const srcFilter = document.getElementById('source-filter').value;
      const tagFilter = currentSelectedTag;

      const filtered = currentSkills.filter(s => {
        const matchSearch = !q 
          || s.name.toLowerCase().includes(q) 
          || s.desc.toLowerCase().includes(q) 
          || (s.tag && s.tag.toLowerCase().includes(q))
          || (s.folder_path && s.folder_path.toLowerCase().includes(q));

        const matchSrc = (srcFilter === 'all') || (s.source_id === srcFilter);
        const matchTag = (tagFilter === 'all') || (s.tag === tagFilter);

        return matchSearch && matchSrc && matchTag;
      });
      renderSkills(filtered);
    }

    function filterSkills() {
      const q = document.getElementById('search-box').value.toLowerCase();
      const srcFilter = document.getElementById('source-filter').value;
      const tagFilter = currentSelectedTag;

      const filtered = currentSkills.filter(s => {
        const matchSearch = s.name.toLowerCase().includes(q) 
          || s.desc.toLowerCase().includes(q) 
          || (s.tag && s.tag.toLowerCase().includes(q))
          || (s.folder_path && s.folder_path.toLowerCase().includes(q));

        const matchSrc = (srcFilter === 'all') || (s.source_id === srcFilter);
        const matchTag = (tagFilter === 'all') || (s.tag === tagFilter);

        return matchSearch && matchSrc && matchTag;
      });
      renderSkills(filtered);
    }

    function selectAll(checked) {
      document.querySelectorAll('.skill-checkbox').forEach(cb => cb.checked = checked);
    }

    function showStatus(msg, isError = false) {
      const box = document.getElementById('status-box');
      box.textContent = msg;
      box.className = `p-3 rounded-lg text-xs ${isError ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'}`;
      box.classList.remove('hidden');
    }

    async function saveDefaultInstallPath() {
      const path = document.getElementById('cfg-default-install').value.trim();
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ default_install_to: path })
      });
      showStatus('默认安装路径已更新并保存！');
      loadSkills();
    }

    // Modal Operations for Sources
    function openSourceModal(source = null) {
      document.getElementById('modal-src-id').value = source ? source.id : '';
      document.getElementById('modal-src-name').value = source ? source.name : '';
      document.getElementById('modal-src-url').value = source ? source.git_url : '';
      document.getElementById('modal-src-branch').value = source ? source.branch : 'main';
      document.getElementById('modal-src-subdir').value = source ? source.sub_dir : 'skills';
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
      const src = {
        id: id || ('src-' + Date.now()),
        name: document.getElementById('modal-src-name').value.trim() || '未命名仓库',
        git_url: document.getElementById('modal-src-url').value.trim(),
        branch: document.getElementById('modal-src-branch').value.trim() || 'main',
        sub_dir: document.getElementById('modal-src-subdir').value.trim() || 'skills'
      };
      if (!src.git_url) {
        alert('请填写 Git 仓库 URL');
        return;
      }
      closeSourceModal();
      showStatus(`正在拉取仓库 [${src.name}] 分支 [${src.branch}]，请稍候...`);

      const res = await fetch('/api/sources/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(src)
      });
      const data = await res.json();
      if (data.ok) {
        showStatus(`仓库 [${src.name}] 保存并拉取成功！`);
        await loadConfig();
        await loadSkills();
      } else {
        showStatus('仓库拉取失败: ' + data.error, true);
      }
    }

    async function deleteSource(id) {
      if (!confirm('确定要移除此 Git 仓库源吗？')) return;
      const res = await fetch('/api/sources/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id })
      });
      showStatus('仓库源已移除。');
      await loadConfig();
      await loadSkills();
    }

    async function pullSingleSource(id) {
      showStatus(`正在更新仓库源 [${id}]...`);
      const res = await fetch('/api/pull', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id })
      });
      const data = await res.json();
      if (data.ok) {
        showStatus('仓库更新成功！');
        loadSkills();
      } else {
        showStatus('更新失败: ' + data.error, true);
      }
    }

    async function pullAllSources() {
      showStatus('正在批量拉取/更新所有 Git 仓库源...');
      const res = await fetch('/api/pull_all', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showStatus('所有 Git 仓库源已更新至最新！');
        loadSkills();
      } else {
        showStatus('拉取更新遇到问题: ' + data.error, true);
      }
    }

    // Modal Operations for Custom Skill Path
    function openPathModal(skillName, currentCustomPath) {
      currentEditingSkill = skillName;
      document.getElementById('path-modal-skill-name').textContent = skillName;
      document.getElementById('path-modal-input').value = currentCustomPath || '';
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
      showStatus(`技能 [${currentEditingSkill}] 安装路径配置已更新。`);
      await loadConfig();
      await loadSkills();
    }

    async function resetSkillPathToDefault() {
      document.getElementById('path-modal-input').value = '';
      await saveSkillPathModal();
    }

    // Sync Selected
    async function syncSelected() {
      const selected = Array.from(document.querySelectorAll('.skill-checkbox:checked')).map(c => c.value);
      showStatus('正在执行符号链接同步...');
      const res = await fetch('/api/sync', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ selected })
      });
      const data = await res.json();
      if (data.ok) {
        showStatus(`同步完成！当前已启用挂载 ${data.installed} 个技能。`);
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
            skills = scan_all_skills(cfg)
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
            if "default_install_to" in data:
                cfg["default_install_to"] = data["default_install_to"]
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        elif url.path == "/api/sources/save":
            cfg = load_config()
            src_id = data.get("id")
            sources = cfg.get("sources", [])

            # 替换或新增
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

            # 自动拉取该仓库
            try:
                pull_single_source(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

        elif url.path == "/api/sources/delete":
            cfg = load_config()
            src_id = data.get("id")
            cfg["sources"] = [s for s in cfg.get("sources", []) if s["id"] != src_id]
            save_config(cfg)
            # 可选：清理缓存
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
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as e:
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

        elif url.path == "/api/sync":
            cfg = load_config()
            selected = set(data.get("selected", []))
            all_skills = scan_all_skills(cfg)
            default_dir = Path(cfg.get("default_install_to", "")).expanduser()
            overrides = cfg.get("skill_overrides", {})

            try:
                # 遍历所有可用 skills
                installed_count = 0
                for s in all_skills:
                    name = s["name"]
                    source_path = Path(s["source_path"])
                    custom_path = overrides.get(name, "").strip()
                    target_dir = Path(custom_path).expanduser() if custom_path else default_dir
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_link = target_dir / name

                    # 同时也需要检查是否之前安装在 default_dir（若之前改了路径）
                    alt_dirs = [default_dir]
                    if custom_path:
                        alt_dirs.append(Path(custom_path).expanduser())

                    if name in selected:
                        # 确保 target_link 正确挂载
                        if not target_link.exists():
                            if sys.platform == "win32":
                                subprocess.run(["cmd", "/c", "mklink", "/J", str(target_link), str(source_path)], check=True, stdout=subprocess.DEVNULL)
                            else:
                                target_link.symlink_to(source_path)
                        installed_count += 1
                    else:
                        # 从所有可能的目标目录中卸载
                        for ad in alt_dirs:
                            al = ad / name
                            if al.exists():
                                if al.is_symlink():
                                    al.unlink()
                                elif al.is_dir():
                                    if sys.platform == "win32":
                                        subprocess.run(["cmd", "/c", "rmdir", str(al)], check=True, stdout=subprocess.DEVNULL)
                                    else:
                                        shutil.rmtree(al)

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
