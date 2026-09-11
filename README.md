# SkillBox 📦

> **基于 Git 原生能力驱动的 AI Agent 技能管理器**  
> 支持多 Git 仓库与独立分支、像文件树一样逐层进入浏览、目录级与单 Skill 专属挂载路径、符号链接零拷贝秒级挂载、统一 CLI 控制中枢与后台自动更新。

[![GitHub Repo](https://img.shields.io/badge/GitHub-SenZh%2FSkillBox-181717.svg?logo=github)](https://github.com/SenZh/SkillBox)
[![Version](https://img.shields.io/badge/version-v0.1-blue.svg)](https://github.com/SenZh/SkillBox/releases)
[![Python](https://img.shields.io/badge/python-3.8+-brightgreen.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-orange.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🌟 为什么选择 SkillBox？

在开发或使用 AI Coding Agent（如 OpenCode、Claude Code、Cursor、Windsurf、Cline 等）时，现存的技能管理工具往往存在诸多痛点：
1. **无法指定 Git 分支**：对企业内网私有 GitLab、分支开发模式极不友好，默认只能克隆 main/master；
2. **多层级 Monorepo 无法有效浏览**：大型仓库内部按业务线分了多层目录，扁平展开直接刷屏甚至无法识别；
3. **安装目录僵化**：无法区分“全局默认技能”、“业务线目录级技能”与“特定工程专有技能”；
4. **运维脚本散乱**：启停、自启、状态查看散落多个批处理，缺乏统一的管理中枢；
5. **挂载体验不佳**：反复复制大文件，或建立软链接时频繁弹出黑色命令行黑框。

**SkillBox 专为解决上述痛点而生！**

---

## ✨ 核心特性

- 🌿 **支持配置多个 Git 仓库与独立分支**：
  - 自由纳管多个私有/公开仓库（内网 GitLab、GitHub、Gitea、SSH、HTTPS 协议）；
  - 每个仓库独立指定**分支（Branch）**与 **Skill 相对子目录（Subdirectory）**；
  - 自动记录每个仓库的最后拉取时间，并持久化存储。
- 📁 **像文件树一样一层一层进入浏览 (Folder Drill-down)**：
  - 资源管理器级下钻体验，从顶级目录点击文件夹逐级进入子目录，页面始终清晰聚焦；
  - 配备精致的**面包屑路径导航（Breadcrumbs）**与 `⬅ 返回上一级` 按钮，随时瞬时跳转；
  - 文件夹卡片支持一键「全选本目录（含全部子孙技能）」。
- 🎯 **三层灵活挂载路径架构（目录级统一挂载）**：
  - **单 Skill 专属路径**（最高优先级）：精确覆盖特定单个技能；
  - **目录级统一挂载路径**（第二优先级，自底向上多级继承）：为任意目录（如 `business/bind-center` 或 `business`）指定专属目录，该目录下所有技能自动继承统一挂载；
  - **全局默认安装路径**（保底优先级）：统一未指定目录的默认安装位置（如 `~/.agents/skills`）；
  - **修改路径全自动平滑迁移**：无论修改全局默认还是某个目录的挂载路径，系统自动在旧位置解绑并在新位置重建软链接，无需人工重新勾选。
- 🛠️ **统一 CLI 命令行中枢与双击一体化**：
  - 根目录提供统一命令 **`skillbox.bat`**，双击默认直接后台启动，命令行传参可一键启停、重启、查状态、开机自启、全量更新与查日志。
- 🏷️ **智能直接父目录名 Tag**：
  - 严格按技能所属的直接父目录名提取 Tag（如 `A/B/C/skill` 对应 `Tag = C`）；
  - 顶部配备 Tag 下拉筛选与快捷 Tag 胶囊栏（Tag Pills），点击卡片标签联动过滤。
- 🔍 **按挂载状态快速收窄**：
  - 工具栏提供状态过滤器，支持一键切换 `全部` / `🟢 仅已挂载 (Installed)` / `⚪ 仅未挂载 (Unmounted)`，环境现状一目了然。
- 👁️ **Skill 详情与 SKILL.md 文档正文预览**：
  - 点击卡片标题或详情按钮，大弹窗结构化展示完整功能描述、生效挂载路径与 **`SKILL.md` 完整文档指令正文**，支持一键复制。
- 🔄 **后台静默定时自动更新**：
  - 每个仓库可独立配置自动拉取频率（每 30 分钟、每 1 小时、每 6 小时、每天）；
  - 后台常驻守护线程到期自动 `git pull`；由于采用符号链接机制，Agent 本地读取的代码**全自动秒级变为最新版本**。
- ⚡ **零拷贝、零闪屏与安全解绑**：
  - Windows 原生采用底层 Win32 C 级系统调用（`_winapi.CreateJunction`）创建 NTFS 目录联结，**100% 杜绝终端黑框闪烁，纳秒级生效**；
  - 解绑采用 Python 原生 `os.rmdir` 安全移除挂载指针，**绝不误伤** Git 缓存里的物理源码。
- 🚀 **Windows 开机静默自启**：
  - 基于当前用户注册表机制，无需 Administrator 管理员权限；
  - 支持在 WebUI 设置页面一键开关，或通过命令行一键配置；开机静默常驻，不弹黑框与浏览器。
- 📝 **内置标准审计日志系统**：
  - 所有后台服务事件、Git 拉取、符号链接挂载（`[Mount]`）、旧链接清理（`[Clean]`）、解绑（`[Unmount]`）实时写入 `skillbox.log`；
  - 可在命令行直接输入 `skillbox log` 秒级查看最新运行日志。
- 🛡️ **安全与凭据完全隔离**：
  - 不保存任何私钥密码，直接复用操作系统的 Git 原生凭据（SSH 密钥系统 / Windows 凭据管理器）；
  - 本地配置文件与 Git 源码缓存已被 `.gitignore` 严格物理屏蔽，绝不上库。

---

## 🚀 快速上手与统一 CLI

**首次使用一键完成**（命令注册 + 桌面图标 + 开机自启 + 启动服务）：

```bash
skillbox install init
```

之后**双击桌面 SkillBox 图标**即可启动服务，并以独立应用窗口（无地址栏，接近原生客户端）打开控制台。

SkillBox 将所有运维操作统一收拢在 **`skillbox`** 命令中（Windows 为 `skillbox.bat`）：

| 操作指令 | 效果说明 |
| :--- | :--- |
| **`skillbox install [init]`** | 一键安装：注册命令到 PATH + 创建桌面图标 + 开机自启（加 `init` 同时启动服务） |
| **`skillbox shortcut`** | 仅创建桌面快捷方式（双击即启动并打开应用窗口） |
| **`skillbox gui`** | 启动服务并以独立应用窗口打开（桌面图标调用入口） |
| **`skillbox start`** (或 `up`) | 后台静默启动服务（自动探活自愈，不重复拉起） |
| **`skillbox stop`** (或 `down`) | 安全停止后台服务并释放端口占用 |
| **`skillbox restart`** | 一键重启服务 |
| **`skillbox status`** | 查看当前运行状态、后台 PID、服务端口与开机自启情况 |
| **`skillbox open`** | 以应用窗口打开控制台（`http://127.0.0.1:7860`） |
| **`skillbox update`** | 触发所有 Git 仓库源增量拉取最新提交 |
| **`skillbox resolve <name>`** | 定位技能源真身路径及 Git 目录（未被 Git 管理会明确提示） |
| **`skillbox commit <name> -m s`** | 白名单提交并推送该技能改动（仅提交该技能目录） |
| **`skillbox log [N]`** | 查看后台最近运行审计日志（默认 50 行） |
| **`skillbox autostart on / off`** | 一键开启 / 关闭开机静默自启（无需管理员提权，跨平台） |
| **`skillbox run`** | 前台直接运行服务（用于排错调试查看实时日志） |
| **`skillbox test`** | 一键运行全量自动化单元测试套件 |
| **`skillbox uninstall`** | 移除命令注册与桌面快捷方式 |

> **跨平台**：Windows / macOS / Linux 三平台均支持。打开控制台优先使用 Chrome/Edge 应用模式（无地址栏独立窗口），找不到时自动回退系统默认浏览器。

---

## 💡 使用工作流

1. **设置全局默认安装路径**：
   - 进入顶部导航栏的 **「⚙️ 仓库与配置」** 页面配置通用路径（如 `C:\Users\Name\.agents\skills`）。
2. **添加你的 Git 仓库源**：
   - 点击 **「+ 添加仓库源」**，填写仓库名称、Git URL、指定分支与子目录，并选定自动更新频率。
3. **设置目录级统一挂载（可选，高级特性）**：
   - 在文件夹卡片上点击 **「⚙️ 设置本目录安装路径」**（或进入该目录后点击面包屑右侧按钮）；
   - 为该目录（如 `business/bind-center`）指定专有目录，其内部所有技能自动继承该路径！
4. **浏览、勾选与应用挂载**：
   - 逐层下钻浏览文件夹，勾选需要启用的技能；
   - 点击右上角 **「💾 保存并生效挂载」**，系统秒级在对应目标目录建立符号链接！

---

## 📂 项目结构

```text
skillbox/
├── skillbox.bat             # 统一 CLI 命令与启动入口（双击默认启动）
├── start.bat                # 兼容启动快捷方式（调用 skillbox start）
├── cli.py                   # CLI 命令行逻辑引擎（启停、重启、状态、更新、日志）
├── app.py                   # SkillBox 服务端核心（多仓库引擎 + 递归扫描 + 前端 SPA）
├── run_tests.py             # 自动化单元测试运行器
├── tests/                   # 自动化测试套件 (全量 10 个用例)
│   ├── test_config.py       # 配置管理与持久化测试
│   ├── test_folder_mount.py # 目录级挂载与继承优先级测试
│   ├── test_scanner.py      # 元数据解析与 Tag 父目录名规则测试
│   ├── test_symlink.py      # Junction 挂载与安全解绑测试
│   ├── test_autostart.py    # Windows 开机自启注册测试
│   └── test_api.py          # HTTP REST API 全链路测试
├── docs/
│   ├── architecture.md      # 系统架构设计文档
│   └── changelog.md         # 变更日志 (Keep a Changelog)
├── ROADMAP.md               # 产品演进路线图
├── .gitignore               # Git 忽略配置
└── README.md                # 本说明文档
```

---

## 🧪 自动化测试

运行全量自动化单元测试套件：

```bash
skillbox test
```
或：
```bash
python run_tests.py
```

---

## 📚 更多参考

* 详细系统架构与数据流图：请参阅 [架构设计文档 (docs/architecture.md)](docs/architecture.md)
* 迭代历史与版本记录：请参阅 [变更日志 (docs/changelog.md)](docs/changelog.md)
* 未来规划与生态演进：请参阅 [产品路线图 (ROADMAP.md)](ROADMAP.md)
* 项目仓库地址：[https://github.com/SenZh/SkillBox](https://github.com/SenZh/SkillBox)
