#!/usr/bin/env python3
"""
在虚拟显示上启动 erArk 的 Tk 游戏窗口：起 Xvfb 与 openbox，用探针启动器 tk_probe.py 跑游戏，
等窗口和 probe.json 出现后打印 ready 事件。

内存上限、运行时限和游戏槽位都由 limited_run.run() 负责，本脚本不另做一份，所以 Tk 游戏与无头运行共用同一组槽位、
同一张退出码表和同样的 JSON 事件行。
每次 Tk 运行起自己的 Xvfb（-displayfd 选空闲的显示号），并发的 Tk 运行各用各的显示。status 与 stop 用 limited_run.py。

用法（在 erArk checkout 的根目录，用 .venv 的 python 运行本脚本）：
  tk_game.py --out <空的证据目录> [--mem 3G] [--timeout 600] [--ready-timeout 300]
"""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_run

PROBE = Path(__file__).resolve().parent / "tk_probe.py"
SCREEN = "2100x1100x24"

# 默认内存上限。Tk 游戏启动峰值连文件缓存在内不到 2 GB，3G 留出余量，
# 按 limited_run.SLOT_SIZE 占 ceil(3G / SLOT_SIZE) 个槽位；
# 图片首次显示时才解码并保留到进程结束（Script/Core/era_image.py），显示过很多图片的长时间运行需另传更大的 --mem
DEFAULT_MEM = "3G"


def tk_command(root, out_dir, python):
    """
    拼出在 scope 里运行的脚本：起 Xvfb 与 openbox，再用探针启动器跑游戏，游戏退出后收掉显示服务
    参数：
        root (Path): erArk checkout 根目录
        out_dir (Path): 证据目录，日志、display.txt、probe.json 都写在这里
        python (str): 运行游戏用的 python
    返回：
        list[str]: argv
    """
    out = shlex.quote(str(out_dir))
    script = f"""
cd {out}
Xvfb -displayfd 3 -screen 0 {SCREEN} -nolisten tcp 3>display.txt >xvfb.log 2>&1 &
for i in $(seq 100); do [ -s display.txt ] && break; sleep 0.1; done
export DISPLAY=:$(cat display.txt)
openbox >openbox.log 2>&1 &
cd {shlex.quote(str(root))}
{shlex.quote(python)} {shlex.quote(str(PROBE))} >{out}/game.log 2>&1
rc=$?
kill $(jobs -p) 2>/dev/null
exit $rc
"""
    return ["bash", "-c", script]


def find_window(display):
    """
    在指定显示上找游戏窗口
    参数：
        display (str): 形如 :51
    返回：
        str: 窗口 id，找不到时为空字符串
    """
    result = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", "^erArk "],
        capture_output=True,
        text=True,
        env={**os.environ, "DISPLAY": display},
        check=False,
    )
    return result.stdout.split("\n", 1)[0].strip()


def tk_ready(out_dir):
    """
    检查 Tk 实例是否就绪：显示已分配、窗口已出现、探针已写出第一份 probe.json
    参数：
        out_dir (Path): 证据目录
    返回：
        dict | None: 就绪时为要并入状态的字段，否则为 None
    """
    display_file, probe = out_dir / "display.txt", out_dir / "probe.json"
    number = display_file.read_text().strip() if display_file.exists() else ""
    if not number or not probe.exists():
        return None
    window = find_window(f":{number}")
    return (
        {"display": f":{number}", "window": window, "probe": str(probe)}
        if window
        else None
    )


def main(argv=None):
    """
    命令行入口
    参数：
        argv (list[str] | None): 命令行参数，不含脚本名；为 None 时读 sys.argv
    返回：
        int: 退出码
    """
    parser = argparse.ArgumentParser(
        prog="tk_game.py",
        description="经 limited_run 在虚拟显示上启动 Tk 游戏；status 与 stop 用 limited_run.py",
    )
    parser.add_argument(
        "--mem",
        type=limited_run.parse_size,
        default=DEFAULT_MEM,
        help=f"内存上限，默认 {DEFAULT_MEM}",
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="运行时限（秒），默认 600"
    )
    parser.add_argument(
        "--out", required=True, type=Path, help="证据目录，必须不存在或为空"
    )
    parser.add_argument(
        "--ready-timeout",
        type=int,
        default=300,
        help="等待窗口与 probe.json 出现的秒数，默认 300",
    )
    args = parser.parse_args(argv)
    mem_max = args.mem
    root = limited_run.game_checkout()
    out_dir = args.out.expanduser().resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        parser.error(
            f"{out_dir} 不是空目录。每次 Tk 运行用一个新目录，免得读到上一次的 probe.json 和帧。"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = limited_run.seed()
    extra = {
        "ERARK_SEED": seed,
        "PYTHONHASHSEED": seed,
        "ERARK_PROBE_JSON": str(out_dir / "probe.json"),
    }
    return limited_run.run(
        "tk",
        tk_command(root, out_dir, sys.executable),
        mem_max,
        args.timeout,
        extra,
        out_dir,
        lambda: tk_ready(out_dir),
        args.ready_timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
