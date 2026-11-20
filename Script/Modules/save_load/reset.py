"""
save_load 的 Reset 步骤
======================
换掉整个 GameState（读档、新周目、新游戏）时要做的修补、初始化与投影，按 STEPS 的顺序在 kernel.Reset 的输入钩子里运行。
这时 core.state() 与 game_time.now() 已是换入的 GameState 与它的时钟。
每一步只在 why["cause"] 属于它的 causes 时运行，可以写缓存，返回交给下一步的 GameState。
读档时另跑一次各模块用 repair 登记的旧存档修补（面板打开时只读，旧存档的修补放在这里）。
本模块排在 LOAD_ORDER 的最后，它的输入钩子最先运行。本模块不登记行动、事件或规则。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

type Step = Callable[[core.GameState, Mapping[str, core.JSON]], core.GameState]
type Repair = Callable[[], None]

_repairs: list[Repair] = []
""" 读档后依次运行的旧存档修补 """


def repair(fn: Repair) -> Repair:
    """
    装饰器：登记一个旧存档修补，读档时（装好缓存之后）每次 Reset 运行一次；它只写缓存
    Keyword arguments:
    fn -- 修补函数
    Return arguments:
    Repair -- 原样交回 fn
    """
    _repairs.append(fn)
    return fn


@dataclass(frozen=True)
class ResetStep:
    """Reset 的一步"""

    name: str
    """ 步骤名 """
    causes: frozenset[str]
    """ 运行这一步的 why["cause"] """
    run: Step
    """ 这一步：读换入的 GameState 与 why，可以写缓存，返回下一步的 GameState """


def _install_save(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """存档的缓存装进游戏缓存"""
    from Script.Core import save_handle

    version = why.get("version", 0)
    if not isinstance(version, int):
        raise TypeError(f"version {version!r} is not an int")
    save_handle.install_save(str(why["save"]), version)
    return new


def _exact_stats(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """装好的缓存里 float 数值换成精确值"""
    from Script.Core import save_handle

    save_handle.exact_stats()
    return new


def _new_round(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """按继承选择建新周目的缓存"""
    from Script.UI.Panel import new_round

    inherit = why["inherit"]
    if not isinstance(inherit, Mapping):
        raise TypeError(f"inherit {inherit!r} is not a mapping")
    new_round.setup(inherit)
    return new


def _project(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """没有角色时由缓存投影出角色"""
    from Script.Modules.gameplay_resolution import actions

    return actions.project(new)


def _repair_installed(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """读档时，系统设置 14（是否开启游戏状态自检）开着就运行读档修复（run_load_repair）"""
    from Script.Core import save_handle

    save_handle.repair_installed()
    return new


def _repairs_registered(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """依次运行 repair 登记的旧存档修补"""
    for fn in _repairs:
        fn()
    return new


def _reconcile_roster_data(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """每个角色的数据只留在一处，roster.offstage 里缓存已没有的角色的数据丢掉（working.reconcile）"""
    return working.reconcile(new)


def _panel(new: core.GameState, why: Mapping[str, core.JSON]) -> core.GameState:
    """回到场景面板"""
    from Script.Core import cache_control, constant

    cache_control.cache.now_panel_id = constant.Panel.IN_SCENE
    return new


STEPS: tuple[ResetStep, ...] = (
    ResetStep("install_save", frozenset({"load"}), _install_save),
    ResetStep("exact_stats", frozenset({"load"}), _exact_stats),
    ResetStep("new_round", frozenset({"new_round"}), _new_round),
    ResetStep(
        "project", frozenset({"load", "new_round", "new_game"}), _project
    ),
    ResetStep("repair_installed", frozenset({"load"}), _repair_installed),
    ResetStep("repairs", frozenset({"load"}), _repairs_registered),
    ResetStep(
        "reconcile_roster_data",
        frozenset({"load", "new_round", "new_game"}),
        _reconcile_roster_data,
    ),
    ResetStep("panel", frozenset({"load", "new_round"}), _panel),
)
""" Reset 的步骤，按运行顺序 """


@core.input_hook(core.reset)
def run_steps(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> tuple[core.GameState, Mapping[str, core.JSON]]:
    """
    依次运行 cause 属于它的步骤
    Keyword arguments:
    new -- 换入的 GameState
    why -- 换入的原因，{"cause": ...} 加上这个原因的键
    Return arguments:
    tuple -- 最后一步返回的 GameState 与 why
    """
    for step in STEPS:
        if why.get("cause") in step.causes:
            with working.based_on(new) as buffer:
                stepped = step.run(new, why)
                effects = buffer.effects()
            new = core.preview(stepped, effects)
    return (new, why)
