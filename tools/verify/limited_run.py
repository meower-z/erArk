#!/usr/bin/env python3
"""
在内存上限、运行时限和全机共用的游戏槽位下运行一条命令。
凡是会启动 erArk 游戏的进程（无头脚本、Tk 界面）都必须经由本脚本启动，Tk 界面经由 tk_game.py。

每次运行放进一个独立的 systemd scope，内存上限（MemoryMax，禁用 swap）与运行时限（RuntimeMaxSec）由内核和
systemd 强制执行，
超限时只杀这一组进程。全机共有 SLOTS 个槽位，每个代表 SLOT_SIZE 内存；
一次运行占 ceil(内存上限 / SLOT_SIZE) 个。
run() 对每个槽位的锁文件持有 flock，进程死掉时内核自动放开。
哪次运行活着只看 /proc/locks 里槽位锁的真实持有者，状态文件只是线索。
槽位不够、同一 checkout 已有运行、或有不属于任何运行的 era-game scope 时以退出码 75 拒绝，不等待。
调用 run() 的进程被中断时，run() 会停掉它的 scope。
每次运行用 mkdtemp 建一个自己的临时目录。运行结束、启动的进程已结束且 scope 确认已停后，删掉这个目录。
没来得及删的目录（例如启动进程被 SIGKILL）由之后启动的运行清掉，条件是它 SWEEP_MIN_AGE_S 秒没改动，
且不属于正在运行的实例或存活 scope。
删不掉的文件留下。

用法（在 erArk checkout 的根目录，用 .venv 的 python 运行本脚本）：
  limited_run.py [--mem 2G] [--timeout 600] -- <命令...>
  limited_run.py status
  limited_run.py stop [槽位|pid]

需要免密 sudo 来调用 systemd-run。
本机只供一个用户运行本脚本：STATE_DIR 与其中的槽位锁按第一次运行的用户的 umask 建立，别的用户打不开它们。
"""

import argparse
import fcntl
import getopt
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 槽位锁、各运行的状态与停止请求、各运行的临时目录都放在这里
STATE_DIR = Path("/tmp/era-game")
CGROUP = Path("/sys/fs/cgroup")
PROC = Path("/proc")
# earlyoom v1.7 的选项表（earlyoom -h，加上已废弃但仍接受的 -i、-k），用来按它的规则拆开组合的短选项和选项参数
EARLYOOM_SHORT = "m:s:M:S:N:r:ndvpghik"
EARLYOOM_LONG = ["prefer=", "avoid=", "dryrun", "help"]
UNIT_PATTERN = re.compile(r"^era-game-\d+$")
# 运行的临时目录名：scope 名称加 mkdtemp 的随机后缀。没有后缀的 era-game-<数字> 目录不匹配，清理不动它们
TMPDIR_PATTERN = re.compile(r"^(era-game-\d+)-[a-z0-9_]+$")
DEFAULT_SEED = "20260719"

# 全机的槽位数与每个槽位代表的内存。两个数只在这里设，不读环境变量，本机所有调用方按同一套数占槽位
SLOTS = 5
SLOT_SIZE = "2G"

# 默认内存上限为一个槽位；Tk 游戏的默认值在 tk_game.py
DEFAULT_MEM = SLOT_SIZE

# 传进 scope 的环境变量白名单：命令行与 unit 描述对本机所有用户可见，令牌之类的变量一律不传
ENV_ALLOW = re.compile(
    r"^(HOME|USER|LOGNAME|PATH|SHELL|TERM|TZ|LANG|LANGUAGE|LC_\w+|VIRTUAL_ENV|PYTHON\w*|ERARK_\w+)$"
)

# 结束原因到退出码。命令正常结束时退出码原样返回
REASON_EXIT = {
    "timeout": 124,
    "oom": 137,
    "not-ready": 77,
    "stopped-headless": 78,
    "stopped-tk": 0,
}
EXIT_BUSY = 75
EXIT_NO_HEADROOM = 76
# 清理只删这么多秒内没改动过的临时目录；这个时长比正常运行的时限加余量还长。
# 启动进程可能已经退出，而 systemd-run 还没建好 scope；这样的目录还会被用到，不能删
SWEEP_MIN_AGE_S = 7200


def parse_size(text):
    """
    把 4G、512M 这样的大小写法换算成字节，供 argparse 使用
    参数：
        text (str): 大小，支持 K/M/G 后缀
    返回：
        int: 字节数
    """
    units = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)", text.strip().upper())
    if not match:
        raise argparse.ArgumentTypeError(
            f"无法识别的大小 {text!r}，写成 4G、512M 这样"
        )
    return int(float(match.group(1)) * units.get(match.group(2), 1))


def mib(value):
    """
    字节换算成 MiB 整数
    参数：
        value (int): 字节数
    返回：
        int: MiB
    """
    return value // (1 << 20)


