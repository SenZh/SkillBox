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
        # 后台启动测试实例（使用当前解释器，保证跨平台可用；--silent 避免无头环境弹出浏览器）
        repo_root = Path(__file__).resolve().parent.parent
        cls.pid_file = repo_root / ".skillbox.pid"
        cls.base_url = "http://127.0.0.1:7860"
        cls.proc = subprocess.Popen(
            [sys.executable, "-u", "app.py", "--silent"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # 轮询探活：自适应解析实际绑定端口（若 7860 冲突则自动跟随降级端口）
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            if cls.pid_file.exists():
                try:
                    parts = cls.pid_file.read_text(encoding="utf-8").strip().split(":")
                    if len(parts) >= 2 and parts[1].isdigit():
                        cls.base_url = f"http://127.0.0.1:{parts[1]}"
                except Exception:
                    pass
            try:
                resp = urllib.request.urlopen(f"{cls.base_url}/", timeout=1)
                if resp.status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)
        if not ready:
            # 探活失败：收集子进程状态与输出，便于定位“服务为何没起来”
            diag = [f"SkillBox 测试服务未能在 20 秒内就绪 (base_url={cls.base_url})"]
            diag.append(f"子进程 returncode={cls.proc.poll()}")
            try:
                out, err = cls.proc.communicate(timeout=3)
                diag.append(f"--- app.py stdout ---\n{(out or '').strip()}")
                diag.append(f"--- app.py stderr ---\n{(err or '').strip()}")
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                out, err = cls.proc.communicate()
                diag.append("[子进程仍在运行，已被 kill]")
                diag.append(f"--- app.py stdout ---\n{(out or '').strip()}")
                diag.append(f"--- app.py stderr ---\n{(err or '').strip()}")
            raise RuntimeError("\n".join(diag))

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
