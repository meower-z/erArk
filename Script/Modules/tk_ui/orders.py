"""
玩家最近输入的暂存与写入
========================
flow_handle.order_deal 在协议端口收到 Choose 或 InputText 应答后调用 accept，
把玩家输入交给本模块（暂停应答不进入 accept）。
accept 忽略空字符串，把非空输入按先后暂存在 _unsettled 中。
处于结算阶段（core.in_settlement()）时，accept 立即调用 settle 写入当前写缓冲区。
玩家选行动时与一步之外，输入留在 _unsettled 中等待写入。
kernel.StartAction 输入钩子 settle_on_start 在行动开始前调用 settle，把暂存输入写入当前写缓冲区。
kernel.Reset 输入钩子 drop_on_load 在读档（cause 为 "load"）时清空 _unsettled，其余原因时保留。
导入时经 kernel_state.on_settled 登记 settled，存档时由 kernel_state.write 调用，合并 _unsettled 且不清空。
"""

from collections.abc import Mapping

from Script.Kernel import core
from Script.Modules.domains import history
from Script.Modules.save_load import kernel_state

_unsettled: list[str] = []
""" 尚未写入 GameState 的非空玩家输入，旧的在前 """


def accept(order: str) -> None:
    """
    接收一条玩家输入，忽略空字符串并将非空输入追加到 _unsettled。
    处于结算阶段（core.in_settlement()）时立即调用 settle，将其写入当前写缓冲区
    Keyword arguments:
    order -- 玩家输入的字符串
    """
    if order == "":
        return
    _unsettled.append(order)
    if core.in_settlement():
        settle()


def settle() -> None:
    """
    将 _unsettled 中暂存的输入经 history.add_inputs 写入当前写缓冲区并清空 _unsettled。
    _unsettled 为空时不做操作
    """
    if _unsettled:
        history.add_inputs(_unsettled)
        _unsettled.clear()


@kernel_state.on_settled
def settled(game: core.GameState) -> core.GameState:
    """
    返回在 game 的 log.inputs 末尾接上 _unsettled 后的 GameState，不清空 _unsettled
    Keyword arguments:
    game -- 基准 GameState
    Return arguments:
    GameState -- 合并暂存输入后的 GameState，_unsettled 为空时原样返回 game
    """
    return history.with_inputs(game, _unsettled)


@core.input_hook(core.start_action)
def settle_on_start(act: core.Action) -> tuple[core.Action]:
    """
    kernel.StartAction 输入钩子：行动开始函数运行前调用 settle，将暂存输入写入当前写缓冲区
    Keyword arguments:
    act -- 即将开始的行动
    Return arguments:
    tuple -- 原样交给内层的行动元组 (act,)
    """
    settle()
    return (act,)


@core.input_hook(core.reset)
def drop_on_load(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> tuple[core.GameState, Mapping[str, core.JSON]]:
    """
    kernel.Reset 输入钩子：读档（why["cause"] 为 "load"）时清空 _unsettled，其余原因时保留
    Keyword arguments:
    new -- 换入的 GameState
    why -- Reset 原因映射
    Return arguments:
    tuple -- 原样交给内层的参数元组 (new, why)
    """
    if why.get("cause") == "load":
        _unsettled.clear()
    return (new, why)
