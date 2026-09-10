"""将 NPC 选定的行动准备工作表示为普通 Action。"""

from Script.Modules.scheduler.action import Action


def state_machine_action(actor: int, state_machine_id: int, record_absence: bool = False) -> Action:
    """输入角色、状态机编号及缺课记录要求，返回交给执行侧准备的 Action。"""
    return Action("prepare_npc_action", 0, actor, params={"state_machine_id": state_machine_id, "record_absence": record_absence})
