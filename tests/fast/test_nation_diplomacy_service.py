"""
势力外交服务测试
================
覆盖读档时的感染率修补与启动登记、国家与无国家势力列表及详情、
外交官摘要、候选筛选、外派与岛上任免、可选外交方针判定，
以及无界面纯后端子进程中的外交官任免与导入隔离。
"""

import json
import subprocess
import sys

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, country, diplomacy
from Script.Modules.domains import flags, location, relations, roster
from Script.Modules.gameplay_resolution import nation_diplomacy_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Panel import nation_diplomacy_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

COLUMBIA = 4
""" 哥伦比亚的国家编号。 """
COLUMBIA_NATION = 41
""" 哥伦比亚主势力的编号。 """
RHINE_LAB = 42
""" 哥伦比亚附属势力莱茵生命的编号。 """
YAN = 17
""" 炎的国家编号。 """
REUNION = 511
""" 无所属国家的整合运动势力编号。 """

BACKEND_RUN = """
import contextlib, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle", "Script.System.Instruct_System.handle_instruct",
    "Script.Core.flow_handle", "Script.Core.io_init", "Script.Core.game_init",
    "Script.Core.image_cache", "Script.Core.key_listion_event", "Script.Core.main_frame",
    "Script.Core.py_cmd", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
ALLOWED = ("Script.Modules.tk_ui", "Script.Modules.tk_ui.orders")
attempted = []
def is_blocked(name):
    return name not in ALLOWED and any(
        name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
sys.meta_path.insert(0, Blocker())
out = {}
with contextlib.redirect_stdout(io.StringIO()):
    from Script.Config import game_config, map_config, normal_config
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
    from Script.Design import attr_calculation, game_time
    from Script.Kernel import core
    from Script.Modules.domains import abilities, body_manage, chara_life
    from Script.Modules.domains import country, diplomacy, flags, identity, location
    from Script.Modules.domains import needs, roster, status, wardrobe
    from Script.Modules.gameplay_resolution import nation_diplomacy_service as svc
    from Script.Modules.gameplay_resolution import plan_queue, working
    from Script.Modules.save_load import kernel_state, reset
    from Script.Core import game_type
    from Script.Design import talk
    out["repairs"] = reset._repairs.count(svc.update_nation_data)
    talks = []
    draw = talk.handle_talk_draw
    def record(character_id, talk_text, talk_id, behavior_id, *rest):
        talks.append([character_id, behavior_id])
        return draw(character_id, talk_text, talk_id, behavior_id, *rest)
    talk.handle_talk_draw = record
    normal_config.system_setting = attr_calculation.get_system_setting_zero()
    normal_config.ai_setting = game_type.Ai_Setting()
    kernel_state.reset_clock(kernel_state.first_clock())
    def seen(cid):
        return [chara_life.work_type(cid), flags.get(cid, "in_diplomatic_visit"),
            roster.has(cid)]
    with working.based_on(core.state()):
        for cid in (0, 1, 2, 3):
            identity.put(identity.Identity(cid, name=f"c{cid}"))
            abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
            abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
            abilities.juel(cid).replace(attr_calculation.get_juel_zero({}))
            abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
            wardrobe.put(cid, attr_calculation.get_cloth_zero())
            status.replace(cid, attr_calculation.get_status_zero({}))
            body_manage.replace(cid, attr_calculation.get_body_manage_zero())
            needs.set(cid, hit_max=100, hit=1, mana_max=100, mana=1)
            if cid:
                roster.add(cid)
        country.fill()
        abroad = svc.assign_diplomat(1, 4)
        out["abroad"] = [abroad.is_local, seen(1)]
        flags.set(1, escaping=True)
        mark = plan_queue.mark()
        relieved = svc.assign_diplomat(0, 4)
        out["relieved"] = [relieved, seen(1), needs.of(1)["hit"], flags.get(1, "escaping"),
            plan_queue.take_since(mark)]
        location.set_move(4, game_time.now())
        location.arrive()
        local = svc.assign_diplomat(2, 4)
        out["local"] = [local.is_local, seen(2)]
        mark = plan_queue.mark()
        svc.assign_diplomat(3, 4)
        out["replaced"] = [seen(2), seen(3), diplomacy.of(4)["diplomat"],
            needs.of(2)["hit"], plan_queue.take_since(mark)]
out["talks"] = talks
out["loaded"] = sorted(name for name in sys.modules if is_blocked(name))
out["attempted"] = sorted(set(attempted))
print(json.dumps(out))
"""
"""
在拦截界面、结算与窗口模块的独立子进程中加载预构建配置并执行外交官任免全流程，
以单行 JSON 输出修补登记数、状态变化、触发对话及拦截结果的测试脚本。
"""

