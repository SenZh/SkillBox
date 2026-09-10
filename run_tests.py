import unittest
import sys
from pathlib import Path

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
