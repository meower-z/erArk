# -*- coding: UTF-8 -*-
"""
基地的派对排期、旅馆房间、四项计数、冰箱与三项上限
==================================================
- 图书馆面板选读书会之日：别的日子的读书会取消，这天成为读书会。这天已有别的活动时，排期不变。
- 当前角色是玩家或交互对象是玩家时，好感度上升才计入计数 favorability。
  粉红凭证结算把这项计数的百分之一与计数 fallen_certificates 存进仓库。结算后两项计数清零。
- 计数 aromatherapy 在日结与刷新基地时按疗养庭院的等级给出，4 级为 2，5 级为 3。
- 冰箱：按种类加存量，表按第一次存进的先后排列。拿走一名角色的存量。换 id 时旧 id 换成新 id。删掉给出的角色。
- 干员人数上限与仓库容量由当前的设施等级与扩展模块数算出。等级或模块数变了，上限跟着变。
- 床位上限只在重算时变。加了住院医生后床位上限不变，新收费系数生效时的重算才算上医生的加成。
- 读档：版本 12 的罗德岛对象带着这些属性时，值写进 GameState，属性从对象上删掉。
  版本 13 之前的存档缺一个属性计 1 条跨版本更新，版本 13 的不计。派对排期或冰箱的表不是 dict 时计 1 条，按默认值读。
"""

import pickle
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type, get_text, save_handle
from Script.Design import basement, character_handle
from Script.Kernel import core
from Script.Modules.domains import (
    country,
    entertainment,
    facility,
    fridge,
)
from Script.Modules.domains import medical, tallies, warehouse
from Script.Modules.gameplay_resolution import working
from Script.System.Medical_System import clinic_patient_management
from Script.System.Medical_System import medical_constant, medical_service
from Script.UI.Moudle import draw
from Script.UI.Panel import aromatherapy_panel, manage_library
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

SLOT = "base_tallies"
""" 读档用的存档id。测试换掉 save_handle.load_save，不读文件 """
COURTYARD = 16
""" 疗养庭院的设施id """
READING = 101
""" 读书会的娱乐id """


def cid_named(name: str) -> int:
    """
    按当前语言的设施名找设施id
    Keyword arguments:
    name -- 设施名的原文，函数里翻译成当前语言
    Return arguments:
    int -- 设施id
    """
    wanted = get_text._(name)
    return next(
        cid
        for cid, data in game_config.config_facility.items()
        if data.name == wanted
    )


def effect_of(cid: int, level: int) -> int:
    """
    设施在给定等级的效果值，按配置表算
    Keyword arguments:
    cid -- 设施id
    level -- 等级
    Return arguments:
    int -- 效果值
    """
    name = game_config.config_facility[cid].name
    effect_cid = game_config.config_facility_effect_data[name][level]
    return game_config.config_facility_effect[effect_cid].effect


