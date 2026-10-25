# -*- coding: UTF-8 -*-
"""
读档后穿着与衣柜的服装精液表各用各的列表
========================================
开新游戏后摆出三名穿着袜子的干员，袜子上都有精液：
- 阿米娅：衣柜精液表与穿着的表是同一个 dict；
- 第二名：两表各是一个 dict，每个服装部位共用同一个列表；
- 第三名：两表都缺最后一个服装部位（读档时两表都换成全部部位、精液量为 0 的新表）。
经 save_handle 真实写盘、读档后：
- 前两名两表的精液量与写盘前相同，第三名两表的精液量都是 0；
- 往每人穿着的袜子上射精（ejaculation_panel.update_semen_dirty），只有穿着的表变，
  衣柜的表不变，自检 BODY-14 不报告失败；
- 再写盘、读档一次，三人两表的精液量不变。
"""

import shutil

from tests.slow.base import SlowTestCase

SAVE_ID = "test_load_splits_shared_cloth_semen"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
SOCKS = 10
""" 袜子的服装部位 """
SOCKS_SEMEN = 20
""" 写盘前袜子上的精液量（ml） """
SHOT = 15
""" 读档后往穿着的袜子上射的精液量（ml） """


class TestLoadSplitsSharedClothSemen(SlowTestCase):
  """存档里穿着与衣柜的服装精液表共用 dict 或列表、或两表都缺部位时，读档后两表分开"""

  def tearDown(self) -> None:
    """
    删掉本测试写入的存档
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import save_handle

    shutil.rmtree(save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True)
    super().tearDown()

  def _save_and_load(self) -> None:
    """
    写盘再读档
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import save_handle

    save_handle.establish_save(SAVE_ID)
    self.assertTrue(
        save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上"
    )
    save_handle.input_load_save(SAVE_ID)

  def _semen(self, cid: int) -> tuple[dict[int, int], dict[int, int]]:
    """
    两表各部位的当前精液量
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    tuple -- ({部位: 穿着的量}, {部位: 衣柜的量})
    """
    dirty = self.cache.character_data[cid].dirty
    return (
        {t: v[1] for t, v in dirty.cloth_semen.items()},
        {t: v[1] for t, v in dirty.cloth_locker_semen.items()},
    )

  def test_tables_split_after_load(self) -> None:
    """三种存档读档后：精液量按读档规则保留或清零，射在穿着的袜子上只改穿着的表，BODY-14 通过，再存读一次不变"""
    from Script.Config import game_config
    from Script.Test.Static_Check.checks.check_body import (
        check_semen_list_aliasing,
    )
    from Script.UI.Panel import ejaculation_panel

    all_types = sorted(game_config.config_clothing_type)
    whole_dict_id = self.npc("阿米娅")
    shared_list_id, short_id = sorted(
        cid
        for cid in self.cache.npc_id_got
        if cid not in (0, whole_dict_id)
        and self.cache.character_data[cid].cloth.cloth_wear[SOCKS]
    )[:2]
    for cid in (whole_dict_id, shared_list_id, short_id):
      self.assertTrue(
          self.cache.character_data[cid].cloth.cloth_wear[SOCKS],
          f"{cid} 穿着袜子",
      )
      ejaculation_panel.update_semen_dirty(cid, SOCKS, 1, SOCKS_SEMEN)
    whole = self.cache.character_data[whole_dict_id].dirty
    whole.cloth_locker_semen = whole.cloth_semen
    shared = self.cache.character_data[shared_list_id].dirty
    shared.cloth_locker_semen = dict(shared.cloth_semen)
    short = self.cache.character_data[short_id].dirty
    short.cloth_locker_semen = {
        t: list(v) for t, v in short.cloth_semen.items()
    }
    for table in (short.cloth_semen, short.cloth_locker_semen):
      del table[all_types[-1]]
    expected = {
        cid: self._semen(cid) for cid in (whole_dict_id, shared_list_id)
    }
    zero = {t: 0 for t in all_types}
    expected[short_id] = (zero, zero)
    for cid in (whole_dict_id, shared_list_id):
      self.assertEqual(
          (expected[cid][0][SOCKS], expected[cid][1][SOCKS]),
          (SOCKS_SEMEN, SOCKS_SEMEN),
          f"{cid} 写盘前两表袜子上的精液",
      )

    self._save_and_load()
    for cid in expected:
      self.assertEqual(
          self._semen(cid), expected[cid], f"{cid} 读档后两表的精液量"
      )

    for cid in expected:
      ejaculation_panel.update_semen_dirty(cid, SOCKS, 1, SHOT)
      worn, locker = self._semen(cid)
      self.assertEqual(
          (worn[SOCKS], locker),
          (expected[cid][0][SOCKS] + SHOT, expected[cid][1]),
          f"{cid} 射在穿着的袜子上：穿着的表加上射精量，衣柜的表不变",
      )
    self.assertEqual([f.message for f in check_semen_list_aliasing()], [])

    after_shot = {cid: self._semen(cid) for cid in expected}
    self._save_and_load()
    for cid in expected:
      self.assertEqual(
          self._semen(cid), after_shot[cid], f"{cid} 再存读一次两表的精液量"
      )
