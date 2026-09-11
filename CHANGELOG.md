# Changelog

本项目所有关键架构演进与版本迭代均遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，
版本号遵循 [语义化版本 (SemVer)](https://semver.org/lang/zh-CN/)。

---

## [0.2.0] - 2026-09-11

### 🖥️ 桌面托盘客户端 (Desktop Tray App)
- **新增 `desktop_app.py` 常驻桌面应用**：将 SkillBox 包装为可见的系统托盘客户端，
  内嵌托管 HTTP 服务（后台线程），不再需要独立的隐藏守护进程。
- **原生 WebView 窗口**：基于 pywebview 使用系统原生 WebView2 承载现有 WebUI，
  观感接近原生客户端（非外挂浏览器窗口）。
- **关闭即缩托盘**：点击窗口关闭按钮时静默隐藏到右下角系统托盘，服务继续后台运行，
  不再弹出任何气泡提示；通过托盘右键菜单「退出 SkillBox」才真正结束。
- **系统托盘右键菜单**：打开控制台 / 在浏览器中打开 / 同步更新技能 / 查看运行日志 /
  打开程序目录 / 退出。
- **单实例保证（跨进程锁）**：基于 Windows 命名互斥体 / 类 Unix flock 实现真正的单实例，
  重复启动时第二个实例不创建窗口与托盘，而是调用已运行实例的 `/api/activate`
  呼出既有窗口后自身退出，彻底解决「多次打开 exe 会弹出多个窗口」的问题。
- **开机自动启动**：开机登录后自动拉起桌面托盘应用，静默进入系统托盘（`--startup`），
  不弹出窗口；支持 WebUI 一键开关与 `skillbox autostart on/off`。
- **自动检测并安装 CLI**：启动桌面应用时自动检测 `skillbox` 命令是否已注册，
  未安装则自动写入用户 PATH。
- **降级兼容**：未安装 pywebview/pystray 时，`skillbox gui` 自动回退为
  「后台服务 + 浏览器应用窗口」模式，功能不受影响。

### 🎨 WebUI 体验优化
- **移除 Tag 目录下拉框与快捷过滤胶囊栏**：简化工具栏，减少视觉噪音。
- **挂载状态改为 Tab 切换**：`全部 / 仅已挂载 / 仅未挂载`，样式与「目录树/平铺」视图切换一致。
- **搜索框放大**：加宽加高搜索输入框，提升可读性与操作手感。

### 📦 独立可执行文件与快捷方式
- **新增 `tools/build_exe.py`**：基于 PyInstaller 一键打包单文件 `dist/SkillBox.exe`
  （内嵌 SkillBox 图标、无控制台黑窗、自带资源）。
- **打包路径适配**：区分「数据目录」（config/缓存/日志/PID）与「资源目录」
  （assets/builtin_skills），frozen 运行时数据落在 exe 同级目录，避免写入临时解包目录。
- **快捷方式升级**：`skillbox shortcut` 优先指向打包好的 `SkillBox.exe`，
  图标/进程名正确、无需本机 Python。
- **新增 `requirements.txt`**：声明桌面应用运行依赖（pywebview/pystray/Pillow）。

### 🔧 服务层重构
- `app.py` 抽出可复用的 `create_server()` / `start_server()` / `stop_server()`，
  支持服务在独立线程中托管，为桌面应用内嵌运行提供支撑。
- 数据目录与代码目录解耦（`BASE_DIR` / `CODE_DIR` / `RESOURCE_DIR`），
  适配源码运行与打包运行两种形态。

### ⌨️ Agent CLI 精简
- **CLI 收敛为三条命令**：`search`（按关键词搜索技能，输出名称 + 真身路径 + 描述）、
  `commit`（白名单提交并推送单个技能目录）、`help`；
- **`commit` 提交前自动拉取该技能所在仓库**，降低推送冲突；
- 删除 `start`/`stop`/`status`/`open`/`gui`/`install`/`shortcut`/`update`/`resolve`/
  `log`/`autostart`/`run`/`test`/`uninstall` 等运维命令，相关能力全部移交桌面应用与 WebUI；
- 移除 `resolve`，由 `search` 统一承担技能定位；
- 内置说明技能 `builtin_skills/skillbox/SKILL.md` 同步更新为新命令。

---

## [0.1.0] - 2026-09-10

### 🚀 核心架构与特性 (Initial Release)
- **多 Git 仓库与分支支持 (Multi-repo Sources)**：
  - 支持配置任意数量的公开/私有 Git 仓库（GitLab、GitHub、Gitea、SSH、HTTPS）；
  - 每个仓库支持**独立指定分支**（如 `dev`、`feature/xxx`）与 **Skill 所在子目录**（Monorepo 支持）。
- **双层安装路径架构 (Dual Install Paths)**：
  - 提供**全局默认安装目录**（如 `~/.agents/skills`）；
  - 支持为单个具体 Skill 单独覆盖**专属安装目录**（如特定工程的 `.opencode/skills`）。
- **真正的文件树逐层下钻 (Folder Tree & Drill-down)**：
  - 像 Windows 资源管理器 / Finder 一样，支持**一层一层点击文件夹进入下一级**；
  - 顶部配备精致的**面包屑路径导航（Breadcrumbs）**与 `⬅ 返回上一级` 按钮；
  - 文件夹卡片上提供「全选本目录（含子孙级）」批量操作。
- **Tag 抽取规则优化**：
  - 严格按照 Skill 所在的**直接所属父目录名**提取 Tag（即 A/B/C 目录下，`Tag = C`）。
- **符号链接与目录联结挂载机制**：
  - Windows 原生采用 NTFS 目录联结（Junction，无需管理员权限）；
  - 类 Unix 原生采用软链接（Symlink）；
  - 卸载时采用原生 `os.rmdir()` 安全解绑，彻底避免误删真实源码。
- **默认安装路径变更自动平滑迁移 (Auto-Migration)**：
  - 当全局默认路径发生变更时，自动在旧目录下卸载、并在新目录下重建所有已挂载链接。
- **定时自动更新调度器 (Auto-Update Scheduler)**：
  - 每个仓库可独立配置自动更新频率（每 30 分钟、每 1 小时、每 6 小时、每天等）；
  - 后台常驻守护线程到期自动 `git pull`，已挂载的 Agent 技能秒级实时生效。
- **UI / UX 现代解耦设计**：
  - 将 Git 仓库与路径设置解耦至独立的 **「⚙️ 仓库与配置」** 页面；
  - 释放 **「🗂️ 技能工作区」** 为全宽文件树浏览视野；
  - 右上角同步按钮集成实时已选技能动态计数角标；
  - 操作反馈升级为现代悬浮 Toast 提示。
- **自动化单元测试套件**：
  - 新增 `tests/` 目录与 `run_tests.py`，全量覆盖配置持久化、递归扫描、Tag 计算、
    符号链接挂载与解绑、HTTP REST API 等核心链路。

[0.2.0]: https://github.com/SenZh/SkillBox/releases/tag/v0.2.0
[0.1.0]: https://github.com/SenZh/SkillBox/releases/tag/v0.1.0
