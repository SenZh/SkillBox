# SkillBox 变更日志 (Changelog)

所有关键架构演进与版本迭代均遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范。

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
  - 严格按照 Skill 所在的**直接所属父目录名**提取 Tag（即 A/B/C 目录下，`Tag = C`）；
  - 顶部新增 Tag 快捷过滤胶囊栏（Tag Pills）与下拉筛选。
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
- **Windows 后台静默运行与服务生命周期**：
  - 新增 `start.bat`：采用 `pythonw` 与 `DETACHED_PROCESS` 完全脱离 CMD 窗口后台运行；
  - 新增 `stop.bat`：一键读取 PID 安全结束后台服务并释放端口；
  - 新增 `status.bat`：查看服务运行状态与端口占用。
- **自动化单元测试套件**：
  - 新增 `tests/` 目录与 `run_tests.py`，全量覆盖配置持久化、递归扫描、Tag 计算、符号链接挂载与解绑、HTTP REST API 等核心链路。
