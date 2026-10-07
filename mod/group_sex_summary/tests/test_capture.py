# -*- coding: UTF-8 -*-
"""
capture.py 测试（假绘制类）：无窗口直通、最内层窗口生效、嵌套隔离、draw_live 绕过窗口、回放、重复安装
运行：python3 mod/group_sex_summary/tests/test_capture.py（不需要游戏环境）
"""
import sys

from _harness import check, finish, load_mod_package

load_mod_package()
from _erark_mod_group_sex_summary import capture  # noqa: E402

LOG = []


class FakeDraw:
    def __init__(self):
        self.text = ""
        self.style = "standard"
        self.width = 0
        self.tooltip = ""

    def draw(self):
        LOG.append(("Fake", self.text, self.style))
        return "drawn"


class FakeWait(FakeDraw):
    def draw(self):
        LOG.append(("Wait", self.text, self.style))


def make(cls, text, style="standard", width=10, tooltip=""):
    obj = cls()
    obj.text, obj.style, obj.width, obj.tooltip = text, style, width, tooltip
    return obj


original_fake = FakeDraw.draw
capture.install_draw_wrappers((FakeDraw, FakeWait))
wrapped_fake = FakeDraw.draw
check("安装后 draw 被包装", wrapped_fake is not original_fake)
capture.install_draw_wrappers((FakeDraw, FakeWait))
check("重复安装不再套一层", FakeDraw.draw is wrapped_fake)

# 无窗口：直通原 draw，返回值不变
check("无窗口直通并返回原值", make(FakeDraw, "a").draw() == "drawn" and LOG == [("Fake", "a", "standard")], LOG)
LOG.clear()

# 窗口：只记录值，不绘制
box = []
with capture.capture_into(box):
    result = make(FakeDraw, "b", "red", 7, "tip").draw()
    make(FakeWait, "w").draw()
check("窗口内不绘制", LOG == [], LOG)
check("窗口内返回 None", result is None)
check("记录值元组（含子类类型）", box == [(FakeDraw, "b", "red", 7, "tip"), (FakeWait, "w", "standard", 10, "")], box)

# 嵌套：内层只进内层，外层恢复后继续进外层
outer, inner = [], []
with capture.capture_into(outer):
    make(FakeDraw, "外1").draw()
    with capture.capture_into(inner):
        make(FakeDraw, "内2").draw()
    make(FakeDraw, "外3").draw()
check("嵌套：外层只收外层的", [item[1] for item in outer] == ["外1", "外3"], outer)
check("嵌套：内层只收内层的", [item[1] for item in inner] == ["内2"], inner)
check("嵌套：全程没有绘制", LOG == [])

# 异常也会关窗口
try:
    with capture.capture_into([]):
        raise ValueError
except ValueError:
    pass
make(FakeDraw, "after").draw()
check("异常后窗口已关闭", LOG == [("Fake", "after", "standard")], LOG)
LOG.clear()

# draw_live：即使在窗口内也真正画出，不进任何窗口
outer = []
with capture.capture_into(outer):
    capture.draw_live([(FakeDraw, "live", "gold", 5, ""), (FakeWait, "lw", "standard", 5, "")])
check("draw_live 绕过窗口", LOG == [("Fake", "live", "gold"), ("Wait", "lw", "standard")] and outer == [], (LOG, outer))
LOG.clear()

# replay：无窗口时按顺序新建对象绘制
capture.replay([(FakeDraw, "r1", "standard", 1, ""), (FakeWait, "r2", "red", 1, "")])
check("replay 按顺序绘制", LOG == [("Fake", "r1", "standard"), ("Wait", "r2", "red")], LOG)
LOG.clear()

check("不 import 游戏", "Script.Core.cache_control" not in sys.modules)
finish()
