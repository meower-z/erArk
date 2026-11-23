"""Tk 前端按需解码、按字体比例缩放并缓存 `PhotoImage` 的图片缓存模块。"""

import threading

from PIL import Image
from PIL.ImageTk import PhotoImage

from Script.Core import image_catalog

_font_scaling: float | None = None
_image_load_lock = threading.Lock()


def set_font_scaling(scaling: float) -> None:
    """
    设置解码图片时应用的字体缩放比例

    参数：
    scaling (float) -- 图片缩放系数

    返回值类型：None
    """
    global _font_scaling
    _font_scaling = scaling


def _decode_image(image_name: str) -> PhotoImage | None:
    image_file_path = image_catalog.image_path_data[image_name]
    font_scaling = 1.0 if _font_scaling is None else _font_scaling
    try:
        with Image.open(image_file_path) as img:
            old_width, old_height = img.size
            now_width = int(old_width * font_scaling)
            now_height = int(old_height * font_scaling)
            resized_img = img.resize(
                (now_width, now_height), Image.Resampling.BILINEAR
            )
        return PhotoImage(resized_img)
    except Exception as e:
        print(f"  加载图片失败: {image_file_path} - {e}")
        return None


class _LazyImageDict(dict):
    """首次按键读取时加锁解码、缩放并缓存 `PhotoImage` 的字典子类，解码失败时缓存 1x1 透明占位图。"""

    def __getitem__(self, key: str) -> PhotoImage:
        if super().__contains__(key):
            return super().__getitem__(key)
        if key not in self:
            raise KeyError(key)

        with _image_load_lock:
            if super().__contains__(key):
                return super().__getitem__(key)
            photo_image = _decode_image(key)
            if photo_image is None:
                photo_image = PhotoImage(
                    Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                )
            super().__setitem__(key, photo_image)
            return photo_image

    def __contains__(self, key: object) -> bool:
        return key in image_catalog.image_path_data

    def get(self, key: str, default: object = None) -> object:
        try:
            return self[key]
        except KeyError:
            return default


image_data = _LazyImageDict()
"""全局按需解码的 Tk `PhotoImage` 图片缓存字典实例。"""
