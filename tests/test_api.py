import unittest
import json
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 后台启动测试实例（使用当前解释器，保证跨平台可用）
        cls.base_url = "http://127.0.0.1:7860"
        cls.proc = subprocess.Popen(
            [sys.executable, "-u", "app.py"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # 轮询探活：干净环境首次启动较慢，固定 sleep 会在慢机器/CI 上导致竞态失败
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            try:
                resp = urllib.request.urlopen(f"{cls.base_url}/", timeout=1)
                if resp.status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)
        if not ready:
            raise RuntimeError("SkillBox 测试服务未能在 20 秒内就绪")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            cls.proc.wait()

    def test_get_index(self):
        """测试首页 HTML 响应正常并包含核心 UI 标识"""
        resp = urllib.request.urlopen(f"{self.base_url}/", timeout=3)
        self.assertEqual(resp.status, 200)
        content = resp.read().decode("utf-8")
        self.assertIn("SkillBox", content)
        self.assertIn("v0.2", content)
        self.assertIn("breadcrumb-nav", content)

    def test_get_config(self):
        """测试获取全局配置接口"""
        resp = urllib.request.urlopen(f"{self.base_url}/api/config", timeout=3)
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("default_install_to", data)
        self.assertIn("sources", data)

    def test_get_skills(self):
        """测试获取技能列表接口"""
        resp = urllib.request.urlopen(f"{self.base_url}/api/skills", timeout=3)
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("skills", data)
        self.assertIsInstance(data["skills"], list)

if __name__ == "__main__":
    unittest.main()
