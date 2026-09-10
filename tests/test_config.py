import unittest
import json
import tempfile
import shutil
from pathlib import Path
from app import load_config, save_config, DEFAULT_CONFIG

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "config.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config_structure(self):
        """验证默认配置包含必需字段"""
        self.assertIn("default_install_to", DEFAULT_CONFIG)
        self.assertIn("sources", DEFAULT_CONFIG)
        self.assertIn("skill_overrides", DEFAULT_CONFIG)

    def test_save_and_load_config(self):
        """验证配置的持久化与读取正确性"""
        import app
        original_config_file = app.CONFIG_FILE
        try:
            app.CONFIG_FILE = self.config_path
            custom_cfg = {
                "default_install_to": "D:\\custom\\install",
                "sources": [
                    {
                        "id": "src-1",
                        "name": "测试仓库",
                        "git_url": "https://git.example.com/skills.git",
                        "branch": "dev",
                        "sub_dir": "skills",
                        "auto_update_interval": 60
                    }
                ],
                "skill_overrides": {
                    "my-skill": "D:\\project\\skills"
                }
            }
            save_config(custom_cfg)
            loaded = load_config()

            self.assertEqual(loaded["default_install_to"], "D:\\custom\\install")
            self.assertEqual(len(loaded["sources"]), 1)
            self.assertEqual(loaded["sources"][0]["name"], "测试仓库")
            self.assertEqual(loaded["skill_overrides"]["my-skill"], "D:\\project\\skills")
        finally:
            app.CONFIG_FILE = original_config_file

if __name__ == "__main__":
    unittest.main()
