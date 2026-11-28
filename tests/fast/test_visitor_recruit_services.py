"""
招募与访客服务测试
==================
- 招募服务（recruit_service）：覆盖招募条件、入职与满员拒绝、候选筛选、结算、效率与修复。
- 访客服务（visitor_service）：覆盖客房排序与空房、抵达与无房、邀请、离开、去留与将离查询。
- Tk 回调（tk_ui.callbacks）：保留启动登记回调，验证招募入职的 WaitDraw 提示与成就通知。
- 模块边界：验证两个面板文件不绑定 MOVED 中的服务函数名。
"""

import ast
import datetime
import os
from pathlib import Path
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Design import basement, game_time, instuct_judege
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, diplomacy, facility
from Script.Modules.domains import flags, npc_template, recruit, roster, visitor
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.gameplay_resolution import recruit_service, visitor_service
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase

_ = get_text._
""" 文本翻译函数 """
unlocked_text = achievement_service.unlocked_text
""" achievement_service.unlocked_text 的别名，用于构造预期成就获得提示文本 """
ROOT = Path(__file__).resolve().parents[2]
""" 仓库根目录路径 """
MOVED = {
    "Script/UI/Panel/recruit_panel.py": (
        "repair_recruit_lines",
        "can_recruit",
        "recruit_new_chara",
        "find_recruitable_npc",
        "update_recruit",
        "calculate_recruit_line_efficiency",
    ),
    "Script/UI/Panel/invite_visitor_panel.py": (
        "get_empty_guest_room_id",
        "sort_guest_room_key",
        "update_invite_visitor",
        "visitor_to_operator",
        "settle_visitor_arrivals",
        "visitor_leave",
        "settle_visitor_arrivals_and_departures",
        "judge_visitor_if_leave",
        "get_today_departing_visitors",
    ),
}
""" 两个面板文件及其不应绑定的服务函数名映射 """
GUEST_ROOMS = sorted(
    cid for cid in game_config.config_facility_open if 2000 < cid < 2100
)
""" 配置中编号 2001 至 2099 的客房设施编号有序列表 """
RECRUIT_ID = 101
""" 测试用招募成就编号（Achievement.csv 编号 101） """
VISITOR_ID = 111
""" 测试用访客成就编号（Achievement.csv 编号 111） """


def source_tree(path: str) -> ast.Module:
    """读取仓库相对路径对应源码文件并解析为语法树模块。"""
    return ast.parse((ROOT / path).read_text(encoding="utf-8"))


def bound_names(path: str) -> set[str]:
    """收集源码文件所有作用域中函数、类、导入别名与赋值目标绑定的名称集合。"""
    bound: set[str] = set()
    for node in ast.walk(source_tree(path)):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
    return bound


def full_text() -> str:
    """返回经翻译的宿舍满员无法招募提示文本。"""
    return _("\n\n   ※ 空余宿舍不足，无法招募 ※\n\n")


def hired_text(name: str) -> str:
    """返回指定角色名经翻译格式化后的招募成功提示文本。"""
    return _("\n\n   ※ 成功招募了{0} ※\n\n").format(name)


def arrived_text(name: str) -> str:
    """返回指定角色名经翻译格式化后的临时访客抵达提示文本。"""
    return _("\n ○【{0}】作为临时访客抵达了罗德岛\n").format(name)


class ServiceCase(FastTestCase):
    """招募与访客服务测试基类，准备测试角色、工作集缓冲区及提示与成就记录桩。"""

    def setUp(self) -> None:
        """创建博士与五名非女儿测试角色，开启工作集缓冲区，替换 ui_hooks._notices 并打桩成就结算函数。"""
        super().setUp()
        kernel_data.written(warehouse.start, {})
        self.world.chara(0, "博士")
        self.ids = sorted(
            cid
            for cid, tem in npc_template.table().items()
            if cid and tem.Mother_id == 0 and tem.AdvNpc < 9000
        )[:5]
        for index, cid in enumerate(self.ids):
            self.world.chara(cid, f"角色{index}")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notice])
        )
        self.settle = self.enterContext(
            mock.patch.object(
                achievement_service, "settle_by_type", return_value=[]
            )
        )

    def notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """将一次提示回调收到的文本与显示参数元组追加到记录列表。"""
        self.notices.append((text, wait, style, use_text_width))

    def candidate(self, index: int) -> int:
        """将指定下标的测试角色从在编名册移除并返回其角色编号。"""
        cid = self.ids[index]
        roster.discard(cid)
        return cid


