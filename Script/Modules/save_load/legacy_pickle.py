"""
save_load 的旧存档读取
======================
受限的旧存档 pickle 读取器。旧槽位的文件 "0"（存档头）与文件 "1"（缓存）经 LegacyUnpickler 读取。
find_class 只放行 VALUES 中的值类型与 datetime.datetime，其余 Script.* 全局名解为 LegacyObject，
其他全局名一律抛 pickle.UnpicklingError。白名单之外的全局名不会被导入或调用。
本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

import datetime
import fractions
import pickle
import uuid
from collections.abc import Callable
from functools import partial
from typing import IO, Any

type Datetimes = Callable[..., datetime.datetime]
""" 按 pickle 构造参数构造 datetime.datetime 对象的构造函数类型 """


class LegacyObject:
    """旧存档游戏对象反序列化后的属性容器"""

    def __new__(cls, *args: object) -> "LegacyObject":
        """
        创建空属性容器；pickle 带构造参数调用时抛 pickle.UnpicklingError
        Keyword arguments:
        args -- pickle 传入的构造参数
        """
        if args:
            raise pickle.UnpicklingError(
                f"legacy object built with arguments {args!r}"
            )
        return super().__new__(cls)

    def __setstate__(self, state: object) -> None:
        """
        接收 pickle 状态：接受字典，或 __slots__ 类的 (dict 或 None, slots dict) 元组；
        其余状态抛 pickle.UnpicklingError
        Keyword arguments:
        state -- pickle 状态对象
        """
        parts = state if isinstance(state, tuple) else (state,)
        for part in parts:
            if part is None:
                continue
            if not isinstance(part, dict):
                raise pickle.UnpicklingError(
                    f"legacy object state {type(part).__name__}"
                )
            vars(self).update(part)


def _game_time(name: str) -> Any:
    from Script.Design import game_time

    return getattr(game_time, name)


def _medical(name: str) -> Any:
    from Script.System.Medical_System import medical_constant

    return getattr(medical_constant, name)


MEDICAL = "Script.System.Medical_System.medical_constant"
""" 医疗枚举与每日计数数据类所在的模块名 """
MEDICAL_VALUES = (
    "MedicalPatientState",
    "MedicalPatientPersonality",
    "MedicalDoctorProfession",
    "MedicalPatientPriority",
    "MedicalMedicineResource",
    "MedicalDailyCounters",
)
""" 旧存档中按原类型加载的 medical_constant 类名 """
VALUES: dict[tuple[str, str], Callable[[], Any]] = {
    ("Script.Design.game_time", "GameTime"): partial(_game_time, "GameTime"),
    ("uuid", "UUID"): lambda: uuid.UUID,
    ("fractions", "Fraction"): lambda: fractions.Fraction,
    **{(MEDICAL, name): partial(_medical, name) for name in MEDICAL_VALUES},
}
""" 旧存档允许按原类型加载的值类型表：(模块名, 类名) 到返回该类的函数 """


class LegacyUnpickler(pickle.Unpickler):
    """读取旧存档文件的受限 Unpickler"""

    def __init__(self, file: IO[bytes], datetimes: Datetimes) -> None:
        """
        Keyword arguments:
        file -- 二进制文件对象
        datetimes -- 反序列化 datetime.datetime 时使用的构造函数
        """
        super().__init__(file)
        self.datetimes = datetimes
        """ 用于构造反序列化出的 datetime.datetime 的函数 """

    def find_class(self, module: str, name: str) -> Any:
        """
        解析允许的全局名：datetime.datetime 返回 datetimes，VALUES 中的项返回对应值类型，
        其余 Script 或 Script.* 返回 LegacyObject，其他全局名抛 pickle.UnpicklingError
        Keyword arguments:
        module -- 模块名
        name -- 全局名
        Return arguments:
        Any -- 允许的类或构造函数
        """
        if (module, name) == ("datetime", "datetime"):
            return self.datetimes
        value = VALUES.get((module, name))
        if value is not None:
            return value()
        if module == "Script" or module.startswith("Script."):
            return LegacyObject
        raise pickle.UnpicklingError(f"{module}.{name} is not allowed")


def _game_datetime(*args: Any) -> datetime.datetime:
    from Script.Design import game_time

    return game_time.to_game_time(datetime.datetime(*args))


def head(path: str) -> dict[str, Any]:
    """
    读取旧存档的存档头文件 "0"，时间保持普通 datetime.datetime；顶层值不是 dict 时抛 pickle.UnpicklingError
    Keyword arguments:
    path -- 文件路径
    Return arguments:
    dict -- 存档头字典
    """
    with open(path, "rb") as f:
        loaded = LegacyUnpickler(f, datetime.datetime).load()
    if not isinstance(loaded, dict):
        raise pickle.UnpicklingError(f"{path} does not hold a head")
    return loaded


def cache(path: str) -> dict[str, Any]:
    """
    读取旧存档的缓存文件 "1" 并返回其属性字典，datetime 经 game_time.to_game_time 转为游戏时间；
    顶层值不是 LegacyObject 时抛 pickle.UnpicklingError
    Keyword arguments:
    path -- 文件路径
    Return arguments:
    dict -- 属性名到值
    """
    with open(path, "rb") as f:
        loaded = LegacyUnpickler(f, _game_datetime).load()
    if not isinstance(loaded, LegacyObject):
        raise pickle.UnpicklingError(f"{path} does not hold a game cache")
    return vars(loaded)
