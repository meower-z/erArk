"""
礼物面板纯规则服务测试
======================
覆盖礼物列表展开收起与可选状态、骚扰判定字符串、好感与道歉及倒模礼物拦截规则、
体型与妊娠及成长类药物条件、卵与婴儿候选查询、面板等待提示适配以及无界面导入边界。
"""

import datetime
import json
import subprocess
import sys
from unittest import mock

from Script.Config import game_config
from Script.Design import game_time, handle_premise, second_behavior
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, flags, identity
from Script.Modules.domains import inventory, pregnancy
from Script.Modules.gameplay_resolution import gift_service as svc
from Script.Modules.gameplay_resolution import working
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.System.Pregnancy_System import pregnancy_handle
from Script.UI.Panel import gift_panel
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL.ImageTk")
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
def is_blocked(name):
    if name in ALLOWED:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, io, json
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Config import game_config
with contextlib.redirect_stdout(io.StringIO()):
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import abilities, identity, inventory
from Script.Modules.gameplay_resolution import gift_service, working
target = identity.Identity(1, name="甲")
with working.based_on(core.state()):
    for gift in game_config.config_gift_items.values():
        inventory.set_item(0, gift.item_id, 0)
    inventory.set_item(0, 171, 1)
    for talent_id in (125, 128):
        abilities.talent(1)[talent_id] = 0
    abilities.talent(1)[125] = 1
    menu = gift_service.gift_menu(False)
    out = {
        "menu": [getattr(e, "gift_id", e.text) for e in menu],
        "selectable": [e.gift_id for e in menu if getattr(e, "selectable", 0)],
        "judge": [gift_service.gift_judge(g) for g in (21, 51, 2)],
        "drug": [gift_service.drug_block_reason(d, target) for d in (21, 23)],
        "eggs": repr(gift_service.egg_pick(1)),
        "babies": repr(gift_service.baby_pick(1)),
    }
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的子进程中调用 gift_service 并输出调用结果与已加载受限模块列表的脚本。 """


class GiftServiceCase(FastTestCase):
    """礼物服务测试基类，初始化玩家与交互目标、启用临时状态缓冲并清空玩家礼物道具库存。"""

    def setUp(self) -> None:
        """
        创建玩家角色 0（博士）与目标角色 1（干员甲），设置交互目标并进入临时状态缓冲，随后将玩家各礼物对应道具数量清零。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.target = self.world.chara(1, "干员甲")
        aim(0, 1)
        self.enterContext(working.based_on(core.state()))
        for gift in game_config.config_gift_items.values():
            inventory.set_item(0, gift.item_id, 0)

    def refused(self, reason: str | None) -> str:
        """
        断言阻止原因不为 None 并返回该文本。
        当 reason 为 None 时直接使当前测试用例失败。
        Keyword arguments:
        reason -- str | None，待检查的阻止原因文本
        Return arguments:
        str -- 非 None 的阻止原因文本
        """
        if reason is None:
            self.fail("应当给出拒绝理由")
        return reason

    def patch(self, owner: object, name: str, value: object) -> None:
        """
        在当前测试用例生命周期内临时替换对象属性。
        Keyword arguments:
        owner -- object，待替换属性的宿主对象或模块
        name -- str，属性名称
        value -- object，替换后的属性值
        Return arguments:
        None -- 无返回值
        """
        self.enterContext(mock.patch.object(owner, name, value))