class RecruitServiceTest(ServiceCase):
    """招募服务（recruit_service）各函数的行为与提示测试。"""

    def test_can_recruit_needs_pending_and_room(self) -> None:
        """断言无待确认返回 False、有待确认返回 True、宿舍上限为 0 返回 False 并发出满员金色等待提示。"""
        self.assertFalse(recruit_service.can_recruit())
        recruit.set_pending({self.candidate(1)})
        self.assertTrue(recruit_service.can_recruit())
        with mock.patch.object(facility, "people_max", return_value=0):
            self.assertFalse(recruit_service.can_recruit())
        self.assertEqual(
            self.notices, [(full_text(), True, "gold_enrod", True)]
        )

    def test_recruit_new_chara_hires_pending(self) -> None:
        """
        断言有待确认时返回 True、角色入编、待确认清空，
        依次发出招募成功提示与成就 101 金色等待提示，并以招募类型调用成就结算。
        """
        cid = self.candidate(1)
        recruit.set_pending({cid})
        self.settle.return_value = [RECRUIT_ID]
        self.assertTrue(recruit_service.recruit_new_chara())
        self.assertTrue(roster.has(cid))
        self.assertEqual(recruit.pending(), set())
        self.assertEqual(
            self.notices,
            [
                (hired_text("角色1"), True, "gold_enrod", True),
                (unlocked_text(RECRUIT_ID), True, "gold_enrod", False),
            ],
        )
        self.settle.assert_called_once_with(_("招募"), 0)

    def test_recruit_new_chara_refuses_full_dorms(self) -> None:
        """断言宿舍上限为 0 时返回 False、保留待确认且不入编、发出满员提示且不调用成就结算。"""
        cid = self.candidate(1)
        recruit.set_pending({cid})
        with mock.patch.object(facility, "people_max", return_value=0):
            self.assertFalse(recruit_service.recruit_new_chara())
        self.assertEqual(recruit.pending(), {cid})
        self.assertFalse(roster.has(cid))
        self.assertEqual(
            self.notices, [(full_text(), True, "gold_enrod", True)]
        )
        self.settle.assert_not_called()

    def test_find_recruitable_npc_skips_taken_characters(self) -> None:
        """断言候选列表跳过待确认角色、现役访客与在任外交官，只返回空闲候选角色。"""
        free, waiting, guest, envoy = (self.candidate(i) for i in (1, 2, 3, 4))
        recruit.set_pending({waiting})
        flags.set(guest, vistor=1)
        diplomacy.set_post(min(game_config.config_nation), diplomat=envoy)
        self.assertEqual(recruit_service.find_recruitable_npc(), [free])

    def test_update_recruit_fills_pending_and_stops_invite(self) -> None:
        """断言满进度线抽中唯一候选并清零进度、保留未满线进度、清空同目标邀请并发出含停邀句的金色提示。"""
        cid = self.candidate(1)
        recruit.open_lines([0, 1])
        recruit.set_line(0, progress=100, strategy=1)
        recruit.set_line(1, progress=40, strategy=1)
        visitor.set_invite(cid, 20)
        recruit_service.update_recruit()
        self.assertEqual(recruit.pending(), {cid})
        self.assertEqual(recruit.lines()[0], {**recruit.IDLE, "strategy": 1})
        self.assertEqual(recruit.lines()[1]["progress"], 40)
        self.assertEqual(visitor.invite(), (0, 0))
        text = _("\n\n   ※ 招募到了新的干员，请前往博士办公室确认 ※\n\n") + _(
            "   ※ 招募到的新干员是正在邀请的访客，已自动停止邀请 ※\n\n"
        )
        self.assertEqual(self.notices, [(text, True, "gold_enrod", True)])

    def test_update_recruit_stops_line_without_candidates(self) -> None:
        """断言无候选时满进度线策略设为 11 且进度清零、待确认保持为空并发出 warning 样式失败提示。"""
        recruit.open_lines([0])
        recruit.set_line(0, progress=100, strategy=1)
        recruit_service.update_recruit()
        self.assertEqual(recruit.lines()[0], {**recruit.IDLE, "strategy": 11})
        self.assertEqual(recruit.pending(), set())
        text = _(
            "\n\n   ※ 当前招募策略无可招募npc，招募失败，已自动停止招募，请调整招募策略 ※\n\n"
        )
        self.assertEqual(self.notices, [(text, True, "warning", True)])

    def test_line_efficiency(self) -> None:
        """断言缺失线与策略 11 返回对应说明与 0.0，空缺主专员线效率等于策略 1 系数乘以设施 7 效率。"""
        recruit.open_lines([0, 1])
        recruit.set_line(1, strategy=11)
        self.assertEqual(
            recruit_service.calculate_recruit_line_efficiency(5),
            (_("无此招募线"), 0.0),
        )
        self.assertEqual(
            recruit_service.calculate_recruit_line_efficiency(1),
            (_("已停止招募"), 0.0),
        )
        recruit.set_line(0, strategy=1)
        adjust = game_config.config_recruitment_strategy[1].adjust
        _text, value = recruit_service.calculate_recruit_line_efficiency(0)
        self.assertAlmostEqual(
            value, adjust * basement.calc_facility_efficiency(7)
        )

    def test_repair_recruit_lines(self) -> None:
        """断言修复移除待确认中的编号 0 与不存在角色，清零策略 11 线进度并保留策略 1 线进度。"""
        kept = self.ids[1]
        recruit.set_pending({0, kept, 999999})
        recruit.open_lines([0, 1])
        recruit.set_line(0, progress=30, strategy=11)
        recruit.set_line(1, progress=30, strategy=1)
        recruit_service.repair_recruit_lines()
        self.assertEqual(recruit.pending(), {kept})
        progress = [line["progress"] for line in recruit.lines().values()]
        self.assertEqual(progress, [0, 30])


