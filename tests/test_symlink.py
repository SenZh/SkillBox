import unittest
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
from app import safe_remove_link

class TestSymlink(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.temp_dir / "source_skill"
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "SKILL.md").write_text("# Real Skill Content", encoding="utf-8")
        self.target_link = self.temp_dir / "target_mounted_skill"

    def tearDown(self):
        safe_remove_link(self.target_link)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_junction_creation_and_safe_removal(self):
        """测试目录联结建立与安全解绑，确认源文件不被误删"""
        # 创建挂载
        if sys.platform == "win32":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(self.target_link), str(self.source_dir)],
                check=True,
                stdout=subprocess.DEVNULL
            )
        else:
            self.target_link.symlink_to(self.source_dir)

        self.assertTrue(self.target_link.exists(), "挂载链接应当存在")
        self.assertTrue((self.target_link / "SKILL.md").exists(), "挂载内容应当可访问")

        # 安全解除挂载
        safe_remove_link(self.target_link)

        # 断言链接已消失
        self.assertFalse(self.target_link.exists(), "解除挂载后链接应当被移除")
        # 断言源真实文件仍然完好
        self.assertTrue(self.source_dir.exists(), "物理源目录必须完好无损")
        self.assertTrue((self.source_dir / "SKILL.md").exists(), "物理源文件必须完好无损")

if __name__ == "__main__":
    unittest.main()
