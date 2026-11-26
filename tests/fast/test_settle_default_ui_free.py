"""
Script.Settle.default 无界面测试
================================
本测试在单个独立子进程中放行 Script.Settle，并保留 Script.UI 等其余默认拦截项。
子进程导入 Script.Settle.default，在 working.based_on 上下文中运行七个结算函数，
并通过 ui_hooks.on_notice 记录提示后将结果写入 payload。子进程失败时，setUpClass
抛出 RuntimeError。测试类核对子进程未加载也未尝试导入受拦截模块，并校验七个函数的
提示与状态结果。
"""

from typing import Any, cast

from Script.Config import game_config
from Script.Core import get_text
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, run_ui_free

CHILD_RUN = """
import datetime
import random
from Script.Config import game_config, map_config
from Script.Core import constant, game_type
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, flags, hypnosis
from Script.Modules.domains import identity, inventory, needs, playthrough
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import plan_queue, ui_hooks, working
from Script.Settle import default
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, behave, place
from tests.world import DEFAULT_SCENE, STANDARD_OUTFIT, start_time

map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=cid))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, STANDARD_OUTFIT)
    kernel_data.put(inventory.replace_items, cid, attr_calculation.get_item_zero({}))
    kernel_data.set_needs(cid, hit_max=100, hit=100, mana_max=100, mana=100)
    place(cid, DEFAULT_SCENE)
aim(0, 1)
aim(1, 1)
core.reset_state(kernel_data.reprojected(core.state()))
random.seed(0)
notices = []


@ui_hooks.on_notice
def keep(text, *, wait, style, use_text_width):
    notices.append([text, wait, style, use_text_width])


def run(name, effect, cid=0):
    notices.clear()
    effect(cid, 1, game_type.CharacterStatusChange(), datetime.datetime(2025, 1, 1))
    payload[name] = list(notices)


with working.based_on(core.state()):
    playthrough.reset_difficulty_and_birth()
    warehouse.start({})
    run("weakness", default.handle_target_get_weeknesss_by_dr)
    payload["weakness_talent"] = abilities.talent(1)[402]
    before = [needs.of(1)["hit_max"], needs.of(1)["mana_max"]]
    run("exercise_alone", default.handle_add_hpmp_max, 1)
    payload["exercise_gain"] = [
        needs.of(1)["hit_max"] - before[0],
        needs.of(1)["mana_max"] - before[1],
    ]
    run("invite_without_target", default.handle_invite_visitor_add_adjust)
    apology = min(
        gid for gid, gift in game_config.config_gift_items.items() if gift.type == 2
    )
    behave(0, gift_id=apology)
    run("apology_gift", default.handle_give_gift_add_adjust)
    book = min(game_config.config_book)
    behave(0, book_id=book)
    run("read", default.handle_read_add_adjust)
    payload["book"] = book
    payload["read_progress"] = chara_life.read_book_progress(0)[book]
    needs.set(0, sanity=0)
    flags.set(1, unconscious_h=1)
    run("sanity_out", default.handle_hypnosis_one)
    payload["unconscious_h"] = flags.get(1, "unconscious_h")
    run("active_h_on", default.handle_target_hypnosis_active_h_switch_change)
    payload["active_h"] = hypnosis.get(1, "active_h")
    payload["planned_h"] = plan_queue.plan_has(0, constant.Behavior.H)
"""
"""在无界面子进程中初始化测试状态并运行七个 Script.Settle.default 结算函数的代码片段。"""


class SettleDefaultUiFreeTest(FastTestCase):
    """Script.Settle.default 的无界面子进程导入与运行测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """放行 Script.Settle 并在无界面子进程中执行 CHILD_RUN。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(
            CHILD_RUN, boot=True, blocked=BLOCKED - {"Script.Settle"}
        )
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_no_blocked_module_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何受拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_weakness_notice_uses_text_width(self) -> None:
        """
        断言 handle_target_get_weeknesss_by_dr 发出一则不等待、无样式且启用文本宽度的
        预期提示。同时断言角色 1 的天赋 402 为 1。
        """
        text = get_text._("\n{0}获得了【被博士持有把柄】\n").format("c1")
        self.assertEqual(self.payload["weakness"], [[text, False, None, True]])
        self.assertEqual(self.payload["weakness_talent"], 1)

    def test_exercise_alone_reports_gain_then_blank_line(self) -> None:
        """
        断言角色 1 独自执行 handle_add_hpmp_max 后依次发出两则提示。第一则含实测
        hit_max 与 mana_max 增量，参数为不等待、无样式且启用文本宽度。第二则为采用默认
        参数的换行符。
        """
        hp, mp = self.payload["exercise_gain"]
        text = get_text._("\n{0}的体力上限增加{1},气力上限增加{2}").format(
            "c1", str(hp), str(mp)
        )
        self.assertEqual(
            self.payload["exercise_alone"],
            [[text, False, None, True], ["\n", False, None, False]],
        )

    def test_invite_without_target_prompts_player(self) -> None:
        """
        断言未设邀请目标时，handle_invite_visitor_add_adjust 发出一则预期提示。该提示
        不等待、无样式且启用文本宽度。
        """
        text = get_text._("\n请先使用邀请系统选择邀请的对象，再进行邀请\n")
        self.assertEqual(
            self.payload["invite_without_target"], [[text, False, None, True]]
        )

    def test_apology_gift_waits_in_gold(self) -> None:
        """
        断言传入类型为 2 的礼物时，handle_give_gift_add_adjust 发出一则预期提示。该提示
        等待确认、样式为 gold_enrod 且不启用文本宽度。
        """
        text = get_text._("\n  {0}的反发刻印从1级降为了0\n\n").format("c1")
        self.assertEqual(
            self.payload["apology_gift"], [[text, True, "gold_enrod", False]]
        )

    def test_reading_reports_progress_in_gold(self) -> None:
        """
        断言 handle_read_add_adjust 使角色 0 的 read_progress 严格介于 0 与 100 之间。
        同时断言该函数发出一则包含所读书名与实测进度的预期提示。该提示不等待、样式为
        gold_enrod 且不启用文本宽度。
        """
        progress = self.payload["read_progress"]
        self.assertTrue(0 < progress < 100)
        name = game_config.config_book[self.payload["book"]].name
        text = get_text._("\n{0}阅读了{1}，").format("c0", name)
        text += get_text._("阅读进度增加了{0}%，从{1}%增加到{2}%").format(
            progress, 0, progress
        )
        self.assertEqual(
            self.payload["read"], [[text + "。\n", False, "gold_enrod", False]]
        )

    def test_sanity_out_ends_hypnosis(self) -> None:
        """
        断言理智为 0 时，handle_hypnosis_one 末条提示为采用默认参数的预期文本。同时断言
        角色 1 的 unconscious_h 归零。
        """
        text = get_text._("\n{0}的理智耗尽，催眠结束\n\n").format("c0")
        self.assertEqual(
            self.payload["sanity_out"][-1], [text, False, None, False]
        )
        self.assertEqual(self.payload["unconscious_h"], 0)

    def test_active_h_on_plans_h(self) -> None:
        """
        断言 handle_target_hypnosis_active_h_switch_change 不发出提示。同时断言角色 1
        的 active_h 为真。并断言角色 0 的计划队列包含 constant.Behavior.H。
        """
        self.assertEqual(self.payload["active_h_on"], [])
        self.assertTrue(self.payload["active_h"])
        self.assertTrue(self.payload["planned_h"])
