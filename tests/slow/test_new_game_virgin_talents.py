# -*- coding: UTF-8 -*-
"""
新游戏里玩家以外的角色带齐五个处女素质，写盘读档不改任何角色的素质
====================================================================
开新游戏后，玩家以外的每名角色素质 0~4（阴道处女、肛门处女、尿道处女、子宫处女、无接吻经验）都为 1。
经 save_handle 真实写盘、读档后，每名角色的素质与读档前相同：读档时 old_chara_to_new.update_character_config_data
把U/W插入经验（经验 63、64）为 0 的非玩家角色的素质 2、3 设为 1，开局就带齐这两个素质的角色不受它影响。
"""

import shutil

from tests.slow.base import SlowTestCase

SAVE_ID = "test_new_game_virgin_talents"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
VIRGIN_TALENTS = (0, 1, 2, 3, 4)
""" 五个处女素质：阴道处女、肛门处女、尿道处女、子宫处女、无接吻经验 """


class NewGameVirginTalentsTest(SlowTestCase):
  """新游戏里玩家以外的角色带齐五个处女素质，写盘读档后素质不变"""

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

  def test_new_game_virgin_talents(self) -> None:
    """开局时玩家以外的角色素质 0~4 都为 1"""
    lacking = sorted(
        (chara.adv, [t for t in VIRGIN_TALENTS if chara.talent.get(t) != 1])
        for cid, chara in self.cache.character_data.items()
        if cid != 0 and any(chara.talent.get(t) != 1 for t in VIRGIN_TALENTS)
    )
    self.assertEqual(
        lacking, [], "开局时缺处女素质的角色（模板编号, 缺的素质）"
    )

  def test_talents_kept_on_load(self) -> None:
    """写盘读档后每名角色的素质都与读档前相同"""
    from Script.Core import save_handle

    before = {
        cid: dict(chara.talent)
        for cid, chara in self.cache.character_data.items()
    }
    save_handle.establish_save(SAVE_ID)
    self.assertTrue(
        save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上"
    )
    save_handle.input_load_save(SAVE_ID)
    after = {
        cid: dict(chara.talent)
        for cid, chara in self.cache.character_data.items()
    }
    self.assertEqual(sorted(after), sorted(before), "读档后的角色id")
    changed = sorted(
        (
            self.cache.character_data[cid].adv,
            [
                (t, before[cid].get(t), value)
                for t, value in sorted(after[cid].items())
                if before[cid].get(t) != value
            ],
        )
        for cid in after
        if after[cid] != before[cid]
    )
    self.assertEqual(
        changed,
        [],
        "读档后素质有变化的角色（模板编号, [(素质, 读档前, 读档后)]）",
    )
