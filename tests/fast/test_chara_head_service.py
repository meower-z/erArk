"""
角色信息头部服务测试
====================
覆盖状态标识（status_tag_service）、上课提示与课程文本（class_tip_service）以及头部文本与快捷用药判定（chara_head_service）。
同时验证面板状态列表转换、快捷用药按钮以及三个服务的无界面导入边界。
"""

import datetime
import json
import subprocess
import sys
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, chara_profile
from Script.Modules.domains import flags, h_meters
from Script.Modules.domains import h_state, hypnosis, inventory, needs
from Script.Modules.domains import relations
from Script.Modules.gameplay_resolution import chara_head_service as head
from Script.Modules.gameplay_resolution import class_tip_service as tips
from Script.Modules.gameplay_resolution import hypnosis_service
from Script.Modules.gameplay_resolution import status_tag_service as tags
from Script.Modules.gameplay_resolution import working
from Script.System.Education_System import education_constant as edu
from Script.UI.Panel import character_info_head as panel
from tests.chara_activity import behave
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL.ImageTk")
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, datetime, io, json
from Script.Config import normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
from Script.Config import game_config
with contextlib.redirect_stdout(io.StringIO()):
    game_config.init()
from Script.Core import constant
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, activity, flags
from Script.Modules.domains import h_meters, h_state, hypnosis, identity
from Script.Modules.domains import inventory, needs, relations
from Script.Modules.gameplay_resolution import chara_head_service
from Script.Modules.gameplay_resolution import class_tip_service
from Script.Modules.gameplay_resolution import status_tag_service, working
from Script.System.Education_System import education_constant as edu
from types import MappingProxyType
start = game_time.minutes(game_time.to_game_time(datetime.datetime(2020, 12, 22, 10)))
core.reset_state(core.GameState(start, MappingProxyType({}), MappingProxyType({})))
setting = normal_config.system_setting.draw_setting
out = {"tags": [], "tips": [], "heads": [], "drugs": [], "courses": []}
with contextlib.redirect_stdout(io.StringIO()), working.based_on(core.state()):
    for cid in (0, 1, 2):
        identity.put(identity.Identity(cid, name="C%d" % cid, sex=1))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        relations.favorability.set(cid, {0: 1234 * cid})
        relations.trust.set(cid, 20.5 * cid)
        needs.set(cid, hunger=240, urine=240, tired=170, drunk=300)
        flags.set(cid, is_follow=1, tired=1, unconscious_h=4, vistor=1,
            bagging_chara_id=2, imprisonment=1, hidden_sex_mode=4,
            exhibitionism_sex_mode=1)
        hypnosis.set(cid, hypnosis_degree=50, blockhead=1,
            roleplay=tuple(sorted(game_config.config_roleplay)[:2]))
        h_state.set(cid, orgasm_edge=1, npc_active_h=1)
        action_info.set(cid, "sleep_disturbed_end_time",
            game_time.now() + datetime.timedelta(minutes=5))
    abilities.ability(0)[30] = 1
    h_meters.set(0, eja=700)
    for item_id in (0, 1, 3):
        inventory.set_item(0, item_id, 0)
    inventory.set_item(0, 2, 1)
    inventory.set_item(0, 11, 1)
    for item_id in (0, 1, 2, 3, 11):
        inventory.set_item(1, item_id, 0)
        inventory.set_item(2, item_id, 0)
    behaviors = (constant.Behavior.TEACH, constant.Behavior.ATTENT_CLASS,
        constant.Behavior.SELF_STUDY, constant.Behavior.SLEEP)
    for mode in (0, 1, 2):
        setting[3] = mode
        setting[4] = mode
        setting[17] = mode % 2
        for cid, behavior in zip((0, 1, 2), behaviors[mode:]):
            activity.update_behavior(cid, behavior_id=behavior,
                start_time=game_time.now().replace(hour=12))
            out["tags"].append([t.text for t in status_tag_service.status_tags(cid)])
            out["tips"].append(class_tip_service.get_now_class_tip(cid))
            out["heads"].append(chara_head_service.head_message(cid))
            out["drugs"].append(chara_head_service.quick_drugs(cid))
    for course_type in sorted(edu.COURSE_TYPE_NAME):
        target = "T"
        if course_type == edu.COURSE_TYPE_INTEREST:
            target = sorted(game_config.config_entertainment)[0]
        elif course_type == edu.COURSE_TYPE_INTERN:
            target = sorted(game_config.config_work_type)[0]
        out["courses"].append(class_tip_service.get_course_text({
            "course_type": course_type, "ability_id": 1,
            "classroom": "R", "target": target}))
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的子进程中调用三个头部服务的公开函数并输出结果与已加载受限模块列表的脚本。 """


class HeadCase(FastTestCase):
    """头部服务测试基类，初始化测试角色、临时状态缓冲与默认绘制设置。"""

    def setUp(self) -> None:
        """创建玩家 0（博士）与角色 1（甲）、角色 2（乙），进入临时状态缓冲并覆写绘制设置 3、4、17。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.enterContext(working.based_on(core.state()))
        self.setting = normal_config.system_setting.draw_setting
        self.enterContext(mock.patch.dict(self.setting, {3: 0, 4: 0, 17: 1}))

    def texts(self, cid: int) -> list[str]:
        """返回指定角色全部非空状态标识的文本列表。"""
        return [tag.text for tag in tags.status_tags(cid) if tag.text]

    def find(self, cid: int, prefix: str) -> tags.StatusTag:
        """断言指定角色恰有一条文本以 prefix 开头的状态标识并返回该项。"""
        found = [
            tag for tag in tags.status_tags(cid) if tag.text.startswith(prefix)
        ]
        self.assertEqual(len(found), 1, [t.text for t in found])
        return found[0]

    def at_hour(self, cid: int, hour: int) -> None:
        """将指定角色当前行为的开始时间调整为当天 hour 点。"""
        behave(cid, start_time=game_time.now().replace(hour=hour))


