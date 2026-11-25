"""
角色信息服务测试
================
验证角色状态条、能力、经验、宝珠、素质、日程与访客文本规则。
验证玩家能力分组、信物展示与切换、读档修补以及场景角色循环步进。
同时通过无界面子进程验证导入与调用不触发 Script.UI 与 Script.Settle。
"""

import datetime
import os

from Script.Config import game_config
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, chara_life, h_state
from Script.Modules.domains import identity, modes, player_collection, status
from Script.Modules.domains import visitor
from Script.Modules.gameplay_resolution import character_info_service as svc
from Script.Modules.gameplay_resolution import player_ability_service as pas
from Script.Modules.gameplay_resolution import working
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

NPC = 1
""" 测试用首位干员角色编号。 """
OTHER = 2
""" 测试用次位干员角色编号。 """
MONDAY = datetime.datetime(2025, 3, 3, 9, 0)
""" 用于测试工作日日程分支的固定周一时间。 """
UI_FREE_RUN = """
import datetime
from Script.Config import game_config
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, chara_life, h_state
from Script.Modules.domains import identity, player_collection, relations
from Script.Modules.domains import roster, status, visitor, wardrobe
from Script.Modules.gameplay_resolution import character_info_service as svc
from Script.Modules.gameplay_resolution import player_ability_service as pas
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
with working.based_on(core.state()):
    for cid, name, sex in ((0, "doctor", 0), (1, "guest", 1), (2, "aide", 0)):
        identity.put(identity.Identity(cid, name=name, sex=sex, adv=cid))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
        abilities.juel(cid).replace(attr_calculation.get_juel_zero({}))
        status.replace(cid, attr_calculation.get_status_zero({}))
        wardrobe.put(cid, attr_calculation.get_cloth_zero())
        relations.favorability.set(cid, {0: 0})
        activity.set_position(cid, ["A", "B"])
        chara_life.entertainment_type.set(cid, list(game_config.config_entertainment)[1:4])
    roster.add(1)
    roster.add(2)
    abilities.talent(0)[307] = 1
    abilities.experience(1)[0] = 4
    with h_state.editing(1) as hs:
        hs.orgasm_edge_count = {0: 2}
    visitor.arrive(1, datetime.datetime(2025, 5, 1))
    player_collection.put("token_list", {1: True, 2: True})
    player_collection.put("eqip_token", [0, [0]])
    pas.repair_eqip_token()
    payload["repaired"] = player_collection.get("eqip_token")
    pas.toggle_token(1)
    payload["status"] = [
        [name, [bar.style for bar in bars]] for name, bars in svc.status_sections(1)
    ]
    payload["ability"] = [len(rows) for _, rows in svc.ability_sections(0)]
    payload["experience"] = svc.experience_texts(1)
    payload["juel"] = len(svc.juel_texts(2))
    payload["heading"] = len(svc.talent_heading(1))
    payload["talent"] = len(svc.talent_sections(1))
    payload["daily"] = svc.daily_text(1).count("\\n")
    payload["visitor"] = svc.visitor_text(1).count("：")
    payload["arts"] = [lines.count("\\n") for _, lines in pas.arts_groups(0)]
    payload["equipped"] = pas.equipped_token_text().count("guest")
    payload["heading_token"] = pas.token_heading().count("1/1")
    payload["choices"] = [
        [c.character_id, c.equipped, c.selectable] for c in pas.token_choices()
    ]
    payload["others"] = svc.scene_others()
    payload["walk"] = [svc.previous_in_scene(0, [1, 2]), svc.next_in_scene(2, [1, 2])]
"""
""" 在无界面子进程中执行角色信息服务各主要入口的测试脚本。 """