class BaseTalliesStateTest(FastTestCase):
    """基地的派对排期、计数、冰箱、上限与旧存档读档"""

    def setUp(self) -> None:
        """博士与两名干员。测试里对 GameState 的读写记在以当前状态为底的缓冲区里"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))

    def test_reading_party_day_moves(self) -> None:
        """周二已是读书会，周五排了别的活动。选周四：周二取消，周四成为读书会。再选周五，排期不变"""
        library = manage_library.Manage_Library_Panel(80)
        entertainment.set_party_day(1, READING)
        other = next(
            e for e in game_config.config_entertainment if e not in (0, READING)
        )
        entertainment.set_party_day(4, other)
        library.choice_read_party(3)
        expected = {d: 0 for d in range(7)} | {3: READING, 4: other}
        self.assertEqual(entertainment.party_days(), expected)
        library.choice_read_party(4)
        self.assertEqual(entertainment.party_days(), expected)

    def test_favorability_tally_pays_certificates(self) -> None:
        """
        干员甲的交互对象为玩家时加 250 好感，为干员乙时加 40。计数 favorability 只记 250。
        再给计数 fallen_certificates 加 30。粉红凭证结算后粉红凭证多 2 + 30，两项计数为 0
        """
        aim(1, 0)
        character_handle.add_favorability(1, 0, 250, None, None)
        aim(1, 2)
        character_handle.add_favorability(1, 2, 40, None, None)
        self.assertEqual(tallies.get(tallies.FAVORABILITY), 250)
        tallies.add(tallies.FALLEN, 30)
        before = warehouse.amount(4)
        basement.settle_pink_certificate()
        self.assertEqual(warehouse.amount(4) - before, 32)
        self.assertEqual(tallies.get(tallies.FAVORABILITY), 0)
        self.assertEqual(tallies.get(tallies.FALLEN), 0)

    def test_aromatherapy_follows_courtyard_level(self) -> None:
        """疗养庭院 4 级时日结的刷新给 2 次，用掉 1 次剩 1 次。升到 5 级后刷新基地，为 3 次"""
        facility.set_level(COURTYARD, 4)
        aromatherapy_panel.settle_aromatherapy_sessions()
        self.assertEqual(tallies.get(tallies.AROMATHERAPY), 2)
        tallies.add(tallies.AROMATHERAPY, -1)
        self.assertEqual(tallies.get(tallies.AROMATHERAPY), 1)
        facility.set_level(COURTYARD, 5)
        basement.get_base_updata()
        self.assertEqual(tallies.get(tallies.AROMATHERAPY), 3)

    def test_fridge_tables(self) -> None:
        """
        干员乙、干员甲先后存进 milk 表，干员乙再存一次。表按第一次存进的先后排列，存量相加。干员甲还存进 urine 表。
        拿走干员乙的存量。把 id 1 换成 7 后，两个表里都只有 7。删掉 7 后两个表都空了，删掉的条数为 2
        """
        fridge.add(fridge.MILK, 2, 30)
        fridge.add(fridge.MILK, 1, 20)
        fridge.add(fridge.MILK, 2, 5)
        fridge.add(fridge.URINE, 1, 10)
        self.assertEqual(
            list(fridge.table(fridge.MILK).items()), [(2, 35), (1, 20)]
        )
        self.assertEqual(fridge.take(fridge.MILK, 2), 35)
        fridge.remap({1: 7})
        self.assertEqual(fridge.table(fridge.MILK), {7: 20})
        self.assertEqual(fridge.table(fridge.URINE), {7: 10})
        self.assertEqual(fridge.drop({7}), 2)
        self.assertEqual(
            (fridge.table(fridge.MILK), fridge.table(fridge.URINE)), ({}, {})
        )

    def test_caps_follow_levels_and_modules(self) -> None:
        """
        宿舍区升到 3 级，干员人数上限为 3 级的效果值。
        仓储区 2 级、用了 2 个扩展模块时，仓库容量为 2 级效果值加 400
        """
        dormitory = cid_named("宿舍区")
        storage = cid_named("仓储区")
        facility.set_level(dormitory, 3)
        self.assertEqual(facility.people_max(), effect_of(dormitory, 3))
        facility.set_level(storage, 2)
        warehouse.set_extra_modules(2)
        self.assertEqual(warehouse.capacity(), effect_of(storage, 2) + 400)

    def test_bed_limit_waits_for_recompute(self) -> None:
        """医疗部初始化后加两名住院医生，再定下新收费系数，床位上限不变。新收费系数生效时重算，床位上限多两名医生的加成"""
        medical_service.init_medical_department_data(self.cache.rhodes_island)
        start = medical.state().bed_limit
        with medical.editing() as m:
            m.hospital_doctor_ids = [1, 2]
            m.new_price_ratio = 1.5
        self.assertEqual(medical.state().bed_limit, start)
        with medical.editing():
            clinic_patient_management.apply_new_medical_price_ratio()
        bonus = 2 * medical_constant.HOSPITAL_DOCTOR_BED_BONUS
        self.assertEqual(medical.state().bed_limit, start + bonus)

    def install(self, saved: object) -> None:
        """
        按版本 12 跑读档的 Reset 步骤（save_handle.install_save），读入 saved。
        画面输出换成不画的对象。小世界没有国家数据，补国家数据的 country.fill 换成什么也不做的函数
        Keyword arguments:
        saved -- 存档里的游戏缓存
        """

        class Quiet:
            """不画的绘制对象，代替 NormalDraw 与 LeftDraw"""

            def __init__(self) -> None:
                """文本为空，宽度为 0"""
                self.text = ""
                self.width = 0

            def draw(self) -> None:
                """什么也不画"""

        with (
            mock.patch.object(save_handle, "load_save", lambda _id: saved),
            mock.patch.object(draw, "NormalDraw", Quiet),
            mock.patch.object(draw, "LeftDraw", Quiet),
            mock.patch.object(country, "fill", lambda: None),
        ):
            save_handle.install_save(SLOT, 12)

    def test_old_save_moves_into_state(self) -> None:
        """
        版本 12 的罗德岛对象带着全部八个属性：派对排期周三为读书会，旅馆房间档次 2，四项计数 250、70、2、30，
        冰箱两个表各一名干员。读档后 GameState 里是这些值，对象上没有这些属性
        """
        saved = pickle.loads(pickle.dumps(self.cache))
        party = {d: 0 for d in range(7)} | {2: READING}
        counts = dict(zip(tallies.PICKLED, (250, 70, 2, 30), strict=True))
        tables = dict(zip(fridge.PICKLED, ({1: 40}, {2: 15}), strict=True))
        vars(saved.rhodes_island).update(
            {entertainment.PICKLED_PARTY: party, entertainment.PICKLED_HOTEL: 2}
            | counts
            | tables
        )
        self.install(saved)
        self.assertEqual(entertainment.party_days(), party)
        self.assertEqual(entertainment.hotel_room(), 2)
        self.assertEqual(
            {old: tallies.get(n) for old, n in tallies.PICKLED.items()}, counts
        )
        self.assertEqual(
            {old: fridge.table(k) for old, k in fridge.PICKLED.items()}, tables
        )
        moved = {entertainment.PICKLED_PARTY, entertainment.PICKLED_HOTEL}
        moved |= tallies.PICKLED.keys() | fridge.PICKLED.keys()
        island = self.cache.rhodes_island
        self.assertFalse(moved & vars(island).keys())

    def test_old_save_counts_missing_and_wrong_types(self) -> None:
        """
        罗德岛对象没有这八个属性：按版本 12 读，三个读档函数共交回 8 条，按版本 13 读交回 0 条。
        派对排期与 milk 表不是 dict 时，按版本 13 读交回 2 条，排期读作七天都没有派对，milk 表读作空表
        """
        milk = next(o for o, k in fridge.PICKLED.items() if k == fridge.MILK)
        wrong = {entertainment.PICKLED_PARTY: 5, milk: [1]}
        self.assertEqual(adopted({}, 12), 8)
        self.assertEqual(adopted({}, 13), 0)
        self.assertEqual(adopted(wrong, 13), 2)
        self.assertEqual(entertainment.party_days(), dict.fromkeys(range(7), 0))
        self.assertEqual(fridge.table(fridge.MILK), {})


def adopted(attrs: dict[str, object], version: int) -> int:
    """
    把带着 attrs 的新罗德岛对象交给三个模块的 adopt_old_save
    Keyword arguments:
    attrs -- 对象上的属性
    version -- 存档的版本
    Return arguments:
    int -- 三个函数交回的条数之和
    """
    island = game_type.Rhodes_Island()
    vars(island).update(attrs)
    loaded = {"rhodes_island": island}
    adopters = (entertainment, tallies, fridge)
    return sum(m.adopt_old_save(loaded, version) for m in adopters)
