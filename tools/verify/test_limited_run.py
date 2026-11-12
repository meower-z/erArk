#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
limited_run.py 的测试：命令行解析、传给命令的散列种子、槽位的占用与释放（含进程被杀后释放）、退出码 75 的各种拒绝、
status 与 stop、
算上 earlyoom 的内存余量与退出码 76、各运行临时目录的删除与清理、finished 行的内存峰值；不启动游戏

用法：
    python3 tools/verify/test_limited_run.py
"""

import io
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import limited_run


def run_main(
    argv: list[str], environ: dict[str, str] | None = None
) -> mock.MagicMock:
    """
    在给定的环境变量下运行一次 limited_run.main，替换掉真正的启动
    参数：argv (list[str]) 命令行参数，不含脚本名；environ (dict[str, str] | None) 调用方的环境变量，为 None 时清空
    返回：mock.MagicMock 替换 run 的 mock，记下了调用参数
    """
    with mock.patch.dict(
        os.environ, environ or {}, clear=True
    ), mock.patch.object(limited_run, "game_checkout"), mock.patch.object(
        limited_run, "run", return_value=0
    ) as run:
        limited_run.main(argv)
    return run


class HashSeed(unittest.TestCase):
    """记下传给 run 的额外环境变量"""

    def extra(self, environ: dict[str, str]) -> dict[str, str]:
        """
        在给定的环境变量下运行一次 limited_run.py -- python3 x.py
        参数：environ (dict[str, str]) 调用方的环境变量
        返回：dict[str, str] 传给 run 的额外环境变量
        """
        return run_main(["--", "python3", "x.py"], environ).call_args.args[4]

    def test_default_seed(self) -> None:
        """调用方什么都没设时，用默认种子"""
        self.assertEqual(
            self.extra({}), {"PYTHONHASHSEED": limited_run.DEFAULT_SEED}
        )

    def test_erark_seed(self) -> None:
        """调用方设了 ERARK_SEED 时，用它"""
        self.assertEqual(
            self.extra({"ERARK_SEED": "7"}), {"PYTHONHASHSEED": "7"}
        )

    def test_caller_hash_seed_kept(self) -> None:
        """调用方自己设了 PYTHONHASHSEED 时，保留它"""
        self.assertEqual(
            self.extra({"PYTHONHASHSEED": "3", "ERARK_SEED": "7"}),
            {"PYTHONHASHSEED": "3"},
        )


class Arguments(unittest.TestCase):
    """命令行解析"""

    def test_defaults(self) -> None:
        """不给选项时用一个槽位（SLOT_SIZE）和 600 秒，-- 之后的命令原样传下去，不带 -- 本身"""
        self.assertEqual(limited_run.DEFAULT_MEM, limited_run.SLOT_SIZE)
        args = run_main(
            ["--", "python3", "-u", "x.py", "--mem", "1G"]
        ).call_args.args
        self.assertEqual(
            args[:4],
            (
                "headless",
                ["python3", "-u", "x.py", "--mem", "1G"],
                limited_run.parse_size(limited_run.SLOT_SIZE),
                600,
            ),
        )

    def test_options(self) -> None:
        """--mem 与 --timeout 写在 -- 之前时生效"""
        args = run_main(
            ["--mem", "512M", "--timeout", "30", "--", "true"]
        ).call_args.args
        self.assertEqual(args[2:4], (512 << 20, 30))

    def test_command_needs_double_dash(self) -> None:
        """没有 -- 或 -- 之后为空时报用法错误，不启动"""
        for argv in (["python3", "x.py"], ["--mem", "4G"], ["--"], ["statu"]):
            with self.subTest(argv=argv), self.assertRaises(
                SystemExit
            ) as caught, mock.patch("sys.stderr"):
                run_main(argv)
            self.assertEqual(caught.exception.code, 2)

    def test_status_and_stop(self) -> None:
        """status 与 stop 各自分派，不启动命令；stop 后面的槽位或 pid 原样传给 cmd_stop"""
        for argv, args in (
            (["status"], ()),
            (["stop"], ()),
            (["stop", "3"], ("3",)),
        ):
            action = argv[0]
            with self.subTest(argv=argv), mock.patch.object(
                limited_run, f"cmd_{action}", return_value=1
            ) as handler, mock.patch.object(limited_run, "run") as run:
                self.assertEqual(limited_run.main(argv), 1)
            handler.assert_called_once_with(*args)
            run.assert_not_called()


GIB = 1 << 30
SLOT = limited_run.parse_size(limited_run.SLOT_SIZE)


class SlotCase(unittest.TestCase):
    """
    槽位测试的公共部分：状态目录换成临时目录，当前目录是临时的 checkout，假定没有存活的 era-game scope；
    不碰本机正在用的槽位。
    假运行（hold）在本进程里拿锁，/proc/locks 里记的持锁者是本进程；
    slot_holders 换成把这些槽位的持锁者改写成假运行进程号的版本
    """

    real_slot_holders = staticmethod(limited_run.slot_holders)

    def setUp(self) -> None:
        """建临时状态目录与临时 checkout，并切换到 checkout"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmp = pathlib.Path(tmpdir.name).resolve()
        self.patch(limited_run, "STATE_DIR", self.tmp / "state")
        self.units = self.patch(
            limited_run, "active_game_units", return_value=[]
        )
        # 槽位编号到假运行进程号；只改写本进程真持有的槽位
        self.fake: dict[int, int] = {}
        self.handles: dict[int, list[tuple[int, io.TextIOWrapper]]] = {}
        self.patch(limited_run, "slot_holders", side_effect=self.holders)
        self.checkout = self.make_checkout("mine")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.checkout)

    def patch(self, target, name: str, *args, **kwargs):
        """
        替换一个属性，测试结束时还原
        参数：target 被替换属性所在的对象；name (str) 属性名；args、kwargs 传给 mock.patch.object
        返回：替换后的值，没给替换值时为新建的 mock
        """
        patcher = mock.patch.object(target, name, *args, **kwargs)
        replaced = patcher.start()
        self.addCleanup(patcher.stop)
        return replaced

    def holders(self) -> dict[int, int]:
        """
        真实的 slot_holders()，其中假运行拿着的槽位改写成假运行的进程号
        返回：dict[int, int] 槽位编号到持锁进程号
        """
        holders = type(self).real_slot_holders()
        for slot, pid in self.fake.items():
            if holders.get(slot) == os.getpid():
                holders[slot] = pid
        return holders

    def release(self, pid: int) -> None:
        """
        放开假运行拿着的槽位，相当于它的启动进程结束
        参数：pid (int) 假运行的进程号
        """
        limited_run.release_slots(self.handles.pop(pid))
        self.fake = {
            slot: owner for slot, owner in self.fake.items() if owner != pid
        }

    def make_checkout(self, name: str, web: bool = False) -> pathlib.Path:
        """
        建一个假的 erArk checkout：有 game.py 和 config.ini
        参数：name (str) 目录名；web (bool) config.ini 是否设 web_draw = 1
        返回：pathlib.Path checkout 根目录
        """
        root = self.tmp / name
        root.mkdir()
        (root / "game.py").write_text("")
        (root / "config.ini").write_text(
            f"[game]\ndebug = 0\nweb_draw = {int(web)}\n"
        )
        return root

    def hold(
        self,
        count: int,
        pid: int,
        cwd: pathlib.Path | None = None,
        mode: str = "headless",
        out: str | None = None,
    ) -> dict:
        """
        模拟另一次正在运行的实例：在本进程里另开文件拿 count 个槽位（flock 按打开的文件算，与 run()
        拿的互斥），并写下它的状态
        参数：count (int) 槽位数；pid (int) 假的启动进程号；cwd (pathlib.Path | None) 它的 checkout，默认另建一个；
        mode (str) headless 或 tk；out (str | None) tk 的证据目录
        返回：dict 它的状态
        """
        held = limited_run.take_slots(count)
        self.assertIsNotNone(held)
        self.addCleanup(limited_run.release_slots, held)
        self.handles[pid] = held
        self.fake.update({slot: pid for slot, _ in held})
        cwd = cwd or self.make_checkout(f"other-{pid}")
        state = {
            "unit": f"era-game-{pid}",
            "mode": mode,
            "pid": pid,
            "slots": [slot for slot, _ in held],
            "cwd": str(cwd),
            "mem_max_mib": count * SLOT >> 20,
            "command": f"python3 job-{pid}.py",
        }
        if out:
            state["out"] = out
        limited_run.write_state(state)
        return state

    def free_slots(self) -> int:
        """
        数一数现在空着的槽位
        返回：int 空槽位数
        """
        return limited_run.SLOTS - len(type(self).real_slot_holders())

    def launch(
        self,
        mem_max: int,
        during=None,
        running: int = 0,
        returncode: int | None = 0,
    ) -> tuple[int, str, mock.MagicMock]:
        """
        运行一次 limited_run.run()，scope 换成以 0 结束的假进程，sudo 与 systemctl 换成空操作，内存余量检查放行；
        标准输出记在 self.stdout
        参数：mem_max (int) 内存上限，字节；during (Callable | None) 假进程每次被查询是否结束时调用，
        用来查看运行中的状态；running (int) 假进程在前几次查询时还没结束；
            returncode (int | None) 假进程的 returncode，None 表示还没等到它结束
        返回：tuple 退出码、标准错误、替换 Popen 的 mock；假进程记在 self.proc，替换 Popen 的 mock 记在 self.popen
        """
        proc = self.proc = mock.Mock(returncode=returncode)
        polls = iter([None] * running)

        def poll():
            """先调 during，前 running 次返回 None（还在运行），之后返回 0"""
            seen = during() if during else None
            return next(polls, seen or 0)

        proc.poll.side_effect = poll
        stderr = io.StringIO()
        self.stdout = io.StringIO()
        with mock.patch.object(
            limited_run.subprocess, "Popen", return_value=proc
        ) as self.popen, mock.patch.object(
            limited_run.subprocess, "run", return_value=mock.Mock(stdout="")
        ) as self.systemctl, mock.patch.object(
            limited_run.signal, "signal"
        ), mock.patch(
            "sys.stderr", stderr
        ), mock.patch(
            "sys.stdout", self.stdout
        ):
            try:
                code = limited_run.run("headless", ["true"], mem_max, 10, {})
            except SystemExit as caught:
                code = caught.code
        return code, stderr.getvalue(), self.popen