class GiftMenuTest(GiftServiceCase):
    """礼物列表组装与骚扰判定字符串测试。"""

    def test_collapsed_and_expanded_menu(self) -> None:
        """
        验证药物分组收起与展开时的礼物列表顺序及分组切换文案。
        同时验证已拥有、未拥有与未实装礼物的展示文本和可选标志。
        """
        inventory.set_item(0, 171, 1)
        inventory.set_item(0, 21, 2)
        collapsed = svc.gift_menu(False)
        self.assertEqual(
            [getattr(e, "gift_id", e.text) for e in collapsed],
            [2, 6, 7, 8, 11, "▶药物类", 51, 101],
        )
        expanded = svc.gift_menu(True)
        drugs = [
            g for g, d in game_config.config_gift_items.items() if d.type == 11
        ]
        self.assertEqual(
            [getattr(e, "gift_id", e.text) for e in expanded],
            [2, 6, 7, 8, 11, "▼药物类", *drugs, 51, 101],
        )
        rows = {e.gift_id: e for e in expanded if isinstance(e, svc.GiftRow)}
        item = game_config.config_item[171]
        self.assertEqual(
            rows[2], svc.GiftRow(2, f"[02]{item.name}：{item.info}", True)
        )
        self.assertTrue(rows[21].selectable)
        self.assertTrue(rows[6].text.endswith("(未拥有)"))
        self.assertFalse(rows[6].selectable)
        self.assertEqual(rows[11].text, "[11]节日礼物(未实装)(未拥有)")
        self.assertFalse(rows[11].selectable)

    def test_judge_by_gift_type(self) -> None:
        """验证药物类礼物、阴茎倒模与其他类型礼物分别返回对应的骚扰判定字符串或空字符串。"""
        self.assertEqual(
            [svc.gift_judge(g) for g in (21, 41, 51, 2, 6, 101)],
            ["初级骚扰", "初级骚扰", "严重骚扰", "", "", ""],
        )


class GiftBlockReasonTest(GiftServiceCase):
    """送礼可用性检查函数 gift_block_reason 的各类礼物拦截规则测试。"""

    def test_favor_gift_once_per_day(self) -> None:
        """验证好感礼物在同一天重复赠送时返回拦截提示，隔日赠送时返回 None。"""
        now = game_time.now()
        action_info.set(1, "last_gift_time", now)
        self.assertEqual(
            svc.gift_block_reason(6, self.target),
            "\n  干员甲今天已经收过好感礼物了，不能重复赠送\n",
        )
        action_info.set(1, "last_gift_time", now - datetime.timedelta(days=1))
        self.assertIsNone(svc.gift_block_reason(6, self.target))

    def test_apology_gift_checks_mark_anger_and_hate(self) -> None:
        """
        验证道歉礼物按反发刻印等级、生气标志与负面状态总值返回对应拦截提示或放行，并核对负面状态查询参数为 (51, 1)。
        """
        hate = mock.Mock(return_value=(0, ""))
        self.patch(
            second_behavior,
            "get_now_state_all_value_and_text_from_mark_up_data",
            hate,
        )
        abilities.ability(1)[18] = 2
        self.assertIn(
            "反发刻印大于等于2级",
            self.refused(svc.gift_block_reason(2, self.target)),
        )
        hate.assert_called_with(51, 1)
        abilities.ability(1)[18] = 0
        self.assertIn(
            "没有生气", self.refused(svc.gift_block_reason(2, self.target))
        )
        flags.set(1, angry_with_player=1)
        self.assertIsNone(svc.gift_block_reason(2, self.target))
        hate.return_value = (10000, "")
        self.assertIn(
            "负面状态值过高",
            self.refused(svc.gift_block_reason(2, self.target)),
        )
        abilities.ability(1)[18] = 1
        flags.set(1, angry_with_player=0)
        self.assertIn(
            "负面状态值过高",
            self.refused(svc.gift_block_reason(2, self.target)),
        )
        hate.return_value = (9999, "")
        self.assertIsNone(svc.gift_block_reason(2, self.target))

    def test_penis_mold_reads_the_given_recipient(self) -> None:
        """
        验证阴茎倒模礼物按传入收礼角色的道具 175 库存决定放行或返回包含该角色姓名的拦截提示。
        即使传入角色不是当前交互目标，结果仍依据该角色自身库存判定。
        """
        other = self.world.chara(2, "干员乙")
        inventory.set_item(1, 175, 0)
        inventory.set_item(2, 175, 1)
        self.assertIsNone(svc.gift_block_reason(51, self.target))
        self.assertEqual(
            svc.gift_block_reason(51, other),
            "\n  干员乙已经拥有了你的阴茎倒模，不能重复赠送\n",
        )
        inventory.set_item(1, 175, 1)
        inventory.set_item(2, 175, 0)
        self.assertEqual(
            svc.gift_block_reason(51, self.target),
            "\n  干员甲已经拥有了你的阴茎倒模，不能重复赠送\n",
        )
        self.assertIsNone(svc.gift_block_reason(51, other))

    def test_drug_gift_and_other_gifts(self) -> None:
        """验证药物礼物委托至 drug_block_reason 返回相同结果，未配置拦截规则的礼物返回 None。"""
        self.assertEqual(
            svc.gift_block_reason(22, self.target),
            svc.drug_block_reason(22, self.target),
        )
        self.assertIsNone(svc.gift_block_reason(101, self.target))


