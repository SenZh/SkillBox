---
name: skillbox
description: "SkillBox 技能管理器操作指南。当你需要编辑或更新任何已安装的 Skill、知识库，修改后要提交推送到 Git，或需要确认某个 Skill 的真实文件位置时使用。能做什么：按关键词搜索并定位 Skill 的源真身路径（skillbox search <关键词>）、白名单提交并推送指定 Skill 的改动（skillbox commit <name> -m 说明）。"
---

# SkillBox 技能定位与提交指南

> **关键约束**：绝不能直接编辑 `~/.agents/skills/` 下的挂载目录（那只是软链），必须先 `search` 拿到真身路径再改，改完必须 `commit`。

## 什么时候用这个 skill

- **要修改任何 Skill 或知识库文件时** —— 先在这里确认怎么改、改哪儿、怎么提交。
- **改完 Skill 后要提交到 Git 时** —— 用 `skillbox commit` 安全提交，避免改动丢失。
- **不确定某个 Skill 的文件到底在哪个真实目录时** —— 用 `skillbox search` 定位。
- **看到 `~/.agents/skills/` 下的目录，不确定能不能直接编辑时** —— 先读这里。

**触发场景**：写知识库、更新 skill、提交 skill 改动、skill 提交 git、搜索技能、查找 skill、commit 技能、找 skill 真实路径、skill 挂载点、skill 真身路径。

## 能做什么

| 能力 | 命令 | 说明 |
|------|------|------|
| 搜索并定位技能真身路径 | `skillbox search <关键词>` | 按关键词（名称/描述/目录）搜索，输出每个匹配技能的名称、真身路径、描述、所属目录 |
| 提交并推送技能改动 | `skillbox commit <name> -m "说明"` | 白名单提交，只 `git add` 该技能目录，提交前自动先拉取该技能所在仓库 |

> 说明：SkillBox CLI 仅面向 Agent 提供 `search` / `commit` / `help` 三条命令；
> 服务的启停、安装、开机自启等运维操作请在桌面应用中完成。

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

1. **写前先定位**：修改任何 Skill 前，先执行 `skillbox search <关键词>`，从输出里取该技能的**真身路径**。
2. **只写真身**：只对真身路径下的文件读写，**禁止编辑挂载点目录**（那是软链）。
3. **写后必提交**：修改后必须执行 `skillbox commit <name> -m "说明"`，否则改动会在下次自动 `git pull` 时丢失或被覆盖。

---

## 命令详解

### 搜索并定位真身路径

```bash
skillbox search <关键词>
```

输出示例：

```
=== 匹配 [bindcenter] 的技能 (2 个) ===

● bindcenter-knowledge  [已挂载]
  路径: <...>/skills/business/bind-center/bindcenter-knowledge   ← 真身路径
  描述: 绑定中心（bindCenter）知识库。……
  目录: business/bind-center   来源: saas-skill

● bindcenter-agent  [未挂载]
  路径: <...>/skills/business/bind-center/bindcenter-agent
  描述: ……
  目录: business/bind-center   来源: saas-skill
```

- 关键词会同时匹配**名称 / 描述 / 所属目录**；已挂载的技能排在前面。
- 取每一个匹配项的「路径」作为真身路径进行读写。

### 提交并推送

```bash
skillbox commit <name> -m "提交说明"
```

- **提交前自动先拉取该技能所在的 Git 仓库**，降低推送冲突；
- 白名单提交：只 `git add` 该技能目录，不会误带其他未提交改动；
- 自动推送到该仓库配置的远程分支；
- 目录无变更时自动跳过，不报错；
- 追加 `--no-push` 可只提交到本地。

---

## 标准流程

```
1. skillbox search <关键词>          # 找到技能并拿到真身路径
2. 读/写 真身路径 下的文件            # 用普通文件工具直接编辑
3. skillbox commit <name> -m "说明"  # 提交并推送（会先自动拉取）
```

---

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `search` 搜不到目标技能 | 关键词不匹配或仓库未拉取 | 换更短的关键词；在桌面应用里「拉取 Git 更新」后重试 |
| 提示"未被 Git 管理" | 技能不在 Git 仓库内 | 无法提交，确认技能来源 |
| `commit` 提示"目录无变更" | 真身路径下没有实际改动 | 确认是否误写了挂载点而非真身 |
| 修改后未提交 | 遗漏第 3 步 | 立即 `skillbox commit` |
