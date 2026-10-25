# -*- coding: UTF-8 -*-
"""
图片按需解码的回归测试
======================
Script.Core.era_image 导入时只建立图片名 -> 路径索引，不解码图片；tk 首次取某张图片时才从磁盘解码，之后一直返回同一个对象。
测试数 PIL.Image.open 的调用次数：启动游戏并开新游戏（其间导入 era_image）、in 检查、首次取图、再次取图各调用几次；
另在索引里加一张解码会失败的图片，检查取到的替代图片与 in 的结果。
PhotoImage 换成记录尺寸的替身，所以不需要 Tk 窗口；字体缩放比例固定为 1.5，检查缩放后的尺寸。
导入 era_image 的测试属于慢速层（快速层不能导入它）。
"""

import os
import tempfile
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
  from typing import Any

  from PIL import Image


class FakePhotoImage:
  """PhotoImage 的替身：只记下传入图片的尺寸"""

  def __init__(self, pil_image: "Image.Image") -> None:
    """
    Keyword arguments:
    pil_image -- PIL.Image.Image，要转换的图片
    Return arguments:
    无
    """
    self.size = pil_image.size


class DecodeOnFirstUseTest(SlowTestCase):
  """启动时只建索引；首次取图时解码一次，之后返回同一个对象；解码失败的图片得到 1x1 的替代图片"""

  def setUp(self) -> None:
    """
    数着 Image.open 的调用启动游戏、开新游戏，再换上 PhotoImage 的替身并固定字体缩放比例
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from PIL import Image

    self.opened: list[str] = []
    """ Image.open 打开过的文件 """
    real_open = Image.open

    def counting_open(
        path: str, *args: "Any", **kwargs: "Any"
    ) -> "Image.Image":
      """
      记录型 Image.open：记下文件，再调用真实的 Image.open
      Keyword arguments:
      path -- 图片文件
      Return arguments:
      与 Image.open 相同
      """
      self.opened.append(path)
      return real_open(path, *args, **kwargs)

    self.real_open = real_open
    patcher = mock.patch.object(Image, "open", counting_open)
    patcher.start()
    self.addCleanup(patcher.stop)
    super().setUp()
    self.opened_at_start = list(self.opened)
    """ 启动游戏与开新游戏期间打开过的文件 """
    from Script.Core import era_image

    self.era_image = era_image
    for name, value in (("PhotoImage", FakePhotoImage), ("_font_scaling", 1.5)):
      era_image_patcher = mock.patch.object(era_image, name, value)
      era_image_patcher.start()
      self.addCleanup(era_image_patcher.stop)

  def test_start_indexes_without_decoding(self) -> None:
    """启动游戏、开新游戏不打开任何图片；索引与 image_path_index 的取舍结果一致，角色索引按文件名首段收录"""
    from Script.Core import image_path_index

    self.assertEqual(self.opened_at_start, [])
    expected_index, _ = image_path_index.build_image_path_index("image")
    self.assertEqual(self.era_image.image_path_data, expected_index)
    expected_by_chara: dict[str, set[str]] = {}
    for name in expected_index:
      if "_" in name:
        expected_by_chara.setdefault(name.split("_")[0], set()).add(name)
    self.assertEqual(
        {
            key: set(names)
            for key, names in self.era_image.image_data_index_by_chara.items()
        },
        expected_by_chara,
    )

  def test_first_use_decodes_once(self) -> None:
    """in 检查不打开图片；首次取图打开它的文件一次并按缩放比例缩放；再次取图不打开文件、返回同一个对象；不存在的图片名 get 给默认值、[] 抛 KeyError"""
    image_data = self.era_image.image_data
    path_data = self.era_image.image_path_data
    name = next(n for n in sorted(path_data) if n.endswith("_半身"))
    with self.real_open(path_data[name]) as img:
      original_size = img.size
    self.opened.clear()
    self.assertIn(name, image_data)
    self.assertNotIn("不存在的图片名", image_data)
    self.assertEqual(self.opened, [])
    first = image_data[name]
    self.assertEqual(self.opened, [path_data[name]])
    self.assertEqual(
        getattr(first, "size", None),
        (int(original_size[0] * 1.5), int(original_size[1] * 1.5)),
    )
    self.opened.clear()
    self.assertIs(image_data[name], first)
    self.assertIs(image_data.get(name), first)
    self.assertEqual(self.opened, [])
    self.assertEqual(image_data.get("不存在的图片名", "默认"), "默认")
    self.assertRaises(KeyError, image_data.__getitem__, "不存在的图片名")

  def test_broken_image_decodes_once(self) -> None:
    """索引里有、解码失败的图片：解码前后 in 都找得到，取到 1x1 的图片，再次取图返回同一个对象，文件只打开一次"""
    image_data = self.era_image.image_data
    temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(temp_dir.cleanup)
    broken_path = os.path.join(temp_dir.name, "测试坏图.png")
    with open(broken_path, "wb") as f:
      f.write(b"not a png")
    patcher = mock.patch.dict(
        self.era_image.image_path_data, {"测试坏图": broken_path}
    )
    patcher.start()
    self.addCleanup(patcher.stop)
    self.assertIn("测试坏图", image_data)
    self.opened.clear()
    broken = image_data.get("测试坏图")
    self.assertEqual(getattr(broken, "size", None), (1, 1))
    self.assertIs(image_data["测试坏图"], broken)
    self.assertEqual(self.opened, [broken_path])
    self.assertIn("测试坏图", image_data)
