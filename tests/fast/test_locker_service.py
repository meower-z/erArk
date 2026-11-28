"""
衣柜检查服务测试
================
覆盖各场景衣柜归属扫描与衣柜类型路由、批量与单件偷取写入边界、
衣柜内容与射精选项展示及面板按钮适配、具名编辑 locker_shoot 派发，
以及在拦截界面与结算模块的子进程中独立运行衣柜服务。
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import text_handle
from Script.Design import clothing, map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, dirty
from Script.Modules.domains import player_collection, wardrobe
from Script.Modules.gameplay_resolution import edits, ejaculation_service
from Script.Modules.gameplay_resolution import locker_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import player_pick
from Script.UI.Panel import check_locker_panel
from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
"""仓库根目录路径。"""
DORM = ["宿舍", "1区", "101"]
"""测试用宿舍 101 场景路径。"""
OTHER_DORM = ["宿舍", "1区", "102"]
"""测试用相邻宿舍 102 场景路径。"""
DR_ROOM = ["中枢", "博士房间"]
"""测试用博士房间场景路径。"""
LOCKER_ROOM = ["大浴场", "更衣室"]
"""测试用大浴场更衣室场景路径。"""
PLAIN = ["中枢", "指挥室"]
"""无衣柜标签的普通场景（指挥室）路径。"""
DORM_SLOT = "cloth_locker_in_dormitory"
"""宿舍衣柜对应的服装属性槽位名。"""
SHOWER_SLOT = "cloth_locker_in_shower"
"""大浴场更衣室衣柜对应的服装属性槽位名。"""
UI_FREE_RUN = """
import contextlib, importlib.abc, io, json, sys
from types import MappingProxyType
BLOCKED = (
    "Script.UI",
    "Script.Settle",
    "Script.System.Instruct_System.handle_instruct",
    "Script.Core.flow_handle",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
from Script.Config import game_config, map_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
from Script.Design import attr_calculation, map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, activity, chara_life
from Script.Modules.domains import dirty, h_meters, identity, player_collection
from Script.Modules.domains import roster, wardrobe, warehouse
from Script.Modules.gameplay_resolution import edits, ui_hooks
from Script.Modules.gameplay_resolution import locker_service as svc
from Script.Modules.gameplay_resolution import working
pan, sock = int(sys.argv[1]), int(sys.argv[2])
room = ["宿舍", "1区", "101"]
core.reset_state(core.GameState(0, MappingProxyType({}), MappingProxyType({})))
with working.based_on(core.state()):
    for cid, name in ((0, "博士"), (1, "干员甲")):
        identity.put(identity.Identity(cid, name=name))
        cloth = attr_calculation.get_cloth_zero()
        cloth.cloth_locker_in_dormitory = (
            attr_calculation.get_cloth_locker_in_dormitory_zero()
        )
        cloth.cloth_locker_in_shower = attr_calculation.get_shower_cloth_locker_zero()
        wardrobe.put(cid, cloth)
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
    h_meters.set(0, semen=1000, semen_max=1000)
    warehouse.start({})
    action_info.set(0, "day_first_shoot_semen", False)
    roster.add(1)
    chara_life.dormitory.set(1, map_handle.get_map_system_path_str_for_list(room))
    activity.set_position(0, room)
    player_collection.init_zero(0)
    wardrobe.set_part(1, "cloth_locker_in_dormitory", 9, [pan])
    wardrobe.set_part(1, "cloth_locker_in_dormitory", 10, [sock])
    with dirty.editing(1) as d:
        d.cloth_locker_semen[9] = ["", 25, 0, 25]
    site = svc.site_here()
    locker_type, locker = svc.locker_here(1)
    contents = [
        [p.clothing_type, list(p.cloth_names), p.semen]
        for p in svc.contents(1, locker)
    ]
    before = list(dirty.view(1).cloth_locker_semen[9][1:])
    semen_before = h_meters.of(0)["semen"]
    banners = []
    def note(text, *, style, **_kw):
        if style == "semen":
            banners.append(text)
    ui_hooks.on_notice(note)
    args = json.loads(json.dumps(svc.shoot_args(9, locker_type, 1)))
    act = edits.edit_action(svc.SHOOT_EDIT, name=svc.SHOOT_EDIT, args=args)
    core._bodies[edits.EDIT](act)
    out = {
        "owners": svc.owners(site),
        "locker_type": locker_type,
        "contents": contents,
        "shot": {
            "before": before,
            "after": list(dirty.view(1).cloth_locker_semen[9][1:]),
            "spent": semen_before - h_meters.of(0)["semen"],
            "banners": len(banners),
        },
        "last": svc.steal_last(1, locker_type, 10, locker[10]),
        "all": [
            [s.owner_name, s.cloth_name]
            for s in svc.steal_all([1], site.scene.scene_tag, 9)
        ],
        "left": svc.filled_parts(svc.locker_here(1)[1]),
        "panties": player_collection.get("npc_panties_tem")[1],
        "socks": player_collection.get("npc_socks_tem")[1],
    }
modules = sorted(sys.modules)
out["ui"] = [n for n in modules if n == "Script.UI" or n.startswith("Script.UI.")]
out["settle"] = [
    n for n in modules if n == "Script.Settle" or n.startswith("Script.Settle.")
]
out["blocked"] = [n for n in modules if blocked(n)]
print(json.dumps(out))
"""
"""在拦截界面、结算与 Tk 模块的独立子进程中执行衣柜服务并回传校验结果的脚本。"""


def _clothes(part: int, count: int) -> list[int]:
    """按编号升序返回指定服装部位的前 count 件模板编号。"""
    tem = game_config.config_clothing_tem
    return sorted(i for i in tem if tem[i].clothing_type == part)[:count]


def _name(cloth_id: int) -> str:
    """读取指定衣物模板编号对应的配置名称。"""
    return game_config.config_clothing_tem[cloth_id].name


def _key(path: list[str]) -> str:
    """将地图路径列表转换为场景字典使用的路径键字符串。"""
    return map_handle.get_map_system_path_str_for_list(path)


class LockerServiceCase(FastTestCase):
    """衣柜服务测试基类，初始化博士与两名干员、开启写缓冲并准备测试衣物编号。"""

    def setUp(self) -> None:
        """创建博士与干员甲、乙，开启写缓冲并初始化玩家收藏品与示例衣物编号。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))
        player_collection.init_zero(0)
        self.pans = _clothes(svc.PANTIES, 2)
        self.socks = _clothes(svc.SOCKS, 2)
        self.unknown = max(game_config.config_clothing_tem) + 1

    def stand(self, path: list[str]) -> svc.Site:
        """将玩家移动到指定路径并返回对应的当前位置记录。"""
        activity.set_position(0, path)
        return svc.site_here()

    def fill(self, cid: int, slot: str, part: int, ids: list[int]) -> None:
        """向指定干员的衣柜槽位部位写入给定衣物编号列表。"""
        wardrobe.set_part(cid, slot, part, list(ids))

    def semen(self, cid: int, part: int, amount: int) -> None:
        """设置指定干员衣柜服装部位的当前精液量。"""
        with dirty.editing(cid) as d:
            d.cloth_locker_semen[part] = ["", amount, 0, amount]


