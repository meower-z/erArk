"""
势力外交服务测试
================
验证势力列表与详情查询、在任外交官与候选干员筛选、外交官任免、外交方针查询与设定以及读档感染率修补。
包含独立子进程隔离测试，验证势力外交服务在不导入界面与结算模块、开启翻译与文本生成设置时可正常运行。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from Script.Config import game_config
from Script.Design import attr_calculation, handle_ability
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, chara_life, country
from Script.Modules.domains import diplomacy, flags, location, relations
from Script.Modules.domains import roster
from Script.Modules.gameplay_resolution import nation_diplomacy_service as svc
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
"""仓库根目录路径。"""
COLUMBIA = 4
"""哥伦比亚的出生地编号（Birthplace.csv 编号 4）。"""
MAIN = 41
"""哥伦比亚主势力编号，附属势力为 42 与 43。"""
SUBS = (42, 43)
"""哥伦比亚主势力的附属势力编号。"""
HOME = 171
"""罗德岛开局所在国家（出生地编号 17）的主势力编号。"""
OTHER = 511
"""不属于任何国家的势力编号。"""
ENVOY = 1
"""出身哥伦比亚的测试干员编号。"""
AIDE = 2
"""所属势力为哥伦比亚主势力的测试干员编号。"""
STRANGER = 3
"""出身地与所属势力都不是哥伦比亚的测试干员编号。"""
UI_FREE_RUN = """
import contextlib, importlib.abc, io, json, sys
from types import MappingProxyType
BLOCKED = (
    "Script.UI",
    "Script.Settle",
    "Script.Design.handle_chat_ai",
    "Script.System.Instruct_System.handle_instruct",
    "Script.Core.flow_handle",
    "Script.Core.io_init",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
    "Script.Frontend",
    "PIL",
)
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
attempted = []
def blocked(name):
    if name in ALLOWED:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
from Script.Config import game_config, map_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
normal_config.config_normal.language = "en_US"
normal_config.ai_setting.ai_chat_translator_setting = 2
normal_config.ai_setting.ai_chat_setting[1] = 1
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, country, diplomacy, facility
from Script.Modules.domains import flags, identity, relations, roster, wardrobe
from Script.Modules.gameplay_resolution import nation_diplomacy_service as svc
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.save_load import kernel_state
normal_config.system_setting = attr_calculation.get_system_setting_zero()
ai = []
def text_ai(character_id, behavior_id, original_text, *, translator):
    ai.append([character_id, behavior_id, translator])
    return original_text
ui_hooks.on_text_ai(text_ai)
empty = MappingProxyType({})
core.reset_state(core.GameState(kernel_state.first_clock(), empty, empty))
with working.based_on(core.state()):
    for cid, name in ((0, "Doctor"), (1, "Envoy"), (2, "Aide")):
        identity.put(identity.Identity(cid, name=name))
        wardrobe.put(cid, attr_calculation.get_cloth_zero())
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
    for cid in (1, 2):
        roster.add(cid)
        relations.birthplace.set(cid, 4)
    abilities.ability(1)[svc.SKILL] = 3
    country.fill()
    facility.set_level(svc.VISITOR_AREA, 5)
    out = {
        "countries": [row.nation_id for row in svc.list_nations(True)],
        "others": [row.nation_id for row in svc.list_nations(False)],
        "specialties": len(svc.nation_detail(41).specialties),
        "candidates": [d.character_id for d in svc.candidates(41).diplomats],
        "abroad": svc.assign_diplomat(1, 41).local,
        "abroad_on_roster": roster.has(1),
        "posting": svc.posting(41).diplomat.character_id,
        "policies": [p.policy_id for p in svc.policies(41)],
    }
    svc.set_policy(41, 3)
    out["policy"] = diplomacy.of(4)["policy"]
    flags.set(1, escaping=1)
    out["swap"] = svc.assign_diplomat(2, 41).name
    out["relieved_on_roster"] = roster.has(1)
    out["translated"] = list(ai)
    ai.clear()
    normal_config.ai_setting.ai_chat_translator_setting = 0
    out["toggle"] = svc.assign_diplomat(2, 41)
    out["vacant"] = svc.posting(41)
    out["generated"] = list(ai)
    for nid in game_config.config_nation:
        country.set_reputation(nid, 0)
    for cid in game_config.config_birthplace:
        country.set_infection_rate(cid, 0)
    svc.update_nation_data()
    out["repaired"] = country.infection_rate(4)
