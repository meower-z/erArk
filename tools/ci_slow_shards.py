"""
慢速测试分片工具
================

本脚本把 tests/slow/test_*.py（不含 test_education_suite.py）分配到多个分片。
每个文件以 test_ 函数数量为权重，按权重降序依次放入当前最轻的分片。
用法：python tools/ci_slow_shards.py --shard 0 --total 4
退出码：0 表示正常输出，1 表示所选分片为空，2 表示参数无效。
"""

import argparse
import ast
import heapq
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
""" 仓库根目录路径。 """

EDUCATION_FILE = "test_education_suite.py"
""" 不参与慢速测试分片的教育套件文件名。 """


def count_tests(path: pathlib.Path) -> int:
    """
    用语法树解析 Python 文件并统计测试函数数量。

    参数：
        path (pathlib.Path): 待解析的 Python 文件路径
    返回：
        int: 文件内以 test_ 开头的普通函数与异步函数总数
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def slow_files(root: pathlib.Path) -> dict[str, int]:
    """
    收集 tests/slow 顶层待分片的 test_*.py 文件及其测试函数数量。

    参数：
        root (pathlib.Path): 仓库根目录路径
    返回：
        dict[str, int]: 相对 POSIX 路径到测试函数数量的映射，不含 EDUCATION_FILE
    """
    return {
        path.relative_to(root).as_posix(): count_tests(path)
        for path in (root / "tests" / "slow").glob("test_*.py")
        if path.name != EDUCATION_FILE
    }


def plan(weights: dict[str, int], total: int) -> list[list[str]]:
    """
    按权重降序将文件贪心分配到当前总权重最小的分片。

    权重相同时按路径字典序排列。分片负载相同时优先放入编号较小的分片。

    参数：
        weights (dict[str, int]): 文件路径到测试函数数量的映射
        total (int): 分片总数
    返回：
        list[list[str]]: 长度为 total 的分片列表，每片内的路径按字典序排列
    """
    shards: list[list[str]] = [[] for _ in range(total)]
    heap = [(0, index) for index in range(total)]
    for name in sorted(weights, key=lambda name: (-weights[name], name)):
        load, index = heapq.heappop(heap)
        shards[index].append(name)
        heapq.heappush(heap, (load + weights[name], index))
    return [sorted(shard) for shard in shards]


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    """
    解析命令行参数并向标准输出打印指定分片的文件路径。

    参数无效时解析器向标准错误报错并以退出码 2 结束进程。

    参数：
        argv (list[str] | None): 命令行参数列表，为 None 时读取 sys.argv
        root (pathlib.Path): 仓库根目录路径，默认为 ROOT
    返回：
        int: 成功输出时返回 0，所选分片为空时向标准错误提示并返回 1
    """
    parser = argparse.ArgumentParser(
        description="按测试函数数量输出指定慢速测试分片的文件列表"
    )
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--total", type=int, default=4)
    args = parser.parse_args(argv)
    if args.total < 1 or not 0 <= args.shard < args.total:
        parser.error(
            f"要求 0 <= --shard < --total，当前收到 {args.shard}/{args.total}"
        )
    files = plan(slow_files(root), args.total)[args.shard]
    if not files:
        print(f"分片 {args.shard}/{args.total} 为空", file=sys.stderr)
        return 1
    print("\n".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