class OwnersTest(LockerServiceCase):
    """按场景标签筛选衣柜归属干员与衣柜类型路由测试。"""

    def test_dormitory_lists_residents_with_clothes(self) -> None:
        """宿舍场景使用宿舍衣柜，且仅列出住在该宿舍且宿舍衣柜非空的干员。"""
        chara_life.dormitory.set(2, _key(OTHER_DORM))
        self.fill(1, DORM_SLOT, svc.SOCKS, self.socks[:1])
        self.fill(2, DORM_SLOT, svc.PANTIES, self.pans[:1])
        self.fill(2, SHOWER_SLOT, svc.PANTIES, self.pans[:1])
        site = self.stand(DORM)
        self.assertEqual(site.path, _key(DORM))
        self.assertEqual(site.locker_type, clothing.CLOTH_LOCKER_TYPE_DORMITORY)
        self.assertEqual(svc.owners(site), [1])

    def test_doctor_room_reads_dormitory_lockers(self) -> None:
        """博士房间使用宿舍衣柜，并仅列出宿舍地址位于博士房间的非空干员。"""
        chara_life.dormitory.set(1, _key(DR_ROOM))
        self.fill(1, DORM_SLOT, svc.PANTIES, self.pans[:1])
        self.fill(2, DORM_SLOT, svc.PANTIES, self.pans[:1])
        site = self.stand(DR_ROOM)
        self.assertEqual(site.locker_type, clothing.CLOTH_LOCKER_TYPE_DORMITORY)
        self.assertEqual(svc.owners(site), [1])

    def test_locker_room_lists_every_shower_locker(self) -> None:
        """大浴场更衣室使用更衣室衣柜，列出全部更衣室衣柜非空的干员。"""
        chara_life.dormitory.set(2, _key(OTHER_DORM))
        self.fill(1, SHOWER_SLOT, svc.PANTIES, self.pans[:1])
        self.fill(2, SHOWER_SLOT, 5, _clothes(5, 1))
        site = self.stand(LOCKER_ROOM)
        self.assertEqual(site.locker_type, clothing.CLOTH_LOCKER_TYPE_SHOWER)
        self.assertEqual(sorted(svc.owners(site)), [1, 2])

    def test_other_scene_lists_nobody(self) -> None:
        """无衣柜标签的普通场景不返回任何衣柜归属干员。"""
        self.fill(1, DORM_SLOT, svc.PANTIES, self.pans[:1])
        self.fill(1, SHOWER_SLOT, svc.PANTIES, self.pans[:1])
        self.assertEqual(svc.owners(self.stand(PLAIN)), [])


