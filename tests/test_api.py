import unittest
import json
import time
import threading
import urllib.request
from app import start_server, stop_server

class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 使用当前进程内嵌后台守护线程启动测试服务（与桌面客户端 desktop_app 运行时架构一致）
        # 彻底避免子进程在 CI 无头环境下的进程间通讯、权限沙箱及防火墙弹窗阻塞
        cls.server, cls.port = start_server(7860, 7880)
        if not cls.server:
            raise RuntimeError("SkillBox 测试服务启动失败：端口范围 7860~7880 均被占用")
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # 毫秒级快速探活确保网络就绪
        deadline = time.time() + 10
        ready = False
        last_err = None
        while time.time() < deadline:
            try:
                resp = urllib.request.urlopen(f"{cls.base_url}/", timeout=1)
                if resp.status == 200:
                    ready = True
                    break
            except Exception as e:
                last_err = e
                time.sleep(0.1)
        if not ready:
            raise RuntimeError(f"SkillBox 测试服务就绪超时 ({cls.base_url}): {last_err}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server") and cls.server:
            stop_server(cls.server)

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