class DrugBlockReasonTest(GiftServiceCase):
    """药物可用性检查函数 drug_block_reason 的各类药物拦截规则测试。"""

    def test_body_shape_drugs_stop_at_the_extreme_talent(self) -> None:
        """验证体型药物 21 至 28 在目标未持有对应极限素质时放行，持有该素质时返回对应拦截提示。"""
        extremes = {
            21: (125, "爆乳"),
            22: (121, "绝壁"),
            23: (128, "巨臀"),
            24: (126, "小臀"),
            25: (130, "肉腿"),
            26: (129, "细腿"),
            27: (132, "长足"),
            28: (131, "小足"),
        }
        for drug_id, (talent_id, name) in extremes.items():
            with self.subTest(drug_id=drug_id):
                abilities.talent(1)[talent_id] = 0
                self.assertIsNone(svc.drug_block_reason(drug_id, self.target))
                abilities.talent(1)[talent_id] = 1
                reason = svc.drug_block_reason(drug_id, self.target)
                self.assertIn("干员甲已经是", self.refused(reason))
                self.assertIn(f"【{name}】", self.refused(reason))

    def test_pregnancy_drugs_follow_check_order(self) -> None:
        """验证泌乳药 33、停乳药 34 与妊娠相关药物 35 至 38 按既定前置条件顺序返回拦截提示或放行。"""
        premises = {"handle_in_nursery": False, "handle_pregnancy_1": True}
        for name in (
            "handle_fertilization_1",
            "handle_parturient_1",
            "handle_postpartum_1",
            "handle_rearing_1",
            "handle_fake_inflation_1",
            "handle_inflation_1",
            "handle_lactation_1",
        ):
            premises.setdefault(name, False)
        for name in premises:
            self.patch(handle_premise, name, lambda cid, n=name: premises[n])
        self.patch(egg_handle, "is_viviparous", lambda cid: True)
        self.patch(
            pregnancy_handle, "get_pregnancy_acceleration_amount", lambda c: 0
        )
        reason = svc.drug_block_reason
        self.assertIn("加速到极限", self.refused(reason(35, self.target)))
        self.assertEqual(
            reason(36, self.target), "\n  只能在育儿室使用孵化加速药\n"
        )
        self.assertIn("怀孕相关状态", self.refused(reason(37, self.target)))
        self.assertIn("没有处于假孕状态", self.refused(reason(38, self.target)))
        self.assertIsNone(reason(33, self.target))
        self.assertIn("没有在【泌乳】", self.refused(reason(34, self.target)))
        premises["handle_pregnancy_1"] = False
        self.assertIn(
            "没有处于受精或妊娠状态", self.refused(reason(35, self.target))
        )
        self.assertIsNone(reason(37, self.target))
        premises["handle_in_nursery"] = True
        self.patch(egg_handle, "get_hatching_eggs", lambda cid: {3: {}})
        self.patch(egg_handle, "get_accelerable_hatching_eggs", lambda cid: {})
        self.assertIn(
            "卵都已经加速到极限", self.refused(reason(36, self.target))
        )

    def test_growth_drug_self_target_and_mother(self) -> None:
        """验证成长加速药 39 的女儿自身目标分支按剩余可加速量判定，以及母亲目标分支在非育儿室场景下返回拦截提示。"""
        self_target = mock.Mock(return_value=True)
        self.patch(pregnancy_handle, "is_growth_drug_self_target", self_target)
        amount = mock.Mock(return_value=0)
        self.patch(
            pregnancy_handle, "get_child_growth_acceleration_amount", amount
        )
        self.assertIn(
            "成长到下一阶段",
            self.refused(svc.drug_block_reason(39, self.target)),
        )
        amount.return_value = 3
        self.assertIsNone(svc.drug_block_reason(39, self.target))
        self_target.return_value = False
        self.patch(handle_premise, "handle_in_nursery", lambda cid: False)
        self.assertEqual(
            svc.drug_block_reason(39, self.target),
            "\n  只能在育儿室对母亲使用成长加速药\n",
        )


