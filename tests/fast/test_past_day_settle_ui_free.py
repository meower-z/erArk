"""
跨天结算无界面子进程与导入边界测试
==================================
本模块在三种标准流编码下启动无界面子进程，放行 Script.Settle 并保留其余默认拦截项。
子进程分别构造周日与周一状态，并调用 past_day_settle.update_new_day 完成跨天结算。
子进程用例验证运行期间未触碰受拦截模块，并核对两天结算的提示、刷出事件、访客入编与食物数量。
导入边界用例通过语法树检查 Script/Settle/past_day_settle.py 不含禁用界面或输入输出导入。
"""

import os
from unittest import mock

from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.ui_free_subprocess import BLOCKED, ChildRun, run_ui_free

SOURCE = "Script/Settle/past_day_settle.py"
"""待检查导入边界的跨天结算源码仓库相对路径。"""
ENCODINGS = ("cp1252", "gbk", "utf-16")
"""setUpClass 启动子进程时依次设置的 PYTHONIOENCODING 编码元组。"""
NEW_DAYS = """
import datetime
from unittest import mock
from Script.Config import game_config, map_config, normal_config
from Script.Core import game_type
from Script.Design import attr_calculation, game_time, map_handle
from Script.Modules.domains import chara_life, country, facility, identity
from Script.Modules.domains import inventory, location, npc_template
from Script.Modules.domains import physical_exam, relations, roster, visitor
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Settle import past_day_settle
from Script.System.Cooking_System import cooking
from Script.System.Education_System import semester_handle
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
events = []
ui_hooks.on_notice(lambda text, **options: events.append([text, options]))
ui_hooks.on_flush(lambda: events.append("flush"))
opened = game_config.config_facility_open
rooms = sorted(cid for cid in opened if 2000 < cid < 2100)
guest = opened[min(cid for cid, row in opened.items() if row.NPC_id)].NPC_id
home = map_handle.get_map_system_path_str_for_list(DEFAULT_SCENE)
def new_day(weekday, food_setting, reports):
    day = start_time()
    while day.weekday() != weekday:
        day += datetime.timedelta(days=1)
    kernel_data.reset_clock(day, {})
    kernel_data.written(warehouse.start, {})
    kernel_data.written(country.fill)
    for cid in (0, 1, guest):
        kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", adv=cid))
        chara_abilities.zero_tables(cid)
        services = attr_calculation.get_assistant_services_zero()
        kernel_data.put(relations.assistant_services.set, cid, services)
        kernel_data.put(relations.favorability.set, cid, {0: 0})
        kernel_data.put(chara_life.dormitory.set, cid, home)
        place(cid, DEFAULT_SCENE, start_time=game_time.now())
    template = game_type.NpcTem()
    template.AdvNpc = guest
    kernel_data.written(npc_template.add, template)
    kernel_data.put(relations.birthplace.set, guest, location.country())
    exam = attr_calculation.get_physical_exam_setting_zero()
    kernel_data.put(physical_exam.set_settings, exam)
    kernel_data.set_facility_level(13, 2)
    for cid in (0, 1, 1):
        food = cooking.create_food("0", min(game_config.config_recipes))
        food.quality = 1
        kernel_data.put(inventory.put_food, cid, food)
    normal_config.system_setting.base_setting = {7: 0, 10: food_setting}
    events.clear()
    with kernel_data.writing():
        for room in rooms:
            facility.set_open(room, True)
        visitor.set_moved(True)
        roster.add(1)
        relations.assistant_character_id.set(0, 1)
        relations.assistant_services.set(1, {**services, 10: 1})
        with mock.patch.object(
            semester_handle, "settle_semester_change", return_value=reports
        ):
            past_day_settle.update_new_day()
        return {
            "weekday": game_time.now().weekday(),
            "events": list(events),
            "roster": sorted(roster.active()),
            "visitors": sorted(visitor.visitors()),
            "foods": [len(inventory.foods(0)), len(inventory.foods(1))],
        }
payload["guest"] = guest
payload["sunday"] = new_day(6, 1, [1])
payload["monday"] = new_day(0, 0, [])
"""
"""
在无界面子进程中执行的测试代码片段。
片段初始化地图并登记 ui_hooks.on_notice 与 ui_hooks.on_flush 回调以记录提示与刷出事件。
内部辅助函数 new_day 按指定星期、食物过期开关与成绩单列表重建时钟、三名测试角色、设施、国家与库存状态，
打桩 semester_handle.settle_semester_change 后调用 past_day_settle.update_new_day。
片段分别执行周日与周一两日结算，并将访客编号与两日结果写入 payload。
"""


