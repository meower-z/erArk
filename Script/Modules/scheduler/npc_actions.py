"""把 NPC AI 的选择结果包装成 Action。

NPC AI 选中的是一个"状态机"编号（一段会替 NPC 决定并写入行动的原有代码），运行后才会写出实际行动。本模块把这个编号装进行动编号为 prepare_npc_action 的 Action 交给调度器；
执行时由 action_execution 运行状态机，再换成实际行动。
"""

from Script.Modules.scheduler.action import Action


def state_machine_action(actor: int, state_machine_id: int, record_absence: bool = False) -> Action:
    """输入角色、状态机编号及缺课记录要求，返回交给执行侧准备的 Action。"""
    return Action("prepare_npc_action", 0, actor, params={"state_machine_id": state_machine_id, "record_absence": record_absence})
