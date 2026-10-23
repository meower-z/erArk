"""UI 流程子包，导入角色创建、日常和标题三个流程模块以注册各自的面板"""

from Script.UI.Flow import (
    creator_character_flow,
    normal_flow,
    title_flow,
)

# 导入让各流程模块用 add_panel 注册面板
__all__ = [
    "creator_character_flow",
    "normal_flow",
    "title_flow",
]