def notice(text: str, style: str | None = None) -> list[object]:
    """
    构造一条预期的提示记录项，固定 wait 为 False 且 use_text_width 为 True。
    Keyword arguments:
    text -- str，预期的提示文本
    style -- str | None，预期的文本样式名，默认为 None
    Return arguments:
    list[object] -- 形如 [text, {"wait": False, "style": style, "use_text_width": True}] 的记录项
    """
    return [text, {"wait": False, "style": style, "use_text_width": True}]


START = notice("\n已过24点，开始结算各种数据\n\n")
"""update_new_day 开头预期发出的跨天开始提示记录项。"""


class PastDaySettleUiFreeTest(FastTestCase):
    """验证 past_day_settle.update_new_day 在无界面子进程中完成周日与周一结算的测试类。"""

    runs: dict[str, ChildRun]
    """以 PYTHONIOENCODING 编码名为键、对应无界面子进程运行结果 ChildRun 为值的映射。"""

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用父类类级准备，并在 ENCODINGS 的三种编码下分别以 boot=True 与
        blocked=BLOCKED - {"Script.Settle"} 调用 run_ui_free 执行 NEW_DAYS。
        每次运行结果按编码名存入 cls.runs。
        子进程非零退出时由 run_ui_free 抛出 RuntimeError。
        Return arguments:
        None -- 无返回值
        """
        super().setUpClass()
        cls.runs = {}
        for encoding in ENCODINGS:
            with mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}):
                cls.runs[encoding] = run_ui_free(
                    NEW_DAYS, boot=True, blocked=BLOCKED - {"Script.Settle"}
                )

    def test_touches_no_blocked_module(self) -> None:
        """
        验证各编码子进程均未加载且未尝试导入 BLOCKED - {"Script.Settle"} 中的受拦截模块。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                self.assertEqual((run.loaded, run.attempted), ([], []))

    def test_sunday_notices_and_arrival(self) -> None:
        """
        验证各编码子进程的周日结算结果：星期为 6，
        前四条事件依次为开始提示、刷出、玩家 1 个过期食物提示与金色（gold_enrod）学期成绩单提示。
        同时断言结算后在编名单为 [1, guest]、访客列表为 [guest]，且玩家与角色 1 的剩余食物数均为 0。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                day = run.payload["sunday"]
                assert isinstance(day, dict)
                guest = run.payload["guest"]
                self.assertEqual(day["weekday"], 6)
                self.assertEqual(
                    day["events"][:4],
                    [
                        START,
                        "flush",
                        notice("你持有的1个食物因过期变质而自动丢弃了\n"),
                        notice(
                            "\n【学期结束】c1的成绩单出来了，"
                            "可以用「检查成绩单」指令查看\n",
                            "gold_enrod",
                        ),
                    ],
                )
                self.assertEqual(
                    (day["roster"], day["visitors"], day["foods"]),
                    ([1, guest], [guest], [0, 0]),
                )

    def test_monday_keeps_food_when_setting_off(self) -> None:
        """
        验证各编码子进程的周一结算结果：星期为 0，前两条事件依次为开始提示与刷出。
        同时断言无食物或学期相关提示、玩家与角色 1 的食物数保持为 [1, 2]，且事件中包含每周助理轮换抽签提示。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                day = run.payload["monday"]
                assert isinstance(day, dict)
                self.assertEqual(day["weekday"], 0)
                self.assertEqual(day["events"][:2], [START, "flush"])
                own = [
                    event
                    for event in day["events"]
                    if isinstance(event, list)
                    and ("食物" in event[0] or "学期" in event[0])
                ]
                self.assertEqual((own, day["foods"]), ([], [1, 2]))
                self.assertIn(
                    "\n○本周抽签选中了c1作为c0的助理\n",
                    [event[0] for event in day["events"]],
                )


class PastDaySettleImportBoundaryTest(FastTestCase):
    """验证 Script/Settle/past_day_settle.py 源码导入边界的测试类。"""

    def test_skips_ui_imports(self) -> None:
        """
        通过 banned_imports 检查 Script/Settle/past_day_settle.py 源码，断言不含禁用界面或输入输出导入。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(
            banned_imports((ROOT / SOURCE).read_bytes(), SOURCE), []
        )
