"""
新角色上线无界面子进程测试
==========================
本模块在三种标准流编码下分别启动无界面子进程，按默认规则拦截 Script.UI 与 Script.Settle 等模块。
子进程初始化后端并构造三名测试角色后，依次执行访客抵达与招募入编以触发 get_new_character。
用例验证子进程未触碰受拦截模块，并核对两名角色上线后的返回值、角色状态、设施开放状态与提示条数。
"""

import os
from unittest import mock

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
"""setUpClass 启动子进程时依次设置的 PYTHONIOENCODING 编码元组。"""
ARRIVALS = """
import datetime
import os
from Script.Config import game_config, map_config
from Script.Design import attr_calculation, game_time, map_handle
from Script.Modules.domains import activity, chara_life, facility, flags
from Script.Modules.domains import identity, needs, recruit, relations, roster
from Script.Modules.domains import visitor, warehouse
from Script.Modules.gameplay_resolution import recruit_service, ui_hooks
from Script.Modules.gameplay_resolution import visitor_service
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
kernel_data.written(warehouse.start, {})
opened = game_config.config_facility_open
smithy = min(cid for cid, row in opened.items() if row.NPC_id)
rooms = sorted(cid for cid in opened if 2000 < cid < 2100)
home = map_handle.get_map_system_path_str_for_list(DEFAULT_SCENE)
for cid, adv in ((0, 0), (1, 1), (2, opened[smithy].NPC_id)):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", adv=adv))
    chara_abilities.zero_tables(cid)
    services = attr_calculation.get_assistant_services_zero()
    kernel_data.put(relations.assistant_services.set, cid, services)
    kernel_data.put(relations.favorability.set, cid, {0: 0})
    kernel_data.put(chara_life.dormitory.set, cid, home)
    place(cid, DEFAULT_SCENE, start_time=game_time.now())
    kernel_data.set_needs(cid, hit_max=100, hit=40, mana_max=90, mana=30)
kernel_data.set_facility_level(13, 2)
notices = []
ui_hooks.on_notice(lambda text, *args, **kwargs: notices.append(text))
with kernel_data.writing():
    for room in rooms:
        facility.set_open(room, True)
    arrived = visitor_service.settle_visitor_arrivals(1)
    recruit.set_pending({2})
    hired = recruit_service.recruit_new_chara()
    names = {opened[room].name for room in rooms}
    for cid, done in ((1, arrived), (2, hired)):
        leave = visitor.visitors().get(cid, game_time.now())
        payload[str(cid)] = {
            "done": done,
            "stay_days": (leave - game_time.now()) / datetime.timedelta(days=1),
            "vistor": flags.get(cid, "vistor"),
            "roster": roster.has(cid),
            "needs": [needs.of(cid)["hit"], needs.of(cid)["mana"]],
            "position": activity.position(cid),
            "guest_room": chara_life.dormitory(cid).split(os.sep)[-1] in names,
        }
    payload["smithy_open"] = facility.is_open(smithy)
payload["notices"] = len(notices)
"""
"""
在无界面子进程中执行的测试代码片段。
片段初始化地图、时钟、仓库与三名测试角色，并将设施 13 设为 2 级。
片段注册 ui_hooks.on_notice 回调，在内核写入块内开启编号位于 2001 至 2099 的配置客房，
并依次触发角色 1 访客抵达与角色 2 招募入编。
执行后，片段将两名角色的上线结果、关联设施开放状态与提示条数写入 payload。
"""
OFFICE = ["中枢", "博士办公室"]
"""角色经 get_new_character 上线后预期移动到的目标场景路径。"""


class GetNewCharacterUiFreeTest(FastTestCase):
    """验证 get_new_character 在无界面子进程中完成访客抵达与招募入编的测试类。"""

    runs: dict[str, ChildRun]
    """以 PYTHONIOENCODING 编码名为键、对应无界面子进程运行结果 ChildRun 为值的映射。"""

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用父类类级准备，并在 ENCODINGS 的三种编码下分别以 boot=True 调用 run_ui_free 执行 ARRIVALS。
        每次运行的结果按编码名存入 cls.runs，子进程非零退出时由 run_ui_free 抛出 RuntimeError。
        Return arguments:
        None -- 无返回值
        """
        super().setUpClass()
        cls.runs = {}
        for encoding in ENCODINGS:
            with mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}):
                cls.runs[encoding] = run_ui_free(ARRIVALS, boot=True)

    def test_touches_no_blocked_module(self) -> None:
        """
        验证各编码子进程均未加载且未尝试导入任何默认受拦截模块。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                self.assertEqual((run.loaded, run.attempted), ([], []))

    def test_visitor_arrives_online(self) -> None:
        """
        验证各编码子进程中角色 1 作为访客抵达后的返回值为 1，停留 3 天且 vistor 标记为 1。
        同时断言该角色已在编、体力与气力恢复至上限 [100, 90]、位于 OFFICE 且宿舍分配为客房。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                self.assertEqual(
                    run.payload["1"],
                    {
                        "done": 1,
                        "stay_days": 3,
                        "vistor": 1,
                        "roster": True,
                        "needs": [100, 90],
                        "position": OFFICE,
                        "guest_room": True,
                    },
                )

    def test_recruit_comes_online(self) -> None:
        """
        验证各编码子进程中角色 2 招募入编后的返回值为 True，停留天数为 0 且 vistor 标记为 0。
        同时断言该角色已在编、体力与气力恢复至上限 [100, 90]、位于 OFFICE 且未分入客房。
        用例还断言其关联设施已开放，且累计收集的提示为 2 条。
        Return arguments:
        None -- 无返回值
        """
        for encoding, run in self.runs.items():
            with self.subTest(encoding):
                self.assertEqual(
                    run.payload["2"],
                    {
                        "done": True,
                        "stay_days": 0,
                        "vistor": 0,
                        "roster": True,
                        "needs": [100, 90],
                        "position": OFFICE,
                        "guest_room": False,
                    },
                )
                self.assertTrue(run.payload["smithy_open"])
                self.assertEqual(run.payload["notices"], 2)
