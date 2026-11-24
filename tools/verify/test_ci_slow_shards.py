"""
测试 tools/ci_slow_shards.py 的分片行为与 daily-tests.yml 的作业配置。
本测试不启动游戏，需在仓库根目录执行。

用法：
    python3 -m unittest tools.verify.test_ci_slow_shards
"""

import contextlib
import importlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools import ci_slow_shards

WORKFLOW = ci_slow_shards.ROOT / ".github" / "workflows" / "daily-tests.yml"
""" 每日测试工作流文件 .github/workflows/daily-tests.yml 的路径。 """

SUITE_CONDITION = (
    "${{ github.event_name != 'workflow_dispatch' || inputs.test_path == '' }}"
)
""" 四个完整测试套件作业共用的 if 条件表达式。 """


def run_main(argv: list[str], root: pathlib.Path) -> tuple[int, list[str]]:
    """
    捕获标准输出与标准错误后调用 ci_slow_shards.main。

    参数：
        argv (list[str]): 传给 main 的命令行参数列表
        root (pathlib.Path): 传给 main 的仓库根目录路径
    返回：
        tuple[int, list[str]]: 退出码与按行切分的标准输出列表
    """
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(
        io.StringIO()
    ):
        code = ci_slow_shards.main(argv, root)
    return code, out.getvalue().splitlines()


def live_shards(total: int) -> list[list[str]]:
    """
    对当前仓库依次运行各分片并返回输出的文件列表。

    参数：
        total (int): 分片总数
    返回：
        list[list[str]]: 按分片编号排列的文件路径列表
    """
    return [
        run_main(
            ["--shard", str(shard), "--total", str(total)], ci_slow_shards.ROOT
        )[1]
        for shard in range(total)
    ]


class SyntheticTree(unittest.TestCase):
    """使用临时目录构造测试文件树，验证分片分配与错误处理。"""

    def setUp(self) -> None:
        """创建临时根目录及其下的 tests/slow 子目录。"""
        self.root = pathlib.Path(
            self.enterContext(tempfile.TemporaryDirectory())
        )
        (self.root / "tests" / "slow").mkdir(parents=True)

    def write(self, name: str, tests: int) -> None:
        """
        在临时 tests/slow 目录下写入包含指定数量测试函数的 Python 文件。

        参数：
            name (str): 文件名
            tests (int): 要写入的 test_ 函数数量
        返回：
            None: 无返回值
        """
        body = "".join(
            f"def test_{index}():\n    pass\n" for index in range(tests)
        )
        (self.root / "tests" / "slow" / name).write_text(body, encoding="utf-8")

    def shards(self, total: int) -> list[list[str]]:
        """
        对临时目录依次运行各分片并返回输出的文件列表。

        参数：
            total (int): 分片总数
        返回：
            list[list[str]]: 按分片编号排列的文件路径列表
        """
        return [
            run_main(["--shard", str(shard), "--total", str(total)], self.root)[
                1
            ]
            for shard in range(total)
        ]

    def test_heavy_files_land_on_different_shards(self) -> None:
        """检查四个重文件分散到四个分片且负载均衡，同时排除教育文件与非 test_ 文件。"""
        for index, tests in enumerate([12, 11, 10, 9]):
            self.write(f"test_heavy_{index}.py", tests)
        for index in range(8):
            self.write(f"test_light_{index}.py", 1)
        self.write("test_education_suite.py", 50)
        (self.root / "tests" / "slow" / "base.py").write_text(
            "def test_helper():\n    pass\n", encoding="utf-8"
        )
        shards = self.shards(4)
        heavy_holders = {
            shard
            for shard, files in enumerate(shards)
            for name in files
            if "heavy" in name
        }
        self.assertEqual(heavy_holders, {0, 1, 2, 3})
        listed = sorted(name for files in shards for name in files)
        expected = sorted(
            [f"tests/slow/test_heavy_{index}.py" for index in range(4)]
            + [f"tests/slow/test_light_{index}.py" for index in range(8)]
        )
        self.assertEqual(listed, expected)
        loads = [
            sum(ci_slow_shards.count_tests(self.root / name) for name in files)
            for files in shards
        ]
        self.assertLessEqual(max(loads) - min(loads), 1)

    def test_empty_shard_fails(self) -> None:
        """检查两文件分两片时各得一文件，以及请求空分片时返回状态码 1 且无输出。"""
        self.write("test_a.py", 2)
        self.write("test_b.py", 1)
        self.assertEqual(
            self.shards(2), [["tests/slow/test_a.py"], ["tests/slow/test_b.py"]]
        )
        code, lines = run_main(["--shard", "3", "--total", "4"], self.root)
        self.assertEqual((code, lines), (1, []))

    def test_bad_arguments_exit_2(self) -> None:
        """检查越界、非数字或缺失的命令行参数均以退出码 2 退出。"""
        self.write("test_a.py", 1)
        for argv in (
            ["--shard", "4", "--total", "4"],
            ["--shard", "-1", "--total", "4"],
            ["--shard", "0", "--total", "0"],
            ["--shard", "x"],
            ["--total", "4"],
        ):
            with self.subTest(argv=argv), self.assertRaises(
                SystemExit
            ) as caught:
                run_main(argv, self.root)
            self.assertEqual(caught.exception.code, 2)