class VisitorServiceTest(ServiceCase):
    """访客服务（visitor_service）各函数的行为与提示测试。"""

    def close_rooms(self) -> None:
        """将 GUEST_ROOMS 中的全部客房设施设为未开放。"""
        for room in GUEST_ROOMS:
            facility.set_open(room, False)

    def leaving(self, cid: int, hours: int) -> None:
        """将指定角色登记为访客并设定相对当前时刻偏移指定小时的离开时刻。"""
        visitor.arrive(cid, game_time.now() + datetime.timedelta(hours=hours))

    def test_sort_guest_room_key(self) -> None:
        """断言带路径与纯名称客房按数字返回 10 与 3，非数字后缀与无客房字样均返回 999。"""
        keys = [
            visitor_service.sort_guest_room_key(path)
            for path in ("访客" + os.sep + "客房10", "客房3", "客房x", "大厅")
        ]
        self.assertEqual(keys, [10, 3, 999, 999])

    def test_get_empty_guest_room_id(self) -> None:
        """断言开放两间客房先返回首间、首间被占用后返回次间、全部关闭时返回 False。"""
        first, second = GUEST_ROOMS[:2]
        for room in (first, second):
            facility.set_open(room, True)
        self.assertEqual(visitor_service.get_empty_guest_room_id(), first)
        guest = self.candidate(1)
        self.leaving(guest, 24)
        room_name = game_config.config_facility_open[first].name
        chara_life.dormitory.set(guest, room_name)
        self.assertEqual(visitor_service.get_empty_guest_room_id(), second)
        self.close_rooms()
        self.assertFalse(visitor_service.get_empty_guest_room_id())

    def test_settle_visitor_arrivals_takes_given_visitor(self) -> None:
        """断言接待指定访客返回 1、角色成为访客，依次发出抵达提示与成就 111 金色等待提示，并以访客类型调用成就结算。"""
        cid = self.candidate(1)
        self.settle.return_value = [VISITOR_ID]
        self.assertEqual(visitor_service.settle_visitor_arrivals(cid), 1)
        self.assertTrue(visitor.is_visitor(cid))
        self.assertEqual(
            self.notices,
            [
                (arrived_text("角色1"), True, "gold_enrod", True),
                (unlocked_text(VISITOR_ID), True, "gold_enrod", False),
            ],
        )
        self.settle.assert_called_once_with(_("访客"), 0)

    def test_settle_visitor_arrivals_without_room(self) -> None:
        """断言无开放客房时返回 0、角色未成为访客、发出无空闲客房金色提示且不调用成就结算。"""
        cid = self.candidate(1)
        self.close_rooms()
        self.assertEqual(visitor_service.settle_visitor_arrivals(cid), 0)
        self.assertFalse(visitor.is_visitor(cid))
        text = _("\n ●由于没有空闲的客房，罗德岛没有接待到一名新抵达的访客\n")
        self.assertEqual(self.notices, [(text, True, "gold_enrod", True)])
        self.settle.assert_not_called()

    def test_update_invite_visitor(self) -> None:
        """断言邀请进度 50 时保持邀请且不抵达，进度 100 时目标成为访客且邀请清空。"""
        cid = self.candidate(1)
        visitor.set_invite(cid, 50)
        visitor_service.update_invite_visitor()
        self.assertEqual(visitor.invite(), (cid, 50))
        self.assertFalse(visitor.is_visitor(cid))
        visitor.set_invite(cid, 100)
        visitor_service.update_invite_visitor()
        self.assertEqual(visitor.invite(), (0, 0))
        self.assertTrue(visitor.is_visitor(cid))

    def test_visitor_leave(self) -> None:
        """断言离开清理后角色非访客、不在在编名册、vistor 标志为 2 且位置为 ["0", "0"]。"""
        cid = self.ids[1]
        self.leaving(cid, 24)
        visitor_service.visitor_leave(cid)
        self.assertFalse(visitor.is_visitor(cid))
        self.assertFalse(roster.has(cid))
        self.assertEqual(flags.get(cid, "vistor"), 2)
        self.assertEqual(activity.position(cid), ["0", "0"])

    def test_judge_visitor_if_leave(self) -> None:
        """断言固定随机数下高概率访客转正在编、低概率访客离队、两者非访客且标志为 2 并各自发出对应提示。"""
        stay, leave = self.ids[1], self.ids[2]
        self.leaving(stay, -1)
        self.leaving(leave, -1)
        self.enterContext(mock.patch("random.random", return_value=0.5))
        for cid, probability in ((stay, 0.9), (leave, 0.1)):
            with mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                return_value=(0, 0, probability),
            ):
                visitor_service.judge_visitor_if_leave(cid)
            self.assertFalse(visitor.is_visitor(cid))
            self.assertEqual(flags.get(cid, "vistor"), 2)
        self.assertTrue(roster.has(stay))
        self.assertFalse(roster.has(leave))
        texts = [text for text, *_options in self.notices]
        self.assertEqual(len(texts), 2)
        self.assertIn(
            _("\n ○【{0}】决定放弃离开，留在罗德岛成为一名正式干员\n").format(
                "角色1"
            ),
            texts[0],
        )
        self.assertIn(
            _("\n ●【{0}】打包好行李，离开了罗德岛\n").format("角色2"), texts[1]
        )

    def test_get_today_departing_visitors(self) -> None:
        """断言次日零点前到期访客在留下概率 0.3 时列入结果、0.7 时返回空列表，远期访客不列入。"""
        soon, later = self.ids[1], self.ids[2]
        self.leaving(soon, 1)
        self.leaving(later, 72)
        for probability, expected in ((0.3, [soon]), (0.7, [])):
            with mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                return_value=(0, 0, probability),
            ):
                departing = visitor_service.get_today_departing_visitors()
            self.assertEqual(departing, expected)


