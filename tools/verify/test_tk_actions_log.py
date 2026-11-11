#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
测试 tk.act 写进 actions.log 的行
不启动游戏

用法（在 erArk checkout 根目录）：
    python3 -m unittest tools.verify.test_tk_actions_log
"""

import contextlib
import io
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from tools.verify import tk


class TkActionsLog(unittest.TestCase):
    """检查 tk.act 写进 actions.log 的行。等待用的时钟、读探针和截图都换成假的。"""

    def test_key_with_newline(self) -> None:
        """描述含换行的动作（如 type 加返回值 "\\n0"）在 actions.log 里只占一行。行里的这个换行是反斜杠加 n 两个字符。"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        out = pathlib.Path(tmpdir.name)
        probe = {"awaiting": ["\n0", "返回"], "buttons": {}, "ts": 0}
        clock = [0.0]

        def sleep(seconds: float) -> None:
            """
            只把假时钟推进 seconds 秒
            参数：seconds (float) 要推进的秒数
            """
            clock[0] += seconds

        frames = iter(["001-type-_0.png", "002-advance.png"])
        fake_time = mock.Mock(
            monotonic=lambda: clock[0], sleep=sleep, strftime=time.strftime
        )
        with (
            mock.patch.object(tk, "time", fake_time),
            mock.patch.object(tk, "read_probe", return_value=probe),
            mock.patch.object(
                tk, "shot", side_effect=lambda state, label: out / next(frames)
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tk.act({"out": str(out)}, "type \n0", "type-\n0", probe)
            tk.act({"out": str(out)}, "advance", "advance", probe)
        lines = (out / "actions.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [line.split("\t")[1:] for line in lines],
            [["type \\n0", "001-type-_0.png"], ["advance", "002-advance.png"]],
        )


if __name__ == "__main__":
    unittest.main()
