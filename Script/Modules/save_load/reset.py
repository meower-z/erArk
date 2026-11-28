"""
save_load 的 Reset 步骤
=======================
换掉整个 GameState（读档、新周目、新游戏）时要做的修补、初始化与投影，
按 STEPS 的顺序在 kernel.Reset 的输入钩子里运行。
这时 core.state() 与 game_time.now() 已是换入的 GameState 与它的时钟。
每一步只在 why["cause"] 属于它的 causes 时运行，经 working 缓冲区写游戏状态，
返回交给下一步的 GameState。
读档时另跑一次各模块用 repair 登记的旧存档修补（面板打开时只读，旧存档的修补放在这里）。
new_round 与 panel 两步须由界面经 frontend 登记，否则在任何步骤运行前报 RuntimeError。
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
_frontend: dict[str, Step] = {}
""" 界面登记的步骤映射，键为 STEPS 中的步骤名，值为步骤函数 """


def repair(fn: Repair) -> Repair:
    """
    装饰器：登记一个旧存档修补，读档时（完成存档导入与投影之后）每次 Reset 运行一次，
    经 working 缓冲区写游戏状态
    Keyword arguments:
    fn -- 修补函数
    Return arguments:
    Repair -- 原样交回 fn
    """
    _repairs.append(fn)
    return fn


def frontend(name: str) -> Callable[[Step], Step]:
    """
    返回把步骤函数登记到 _frontend[name] 的装饰器。
    同名步骤重复登记时，后登记的函数会覆盖先登记的函数。
    Keyword arguments:
    name -- STEPS 中的步骤名
    Return arguments:
    Callable -- 登记步骤函数并原样交回该函数的装饰器
    """

    def register(fn: Step) -> Step:
        _frontend[name] = fn
        return fn

    return register


@dataclass(frozen=True)
class _FrontendStep:
    name: str

    def __call__(
        self, new: core.GameState, why: Mapping[str, core.JSON]
    ) -> core.GameState:
        return _frontend[self.name](new, why)


@dataclass(frozen=True)
class ResetStep:
    """Reset 的一步"""

    name: str
    """ 步骤名 """
    causes: frozenset[str]
    """ 运行这一步的 why["cause"] """
    run: Step
    """ 这一步：读换入的 GameState 与 why，可经 working 写游戏状态，返回下一步的 GameState """


def _install_save(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """调用 save_handle.install_save 导入存档数据并执行读档迁移"""
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


def _settle_player_target(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """读档时按当前场景在场角色重定玩家的交互对象（character_behavior.settle_player_target）"""
    from Script.Design import character_behavior

    character_behavior.settle_player_target()
    return new


STEPS: tuple[ResetStep, ...] = (
    ResetStep("install_save", frozenset({"load"}), _install_save),
    ResetStep("exact_stats", frozenset({"load"}), _exact_stats),
    ResetStep(
        "new_round", frozenset({"new_round"}), _FrontendStep("new_round")
    ),
    ResetStep(
        "project", frozenset({"load", "new_round", "new_game"}), _project
    ),
    ResetStep(
        "reconcile_projected", frozenset({"load"}), _reconcile_roster_data
    ),
    ResetStep("repair_installed", frozenset({"load"}), _repair_installed),
    ResetStep("repairs", frozenset({"load"}), _repairs_registered),
    ResetStep(
        "reconcile_roster_data",
        frozenset({"load", "new_round", "new_game"}),
        _reconcile_roster_data,
    ),
    ResetStep(
        "settle_player_target", frozenset({"load"}), _settle_player_target
    ),
    ResetStep(
        "panel", frozenset({"load", "new_round"}), _FrontendStep("panel")
    ),
)
""" Reset 的步骤，按运行顺序 """


@core.input_hook(core.reset)
def run_steps(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> tuple[core.GameState, Mapping[str, core.JSON]]:
    """
    先检查当前 cause 命中的界面步骤是否均已登记，缺失则在运行任何步骤前报 RuntimeError。
    校验通过后，按 STEPS 顺序依次运行当前 cause 命中的各步骤。
    Keyword arguments:
    new -- 换入的 GameState
    why -- 换入的原因，{"cause": ...} 加上这个原因的键
    Return arguments:
    tuple -- 最后一步返回的 GameState 与 why
    """
    steps = [step for step in STEPS if why.get("cause") in step.causes]
    for step in steps:
        if (
            isinstance(step.run, _FrontendStep)
            and step.run.name not in _frontend
        ):
            raise RuntimeError(
                f"no frontend registered the Reset step {step.run.name!r}"
            )
    for step in steps:
        with working.based_on(new) as buffer:
            stepped = step.run(new, why)
            effects = buffer.effects()
        new = core.preview(stepped, effects)
    return (new, why)
