"""
save_load 的 Reset 步骤
======================
换掉整个 GameState（读档、新周目、新游戏）时要做的修补、初始化与投影，按 STEPS 的顺序在 kernel.Reset 的输入钩子里运行。
这时 core.state() 与 game_time.now() 已是换入的 GameState 与它的时钟。
每一步只在 why["cause"] 属于它的 causes 时运行，可以写缓存，返回交给下一步的 GameState。
本模块排在 LOAD_ORDER 的最后，它的输入钩子最先运行。本模块不登记行动、事件或规则。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from Script.Kernel import core

type Step = Callable[[core.GameState, Mapping[str, core.JSON]], core.GameState]


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

    save_handle.install_save(str(why["save"]))
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


def _panel(new: core.GameState, why: Mapping[str, core.JSON]) -> core.GameState:
    """回到场景面板"""
    from Script.Core import cache_control, constant

    cache_control.cache.now_panel_id = constant.Panel.IN_SCENE
    return new


def _session_checks(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """清掉这次还没结束的体检里已检查过的项目：它们属于被换掉的那一局"""
    from Script.UI.Panel import physical_check_and_manage

    physical_check_and_manage._session_checks.clear()
    return new


STEPS: tuple[ResetStep, ...] = (
    ResetStep("install_save", frozenset({"load"}), _install_save),
    ResetStep("exact_stats", frozenset({"load"}), _exact_stats),
    ResetStep("new_round", frozenset({"new_round"}), _new_round),
    ResetStep(
        "project", frozenset({"load", "new_round", "new_game"}), _project
    ),
    ResetStep("repair_installed", frozenset({"load"}), _repair_installed),
    ResetStep("panel", frozenset({"load", "new_round"}), _panel),
    ResetStep(
        "session_checks",
        frozenset({"load", "new_round", "new_game"}),
        _session_checks,
    ),
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
            new = step.run(new, why)
    return (new, why)