class NeedTagTest(HeadCase):
    """饥饿与尿意状态标识的饭点及绘制设置规则测试。"""

    def test_npc_hunger_only_at_meal_hours(self) -> None:
        """验证非玩家角色在 12 点显示 <饿> 而在 10 点隐藏，且 10 点时仍保留饥饿悬停提示。"""
        needs.set(1, hunger=240)
        self.at_hour(1, 12)
        self.assertIn(" <饿>", self.texts(1))
        self.at_hour(1, 10)
        self.assertNotIn(" <饿>", self.texts(1))
        self.assertEqual(
            tags.status_tags(1)[3].tooltip, "肚子饿了，想要吃点东西"
        )

    def test_player_hunger_and_urine_follow_setting(self) -> None:
        """
        验证玩家在 10 点按绘制设置 17 显示或隐藏 <饿> 与 <尿>（缺省时两者均显示）。
        同时验证角色 1 的 <尿> 在设置 17 为 0 时仍显示。
        """
        for cid in (0, 1):
            needs.set(cid, hunger=240, urine=240)
            self.at_hour(cid, 10)
        self.assertEqual(
            [t for t in self.texts(0) if t in (" <饿>", " <尿>")],
            [" <饿>", " <尿>"],
        )
        self.setting[17] = 0
        self.assertNotIn(" <饿>", self.texts(0))
        self.assertNotIn(" <尿>", self.texts(0))
        self.assertIn(" <尿>", self.texts(1))
        del self.setting[17]
        self.assertIn(" <饿>", self.texts(0))
        self.assertIn(" <尿>", self.texts(0))