class Slots(SlotCase):
    """槽位的计数、全拿或全不拿、释放"""

    def test_slots_needed(self) -> None:
        """一次运行占 ceil(内存上限 / SLOT_SIZE) 个槽位，至少一个；全部槽位正好放得下 SLOTS × SLOT_SIZE"""
        cases = {
            1 << 20: 1,
            SLOT: 1,
            SLOT + 1: 2,
            3 * SLOT: 3,
            limited_run.SLOTS * SLOT: limited_run.SLOTS,
            limited_run.SLOTS * SLOT + 1: limited_run.SLOTS + 1,
        }
        for mem_max, count in cases.items():
            with self.subTest(mem_max=mem_max):
                self.assertEqual(
                    limited_run.slots_needed(mem_max, self.checkout), count
                )

    def test_shipped_numbers(self) -> None:
        """现在的设定是 5 个 2G 槽位：2G 的运行占 1 个，3G 占 2 个，6G 占 3 个"""
        self.assertEqual((limited_run.SLOTS, SLOT), (5, 2 * GIB))
        self.assertEqual(
            [
                limited_run.slots_needed(mem, self.checkout)
                for mem in (2 * GIB, 3 * GIB, 6 * GIB)
            ],
            [1, 2, 3],
        )

    def test_run_holds_and_releases(self) -> None:
        """2 个槽位的运行拿到最小的两个空槽位，状态写在最小的槽位下；结束后槽位全空，状态文件删掉"""
        seen = []
        code, _, popen = self.launch(
            2 * SLOT, lambda: seen.append(limited_run.live_runs())
        )
        self.assertEqual(code, 0)
        popen.assert_called_once()
        self.assertEqual(len(seen[0]), 1)
        self.assertEqual(
            (seen[0][0]["slots"], seen[0][0]["pid"], seen[0][0]["cwd"]),
            ([0, 1], os.getpid(), str(self.checkout)),
        )
        self.assertEqual(self.free_slots(), limited_run.SLOTS)
        self.assertFalse(limited_run.slot_file(0, "json").exists())

    def test_runs_fill_slots(self) -> None:
        """别的 checkout 的运行占着 SLOTS-1 个槽位时，1 个槽位的运行照样启动，拿到剩下那个"""
        self.hold(limited_run.SLOTS - 1, 9001)
        seen = []
        code, _, popen = self.launch(
            SLOT,
            lambda: seen.append(
                [run["slots"] for run in limited_run.live_runs()]
            ),
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            seen[0],
            [list(range(limited_run.SLOTS - 1)), [limited_run.SLOTS - 1]],
        )

    def test_all_or_nothing(self) -> None:
        """只剩 1 个空槽位时，要 2 个的运行以 75 退出，不建 scope，消息列出占用者；剩下那个槽位仍然空着"""
        self.hold(limited_run.SLOTS - 1, 9001)
        code, message, popen = self.launch(2 * SLOT)
        self.assertEqual(code, limited_run.EXIT_BUSY)
        self.assertEqual(limited_run.EXIT_BUSY, 75)
        popen.assert_not_called()
        self.assertEqual(self.free_slots(), 1)
        for text in ("这次需要 2 个，空着 1 个", "pid 9001", "job-9001.py"):
            self.assertIn(text, message)
        self.assertIsNone(limited_run.take_slots(2))
        self.assertEqual(self.free_slots(), 1)

    def test_too_big_refused(self) -> None:
        """要的槽位超过全机槽位数时以 2 退出，不占任何槽位，不建 scope"""
        code, message, popen = self.launch(limited_run.SLOTS * SLOT + 1)
        self.assertEqual(code, 2)
        self.assertIn("等多久都启动不了", message)
        popen.assert_not_called()
        self.assertEqual(self.free_slots(), limited_run.SLOTS)

    def test_headroom_refusal_releases(self) -> None:
        """内存余量检查以 76 拒绝时，拿到的槽位与状态文件都放回"""
        self.patch(
            limited_run,
            "check_headroom",
            side_effect=SystemExit(limited_run.EXIT_NO_HEADROOM),
        )
        code, _, popen = self.launch(2 * SLOT)
        self.assertEqual(code, limited_run.EXIT_NO_HEADROOM)
        popen.assert_not_called()
        self.assertEqual(self.free_slots(), limited_run.SLOTS)
        self.assertEqual(list(limited_run.STATE_DIR.glob("*.json")), [])

    def test_crash_releases(self) -> None:
        """拿着槽位的进程被 SIGKILL 杀掉后，内核放开它的锁，槽位又空了"""
        script = (
            "import pathlib, sys, time; sys.path.insert(0, sys.argv[1]); import limited_run; limited_run.STATE_DIR = "
            "pathlib.Path(sys.argv[2]); held = limited_run.take_slots(2); print(held is not None, flush=True); "
            "time.sleep(60)"
        )
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(pathlib.Path(limited_run.__file__).parent),
                str(limited_run.STATE_DIR),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.assertEqual(child.stdout.readline().strip(), "True")
        self.assertEqual(self.free_slots(), limited_run.SLOTS - 2)
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        self.assertEqual(self.free_slots(), limited_run.SLOTS)

    def test_stale_state_ignored(self) -> None:
        """锁空着的状态文件是死掉的运行留下的：live_runs 不算它，新运行拿到这个槽位时覆盖它；
        同一进程号旧运行留下的停止请求也删掉，不会一启动就停"""
        limited_run.STATE_DIR.mkdir(parents=True)
        limited_run.slot_file(0, "json").write_text(
            json.dumps(
                {
                    "unit": "era-game-4242",
                    "pid": 4242,
                    "slots": [0],
                    "cwd": str(self.checkout),
                    "mode": "headless",
                }
            )
        )
        own_stop = limited_run.stop_file(f"era-game-{os.getpid()}")
        own_stop.touch()
        self.assertEqual(limited_run.live_runs(), [])
        seen = []
        code, _, _ = self.launch(
            SLOT,
            lambda: seen.append(
                (limited_run.read_state(0)["pid"], own_stop.exists())
            ),
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen[0], (os.getpid(), False))

    def test_handover_scope_is_orphan(self) -> None:
        """状态记着 9001、槽位锁却已由另一个进程（9999，还没写状态）持有时，9001 不算活着，它的 scope 算遗留，
        新运行以 75 拒绝"""
        self.hold(1, 9001)
        self.fake[0] = 9999
        self.units.return_value = ["era-game-9001.scope"]
        self.assertEqual(limited_run.live_runs(), [])
        code, message, popen = self.launch(SLOT)
        self.assertEqual(code, limited_run.EXIT_BUSY)
        self.assertIn("era-game-9001.scope", message)
        popen.assert_not_called()

    def test_tmpdir_and_reset_failed(self) -> None:
        """每次运行的 TMPDIR 是自己的目录，名字是 unit 加随机后缀；reset-failed 只清自己 unit 名下的记录"""
        code, _, popen = self.launch(SLOT)
        self.assertEqual(code, 0)
        unit = f"era-game-{os.getpid()}"
        tmpdir = pathlib.Path(
            next(
                arg
                for arg in popen.call_args.args[0]
                if arg.startswith("TMPDIR=")
            )[len("TMPDIR=") :]
        )
        self.assertEqual(tmpdir.parent, limited_run.STATE_DIR / "tmp")
        found = limited_run.TMPDIR_PATTERN.match(tmpdir.name)
        assert found is not None
        self.assertEqual(found.group(1), unit)
        resets = [
            call.args[0]
            for call in self.systemctl.call_args_list
            if "reset-failed" in call.args[0]
        ]
        self.assertTrue(resets)
        self.assertTrue(
            all(argv[-1] == f"{unit}.scope" for argv in resets), resets
        )