def read_int(path, default=0):
    """
    读取只含一个整数的 cgroup 文件
    参数：
        path (Path): 文件路径
        default (int): 文件缺失或内容不是整数时的返回值
    返回：
        int: 读到的值
    """
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return default


def scope_dir(unit):
    """
    返回 scope 对应的 cgroup 目录
    参数：
        unit (str): scope 名称（不含 .scope 后缀）
    返回：
        Path: cgroup 目录
    """
    return CGROUP / "system.slice" / f"{unit}.scope"


def read_stat(path):
    """
    读取 cgroup 的 memory.stat
    参数：
        path (Path): memory.stat 文件路径
    返回：
        dict[str, int]: 各字段的值
    """
    return dict(
        (key, int(value))
        for key, value in (
            line.split() for line in path.read_text().splitlines()
        )
    )


def unreclaimable(stat):
    """
    算出 cgroup 里回收不了的内存：anon、shmem（/dev/shm 里的文件）和内核内存（其中只有少量可回收）。
    文件缓存可以回收，不算在内
    参数：
        stat (dict[str, int]): read_stat() 的结果
    返回：
        int: 字节数
    """
    return stat["anon"] + stat["shmem"] + stat["kernel"]


def read_meminfo():
    """
    读取 /proc/meminfo
    返回：
        dict[str, int]: 各字段的值，KiB
    """
    return {
        line.split()[0].rstrip(":"): int(line.split()[1])
        for line in (PROC / "meminfo").read_text().splitlines()
    }


def container_limit():
    """
    容器的内存线：memory.high 是内核开始限速的线，到了这条线就会抖动而不会杀进程，所以以它为准；
    它不设限时用 memory.max；两者都不设限或没有这两个文件（例如在 cgroup 根上）时用 /proc/meminfo 的 MemTotal
    返回：
        int: 字节数
    """
    for name in ("memory.high", "memory.max"):
        path = CGROUP / name
        if path.exists():
            text = path.read_text().strip()
            if text != "max":
                return int(text)
    return read_meminfo()["MemTotal"] * 1024


def container_headroom():
    """
    计算容器还能放下多少不可回收内存（unreclaimable()）
    返回：
        tuple[int, int, dict]: (余量字节数, container_limit() 字节数, memory.stat 各字段)
    """
    limit = container_limit()
    stat = read_stat(CGROUP / "memory.stat")
    return limit - unreclaimable(stat), limit, stat


def earlyoom_commands():
    """
    读取每个正在运行的 earlyoom 的命令行参数
    读进程的命令行而不读 /etc/default/earlyoom，因为配置改了要等 earlyoom 重启才生效。
    返回：
        list[list[str]]: 每个 earlyoom 进程的参数，不含程序本身；earlyoom 没在运行时为空
    """
    commands = []
    for comm in PROC.glob("[0-9]*/comm"):
        try:
            if comm.read_text().strip() == "earlyoom":
                commands.append(
                    (comm.parent / "cmdline")
                    .read_bytes()
                    .decode(errors="replace")
                    .split("\0")[1:]
                )
        except OSError:
            continue
    return commands


def earlyoom_percent(args, mem_total_kib):
    """
    按 earlyoom 的参数算出它用 SIGTERM 杀进程的线：可用内存低于总内存的这个百分比时动手
    -m PERCENT[,KILL_PERCENT] 给百分比，-M SIZE[,KILL_SIZE] 给 KiB；KILL 值较高时 earlyoom 把 SIGTERM 线抬到它，
    同一选项写了几次时用最后一次，-m 与 -M 都写了时用较低的一条，都没写时用默认值 10。
    earlyoom 还要求空闲 swap 低于 -s，这里不看，宁可多拒绝。
    参数：
        args (list[str]): earlyoom 的命令行参数
        mem_total_kib (int): /proc/meminfo 的 MemTotal，KiB
    返回：
        float | None: 百分比；带 --dryrun 时为 None
    """
    try:
        options, _ = getopt.gnu_getopt(args, EARLYOOM_SHORT, EARLYOOM_LONG)
    except getopt.GetoptError as error:
        sys.exit(
            f"读不懂 earlyoom 的命令行（{error}），算不出它的杀进程线：{shlex.join(args)}"
        )
    # --dryrun 的 earlyoom 不杀进程
    if any(flag == "--dryrun" for flag, _ in options):
        return None
    # 同一个选项写了几次时 earlyoom 用最后一次
    values = {flag: value for flag, value in options if flag in ("-m", "-M")}
    percents = []
    for flag, value in values.items():
        term, _, kill = value.partition(",")
        line = max(float(term), float(kill or 0))
        percents.append(line if flag == "-m" else line * 100 / mem_total_kib)
    return min(percents, default=10.0)