class TkCallbackTest(FastTestCase):
    """验证启动阶段登记的 Tk 回调以 WaitDraw 绘制招募入职提示与新达成成就提示。"""

    def test_tk_draws_notices_and_achievements(self) -> None:
        """
        断言保留启动登记回调运行招募入职时，WaitDraw 依次以配置文本宽度绘出金色入职提示，
        再以宽度 0 绘出成就 101 金色提示。
        """
        kernel_data.written(warehouse.start, {})
        self.world.chara(0, "博士")
        cid = min(
            cid
            for cid, tem in npc_template.table().items()
            if cid and tem.Mother_id == 0 and tem.AdvNpc < 9000
        )
        self.world.chara(cid, "新干员")
        self.enterContext(working.based_on(core.state()))
        roster.discard(cid)
        recruit.set_pending({cid})
        waited = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )
        self.enterContext(
            mock.patch.object(
                achievement_service, "settle_by_type", return_value=[RECRUIT_ID]
            )
        )
        recruit_service.recruit_new_chara()
        width = normal_config.config_normal.text_width
        self.assertEqual(
            [
                (now.width, now.style, now.text)
                for (now,), _kw in waited.call_args_list
            ],
            [
                (width, "gold_enrod", hired_text("新干员")),
                (0, "gold_enrod", unlocked_text(RECRUIT_ID)),
            ],
        )


class BoundaryTest(FastTestCase):
    """验证两个界面面板文件不绑定后端服务函数名的边界测试。"""

    def test_panels_bind_no_moved_function(self) -> None:
        """断言两个面板文件在任意作用域均不绑定 MOVED 中对应的服务函数名。"""
        for path, names in MOVED.items():
            self.assertEqual(bound_names(path) & set(names), set(), path)