class TmpDirs(SlotCase):
    """运行结束时删掉自己的临时目录；启动时清掉已结束的运行留下的临时目录"""

    def setUp(self) -> None:
        """记下本次运行的 scope 名称；临时目录由 mkdtemp 建，名字运行中才知道"""
        super().setUp()
        self.unit = f"era-game-{os.getpid()}"
        self.own: pathlib.Path

    def tmpdir_of_launch(self) -> pathlib.Path:
        """
        取出正在进行的 launch 传给 scope 的 TMPDIR
        返回：pathlib.Path 临时目录
        """
        return pathlib.Path(
            next(
                arg
                for arg in self.popen.call_args.args[0]
                if arg.startswith("TMPDIR=")
            )[len("TMPDIR=") :]
        )

    def write_into_own(self) -> None:
        """假命令运行中往临时目录写文件，相当于命令用 tempfile 写日志；临时目录取环境里的 TMPDIR，它不存在时测试失败"""
        self.own = self.tmpdir_of_launch()
        self.assertTrue(self.own.is_dir(), "运行中临时目录不存在")
        (self.own / "sub").mkdir(exist_ok=True)
        (self.own / "sub" / "log.txt").write_text("x")

    def fake_cgroup(self) -> None:
        """cgroup 目录换成临时目录，测试自己在其中建或删 scope 的目录；内存余量检查跟着换掉，放行"""
        self.patch(limited_run, "CGROUP", self.tmp / "cgroup")
        self.patch(limited_run, "check_headroom")

    def finished(self) -> dict:
        """
        取出最近一次 launch 打印的 finished 行
        返回：dict finished 事件
        """
        return [
            event
            for event in map(json.loads, self.stdout.getvalue().splitlines())
            if event["event"] == "finished"
        ][-1]

    def test_removed_after_exit(self) -> None:
        """命令正常结束后临时目录连同其中文件一起删掉，finished 行不带 tmpdir"""
        code, _, _ = self.launch(SLOT, self.write_into_own)
        self.assertEqual(code, 0)
        self.assertFalse(self.own.exists())
        self.assertNotIn("tmpdir", self.finished())

    def test_removed_after_timeout(self) -> None:
        """scope 因运行时限结束（退出码 124）时同样删掉"""
        self.patch(limited_run, "read_and_clear_result", return_value="timeout")
        code, _, _ = self.launch(SLOT, self.write_into_own)
        self.assertEqual(code, limited_run.REASON_EXIT["timeout"])
        self.assertFalse(self.own.exists())

    def test_removed_after_stop(self) -> None:
        """收到停止请求、停掉 scope 后同样删掉"""

        def request_stop():
            self.write_into_own()
            limited_run.stop_file(self.unit).touch()

        code, _, _ = self.launch(SLOT, request_stop, running=1)
        self.assertEqual(code, limited_run.REASON_EXIT["stopped-headless"])
        self.assertFalse(self.own.exists())

    def test_kept_while_scope_alive(self) -> None:
        """停过之后 scope 的 cgroup 目录还在、或 systemd 仍列出这个 scope 时，其中的进程可能还在写，
        临时目录留着，退出码不变"""
        self.fake_cgroup()
        for case in ("cgroup", "unit"):
            with self.subTest(case=case):
                if case == "cgroup":
                    limited_run.scope_dir(self.unit).mkdir(parents=True)
                else:
                    limited_run.scope_dir(self.unit).rmdir()
                    self.units.return_value = [f"{self.unit}.scope"]
                code, _, _ = self.launch(SLOT, self.write_into_own)
                self.assertEqual(code, 0)
                self.assertTrue((self.own / "sub" / "log.txt").exists())

    def test_launcher_stopped_before_scope(self) -> None:
        """刚启动、scope 还没建好就收到 SIGTERM：停掉启动的进程（systemd-run）并等它结束，再放开槽位、删掉临时目录"""
        calls = []

        def terminate():
            calls.append(1)
            if len(calls) == 1:
                self.write_into_own()
                raise SystemExit(128 + signal.SIGTERM)

        code, _, _ = self.launch(SLOT, terminate, returncode=None)
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.proc.terminate.assert_called_once_with()
        self.proc.wait.assert_called_once_with()
        self.assertFalse(self.own.exists())
        self.assertEqual(self.free_slots(), limited_run.SLOTS)

    def test_unique_per_launch(self) -> None:
        """每次运行拿一个新目录，名字是 scope 名称加随机后缀：同一进程号的前一次运行留下的目录不会被接手，
        也不会被这次运行删掉"""
        stale = limited_run.STATE_DIR / "tmp" / f"{self.unit}-stale"
        stale.mkdir(parents=True)
        dirs = []
        for _ in range(2):
            self.assertEqual(
                self.launch(SLOT, lambda: dirs.append(self.tmpdir_of_launch()))[
                    0
                ],
                0,
            )
        self.assertNotEqual(dirs[0], dirs[1])
        for path in dirs:
            found = limited_run.TMPDIR_PATTERN.match(path.name)
            assert found is not None
            self.assertEqual(found.group(1), self.unit)
            self.assertNotEqual(path, stale)
        self.assertTrue(stale.is_dir())

    @unittest.skipIf(os.geteuid() == 0, "root 删得掉只读目录里的文件")
    def test_removal_error_keeps_result(self) -> None:
        """临时目录里有删不掉的文件（只读子目录）时跳过，退出码与 finished 行照常"""

        def write_locked():
            self.write_into_own()
            (self.own / "sub").chmod(0o500)

        self.addCleanup(lambda: (self.own / "sub").chmod(0o700))
        code, _, _ = self.launch(SLOT, write_locked)
        self.assertEqual(code, 0)
        self.assertEqual(
            (self.finished()["reason"], self.finished()["returncode"]),
            ("exit", 0),
        )
        self.assertTrue((self.own / "sub" / "log.txt").exists())

    def age(self, *paths: pathlib.Path) -> None:
        """
        把目录的改动时间调到 SWEEP_MIN_AGE_S 之前，清理才会考虑它
        参数：paths (pathlib.Path) 目录
        """
        old = time.time() - limited_run.SWEEP_MIN_AGE_S - 60
        for path in paths:
            os.utime(path, (old, old))

    def make_entries(self) -> dict[str, pathlib.Path]:
        """
        在 STATE_DIR/tmp 下放各种目录与文件：已结束的运行、只是 scope 名称、没有随机后缀的目录、正在运行的 9001、
        存活的遗留 scope 777、
        systemd 没列出但 cgroup 目录还在的 778、刚改动过的 779、进程号被无关进程重用的目录、本次 scope 名称的、
        指向别处的符号链接、同名的普通文件、名字不对的目录
        返回：dict[str, pathlib.Path] 名称到路径
        """
        root = limited_run.STATE_DIR / "tmp"
        root.mkdir(parents=True)
        self.hold(1, 9001)
        self.units.return_value = ["era-game-777.scope"]
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("x")
        self.fake_cgroup()
        limited_run.scope_dir("era-game-778").mkdir(parents=True)
        names = (
            "era-game-4242-ab_1",
            "era-game-4243",
            "era-game-9001-x",
            "era-game-777-x",
            "era-game-778-x",
            "era-game-779-x",
            f"era-game-{os.getppid()}-x",
            f"{self.unit}-x",
            "era-game-x",
            "era-game-12-AB",
            "other",
        )
        entries = {name: root / name for name in names}
        for path in entries.values():
            path.mkdir()
            (path / "log.txt").write_text("x")
        self.age(
            *(
                path
                for name, path in entries.items()
                if name != "era-game-779-x"
            )
        )
        entries["link"] = root / "era-game-555-x"
        entries["link"].symlink_to(outside)
        entries["file"] = root / "era-game-556-x"
        entries["file"].write_text("x")
        return entries

    def test_sweep(self) -> None:
        """
        清掉已结束的运行与进程号被重用的目录；
        留下正在运行的、存活 scope 的（systemd 列出的 777，或 systemd 没列出、cgroup 目录还在的 778）、
        刚改动过的（779）、本次 scope 名称的、
        没有随机后缀、只是 scope 名称的（era-game-4243，清理不动它）、符号链接（及其指向的文件）、普通文件、名字不对的
        """
        entries = self.make_entries()
        limited_run.sweep_tmpdirs(self.unit)
        removed = {"era-game-4242-ab_1", f"era-game-{os.getppid()}-x"}
        for name, path in entries.items():
            with self.subTest(name=name):
                self.assertEqual(
                    os.path.lexists(path), path.name not in removed
                )
        self.assertTrue((self.tmp / "outside" / "keep.txt").exists())

    def test_run_sweeps(self) -> None:
        """一次运行启动时就清：运行中已结束的运行的目录已不在，正在运行的 9001 的目录还在"""
        root = limited_run.STATE_DIR / "tmp"
        root.mkdir(parents=True)
        self.hold(1, 9001)
        for name in ("era-game-4242-x", "era-game-9001-x"):
            (root / name).mkdir()
            self.age(root / name)
        seen = []
        code, _, _ = self.launch(
            SLOT,
            lambda: seen.append(
                sorted(
                    path.name
                    for path in root.iterdir()
                    if not path.name.startswith(f"{self.unit}-")
                )
            ),
        )
        self.assertEqual(code, 0)
        self.assertEqual(seen[0], ["era-game-9001-x"])
        self.assertTrue((root / "era-game-9001-x").is_dir())

    def test_sweep_races_and_missing(self) -> None:
        """另一次运行同时清掉了同一个目录时不报错；STATE_DIR/tmp 不存在时什么都不做"""
        limited_run.sweep_tmpdirs(self.unit)
        dead = limited_run.STATE_DIR / "tmp" / "era-game-4242-x"
        dead.mkdir(parents=True)
        self.age(dead)

        def remove_dead(unit, real_scope_dir=limited_run.scope_dir):
            dead.rmdir()
            return real_scope_dir(unit)

        self.patch(limited_run, "scope_dir", side_effect=remove_dead)
        limited_run.sweep_tmpdirs(self.unit)
        self.assertFalse(dead.exists())


