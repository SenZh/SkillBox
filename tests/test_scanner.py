import unittest
import tempfile
import shutil
from pathlib import Path
from app import parse_skill_metadata, scan_all_skills

class TestScanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_skill_metadata(self):
        """测试 SKILL.md frontmatter 与简介解析"""
        skill_dir = self.temp_dir / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: 这是一个测试技能工具\ntags: [python, test]\n---\n# Content",
            encoding="utf-8"
        )

        desc, tags = parse_skill_metadata(skill_dir)
        self.assertEqual(desc, "这是一个测试技能工具")
        self.assertEqual(tags, ["python", "test"])

    def test_tag_rule_and_recursive_scanning(self):
        """测试 Tag 严格按照直接所属目录名计算 (A/B/C 下 tag=C)"""
        # 构建目录: skills/business/bind-center/my-skill/SKILL.md
        repo_dir = self.temp_dir / "repo"
        skill_dir = repo_dir / "skills" / "business" / "bind-center" / "my-binding-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: my-binding-skill\ndescription: 测试绑定\n---\n", encoding="utf-8")

        # 模拟配置
        import app
        original_cache = app.CACHE_BASE_DIR
        try:
            app.CACHE_BASE_DIR = self.temp_dir
            # source id 对应 repo_dir.name
            src_id = "test_src"
            (self.temp_dir / src_id).mkdir(parents=True, exist_ok=True)
            # 移动 repo 到 test_src
            shutil.copytree(repo_dir, self.temp_dir / src_id, dirs_exist_ok=True)

            cfg = {
                "default_install_to": str(self.temp_dir / "installed"),
                "sources": [
                    {
                        "id": src_id,
                        "name": "测试仓",
                        "branch": "main",
                        "sub_dir": "skills"
                    }
                ],
                "skill_overrides": {}
            }

            skills = scan_all_skills(cfg)
            self.assertEqual(len(skills), 1)
            s = skills[0]
            self.assertEqual(s["name"], "my-binding-skill")
            # 验证 Tag 必须是直接父目录名: bind-center
            self.assertEqual(s["tag"], "bind-center")
            # 验证所属完整路径为: business/bind-center
            self.assertEqual(s["folder_path"], "business/bind-center")
        finally:
            app.CACHE_BASE_DIR = original_cache

if __name__ == "__main__":
    unittest.main()
