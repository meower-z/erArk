# -*- coding: UTF-8 -*-
"""
旧存档受限反序列化测试（legacy_pickle）
=======================================
- 含 os.system、posix.system、subprocess.Popen、builtins.eval、builtins.exec、
  builtins.getattr 或 copyreg._reconstructor 的文件抛 pickle.UnpicklingError，且不执行任何代码。
- 带构造参数调用 Script.* 全局名抛 pickle.UnpicklingError。
- 旧的 Cache、Character 与 Rhodes_Island 对象加载为 LegacyObject 并保留属性与共享引用；
  __slots__ 类的对象状态同样可加载。
- Fraction、UUID、GameTime 与医疗枚举、每日计数类按各自原类型加载。
- 文件 "0" 保持普通 datetime；文件 "1" 把 datetime 转为游戏时间；
  非字典存档头与非 LegacyObject 缓存均抛 pickle.UnpicklingError。
"""

import datetime
import io
import os
import pickle
import tempfile
import uuid
from fractions import Fraction
from unittest import mock

from Script.Design import game_time
from Script.Modules.save_load import legacy_pickle
from Script.Modules.save_load.legacy_pickle import LegacyObject
from Script.System.Medical_System import medical_constant as mc
from tests import legacy_save
from tests.fast.base import FastTestCase

REFUSED = (
    ("os", "system"),
    ("posix", "system"),
    ("subprocess", "Popen"),
    ("builtins", "eval"),
    ("builtins", "exec"),
    ("builtins", "getattr"),
    ("copyreg", "_reconstructor"),
)
""" 恶意 pickle 文件可能用来执行代码的全局名列表 """


def load(data: bytes) -> object:
    """
    用 LegacyUnpickler 反序列化字节串，datetime 保持普通 datetime
    Keyword arguments:
    data -- pickle 字节串
    Return arguments:
    object -- 反序列化结果
    """
    return legacy_pickle.LegacyUnpickler(
        io.BytesIO(data), datetime.datetime
    ).load()


def call(module: str, name: str, arg: str) -> bytes:
    """
    构造 protocol 0 的 pickle 字节串，普通 Unpickler 加载时会调用 module.name(arg)
    Keyword arguments:
    module -- 模块名
    name -- 全局名
    arg -- 字符串参数
    Return arguments:
    bytes -- pickle 字节串
    """
    return f"c{module}\n{name}\n(V{arg}\ntR.".encode()


class Payload:
    """序列化结果在普通 Unpickler 加载时会执行 os.system 的载荷对象"""

    def __init__(self, command: str) -> None:
        """
        Keyword arguments:
        command -- 壳命令文本
        """
        self.command = command

    def __reduce__(self) -> tuple[object, tuple[str]]:
        """返回 os.system 与命令参数元组"""
        return os.system, (self.command,)