class HypnosisTagTest(HeadCase):
    """催眠状态标识的绘制设置 4 规则与后缀拼接测试。"""

    def test_degree_only_shown_in_mode_2(self) -> None:
        """验证无催眠状态时设置 4 为 0 与 1 不显示催眠标识，为 2 时显示 <催眠(12.3%)> 与对应催眠度颜色。"""
        hypnosis.set(1, hypnosis_degree=12.34)
        for mode in (0, 1):
            self.setting[4] = mode
            self.assertFalse(any(t.startswith(" <催眠") for t in self.texts(1)))
        self.setting[4] = 2
        tag = self.find(1, " <催眠")
        self.assertEqual(tag.text, " <催眠(12.3%)>")
        self.assertEqual(
            tag.style, hypnosis_service.get_hypnosis_degree_color(12.34)
        )

    def test_hypnosis_type_and_roleplay_suffix(self) -> None:
        """验证催眠状态下设置 4 为 1 时显示类型名、扮演对象名与子类型 12 提示，设置为 0 时隐藏该标识。"""
        roles = sorted(game_config.config_roleplay)[:2]
        hypnosis.set(1, hypnosis_degree=30, roleplay=tuple(roles))
        flags.set(1, unconscious_h=5)
        self.setting[4] = 1
        names = "".join(
            "-" + game_config.config_roleplay[r].name for r in roles
        )
        tag = self.find(1, " <催眠")
        self.assertEqual(
            tag.text,
            f" <催眠:{game_config.config_hypnosis_type[2].name}(扮演{names})>",
        )
        self.assertEqual(
            tag.tooltip, game_config.config_hypnosis_sub_type[12].introduce
        )
        self.setting[4] = 0
        self.assertFalse(any(t.startswith(" <催眠") for t in self.texts(1)))


class HStateTagTest(HeadCase):
    """寸止、隐奸、携袋、访客与睡眠打断类状态标识测试。"""

    def test_orgasm_edge_margin_bands(self) -> None:
        """验证未置寸止标志时不显示寸止标识，置位后按余量三档分别输出 <寸止>、<寸止!>、<寸止!!> 及对应样式。"""
        abilities.ability(0)[30] = 2
        self.assertFalse(any("寸止" in t for t in self.texts(1)))
        h_state.set(1, orgasm_edge=1)
        expected = [
            ({0: 1, 1: 1, 2: 1}, " <寸止>", "hot_pink"),
            ({0: 2, 1: 1, 2: 1}, " <寸止!>", "red"),
            ({0: 2, 1: 1, 2: 1, 3: 1}, " <寸止!!>", "levelex"),
        ]
        for counts, text, style in expected:
            with h_state.editing(1) as hs:
                hs.orgasm_edge_count.clear()
                hs.orgasm_edge_count.update(counts)
            tag = self.find(1, " <寸止")
            self.assertEqual((tag.text, tag.style), (text, style))

    def test_hidden_sex_mode_per_side(self) -> None:
        """
        验证玩家在 hidden_sex_mode 为 3 或 4 时显示 <隐>（为 2 时不显示），非玩家角色在 2 或 4 时显示（为 3 时不显示）。
        """
        cases = [(0, 3, True), (0, 2, False), (1, 2, True), (1, 3, False)]
        cases += [(0, 4, True), (1, 4, True)]
        for cid, mode, shown in cases:
            flags.set(cid, hidden_sex_mode=mode)
            self.assertEqual(" <隐>" in self.texts(cid), shown, (cid, mode))

    def test_bag_and_visitor(self) -> None:
        """验证携袋标识包含被装袋角色姓名，访客标识在 vistor 为 1 时显示而为 2 时不显示。"""
        flags.set(0, bagging_chara_id=2)
        self.assertIn(" <携袋:乙>", self.texts(0))
        flags.set(1, vistor=2)
        self.assertNotIn(" <访>", self.texts(1))
        flags.set(1, vistor=1)
        self.assertIn(" <访>", self.texts(1))

    def test_disturbed_sleep_minutes_and_pretend(self) -> None:
        """
        验证非玩家角色被吵醒时按剩余 1 分钟与 10 分钟输出 warning 样式提示。
        同时设置装睡时显示 <装睡> 且玩家不显示 <被吵醒>。
        """
        for cid in (0, 1):
            action_info.set(
                cid,
                "sleep_disturbed_end_time",
                game_time.now() + datetime.timedelta(minutes=1),
            )
        tag = self.find(1, " <被吵醒>")
        self.assertEqual(
            (tag.tooltip, tag.style),
            ("刚被吵醒，还需1分钟才会重新想睡", "warning"),
        )
        action_info.set(
            1,
            "sleep_disturbed_end_time",
            game_time.now() + datetime.timedelta(minutes=10),
        )
        self.assertEqual(
            self.find(1, " <被吵醒>").tooltip,
            "刚被吵醒，还需10分钟才会重新想睡",
        )
        self.assertNotIn(" <被吵醒>", self.texts(0))
        h_state.set(1, pretend_sleep=True)
        self.assertIn(" <装睡>", self.texts(1))
        self.assertNotIn(" <被吵醒>", self.texts(1))