modules = sorted(sys.modules)
out["ui"] = [n for n in modules if n == "Script.UI" or n.startswith("Script.UI.")]
out["settle"] = [
    n for n in modules if n == "Script.Settle" or n.startswith("Script.Settle.")
]
out["blocked"] = [n for n in modules if blocked(n)]
out["attempted"] = attempted
print(json.dumps(out))
"""
"""子进程隔离脚本，用于拦截界面、结算、指令处理与 Tk 相关模块并运行势力外交服务全部入口。"""


class DiplomacyCase(FastTestCase):
    """势力外交服务测试基类。"""

    def setUp(self) -> None:
        """准备博士与三名测试干员、开启写缓冲、补齐国家表并配置出身地、所属势力与话术技能等级。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(ENVOY, "干员甲", adv=12)
        self.world.chara(AIDE, "干员乙")
        self.world.chara(STRANGER, "干员丙")
        self.enterContext(working.based_on(core.state()))
        country.fill()
        relations.birthplace.set(ENVOY, COLUMBIA)
        relations.nation.set(AIDE, MAIN)
        relations.birthplace.set(STRANGER, location.START)
        abilities.ability(ENVOY)[svc.SKILL] = 3
        abilities.ability(AIDE)[svc.SKILL] = 1


class ListNationsTest(DiplomacyCase):
    """势力列表两页的筛选与行数据测试。"""

    def test_country_page_lists_main_nations_with_their_country(self) -> None:
        """国家页列出各国主势力，排除罗德岛、无所属国家势力与附属势力，并返回声望、等级、感染率、外交官与本地标记。"""
        country.set_reputation(MAIN, 12.3456)
        diplomacy.set_post(COLUMBIA, diplomat=ENVOY)
        rows = {row.nation_id: row for row in svc.list_nations(True)}
        self.assertIn(HOME, rows)
        for hidden in (0, OTHER, *SUBS):
            self.assertNotIn(hidden, rows)
        row = rows[MAIN]
        self.assertEqual(row.name, game_config.config_nation[MAIN].name)
        self.assertEqual(row.reputation, 12.35)
        self.assertEqual(
            row.reputation_level,
            attr_calculation.get_reputation_level(12.35)[1],
        )
        self.assertEqual(
            row.infection_rate, round(country.infection_rate(COLUMBIA), 3)
        )
        self.assertEqual(row.diplomat_name, "干员甲")
        self.assertFalse(row.local)
        self.assertIsNone(rows[HOME].diplomat_name)
        self.assertTrue(rows[HOME].local)

    def test_other_page_lists_nations_without_country(self) -> None:
        """其他页仅列出国家编号为 -1 的势力，感染率为 None 且本地标记为 False。"""
        rows = svc.list_nations(False)
        self.assertIn(OTHER, [row.nation_id for row in rows])
        for row in rows:
            nation = game_config.config_nation[row.nation_id]
            self.assertEqual(nation.country, svc.NO_COUNTRY)
            self.assertIsNone(row.infection_rate)
            self.assertFalse(row.local)


class NationDetailTest(DiplomacyCase):
    """势力详情查询测试。"""

    def test_detail_lists_specialties_and_subordinate_reputation(self) -> None:
        """势力详情返回保留三位小数的国家感染率、所属国家特产名称以及各附属势力的声望与等级。"""
        country.set_reputation(SUBS[0], -3.216)
        country.set_infection_rate(COLUMBIA, 12.34567)
        detail = svc.nation_detail(MAIN)
        self.assertEqual(detail.infection_rate, 12.346)
        specialties = game_config.config_resouce_data_of_nation[COLUMBIA]
        self.assertEqual(
            detail.specialties,
            tuple(game_config.config_resouce[r].name for r in specialties),
        )
        first = detail.subordinates[0]
        self.assertEqual(
            [sub.name for sub in detail.subordinates],
            [game_config.config_nation[cid].name for cid in SUBS],
        )
        self.assertEqual(first.reputation, -3.22)
        self.assertEqual(
            first.reputation_level,
            attr_calculation.get_reputation_level(-3.22)[1],
        )

    def test_nation_without_country_has_zero_infection(self) -> None:
        """无所属国家且缺少感染率记录的势力在详情中返回感染率 0。"""
        self.assertEqual(svc.nation_detail(OTHER).infection_rate, 0)