class StealTest(LockerServiceCase):
    """衣柜部位存在检查、批量偷取与单件偷取读写边界测试。"""

    def test_has_part_reads_without_copying(self) -> None:
        """校验 has_part 读取衣柜时不复制可变快照，且 locker_here 每次返回互不影响且不改动已存视图的独立副本。"""
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        self.fill(1, DORM_SLOT, svc.PANTIES, self.pans[:1])
        boom = mock.Mock(side_effect=AssertionError("cloned"))
        with mock.patch.object(wardrobe, "clone_mutable_snapshot", boom):
            self.assertTrue(svc.has_part([2, 1], dorm, svc.PANTIES))
            self.assertFalse(svc.has_part([1, 2], dorm, svc.SOCKS))
        _, first = svc.locker_here(1)
        _, second = svc.locker_here(1)
        first[svc.PANTIES].append(self.unknown)
        self.assertEqual(second[svc.PANTIES], self.pans[:1])
        locker = wardrobe.of(1).cloth_locker_in_dormitory
        self.assertEqual(list(locker[svc.PANTIES]), self.pans[:1])

    def test_has_part(self) -> None:
        """校验 has_part 对目标部位非空判定有效，且计入未知衣物编号。"""
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        self.fill(2, DORM_SLOT, svc.SOCKS, [self.unknown])
        self.assertTrue(svc.has_part([1, 2], dorm, svc.SOCKS))
        self.assertFalse(svc.has_part([1, 2], dorm, svc.PANTIES))
        self.assertFalse(svc.has_part([1], dorm, svc.SOCKS))

    def test_steal_all_skips_unknown_ids_and_empties_parts(self) -> None:
        """批量偷取跳过未知编号但清空部位，保持顺序并仅执行一次收藏品写入。"""
        held = [self.pans[0], self.unknown, self.pans[1]]
        self.fill(1, DORM_SLOT, svc.PANTIES, held)
        self.fill(2, DORM_SLOT, svc.PANTIES, [self.pans[0]])
        put = player_collection.put
        with mock.patch.object(player_collection, "put", wraps=put) as writes:
            stolen = svc.steal_all([1, 2], ["Dormitory"], svc.PANTIES)
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(
            [(s.owner_name, s.cloth_name) for s in stolen],
            [
                ("干员甲", _name(self.pans[0])),
                ("干员甲", _name(self.pans[1])),
                ("干员乙", _name(self.pans[0])),
            ],
        )
        table = player_collection.get("npc_panties_tem")
        self.assertEqual(table[1][-2:], self.pans)
        self.assertEqual(table[2][-1:], self.pans[:1])
        self.assertEqual(wardrobe.of(1).cloth_locker_in_dormitory[9], ())
        self.assertEqual(wardrobe.of(2).cloth_locker_in_dormitory[9], ())

    def test_steal_all_from_empty_lockers_writes_once(self) -> None:
        """目标部位为空时批量偷取返回空元组，仍执行一次收藏品写入且不碰其他部位。"""
        self.fill(1, SHOWER_SLOT, svc.PANTIES, self.pans[:1])
        put = player_collection.put
        with mock.patch.object(player_collection, "put", wraps=put) as writes:
            stolen = svc.steal_all([1, 2], ["Locker_Room"], svc.SOCKS)
        self.assertEqual(stolen, ())
        self.assertEqual(writes.call_count, 1)
        shower = wardrobe.of(1).cloth_locker_in_shower
        self.assertEqual(list(shower[9]), self.pans[:1])

    def test_steal_last_takes_last_item_and_empties_part(self) -> None:
        """单件偷取仅取走快照末件衣物入藏，并清空衣柜中的整个部位。"""
        self.fill(1, SHOWER_SLOT, svc.SOCKS, self.socks)
        shower = clothing.CLOTH_LOCKER_TYPE_SHOWER
        name = svc.steal_last(1, shower, svc.SOCKS, self.socks)
        self.assertEqual(name, _name(self.socks[1]))
        socks = player_collection.get("npc_socks_tem")
        self.assertEqual(socks[1][-1:], self.socks[1:])
        self.assertEqual(wardrobe.of(1).cloth_locker_in_shower[10], ())

    def test_steal_last_with_nothing_writes_nothing(self) -> None:
        """部位快照为空时单件偷取返回 None 且不触发任何收藏品写入。"""
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        with mock.patch.object(player_collection, "put") as writes:
            self.assertIsNone(svc.steal_last(1, dorm, svc.PANTIES, []))
        writes.assert_not_called()

    def test_steal_last_unknown_id_raises_before_writing(self) -> None:
        """快照末件为未知衣物编号时在写入前抛出 KeyError，且收藏品与衣柜不变。"""
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        self.fill(1, DORM_SLOT, svc.PANTIES, [self.unknown])
        with mock.patch.object(player_collection, "put") as writes:
            with self.assertRaises(KeyError):
                svc.steal_last(1, dorm, svc.PANTIES, [self.unknown])
        writes.assert_not_called()
        locker = wardrobe.of(1).cloth_locker_in_dormitory
        self.assertEqual(list(locker[9]), [self.unknown])


