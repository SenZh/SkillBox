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

    def test_registry_value_preserves_path_case(self):
        """注册表中写入的命令应保留 pythonw.exe 路径原始大小写，且可回读"""
        if sys.platform != "win32":
            self.skipTest("仅限 Windows 平台测试")
        import winreg
        from app import AUTOSTART_REG_KEY, AUTOSTART_APP_NAME
        set_autostart(True)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
                cmd_str, _ = winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            self.assertIn("pythonw.exe", cmd_str.lower(), "自启命令应使用 pythonw.exe 静默运行")
            self.assertNotIn("python.exe\"", cmd_str.lower(), "不应回退到非静默的 python.exe")
        finally:
            set_autostart(False)

if __name__ == "__main__":
    unittest.main()
