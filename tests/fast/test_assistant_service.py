"""
助理服务测试
============
覆盖助理候选筛选、任免替换与每周抽签、服务档位切换与同居宿舍迁移、读档跟随状态修补，以及无界面子进程运行边界。
"""

import datetime
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text, save_handle
from Script.Design import game_time, map_handle
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import activity, chara_life, flags, modes
from Script.Modules.domains import relations, roster, visitor, work
from Script.Modules.gameplay_resolution import actions, assistant_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

_ = get_text._

BABY_TALENT = 101
""" 用于构造离线异常角色的婴儿素质编号（101）。 """
HOME = ["宿舍", "1区", "103"]
""" 测试同居宿舍迁移与恢复时使用的常规宿舍路径段列表。 """
SETTINGS = {
    "default": "",
    "en_US_ai_on": """
from Script.Config import normal_config
read_config = normal_config.init_normal_config
def read_config_en_us():
    read_config()
    normal_config.config_normal.language = "en_US"
normal_config.init_normal_config = read_config_en_us
""",
}
""" 无界面子进程启动前的配置前置片段映射，键为配置名，值为在 boot_backend 之前改写配置读取的代码。 """
SERVICE_RUN = """
from tests.ui_free_subprocess import boot_backend
boot_backend()
from Script.Config import map_config, normal_config
if normal_config.config_normal.language != "zh_CN":
    normal_config.ai_setting.ai_chat_setting = {key: 1 for key in range(1, 11)}
    normal_config.ai_setting.ai_chat_translator_setting = 2
map_config.init_map_data()
from Script.Core import get_text
from Script.Design import attr_calculation, map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, flags, identity, modes
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import assistant_service as svc, working
from Script.Modules.save_load import reset
from tests import chara_abilities
from tests.chara_activity import aim
payload["setting"] = [get_text.now_language, normal_config.ai_setting.ai_chat_translator_setting]
payload["repair"] = svc.repair_follow_flag in reset._repairs
home = map_handle.get_map_system_path_str_for_list(["宿舍", "1区", "103"])
room = map_handle.get_map_system_path_str_for_list(svc.COHABIT_ROOM)
with working.based_on(core.state()):
    for cid in (0, 1, 2, 3, 4):
        identity.put(identity.Identity(cid, name=str(cid), sex=1))
        relations.assistant_services.set(cid, attr_calculation.get_assistant_services_zero())
        relations.favorability.set(cid, {0: 0})
        chara_abilities.zero_tables(cid)
        roster.add(cid)
    chara_life.dormitory.set(1, home)
    chara_abilities.talent(4)[101] = 1
    aim(4, 4)
    payload["candidates"] = svc.get_assistant_candidates()
    svc.assistant_replace(1)
    payload["appointed"] = relations.assistant_character_id(0)
    svc.cycle_service(3)
    payload["rejected"] = relations.assistant_services(1)[3]
    modes.set_debug(True)
    svc.cycle_service(3)
    payload["debug"] = relations.assistant_services(1)[3]
    modes.set_debug(False)
    relations.favorability.set(1, {0: 10})
    relations.trust.set(1, 300)
    for cid in (2, 4, 5, 6, 7, 8, 10):
        svc.cycle_service(cid)
    payload["levels"] = [relations.assistant_services(1)[c] for c in (2, 4, 7, 10)]
    payload["cohabit"] = [chara_life.dormitory(1) == room, chara_life.permanent_dormitory(1) == home]
    payload["food"] = [activity.second_behavior(1, f"assistant_send_food_{i}") for i in range(4)]
    svc.assistant_replace(4)
    payload["refused"] = relations.assistant_character_id(0)
    svc.assistant_replace(2)
    payload["replaced"] = [relations.assistant_character_id(0), chara_life.dormitory(1) == home]
    svc.assistant_replace(2)
    payload["dismissed"] = relations.assistant_character_id(0)
    svc.select_random_assistant()
    payload["lottery"] = relations.assistant_character_id(0) in (1, 2, 3)
    flags.set(3, is_follow=7)
    svc.repair_follow_flag()
    payload["repaired"] = flags.get(3, "is_follow")
"""
""" 在无界面子进程中初始化后端与角色 0 至 4，依次执行助理服务五个公开函数并将结果写入 payload 的代码片段。 """

type Drawn = tuple[str, object, object, object]
""" 记录单次绘制调用的四元组类型，依次为绘制类名、文本、宽度与样式。 """


def appointed(name: str) -> str:
    """
    构造任命指定干员为助理时的预期提示文本。
    Keyword arguments:
    name -- str，目标干员名称
    Return arguments:
    str -- 经 get_text._ 翻译并填入干员名称后的任命提示文本
    """
    return _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(name)


