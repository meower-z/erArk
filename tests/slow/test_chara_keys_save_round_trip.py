# -*- coding: UTF-8 -*-
"""
角色键的存档、读档与新周目继承
==============================
新游戏里等待一次，再给一名干员写上非默认的值，然后经 save_handle 存档。存档后改掉这些值，再读档。
读档后每名角色的 social.*、life.*、profile.* 键与存档时相同。读出的值也相同。之后再等待一次，时钟往前走。

新周目继承：陷落干员重建后，trust 与对博士的 favorability 取继承选择里的 fallen_social，
按继承选择「干员的好感与信任」一项的比例折算。
"""

import importlib
import shutil
from types import ModuleType
from typing import Any
from unittest import mock

from tests.slow.base import SlowTestCase
from tests.kernel_project import identity

SAVE_ID = "test_chara_keys_save_round_trip"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """


def game(name: str) -> ModuleType:
    """
    导入游戏模块
    Keyword arguments:
    name -- 模块全名
    Return arguments:
    ModuleType -- 模块
    """
    return importlib.import_module(name)


def moved_keys() -> tuple[Any, ...]:
    """
    social.*、life.*、profile.* 的全部角色键
    Return arguments:
    tuple -- relations、chara_life 与 chara_profile 的 KEYS 连在一起
    """
    relations = game("Script.Modules.domains.relations")
    chara_life = game("Script.Modules.domains.chara_life")
    chara_profile = game("Script.Modules.domains.chara_profile")
    return (*relations.KEYS, *chara_life.KEYS, *chara_profile.KEYS)


class CharaKeysSaveRoundTripTest(SlowTestCase):
    """角色键的存档与读档，以及新周目陷落干员的 trust 与 favorability 继承"""

    def test_chara_keys_survive_save_and_load(self) -> None:
        """存档后改掉的值在读档后回到存档时的值"""
        from tests import kernel_data
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        working = game("Script.Modules.gameplay_resolution.working")
        relations = game("Script.Modules.domains.relations")
        chara_life = game("Script.Modules.domains.chara_life")
        chara_profile = game("Script.Modules.domains.chara_profile")
        core = game("Script.Kernel.core")
        instruct(self.world, constant.Instruct.WAIT)
        cid = self.npc(identity.of(1).name)
        with kernel_data.writing():
            relations.trust.set(cid, 12.5)
            relations.favorability.set_item(cid, 0, 30)
            chara_life.borrow_book_id_set.set(cid, {5, 2})
            chara_profile.nick_name.set(cid, "甲")
        keys = moved_keys()
        ids = list(identity.table())
        saved = {
            (c, key.key): working.get(str(c), key.key)
            for c in ids
            for key in keys
        }
        values = {(c, key.key): repr(key(c)) for c in ids for key in keys}
        save_handle.establish_save(SAVE_ID)
        try:
            with kernel_data.writing():
                relations.trust.set(cid, 1)
                chara_life.borrow_book_id_set.set(cid, set())
                chara_profile.nick_name.set(cid, "")
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        self.assertEqual(
            {
                (c, key.key): working.get(str(c), key.key)
                for c in ids
                for key in keys
            },
            saved,
        )
        self.assertEqual(
            {(c, key.key): repr(key(c)) for c in ids for key in keys}, values
        )
        self.assertEqual(relations.trust(cid), 12.5)
        self.assertEqual(chara_life.borrow_book_id_set(cid), {2, 5})
        clock = core.state().clock
        instruct(self.world, constant.Instruct.WAIT)
        self.assertGreater(core.state().clock, clock)
        self.assertEqual(chara_profile.nick_name(cid), "甲")

    def test_fallen_operator_inherits_choice_social(self) -> None:
        """陷落干员的 trust 与对博士的 favorability 取 fallen_social，按继承比例折算"""
        from tests import kernel_data

        relations = game("Script.Modules.domains.relations")
        new_round = game("Script.UI.Panel.new_round")
        npc_template = game("Script.Modules.domains.npc_template")
        cid = next(c for c in identity.table() if npc_template.get(c))
        with kernel_data.writing():
            relations.trust.set(cid, 80)
            relations.favorability.set_item(cid, 0, 70)
        rate = new_round._inherit_rate(4, 1)
        self.assertGreater(rate, 0)
        inherit = {
            "chara_fon_and_trust_count": 1,
            "chara_abi_and_exp_count": 0,
            "chara_hypnosis_count": 0,
            "fallen_social": {str(cid): (50, 30)},
            "abilities": {},
        }
        template = {cid: npc_template.get(cid)}
        with mock.patch.object(npc_template, "table", return_value=template):
            kernel_data.written(new_round._inherit_npc_data, inherit, {cid})
        self.assertEqual(relations.trust(cid), int(50 * rate / 100))
        self.assertEqual(relations.favorability(cid)[0], int(30 * rate / 100))
