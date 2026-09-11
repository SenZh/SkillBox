# 贡献指南 (Contributing)

感谢你对 SkillBox 的关注！欢迎通过 Issue 与 Pull Request 参与共建。

---

## 🐛 报告问题

提交 Issue 前请先搜索是否已有相同问题。报告时请尽量包含：

- 操作系统与版本（Windows 10/11、macOS、Linux 发行版）
- Python 版本（`python --version`）
- SkillBox 版本（`skillbox status` 或界面右上角）
- 复现步骤、期望结果、实际结果
- 相关日志（`skillbox log` 或 `skillbox.log`）

## 💡 贡献代码

### 1. 开发环境

```bash
git clone https://github.com/SenZh/SkillBox.git
cd SkillBox

# 安装桌面应用运行依赖（可选，纯 CLI 开发可不装）
pip install -r requirements.txt

# 安装开发/打包依赖（可选）
pip install pyinstaller
```

### 2. 目录结构

```text
skillbox/
├── cli.py              # Agent CLI（search / commit / help）
├── app.py              # 服务端核心（HTTP 服务 + 多仓库引擎 + 内嵌 WebUI）
├── desktop_app.py      # 桌面托盘应用（原生窗口 + 系统托盘 + 内嵌服务）
├── platform_utils.py   # 跨平台工具库（快捷方式/应用模式/启动器）
├── builtin_skills/     # 随版本分发的内置技能
├── assets/             # 图标资源
├── tools/              # 构建脚本（图标生成 / exe 打包 / release 打包）
├── tests/              # 自动化单元测试
└── docs/               # 架构与补充文档
```

### 3. 编码规范

- 遵循 PEP 8；模块、函数、变量使用英文命名，注释与用户可见文案使用中文。
- 纯 CLI 功能尽量保持**零第三方依赖**（仅标准库），桌面相关依赖集中在 `desktop_app.py`。
- 不引入与现有架构耦合度高的重型依赖。
- **不要**在代码中硬编码任何密钥、Token 或绝对路径。

### 4. 提交前自检

```bash
# 运行全量单元测试，必须全部通过
python run_tests.py
```

- 新增/修改功能请同步补充或更新 `tests/` 下的测试用例。
- 面向用户的变更请在 `CHANGELOG.md` 的 `[Unreleased]` 或对应版本段落中记录。

### 5. 提交信息规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```text
<type>(<scope>): <subject>

feat(desktop): 新增关闭窗口缩到系统托盘
fix(cli): 修复 resolve 未找到技能时的报错
docs(readme): 补充 Release 安装说明
```

常用 `type`：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `build`。

### 6. Pull Request

- 从最新的 `main` 拉出功能分支，一个 PR 聚焦一件事。
- PR 描述中说明：改动动机、实现方式、验证方式（测试命令/截图）。
- 确保 CI（若配置）通过、`python run_tests.py` 全绿。

---

## 📦 构建与打包

```bash
# 单文件 exe（需 pyinstaller）
python tools/build_exe.py

# Release 成果物（zip 免安装包 + Inno Setup 安装包脚本）
python tools/build_release.py
```

详见 `tools/` 下脚本内的说明。

---

## 📄 许可

本项目采用 [MIT License](LICENSE)。你提交的代码将以相同许可协议发布。