def dismissed(name: str) -> str:
    """
    构造指定干员卸任助理时的预期提示文本。
    Keyword arguments:
    name -- str，卸任干员名称
    Return arguments:
    str -- 经 get_text._ 翻译并填入干员名称后的卸任提示文本
    """
    return _("\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n").format(
        name
    )


class AssistantCase(FastTestCase):
    """助理服务测试基类，准备测试角色、内核工作集并拦截 draw 模块绘制调用以记录输出。"""

    def setUp(self) -> None:
        """创建角色 0 至 3、进入内核工作集、挂接 ui_hooks 的 Tk 回调，并拦截 draw 模块各绘制类的 draw 方法。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(3, "干员丙")
        self.world.chara(2, "干员乙")
        self.world.chara(1, "干员甲")
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[Drawn] = []
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [callbacks.draw_divider])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [callbacks.draw_notice])
        )
        self.width = normal_config.config_normal.text_width
        self.home = map_handle.get_map_system_path_str_for_list(HOME)

    def keep(self, now: object) -> None:
        """
        记录单次绘制对象的类名、文本、宽度与样式到 self.drawn。
        Keyword arguments:
        now -- object，被拦截的绘制对象实例
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )

    def line(self) -> Drawn:
        """
        返回按当前配置文本宽度与标准样式绘制短横线分隔线的预期记录。
        Return arguments:
        Drawn -- LineDraw 对应的四元组记录
        """
        return ("LineDraw", "-", self.width, "standard")

    def wait(self, text: str) -> Drawn:
        """
        返回按当前配置文本宽度与标准样式绘制等待提示的预期记录。
        Keyword arguments:
        text -- str，预期的提示文本
        Return arguments:
        Drawn -- WaitDraw 对应的四元组记录
        """
        return ("WaitDraw", text, self.width, "standard")

    def offline(self, cid: int) -> None:
        """
        为指定角色添加婴儿素质 101 并将目标设为自身，使其进入 7 类离线异常状态。
        Keyword arguments:
        cid -- int，角色编号
        Return arguments:
        None -- 无返回值
        """
        ca.talent(cid)[BABY_TALENT] = 1
        aim(cid, cid)

    def unlock(self, cid: int, trust: int) -> None:
        """
        为指定角色设置对玩家的好感度 10 与指定信赖度，用于满足服务解锁条件。
        Keyword arguments:
        cid -- int，角色编号
        trust -- int，要设置的信赖度
        Return arguments:
        None -- 无返回值
        """
        relations.favorability.set(cid, {0: 10})
        relations.trust.set(cid, trust)

    def services(self, cid: int) -> dict[int, int]:
        """
        返回指定角色当前助理服务映射的浅拷贝字典。
        Keyword arguments:
        cid -- int，角色编号
        Return arguments:
        dict[int, int] -- 助理服务编号到档位的字典拷贝
        """
        return dict(relations.assistant_services(cid))

    def food(self, cid: int) -> list[int]:
        """
        返回指定角色送饭服务（服务 4）0 至 3 档二段行为标记的列表。
        Keyword arguments:
        cid -- int，角色编号
        Return arguments:
        list[int] -- 按 0 至 3 档顺序排列的标记值列表
        """
        return [
            activity.second_behavior(cid, f"assistant_send_food_{i}")
            for i in range(4)
        ]


class CandidatesTest(AssistantCase):
    """助理候选列表筛选规则测试。"""

    def test_candidates_skip_player_offline_warden_and_visitor(self) -> None:
        """验证在编名单包含玩家 0 时，候选列表按编号升序返回，并跳过玩家 0、离线角色、监狱长与访客。"""
        roster.add(0)
        self.world.chara(4, "访客")
        self.world.chara(5, "婴儿")
        self.offline(5)
        work.set_warden(2)
        visitor.arrive(4, game_time.now() + datetime.timedelta(days=1))
        self.assertIn(0, roster.active())
        self.assertEqual(assistant_service.get_assistant_candidates(), [1, 3])