class ShowTest(LockerServiceCase):
    """衣柜内容整理、非空部位顺序、射精选项与面板按钮适配测试。"""

    def test_contents_skip_unknown_ids_and_carry_semen(self) -> None:
        """校验非空部位按配置顺序返回，内容列表跳过未知编号并携带精液量。"""
        self.fill(1, DORM_SLOT, svc.SOCKS, self.socks[:1])
        self.fill(1, DORM_SLOT, svc.PANTIES, [self.pans[0], self.unknown])
        self.semen(1, svc.PANTIES, 30)
        _, locker = svc.locker_here(1)
        self.assertEqual(svc.filled_parts(locker), [svc.PANTIES, svc.SOCKS])
        self.assertEqual(
            svc.contents(1, locker),
            (
                svc.LockerPart(svc.PANTIES, (_name(self.pans[0]),), 30),
                svc.LockerPart(svc.SOCKS, (_name(self.socks[0]),), 0),
            ),
        )

    def test_shoot_option_reads_the_locker_now(self) -> None:
        """校验 shoot_option 实时读取衣柜衣物拼接标签并附带当前精液量。"""
        self.fill(1, DORM_SLOT, svc.PANTIES, self.pans)
        self.semen(1, svc.PANTIES, 12)
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        part = game_config.config_clothing_type[svc.PANTIES].name
        names = " ".join(_name(i) for i in self.pans)
        self.assertEqual(
            svc.shoot_option(1, dorm, svc.PANTIES),
            svc.ShootOption(f"{part}: {names}", 12),
        )

    def test_panel_buttons_show_service_data(self) -> None:
        """校验 FindDraw 与 Ejaculation_NameDraw 按钮文本及提交的编辑参数。"""
        self.fill(1, DORM_SLOT, svc.PANTIES, self.pans[:1])
        self.semen(1, svc.PANTIES, 7)
        self.stand(DORM)
        find = check_locker_panel.FindDraw(1, 60, True, True, 0)
        self.assertEqual(
            find.draw_text,
            f"{text_handle.id_index(0)}干员甲的衣柜",
        )
        self.assertEqual(find.now_locker[svc.PANTIES], self.pans[:1])
        button = check_locker_panel.Ejaculation_NameDraw(
            [9, 1], 60, True, True, 3
        )
        part = game_config.config_clothing_type[svc.PANTIES].name
        label = f"{part}: {_name(self.pans[0])}"
        self.assertEqual(
            button.draw_text,
            f"{text_handle.id_index(3)} {label} (7ml精液)",
        )
        with mock.patch.object(player_pick, "commit_edit") as commit:
            button.shoot_here()
        commit.assert_called_once_with(
            svc.SHOOT_EDIT,
            {
                "part": 9,
                "locker": clothing.CLOTH_LOCKER_TYPE_DORMITORY,
                "target": 1,
            },
        )


