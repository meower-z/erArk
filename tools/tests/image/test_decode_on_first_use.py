# -*- coding: UTF-8 -*-
"""
图片按需解码的回归测试
======================
Script.Core.era_image 导入时只建立图片名 -> 路径索引，不解码图片；tk 首次取某张图片时才从磁盘解码，之后一直返回同一个对象。
测试数 PIL.Image.open 的调用次数：导入期间、in 检查、首次取图、再次取图各调用几次；另在索引里加一张解码会失败的图片，检查取到的替代图片与 in 的结果。
PhotoImage 换成记录尺寸的替身，所以不需要 Tk 窗口；字体缩放比例固定为 1.5，检查缩放后的尺寸。

导入 era_image，需在仓库根目录运行：python tools/tests/image/test_decode_on_first_use.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import os
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

results = {"pass": 0, "fail": 0}


def check(label, condition, detail=""):
    """
    记录一条断言并打印结果
    Keyword arguments:
    label -- str，断言说明
    condition -- bool，断言是否成立
    detail -- str，失败时附带打印的信息
    Return arguments:
    无
    """
    if condition:
        results["pass"] += 1
        print(f"[OK] {label}")
    else:
        results["fail"] += 1
        print(f"[FAIL] {label} {detail}")


def finish():
    """
    打印汇总并按结果退出；导入链可能起非守护线程，用 os._exit 结束
    Return arguments:
    无
    """
    print(f"PASS={results['pass']} FAIL={results['fail']}")
    sys.stdout.flush()
    os._exit(1 if results["fail"] else 0)


class FakePhotoImage:
    """PhotoImage 的替身：只记下传入图片的尺寸"""

    def __init__(self, pil_image):
        """
        Keyword arguments:
        pil_image -- PIL.Image.Image，要转换的图片
        """
        self.size = pil_image.size


def main():
    """
    导入 era_image，检查导入、in 检查、首次取图与再次取图各自解码几次
    Return arguments:
    无
    """
    os.chdir(REPO_ROOT)
    from PIL import Image
    from Script.Core import image_path_index

    # 数 Image.open 的调用次数
    opened = []
    real_open = Image.open

    def counting_open(path, *args, **kwargs):
        """记录被打开的文件，再调用真实的 Image.open"""
        opened.append(path)
        return real_open(path, *args, **kwargs)

    Image.open = counting_open
    try:
        from Script.Core import era_image
    finally:
        Image.open = real_open
    check("导入 era_image 时不打开任何图片", len(opened) == 0, f"打开了 {len(opened)} 张")

    # 索引与 image_path_index 的取舍结果一致
    expected_index, _ = image_path_index.build_image_path_index("image")
    check("image_path_data 收录 image 目录下的全部图片名", era_image.image_path_data == expected_index, f"{len(era_image.image_path_data)} 对 {len(expected_index)}")
    expected_by_chara = {}
    for name in expected_index:
        if "_" in name:
            expected_by_chara.setdefault(name.split("_")[0], set()).add(name)
    check("角色索引按文件名首段收录图片", {key: set(names) for key, names in era_image.image_data_index_by_chara.items()} == expected_by_chara)

    # 取一张真实存在的立绘
    name = next((n for n in sorted(expected_index) if n.endswith("_半身")), sorted(expected_index)[0])
    with real_open(expected_index[name]) as img:
        original_size = img.size

    era_image.PhotoImage = FakePhotoImage
    era_image._font_scaling = 1.5
    Image.open = counting_open
    try:
        opened.clear()
        check(f"in 检查能找到 {name}", name in era_image.image_data)
        check("in 检查找不到不存在的图片名", "不存在的图片名" not in era_image.image_data)
        check("in 检查不打开图片", len(opened) == 0, f"打开了 {opened}")

        first = era_image.image_data[name]
        check("首次取图时打开它的文件一次", opened == [expected_index[name]], f"打开了 {opened}")
        check("取到的图片按字体缩放比例缩放", getattr(first, "size", None) == (int(original_size[0] * 1.5), int(original_size[1] * 1.5)), f"原始 {original_size}，得到 {getattr(first, 'size', None)}")

        opened.clear()
        second = era_image.image_data[name]
        by_get = era_image.image_data.get(name)
        check("再次取图不打开文件", len(opened) == 0, f"打开了 {opened}")
        check("再次取图返回同一个对象", second is first and by_get is first)

        check("get 取不存在的图片名返回默认值", era_image.image_data.get("不存在的图片名", "默认") == "默认")
        try:
            era_image.image_data["不存在的图片名"]
            check("[] 取不存在的图片名抛 KeyError", False)
        except KeyError:
            check("[] 取不存在的图片名抛 KeyError", True)

        # 索引里有、但文件解码失败的图片：取到 1x1 的透明图片，in 照样找得到，再次取图不重新解码
        with tempfile.TemporaryDirectory() as temp_dir:
            broken_path = os.path.join(temp_dir, "测试坏图.png")
            with open(broken_path, "wb") as f:
                f.write(b"not a png")
            era_image.image_path_data["测试坏图"] = broken_path
            try:
                check("解码前 in 检查能找到坏图", "测试坏图" in era_image.image_data)
                opened.clear()
                broken = era_image.image_data.get("测试坏图")
                check("取坏图得到 1x1 的图片", getattr(broken, "size", None) == (1, 1), f"得到 {getattr(broken, 'size', broken)}")
                try:
                    again = era_image.image_data["测试坏图"]
                except KeyError:
                    again = KeyError
                check("再次取坏图返回同一个对象，文件只打开一次", again is broken and opened == [broken_path], f"得到 {again}，打开了 {opened}")
                check("解码失败后 in 检查仍能找到坏图", "测试坏图" in era_image.image_data)
            finally:
                del era_image.image_path_data["测试坏图"]
    finally:
        Image.open = real_open

    finish()


try:
    main()
except Exception:
    import traceback

    traceback.print_exc()
    sys.stdout.flush()
    os._exit(2)