class ReplaceTest(AssistantCase):
    """助理任命、解任、拒绝、替换与每周抽签行为测试。"""

    def test_appoint_without_assistant(self) -> None:
        """验证无当前助理时任命干员会设置助理编号、跟随状态、服务 2 与二段行为，并绘制分隔线与任命提示。"""
        assistant_service.assistant_replace(1)
        self.assertEqual(relations.assistant_character_id(0), 1)
        self.assertEqual(flags.get(1, "is_follow"), 1)
        self.assertEqual(self.services(1)[2], 1)
        self.assertEqual(activity.second_behavior(1, "chosen_as_assistant"), 1)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(appointed("干员甲"))]
        )

    def test_choosing_current_assistant_dismisses_her(self) -> None:
        """验证再次选择当前助理会解除职务、清零跟随与服务、更新二段行为，并绘制分隔线与卸任提示。"""
        assistant_service.assistant_replace(1)
        relations.assistant_services.set_item(1, 5, 2)
        self.drawn.clear()
        assistant_service.assistant_replace(1)
        self.assertEqual(relations.assistant_character_id(0), 0)
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(set(self.services(1).values()), {0})
        self.assertEqual(activity.second_behavior(1, "chosen_as_assistant"), 0)
        self.assertEqual(activity.second_behavior(1, "not_as_assistant"), 1)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(dismissed("干员甲"))]
        )

    def test_offline_character_is_not_appointed(self) -> None:
        """验证任命处于离线异常状态的角色会被拒绝、保持玩家助理编号不变，并绘制分隔线与拒绝提示。"""
        assistant_service.assistant_replace(1)
        self.offline(2)
        self.drawn.clear()
        assistant_service.assistant_replace(2)
        self.assertEqual(relations.assistant_character_id(0), 1)
        self.assertEqual(flags.get(2, "is_follow"), 0)
        refused = _("\n{0}的状态异常，无法任命为助理干员\n").format("干员乙")
        self.assertEqual(self.drawn, [self.line(), self.wait(refused)])

    def test_replace_moves_old_assistant_out_of_cohabitation(self) -> None:
        """验证替换同居中的在任助理会将其迁回登记宿舍、清零其跟随与服务，并合并绘制任命与卸任提示。"""
        assistant_service.assistant_replace(1)
        self.unlock(1, 200)
        chara_life.dormitory.set(1, self.home)
        assistant_service.cycle_service(7)
        self.drawn.clear()
        assistant_service.assistant_replace(3)
        self.assertEqual(relations.assistant_character_id(0), 3)
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(flags.get(3, "is_follow"), 1)
        self.assertEqual(chara_life.dormitory(1), self.home)
        self.assertEqual(set(self.services(1).values()), {0})
        self.assertEqual(activity.second_behavior(1, "not_as_assistant"), 1)
        self.assertEqual(
            self.drawn,
            [
                self.line(),
                self.wait(appointed("干员丙") + dismissed("干员甲")),
            ],
        )

    def test_weekly_lottery_appoints_a_candidate(self) -> None:
        """验证每周抽签从候选列表中选取角色，并依次绘制抽签提示、分隔线与任命提示。"""
        self.offline(3)
        with mock.patch.object(
            assistant_service.random, "choice", side_effect=lambda ids: ids[-1]
        ):
            assistant_service.select_random_assistant()
        self.assertEqual(relations.assistant_character_id(0), 2)
        lottery = _("\n○本周抽签选中了{0}作为{1}的助理\n").format(
            "干员乙", "博士"
        )
        self.assertEqual(
            self.drawn,
            [self.wait(lottery), self.line(), self.wait(appointed("干员乙"))],
        )