class InfoCase(FastTestCase):
    """角色信息服务单元测试基类。"""

    def setUp(self) -> None:
        """初始化主角与两名测试干员并开启状态写缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员甲", adv=7)
        self.world.chara(OTHER, "干员乙", adv=12)
        self.enterContext(working.based_on(core.state()))

    @staticmethod
    def set_sex(cid: int, sex: int) -> None:
        """
        更新测试角色的性别字段并写回身份表。
        Keyword arguments:
        cid -- int，目标角色编号
        sex -- int，待设置的性别数值
        Return arguments:
        None -- 无返回值
        """
        old = identity.of(cid)
        identity.put(
            identity.Identity(cid, name=old.name, sex=sex, adv=old.adv)
        )

    @staticmethod
    def feel_ids(hidden: set[int]) -> list[int]:
        """
        获取类型 0 状态分区中排除指定编号后的状态编号列表。
        Keyword arguments:
        hidden -- set[int]，需要排除的状态编号集合
        Return arguments:
        list[int] -- 过滤后的状态编号列表
        """
        ids = game_config.config_character_state_type_data[0]
        return [i for i in ids if i not in hidden]

    @staticmethod
    def names(bars: list[svc.StatusBar]) -> list[str]:
        """
        从状态条列表提取各条目的状态名称前缀。
        Keyword arguments:
        bars -- list[svc.StatusBar]，状态条对象列表
        Return arguments:
        list[str] -- 按原顺序提取的状态名称列表
        """
        return [bar.text.split("lv")[0] for bar in bars]


class StatusSectionsTest(InfoCase):
    """角色状态条分区、性别过滤与寸止样式测试。"""

    def test_female_feel_section_lists_lubrication_last(self) -> None:
        """验证女性角色类型 0 分区隐藏编号 3 并将编号 8 排在末尾。"""
        sections = dict(svc.status_sections(NPC))
        state = game_config.config_character_state
        feel = game_config.config_character_state_type[0].name
        other = game_config.config_character_state_type[1].name
        self.assertEqual(
            self.names(sections[feel]),
            [state[i].name for i in self.feel_ids({3})] + [state[8].name],
        )
        self.assertNotIn(state[8].name, self.names(sections[other]))

    def test_male_hides_female_parts(self) -> None:
        """验证男性角色隐藏编号 2、4、7 状态条并将编号 8 排在末尾。"""
        self.set_sex(NPC, 0)
        feel = svc.status_sections(NPC)[0][1]
        state = game_config.config_character_state
        self.assertEqual(
            self.names(feel),
            [state[i].name for i in self.feel_ids({2, 4, 7})] + [state[8].name],
        )

    def test_level_and_edge_count_colours(self) -> None:
        """验证状态等级、上限值、寸止样式与提示文本追加规则。"""
        status.set(NPC, 1, 999999)
        with h_state.editing(NPC) as hs:
            hs.orgasm_edge_count = {0: 1, 1: 1, 2: 3, 4: 4}
            hs.time_stop_orgasm_count = {1: 1}
        bars = dict(
            zip(
                (0, 1, 2, 4, 5), svc.status_sections(NPC)[0][1][:5], strict=True
            )
        )
        self.assertEqual(
            [bars[i].style for i in (0, 1, 2, 4, 5)],
            ["hot_pink", "deep_pink", "red", "levelex", ""],
        )
        self.assertTrue(bars[4].tooltip.endswith("(绝顶寸止4次)"))
        self.assertTrue(bars[0].tooltip.endswith("(绝顶寸止1次)"))
        self.assertEqual(
            bars[5].tooltip, game_config.config_character_state[5].info
        )
        level = attr_calculation.get_status_level(999999)
        self.assertEqual(bars[1].value, 999999)
        self.assertEqual(bars[1].text.split("lv")[1], str(level))
        self.assertEqual(
            bars[1].max_value,
            game_config.config_character_state_level[level].max_value,
        )
        self.assertEqual((bars[0].text[-3:], bars[0].max_value), ("lv0", 100))


class AbilitySectionsTest(InfoCase):
    """角色能力分区过滤与换行标记测试。"""

    def test_player_skips_mark_and_last_types(self) -> None:
        """验证主角跳过能力分类 2 与 6 而干员包含这些分类。"""
        player = [kind for kind, _ in svc.ability_sections(0)]
        npc = [kind for kind, _ in svc.ability_sections(NPC)]
        self.assertEqual(player, [kind for kind in npc if kind not in {2, 6}])
        self.assertIn(2, npc)

    def test_rows_follow_sex_and_breaks(self) -> None:
        """验证能力过滤、名称对齐、换行标记与性别隐藏规则。"""
        abilities.ability(NPC)[2] = 5
        rows = {
            row.label.strip(): row
            for _, part in svc.ability_sections(NPC)
            for row in part
        }
        config = game_config.config_ability
        self.assertNotIn(config[16].name, rows)
        self.assertEqual(rows[config[2].name].level, 5)
        self.assertEqual(
            rows[config[2].name].label,
            "  " + attr_calculation.pad_display_width(config[2].name, 10),
        )
        self.assertEqual(
            sorted(name for name, row in rows.items() if row.break_before),
            sorted([config[48].name, config[101].name]),
        )
        self.set_sex(NPC, 0)
        male = [
            row.label.strip()
            for _, part in svc.ability_sections(NPC)
            for row in part
        ]
        self.assertNotIn(config[2].name, male)


class CountTextsTest(InfoCase):
    """角色经验与宝珠列表文本测试。"""

    def test_experience_lists_positive_values(self) -> None:
        """验证经验文本仅列出正值并在男性角色上跳过隐藏编号。"""
        names = game_config.config_experience
        abilities.experience(NPC)[0] = 3
        abilities.experience(NPC)[2] = 4
        self.assertEqual(
            svc.experience_texts(NPC),
            [f" {names[0].name}:3", f" {names[2].name}:4"],
        )
        self.set_sex(NPC, 0)
        self.assertEqual(svc.experience_texts(NPC), [f" {names[0].name}:3"])

    def test_juel_lists_every_kind(self) -> None:
        """验证宝珠文本含零值并在男性角色上跳过编号 2、4、7。"""
        abilities.juel(NPC)[1] = 25
        del abilities.juel(NPC)[0]
        names = game_config.config_juel
        texts = svc.juel_texts(NPC)
        self.assertEqual(len(texts), len(names))
        self.assertIn(f" {names[1].name}:25", texts)
        self.assertIn(f" {names[0].name}:0", texts)
        self.set_sex(NPC, 0)
        self.assertEqual(
            svc.juel_texts(NPC),
            [
                t
                for i, t in zip(names, texts, strict=True)
                if i not in {2, 4, 7}
            ],
        )


class TalentTextsTest(InfoCase):
    """角色基础信息行与素质分类文本测试。"""

    def test_heading_and_owned_talents(self) -> None:
        """验证四行基础信息格式与分类素质标题及已拥有项。"""
        heading = svc.talent_heading(NPC)
        self.assertEqual(len(heading), 4)
        self.assertTrue(all(line.endswith("]\n") for line in heading))
        race = game_config.config_race[identity.of(NPC).race].name
        self.assertEqual(heading[1], f" 种族    ：[{race}]\n")
        sections = svc.talent_sections(NPC)
        kinds = game_config.config_talent_type
        order = list(game_config.config_talent_type_data)
        labels = dict(zip(order, [label for label, _ in sections], strict=True))
        other = next(kind for kind in order if kind != 0)
        self.assertEqual(labels[0], f" {kinds[0].name}  ：")
        self.assertEqual(labels[other], f" {kinds[other].name}：")
        owned = [text for _, talents in sections for text, _ in talents]
        self.assertEqual(owned, [f"[{game_config.config_talent[121].name}] "])


class DailyAndVisitorTest(InfoCase):
    """角色日程与访客信息文本测试。"""

    def plans(self) -> list[str]:
        """
        为测试干员设置三项娱乐计划并返回对应名称列表。
        Keyword arguments:
        无
        Return arguments:
        list[str] -- 三项娱乐计划的展示名称列表
        """
        plans = list(game_config.config_entertainment)[1:4]
        chara_life.entertainment_type.set(NPC, plans)
        return [game_config.config_entertainment[i].name for i in plans]

    def test_daily_text_by_work_day(self) -> None:
        """验证未分配工作与工作日有工作时的日程文本及房间行。"""
        plans = self.plans()
        room = chara_life.dormitory(NPC).split(os.sep)[-1]
        activity.update_behavior(NPC, start_time=MONDAY)
        free = svc.daily_text(NPC)
        self.assertIn(
            f" 今日上午：{plans[0]}    今日下午：{plans[1]}    今日晚上：{plans[2]}",
            free,
        )
        self.assertTrue(free.endswith(f"\n居住房间：{room}"))
        work = next(i for i in game_config.config_work_type if i)
        chara_life.work_type.set(NPC, work)
        busy = svc.daily_text(NPC)
        self.assertTrue(
            busy.startswith(
                f"当前工作：{game_config.config_work_type[work].name}     "
            )
        )
        self.assertIn("今日下午：工作    今日晚上：" + plans[2], busy)

    def test_visitor_text(self) -> None:
        """验证访客留下意愿、离开时间与居住房间文本拼接。"""
        leave = datetime.datetime(2025, 6, 2)
        visitor.arrive(NPC, leave)
        modes.set_debug(True)
        text = svc.visitor_text(NPC)
        attitude = game_config.config_visitor_stay_attitude
        self.assertTrue(
            text.startswith(f"留下意愿：{list(attitude.values())[-1].name}")
        )
        self.assertIn(game_time.get_date_until_day(leave), text)
        room = chara_life.dormitory(NPC).split(os.sep)[-1]
        self.assertTrue(text.endswith(f"居住房间：{room}"))


class TokenTest(InfoCase):
    """玩家能力分组、信物展示、切换与读档修补测试。"""

    def test_arts_groups_list_owned_talents(self) -> None:
        """验证五个能力系别顺序及已拥有素质的说明拼接。"""
        abilities.talent(0)[331] = 1
        groups = pas.arts_groups(0)
        self.assertEqual(
            [name for name, _ in groups],
            ["视觉系", "触觉系", "激素系", "催眠系", "时间系"],
        )
        talent = game_config.config_talent[331]
        self.assertEqual(groups[3][1], f"  {talent.name}：{talent.info}\n")
        self.assertEqual(groups[0][1], "")

    def test_equip_texts_and_choices(self) -> None:
        """验证已装备信物文本、标题计数、编号补零与可选状态。"""
        player_collection.put("token_list", {NPC: True, OTHER: False})
        player_collection.set_eqip_token(1, [0, NPC])
        text = pas.equipped_token_text()
        self.assertIn("  当前最大可装备数量：1\n", text)
        self.assertTrue(text.endswith("  当前装备的信物：\n  干员甲：\n"))
        self.assertIn("2/1", pas.token_heading())
        self.assertEqual(
            pas.token_choices(),
            [pas.TokenChoice(NPC, "[0007]干员甲：", True, True)],
        )
        player_collection.put("token_list", {NPC: True, OTHER: True})
        player_collection.set_eqip_token(1, [NPC])
        choices = {c.character_id: c for c in pas.token_choices()}
        self.assertFalse(choices[OTHER].selectable)
        self.assertTrue(choices[NPC].selectable)
        self.assertEqual(choices[OTHER].text, "[0012]干员乙：")

    def test_toggle_and_repair(self) -> None:
        """验证信物装备切换以及异常初始值 [0, [0]] 的读档修补。"""
        player_collection.set_eqip_token(2, [NPC])
        pas.toggle_token(OTHER)
        self.assertEqual(player_collection.get("eqip_token"), [2, [NPC, OTHER]])
        pas.toggle_token(NPC)
        self.assertEqual(player_collection.get("eqip_token"), [2, [OTHER]])
        player_collection.put("eqip_token", [0, [0]])
        pas.repair_eqip_token()
        self.assertEqual(player_collection.get("eqip_token"), [1, []])
        player_collection.put("eqip_token", [0, [3]])
        pas.repair_eqip_token()
        self.assertEqual(player_collection.get("eqip_token"), [0, [3]])


class SceneWalkTest(InfoCase):
    """同场景其他角色查询与上下循环步进测试。"""

    def test_previous_and_next(self) -> None:
        """验证上下切换在列表两端、主角、空列表与外部编号上的结果。"""
        others = [4, 6, 9]
        self.assertEqual(
            [svc.previous_in_scene(c, others) for c in (0, 4, 6, 5)],
            [9, 0, 4, 5],
        )
        self.assertEqual(
            [svc.next_in_scene(c, others) for c in (0, 4, 9, 5)],
            [4, 6, 0, 5],
        )
        self.assertEqual(
            (svc.previous_in_scene(0, []), svc.next_in_scene(0, [])), (0, 0)
        )

    def test_scene_others_skip_player(self) -> None:
        """验证 scene_others 排除主角并仅返回同场景角色。"""
        self.assertEqual(svc.scene_others(), [NPC, OTHER])
        activity.set_position(OTHER, ["测试", "别处"])
        self.assertEqual(svc.scene_others(), [NPC])


class UiFreeRunTest(FastTestCase):
    """角色信息服务无界面子进程隔离测试。"""

    child: ChildRun
    out: dict
    error: str

    @classmethod
    def setUpClass(cls) -> None:
        """在拦截界面与结算导入的子进程中执行服务脚本并收集结果。"""
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])
        cls.out = cls.child.payload

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程运行无报错且未加载或尝试导入受限模块。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_child_results(self) -> None:
        """验证子进程内服务各主要入口的返回结果符合预期。"""
        out = self.out
        self.assertEqual(out["repaired"], [1, []])
        feel = len(InfoCase.feel_ids({3}))
        self.assertEqual(out["status"][0][1], ["deep_pink"] + [""] * feel)
        self.assertEqual(out["experience"][0].split(":")[1], "4")
        self.assertEqual(out["juel"], len(game_config.config_juel) - 3)
        self.assertEqual(
            (out["heading"], out["daily"], out["visitor"]), (4, 1, 3)
        )
        self.assertEqual(out["arts"], [1, 0, 0, 0, 0])
        self.assertEqual((out["equipped"], out["heading_token"]), (1, 1))
        self.assertEqual(out["choices"], [[1, True, True], [2, False, False]])
        self.assertEqual(out["others"], [1, 2])
        self.assertEqual(out["walk"], [2, 0])
        kinds = game_config.config_ability_type_data
        self.assertEqual(
            len(out["ability"]), len([k for k in kinds if k not in {2, 6}])
        )
        self.assertEqual(
            out["talent"], len(game_config.config_talent_type_data)
        )
