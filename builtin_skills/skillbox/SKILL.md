---
name: skillbox
description: "SkillBox 技能管理器操作指南。当你需要编辑或更新任何已安装的 Skill、知识库，修改后要提交推送到 Git，或需要确认某个 Skill 的真实文件位置时使用。能做什么：定位 Skill 的源真身路径（skillbox resolve <name>）、白名单提交并推送指定 Skill 的改动（skillbox commit <name> -m 说明）。"
---

# SkillBox 技能定位与提交指南

> **关键约束**：绝不能直接编辑 `~/.agents/skills/` 下的挂载目录（那只是软链），必须先 `resolve` 拿到真身路径再改，改完必须 `commit`。

## 什么时候用这个 skill

- **要修改任何 Skill 或知识库文件时** —— 先在这里确认怎么改、改哪儿、怎么提交。
- **改完 Skill 后要提交到 Git 时** —— 用 `skillbox commit` 安全提交，避免改动丢失。
- **不确定某个 Skill 的文件到底在哪个真实目录时** —— 用 `skillbox resolve` 定位。
- **看到 `~/.agents/skills/` 下的目录，不确定能不能直接编辑时** —— 先读这里。

**触发场景**：写知识库、更新 skill、提交 skill 改动、skill 提交 git、resolve 技能、commit 技能、找 skill 真实路径、skill 挂载点、skill 真身路径。

## 能做什么

| 能力 | 命令 | 说明 |
|------|------|------|
| 定位技能真身路径 | `skillbox resolve <name>` | 输出源真身路径、Git 目录、相对子路径、目标分支、挂载位置；最后一行是纯真身路径 |
| 提交并推送技能改动 | `skillbox commit <name> -m "说明"` | 白名单提交，只 `git add` 该技能目录，自动推送到配置分支 |

---

## 背景：为什么不能直接编辑

SkillBox 通过符号链接（Windows 为 NTFS Junction）把 Git 仓库里的 Skill 挂载到 Agent 技能目录。

**关键认知：挂载点只是链接，真身在 SkillBox 的本地缓存仓库里。** 直接编辑挂载点看似生效，实际会造成 Git 仓库错位、提交丢失、被自动拉取覆盖。

```
~/.agents/skills/foo   ──(软链)──►   <SkillBox缓存>/.../foo   ← 真正要读写的地方
     挂载点（别碰）                        真身（读写这里）
```

---

## 硬规则（必须遵守）

1. **写前先定位**：修改任何 Skill 前，先执行 `skillbox resolve <name>`，取输出**最后一行的绝对路径**作为真身路径。
2. **只写真身**：只对真身路径下的文件读写，**禁止编辑挂载点目录**（那是软链）。
3. **写后必提交**：修改后必须执行 `skillbox commit <name> -m "说明"`，否则改动会在下次自动 `git pull` 时丢失或被覆盖。

---

## 命令详解

### 定位真身路径

```bash
skillbox resolve <name>
```

输出示例：

```
技能名称 : bindcenter-knowledge
源真身路径: <...>/skills/.../bindcenter-knowledge
Git 管理 : [ YES ] 是
Git 目录 : <...>/src-xxxxxxxx
相对子路径: skills/.../bindcenter-knowledge
目标分支 : dev
挂载位置 :  - ~/.agents/skills/.../bindcenter-knowledge
============================================================
<...>/skills/.../bindcenter-knowledge          ← 最后一行：真身路径
```

- 被 Git 管理：显示 `Git 管理 : [ YES ] 是` 与 Git 目录；
- 未被 Git 管理：显示 `Git 管理 : [ NO ] 未被任何 Git 仓库管理`，此时无法提交。

### 提交并推送

```bash
skillbox commit <name> -m "提交说明"
```

- 白名单提交：只 `git add` 该技能目录，不会误带其他未提交改动；
- 自动推送到该仓库配置的远程分支；
- 目录无变更时自动跳过，不报错；
- 追加 `--no-push` 可只提交到本地。

---

## 标准流程

```
1. skillbox resolve <name>        # 拿到真身路径
2. 读/写 真身路径 下的文件          # 用普通文件工具直接编辑
3. skillbox commit <name> -m "说明" # 提交并推送
```

---

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `resolve` 报"未找到技能" | 名称错误或仓库未拉取 | 核对名称；`skillbox update` 拉取最新 |
| 提示"未被 Git 管理" | 技能不在 Git 仓库内 | 无法提交，确认技能来源 |
| `commit` 提示"目录无变更" | 真身路径下没有实际改动 | 确认是否误写了挂载点而非真身 |
| 修改后未提交 | 遗漏第 3 步 | 立即 `skillbox commit` |
| `sync` 报"安全阀拦截" | 勾选集骤减触发保护 | 确需批量解绑时传 `allow_shrink=true` |