class CycleServiceTest(AssistantCase):
    """助理服务选项切换、解锁校验、二段行为与同居宿舍迁移测试。"""

    def setUp(self) -> None:
        """任命 1 号干员为当前助理并清空初始化阶段的绘制记录。"""
        super().setUp()
        assistant_service.assistant_replace(1)
        self.drawn.clear()

    def test_follow_service_toggles_and_steps_follow_state(self) -> None:
        """验证连续切换服务 2（跟随服务）会交替翻转开关布尔值，并按规则步进与归零 is_follow。"""
        flags.set(1, is_follow=3)
        seen = []
        for _round in range(5):
            assistant_service.cycle_service(2)
            seen.append((bool(self.services(1)[2]), flags.get(1, "is_follow")))
        self.assertEqual(
            seen, [(False, 4), (True, 5), (False, 0), (True, 1), (False, 0)]
        )

    def test_locked_option_shows_reason_and_resets(self) -> None:
        """验证未满足解锁条件时以 WaitDraw 默认宽度绘制失败原因、将服务档位归零且不设置开启二段行为。"""
        relations.assistant_services.set_item(1, 3, 0)
        assistant_service.cycle_service(3)
        option = game_config.config_assistant_services_option[3][0][1]
        reason = _("需要:") + _("信赖度>={0}").format(50)
        reason += _("或催眠进度>={0}").format(25.0)
        text = _("\n  ○更改失败，[{0}]{1}\n").format(option, reason + "  ")
        self.assertEqual(self.services(1)[3], 0)
        self.assertEqual(
            self.drawn,
            [("WaitDraw", text, draw.WaitDraw().width, "standard")],
        )
        self.assertEqual(activity.second_behavior(1, "support_service_on"), 0)

    def test_debug_mode_skips_unlock_check(self) -> None:
        """验证调试模式下跳过解锁校验、直接开启服务并设置开启二段行为，且不绘制提示。"""
        modes.set_debug(True)
        assistant_service.cycle_service(3)
        self.assertEqual(self.services(1)[3], 1)
        self.assertEqual(activity.second_behavior(1, "support_service_on"), 1)
        self.assertEqual(activity.second_behavior(1, "support_service_off"), 0)
        self.assertEqual(self.drawn, [])

    def test_option_service_marks_current_option(self) -> None:
        """
        验证多档位服务逐档推进时，同组二段行为标记仅保留当前档位为 1。
        解锁失败时服务档位归零，已设置的二段行为标记保持不变。
        越过末档归零后，同组二段行为标记切回 0 档。
        """
        self.unlock(1, 100)
        self.assertEqual(self.food(1), [0, 0, 0, 0])
        assistant_service.cycle_service(4)
        self.assertEqual(self.food(1), [0, 1, 0, 0])
        assistant_service.cycle_service(4)
        self.assertEqual(self.food(1), [0, 0, 1, 0])
        assistant_service.cycle_service(4)
        self.assertEqual(self.services(1)[4], 0)
        self.assertEqual(len(self.drawn), 1)
        self.assertEqual(self.food(1), [0, 0, 1, 0])
        relations.trust.set(1, 300)
        levels = []
        for _round in range(4):
            assistant_service.cycle_service(4)
            levels.append(self.services(1)[4])
        self.assertEqual(levels, [1, 2, 3, 0])
        self.assertEqual(self.food(1), [1, 0, 0, 0])

    def test_cohabitation_moves_dormitory_and_back(self) -> None:
        """验证开启服务 7（同居服务）会登记常住宿舍并迁入同居房间，关闭后会迁回登记宿舍并切换同居二段行为。"""
        self.unlock(1, 200)
        chara_life.dormitory.set(1, self.home)
        room = map_handle.get_map_system_path_str_for_list(
            assistant_service.COHABIT_ROOM
        )
        assistant_service.cycle_service(7)
        self.assertEqual(chara_life.dormitory(1), room)
        self.assertEqual(chara_life.permanent_dormitory(1), self.home)
        self.assertEqual(activity.second_behavior(1, "cohabitation_on"), 1)
        assistant_service.cycle_service(7)
        self.assertEqual(self.services(1)[7], 0)
        self.assertEqual(chara_life.dormitory(1), self.home)
        self.assertEqual(activity.second_behavior(1, "cohabitation_on"), 0)
        self.assertEqual(activity.second_behavior(1, "cohabitation_off"), 1)

    def test_weekly_rotation_sets_no_second_behavior(self) -> None:
        """验证开启服务 10（每周轮换）会更新服务档位，且不改动角色二段行为表。"""
        self.unlock(1, 0)
        before = dict(activity.second_behaviors(1))
        assistant_service.cycle_service(10)
        self.assertEqual(self.services(1)[10], 1)
        self.assertEqual(dict(activity.second_behaviors(1)), before)


class RepairFollowFlagTest(FastTestCase):
    """读档跟随状态修补钩子测试。"""

    def test_load_resets_follow_state_above_four(self) -> None:
        """验证读档流程触发修补钩子后，大于 4 的 is_follow 会归零，等于 4 的保持不变。"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        kernel_data.put(flags.set, 1, is_follow=7)
        kernel_data.put(flags.set, 2, is_follow=4)
        for module, name in (
            (save_handle, "install_save"),
            (save_handle, "exact_stats"),
            (save_handle, "repair_installed"),
        ):
            self.enterContext(mock.patch.object(module, name))
        self.enterContext(
            mock.patch.object(actions, "project", side_effect=lambda new: new)
        )
        core.load(load_order.LOAD_ORDER)
        core.reset_state(core.state(), {"cause": "load", "save": "1"})
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(flags.get(2, "is_follow"), 4)


class UiFreeRunTest(FastTestCase):
    """助理服务在屏蔽界面与结算模块的子进程中运行的边界测试。"""

    def test_service_runs_without_ui_or_settle(self) -> None:
        """
        验证默认配置与 en_US 语言并开启文本 AI 两种配置下，SERVICE_RUN 在子进程中产出相同的预期结果。
        同时验证两种配置下子进程均未加载也未尝试导入任何受拦截模块。
        """
        expected = {
            "repair": True,
            "candidates": [1, 2, 3],
            "appointed": 1,
            "rejected": 0,
            "debug": 1,
            "levels": [False, 1, 1, 1],
            "cohabit": [True, True],
            "food": [0, 1, 0, 0],
            "refused": 1,
            "replaced": [2, True],
            "dismissed": 0,
            "lottery": True,
            "repaired": 0,
        }
        settings = {"default": ["zh_CN", 0], "en_US_ai_on": ["en_US", 2]}
        for name, prelude in SETTINGS.items():
            with self.subTest(name):
                run = run_ui_free(prelude + SERVICE_RUN)
                self.assertEqual(run.payload.pop("setting"), settings[name])
                self.assertEqual(run.payload, expected)
                self.assertEqual((run.loaded, run.attempted), ([], []))
