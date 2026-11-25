"""
源石技艺面板菜单规则服务与面板绘制委托的快速测试。
覆盖各能力系菜单可见性、调试模式与新周目跨年入口、素质名拼接与视觉系理智消耗、
能力系详情行组装，以及面板主菜单标签、未解锁置灰与条件文案格式化。
"""

import datetime
from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, modes
from Script.Modules.gameplay_resolution import originium_arts_panel_service
from Script.Modules.gameplay_resolution import originium_arts_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw, view
from Script.UI.Panel import originium_arts
from tests import world
from tests.fast.base import FastTestCase

panel_svc = originium_arts_panel_service
"""源石技艺面板菜单规则服务模块的简短别名。"""

ART_TALENT_IDS: tuple[int, ...] = (304, 305, 306, 307, 308, 309, 310, 311)
ART_TALENT_IDS += (312, 316, 317, 318, 331, 332, 333, 334)
"""测试中统一重置的全部源石技艺相关素质编号元组。"""


def talent_name(talent_id: int) -> str:
    """
    按素质编号读取配置表中的素质名称。
    Keyword arguments:
    talent_id -- int，素质配置编号
    Return arguments:
    str -- 配置表中的素质名称
    """
    return game_config.config_talent[talent_id].name


class ArtMenuCase(FastTestCase):
    """源石技艺面板菜单测试基类，初始化玩家工作集、清空源石技艺素质并关闭调试模式。"""

    def setUp(self) -> None:
        """重置测试世界，创建玩家并进入工作集，清空源石技艺素质并关闭调试模式。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        for talent_id in ART_TALENT_IDS:
            abilities.talent(0)[talent_id] = 0
        modes.set_debug(False)

    def grant(self, *talent_ids: int) -> None:
        """
        为玩家批量授予指定的源石技艺素质。
        Keyword arguments:
        talent_ids -- int，要设为已持有的素质编号序列
        """
        for talent_id in talent_ids:
            abilities.talent(0)[talent_id] = 1


class ArtMenuServiceTest(ArtMenuCase):
    """源石技艺面板菜单规则服务的单元测试。"""

    def test_each_talent_family_opens_its_entry(self) -> None:
        """验证无素质以及各能力系素质分别开放对应的主菜单条目，且单独持有 317 不开放时间系入口。"""
        cases = (
            ((), None),
            ((316,), 2),
            ((317,), None),
            ((331,), 3),
            ((334,), 3),
            ((304,), 5),
            ((306,), 5),
            ((307,), 6),
            ((309,), 6),
            ((310,), 7),
            ((312,), 7),
        )
        for talent_ids, key in cases:
            with self.subTest(talent_ids=talent_ids):
                for talent_id in ART_TALENT_IDS:
                    abilities.talent(0)[talent_id] = 0
                self.grant(*talent_ids)
                keys = [e.key for e in panel_svc.menu_entries()]
                self.assertEqual(keys, [1, *([key] if key else []), 11, 12])

    def test_debug_mode_adds_self_reinforcement(self) -> None:
        """验证开启调试模式时主菜单额外显示自我强化条目 4。"""
        modes.set_debug(True)
        keys = [e.key for e in panel_svc.menu_entries()]
        self.assertEqual(keys, [1, 4, 11, 12])

    def test_new_round_entry_needs_second_year_or_debug(self) -> None:
        """验证新周目条目 12 在进入游戏第二年前一分钟关闭调试时隐藏，开启调试或到达第二年首日零点时显示。"""
        threshold = game_time.to_game_time(datetime.datetime(2020, 3, 1))
        before = threshold - datetime.timedelta(minutes=1)
        cases = (
            (before, False, [1, 11]),
            (before, True, [1, 4, 11, 12]),
            (threshold, False, [1, 11, 12]),
        )
        for when, debug, keys in cases:
            with self.subTest(when=str(when), debug=debug):
                world.set_clock(when)
                modes.set_debug(debug)
                entries = panel_svc.menu_entries()
                self.assertEqual([e.key for e in entries], keys)

    def test_group_names_join_owned_talents_and_price_visual(self) -> None:
        """验证各能力系已持有素质名拼接规则（含首项未持有时的前导分隔符）及视觉系每小时理智消耗。"""
        self.grant(316, 318, 305, 307, 308, 309)
        entries = {e.key: e for e in panel_svc.menu_entries()}
        self.assertEqual(
            entries[2],
            panel_svc.ArtMenuEntry(
                2, f"{talent_name(316)} + {talent_name(318)}"
            ),
        )
        self.assertEqual(
            entries[5], panel_svc.ArtMenuEntry(5, f" + {talent_name(305)}")
        )
        visual = " + ".join(talent_name(t) for t in (307, 308, 309))
        self.assertEqual(entries[6], panel_svc.ArtMenuEntry(6, visual, 15))

    def test_group_rows_follow_family_order_and_unlock_state(self) -> None:
        """验证各能力系详情行保持配置顺序、正确反映解锁状态并携带配置名称与说明。"""
        self.grant(305, 317, 309)
        expected = {
            2: [(316, False), (317, True), (318, False)],
            5: [(304, False), (305, True), (306, False)],
            6: [(307, False), (308, False), (309, True)],
        }
        for key, pairs in expected.items():
            with self.subTest(key=key):
                rows = panel_svc.group_rows(key)
                self.assertEqual(
                    [(r.talent_id, r.unlocked) for r in rows], pairs
                )
        row = panel_svc.group_rows(5)[1]
        data = game_config.config_talent[305]
        self.assertEqual((row.name, row.info), (data.name, data.info))


class ArtMenuPanelTest(ArtMenuCase):
    """源石技艺主面板绘制、菜单标签、详情页样式与条件文案格式化的测试。"""

    def test_main_menu_labels_and_back(self) -> None:
        """验证主面板按规则绘制全部九个菜单按钮标签与返回码，选择返回后切回场景面板。"""
        self.grant(316, 318, 331, 305, 307, 309, 310)
        modes.set_debug(True)
        type_id = next(iter(game_config.config_hypnosis_type))
        svc.set_hypnosis_type(type_id)
        type_name = game_config.config_hypnosis_type[type_id].name
        view.now_panel_id = constant.Panel.ORIGINIUM_ARTS
        buttons: list[tuple[str, str]] = []
        with (
            mock.patch.object(
                draw.LeftButton,
                "draw",
                lambda inst: buttons.append((inst.text, inst.return_text)),
            ),
            mock.patch.object(
                originium_arts.flow_handle, "askfor_all", return_value="返回"
            ),
        ):
            originium_arts.Originium_Arts_Panel(80).draw()
        n = talent_name
        self.assertEqual(
            buttons,
            [
                ("[001]消除负面刻印", "1"),
                (f"[002]时间系能力：{n(316)} + {n(318)}", "2"),
                (f"[003]催眠系能力：当前默认催眠类型：{type_name}", "3"),
                ("[004]自我强化(未实装)", "4"),
                (f"[005]激素系能力： + {n(305)}", "5"),
                (f"[006]视觉系能力：{n(307)} + {n(309)}(10理智/h)", "6"),
                ("[007]触觉系能力(未实装)", "7"),
                ("[011]能力获得与升级", "11"),
                ("[012]Re:败者食尘", "12"),
            ],
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_arts_show_greys_locked_talents(self) -> None:
        """验证能力系详情页输出标题与各素质行，并对未解锁素质应用深灰样式。"""
        self.grant(305)
        shown: list[tuple[str, str]] = []
        with (
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                lambda inst: shown.append((inst.text, inst.style)),
            ),
            mock.patch.object(draw.LineDraw, "draw"),
            mock.patch.object(
                originium_arts.flow_handle, "askfor_all", return_value="返回"
            ),
        ):
            originium_arts.Originium_Arts_Panel(80).arts_show(5)
        cfg = game_config.config_talent
        self.assertEqual(
            shown[:4],
            [
                ("\n激素系能力（不消耗理智）：\n", "standard"),
                (f"  {cfg[304].name}(未解锁)：{cfg[304].info}\n", "deep_gray"),
                (f"  {cfg[305].name}：{cfg[305].info}\n", "standard"),
                (f"  {cfg[306].name}(未解锁)：{cfg[306].info}\n", "deep_gray"),
            ],
        )

    def test_condition_text_by_kind(self) -> None:
        """验证按条件类型格式化二参数、四参数及催眠回退模板的解锁条件文案。"""
        panel = originium_arts.Originium_Arts_Panel(80)
        cases = (
            (
                svc.ArtConditionProgress("child_count", 3, 1),
                "：需要生育孩子数量≥3（当前1）",
            ),
            (
                svc.ArtConditionProgress(
                    "max_favorability_trust", 10, 2, 20, 4
                ),
                "：需要单干员最高好感度≥10（当前2），最高信赖度≥20（当前4）",
            ),
            (
                svc.ArtConditionProgress("hypnosis_exp_degree", 5, 1, 50, 7),
                "：需要博士催眠经验≥5（当前1），需要全干员总催眠深度≥50%（当前7%）",
            ),
        )
        for condition, text in cases:
            with self.subTest(kind=condition.kind):
                self.assertEqual(panel._format_condition_text(condition), text)
