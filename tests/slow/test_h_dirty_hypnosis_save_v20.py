# -*- coding: UTF-8 -*-
"""
存档版本 20 起七个键的往返与续玩：h.meters、h.shoot_position、h.state、body.dirty、
mind.hypnosis、history.first_record 与 history.first_record_history
===================================================================================
开新游戏后给玩家与一名成年干员写入七个键的代表值（含洗浴按比例保留产生的 Fraction 精确数值），存档到临时槽位：
- save.json 版本不低于 20，含全部七个键与 "$frac" 标签；
- 角色身份对象上没有这十个旧属性；
- 读档后内核状态与存档前 JSON 逐字节相同，洗浴保留后的精液量保持精确 Num（无 float）且继续吸收后仍为精确 Num；
  再存一次 save.json（除 head 外）不变；
- 存档后接着等 60 分钟与读档后接着等 60 分钟（同随机种子）内核状态、花名册、行动序列与随机数状态完全相同。
"""

import hashlib
import importlib
import json
import os
import random
import tempfile
from fractions import Fraction
from typing import Any
from unittest import mock

from tests.slow.base import SlowTestCase
from tests.kernel_project import identity

SLOT = "h_dirty_hypnosis_v20"
SEED = 20261121


def _mod(name: str) -> Any:
    return importlib.import_module(name)


