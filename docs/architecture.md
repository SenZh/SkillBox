# SkillBox 架构设计文档 (Architecture)

> 版本：v0.2  
> 状态：正式发布  
> 适用：AI Coding Agent（OpenCode、Claude Code、Cursor、Windsurf 等）技能管理与同步

---

## 1. 系统定位与核心设计哲学

**SkillBox** 是一个专为 AI Agent Skills 设计的轻量级包管理与挂载调度中心。其核心设计哲学为：

1. **Git 原生与分支第一（Git-Native & Branch-First）**：绝不依赖中心化镜像源，直接对接任意公开/私有 Git 仓库，原生支持企业分支与 Monorepo 多层子目录。
2. **零拷贝秒级挂载（Zero-Copy Mounting via Symlinks/Junctions）**：不复制代码副本，利用操作系统级符号链接（Windows NTFS Junction / 类 Unix Symlink）进行直接映射，修改实时联动，更新秒级生效。
3. **安全凭据隔离（Zero-Credential Persistence）**：不自建敏感认证体系，直接复用操作系统的原生 Git 凭据（SSH Key / Windows Credential Manager），本地配置与 Git 源码严格物理隔离防泄露。
4. **轻量与自包含（Zero Heavy Dependencies）**：纯 Python 标准库编写，单文件可独立运行，无需 Node.js/Rust/Docker 等复杂运行环境，极速启动。

---

## 2. 系统整体拓扑图

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             用户操作界面 (WebUI)                            │
│  ┌───────────────────────────────┐     ┌─────────────────────────────────┐  │
│  │   🗂️ 技能工作区 (全宽模式)    │     │      ⚙️ 仓库与配置 (独立页)      │  │
│  │ - 目录树逐层下钻 (Drill-down) │     │ - 全局默认目标路径与自动迁移    │  │
│  │ - 面包屑导航 (Breadcrumbs)    │     │ - 多 Git 仓库源管理 (URL/分支)  │  │
│  │ - Tag / 目录分类快捷过滤      │     │ - 定时自动更新频率设置 (Cron)   │  │
│  │ - 响应式已选状态集合          │     │ - 仓库单独拉取与移除            │  │
│  └───────────────────────────────┘     └─────────────────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP REST APIs
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    SkillBox Core (Python Threading Server)                  │
│                                                                             │
│   ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐   │
│   │ 目录索引器 (Scanner)│    │ 挂载管理器 (Mount) │    │ 定时更新调度器  │   │
│   │ - 多级递归文件树   │    │ - NTFS Junction    │    │ - 后台守护线程  │   │
│   │ - Tag 直接父目录名 │    │ - Symlink          │    │ - 频率轮询      │   │
│   │ - SKILL.md 元数据  │    │ - safe_remove_link │    │ - 自动 Git Pull │   │
│   └────────────────────┘    └────────────────────┘    └─────────────────┘   │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │ Git 操作                    │ 符号链接指针
┌───────────────────────▼─────────────┐ ┌─────────────▼───────────────────────┐
│     本地 Git 缓存区 (.skillbox_cache)│ │       Agent 目标运行目录            │
│  ├── src-1789... (saas-skill: dev)  │ │  C:\Users\User\.agents\skills\      │
│  │     └── skills/business/bind/... │ │    ├── bindcenter-knowledge ──┐     │
│  └── src-1790... (oms&dubhe: main)  │ │    └── ...                    │     │
└─────────────────────────────────────┘ └───────────────────────────────┼─────┘
                                                                        │ 物理指向
                                                                        └───────►