class RefusalTest(FastTestCase):
    """拒绝白名单之外全局名的测试"""

    def setUp(self) -> None:
        """准备临时目录，mark 为载荷成功执行时会创建的文件路径"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.mark = os.path.join(folder, "ran")

    def test_code_globals_are_refused(self) -> None:
        """REFUSED 中每个全局名都抛 pickle.UnpicklingError 且不创建标记文件"""
        for module, name in REFUSED:
            with self.subTest(f"{module}.{name}"):
                with self.assertRaisesRegex(
                    pickle.UnpicklingError, f"{module}.{name}"
                ):
                    load(call(module, name, f"touch {self.mark}"))
        self.assertFalse(os.path.exists(self.mark))

    def test_reduce_payloads_are_refused(self) -> None:
        """
        单独、字典内与旧缓存对象内的 __reduce__ 载荷在各 pickle 协议下都抛 pickle.UnpicklingError，
        且不执行命令
        """
        payload = Payload(f"touch {self.mark}")
        for value in (
            payload,
            {"x": [payload]},
            legacy_save.old("Cache", npc_tem_data={1: payload}),
        ):
            for protocol in (0, 2, pickle.HIGHEST_PROTOCOL):
                with self.subTest(protocol=protocol, value=type(value)):
                    with legacy_save.old_classes():
                        data = pickle.dumps(value, protocol=protocol)
                    with self.assertRaises(pickle.UnpicklingError):
                        load(data)
        self.assertFalse(os.path.exists(self.mark))

    def test_script_global_with_arguments_is_refused(self) -> None:
        """带构造参数调用 Script.* 全局名抛 pickle.UnpicklingError"""
        data = call("Script.Core.save_handle", "establish_save", "99")
        with self.assertRaisesRegex(pickle.UnpicklingError, "arguments"):
            load(data)

    def test_bad_state_is_refused(self) -> None:
        """LegacyObject 收到非字典状态时抛 pickle.UnpicklingError"""
        with self.assertRaises(pickle.UnpicklingError):
            LegacyObject().__setstate__([1])


class LegacyObjectTest(FastTestCase):
    """旧存档游戏对象加载为 LegacyObject 的测试"""

    def test_old_cache_loads_as_bags(self) -> None:
        """Cache、Character 与 Rhodes_Island 加载为 LegacyObject，共享字典保持同一引用"""
        shared = {"semen": [1, 2]}
        chara = legacy_save.old("Character", name="甲", a=shared, b=shared)
        island = legacy_save.old("Rhodes_Island", people_max=9)
        cache = legacy_save.old(
            "Cache", character_data={1: chara}, rhodes_island=island
        )
        loaded = load(legacy_save.dumps(cache))
        assert isinstance(loaded, LegacyObject)
        got = vars(loaded)["character_data"][1]
        self.assertIs(type(got), LegacyObject)
        self.assertEqual(vars(got)["name"], "甲")
        self.assertIs(vars(got)["a"], vars(got)["b"])
        self.assertEqual(vars(vars(loaded)["rhodes_island"]), {"people_max": 9})

    def test_slots_state_loads(self) -> None:
        """带 __slots__ 的 Script.* 类对象反序列化后保留各槽位属性"""
        slotted = type(
            "Mask",
            (),
            {
                "__module__": "Script.Core.game_type",
                "__qualname__": "Mask",
                "__slots__": ("_mask", "_known_bits"),
            },
        )
        mask = slotted()
        mask._mask, mask._known_bits = 3, 7
        with mock.patch("Script.Core.game_type.Mask", slotted, create=True):
            data = pickle.dumps(mask)
        self.assertEqual(vars(load(data)), {"_mask": 3, "_known_bits": 7})


class ValuesTest(FastTestCase):
    """白名单值类型保持原类型的测试"""

    def test_values_keep_their_classes(self) -> None:
        """Fraction、UUID、GameTime、医疗枚举与每日计数往返后保持原类型与原值"""
        counters = mc.MedicalDailyCounters(discharged_today=2)
        values = [
            Fraction(7, 3),
            uuid.UUID(int=5),
            game_time.GameTime(2024, 6, 6, 7, 8),
            mc.MedicalPatientState.HOSPITALIZED,
            mc.MedicalPatientPriority.NORMAL,
            counters,
        ]
        loaded = load(pickle.dumps(values))
        assert isinstance(loaded, list)
        self.assertEqual([type(v) for v in loaded], [type(v) for v in values])
        self.assertEqual(loaded, values)


class FilesTest(FastTestCase):
    """legacy_pickle.head 与 legacy_pickle.cache 的文件读写测试"""

    def setUp(self) -> None:
        """创建存放测试文件的临时目录"""
        super().setUp()
        self.folder = self.enterContext(tempfile.TemporaryDirectory())

    def write(self, name: str, value: object) -> str:
        """
        把 value 序列化写入临时目录中的指定文件
        Keyword arguments:
        name -- 文件名
        value -- 待序列化的值
        Return arguments:
        str -- 文件路径
        """
        path = os.path.join(self.folder, name)
        with open(path, "wb") as f:
            f.write(legacy_save.dumps(value))
        return path

    def test_head_keeps_plain_datetime(self) -> None:
        """文件 "0" 读出存档头字典，其中的 datetime 保持普通 datetime"""
        when = datetime.datetime(2025, 1, 2, 3, 4)
        head = legacy_pickle.head(self.write("0", {"save_time": when}))
        self.assertIs(type(head["save_time"]), datetime.datetime)
        self.assertEqual(head["save_time"], when)

    def test_cache_turns_datetime_into_game_time(self) -> None:
        """文件 "1" 读出属性字典，其中的 datetime 经 game_time.to_game_time 转为游戏时间"""
        when = datetime.datetime(2025, 1, 2, 3, 4)
        cache = legacy_save.old("Cache", born=when)
        loaded = legacy_pickle.cache(self.write("1", cache))
        self.assertEqual(loaded["born"], game_time.to_game_time(when))
        self.assertIs(type(loaded["born"]), type(game_time.to_game_time(when)))

    def test_wrong_top_values_are_refused(self) -> None:
        """非字典的文件 "0" 与非游戏对象的文件 "1" 都抛 pickle.UnpicklingError"""
        with self.assertRaises(pickle.UnpicklingError):
            legacy_pickle.head(self.write("0", [1]))
        with self.assertRaises(pickle.UnpicklingError):
            legacy_pickle.cache(self.write("1", {"a": 1}))