def earlyoom_headroom():
    """
    计算 earlyoom 动手之前还能用多少内存：/proc/meminfo 的 MemAvailable 减去 MemTotal × earlyoom_percent() / 100
    返回：
        tuple[int, float] | None: (余量字节数, 百分比)；没有会杀进程的 earlyoom 在运行时为 None
    """
    commands = earlyoom_commands()
    if not commands:
        return None
    info = read_meminfo()
    # 有几个 earlyoom 时，最先动手的是线最高的那个
    percents = [
        percent
        for percent in (
            earlyoom_percent(args, info["MemTotal"]) for args in commands
        )
        if percent is not None
    ]
    if not percents:
        return None
    percent = max(percents)
    return (
        info["MemAvailable"] - int(info["MemTotal"] * percent / 100)
    ) * 1024, percent


def memory_headroom():
    """
    启动前检查与 status 共用的内存余量：容器余量与 earlyoom 余量中较小的一个
    earlyoom 可能在容器到达 memory.high 之前就杀掉游戏，这样被杀的运行以 143 退出。
    返回：
        tuple[int, tuple, tuple | None]: (余量字节数, container_headroom() 的结果, earlyoom_headroom() 的结果)
    """
    container = container_headroom()
    early = earlyoom_headroom()
    return (
        min(container[0], early[0] if early else container[0]),
        container,
        early,
    )


def active_game_units():
    """
    列出仍存活的 era-game scope
    返回：
        list[str]: unit 名称（含 .scope 后缀）
    """
    out = subprocess.run(
        [
            "systemctl",
            "list-units",
            "--plain",
            "--no-legend",
            "--state=active,activating,deactivating",
            "era-game-*.scope",
        ],
        capture_output=True,
        text=True,
    ).stdout
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def stop_unit(unit):
    """
    停掉一个 scope 及其中所有进程
    参数：
        unit (str): scope 名称，必须形如 era-game-<数字>
    """
    if UNIT_PATTERN.match(unit):
        subprocess.run(
            ["sudo", "-n", "systemctl", "stop", f"{unit}.scope"],
            capture_output=True,
        )


