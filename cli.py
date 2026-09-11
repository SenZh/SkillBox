#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillBox Agent 命令行工具 (Agent CLI)

专为 AI Agent 设计的轻量 CLI，仅提供三个命令：
  - search   按关键词搜索技能，输出名称 + 真身路径 + 描述（供 Agent 定位技能）
  - commit   白名单提交并推送单个技能目录（提交前自动拉取该技能所在仓库）
  - help     显示帮助

服务的启停、安装、开机自启、桌面图标等运维能力已迁移到
桌面托盘应用（SkillBox.exe）与 WebUI，本 CLI 不再承担。
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def cmd_search(keyword):
    """按关键词搜索技能：匹配名称 / 描述 / 所属目录，输出真身路径与描述"""
    if not keyword:
        print("[!] 用法: skillbox search <关键词>")
        return 1

    from app import load_config, scan_all_skills

    kw = keyword.lower()
    try:
        cfg = load_config()
        skills = scan_all_skills(cfg)
    except Exception as e:
        print(f"[!] 搜索失败: {e}")
        return 1

    matched = [
        s for s in skills
        if kw in s["name"].lower()
        or kw in (s.get("desc") or "").lower()
        or kw in (s.get("folder_path") or "").lower()
        or kw in (s.get("tag") or "").lower()
    ]

    if not matched:
        print(f"[*] 未找到匹配 [{keyword}] 的技能。")
        return 1

    matched.sort(key=lambda s: (not s.get("installed"), s["name"]))
    print(f"=== 匹配 [{keyword}] 的技能 ({len(matched)} 个) ===")
    for s in matched:
        status = "已挂载" if s.get("installed") else "未挂载"
        print(f"\n● {s['name']}  [{status}]")
        print(f"  路径: {s['source_path']}")
        print(f"  描述: {s.get('desc') or '无描述'}")
        print(f"  目录: {s.get('folder_path') or '(根)'}   来源: {s.get('source_name')}")
    print("\n提示: 使用 `skillbox commit <名称> -m \"说明\"` 提交该技能改动。")
    return 0


def cmd_commit(name, message, push=True):
    """提交并推送单个技能目录（白名单提交，仅限该技能目录）"""
    if not name:
        print('[!] 用法: skillbox commit <技能名称> -m "提交说明"')
        return 1

    from app import load_config, resolve_skill, git_cmd, pull_single_source

    try:
        cfg = load_config()
        info = resolve_skill(name, cfg)
    except Exception as e:
        print(f"[!] 解析技能失败: {e}")
        return 1

    if not info["git_managed"]:
        print(f"[!] 技能 [{name}] 未被 Git 管理，跳过提交。")
        return 2

    repo_dir = info["git_dir"]
    branch = info["git_branch"]
    pathspec = info["sub_dir"]
    if not pathspec:
        print(f"[!] 技能 [{name}] 相对路径解析失败，拒绝提交（避免误伤其他文件）。")
        return 3

    # 提交前先拉取该技能所在的 Git 仓库，尽量降低推送冲突
    try:
        src = next((x for x in cfg.get("sources", []) if x.get("id") == info.get("source_id")), None)
        if src:
            print(f"[*] 提交前先拉取仓库 [{src.get('name')}] ...")
            pull_single_source(src)
        else:
            print("[*] 未找到对应仓库源，跳过拉取。")
    except Exception as e:
        print(f"[!] 拉取仓库失败（继续提交）: {e}")

    try:
        git_cmd(["add", "--", pathspec], cwd=repo_dir)
        status = git_cmd(["status", "--porcelain", "--", pathspec], cwd=repo_dir)
        if not status.strip():
            print(f"[*] 技能 [{name}] 目录无变更，无需提交。")
            return 0
        git_cmd(["commit", "-m", message or f"chore(skill): update {name}"], cwd=repo_dir)
        committed_hash = git_cmd(["rev-parse", "--short", "HEAD"], cwd=repo_dir)
        print(f"[OK] 已提交 {committed_hash} (分支: {branch})")
        if push:
            git_cmd(["push", "origin", branch], cwd=repo_dir)
            print(f"[OK] 已推送到 origin/{branch}")
        return 0
    except Exception as e:
        print(f"[!] 提交失败: {e}")
        return 1


def print_help():
    print("""
SkillBox Agent CLI (v0.2)

用法:
  skillbox search <关键词>            按关键词搜索技能，输出名称 + 真身路径 + 描述
  skillbox commit <名称> [-m "说明"]  白名单提交并推送该技能目录（提交前自动拉取所在仓库）
  skillbox help                       显示本帮助

说明:
  - 本 CLI 面向 AI Agent，仅负责技能检索与提交；
  - 服务的启停、安装、开机自启、桌面图标等请在桌面应用中完成。
""")


def main():
    args = sys.argv[1:]
    if not args:
        print_help()
        return 0

    cmd = args[0].lower()

    if cmd in ("help", "-h", "--help"):
        print_help()
        return 0

    if cmd in ("search", "find", "query"):
        return cmd_search(args[1] if len(args) > 1 else "")

    if cmd == "commit":
        sub_args = args[1:]
        msg = ""
        no_push = False
        positional = []
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-m", "--message"):
                msg = sub_args[i + 1] if i + 1 < len(sub_args) else ""
                i += 2
                continue
            if a in ("--no-push", "--local"):
                no_push = True
            else:
                positional.append(a)
            i += 1
        return cmd_commit(positional[0] if positional else "", msg, push=not no_push)

    print(f"[!] 未知命令: {cmd}")
    print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