class ClassTipTest(HeadCase):
    """上课提示与课程文本格式化测试。"""

    def test_behavior_without_schedule(self) -> None:
        """验证无课表时授课、听课与自习行为返回对应提示并生成 light_steel_blue 样式的 <课> 标识，发呆行为返回 None。"""
        cases = [
            (constant.Behavior.TEACH, "授课中"),
            (constant.Behavior.ATTENT_CLASS, "上课中"),
            (constant.Behavior.SELF_STUDY, "自习中（日程安排，此刻没课）"),
        ]
        for behavior, tip in cases:
            behave(1, behavior)
            self.assertEqual(tips.get_now_class_tip(1), (False, tip))
            tag = self.find(1, " <课>")
            self.assertEqual(
                (tag.style, tag.tooltip), ("light_steel_blue", tip)
            )
        behave(1, constant.Behavior.SHARE_BLANKLY)
        self.assertIsNone(tips.get_now_class_tip(1))
        self.assertNotIn(" <课>", self.texts(1))

    def test_course_text_by_type(self) -> None:
        """验证班级类课程按能力编号是否大于 0 输出含科目或不含科目文本，体育、兴趣与实习课按目标格式化。"""
        names = edu.COURSE_TYPE_NAME
        ability_id = sorted(game_config.config_ability)[1]
        classroom_type = sorted(edu.CLASSROOM_COURSE_TYPE_SET)[0]
        ability = game_config.config_ability[ability_id].name
        base = {"classroom": "一号教室", "target": "木桩房"}
        self.assertEqual(
            tips.get_course_text(
                {
                    **base,
                    "course_type": classroom_type,
                    "ability_id": ability_id,
                }
            ),
            f"{names[classroom_type]}·{ability}｜一号教室",
        )
        self.assertEqual(
            tips.get_course_text(
                {**base, "course_type": classroom_type, "ability_id": 0}
            ),
            f"{names[classroom_type]}｜一号教室",
        )
        ent = sorted(game_config.config_entertainment)[0]
        work = sorted(game_config.config_work_type)[0]
        cases = [
            (edu.COURSE_TYPE_PE, "木桩房", "木桩房"),
            (
                edu.COURSE_TYPE_INTEREST,
                ent,
                game_config.config_entertainment[ent].name,
            ),
            (
                edu.COURSE_TYPE_INTERN,
                work,
                game_config.config_work_type[work].name,
            ),
        ]
        for course_type, target, shown in cases:
            course = {"course_type": course_type, "target": target}
            self.assertEqual(
                tips.get_course_text(course), f"{names[course_type]}·{shown}"
            )