```

---

## 3. 核心模块详解

### 3.1 目录索引器 (Directory Tree Scanner)
* **递归扫描与过滤**：使用 `os.walk` 穿透任意层级的目录结构，自动过滤 `.git`、`node_modules` 等隐藏或系统目录，精准捕获包含 `SKILL.md` 或 `skill.md` 的技能包。
* **Tag 计算规则**：
  * 规则规范：`Tag = p_root.parent.name`（取技能目录的直接父目录名称）。
  * 案例：`skills/business/bind-center/bindcenter-knowledge` 对应的 Tag 计算为 `bind-center`（非全路径），精准收窄标签维度。
* **完整路径留存**：保留相对于仓库 `sub_dir` 的完整相对路径 `folder_path`（如 `business/bind-center`），供文件树逐层进入使用。

### 3.2 挂载生命周期管理器 (Mount & Symlink Manager)
* **Windows NTFS Junction**：
  * 创建：`cmd /c mklink /J "<target>" "<source>"`，不需要 Windows 管理员权限或开发者模式。
  * 卸载：通过 Python 原生 `os.rmdir("<target>")` 安全解绑目录联结，绝不误伤源目录下的物理源码文件。
* **类 Unix Symlink**：
  * 创建：`target.symlink_to(source)`
  * 卸载：`target.unlink()`
* **全局默认目录平滑迁移 (Auto-Migration)**：
  * 当用户修改全局默认路径时，系统自动识别出所有使用默认目录的已挂载技能，在旧目录下解绑，并在新目录下重建映射，零人工介入。

### 3.3 后台自动定时更新调度器 (Auto-Update Scheduler)
* **常驻守护线程**：服务启动时拉起 `auto_update_scheduler()` 守护线程（`daemon=True`），每 30 秒轮询一次。
* **多仓库细粒度调度**：
  * 每个仓库独立记录 `auto_update_interval`（分钟）及 `last_pulled_ts`（上次更新时间戳）。
  * 到期自动在 `.skillbox_cache/<source_id>` 下执行 `git fetch`、`git checkout <branch>`、`git pull`。
  * 由于目标目录采用符号链接，Git 拉取完成即意味着 Agent 端实时生效。

### 3.4 桌面托盘应用 (Desktop Tray App)

`desktop_app.py` 提供 SkillBox 的常驻桌面客户端形态，取代「隐藏守护进程 + 外挂浏览器」旧模式。

* **进程与线程模型（关键约束）**：
  * **主线程**：运行 pywebview 的原生窗口消息循环（`webview.start()`），这是 GUI 框架的硬性要求；
  * **HTTP 服务线程**：`daemon=True` 后台线程运行 `server.serve_forever()`，即服务内嵌于 App 进程；
  * **托盘线程**：`pystray.Icon.run()` 运行在独立线程（pystray 需独占一个事件循环）；
  * 三者的互调（托盘菜单点击 → 操作窗口 / 退出）通过实例方法与线程安全锁协调。
* **关闭即缩托盘**：
  * 绑定 pywebview `window.events.closing` 事件，回调中调用 `window.hide()` 并返回 `False`，
    阻止默认的窗口销毁行为；应用不退出，服务继续运行；
  * 仅托盘菜单「退出 SkillBox」触发 `quit_app()`：停服务 → 停托盘 → `os._exit(0)`。
* **单实例与端口复用**：
  * 启动时先 `find_running_service()` 探测已有服务（优先读 PID 文件，再扫描端口区间）；
  * 命中则复用该端口、不再另起服务；未命中才 `start_server()` 内嵌新服务。
* **依赖降级**：`check_dependencies()` 缺失 pywebview/pystray/Pillow 时，
  `cli.py gui` 自动回退为「后台服务 + 浏览器应用窗口」，保证功能可用性。
* **打包适配（PyInstaller）**：
  * 区分「数据目录」与「资源目录」：`sys.frozen` 时数据目录 = exe 所在目录，
    资源目录 = `sys._MEIPASS`（临时解包目录），避免配置/缓存写入临时目录而丢失。

### 3.5 前端交互与状态架构 (Frontend SPA)
* **单页双模式架构**：
  * `page-skills`：100% 满屏文件树浏览、搜索与勾选同步。
  * `page-settings`：仓库源配置、定时策略、全局默认路径配置。
* **全局响应式已选集合 (`selectedSkills = new Set()`)**：
  * 彻底解决在多层级目录进入/退回时 DOM 元素销毁导致的勾选丢失问题；
  * 全局集合保证勾选状态跨目录、跨页面全局持久生效。

---

## 4. 安全与隔离规范

1. **凭据零留存**：SkillBox 不存储任何私钥或明文密码，认证全部交由操作系统的 Git 原生凭据管理器负责。
2. **物理隔离屏蔽**：
   * `config.json`（本地路径配置）
   * `.skillbox_cache/`（本地下载的 Git 仓库源码）
   * `.skillbox.pid`（进程运行标记）
   全部在 `.gitignore` 首行屏蔽，绝不上库。