class MemoryPeak(SlotCase):
    """finished 行的两个内存峰值：memory_peak_mib 是 scope 的 memory.peak，含文件缓存；
    unreclaimable_peak_mib 是运行中各次取样里回收不了的内存的最大值"""

    def test_unreclaimable_peak(self) -> None:
        """文件缓存把 memory.peak 推到上限时，unreclaimable_peak_mib 只报各次取样里 anon、shmem、内核内存之和的最大值；
        scope 还没有 memory.stat 的那次取样跳过"""
        self.patch(limited_run, "CGROUP", self.tmp / "cgroup")
        self.patch(limited_run, "check_headroom")
        unit_dir = limited_run.scope_dir(f"era-game-{os.getpid()}")
        unit_dir.mkdir(parents=True)
        (unit_dir / "memory.peak").write_text(str(SLOT))
        # 每次取样前写入的 (anon, shmem, kernel, file)，MiB；None 表示 memory.stat 还不存在
        samples = iter(
            [None, (700, 10, 5, 1300), (1300, 20, 6, 700), (400, 0, 4, 1600)]
        )

        def write_stat() -> None:
            """假命令每被查询一次是否结束，就换一组 memory.stat 的值"""
            values = next(samples, None)
            if values:
                anon, shmem, kernel, file = (value << 20 for value in values)
                (unit_dir / "memory.stat").write_text(
                    f"anon {anon}\nfile {file}\nkernel {kernel}\nshmem {shmem}\n"
                )

        code, _, _ = self.launch(SLOT, write_stat, running=4)
        self.assertEqual(code, 0)
        finished = [
            event
            for event in map(json.loads, self.stdout.getvalue().splitlines())
            if event["event"] == "finished"
        ][-1]
        self.assertEqual(
            (finished["memory_peak_mib"], finished["unreclaimable_peak_mib"]),
            (SLOT >> 20, 1300 + 20 + 6),
        )