STARTUP_RUN = """
import contextlib, io, json
with contextlib.redirect_stdout(io.StringIO()):
    from Script.Config import game_config, normal_config
    normal_config.init_normal_config()
    game_config.init()
    import Script.Settle, Script.StateMachine, Script.System.Medical_System
    import Script.UI.Flow
    from Script.Kernel import core
    from Script.Modules import load_order
    from Script.Modules.domains import country
    from Script.Modules.gameplay_resolution import working
    from Script.Modules.save_load import kernel_state, reset
    kernel_state.reset_clock(kernel_state.first_clock())
    core.load(load_order.LOAD_ORDER)
    found = [fn for fn in reset._repairs if fn.__name__ == "update_nation_data"]
    names = [f"{fn.__module__}.{fn.__qualname__}" for fn in found]
    with working.based_on(core.state()):
        found[0]()
        rate = country.infection_rate(4)
print(json.dumps([names, rate]))
"""
"""
按游戏启动顺序导入界面流程并载入插件模块，在工作集中运行已登记的读档修补，
并以单行 JSON 输出登记项名称与哥伦比亚感染率的测试脚本。
"""


def run_script(script: str) -> object:
    """在仓库根目录的新子进程中执行脚本，并将标准输出按 JSON 解析后返回。"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


class NationDiplomacyCase(FastTestCase):
    """初始化玩家与三名干员并打开工作集上下文的测试基类。"""

    def setUp(self) -> None:
        """重置测试世界，创建玩家与干员 1 至 3，并进入工作集上下文。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.world.chara(3, "丙")
        self.enterContext(working.based_on(core.state()))

    def move_to(self, country_id: int) -> None:
        """将罗德岛移动到指定国家并完成抵达。"""
        location.set_move(country_id, game_time.now())
        location.arrive()


class FilledCase(NationDiplomacyCase):
    """在 NationDiplomacyCase 基础上补齐国家数据的测试基类，供势力列表与外交官测试继承。"""

    def setUp(self) -> None:
        """完成基类初始化后调用 country.fill() 补齐国家声望与感染率表。"""
        super().setUp()
        country.fill()


class RepairTest(NationDiplomacyCase):
    """读档时的国家感染率修补与启动登记测试。"""

    def blank_world(self) -> None:
        """将全部势力声望与全部国家感染率清零。"""
        for nation_id in game_config.config_nation:
            country.set_reputation(nation_id, 0)
        for country_id in game_config.config_birthplace:
            country.set_infection_rate(country_id, 0)

    def test_blank_world_gets_configured_infection_rates(self) -> None:
        """验证全零状态下所有国家感染率按配置重置，且哥伦比亚为 45.0。"""
        self.blank_world()
        svc.update_nation_data()
        self.assertEqual(country.infection_rate(COLUMBIA), 45.0)
        self.assertEqual(
            {
                cid: country.infection_rate(cid)
                for cid in game_config.config_birthplace
            },
            {
                cid: data.infect_rate
                for cid, data in game_config.config_birthplace.items()
            },
        )

    def test_empty_tables_get_configured_infection_rates(self) -> None:
        """验证国家数据表为空时视作全零，各国感染率设为配置值（哥伦比亚为 45.0）且声望表保持为空。"""
        svc.update_nation_data()
        self.assertEqual(country.infection_rate(COLUMBIA), 45.0)
        self.assertEqual(country.table(country.REPUTATION), {})

    def test_any_reputation_or_infection_keeps_state(self) -> None:
        """验证任一势力存在声望或任一国家存在感染率时，修补不改动感染率。"""
        self.blank_world()
        country.set_reputation(RHINE_LAB, 1)
        svc.update_nation_data()
        self.assertEqual(country.infection_rate(COLUMBIA), 0)
        self.blank_world()
        country.set_infection_rate(YAN, 3)
        svc.update_nation_data()
        self.assertEqual(
            (country.infection_rate(COLUMBIA), country.infection_rate(YAN)),
            (0, 3),
        )

    def test_game_startup_registers_repair_once(self) -> None:
        """
        验证仅经游戏启动流程导入即可登记一次 nation_diplomacy_service.update_nation_data，
        且执行后哥伦比亚感染率为 45.0。
        """
        self.assertEqual(
            run_script(STARTUP_RUN),
            [
                [
                    "Script.Modules.gameplay_resolution.nation_diplomacy_service"
                    ".update_nation_data"
                ],
                45.0,
            ],
        )


