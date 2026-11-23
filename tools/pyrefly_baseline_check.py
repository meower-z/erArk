"""
按 pyproject.toml 中棘轮的 pyrefly 配置检查受 git 跟踪的 .py 文件，
按「文件、规则」汇总报错数并与 .lint-baseline.tsv 对比。
无超限时打印通过提示并返回 0；任一项超限时输出超限项与原始报错行并返回 1。

用法（在装有 requirements-lint.txt 的环境中于仓库根目录运行）：
  python tools/pyrefly_baseline_check.py
"""

import fnmatch
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
""" 仓库根目录路径 """
CHECKER = "pyrefly"
""" pyproject.toml 中读取的棘轮检查器表名 """
FILES = "{files}"
""" 检查器命令模板中代表待检查文件列表的占位符 """

Key = tuple[str, str]
""" 报错统计键类型，由相对路径与带前缀规则名组成 """


def tracked_files(root: Path, exclude: list[str]) -> list[str]:
    """
    列出仓库中受 git 跟踪、磁盘上存在且不匹配排除模式的 .py 文件。
    Keyword arguments:
    root -- 仓库根目录路径
    exclude -- fnmatch 排除模式列表
    Return arguments:
    list[str] -- 排序后的仓库相对路径列表
    """
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        rel
        for rel in out.split("\0")
        if rel
        and (root / rel).is_file()
        and not any(fnmatch.fnmatchcase(rel, p) for p in exclude)
    )


def run_checker(
    root: Path, table: dict, files: list[str]
) -> list[tuple[Key, str]]:
    """
    按棘轮配置表运行检查器并解析输出记录。
    退出码异常、非零退出且无可读记录、出现不匹配 format 的 ERROR 行或命中未传入文件时抛出异常。
    Keyword arguments:
    root -- 仓库根目录路径
    table -- pyproject.toml 中对应检查器的配置字典
    files -- 待检查的仓库相对路径列表
    Return arguments:
    list[tuple[Key, str]] -- 每条命中的 (统计键, 原始输出行) 列表
    """
    argv: list[str] = []
    for arg in table["argv"]:
        argv.extend(files if arg == FILES else [arg])
    path = os.environ.get("PATH", "")
    env = dict(
        os.environ,
        PYTHONPATH=str(root),
        PATH=os.path.dirname(sys.executable) + os.pathsep + path,
    )
    proc = subprocess.run(
        argv, cwd=root, env=env, capture_output=True, text=True, check=False
    )
    text = proc.stderr if table.get("stream") == "stderr" else proc.stdout
    if proc.returncode not in table.get("ok_exit", [0, 1]):
        raise RuntimeError(
            f"{CHECKER} exited {proc.returncode}\n{proc.stdout}{proc.stderr}"
        )
    pattern = re.compile(table["format"])
    prefix = table.get("prefix", "")
    known = set(files)
    hits: list[tuple[Key, str]] = []
    for line in text.splitlines():
        match = pattern.match(line)
        if match is None:
            if line.lstrip().startswith("ERROR"):
                raise RuntimeError(
                    f"{CHECKER} printed an unreadable error: {line}"
                )
            continue
        if match["path"] not in known:
            raise RuntimeError(f"{CHECKER} named an unchecked file: {line}")
        rule = prefix + (match.groupdict().get("rule") or "syntax")
        hits.append(((match["path"], rule), line))
    if proc.returncode != 0 and not hits:
        raise RuntimeError(
            f"{CHECKER} exited {proc.returncode} with no readable record\n"
            f"{text}"
        )
    return hits


def baseline_counts(path: Path, prefix: str) -> Counter[Key]:
    """
    读取基线 TSV 文件，按 (文件, 规则) 累加规则以 prefix 开头且度量以 count= 开头的允许上限。
    Keyword arguments:
    path -- 基线文件路径
    prefix -- 规则名前缀
    Return arguments:
    Counter[Key] -- 各 (文件, 规则) 对应的允许报错上限计数
    """
    counts: Counter[Key] = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rel, _, rule, measure = line.split("\t")
        if rule.startswith(prefix) and measure.startswith("count="):
            counts[(rel, rule)] += int(measure.removeprefix("count="))
    return counts


def check(root: Path) -> list[str]:
    """
    读取配置与基线，对受跟踪 .py 文件运行 pyrefly，返回超限的 (文件, 规则) 汇总行与对应原始报错行。
    Keyword arguments:
    root -- 仓库根目录路径
    Return arguments:
    list[str] -- 报告行列表，无超限时为空列表
    """
    with open(root / "pyproject.toml", "rb") as f:
        ratchet = tomllib.load(f)["tool"]["lint-ratchet"]
    table = ratchet["checkers"][CHECKER]
    files = tracked_files(root, ratchet.get("exclude", []))
    hits = run_checker(root, table, files)
    allowed = baseline_counts(
        root / ratchet["baseline"], table.get("prefix", "")
    )
    counts = Counter(key for key, _ in hits)
    report: list[str] = []
    for key in sorted(counts):
        if counts[key] > allowed[key]:
            report.append(f"{key[0]} {key[1]}: {counts[key]} > {allowed[key]}")
            report.extend("  " + line for k, line in hits if k == key)
    return report


def main() -> int:
    """
    对当前仓库执行基线检查并打印结果，返回进程退出码。
    Keyword arguments:
    无
    Return arguments:
    int -- 无超限时返回 0，存在超限时返回 1
    """
    report = check(ROOT)
    print("\n".join(report) or f"{CHECKER}: no rise over the baseline")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