class Refusals(SlotCase):
    """槽位够用也以 75 拒绝的情形：不属于任何运行的 scope、web 模式、同一 checkout"""

    def test_orphan_scope(self) -> None:
        """有不属于任何运行的存活 scope 时以 75 拒绝并写出它；属于正在运行的实例的 scope 不算"""
        self.hold(1, 9001)
        self.units.return_value = ["era-game-9001.scope", "era-game-777.scope"]
        code, message, popen = self.launch(SLOT)
        self.assertEqual(code, limited_run.EXIT_BUSY)
        self.assertIn("era-game-777.scope", message)
        self.assertNotIn("era-game-9001.scope", message)
        popen.assert_not_called()
        self.assertEqual(self.free_slots(), limited_run.SLOTS - 1)
        self.units.return_value = ["era-game-9001.scope"]
        self.assertEqual(self.launch(SLOT)[0], 0)

    def test_run_registering_between_reads(self) -> None:
        """另一次运行在本次读完运行列表之后、列 scope 之前写下状态并建好 scope 时，它的 scope 不算遗留，
        本次启动不被拒绝"""
        held = limited_run.take_slots(1)
        self.addCleanup(limited_run.release_slots, held)
        slot = held[0][0]
        late = {
            "unit": "era-game-9005",
            "mode": "headless",
            "pid": 9005,
            "slots": [slot],
            "cwd": str(self.make_checkout("other-9005")),
            "mem_max_mib": 2048,
            "command": "python3 job-9005.py",
        }

        def register():
            """列 scope 的那一刻，9005 刚写下状态、建好 scope"""
            if self.fake.get(slot) != 9005:
                self.fake[slot] = 9005
                limited_run.write_state(late)
            return ["era-game-9005.scope"]

        self.units.side_effect = register
        code, message, popen = self.launch(SLOT)
        self.assertEqual(code, 0, message)
        popen.assert_called_once()

    def test_web_mode_keeps_size_check(self) -> None:
        """web 模式的内存上限超过全部槽位时，照样以 2 拒绝，不因占全部槽位而放行"""
        (self.checkout / "config.ini").write_text("[game]\nweb_draw = 1\n")
        code, message, popen = self.launch(limited_run.SLOTS * SLOT + 1)
        self.assertEqual(code, 2)
        self.assertIn("等多久都启动不了", message)
        popen.assert_not_called()

    def test_web_mode_takes_all(self) -> None:
        """config.ini 设了 web_draw = 1 时，不管内存上限多少都占全部槽位；别人占着一个时以 75 拒绝"""
        (self.checkout / "config.ini").write_text("[game]\nweb_draw = 1\n")
        self.assertEqual(
            limited_run.slots_needed(SLOT, self.checkout), limited_run.SLOTS
        )
        seen = []
        self.assertEqual(
            self.launch(
                SLOT, lambda: seen.append(limited_run.live_runs()[0]["slots"])
            )[0],
            0,
        )
        self.assertEqual(seen[0], list(range(limited_run.SLOTS)))
        self.hold(1, 9001)
        code, message, _ = self.launch(SLOT)
        self.assertEqual(code, limited_run.EXIT_BUSY)
        self.assertIn(f"这次需要 {limited_run.SLOTS} 个", message)

    def test_same_checkout(self) -> None:
        """同一 checkout（经符号链接进来也算）已有运行时以 75 拒绝；
        消息写出 checkout、占用者的 pid、槽位、模式、命令，并让调用方换自己的 worktree"""
        self.hold(1, 9001, cwd=self.checkout, mode="tk", out="/x/run")
        link = self.tmp / "link"
        link.symlink_to(self.checkout)
        os.chdir(link)
        code, message, popen = self.launch(SLOT)
        self.assertEqual(code, limited_run.EXIT_BUSY)
        popen.assert_not_called()
        for text in (
            f"checkout {self.checkout} 正被另一次运行占用",
            "槽位 [0]",
            "pid 9001",
            "tk",
            "job-9001.py",
            "别等重试窗口",
            "worktree",
        ):
            self.assertIn(text, message)
        self.assertEqual(self.free_slots(), limited_run.SLOTS - 1)

    def test_other_checkout_runs(self) -> None:
        """别的 checkout 的运行不妨碍本 checkout 启动"""
        self.hold(1, 9001)
        self.assertEqual(self.launch(SLOT)[0], 0)


