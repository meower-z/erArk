"""
json 文件的读取：判断文件是否带 utf-8 BOM，并按对应编码载入
"""

import json


def is_utf8bom(file_path: str) -> bool:
    """
    判断文件编码是否为utf-8
    Keyword arguments:
    filepath -- 文件路径
    """
    with open(file_path, mode="rb") as now_file:
        return now_file.read(3) == b"\xef\xbb\xbf"


def load_json(file_path: str) -> dict:
    """
    载入json文件。
    文件不是合法的 JSON 时抛 json.JSONDecodeError。
    Keyword arguments:
    file_path -- str，文件路径
    """
    if is_utf8bom(file_path):
        ec = "utf-8-sig"
    else:
        ec = "utf-8"
    with open(file_path, encoding=ec) as f:
        return json.loads(f.read())
