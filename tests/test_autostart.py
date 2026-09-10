import unittest
import sys
from app import get_autostart_status, set_autostart

class TestAutostart(unittest.TestCase):
    def test_autostart_lifecycle(self):
        """测试开机自启动项的注册、状态查询与安全注销全流程"""
        if sys.platform != "win32":
            self.skipTest("仅限 Windows 平台测试")

        # 1. 注册自启动
        res_enable = set_autostart(True)
        self.assertTrue(res_enable)
        status_after_enable = get_autostart_status()
        self.assertTrue(status_after_enable, "注册后状态应当为 True")

        # 2. 取消自启动
        res_disable = set_autostart(False)
        self.assertFalse(res_disable)
        status_after_disable = get_autostart_status()
        self.assertFalse(status_after_disable, "注销后状态应当为 False")

if __name__ == "__main__":
    unittest.main()
