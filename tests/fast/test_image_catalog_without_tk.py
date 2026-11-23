"""
无 Tk 环境下导入图片目录索引与立绘查找的测试
============================================
本测试在独立子进程中屏蔽 tkinter、_tkinter、PIL.ImageTk 与 Script.Core.main_frame 后，验证
image_catalog 与 character_image 可正常导入并建立与 build_image_path_index 一致的非空索引。
快速层禁止在当前进程导入 image_catalog。本测试因此通过子进程在仓库根目录执行。
"""

import json
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.world import ROOT

WITHOUT_TK = """
import json
import sys

for name in ("tkinter", "_tkinter", "PIL.ImageTk", "Script.Core.main_frame"):
    sys.modules[name] = None
from Script.Config import normal_config

normal_config.init_normal_config()
from Script.Core import image_catalog, image_path_index
from Script.Design import character_image

expected, _ = image_path_index.build_image_path_index(image_catalog.image_dir_path)
print(json.dumps({
    "same_index": image_catalog.image_path_data == expected,
    "indexed": len(image_catalog.image_path_data),
}))
"""
""" 子进程脚本：屏蔽 Tk 与主界面后加载配置，导入 image_catalog 与 character_image 并打印核对 JSON。 """


class ImageCatalogWithoutTkTest(FastTestCase):
    """验证 image_catalog 与 character_image 在无 Tk 环境下可导入并正确建立图片索引。"""

    def test_catalog_and_portrait_lookup_import_without_tk(self) -> None:
        """运行子进程脚本 WITHOUT_TK，断言退出码为 0、图片路径索引一致且索引数量大于 0。"""
        result = subprocess.run(
            [sys.executable, "-c", WITHOUT_TK],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(report["same_index"])
        self.assertGreater(report["indexed"], 0)