class TargetPickTest(GiftServiceCase):
    """孵化中卵与婴儿候选查询函数 egg_pick 和 baby_pick 的返回结构与文案测试。"""

    def test_egg_pick_none_single_and_many(self) -> None:
        """验证 egg_pick 在无卵、单卵与多卵三种情况下的返回结果，并核对多卵选项的顺序与完整格式化文本。"""
        now = game_time.now()
        eggs: dict[int, dict] = {}
        self.patch(
            egg_handle, "get_accelerable_hatching_eggs", lambda cid: eggs
        )
        self.patch(egg_handle, "get_hatch_day", lambda egg: 4)
        self.assertEqual(svc.egg_pick(1), svc.TargetPick(None, ()))
        eggs[5] = {"lay_time": now}
        self.assertEqual(svc.egg_pick(1), svc.TargetPick(5, ()))
        eggs[3] = {"lay_time": now, "acceleration_days": 2.9}
        pick = svc.egg_pick(1)
        self.assertIsNone(pick.chosen)
        self.assertEqual([o.choice_id for o in pick.options], [5, 3])
        hatch = game_time.get_predict_date(
            pregnancy_constant.HATCH_TOTAL_DAY - 2, now
        )
        speed = game_time.get_duration_text(2)
        date = pregnancy_constant.format_season_date(hatch)
        self.assertEqual(
            pick.options[1].text,
            f"[3号卵] 孵化第4天（已加速{speed}，预计{date}破壳）",
        )

    def test_baby_pick_none_single_and_many(self) -> None:
        """验证 baby_pick 在无婴儿、单婴儿与多婴儿三种情况下的返回结果，并核对多婴儿选项的顺序与完整格式化文本。"""
        now = game_time.now()
        babies: list[int] = []
        self.patch(pregnancy_handle, "get_accelerable_babies", lambda c: babies)
        self.patch(pregnancy_handle, "get_child_grow_day", lambda c: 6)
        self.assertEqual(svc.baby_pick(1), svc.TargetPick(None, ()))
        for cid in (2, 3):
            self.world.chara(cid, f"婴儿{cid}")
            pregnancy.update(cid, born_time=now, growth_acceleration_days=1.5)
        babies.append(3)
        self.assertEqual(svc.baby_pick(1), svc.TargetPick(3, ()))
        babies.insert(0, 2)
        pick = svc.baby_pick(1)
        self.assertEqual([o.choice_id for o in pick.options], [2, 3])
        grown = game_time.get_predict_date(
            pregnancy_constant.REARING_COMPLETE_DAY - 1, now
        )
        speed = game_time.get_duration_text(1)
        date = pregnancy_constant.format_season_date(grown)
        self.assertEqual(
            pick.options[0].text,
            f"[婴儿2] 出生第6天（已加速{speed}，预计{date}成长为幼女）",
        )


class PanelAdapterTest(GiftServiceCase):
    """Gift_Panel 校验适配器方法与等待确认提示绘制的联动测试。"""

    def test_refusal_draws_one_wait_text(self) -> None:
        """验证礼物或药物被拒绝时面板仅绘制一条与服务返回值一致的等待确认提示，允许通过时不绘制任何提示。"""
        panel = gift_panel.Gift_Panel(80)
        abilities.talent(1)[125] = 1
        self.assertFalse(panel.is_drug_effective(21, identity.of(1)))
        self.assertEqual(
            self.world.wait_texts, [svc.drug_block_reason(21, self.target)]
        )
        self.world.wait_texts.clear()
        self.assertFalse(panel.check_gift_available(21))
        self.assertEqual(len(self.world.wait_texts), 1)
        self.world.wait_texts.clear()
        self.assertTrue(panel.check_gift_available(101))
        self.assertTrue(panel.is_drug_effective(23, identity.of(1)))
        self.assertEqual(self.world.wait_texts, [])


class BackendIsolationTest(FastTestCase):
    """gift_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """
        在拦截界面、结算与窗口模块的全新 Python 子进程中运行 gift_service 核心接口，验证调用结果正确且未加载受限模块。
        """
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["menu"], [2, 6, 7, 8, 11, "▶药物类", 51, 101])
        self.assertEqual(out["selectable"], [2])
        self.assertEqual(out["judge"], ["初级骚扰", "严重骚扰", ""])
        self.assertIn("【爆乳】", out["drug"][0])
        self.assertIsNone(out["drug"][1])
        self.assertEqual(out["eggs"], repr(svc.TargetPick(None, ())))
        self.assertEqual(out["babies"], repr(svc.TargetPick(None, ())))
