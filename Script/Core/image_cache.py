"""
Tk 图片缓存：image_data 按需从磁盘解码图片，按字体缩放比例生成 PhotoImage 并缓存至进程结束。
成员检查（in）只查询 image_catalog.image_path_data，不解码图片。
解码失败的图片缓存为 1x1 透明 PhotoImage。
"""

import threading
from PIL.ImageTk import PhotoImage
from PIL import Image
from Script.Core import image_catalog

_font_scaling = None
_image_load_lock = threading.Lock()


def _get_font_scaling() -> float:
    """
    获取字体缩放比例（缓存结果避免重复计算）
    """
    global _font_scaling
    if _font_scaling is None:
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


def _decode_image(image_name: str) -> PhotoImage | None:
    """
    从磁盘解码一张图片，按字体缩放比例缩放后转换为 PhotoImage

    Keyword arguments:
    image_name -- str，图片名称（不含扩展名），必须在 image_path_data 中

    Return arguments:
    PhotoImage -- 转换好的图片；解码失败时返回 None
    """
    image_file_path = image_catalog.image_path_data[image_name]
    font_scaling = _get_font_scaling()
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
    """
    按需解码的图片字典
    键是 image_path_data 中的图片名；首次取某张图片时从磁盘解码并保存，此后到进程结束都返回同一个 PhotoImage，不会释放
    解码失败的图片保存为 1x1 的透明图片，tk 显示空白
    """

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