class HDirtyHypnosisSaveV20Test(SlowTestCase):
    """v20 存档往返、旧属性移除、洗浴后吸收精确数值与 60 分钟续玩一致性"""

    time_limit = 900

    def setUp(self) -> None:
        """开新游戏，把存档目录换到临时目录"""
        super().setUp()
        index = _mod("Script.Modules.save_load.index")
        kernel = _mod("Script.Kernel.core")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))
        self.started: list[tuple[int, str, str]] = []
        saved = kernel._bodies["kernel.StartAction"]

        def spy(act: Any) -> Any:
            self.started.append((kernel.state().clock, act.who, act.action_id))
            return saved(act)

        kernel._bodies["kernel.StartAction"] = spy
        self.addCleanup(kernel._bodies.__setitem__, "kernel.StartAction", saved)

    def _wait(self, minutes: int) -> None:
        constant = _mod("Script.Core.constant")
        kernel = _mod("Script.Kernel.core")
        player_pick = _mod("Script.Modules.tk_ui.player_pick")
        handle_instruct = _mod("Script.System.Instruct_System.handle_instruct")

        def wait() -> None:
            handle_instruct.handle_instruct(constant.Instruct.WAIT)

        start = kernel.state().clock
        with mock.patch.object(player_pick, "chooser", wait):
            while kernel.state().clock < start + minutes:
                kernel.step()

    def _load(self, save_id: str) -> None:
        from Script.UI.Moudle import view

        constant = _mod("Script.Core.constant")
        save_handle = _mod("Script.Core.save_handle")
        kernel = _mod("Script.Kernel.core")
        load_order = _mod("Script.Modules.load_order")
        save_handle.input_load_save(save_id)
        view.now_panel_id = constant.Panel.IN_SCENE
        kernel.load(load_order.LOAD_ORDER)

    def _state_json(self) -> str:
        kernel = _mod("Script.Kernel.core")
        kernel_state = _mod("Script.Modules.save_load.kernel_state")
        return json.dumps(kernel_state.encode(kernel.state()), sort_keys=True)

    def _digest(self) -> tuple[object, ...]:
        kernel = _mod("Script.Kernel.core")
        rng = hashlib.sha256(repr(random.getstate()).encode()).hexdigest()
        return (
            self._state_json(),
            tuple(kernel.state().characters),
            tuple(self.started),
            rng,
        )

    def test_v20_round_trip_and_continuation(self) -> None:
        """七个键写入、洗浴精确保留、存读往返、吸收后仍精确与 60 分钟续玩一致，且旧属性已删除"""
        save_handle = _mod("Script.Core.save_handle")
        game_type = _mod("Script.Core.game_type")
        index = _mod("Script.Modules.save_load.index")
        game_time = _mod("Script.Design.game_time")
        settle_default = _mod("Script.Settle.default")
        realtime_settle = _mod("Script.Settle.realtime_settle")
        h_meters = _mod("Script.Modules.domains.h_meters")
        h_state = _mod("Script.Modules.domains.h_state")
        dirty = _mod("Script.Modules.domains.dirty")
        hypnosis = _mod("Script.Modules.domains.hypnosis")
        first_record = _mod("Script.Modules.domains.first_record")
        kernel_data = _mod("tests.kernel_data")

        npc_id = self.npc("阿米娅")
        now = game_time.now()
        with kernel_data.writing():
            h_meters.set(
                0, eja=Fraction(7, 2), semen=Fraction(199, 2), extra_semen=15
            )
            h_meters.set_shoot_position(2)
            h_state.set(npc_id, bondage=1, endure_not_shot_count=2)
            with dirty.editing(npc_id) as d:
                d.body_semen[6][1] = 33
                d.body_semen[6][3] = 33
                d.body_semen[7][1] = 21
                d.body_semen[7][3] = 21
                d.body_semen[8][1] = 25
                d.body_semen[8][3] = 25
                d.absorbed_total_semen = Fraction(3, 2)
            settle_default.handle_dirty_reset_in_shower(
                npc_id, 5, game_type.CharacterStatusChange(), now
            )
            with dirty.editing(npc_id) as d:
                d.condom_decoration[(0, 0)] = [6]
            hypnosis.set(npc_id, hypnosis_degree=40, roleplay=(1,))
            first_record.set(npc_id, first_meet=0, day_first_meet=0)
            first_record.restore_for_new_round(
                npc_id,
                1,
                {
                    str(npc_id): {
                        "current": {
                            "first_kiss_id": 0,
                            "first_kiss_time": game_time.minutes(now),
                        },
                        "history": {},
                    }
                },
            )

        for attr in (
            "eja_point_max",
            "eja_point",
            "semen_point_max",
            "semen_point",
            "tem_extra_semen_point",
            "h_state",
            "dirty",
            "hypnosis",
            "first_record",
            "first_record_history",
        ):
            self.assertFalse(hasattr(identity.of(npc_id), attr))

        before_save = self._state_json()
        save_handle.establish_save(SLOT)
        path = os.path.join(self.folder, SLOT, index.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            first_file = json.load(f)
        self.assertGreaterEqual(first_file["version"], 20)
        raw_text = json.dumps(first_file)
        self.assertIn('"$frac"', raw_text)
        for key in (
            h_meters.KEY,
            h_meters.SHOOT_POSITION,
            h_state.KEY,
            dirty.KEY,
            hypnosis.KEY,
            first_record.KEY,
            first_record.HISTORY,
        ):
            self.assertIn(key, raw_text)

        random.seed(SEED)
        self.started.clear()
        self._wait(60)
        played = self._digest()

        self._load(SLOT)
        self.assertEqual(self._state_json(), before_save)

        random.seed(SEED)
        self.started.clear()
        self._wait(60)
        replayed = self._digest()
        self.assertEqual(played, replayed)

        self._load(SLOT)
        reloaded_dirty = dirty.view(npc_id)
        for part_id in (6, 7, 8):
            self.assertIsInstance(
                reloaded_dirty.body_semen[part_id][1], (int, Fraction)
            )
            self.assertNotIsInstance(
                reloaded_dirty.body_semen[part_id][1], float
            )
        save_handle.establish_save(SLOT)
        with open(path, encoding="utf-8") as f:
            second_file = json.load(f)
        first_file.pop("head")
        second_file.pop("head")
        self.assertEqual(second_file, first_file)
        with kernel_data.writing():
            realtime_settle.semen_absorb(npc_id, 5, 7)
        absorbed_dirty = dirty.view(npc_id)
        self.assertIsInstance(absorbed_dirty.body_semen[7][1], (int, Fraction))
        self.assertNotIsInstance(absorbed_dirty.body_semen[7][1], float)
        self.assertIsInstance(
            absorbed_dirty.absorbed_total_semen, (int, Fraction)
        )
        self.assertNotIsInstance(absorbed_dirty.absorbed_total_semen, float)