class ShootEditTest(LockerServiceCase):
    """具名编辑 locker_shoot 执行派发测试。"""

    def test_shoot_edit_runs_ejaculation_on_the_locker(self) -> None:
        """校验 JSON 往返后的 locker_shoot 经已注册 Edit 入口以整数参数与 draw_flag=True 调用射精流程。"""
        args = svc.shoot_args(9, clothing.CLOTH_LOCKER_TYPE_SHOWER, 2)
        args = json.loads(json.dumps(args))
        act = edits.edit_action(svc.SHOOT_EDIT, name=svc.SHOOT_EDIT, args=args)
        with mock.patch.object(ejaculation_service, "ejaculation_flow") as flow:
            core._bodies[edits.EDIT](act)
        flow.assert_called_once_with(
            part_cid=9,
            part_type=clothing.CLOTH_LOCKER_TYPE_SHOWER,
            target_character_id=2,
            draw_flag=True,
        )


class UiFreeRunTest(FastTestCase):
    """衣柜服务在无界面与无结算环境中的独立运行边界测试。"""

    def test_service_runs_without_ui_or_settle(self) -> None:
        """在拦截界面、结算与 Tk 模块的独立子进程中完整跑通查询、编辑与偷取调用。"""
        pan, sock = _clothes(svc.PANTIES, 1)[0], _clothes(svc.SOCKS, 1)[0]
        result = subprocess.run(
            [sys.executable, "-c", UI_FREE_RUN, str(pan), str(sock)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
        dorm = clothing.CLOTH_LOCKER_TYPE_DORMITORY
        self.assertEqual(out["ui"], [])
        self.assertEqual(out["settle"], [])
        self.assertEqual(out["blocked"], [])
        self.assertEqual(out["owners"], [1])
        self.assertEqual(out["locker_type"], dorm)
        self.assertEqual(
            out["contents"], [[9, [_name(pan)], 25], [10, [_name(sock)], 0]]
        )
        shot = out["shot"]
        added = shot["after"][0] - shot["before"][0]
        self.assertEqual(shot["before"], [25, 0, 25])
        self.assertGreater(added, 0)
        self.assertEqual(shot["after"][2] - shot["before"][2], added)
        self.assertEqual(shot["spent"], added)
        self.assertGreater(shot["banners"], 0)
        self.assertEqual(out["last"], _name(sock))
        self.assertEqual(out["all"], [["干员甲", _name(pan)]])
        self.assertEqual(out["left"], [])
        self.assertEqual(out["panties"], [pan])
        self.assertEqual(out["socks"], [sock])
