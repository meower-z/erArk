# -*- coding: UTF-8 -*-
"""
停用图片不被加载、不被打包的回归测试
====================================
游戏不显示的图片放在仓库根目录的 image_inactive 文件夹，它在游戏加载图片的 image 目录之外。
测试检查：image 目录下没有重名图片（启动时不打印「图片重名」提示）；image_inactive 不在 image 目录里；
发布流程 .github/workflows/python-app.yml 的复制命令不复制 image_inactive，也不复制整个仓库根目录。
不导入游戏，也不解码图片。

在仓库根目录运行：python tools/tests/image/test_inactive_images_not_loaded.py
退出码：0 全部断言通过；1 有断言失败或运行出错。
"""
import os
import re
import sys

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
    打印汇总并按结果退出
    Return arguments:
    无
    """
    print(f"PASS={results['pass']} FAIL={results['fail']}")
    sys.exit(1 if results["fail"] else 0)


def main():
    """
    检查 image 目录的重名、停用文件夹的位置与发布流程的复制命令
    Return arguments:
    无
    """
    from Script.Core import image_path_index

    os.chdir(REPO_ROOT)
    inactive_dir = "image_inactive"

    # image 目录下的图片按名字取文件，重名的会在启动时逐条提示
    index, duplicates = image_path_index.build_image_path_index("image")
    check("image 目录下没有重名图片", not duplicates, f"重名 {len(duplicates)} 个：{sorted(duplicates)}")

    # 停用文件夹在仓库根目录，含有 png，且不在 image 目录里
    inactive_pngs = [os.path.join(root, file) for root, dirs, files in os.walk(inactive_dir) for file in files if file.endswith(".png")]
    check("image_inactive 文件夹里有停用的 png", len(inactive_pngs) > 0, "没有找到 png")
    check("image_inactive 不在 image 目录里", not os.path.abspath(inactive_dir).startswith(os.path.abspath("image") + os.sep))

    # 发布流程只复制列出的文件和文件夹
    with open(os.path.join(".github", "workflows", "python-app.yml"), encoding="utf-8") as f:
        workflow = f.read()
    copy_sources = re.findall(r"Copy-Item\s+(\"[^\"]+\"|\S+)", workflow)
    check("发布流程有复制命令", len(copy_sources) > 0)
    check("发布流程不复制 image_inactive", not any(inactive_dir in source for source in copy_sources), f"复制来源 {copy_sources}")
    check("发布流程不复制整个仓库根目录", not any(source.strip('"') in (".", "*", "./*", ".\\*") for source in copy_sources), f"复制来源 {copy_sources}")

    finish()


main()
