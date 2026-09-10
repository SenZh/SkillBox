# SkillBox 📦

> **基于 Git 原生能力驱动的 AI Agent 技能管理器**  
> 支持多 Git 仓库与独立分支、像文件树一样逐层进入浏览、目录级与单 Skill 专属挂载路径、符号链接零拷贝挂载与统一 CLI 控制中枢。

![Version](https://img.shields.io/badge/version-v0.1-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 🌟 为什么选择 SkillBox？

现有的 Agent Skill 管理工具往往存在以下痛点：
1. **无法指定 Git 分支**：对企业内网 GitLab、私有 Git 仓库的分支开发极其不友好，默认只能拉取 main/master；
2. **多层级 Monorepo 无法浏览**：大型仓库内部按业务线分了多层目录，扁平列表直接冲爆界面或无法扫描；
3. **安装目录僵化**：无法区分“全局技能”、“特定业务线目录技能”与“单个项目专有技能”；
4. **多个脚本散乱**：启停、自启、状态查看散落多个批处理，缺乏统一 CLI 入口。

**SkillBox 专为解决上述痛点而生！**

---

## ✨ 核心特性

- 🌿 **支持配置多个 Git 仓库**：
  - 自由纳管多个私有/公开仓库（内网 GitLab、GitHub、Gitea 等）；
  - 每个仓库独立指定**分支（Branch）**与 **Skill 所在子目录（Subdirectory）**。
- 📁 **像文件树一样一层一层进入浏览**：
  - 资源管理器级下钻体验，从顶级目录点击文件夹逐级进入子目录，页面永远清晰聚焦；
  - 顶部配备**面包屑路径导航**与 `⬅ 返回上一级` 按钮，随时一键跳转；
  - 文件夹卡片支持一键「全选本目录（含全部子孙技能）」。
- 🎯 **三层灵活挂载路径架构（目录级统一挂载）**：
  - **单 Skill 专属路径**（最高优先级）：精确覆盖单个具体技能；
  - **目录级统一挂载路径**（第二优先级，自底向上多级继承）：为任意目录（如 `business/bind-center` 或 `business`）指定专属目录，该目录下所有技能自动继承统一挂载；
  - **全局默认安装路径**（保底优先级）：统一未指定目录的默认安装位置（如 `~/.agents/skills`）；
  - **修改路径全自动平滑迁移**：无论修改全局默认还是某个目录的挂载路径，系统自动在旧位置解绑并在新位置重建软链接，无需人工重新勾选。
- 🛠️ **统一 CLI 命令行中枢与双击一体化**：
  - 根目录提供统一命令 **`skillbox.bat`**，双击默认直接后台启动，命令行传参可一键启停、重启、查状态、开机自启与全量更新。
- 🏷️ **智能直接父目录名 Tag**：
  - 严格按技能所属的直接父目录名提取 Tag（如 `A/B/C/skill` 对应 `Tag = C`）；
  - 顶部配备 Tag 下拉筛选与快捷 Tag 胶囊栏（Tag Pills），点击卡片标签联动过滤。
- 🔄 **后台静默定时自动更新**：
  - 每个仓库可独立配置自动拉取频率（每 30 分钟、每 1 小时、每 6 小时、每天）；
  - 后台常驻守护线程到期自动 `git pull`；由于采用符号链接机制，Agent 本地读取的代码**全自动秒级变为最新版本**。
- 🔗 **零拷贝与安全解绑**：
  - Windows 原生采用 NTFS 目录联结（Junction，无需管理员权限），类 Unix 采用 Symlink；
  - 解绑采用 Python 原生 `os.rmdir` 安全移除挂载指针，**绝不误伤** Git 缓存里的物理源码。
- 🛡️ **安全与凭据完全隔离**：
  - 不保存任何私钥密码，直接复用操作系统的 Git 原生凭据（SSH 密钥系统 / Windows 凭据管理器）；
  - 本地配置文件与 Git 源码缓存已被 `.gitignore` 严格物理屏蔽，绝不上库。

---

## 🚀 快速上手与统一 CLI

SkillBox 将所有运维操作统一收拢在 **`skillbox.bat`**（或快捷方式 `start.bat`）中：

| 操作指令 | 效果说明 |
| :--- | :--- |
| **双击 `skillbox.bat` 或 `start.bat`** | **默认后台静默启动**，不留黑色 CMD 窗口，自动在浏览器打开控制台 |
| **`skillbox start`** (或 `up`) | 后台静默启动服务（自动探活自愈，不重复启动） |
| **`skillbox stop`** (或 `down`) | 安全停止后台服务并释放端口占用 |
| **`skillbox restart`** | 一键重启服务 |
| **`skillbox status`** | 查看当前运行状态、后台 PID、服务端口与开机自启情况 |
| **`skillbox open`** | 在浏览器中打开控制台（`http://127.0.0.1:7860`） |
| **`skillbox update`** | 触发所有 Git 仓库源增量拉取最新代码 |
| **`skillbox autostart on / off`** | 一键开启 / 关闭 Windows 开机静默自启（无需管理员提权） |
| **`skillbox run`** | 前台直接运行服务（用于排错调试查看实时日志） |
| **`skillbox test`** | 一键运行全量自动化单元测试套件 |

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
   - 点击右上角 **「⚡ 应用同步」**，系统秒级在对应目标目录建立符号链接！

---

## 📂 项目结构

```text
skillbox/
├── skillbox.bat           # 统一 CLI 命令与启动入口（双击默认启动）
├── start.bat              # 兼容启动快捷方式（调用 skillbox start）
├── cli.py                 # CLI 命令行逻辑引擎（启停、重启、状态、更新）
├── app.py                 # SkillBox 服务端核心（多仓库引擎 + 递归扫描 + 前端 SPA）
├── run_tests.py           # 自动化单元测试运行器
├── tests/                 # 自动化测试套件 (10 个用例全部通过)
│   ├── test_config.py     # 配置管理与持久化测试
│   ├── test_folder_mount.py # 目录级挂载与继承优先级测试
│   ├── test_scanner.py    # 元数据解析与 Tag 父目录名规则测试
│   ├── test_symlink.py    # Junction 挂载与安全解绑测试
│   ├── test_autostart.py  # Windows 开机自启注册测试
│   └── test_api.py        # HTTP REST API 全链路测试
├── docs/
│   ├── architecture.md    # 系统架构设计文档
│   └── changelog.md       # 变更日志 (Keep a Changelog)
├── ROADMAP.md             # 产品演进路线图
├── .gitignore             # Git 忽略配置
└── README.md              # 本说明文档
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
