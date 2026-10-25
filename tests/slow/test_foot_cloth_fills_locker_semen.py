# -*- coding: UTF-8 -*-
"""
脱鞋袜进大浴场衣柜后衣柜精液表完整的回归测试
============================================
开新游戏后，干员的衣柜精液表 cloth_locker_semen 是空 dict。
干员去足浴前先脱鞋袜（行为 foot_cloth_to_locker，效果 646「袜子和鞋子转移到大浴场衣柜」），泡完脚穿回（行为 locker_to_wear，效果 643「大浴场衣柜里的衣服转移到身上」）。
效果 646 之后这张表须覆盖全部服装部位：自检 BODY-10 要求非空的表覆盖全部部位，效果 643 按全部部位下标读取它。
本测试对开局的阿米娅直接调用这两个结算函数。
"""

from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
  import datetime
  from collections.abc import Callable

  from Script.Core import game_type

SHOE_SEMEN = 30
""" 脱鞋前鞋上的精液量（ml） """


class FootClothFillsLockerSemenTest(SlowTestCase):
  """衣柜精液表为空的干员脱鞋袜进衣柜：表覆盖全部服装部位，BODY-10 通过；穿回鞋袜时鞋上的精液回到鞋上"""

  def settle(
      self,
      effect: "Callable[[int, int, game_type.CharacterStatusChange, datetime.datetime], None]",
      cid: int,
  ) -> None:
    """
    对干员跑一次行为效果结算（结算时间 5 分钟）
    Keyword arguments:
    effect -- 结算函数
    cid -- 角色id
    Return arguments:
    无
    """
    from Script.Core import game_type

    effect(cid, 5, game_type.CharacterStatusChange(), self.cache.game_time)

  def foot_cloth_to_locker(
      self,
  ) -> "tuple[game_type.Character, list[int], list[int]]":
    """
    开局的阿米娅鞋上有 30ml 精液时，跑一次脱鞋袜进大浴场衣柜的结算
    Keyword arguments:
    无
    Return arguments:
    tuple -- (角色对象, 脱下前的袜子列表, 脱下前的鞋子列表)
    """
    from Script.Design import attr_calculation
    from Script.Settle import default_cloth

    cid = self.npc("阿米娅")
    cd = self.cache.character_data[cid]
    self.assertEqual(cd.dirty.cloth_locker_semen, {}, "开局的衣柜精液表")
    socks, shoes = list(cd.cloth.cloth_wear[10]), list(cd.cloth.cloth_wear[11])
    self.assertTrue(shoes, "开局穿着鞋")
    cd.dirty.cloth_semen[11][1] = SHOE_SEMEN
    cd.dirty.cloth_semen[11][2] = attr_calculation.get_semen_now_level(
        SHOE_SEMEN, 11, 1
    )
    self.settle(default_cloth.handle_foot_cloth_to_shower_locker, cid)
    return cd, socks, shoes

  def test_locker_table_complete(self) -> None:
    """脱鞋袜进衣柜后：鞋袜与鞋上的精液进了衣柜，衣柜精液表覆盖全部服装部位，BODY-10 不报告失败"""
    import Script.Test.Static_Check  # noqa: F401  导入即注册全部检查
    from Script.Config import game_config
    from Script.Test.Static_Check.check_registry import get_all_checks

    cd, socks, shoes = self.foot_cloth_to_locker()
    self.assertEqual(
        (
            cd.cloth.cloth_locker_in_shower[10],
            cd.cloth.cloth_locker_in_shower[11],
        ),
        (socks, shoes),
        "衣柜里的鞋袜",
    )
    self.assertEqual(
        (cd.dirty.cloth_semen[11][1], cd.dirty.cloth_locker_semen[11][1]),
        (0, SHOE_SEMEN),
        "鞋上的精液进了衣柜",
    )
    self.assertEqual(
        sorted(cd.dirty.cloth_locker_semen),
        sorted(game_config.config_clothing_type),
        "衣柜精液表的服装部位",
    )
    self.assertEqual([f.message for f in get_all_checks()["BODY-10"][1]()], [])

  def test_back_on_with_semen(self) -> None:
    """脱鞋袜进衣柜后再穿回：鞋袜回到身上，鞋上的精液回到鞋上"""
    from Script.Settle import default_cloth

    cd, socks, shoes = self.foot_cloth_to_locker()
    self.settle(default_cloth.handle_shower_locker_to_wear, cd.cid)
    self.assertEqual(
        (cd.cloth.cloth_wear[10], cd.cloth.cloth_wear[11]),
        (socks, shoes),
        "穿回身上的鞋袜",
    )
    self.assertEqual(cd.dirty.cloth_semen[11][1], SHOE_SEMEN, "精液回到鞋上")
