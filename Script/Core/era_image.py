"""游戏图片的路径索引与按需解码缓存"""

import os
import threading
import time
from PIL.ImageTk import PhotoImage
from PIL import Image
from Script.Core import game_type, cache_control, image_path_index

image_path_data = {}  # 图片路径数据
image_data_index_by_chara = {}
image_text_data = {}
image_lock = 0
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
image_dir_path = os.path.join("image")

_font_scaling = None
_image_load_lock = threading.Lock()


def _get_font_scaling():
  """
  获取字体缩放比例（缓存结果避免重复计算）
  """
  global _font_scaling
  if _font_scaling is None:
    # Web模式或无Tk环境下，main_frame.normal_font 可能不存在，退化为 1.0
    try:
      from Script.Core import main_frame

      if (
          main_frame is not None
          and getattr(main_frame, "normal_font", None) is not None
      ):
        _font_scaling = main_frame.normal_font.measure("A") / 11
      else:
        _font_scaling = 1.0
    except Exception:
      _font_scaling = 1.0
  return _font_scaling


def _decode_image(image_name):
  """
  从磁盘解码一张图片，按字体缩放比例缩放后转换为 PhotoImage

  Keyword arguments:
  image_name -- str，图片名称（不含扩展名），必须在 image_path_data 中

  Return arguments:
  PhotoImage -- 转换好的图片；解码失败时返回 None
  """
  image_file_path = image_path_data[image_name]
  font_scaling = _get_font_scaling()
  try:
    with Image.open(image_file_path) as img:
      old_width, old_height = img.size
      now_width = int(old_width * font_scaling)
      now_height = int(old_height * font_scaling)
      # 使用BILINEAR，比LANCZOS快且质量可接受
      resized_img = img.resize(
          (now_width, now_height), Image.Resampling.BILINEAR
      )
    return PhotoImage(resized_img)
  except Exception as e:
    print(f"  加载图片失败: {image_file_path} - {e}")
    return None


def index_images_from_directory(directory):
  """
  建立目录下全部图片的名字 -> 路径索引与角色索引，不解码图片

  Keyword arguments:
  directory -- str，图片根目录

  Return arguments:
  无
  """
  start_time = time.time()

  # 每个图片名只取一个文件
  path_index, duplicates = image_path_index.build_image_path_index(directory)
  for image_file_name in sorted(duplicates):
    paths = duplicates[image_file_name]
    print(
        f"图片重名：{image_file_name} 使用 {paths[0]}，忽略 {'、'.join(paths[1:])}"
    )

  if not path_index:
    print("未找到任何图片文件")
    return

  for image_file_name, image_file_path in path_index.items():
    image_path_data[image_file_name] = image_file_path
    # 建立角色索引，键为文件名首段（第一个"_"之前的部分）
    if "_" in image_file_name:
      character_name = image_file_name.split("_")[0]
      image_data_index_by_chara.setdefault(character_name, []).append(
          image_file_name
      )

  elapsed_time = time.time() - start_time
  print(
      f"图片索引完成！共 {len(image_path_data)} 张，耗时 {elapsed_time:.2f} 秒"
  )


class _LazyImageDict(dict):
  """
  按需解码的图片字典
  键是 image_path_data 中的图片名；首次取某张图片时从磁盘解码并保存，此后到进程结束都返回同一个 PhotoImage，不会释放
  解码失败的图片保存为 1x1 的透明图片，tk 显示空白
  """

  def __getitem__(self, key):
    # 已解码的直接返回
    if super().__contains__(key):
      return super().__getitem__(key)
    if key not in self:
      raise KeyError(key)

    # 首次使用时解码；加锁避免同一张图片被解码两次
    with _image_load_lock:
      if super().__contains__(key):
        return super().__getitem__(key)
      photo_image = _decode_image(key)
      if photo_image is None:
        photo_image = PhotoImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
      super().__setitem__(key, photo_image)
      return photo_image

  def __contains__(self, key):
    # 只查索引，不解码
    return key in image_path_data

  def get(self, key, default=None):
    try:
      return self[key]
    except KeyError:
      return default


image_data = _LazyImageDict()

index_images_from_directory(image_dir_path)
