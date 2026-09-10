# SkillBox 产品演进路线图 (ROADMAP)

本文档规划了 SkillBox 从 v0.1 到长期生态演进的发展路线图。

---

## 🎯 当前版本：v0.1 (已交付)

- [x] 多 Git 仓库源管理（支持内网私有 GitLab、GitHub、SSH、HTTPS 协议）
- [x] 显式指定 Git 分支（Branch）与 Monorepo 子目录过滤
- [x] 像文件管理器一样的逐层下钻目录树（Folder Drill-down）与面包屑导航
- [x] Tag 严格按直接父目录名抽取（A/B/C 下 `Tag = C`）与 Tag 胶囊筛选
- [x] 全局默认安装路径 + 单 Skill 专属覆盖路径
- [x] 全局默认路径修改后的已挂载软链接自动平滑迁移
- [x] 每个仓库独立配置定时自动更新调度器（后台静默 Git Pull，零成本即时生效）
- [x] Windows NTFS Junction 目录联结挂载与 `os.rmdir` 安全解绑
- [x] Windows 后台静默运行脚本（`start.bat` / `stop.bat` / `status.bat`）
- [x] 独立设置页面与全宽技能工作区 UI/UX 重构
- [x] 全量自动化单元测试套件（`tests/` & `run_tests.py`）

---

## 🚀 近期计划：v0.2 (体验深化与高级管理)

- [ ] **多 Agent 一键矩阵分发 (Agent Matrix)**：
  - 一键扫描本机已安装的 Agent（OpenCode、Claude Code、Cursor、Windsurf 等）；
  - 支持在卡片上直接勾选分发给哪些 Agent，无需手动配置多个路径。
- [ ] **Preset 技能预设方案 (Preset Kits)**：
  - 支持将一组常用的技能保存为一个预设（如“Java 后端开发套件”、“大数据分析套件”）；
  - 支持一键激活或禁用某个预设。
- [ ] **Git 凭据可视化检测与配置向导**：
  - 在设置页添加 Git 连接测试按钮，直观反馈 SSH 证书或 Token 连通性。
- [ ] **Skill 内容快速预览 (SKILL.md Markdown Viewer)**：
  - 点击卡片可弹窗预览完整的 `SKILL.md` 正文及脚本依赖。

---

## 🔮 中远期展望：v0.3+ (生态与协同)

- [ ] **团队配置共享导出**：
  - 支持将仓库源与推荐的 Skills 清单导出为 `skillbox-team.json`，新成员一键导入开箱即用。
- [ ] **CLI 命令行互操作**：
  - 提供 `skillbox install <name>`、`skillbox update` 纯命令行命令，方便集成到终端工具流。
- [ ] **版本差异 Diff 对比**：
  - 当远程仓库分支有新提交时，支持在界面对比新旧版本的代码改动。
- [ ] **跨平台托盘常驻 (System Tray)**：
  - 基于轻量 GUI 框架提供 Windows/macOS 系统托盘常驻图标，右键菜单快速启停与同步。