class PostingTest(DiplomacyCase):
    """在任外交官与外交方针查询测试。"""

    def test_vacant_post_has_no_posting(self) -> None:
        """外交官空缺时即使已设定方针，posting 仍返回 None。"""
        diplomacy.set_post(COLUMBIA, policy=2)
        self.assertIsNone(svc.posting(MAIN))

    def test_posting_shows_skill_effect_and_policy(self) -> None:
        """已任命外交官时，posting 返回外交官展示数据、话术技能名称、效果百分比与当前外交方针名称。"""
        diplomacy.set_post(COLUMBIA, diplomat=ENVOY, policy=2)
        post = svc.posting(MAIN)
        assert post is not None
        self.assertEqual(post.diplomat, svc.Diplomat(ENVOY, 12, "干员甲", 3))
        self.assertEqual(
            post.skill_name, game_config.config_ability[svc.SKILL].name
        )
        self.assertEqual(post.effect, 5 * handle_ability.get_ability_adjust(3))
        self.assertEqual(
            post.policy_name, game_config.config_diplomatic_policy[2].name
        )


class CandidatesTest(DiplomacyCase):
    """外交官候选筛选测试。"""

    def test_candidates_match_birthplace_or_nation_and_keep_incumbent(
        self,
    ) -> None:
        """候选列表包含出身地或所属势力符合条件的在编干员，并保留已离队的在任外交官。"""
        roster.remove(ENVOY)
        diplomacy.set_post(COLUMBIA, diplomat=ENVOY)
        found = svc.candidates(MAIN)
        self.assertEqual(
            found.country_name, game_config.config_birthplace[COLUMBIA].name
        )
        self.assertEqual(found.current_id, ENVOY)
        self.assertEqual(
            sorted(d.character_id for d in found.diplomats), [ENVOY, AIDE]
        )


class AssignDiplomatTest(DiplomacyCase):
    """外交官任免测试。"""

    def test_appointment_abroad_takes_diplomat_off_the_ship(self) -> None:
        """任命非当前所在国家的外交官时，写入外交岗位、工作类型与驻在国标记，并将该干员移出在编名单与地图。"""
        appointment = svc.assign_diplomat(ENVOY, MAIN)
        self.assertEqual(
            appointment,
            svc.Appointment(
                "干员甲", game_config.config_birthplace[COLUMBIA].name, False
            ),
        )
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], ENVOY)
        self.assertEqual(chara_life.work_type(ENVOY), svc.DIPLOMAT_WORK)
        self.assertEqual(flags.get(ENVOY, "in_diplomatic_visit"), COLUMBIA)
        self.assertFalse(roster.has(ENVOY))
        self.assertEqual(activity.position(ENVOY), ["0", "0"])

    def test_local_appointment_stays_on_the_ship(self) -> None:
        """任命罗德岛当前所在国家的外交官时，返回本地任命结果且干员保留在在编名单中。"""
        appointment = svc.assign_diplomat(STRANGER, HOME)
        assert appointment is not None
        self.assertTrue(appointment.local)
        self.assertEqual(diplomacy.of(location.START)["diplomat"], STRANGER)
        self.assertTrue(roster.has(STRANGER))

    def test_replacement_relieves_and_brings_back_the_incumbent(self) -> None:
        """改任其他干员时解除原在任外交官并清空其外交状态，原任因其他标记仍判定离线时被召回在编名单。"""
        svc.assign_diplomat(ENVOY, MAIN)
        flags.set(ENVOY, escaping=1)
        appointment = svc.assign_diplomat(AIDE, MAIN)
        assert appointment is not None
        self.assertEqual(appointment.name, "干员乙")
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], AIDE)
        self.assertEqual(chara_life.work_type(ENVOY), 0)
        self.assertEqual(flags.get(ENVOY, "in_diplomatic_visit"), 0)
        self.assertTrue(roster.has(ENVOY))

    def test_choosing_the_incumbent_only_relieves(self) -> None:
        """再次选中在任外交官本人时仅解除其任命并清空外交状态，返回 None。"""
        svc.assign_diplomat(STRANGER, HOME)
        self.assertIsNone(svc.assign_diplomat(STRANGER, HOME))
        self.assertEqual(diplomacy.of(location.START)["diplomat"], 0)
        self.assertEqual(chara_life.work_type(STRANGER), 0)
        self.assertEqual(flags.get(STRANGER, "in_diplomatic_visit"), 0)


