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

    def test_registry_command_targets_desktop_app(self):
        """自启命令应指向桌面托盘应用（SkillBox.exe 或 desktop_app.py）并以 --startup 静默进托盘"""
        if sys.platform != "win32":
            self.skipTest("仅限 Windows 平台测试")
        import winreg
        from app import AUTOSTART_REG_KEY, AUTOSTART_APP_NAME
        set_autostart(True)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
                cmd_str, _ = winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            low = cmd_str.lower()
            # 目标必须是桌面托盘应用：打包 exe 或 desktop_app.py，两者之一
            self.assertTrue(
                ("skillbox.exe" in low) or ("desktop_app.py" in low),
                f"自启命令应指向桌面托盘应用（SkillBox.exe / desktop_app.py），实际: {cmd_str}",
            )
            # 开机启动时应静默进入托盘
            self.assertIn("--startup", low, "自启命令应携带 --startup 以静默进入系统托盘")
            # 不应再回退到旧的后台隐藏服务入口
            self.assertNotIn("app.py\" --silent", low, "不应再使用旧的后台服务静默入口")
        finally:
            set_autostart(False)

if __name__ == "__main__":
    unittest.main()
