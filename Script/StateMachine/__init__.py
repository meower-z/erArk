"""角色状态机包，导入注册状态机的模块"""

from Script.StateMachine import default
from Script.System.Dormitory_System import dormitory_manager_system

# 导入让两个模块用 add_state_machine 注册状态机
__all__ = [
    "default",
    "dormitory_manager_system",
]