class PolicyTest(DiplomacyCase):
    """外交方针查询与设定测试。"""

    def test_policies_follow_visitor_area_and_diplomat_skill(self) -> None:
        """可选外交方针按访客区等级与在任外交官话术技能等级过滤，并标出当前生效方针。"""
        diplomacy.set_post(COLUMBIA, diplomat=ENVOY, policy=1)
        kernel_data.set_facility_level(svc.VISITOR_AREA, 2)
        options = svc.policies(MAIN)
        self.assertEqual([p.policy_id for p in options], [0, 1, 2])
        self.assertEqual([p.selected for p in options], [False, True, False])
        kernel_data.set_facility_level(svc.VISITOR_AREA, 5)
        self.assertEqual(
            [p.policy_id for p in svc.policies(MAIN)], [0, 1, 2, 3]
        )
        diplomacy.set_post(COLUMBIA, diplomat=AIDE)
        self.assertEqual([p.policy_id for p in svc.policies(MAIN)], [0, 1])

    def test_set_policy_writes_the_country_post(self) -> None:
        """设定外交方针仅更新势力所属国家的方针编号，保留在任外交官不变。"""
        diplomacy.set_post(COLUMBIA, diplomat=ENVOY, policy=1)
        svc.set_policy(MAIN, 3)
        self.assertEqual(
            diplomacy.of(COLUMBIA), {"diplomat": ENVOY, "policy": 3}
        )


class UpdateNationDataTest(DiplomacyCase):
    """读档感染率修补测试。"""

    def zero(self) -> None:
        """将全部势力声望与全部国家矿石病感染率清零。"""
        for nid in game_config.config_nation:
            country.set_reputation(nid, 0)
        for cid in game_config.config_birthplace:
            country.set_infection_rate(cid, 0)

    def test_all_zero_resets_infection_to_config(self) -> None:
        """全部势力声望与全部国家感染率均为 0 时，将各国感染率重置为配置初始值。"""
        self.zero()
        svc.update_nation_data()
        for cid, data in game_config.config_birthplace.items():
            self.assertEqual(country.infection_rate(cid), data.infect_rate)

    def test_any_reputation_or_infection_keeps_data(self) -> None:
        """存在任意非零势力声望或非零国家感染率时，保持各国感染率不变。"""
        for nid, cid in ((MAIN, None), (None, COLUMBIA)):
            with self.subTest(nation=nid, country=cid):
                self.zero()
                if nid is not None:
                    country.set_reputation(nid, 1)
                if cid is not None:
                    country.set_infection_rate(cid, 2)
                before = country.table(country.INFECTION)
                svc.update_nation_data()
                self.assertEqual(country.table(country.INFECTION), before)


class UiFreeRunTest(FastTestCase):
    """势力外交服务在无界面、无结算隔离环境中的独立运行测试。"""

    def test_service_runs_without_ui_or_settle(self) -> None:
        """在 cp1252 隔离子进程跑通服务全部入口，确认翻译与文本生成回调触发且无受拦导入。"""
        result = subprocess.run(
            [sys.executable, "-c", UI_FREE_RUN],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["ui"], [])
        self.assertEqual(out["settle"], [])
        self.assertEqual(out["blocked"], [])
        self.assertEqual(out["attempted"], [])
        self.assertIn(MAIN, out["countries"])
        self.assertIn(OTHER, out["others"])
        self.assertEqual(out["specialties"], 2)
        self.assertEqual(out["candidates"], [ENVOY, AIDE])
        self.assertFalse(out["abroad"])
        self.assertFalse(out["abroad_on_roster"])
        self.assertEqual(out["posting"], ENVOY)
        self.assertEqual(out["policies"], [0, 1, 2, 3])
        self.assertEqual(out["policy"], 3)
        self.assertEqual(out["swap"], "Aide")
        self.assertTrue(out["relieved_on_roster"])
        self.assertEqual(
            out["translated"], [[ENVOY, "relieved_of_diplomat_out", True]]
        )
        self.assertIsNone(out["toggle"])
        self.assertIsNone(out["vacant"])
        self.assertEqual(
            out["generated"], [[AIDE, "relieved_of_diplomat_out", False]]
        )
        self.assertEqual(
            out["repaired"], game_config.config_birthplace[COLUMBIA].infect_rate
        )
