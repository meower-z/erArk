"""
图片目录索引：导入时遍历 image 目录，建立图片名到路径的映射与按文件名首段分组的角色索引。
本模块不解码图片，也不导入 Tk、PIL.ImageTk 或主界面模块。
"""

import os
import time
from Script.Core import image_path_index

image_path_data: dict[str, str] = {}
image_data_index_by_chara: dict[str, list[str]] = {}
image_dir_path = os.path.join("image")


def index_images_from_directory(directory: str) -> None:
    """
    建立目录下全部图片的名字 -> 路径索引与角色索引，不解码图片

    Keyword arguments:
    directory -- str，图片根目录

    Return arguments:
    无
    """
    start_time = time.time()
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
        if "_" in image_file_name:
            character_name = image_file_name.split("_")[0]
            image_data_index_by_chara.setdefault(character_name, []).append(
                image_file_name
            )

    elapsed_time = time.time() - start_time
    print(
        f"图片索引完成！共 {len(image_path_data)} 张，耗时 {elapsed_time:.2f} 秒"
    )


index_images_from_directory(image_dir_path)
