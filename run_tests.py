import unittest
import sys
from pathlib import Path

# CI 的 Windows runner 默认 stdout 编码为 cp1252，打印中文测试标题会抛
# UnicodeEncodeError 导致测试在收集阶段就崩溃。这里强制切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def run_all_tests():
    print("=" * 60)
    print("       SkillBox v0.1 - 自动化单元测试套件")
    print("=" * 60)
    
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(Path(__file__).parent / "tests"),
        pattern="test_*.py"
    )
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"[SUCCESS] 全部单测通过！运行测试用例数: {result.testsRun}")
        return 0
    else:
        print(f"[FAILURE] 存在失败用例: 错误 {len(result.errors)}, 失败 {len(result.failures)}")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
