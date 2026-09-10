import unittest
import tempfile
import shutil
from pathlib import Path
from app import resolve_skill_install_dir

class TestFolderMount(unittest.TestCase):
    def test_folder_mount_inheritance_priority(self):
        """测试目录级挂载路径的自底向上多级继承与优先级"""
        default_path = "D:\\global\\agents\\skills"
        parent_folder_path = "D:\\projects\\all-business\\.opencode\\skills"
        sub_folder_path = "D:\\projects\\bind-center\\.opencode\\skills"
        skill_custom_path = "D:\\special\\my-skill"

        cfg = {
            "default_install_to": default_path,
            "folder_overrides": {
                "business": parent_folder_path,
                "business/bind-center": sub_folder_path
            },
            "skill_overrides": {
                "special-skill": skill_custom_path
            }
        }

        # 1. 测试未配置目录的技能 -> 继承全局默认路径
        dir1, src_type1, path_str1, matched1 = resolve_skill_install_dir("kafka-skill", "bigdata", cfg)
        self.assertEqual(src_type1, "default")
        self.assertEqual(path_str1, default_path)

        # 2. 测试配置了父目录 business -> 自动继承父目录
        dir2, src_type2, path_str2, matched2 = resolve_skill_install_dir("user-skill", "business/user-center", cfg)
        self.assertEqual(src_type2, "folder")
        self.assertEqual(path_str2, parent_folder_path)
        self.assertEqual(matched2, "business")

        # 3. 测试同时存在父目录与子目录 -> 优先继承最精准的子目录 business/bind-center
        dir3, src_type3, path_str3, matched3 = resolve_skill_install_dir("binding-skill", "business/bind-center", cfg)
        self.assertEqual(src_type3, "folder")
        self.assertEqual(path_str3, sub_folder_path)
        self.assertEqual(matched3, "business/bind-center")

        # 4. 测试技能本身有专属路径 -> 最高优先级
        dir4, src_type4, path_str4, matched4 = resolve_skill_install_dir("special-skill", "business/bind-center", cfg)
        self.assertEqual(src_type4, "skill")
        self.assertEqual(path_str4, skill_custom_path)

if __name__ == "__main__":
    unittest.main()