class LiveSlowSuite(unittest.TestCase):
    """针对仓库真实 tests/slow 目录验证分片覆盖、均衡性与命令行输出。"""

    def test_shards_cover_slow_suite_once(self) -> None:
        """检查四个分片非空、不重不漏覆盖除教育套件外的慢速测试文件，且结果稳定。"""
        slow = ci_slow_shards.ROOT / "tests" / "slow"
        expected = sorted(
            f"tests/slow/{path.name}"
            for path in slow.glob("test_*.py")
            if path.name != "test_education_suite.py"
        )
        shards = live_shards(4)
        self.assertTrue(all(shards))
        listed = [name for files in shards for name in files]
        self.assertEqual(sorted(listed), expected)
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(live_shards(4), shards)

    def test_shard_loads_differ_by_at_most_heaviest_file(self) -> None:
        """检查四片测试函数总数之差不超过最重单个文件的测试函数数量。"""
        root = ci_slow_shards.ROOT
        loads = [
            sum(ci_slow_shards.count_tests(root / name) for name in files)
            for files in live_shards(4)
        ]
        heaviest = max(ci_slow_shards.slow_files(root).values())
        self.assertLessEqual(max(loads) - min(loads), heaviest)

    def test_command_line_prints_same_shard(self) -> None:
        """检查直接通过命令行运行脚本打印的 2 号分片与函数调用结果一致。"""
        result = subprocess.run(
            [
                sys.executable,
                "tools/ci_slow_shards.py",
                "--shard",
                "2",
                "--total",
                "4",
            ],
            cwd=ci_slow_shards.ROOT,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(result.stdout.splitlines(), live_shards(4)[2])


@unittest.skipUnless(importlib.util.find_spec("yaml"), "未安装 PyYAML")
class DailyTestsWorkflow(unittest.TestCase):
    """检查每日测试工作流文件的触发条件、分片矩阵与汇总作业配置。"""

    def setUp(self) -> None:
        """解析每日测试工作流 YAML，保存触发配置与作业定义。"""
        yaml = importlib.import_module("yaml")
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.triggers = doc[True]
        self.jobs = doc["jobs"]

    def test_pull_request_runs_when_marked_ready(self) -> None:
        """检查 pull_request 触发类型恰好为 opened、synchronize、reopened 与 ready_for_review。"""
        self.assertEqual(
            self.triggers["pull_request"]["types"],
            ["opened", "synchronize", "reopened", "ready_for_review"],
        )

    def test_suite_jobs_share_one_condition(self) -> None:
        """检查四个套件作业的 if 条件均等于 SUITE_CONDITION 且不含 draft。"""
        for name in ("typecheck", "fast-and-verify", "slow", "education"):
            with self.subTest(job=name):
                condition = self.jobs[name]["if"]
                self.assertEqual(condition, SUITE_CONDITION)
                self.assertNotIn("draft", condition)

    def test_slow_matrix_matches_shard_total(self) -> None:
        """检查 slow 作业关闭 fail-fast，且矩阵分片编号与 --total 4 一致。"""
        strategy = self.jobs["slow"]["strategy"]
        self.assertIs(strategy["fail-fast"], False)
        self.assertEqual(strategy["matrix"]["shard"], [0, 1, 2, 3])
        runs = "\n".join(
            step.get("run", "") for step in self.jobs["slow"]["steps"]
        )
        self.assertIn("tools/ci_slow_shards.py --shard", runs)
        self.assertIn("--total 4", runs)

    def test_targeted_runs_only_for_a_test_path(self) -> None:
        """检查 targeted 作业条件要求手动触发并传入非空 test_path。"""
        condition = self.jobs["targeted"]["if"]
        self.assertIn("github.event_name == 'workflow_dispatch'", condition)
        self.assertIn("inputs.test_path != ''", condition)

    def test_summary_job_waits_for_every_test_job(self) -> None:
        """检查汇总作业 tests 依赖四个测试作业并带 always() 条件。"""
        summary = self.jobs["tests"]
        self.assertEqual(
            summary["needs"],
            ["fast-and-verify", "slow", "education", "targeted"],
        )
        self.assertIn("always()", summary["if"])


if __name__ == "__main__":
    unittest.main()