class HeadMessageTest(HeadCase):
    """头部标题文本、快捷用药按钮与状态列表转换测试。"""

    def test_npc_favorability_and_trust_by_setting(self) -> None:
        """验证非玩家角色头部文本在设置 3 为 0、1、2 时分别输出空白、等级以及数值加等级格式的好感度与信赖度。"""
        relations.favorability.set(1, {0: 1234})
        relations.trust.set(1, 56.78)
        fav = attr_calculation.judge_grade(
            attr_calculation.get_favorability_level(1234)[0]
        )
        trust = attr_calculation.judge_grade(
            attr_calculation.get_trust_level(56.78)[0]
        )
        expected = {
            0: "甲 ",
            1: f"甲 好感度:{fav}，信赖度:{trust}",
            2: f"甲 好感度:1234({fav})，信赖度:56.8%({trust})",
        }
        for mode, message in expected.items():
            self.setting[3] = mode
            self.assertEqual(head.head_message(1), message)

    def test_player_ejaculation_bands(self) -> None:
        """验证玩家头部文本在射精欲为 0、300、301、900、901 时分别拼接空串及低、中、高、极四档标识。"""
        cases = [
            (0, ""),
            (300, " <射精欲:低>"),
            (301, " <射精欲:中>"),
            (900, " <射精欲:高>"),
            (901, " <射精欲:极>"),
        ]
        for eja, suffix in cases:
            h_meters.set(0, eja=eja)
            self.assertEqual(
                head.head_message(0),
                "博士" + chara_profile.nick_name(0) + suffix,
            )

    def test_panel_quick_drug_buttons(self) -> None:
        """验证玩家持有道具 3 与道具 11 时的快捷按钮数量及 quick_drugs 返回值，以及非玩家角色无快捷按钮。"""
        needs.set(0, sanity_max=100, sanity=50)
        h_meters.set(0, semen_max=100)
        for cid in (0, 1):
            for item_id in (0, 1, 2, 3, 11):
                inventory.set_item(cid, item_id, 0)
        self.assertEqual(panel.CharacterInfoHead(0, 120).return_list, [])
        inventory.set_item(0, 3, 1)
        self.assertEqual(len(panel.CharacterInfoHead(0, 120).return_list), 1)
        inventory.set_item(0, 11, 1)
        self.assertEqual(len(panel.CharacterInfoHead(0, 120).return_list), 2)
        self.assertEqual(head.quick_drugs(0), (True, True))
        inventory.set_item(0, 3, 0)
        self.assertEqual(head.quick_drugs(0), (False, True))
        self.assertEqual(panel.CharacterInfoHead(1, 120).return_list, [])

    def test_status_list_adapter_mirrors_tags(self) -> None:
        """验证 get_character_status_list 逐项复制 status_tags 的文本、样式与悬停提示并返回一致文本列表。"""
        flags.set(1, is_follow=1, imprisonment=1)
        draws, texts = panel.get_character_status_list(1)
        expected = tags.status_tags(1)
        self.assertEqual(
            [(d.text, d.style, d.tooltip) for d in draws],
            [(t.text, t.style, t.tooltip) for t in expected],
        )
        self.assertEqual(texts, [t.text for t in expected])
        self.assertEqual(
            (draws[0].text, draws[0].style), (" <跟>", "spring_green")
        )


class BackendIsolationTest(FastTestCase):
    """三个头部服务无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """在拦截界面、结算与窗口模块的子进程中按三档绘制设置运行三个头部服务接口，验证输出正确且未加载受限模块。"""
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
        roles = sorted(game_config.config_roleplay)[:2]
        hypnosis_text = (
            f" <催眠(50%):{game_config.config_hypnosis_type[1].name}(木头人)(扮演"
            + "".join("-" + game_config.config_roleplay[r].name for r in roles)
            + ")>"
        )
        self.assertEqual(len(out["tags"]), 8)
        self.assertTrue(all(len(row) == 18 for row in out["tags"]))
        self.assertEqual(out["tags"][0][3:5], ["", ""])
        self.assertEqual(out["tags"][1][3:5], [" <饿>", " <尿>"])
        self.assertEqual(out["tags"][0][8], "")
        self.assertEqual(out["tags"][6][8], hypnosis_text)
        self.assertEqual(out["tips"][0], [False, "授课中"])
        self.assertTrue(out["tips"][1][1].endswith("｜授课：C0"))
        self.assertEqual(
            out["tips"][2], [False, "自习中（日程安排，此刻没课）"]
        )
        fav = attr_calculation.judge_grade(
            attr_calculation.get_favorability_level(1234)[0]
        )
        trust = attr_calculation.judge_grade(
            attr_calculation.get_trust_level(20.5)[0]
        )
        self.assertEqual(out["heads"][:2], ["C0 <射精欲:高>", "C1 "])
        self.assertEqual(
            out["heads"][7], f"C1 好感度:1234({fav})，信赖度:20.5%({trust})"
        )
        self.assertEqual(
            out["drugs"],
            [[True, True], [False, False], [False, False]] * 2
            + [[True, True], [False, False]],
        )
        names = edu.COURSE_TYPE_NAME
        ent = sorted(game_config.config_entertainment)[0]
        work = sorted(game_config.config_work_type)[0]
        self.assertEqual(
            out["courses"][-3:],
            [
                f"{names[edu.COURSE_TYPE_PE]}·T",
                f"{names[edu.COURSE_TYPE_INTEREST]}·"
                + game_config.config_entertainment[ent].name,
                f"{names[edu.COURSE_TYPE_INTERN]}·"
                + game_config.config_work_type[work].name,
            ],
        )
