# -*- coding: UTF-8 -*-
"""
同名图片取舍规则的回归测试
==========================
image 目录下同一个图片名可能有多个文件（角色主文件夹里一份，草稿或差分子文件夹里一份，或两个分类各一份）。
tk 模式与 web 模式都通过 image_path_index.build_image_path_index 为每个图片名取一个文件：
目录层级浅的优先，层级相同时按 干员、特殊NPC、路人、女儿 的分类顺序，与文件系统的遍历顺序无关；重名的图片名全部列出，供启动时打印提示。
测试在临时目录里摆出这几种重名，不导入游戏，也不解码图片。

在仓库根目录运行：python tools/tests/image/test_same_name_image_pick.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

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
    打印汇总并按结果退出
    Return arguments:
    无
    """
    print(f"PASS={results['pass']} FAIL={results['fail']}")
    sys.exit(1 if results["fail"] else 0)


def touch(root, *parts):
    """
    在临时目录里建一个空文件（取舍只看路径，不读内容）
    Keyword arguments:
    root -- str，临时目录
    parts -- str，相对路径的各段
    Return arguments:
    str -- 建好的文件路径
    """
    path = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    return path


def main():
    """
    在临时目录里摆出重名图片，检查取舍结果与重名清单
    Return arguments:
    无
    """
    try:
        from Script.Core import image_path_index
    except ImportError as error:
        check("能导入同名图片取舍规则 Script.Core.image_path_index", False, repr(error))
        finish()

    with tempfile.TemporaryDirectory() as temp_dir:
        root = os.path.join(temp_dir, "image")
        # 主文件夹与更深一层的草稿文件夹重名：草稿文件夹「构思」按路径排序在前，层级规则仍要选主文件夹
        main_full = touch(root, "立绘", "干员", "莱伊", "莱伊_全身.png")
        draft_full = touch(root, "立绘", "干员", "莱伊", "构思", "莱伊_全身.png")
        # 两个分类下同层级的重名：按分类顺序，干员在特殊NPC之前
        operator_half = touch(root, "立绘", "干员", "电弧", "电弧_半身.png")
        npc_half = touch(root, "立绘", "特殊NPC", "电弧", "电弧_半身.png")
        # 按路径排序时「女儿」排在「路人」之前，分类顺序要选路人
        passerby = touch(root, "立绘", "路人", "路人_1.png")
        daughter = touch(root, "立绘", "女儿", "路人_1.png")
        # 不重名的图片
        single = touch(root, "立绘", "干员", "莱伊", "莱伊_半身.png")
        touch(root, "立绘", "干员", "莱伊", "莱伊_body.json")

        index, duplicates = image_path_index.build_image_path_index(root)
        check("主文件夹的文件胜过更深的草稿文件夹", index.get("莱伊_全身") == main_full, f"得到 {index.get('莱伊_全身')}")
        check("同层级时按分类顺序取干员的文件", index.get("电弧_半身") == operator_half, f"得到 {index.get('电弧_半身')}")
        check("同层级时按分类顺序取路人的文件，不按路径排序取女儿的", index.get("路人_1") == passerby, f"得到 {index.get('路人_1')}")
        check("不重名的图片照常收录", index.get("莱伊_半身") == single, f"得到 {index.get('莱伊_半身')}")
        check("只收录 png", set(index) == {"电弧_半身", "路人_1", "莱伊_全身", "莱伊_半身"}, f"得到 {sorted(index)}")
        check("重名清单只含三个重名的图片名", set(duplicates) == {"电弧_半身", "路人_1", "莱伊_全身"}, f"得到 {sorted(duplicates)}")
        check("重名清单按取舍顺序列出全部文件（莱伊_全身）", duplicates.get("莱伊_全身") == [main_full, draft_full], f"得到 {duplicates.get('莱伊_全身')}")
        check("重名清单按取舍顺序列出全部文件（电弧_半身）", duplicates.get("电弧_半身") == [operator_half, npc_half], f"得到 {duplicates.get('电弧_半身')}")
        check("重名清单按取舍顺序列出全部文件（路人_1）", duplicates.get("路人_1") == [passerby, daughter], f"得到 {duplicates.get('路人_1')}")

        # 文件系统的遍历顺序反过来，取舍结果不变
        real_walk = os.walk
        reversed_walk = lambda directory: [(dir_path, dir_names, file_names[::-1]) for dir_path, dir_names, file_names in list(real_walk(directory))[::-1]]
        with mock.patch.object(image_path_index.os, "walk", reversed_walk):
            reversed_index, reversed_duplicates = image_path_index.build_image_path_index(root)
        check("遍历顺序反过来，取舍结果不变", reversed_index == index, f"得到 {reversed_index}")
        check("遍历顺序反过来，重名清单不变", reversed_duplicates == duplicates, f"得到 {reversed_duplicates}")

    finish()


main()