def read_and_clear_result(unit):
    """
    读取 systemd 记录的 scope 结束原因，读完清掉失败记录
    参数：
        unit (str): scope 名称
    返回：
        str: success、oom-kill、timeout 等；scope 已被回收时为空字符串
    """
    result = subprocess.run(
        ["systemctl", "show", f"{unit}.scope", "-p", "Result", "--value"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["sudo", "-n", "systemctl", "reset-failed", f"{unit}.scope"],
        capture_output=True,
    )
    return result


def slot_file(slot, suffix):
    """
    返回槽位的一个文件：lock 是槽位锁，json 是占用该槽位的运行的状态；一次运行的状态只放在它占的最小槽位下
    参数：
        slot (int): 槽位编号，0 到 SLOTS-1
        suffix (str): lock 或 json
    返回：
        Path: 文件路径
    """
    return STATE_DIR / f"slot-{slot}.{suffix}"


def stop_file(unit):
    """
    返回对一次运行的停止请求文件。
    按 unit（含启动进程号）而不按槽位命名：槽位会被下一次运行接手，停止请求不能落到接手的运行头上
    参数：
        unit (str): scope 名称，形如 era-game-<pid>
    返回：
        Path: 文件路径
    """
    return STATE_DIR / f"{unit}.stop"


def lock_slot(slot):
    """
    以非阻塞方式拿一个槽位的锁
    参数：
        slot (int): 槽位编号
    返回：
        file | None: 拿到时为持有锁的文件对象，被占用时为 None
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(slot_file(slot, "lock"), "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def take_slots(count):
    """
    全拿或全不拿地占 count 个空槽位：拿不够时放回已拿的
    参数：
        count (int): 需要的槽位数
    返回：
        list[tuple[int, file]] | None: 拿到的 (槽位编号, 锁文件对象)，按编号升序；拿不够时为 None
    """
    held = []
    for slot in range(SLOTS):
        if len(held) == count:
            break
        handle = lock_slot(slot)
        if handle is not None:
            held.append((slot, handle))
    if len(held) < count:
        release_slots(held)
        return None
    return held


def release_slots(held):
    """
    放开 take_slots() 拿到的槽位
    参数：
        held (list[tuple[int, file]]): take_slots() 的结果
    """
    for _, handle in held:
        handle.close()


def slots_needed(mem_max):
    """
    计算一次运行要占的槽位数：ceil(内存上限 / SLOT_SIZE)，至少一个
    参数：
        mem_max (int): 内存上限，字节
    返回：
        int: 槽位数，可能超过 SLOTS
    """
    return max(1, -(-mem_max // parse_size(SLOT_SIZE)))


def read_state(slot):
    """
    读取记在槽位下的运行状态
    参数：
        slot (int): 槽位编号
    返回：
        dict | None: 状态；文件不存在或正在被替换时为 None
    """
    try:
        return json.loads(slot_file(slot, "json").read_text())
    except (OSError, ValueError):
        return None


def write_state(state):
    """
    原子地写入运行状态，写在它占的最小槽位下
    参数：
        state (dict): 状态，slots 为它占的槽位，升序
    """
    path = slot_file(state["slots"][0], "json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def lock_device(path):
    """
    返回 /proc/locks 用来标识文件所在文件系统的设备号：文件所在挂载点（mountinfo 里最长的前缀）的 major:minor。
    不用 stat 的 st_dev，因为 btrfs 子卷的 st_dev 与内核在 /proc/locks 里写的不同。
    参数：
        path (str): 已解析符号链接的文件路径
    返回：
        tuple[int, int]: (major, minor)；找不到挂载点时为 (-1, -1)
    """
    best, device = "", (-1, -1)
    for line in (PROC / "self" / "mountinfo").read_text().splitlines():
        fields = line.split()
        # 挂载点里的空格等字符写成八进制转义，例如 \040
        mount = re.sub(
            r"\\([0-7]{3})",
            lambda match: chr(int(match.group(1), 8)),
            fields[4],
        )
        inside = path == mount or path.startswith(mount.rstrip("/") + "/")
        if inside and len(mount) >= len(best):
            best, (major, minor) = mount, fields[2].split(":")
            device = (int(major), int(minor))
    return device


def slot_holders():
    """
    从 /proc/locks 读出各槽位锁的真实持有者：按锁文件的 inode 与设备号对上 FLOCK 行，等待中的锁（带 ->）与 POSIX 锁不算
    运行是否活着只看这里；状态文件只是线索，它记下的进程可能已死、成了僵尸，或槽位已被另一次运行接手。
    返回：
        dict[int, int]: 槽位编号到持锁进程号；空着的槽位不在其中
    """
    keys = {}
    for slot in range(SLOTS):
        path = slot_file(slot, "lock")
        try:
            inode = path.stat().st_ino
        except OSError:
            continue
        keys[(*lock_device(os.path.realpath(path)), inode)] = slot
    holders = {}
    for line in (PROC / "locks").read_text().splitlines():
        # 形如 "21: FLOCK  ADVISORY  WRITE 400487 00:2f:5222887 0 EOF"，设备号是十六进制，inode 是十进制
        parts = line.split()
        if len(parts) < 6 or parts[1] != "FLOCK":
            continue
        major, minor, inode = parts[5].split(":")
        held_slot = keys.get((int(major, 16), int(minor, 16), int(inode)))
        if held_slot is not None:
            holders[held_slot] = int(parts[4])
    return holders


def live_runs():
    """
    列出正在运行的实例：状态记在某槽位下、且该槽位的锁正由状态里记的启动进程持有的运行（slot_holders()）
    返回：
        list[dict]: 各运行的状态，按最小槽位升序
    """
    holders = slot_holders()
    runs = []
    for slot in range(SLOTS):
        state = read_state(slot) if slot in holders else None
        if (
            state
            and state.get("slots", [None])[0] == slot
            and holders[slot] == state.get("pid")
        ):
            runs.append(state)
    return runs


def orphan_units(runs):
    """
    列出不属于任何运行的存活 era-game scope：没有哪个运行的状态文件认领它，例如启动它的进程已死。
    列完 scope 后再读一次 live_runs()：运行先写状态、后建 scope，在 runs 之后才建好 scope 的运行在第二次读里能看到。
    两次读里都没有运行认领的 scope 才算遗留。
    参数：
        runs (list[dict]): 调用方先前读到的 live_runs() 结果
    返回：
        list[str]: unit 名称（含 .scope 后缀）
    """
    units = active_game_units()
    owned = {f"{run['unit']}.scope" for run in [*runs, *live_runs()]}
    return [unit for unit in units if unit not in owned]


def remove_tmpdir(path):
    """
    删掉一次运行的临时目录及其中所有文件；目录已被别的运行删掉、或有删不掉的文件时跳过，不报错
    参数：
        path (Path): 临时目录
    """
    shutil.rmtree(path, ignore_errors=True)


def sweep_tmpdirs(unit):
    """
    删掉已结束的运行留下的临时目录：STATE_DIR/tmp 下名字符合 TMPDIR_PATTERN、SWEEP_MIN_AGE_S 秒内没改动过的目录，
    且它所属的 scope 名称不是本次运行、
    不属于任何正在运行的实例、systemd 没列出这个 scope、cgroup 目录也不在（systemctl 出错时列表为空，所以两样都看）。
    每个目录都是 mkdtemp 建的，不会被新运行重用，所以开头读一次正在运行的实例与存活的 scope 就够；cgroup 目录逐个看。
    符号链接与普通文件不动。
    参数：
        unit (str): 本次运行的 scope 名称
    """
    try:
        entries = list((STATE_DIR / "tmp").iterdir())
    except OSError:
        return
    live = {run["unit"] for run in live_runs()}
    scopes = set(active_game_units())
    for entry in entries:
        match = TMPDIR_PATTERN.match(entry.name)
        if not match or entry.is_symlink() or not entry.is_dir():
            continue
        owner = match.group(1)
        try:
            old = time.time() - entry.stat().st_mtime >= SWEEP_MIN_AGE_S
        except OSError:
            continue
        if (
            old
            and owner != unit
            and owner not in live
            and f"{owner}.scope" not in scopes
            and not scope_dir(owner).exists()
        ):
            remove_tmpdir(entry)


def describe_run(run):
    """
    把一次运行写成一行说明，用于拒绝消息与 stop 的列表
    参数：
        run (dict): 运行状态
    返回：
        str: 说明
    """
    out = f" out {run['out']}" if run.get("out") else ""
    return (
        f"槽位 {run['slots']} pid {run['pid']} {run['mode']} 内存上限 {run['mem_max_mib']} MiB cwd {run['cwd']}{out}："
        f"{run['command']}"
    )


def emit(event):
    """
    向标准输出打印一行 JSON 事件
    参数：
        event (dict): 事件内容
    """
    print(json.dumps(event, ensure_ascii=False), flush=True)


def refuse_busy(count, runs, orphans):
    """
    槽位不够或有不属于任何运行的 era-game scope 时，列出占用者并以 EXIT_BUSY 退出
    参数：
        count (int): 本次需要的槽位数
        runs (list[dict]): 正在运行的实例
        orphans (list[str]): 不属于任何运行的存活 scope
    """
    if orphans:
        head = (
            f"有不属于任何运行的 era-game scope 还活着：{' '.join(orphans)}。启动它的进程已不在；"
            f"它占的内存不归任何槽位管，所以先不启动新的。"
        )
    else:
        free = SLOTS - len(slot_holders())
        head = f"槽位不够：这次需要 {count} 个，空着 {free} 个（全机 {SLOTS} 个，每个 {SLOT_SIZE}）。"
    print(
        head + "\n正在运行：\n" + "\n".join(describe_run(run) for run in runs),
        file=sys.stderr,
    )
    print(
        "等它们结束后再启动。只停你自己启动的运行：`limited_run.py stop <槽位|pid>`。",
        file=sys.stderr,
    )
    sys.exit(EXIT_BUSY)


def refuse_same_checkout(runs, cwd):
    """
    同一 checkout 已有运行时说明原因并以 EXIT_BUSY 退出：两次运行会同时写这个 checkout 的 data/*.json 与 save/
    参数：
        runs (list[dict]): 其他正在运行的实例
        cwd (str): 本次运行的 checkout 根目录，已解析符号链接
    """
    for run in runs:
        if run["cwd"] == cwd:
            print(
                f"checkout {cwd} 正被另一次运行占用：{describe_run(run)}\n"
                "同一 checkout 里的两次运行会同时写 data/*.json 和 save/，所以一个 checkout 同一时间只跑一次。"
                "别等重试窗口：用你自己的 worktree（git worktree add）启动。"
                "那次运行是你自己先前启动的才等它结束，或用 `limited_run.py stop <槽位|pid>` 停掉它。",
                file=sys.stderr,
            )
            sys.exit(EXIT_BUSY)


def check_headroom(mem_max):
    """
    启动前检查内存余量（memory_headroom()），放不下一个满额实例就拒绝启动
    参数：
        mem_max (int): 本次实例的内存上限，字节
    """
    headroom, (container, high, stat), early = memory_headroom()
    if headroom >= mem_max:
        return
    top = subprocess.run(
        ["ps", "-eo", "pid,rss,etime,comm", "--sort=-rss"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()[:6]
    early_line = (
        f"earlyoom：可用内存低于总内存的 {early[1]:.4g}% 就杀进程，在那之前还能用 {mib(early[0])} MiB。\n"
        if early
        else ""
    )
    print(
        f"内存余量不足，拒绝启动：需要 {mib(mem_max)} MiB，只剩 {mib(headroom)} MiB。\n"
        + early_line
        + (
            f"容器余量 {mib(container)} MiB：限速线 memory.high = {mib(high)} MiB；已用 anon {mib(stat['anon'])} MiB、"
            f"shmem {mib(stat['shmem'])} MiB（/dev/shm 里的文件）、kernel {mib(stat['kernel'])} MiB。\n"
            "占用最多的进程：\n"
        )
        + "\n".join(top),
        file=sys.stderr,
    )
    sys.exit(EXIT_NO_HEADROOM)


def scope_env(extra):
    """
    组装传进 scope 的环境变量：白名单内的变量加上额外指定的变量
    参数：
        extra (dict[str, str]): 额外变量
    返回：
        dict[str, str]: 环境变量
    """
    env = {
        key: value for key, value in os.environ.items() if ENV_ALLOW.match(key)
    }
    env.update(extra)
    # game_runner_guard.py 凭这个标记放行 era_image、game_init 的导入
    env["USE_GAME_RUNNER"] = "1"
    return env


def scope_argv(unit, mode, mem_max, timeout, env, command):
    """
    拼出在受限 scope 里以当前用户身份运行命令的 argv
    参数：
        unit (str): scope 名称
        mode (str): headless 或 tk，写进 unit 描述
        mem_max (int): 内存上限，字节
        timeout (int): 运行时限，秒
        env (dict[str, str]): 传给命令的完整环境变量
        command (list[str]): 要运行的命令
    返回：
        list[str]: argv
    """
    user = pwd.getpwuid(os.getuid()).pw_name
    return [
        *[
            "sudo",
            "-n",
            "systemd-run",
            "--quiet",
            "--scope",
            f"--unit={unit}",
            f"--description=era-game-{mode}",
        ],
        *[
            "-p",
            f"MemoryMax={mem_max}",
            "-p",
            "MemorySwapMax=0",
            "-p",
            f"RuntimeMaxSec={timeout}",
            "-p",
            "TimeoutStopSec=10",
        ],
        *["--", "runuser", "-u", user, "--", "/usr/bin/env", "-i"],
        *[f"{key}={value}" for key, value in env.items()],
        *command,
    ]


def game_checkout():
    """
    确认当前目录是 erArk checkout 的根目录
    返回：
        Path: checkout 根目录
    """
    root = Path.cwd()
    if not (root / "game.py").is_file():
        sys.exit(f"{root} 下没有 game.py。在 erArk checkout 的根目录运行。")
    return root


def end_signal(signum, frame):
    """
    把 SIGTERM、SIGHUP 转成 SystemExit，让 run() 的 finally 停掉 scope
    参数：
        signum (int): 信号编号
        frame: 当前栈帧
    """
    raise SystemExit(128 + signum)


def run(
    mode,
    command,
    mem_max,
    timeout,
    extra_env,
    out_dir=None,
    ready_check=None,
    ready_timeout=0,
):
    """
    在受限 scope 里运行一次游戏，等它结束，报告结果；调用它的进程被中断时停掉 scope
    参数：
        mode (str): headless 或 tk（由 tk_game.py 传入）
        command (list[str]): 要运行的命令
        mem_max (int): 内存上限，字节
        timeout (int): 运行时限，秒
        extra_env (dict[str, str]): 额外传给命令的环境变量
        out_dir (Path | None): tk 模式的证据目录
        ready_check (Callable[[], dict | None] | None): tk 模式的就绪检查，就绪时返回要并入状态的字段。
        为 None 时不等就绪
        ready_timeout (int): tk 模式等待就绪的秒数
    返回：
        int: 退出码
    """
    cwd = os.path.realpath(os.getcwd())
    count = slots_needed(mem_max)
    if count > SLOTS:
        print(
            (
                f"内存上限 {mib(mem_max)} MiB 要占 {count} 个槽位，超过全机的 {SLOTS} 个（每个 {SLOT_SIZE}），"
                f"等多久都启动不了。把 --mem 降到 {SLOTS} × {SLOT_SIZE} 以内。"
            ),
            file=sys.stderr,
        )
        sys.exit(2)
    refuse_same_checkout(live_runs(), cwd)
    held = take_slots(count)
    if held is None:
        runs = live_runs()
        refuse_busy(count, runs, orphan_units(runs))
    slots = [slot for slot, _ in held]
    unit = f"era-game-{os.getpid()}"
    stop_request = stop_file(unit)
    try:
        # 拿到的槽位下的状态文件是死掉的运行留下的；同名的停止请求是用过同一进程号的旧运行留下的
        for slot in slots:
            slot_file(slot, "json").unlink(missing_ok=True)
        stop_request.unlink(missing_ok=True)
        summary = "tk game" if mode == "tk" else shlex.join(command)[:300]
        state = {
            "unit": unit,
            "mode": mode,
            "pid": os.getpid(),
            "slots": slots,
            "cwd": cwd,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mem_max_mib": mib(mem_max),
            "timeout_s": timeout,
            "command": summary,
        }
        if out_dir:
            state["out"] = str(out_dir)
        write_state(state)
        # 先写状态再复查：同一 checkout 同时起的两次运行至少有一方看得见对方
        others = [run for run in live_runs() if run["pid"] != os.getpid()]
        refuse_same_checkout(others, cwd)
        orphans = orphan_units(others)
        if orphans:
            refuse_busy(count, others, orphans)
        # 只清本次 unit 名下的失败记录；别的运行的失败记录留给它自己读结束原因
        subprocess.run(
            ["sudo", "-n", "systemctl", "reset-failed", f"{unit}.scope"],
            capture_output=True,
        )
        check_headroom(mem_max)
        sweep_tmpdirs(unit)
    except SystemExit:
        slot_file(slots[0], "json").unlink(missing_ok=True)
        release_slots(held)
        raise
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, end_signal)
    emit({"event": "started", **state})

    (STATE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix=f"{unit}-", dir=STATE_DIR / "tmp"))
    env = scope_env({**extra_env, "TMPDIR": str(tmpdir)})
    proc = subprocess.Popen(
        scope_argv(unit, mode, mem_max, timeout, env, command),
        stdin=None if mode == "headless" else subprocess.DEVNULL,
    )
    started = time.monotonic()
    peak, unreclaimable_peak, reason, ready = 0, 0, None, ready_check is None
    try:
        while proc.poll() is None:
            time.sleep(0.2)
            # memory.peak 含文件缓存。内核在 scope 到内存上限时先回收文件缓存，所以 memory.peak 到了上限不说明运行被杀。
            # 内核不给回收不了的内存记峰值，所以这里每轮读 memory.stat 算出这部分，留下最大值 unreclaimable_peak。
            peak = max(peak, read_int(scope_dir(unit) / "memory.peak"))
            try:
                unreclaimable_peak = max(
                    unreclaimable_peak,
                    unreclaimable(read_stat(scope_dir(unit) / "memory.stat")),
                )
            except (OSError, ValueError, KeyError):
                pass
            if stop_request.exists():
                reason = f"stopped-{mode}"
                stop_unit(unit)
                proc.wait()
            elif not ready:
                fields = ready_check()
                if fields:
                    ready = True
                    state.update(fields)
                    write_state(state)
                    emit(
                        {
                            "event": "ready",
                            "elapsed_s": int(time.monotonic() - started),
                            "memory_mib": mib(
                                read_int(scope_dir(unit) / "memory.current")
                            ),
                            **state,
                        }
                    )
                elif time.monotonic() - started > ready_timeout:
                    reason = "not-ready"
                    stop_unit(unit)
                    proc.wait()
    finally:
        leftover = scope_dir(unit).exists()
        if leftover:
            stop_unit(unit)
        elif proc.returncode is None:
            # 刚 Popen 就被中断时 systemd-run 可能还没建 scope：停掉它，免得它在槽位放开之后才跑起命令
            proc.terminate()
        proc.wait()
        result = read_and_clear_result(unit)
        slot_file(slots[0], "json").unlink(missing_ok=True)
        stop_request.unlink(missing_ok=True)
        release_slots(held)
        # scope 停不掉（例如 sudo 被拒、systemctl stop 出错）时，其中的进程可能还在写临时目录，这时留给之后启动的运行清
        if (
            not scope_dir(unit).exists()
            and f"{unit}.scope" not in active_game_units()
        ):
            remove_tmpdir(tmpdir)

    code = proc.returncode if proc.returncode >= 0 else 128 - proc.returncode
    if reason is None:
        reason = {"oom-kill": "oom", "timeout": "timeout"}.get(result, "exit")
    emit(
        {
            "event": "finished",
            "unit": unit,
            "reason": (
                reason.split("-")[0] if reason.startswith("stopped") else reason
            ),
            "scope_result": result,
            "returncode": code,
            "leftover_processes_stopped": leftover,
            "elapsed_s": int(time.monotonic() - started),
            "memory_peak_mib": mib(peak),
            "unreclaimable_peak_mib": mib(unreclaimable_peak),
            "mem_max_mib": mib(mem_max),
        }
    )
    return REASON_EXIT.get(reason, code)


def cmd_status():
    """
    每个正在运行的实例与每个不属于任何运行的 scope 各打印一行，最后一行是槽位占用与内存余量
    返回：
        int: 有实例或遗留 scope 在运行时为 0，否则为 1
    """
    runs = live_runs()
    orphans = orphan_units(runs)
    for run in runs:
        unit_dir = scope_dir(run["unit"])
        emit(
            {
                **run,
                "memory_mib": mib(read_int(unit_dir / "memory.current")),
                "memory_peak_mib": mib(read_int(unit_dir / "memory.peak")),
            }
        )
    for unit in orphans:
        emit(
            {
                "orphan_unit": unit,
                "memory_mib": mib(
                    read_int(
                        scope_dir(unit.removesuffix(".scope"))
                        / "memory.current"
                    )
                ),
            }
        )
    headroom, (_, high, _), _ = memory_headroom()
    emit(
        {
            "slots_used": len(slot_holders()),
            "slots": SLOTS,
            "slot_size": SLOT_SIZE,
            "headroom_mib": mib(headroom),
            "memory_high_mib": mib(high),
        }
    )
    return 0 if runs or orphans else 1


def still_running(run):
    """
    判断一次运行是否还持有它的最小槽位：按 /proc/locks 的真实持锁者判断，槽位被别的运行接手也不会误判
    参数：
        run (dict): 运行状态
    返回：
        bool: 还在运行时为 True
    """
    return slot_holders().get(run["slots"][0]) == run["pid"]


def stop_orphan(unit):
    """
    直接停掉一个不属于任何运行的 scope
    参数：
        unit (str): unit 名称（含 .scope 后缀）
    返回：
        int: 停下时为 0，没停下时为 2
    """
    stop_unit(unit.removesuffix(".scope"))
    read_and_clear_result(unit.removesuffix(".scope"))
    if unit in active_game_units():
        print(
            f"启动它的进程已不在，遗留的 scope 没能停掉：{unit}",
            file=sys.stderr,
        )
        return 2
    print(
        f"启动它的进程已不在，直接停掉了遗留的 scope：{unit}", file=sys.stderr
    )
    return 0


def cmd_stop(target=None):
    """
    停掉一次运行：请求它的启动进程（limited_run.py 或 tk_game.py）停掉 scope，并等它放开槽位。
    给了槽位编号或 pid 时只停那一次；没给时只在恰好有一次运行时停它，不核对它是谁启动的；有几次运行时不默认停任何一个。
    参数：
        target (str | None): 小于 SLOTS 的数是槽位编号，其他数是 pid；None 表示没给
    返回：
        int: 停下（含直接停掉启动进程已不在的遗留 scope）时为 0；没有可停的、目标不明或不存在时为 1；
        30 秒内没停下，或遗留 scope 没能停掉时为 2
    """
    runs = live_runs()
    orphans = orphan_units(runs)
    listing = "\n".join(
        [describe_run(run) for run in runs]
        + [f"遗留 scope {unit}（启动进程已不在）" for unit in orphans]
    )
    if target is None:
        if not runs and not orphans:
            print("没有游戏实例在运行。", file=sys.stderr)
            return 1
        if len(runs) + len(orphans) > 1:
            print(
                (
                    f"有不止一次运行，不默认停任何一个。用 `limited_run.py stop <槽位|pid>` 指定，只停你自己启动的：\n"
                    f"{listing}"
                ),
                file=sys.stderr,
            )
            return 1
        if orphans:
            return stop_orphan(orphans[0])
        run = runs[0]
    else:
        if not target.isdigit():
            print(
                f"stop 只接受槽位编号或 pid，不认识 {target!r}。",
                file=sys.stderr,
            )
            return 1
        number = int(target)
        matches = [
            run
            for run in runs
            if (
                number in run["slots"]
                if number < SLOTS
                else run["pid"] == number
            )
        ]
        if not matches:
            if f"era-game-{number}.scope" in orphans:
                return stop_orphan(f"era-game-{number}.scope")
            print(
                f"没有占着槽位或 pid 为 {number} 的运行。正在运行：\n{listing}",
                file=sys.stderr,
            )
            return 1
        run = matches[0]
    request = stop_file(run["unit"])
    request.touch()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not still_running(run):
            # 运行在看到请求之前就自己结束时，请求文件留着没人删
            request.unlink(missing_ok=True)
            return 0
        time.sleep(0.2)
    print(
        "30 秒内实例没有停下。用 `limited_run.py status` 查看。",
        file=sys.stderr,
    )
    return 2


def seed():
    """
    本次运行的随机种子：调用方设了 ERARK_SEED 就用它，否则用默认种子
    返回：
        str: 种子
    """
    return os.environ.get("ERARK_SEED", DEFAULT_SEED)


def main(argv=None):
    """
    命令行入口
    参数：
        argv (list[str] | None): 命令行参数，不含脚本名；为 None 时读 sys.argv
    返回：
        int: 退出码
    """
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["status"]:
        return cmd_status()
    if argv[:1] == ["stop"] and len(argv) <= 2:
        return cmd_stop(*argv[1:])
    parser = argparse.ArgumentParser(
        prog="limited_run.py",
        usage=(
            f"%(prog)s [--mem {DEFAULT_MEM}] [--timeout 600] -- <命令...>\n       %(prog)s status\n       %(prog)s "
            f"stop [槽位|pid]"
        ),
        description=(
            f"在内存上限、运行时限和全机 {SLOTS} 个游戏槽位（每个 {SLOT_SIZE}）下运行一条命令；status "
            f"列出正在运行的实例，stop 停掉其中一个"
        ),
    )
    parser.add_argument(
        "--mem",
        type=parse_size,
        default=DEFAULT_MEM,
        help=f"内存上限，默认 {DEFAULT_MEM}",
    )
    parser.add_argument(
        "--timeout", type=int, default=600, help="运行时限（秒），默认 600"
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="-- 之后是要运行的命令"
    )
    args = parser.parse_args(argv)
    mem_max = args.mem
    if args.command[:1] != ["--"] or len(args.command) < 2:
        parser.error("在 -- 之后给出要运行的命令，或者只写 status、stop")
    game_checkout()
    return run(
        "headless",
        args.command[1:],
        mem_max,
        args.timeout,
        {"PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", seed())},
    )


if __name__ == "__main__":
    sys.exit(main())
