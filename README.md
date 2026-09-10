# SkillBox 📦

> **基于 Git 原生能力驱动的 AI Agent 技能管理器**  
> 支持多 Git 仓库与独立分支、像文件树一样逐层进入浏览、全局默认与单 Skill 专属安装路径、符号链接零拷贝挂载与后台自动定时更新。

![Version](https://img.shields.io/badge/version-v0.1-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 🌟 为什么选择 SkillBox？

现有的 Agent Skill 管理工具往往存在以下痛点：
1. **无法指定 Git 分支**：对企业内网 GitLab、私有 Git 仓库的分支开发极其不友好，默认只能拉取 main/master；
2. **多层级 Monorepo 无法浏览**：大型仓库内部按业务线分了多层目录，扁平列表直接冲爆界面或无法扫描；
3. **安装目录僵化**：无法区分“全局技能”与“特定项目本地专有技能”；
4. **手动维护成本高**：每次更新需要重新覆盖拷贝，容易破坏本地软链接。

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
- 🏷️ **智能直接父目录名 Tag**：
  - 严格按技能所属的直接父目录名提取 Tag（如 `A/B/C/skill` 对应 `Tag = C`）；
  - 顶部配备 Tag 下拉筛选与快捷 Tag 胶囊栏（Tag Pills），点击卡片标签联动过滤。
- 🎯 **双层安装路径与平滑自动迁移**：
  - **全局默认安装目录**：统一设置所有未特殊指定的技能默认安装位置（如 `~/.agents/skills`）；
  - **单 Skill 专属安装目录**：支持在界面上为任意具体 Skill 单独指定目标目录（例如特定工程本地的 `.opencode/skills`）；
  - **修改默认路径自动迁移**：一旦修改全局默认路径，系统自动在旧位置解绑并在新位置重建软链接，无需人工介入。
- 🔄 **后台静默定时自动更新**：
  - 每个仓库可独立配置自动拉取频率（每 30 分钟、每 1 小时、每 6 小时、每天）；
  - 后台常驻守护线程到期自动 `git pull`；由于采用符号链接机制，Agent 本地读取的代码**全自动秒级变为最新版本**。
- 🔗 **零拷贝与安全解绑**：
  - Windows 原生采用 NTFS 目录联结（Junction，无需管理员权限），类 Unix 采用 Symlink；
  - 解绑采用 Python 原生 `os.rmdir` 安全移除挂载指针，**绝不误伤** Git 缓存里的物理源码。
- 🖥️ **Windows 后台静默运行**：
  - 双击 `start.bat` 秒级启动并脱离 CMD 窗口，自动在浏览器打开控制台，告别烦人的黑色命令框；
  - 提供配套的 `stop.bat`（一键停止）与 `status.bat`（查看状态）。
- 🛡️ **安全与凭据完全隔离**：
  - 不保存任何私钥密码，直接复用操作系统的 Git 原生凭据（SSH 密钥系统 / Windows 凭据管理器）；
  - 本地配置文件与 Git 源码缓存已被 `.gitignore` 严格物理屏蔽，绝不上库。

---

## 🚀 快速上手

### 1. 启动服务 (Windows)

SkillBox 支持完全脱离命令提示符窗口在后台静默运行，并支持注册为开机启动：

* **启动服务**：双击运行根目录下的 **`start.bat`**；
  - 服务在后台静默拉起，并自动在默认浏览器中打开控制台：`http://127.0.0.1:7860`。
* **停止服务**：双击运行 **`stop.bat`**；
* **查看状态**：双击运行 **`status.bat`**。
* **开机自启动**：
  - **方式 1 (推荐)**：在 WebUI 控制台的「⚙️ 仓库与配置」页面，直接开启 **「Windows 开机静默自启服务」** 开关；
  - **方式 2 (脚本)**：双击运行 **`register_autostart.bat`**（取消运行 **`unregister_autostart.bat`**）；
  - *特性：基于当前用户注册表，无需管理员提权，开机在后台静默运行并执行定时更新，不弹出黑框与浏览器。*

> **命令行方式**（前台调试）：
> ```bash
> python app.py
> ```

---

### 2. 使用工作流

1. **设置全局默认安装路径**：
   - 进入顶部导航栏的 **「⚙️ 仓库与配置」** 页面；
   - 在「全局默认安装目录」输入框中填入你的 Agent 技能目录（如 `C:\Users\YourName\.agents\skills`），点击保存。
2. **添加你的 Git 仓库源**：
   - 点击 **「+ 添加仓库源」**；
   - 填写仓库名称、Git 仓库地址（支持 HTTP/HTTPS/SSH）、**指定分支**、**Skill 子目录**，并选择**定时自动更新频率**；
   - 保存时系统将自动拉取该分支并在本地安全建立缓存索引。
3. **浏览与逐层进入**：
   - 切回 **「🗂️ 技能工作区」**；
   - 像操作文件管理器一样，点击文件夹卡片**一层一层进入**目标分类；
   - 随时点击面包屑路径或 `⬅ 返回上一级` 进行回退。
4. **勾选与应用挂载**：
   - 勾选你需要启用的技能（可点击文件夹右上角一键全选）；
   - 如需为某技能单独指定项目路径，点击卡片中的 **「修改」** 按钮；
   - 点击右上角 **「⚡ 应用同步」**，系统秒级在目标目录建立符号链接！

---

## 📂 项目结构

```text
skillbox/
├── app.py                 # SkillBox 核心服务（多仓库引擎 + 递归扫描 + 前端 SPA）
├── start.bat              # Windows 后台静默启动脚本
├── stop.bat               # Windows 安全停止脚本
├── status.bat             # Windows 状态查看脚本
├── register_autostart.bat # 一键注册开机自启脚本
├── unregister_autostart.bat # 一键取消开机自启脚本
├── run_tests.py           # 自动化单元测试运行器
├── tests/                 # 自动化测试套件
│   ├── test_config.py     # 配置管理与持久化测试
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

SkillBox 自带完整的自动化单元测试套件，无需外部框架即可一键运行：

```bash
python run_tests.py
```

或使用标准命令：
```bash
python -m unittest discover tests
```

---

## 📚 更多文档

* 详细系统架构与数据流图：请参阅 [架构设计文档 (docs/architecture.md)](docs/architecture.md)
* 迭代历史与版本记录：请参阅 [变更日志 (docs/changelog.md)](docs/changelog.md)
* 未来规划与生态演进：请参阅 [产品路线图 (ROADMAP.md)](ROADMAP.md)