class NationListTest(FilledCase):
    """国家与无国家势力列表及势力详情查询测试。"""

    def test_country_tab_lists_main_nations_with_figures(self) -> None:
        """验证国家标签页仅列有国家的主势力，并核对声望、感染率、外交官与所在地高亮。"""
        self.move_to(COLUMBIA)
        country.set_reputation(COLUMBIA_NATION, 30.126)
        country.set_infection_rate(COLUMBIA, 12.34567)
        diplomacy.set_post(COLUMBIA, diplomat=1)
        rows = {row.nation_id: row for row in svc.list_nations(False)}
        self.assertNotIn(RHINE_LAB, rows)
        self.assertNotIn(REUNION, rows)
        self.assertFalse(
            {nid for nid in rows if game_config.config_nation[nid].country == 0}
        )
        self.assertEqual(
            rows[COLUMBIA_NATION],
            svc.NationRow(
                COLUMBIA_NATION, "哥伦比亚", 30.13, "友好", 12.346, "甲", True
            ),
        )
        self.assertEqual(
            [nid for nid, row in rows.items() if row.is_local], [41]
        )
        self.assertIsNone(rows[171].diplomat_name)

    def test_other_tab_lists_stateless_nations(self) -> None:
        """验证其他势力标签页仅列无国家势力，且无感染率、外交官与所在地高亮。"""
        self.move_to(COLUMBIA)
        rows = svc.list_nations(True)
        self.assertEqual([row.nation_id for row in rows], [504, 511, 512, 513])
        self.assertEqual(
            {(r.infection_rate, r.diplomat_name, r.is_local) for r in rows},
            {(None, None, False)},
        )

    def test_nation_detail(self) -> None:
        """验证势力详情包含四舍五入后的声望与感染率、特产列表及附属势力声望。"""
        country.set_reputation(COLUMBIA_NATION, -60.004)
        country.set_reputation(RHINE_LAB, 80)
        country.set_infection_rate(COLUMBIA, 7.77777)
        detail = svc.get_nation_detail(COLUMBIA_NATION)
        self.assertEqual(
            detail,
            svc.NationDetail(
                COLUMBIA,
                "哥伦比亚",
                -60.0,
                7.778,
                ("噪音引擎", "飞行数据记录芯片"),
                (
                    svc.SubordinateReputation("莱茵生命", 80, "尊敬"),
                    svc.SubordinateReputation("黑钢国际", 0, "中立"),
                ),
            ),
        )


