# -*- coding: utf-8 -*-
"""
控制台缓存仓库的拉取健壮性测试。

覆盖场景：
1. 缓存仓库存在本地已跟踪改动 + 上游新增同名未跟踪文件 → 仍能拉取成功且不报错（历史故障）
2. 拉取上游确实前进时，本地改动落盘到 .skillbox_conflicts，不覆盖上游版本
3. 上游未前进时，本地改动还原回工作区，不丢失
4. 日志按体积轮转，轮转后仍可继续写入
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app


def git(*args, cwd):
    res = subprocess.run(
        ["git"] + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {res.stderr or res.stdout}")
    return res.stdout.strip()


class GitRepoHarness:
    """构造「远端 bare 仓库 + 本地缓存克隆」两段式测试环境"""

    def __init__(self, root: Path):
        self.root = root
        self.remote = root / "remote.git"
        self.work = root / "upstream"
        git("init", "--bare", "-b", "main", str(self.remote), cwd=root)
        self.work.mkdir()
        git("init", "-b", "main", str(self.work), cwd=root)
        git("config", "user.email", "t@example.com", cwd=self.work)
        git("config", "user.name", "tester", cwd=self.work)
        (self.work / "a.txt").write_text("v1\n", encoding="utf-8")
        git("add", ".", cwd=self.work)
        git("commit", "-m", "init", cwd=self.work)
        git("remote", "add", "origin", str(self.remote), cwd=self.work)
        git("push", "-u", "origin", "main", cwd=self.work)

    def push_change(self, rel_path: str, content: str, commit_msg: str = "upstream"):
        target = self.work / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git("add", ".", cwd=self.work)
        git("commit", "-m", commit_msg, cwd=self.work)
        git("push", "origin", "main", cwd=self.work)


class TestPullSingleSource(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self._orig_cache = app.CACHE_BASE_DIR
        app.CACHE_BASE_DIR = self.temp_dir / "cache"
        app.CACHE_BASE_DIR.mkdir(parents=True)
        self.harness = GitRepoHarness(self.temp_dir)
        self.src = {
            "id": "src-test",
            "name": "测试仓库",
            "git_url": str(self.harness.remote),
            "branch": "main",
            "auto_update_interval": 0,
        }
        # 首次拉取建立缓存
        app.pull_single_source(self.src)
        self.cache_dir = app.CACHE_BASE_DIR / "src-test"

    def tearDown(self):
        app.CACHE_BASE_DIR = self._orig_cache
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_changes_and_upstream_untracked_do_not_block_pull(self):
        """历史故障复现：本地改了已跟踪文件 + 上游新增同名未跟踪文件，pull 必须成功"""
        # 本地修改已跟踪文件
        (self.cache_dir / "a.txt").write_text("local-edit\n", encoding="utf-8")
        # 本地自建未跟踪文件
        (self.cache_dir / "bin").mkdir()
        (self.cache_dir / "bin" / "tool.sh").write_text("#!/bin/sh\n", encoding="utf-8")

        # 上游推进：修改 a.txt，并提交同名未跟踪文件 tool.sh
        self.harness.push_change("a.txt", "v2-upstream\n")
        self.harness.push_change("bin/tool.sh", "#!/bin/sh\necho upstream\n")

        app.pull_single_source(self.src)  # 修复前这里会抛 overwritten by merge

        self.assertEqual((self.cache_dir / "a.txt").read_text(encoding="utf-8"), "v2-upstream\n")
        self.assertEqual(
            (self.cache_dir / "bin" / "tool.sh").read_text(encoding="utf-8"),
            "#!/bin/sh\necho upstream\n",
            "上游版本必须生效，不能被本地未跟踪文件挡住",
        )
        # 工作区必须干净，否则下一次 pull 还会被本地改动拦住
        self.assertEqual(git("status", "--porcelain", cwd=self.cache_dir), "")

    def test_local_changes_archived_when_upstream_advances(self):
        """上游前进时：本地改动落盘留档（含 patch 与完整文件），不覆盖上游"""
        (self.cache_dir / "a.txt").write_text("local-only-change\n", encoding="utf-8")
        self.harness.push_change("a.txt", "v2-upstream\n")

        app.pull_single_source(self.src)

        self.assertEqual((self.cache_dir / "a.txt").read_text(encoding="utf-8"), "v2-upstream\n")
        snapshots = list((app.CACHE_BASE_DIR / ".skillbox_conflicts" / "src-test").glob("*/changes.patch"))
        self.assertTrue(snapshots, "本地改动必须落盘留档")
        patch_text = snapshots[0].read_text(encoding="utf-8")
        self.assertIn("local-only-change", patch_text)
        self.assertTrue((snapshots[0].parent / "README.txt").exists())

    def test_local_changes_restored_when_upstream_unchanged(self):
        """上游未前进时：本地改动应还原回工作区，不应被吞掉"""
        (self.cache_dir / "a.txt").write_text("local-only-change\n", encoding="utf-8")

        app.pull_single_source(self.src)

        self.assertEqual((self.cache_dir / "a.txt").read_text(encoding="utf-8"), "local-only-change\n")
        self.assertNotIn(
            "a.txt",
            git("stash", "list", cwd=self.cache_dir),
            "stash 必须被消费掉，不能越积越多",
        )

    def test_last_updated_recorded(self):
        app.pull_single_source(self.src)
        self.assertTrue(self.src.get("last_updated"))
        self.assertGreater(self.src.get("last_pulled_ts", 0), 0)


class TestLogRotation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self._orig_log = app.LOG_FILE
        self._orig_max = app.LOG_MAX_BYTES
        self._orig_every = app.LOG_CHECK_EVERY
        app.LOG_FILE = self.temp_dir / "skillbox.log"
        app.LOG_MAX_BYTES = 2048
        app.LOG_CHECK_EVERY = 1
        app._log_write_count = 0

    def tearDown(self):
        app.LOG_FILE = self._orig_log
        app.LOG_MAX_BYTES = self._orig_max
        app.LOG_CHECK_EVERY = self._orig_every
        app._log_write_count = 0
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_rotates_and_keeps_writing(self):
        for i in range(400):
            app.log(f"line-{i} " + "x" * 100)

        rotated = app.LOG_FILE.with_name(app.LOG_FILE.name + ".1")
        self.assertTrue(rotated.exists(), "超过上限后必须生成轮转文件")
        self.assertLess(app.LOG_FILE.stat().st_size, 2048 * 2, "当前日志不应无限增长")
        self.assertGreater(app.LOG_FILE.stat().st_size, 0, "轮转后必须能继续写入")


if __name__ == "__main__":
    unittest.main()