class RealLocks(unittest.TestCase):
    """用真进程和本机真实的 /proc/locks 判断哪次运行活着：状态文件只是线索，锁的真实持有者才算数"""

    CHILD = (
        "import pathlib, sys, time; sys.path.insert(0, sys.argv[1]); import limited_run; limited_run.STATE_DIR = "
        "pathlib.Path(sys.argv[2]); held = limited_run.take_slots(1); {body}; print(held[0][0], flush=True); "
        "time.sleep(60)"
    )

    def setUp(self) -> None:
        """状态目录换成临时目录，scope 列表换成可设的假列表"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        patcher = mock.patch.object(
            limited_run, "STATE_DIR", pathlib.Path(tmpdir.name) / "state"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        units_patcher = mock.patch.object(
            limited_run, "active_game_units", return_value=[]
        )
        self.units = units_patcher.start()
        self.addCleanup(units_patcher.stop)

    def child(self, body: str = "pass") -> subprocess.Popen:
        """
        起一个拿着 1 个槽位的子进程，等它报告拿到的槽位
        参数：body (str) 拿到槽位之后、报告之前执行的语句，可用 held
        返回：subprocess.Popen 子进程，测试结束时杀掉并回收
        """
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                self.CHILD.format(body=body),
                str(pathlib.Path(limited_run.__file__).parent),
                str(limited_run.STATE_DIR),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "0")
        return proc

    def state_of(self, pid: int) -> dict:
        """
        一份占槽位 0 的运行状态
        参数：pid (int) 启动进程号
        返回：dict 状态
        """
        return {
            "unit": f"era-game-{pid}",
            "mode": "headless",
            "pid": pid,
            "slots": [0],
            "cwd": f"/c/{pid}",
            "mem_max_mib": 2048,
            "command": f"job-{pid}",
        }

    def test_zombie_launcher(self) -> None:
        """启动进程被 SIGKILL 后成了没回收的僵尸、它的槽位已被别的进程接手：僵尸的状态不算活着的运行，
        它的 scope 算遗留"""
        launcher = self.child(
            "limited_run.write_state({'unit': 'era-game-%d' % __import__('os').getpid(), 'mode': 'headless', 'pid': "
            "__import__('os').getpid(), 'slots': [0], 'cwd': '/c/z', 'mem_max_mib': 2048, 'command': 'job-z'})"
        )
        os.kill(launcher.pid, signal.SIGKILL)
        for _ in range(100):
            if (
                pathlib.Path(f"/proc/{launcher.pid}/stat")
                .read_text()
                .split(")")[1]
                .split()[0]
                == "Z"
            ):
                break
            time.sleep(0.05)
        self.assertEqual(
            pathlib.Path(f"/proc/{launcher.pid}/stat")
            .read_text()
            .split(")")[1]
            .split()[0],
            "Z",
        )
        handle = limited_run.lock_slot(0)
        self.assertIsNotNone(handle)
        self.addCleanup(handle.close)
        self.assertEqual(limited_run.read_state(0)["pid"], launcher.pid)
        self.assertEqual(limited_run.live_runs(), [])
        self.units.return_value = [f"era-game-{launcher.pid}.scope"]
        self.assertEqual(
            limited_run.orphan_units(limited_run.live_runs()),
            [f"era-game-{launcher.pid}.scope"],
        )

    def test_handover(self) -> None:
        """槽位 0 的锁在另一个进程手里、状态文件却记着一个还活着但不持锁的进程：活着的运行是持锁的那个，不是旧状态；
        持锁者写下状态后它才算活着"""
        bystander = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"]
        )
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        holder = self.child()
        limited_run.write_state(self.state_of(bystander.pid))
        self.assertEqual(limited_run.live_runs(), [])
        self.units.return_value = [f"era-game-{bystander.pid}.scope"]
        self.assertEqual(
            limited_run.orphan_units(limited_run.live_runs()),
            [f"era-game-{bystander.pid}.scope"],
        )
        limited_run.write_state(self.state_of(holder.pid))
        self.assertEqual(
            [run["pid"] for run in limited_run.live_runs()], [holder.pid]
        )

    def test_proc_locks_parsing(self) -> None:
        """假的 /proc/locks 与 mountinfo：只认 FLOCK 的持有者（不认等待者与 POSIX 锁），
        设备号按文件所在挂载点（最长前缀）对上，十六进制的设备号也能对上"""
        lock = limited_run.slot_file(0, "lock")
        lock.parent.mkdir(parents=True)
        lock.touch()
        inode = lock.stat().st_ino
        proc = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(proc))
        (proc / "self").mkdir()
        (proc / "self" / "mountinfo").write_text(
            "1 0 0:47 / / rw - btrfs /dev/x rw\n2 1 0:99 / /tmp rw - tmpfs none rw\n3 2 0:98 / /tmp/elsewhere rw - "
            "tmpfs none rw\n"
        )
        (proc / "locks").write_text(
            f"1: FLOCK  ADVISORY  WRITE 7777 00:2f:{inode} 0 EOF\n"
            f"2: POSIX  ADVISORY  WRITE 6666 00:63:{inode} 0 EOF\n"
            f"3: FLOCK  ADVISORY  WRITE 4242 00:63:{inode} 0 EOF\n"
            f"3: -> FLOCK  ADVISORY  WRITE 5555 00:63:{inode} 0 EOF\n"
        )
        with mock.patch.object(limited_run, "PROC", proc):
            self.assertEqual(limited_run.slot_holders(), {0: 4242})


class StatusAndStop(SlotCase):
    """有几次运行时的 status 与 stop"""

    def setUp(self) -> None:
        """起两次假的运行：9001 占 1 个槽位，9002 占 2 个"""
        super().setUp()
        self.first = self.hold(1, 9001)
        self.second = self.hold(2, 9002, mode="tk", out="/x/run")
        self.patch(
            limited_run,
            "memory_headroom",
            return_value=(5 * GIB, (5 * GIB, 10 * GIB, {}), None),
        )

    def stop(self, target: str | None) -> tuple[int, str, list[pathlib.Path]]:
        """
        运行一次 cmd_stop；假运行看到自己的停止请求时放开槽位（真的启动进程停掉 scope 后在 finally 里这样做）
        参数：target (str | None) 槽位编号或 pid
        返回：tuple 退出码、标准错误、出现过的停止请求文件
        """
        requested = []

        def tick(_seconds):
            for state in (self.first, self.second):
                stop = limited_run.stop_file(state["unit"])
                if stop.exists():
                    requested.append(stop)
                    stop.unlink()
                    limited_run.slot_file(state["slots"][0], "json").unlink()
                    self.release(state["pid"])

        stderr = io.StringIO()
        with mock.patch.object(
            limited_run.time, "sleep", side_effect=tick
        ), mock.patch("sys.stderr", stderr):
            code = limited_run.cmd_stop(target)
        return code, stderr.getvalue(), requested

    def test_status_lists_runs(self) -> None:
        """status 每次运行一行（pid、模式、cwd、命令、内存上限、当前内存），遗留 scope 一行，最后一行是槽位占用与余量"""
        self.units.return_value = [
            "era-game-9001.scope",
            "era-game-9002.scope",
            "era-game-777.scope",
        ]
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(limited_run.cmd_status(), 0)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([line.get("pid") for line in lines[:2]], [9001, 9002])
        for line in lines[:2]:
            self.assertTrue(
                {"slots", "mode", "cwd", "command", "mem_max_mib", "memory_mib"}
                <= line.keys(),
                line,
            )
        self.assertEqual(lines[2]["orphan_unit"], "era-game-777.scope")
        self.assertEqual(
            lines[3],
            {
                "slots_used": 3,
                "slots": limited_run.SLOTS,
                "slot_size": limited_run.SLOT_SIZE,
                "headroom_mib": 5120,
                "memory_high_mib": 10240,
            },
        )

    def test_status_idle(self) -> None:
        """没有运行时 status 只打印槽位与余量那一行，以 1 退出"""
        limited_run.slot_file(0, "json").unlink()
        limited_run.slot_file(1, "json").unlink()
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(limited_run.cmd_status(), 1)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_bare_stop_with_several(self) -> None:
        """不给目标、有两次运行时不停任何一个，列出它们，以 1 退出"""
        code, message, requested = self.stop(None)
        self.assertEqual((code, requested), (1, []))
        self.assertIn("pid 9001", message)
        self.assertIn("pid 9002", message)

    def test_stop_by_pid_and_slot(self) -> None:
        """stop <pid> 与 stop <槽位> 只停那一次运行，另一次不动"""
        code, _, requested = self.stop("9002")
        self.assertEqual(
            (code, requested), (0, [limited_run.stop_file("era-game-9002")])
        )
        self.assertEqual(
            [run["pid"] for run in limited_run.live_runs()], [9001]
        )
        code, _, requested = self.stop(str(self.first["slots"][0]))
        self.assertEqual(
            (code, requested), (0, [limited_run.stop_file("era-game-9001")])
        )
        self.assertEqual(limited_run.live_runs(), [])

    def test_bare_stop_with_one(self) -> None:
        """只有一次运行时不给目标也停它"""
        limited_run.slot_file(self.first["slots"][0], "json").unlink()
        code, _, requested = self.stop(None)
        self.assertEqual(
            (code, requested), (0, [limited_run.stop_file("era-game-9002")])
        )

    def test_stop_after_slot_handover(self) -> None:
        """选中的运行在发请求前已结束、它的槽位被另一次运行接手时，请求只对原来那次运行，不落到接手的运行头上"""
        stale = [dict(self.first)]
        limited_run.slot_file(self.first["slots"][0], "json").unlink()
        self.fake[self.first["slots"][0]] = 9003
        limited_run.write_state(
            {
                **self.first,
                "unit": "era-game-9003",
                "pid": 9003,
                "command": "python3 job-9003.py",
            }
        )
        with mock.patch.object(
            limited_run, "live_runs", return_value=stale
        ), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(limited_run.cmd_stop("9001"), 0)
        self.assertEqual(list(limited_run.STATE_DIR.glob("*.stop")), [])
        self.assertEqual(
            limited_run.read_state(self.first["slots"][0])["pid"], 9003
        )

    def test_stop_unknown(self) -> None:
        """没有这个槽位或 pid 的运行、或目标不是数时以 1 退出，什么都不停"""
        for target in ("99999", "abc"):
            with self.subTest(target=target):
                code, _, requested = self.stop(target)
                self.assertEqual((code, requested), (1, []))

    def test_stop_orphan(self) -> None:
        """stop <pid> 指向遗留 scope 时直接停掉它"""
        self.units.return_value = ["era-game-777.scope"]
        stop_unit = self.patch(
            limited_run,
            "stop_unit",
            side_effect=lambda unit: self.units.configure_mock(return_value=[]),
        )
        self.patch(limited_run, "read_and_clear_result", return_value="")
        code, _, requested = self.stop("777")
        self.assertEqual((code, requested), (0, []))
        stop_unit.assert_called_once_with("era-game-777")


class Headroom(unittest.TestCase):
    """内存余量取容器余量与 earlyoom 余量中较小的一个；/proc 换成临时目录里的假进程与假 meminfo"""

    def setUp(self) -> None:
        """建一个假 /proc：总内存 12 GiB、可用 8 GiB，容器余量假定为 10 GiB"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.proc = pathlib.Path(tmpdir.name)
        (self.proc / "meminfo").write_text(
            f"MemTotal:       {12 << 20} kB\nMemFree:        {1 << 20} kB\nMemAvailable:   {8 << 20} kB\n"
        )
        for name, value in {
            "PROC": self.proc,
            "container_headroom": lambda: (
                10 * GIB,
                11 * GIB,
                {"anon": GIB, "shmem": 0, "kernel": 0},
            ),
        }.items():
            patcher = mock.patch.object(limited_run, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def process(self, pid: int, comm: str, *args: str) -> None:
        """
        在假 /proc 里放一个进程
        参数：pid (int) 进程号；comm (str) 进程名；args (str) 命令行参数，不含程序本身
        """
        (self.proc / str(pid)).mkdir()
        (self.proc / str(pid) / "comm").write_text(comm + "\n")
        (self.proc / str(pid) / "cmdline").write_bytes(
            b"\0".join(arg.encode() for arg in (f"/usr/bin/{comm}", *args))
            + b"\0"
        )

    def test_container_limit(self) -> None:
        """容器的内存线取 memory.high；它为 max 时取 memory.max；两者都为 max 或都没有时取 MemTotal"""
        cgroup = self.proc / "cgroup"
        cgroup.mkdir()
        cases = {
            ("8589934592", "max"): 8 * GIB,
            ("max", "9663676416"): 9 * GIB,
            ("max", "max"): 12 * GIB,
            (None, None): 12 * GIB,
        }
        with mock.patch.object(limited_run, "CGROUP", cgroup):
            for (high, top), limit in cases.items():
                with self.subTest(high=high, max=top):
                    for name, value in (
                        ("memory.high", high),
                        ("memory.max", top),
                    ):
                        if value is None:
                            (cgroup / name).unlink(missing_ok=True)
                        else:
                            (cgroup / name).write_text(value + "\n")
                    self.assertEqual(limited_run.container_limit(), limit)

    def test_earlyoom_margin(self) -> None:
        """earlyoom -m 20 时，余量是可用内存减去总内存的 20%，比容器余量小就用它；
        再有一个 -m 15 的 earlyoom 时仍按 20%"""
        self.process(7, "python3", "-m", "50")
        self.process(
            42, "earlyoom", "-m", "20", "-s", "100", "--prefer", "^python"
        )
        expected = (8 << 20) * 1024 - int((12 << 20) * 0.2) * 1024
        self.assertEqual(limited_run.earlyoom_headroom(), (expected, 20.0))
        self.assertEqual(limited_run.memory_headroom()[0], expected)
        self.process(43, "earlyoom", "-m", "15")
        self.assertEqual(limited_run.earlyoom_headroom()[1], 20.0)

    def test_percent_forms(self) -> None:
        """各种写法下 SIGTERM 线的百分比，与 earlyoom v1.7 --dryrun 在 12 GiB 机器上打印的一致；
        组合短选项和重复选项按 earlyoom 的规则"""
        total = 12 << 20
        cases = {
            ("-m", "20", "-r", "0"): 20.0,
            ("-m20,10",): 20.0,
            ("-m", "10,20"): 20.0,
            ("-r", "0"): 10.0,
            ("-M", "2000000"): 2000000 * 100 / total,
            ("-m", "20", "-M", "1000000"): 1000000 * 100 / total,
            ("-m", "5", "-M", "3000000"): 5.0,
            ("-m", "10", "-m", "20"): 20.0,
            ("-m", "20", "-m", "10,15"): 15.0,
            ("-M", "1000000", "-M", "2000000"): 2000000 * 100 / total,
            ("-dm20",): 20.0,
            ("-dm", "20"): 20.0,
            ("--pref", "^x", "-m", "20"): 20.0,
        }
        for args, percent in cases.items():
            with self.subTest(args=args):
                self.assertAlmostEqual(
                    limited_run.earlyoom_percent(list(args), total), percent
                )

    def test_unknown_option(self) -> None:
        """命令行里有 earlyoom v1.7 没有的选项时报错退出，不猜杀进程线"""
        with self.assertRaises(SystemExit) as caught:
            limited_run.earlyoom_percent(
                ["--sort-by-rss", "-m", "20"], 12 << 20
            )
        self.assertIn("读不懂 earlyoom 的命令行", str(caught.exception.code))

    def test_dryrun_ignored(self) -> None:
        """带 --dryrun 的 earlyoom 不杀进程，不算进余量；它旁边有真正的 earlyoom 时按那个算"""
        self.process(42, "earlyoom", "-m", "50", "--dryrun")
        self.assertIsNone(limited_run.earlyoom_headroom())
        self.process(43, "earlyoom", "-m", "20")
        self.assertEqual(limited_run.earlyoom_headroom()[1], 20.0)

    def test_no_earlyoom(self) -> None:
        """earlyoom 没在运行时不留额外余量，余量就是容器余量"""
        self.process(7, "python3", "-m", "20")
        self.assertIsNone(limited_run.earlyoom_headroom())
        self.assertEqual(limited_run.memory_headroom()[0], 10 * GIB)

    def check(self, mem_max: int) -> tuple[str | int | None, str]:
        """
        运行一次启动前的内存检查 check_headroom
        参数：mem_max (int) 内存上限，字节
        返回：tuple[str | int | None, str] 检查退出时 SystemExit 的 code（放行时为 None），以及写到标准错误的文字
        """
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr), mock.patch.object(
            limited_run.subprocess, "run", return_value=mock.Mock(stdout="")
        ):
            try:
                limited_run.check_headroom(mem_max)
            except SystemExit as caught:
                return caught.code, stderr.getvalue()
        return None, stderr.getvalue()

    def test_refusal_names_both(self) -> None:
        """容器放得下、earlyoom 余量放不下时以 76 拒绝，消息写出两个余量和 earlyoom 的杀进程线；放得下时放行"""
        self.process(42, "earlyoom", "-m", "20")
        code, message = self.check(7 * GIB)
        self.assertEqual(code, limited_run.EXIT_NO_HEADROOM)
        self.assertEqual(limited_run.EXIT_NO_HEADROOM, 76)
        early = limited_run.mib((8 << 20) * 1024 - int((12 << 20) * 0.2) * 1024)
        for text in (
            f"需要 7168 MiB，只剩 {early} MiB",
            "低于总内存的 20% 就杀进程",
            f"还能用 {early} MiB",
            "容器余量 10240 MiB",
        ):
            self.assertIn(text, message)
        self.assertEqual(self.check(5 * GIB), (None, ""))

    def test_refusal_without_earlyoom(self) -> None:
        """earlyoom 没在运行时照旧只按容器余量判断，消息里没有 earlyoom 那一行"""
        self.assertEqual(self.check(7 * GIB), (None, ""))
        code, message = self.check(11 * GIB)
        self.assertEqual(code, limited_run.EXIT_NO_HEADROOM)
        self.assertIn("只剩 10240 MiB", message)
        self.assertNotIn("earlyoom", message)


if __name__ == "__main__":
    unittest.main()