class DiplomatTest(FilledCase):
    """外交官摘要、候选筛选、任免状态及外交方针测试。"""

    def diplomat_state(self, cid: int) -> tuple[int, int, bool]:
        """返回指定角色的工作类型、外交访问国家编号与在编状态三元组。"""
        return (
            chara_life.work_type(cid),
            flags.get(cid, "in_diplomatic_visit"),
            roster.has(cid),
        )

    def test_summary_shows_ability_effect_and_policy(self) -> None:
        """验证现任外交官的话术效果按 5 倍等级修正计算，并返回对应外交方针名称。"""
        self.assertIsNone(svc.get_diplomat_summary(COLUMBIA))
        abilities.ability(1)[40] = 3
        diplomacy.set_post(COLUMBIA, diplomat=1, policy=2)
        self.assertEqual(
            svc.get_diplomat_summary(COLUMBIA),
            svc.DiplomatSummary(
                0, "甲", "话术技能", 3, 7.0, "设立和完善外勤办事处"
            ),
        )

    def test_candidates_by_birthplace_nation_and_current(self) -> None:
        """验证候选干员按出身国或所属势力筛选，且包含离舰状态的现任外交官。"""
        relations.birthplace.set(1, COLUMBIA)
        relations.nation.set(2, COLUMBIA_NATION)
        relations.nation.set(3, RHINE_LAB)
        abilities.ability(2)[40] = 4
        view = svc.list_diplomat_candidates(COLUMBIA_NATION)
        self.assertEqual((view.country_id, view.country_name), (4, "哥伦比亚"))
        self.assertEqual(
            [(c.character_id, c.ability_level) for c in view.candidates],
            [(1, 0), (2, 4)],
        )
        relations.birthplace.set(3, COLUMBIA)
        diplomacy.set_post(COLUMBIA, diplomat=3)
        roster.remove(3)
        current = svc.list_diplomat_candidates(COLUMBIA_NATION).candidates
        self.assertEqual(
            [(c.character_id, c.is_current) for c in current],
            [(1, False), (2, False), (3, True)],
        )

    def test_overseas_appointment_replacement_and_toggle(self) -> None:
        """验证外派任命使干员离舰、改任解除前任外交官，以及重复选择现任时仅解除。"""
        self.move_to(YAN)
        appointment = svc.assign_diplomat(1, COLUMBIA)
        self.assertEqual(
            appointment, svc.DiplomatAppointment("甲", "哥伦比亚", False)
        )
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], 1)
        self.assertEqual(self.diplomat_state(1), (131, COLUMBIA, False))
        svc.assign_diplomat(2, COLUMBIA)
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], 2)
        self.assertEqual(self.diplomat_state(1)[:2], (0, 0))
        self.assertEqual(self.diplomat_state(2), (131, COLUMBIA, False))
        self.assertIsNone(svc.assign_diplomat(2, COLUMBIA))
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], 0)
        self.assertEqual(self.diplomat_state(2)[:2], (0, 0))

    def test_local_appointment_stays_on_board(self) -> None:
        """验证在罗德岛所在国经面板任命外交官时干员留在舰上并输出岛上办公提示。"""
        self.move_to(COLUMBIA)
        self.world.wait_texts.clear()
        nation_diplomacy_panel.Nation_Diplomacy_Panel(80).sure_NPC(1, COLUMBIA)
        self.assertEqual(self.diplomat_state(1), (131, COLUMBIA, True))
        self.assertEqual(diplomacy.of(COLUMBIA)["diplomat"], 1)
        self.assertEqual(len(self.world.wait_texts), 1)
        self.assertIn("甲被任命为哥伦比亚的外交官", self.world.wait_texts[0])

    def test_policies_follow_visitor_area_and_ability(self) -> None:
        """验证可选外交方针受访客区等级与外交官话术等级限制，并正确标记与切换当前方针。"""
        abilities.ability(1)[40] = 2
        diplomacy.set_post(COLUMBIA, diplomat=1, policy=1)
        kernel_data.set_facility_level(13, 3)
        view = svc.list_available_policies(COLUMBIA_NATION)
        self.assertEqual(view.country_id, COLUMBIA)
        self.assertEqual(
            [(o.policy_id, o.is_selected) for o in view.options],
            [(0, False), (1, True), (2, False)],
        )
        kernel_data.set_facility_level(13, 1)
        svc.set_diplomatic_policy(COLUMBIA, 0)
        self.assertEqual(
            [
                (o.policy_id, o.is_selected)
                for o in svc.list_available_policies(COLUMBIA_NATION).options
            ],
            [(0, True), (1, False)],
        )


class BackendRunTest(FastTestCase):
    """无界面纯后端子进程中的势力外交服务运行与导入隔离测试。"""

    def test_backend_only_subprocess_assigns_without_ui(self) -> None:
        """
        验证在拦截界面、结算与窗口模块的独立子进程中可登记修补并完成外交官外派、
        解除、本地任命与改任，且未加载或尝试导入任何被拦截模块。
        """
        self.assertEqual(
            run_script(BACKEND_RUN),
            {
                "repairs": 1,
                "abroad": [False, [131, COLUMBIA, False]],
                "relieved": [None, [0, 0, True], 100, False, ["1"]],
                "local": [True, [131, COLUMBIA, True]],
                "replaced": [[0, 0, True], [131, COLUMBIA, True], 3, 1, []],
                "talks": [
                    [1, "appoinnted_as_diplomat_out"],
                    [1, "relieved_of_diplomat_out"],
                    [2, "appoinnted_as_diplomat_local"],
                    [2, "relieved_of_diplomat_local"],
                    [3, "appoinnted_as_diplomat_local"],
                ],
                "loaded": [],
                "attempted": [],
            },
        )
