"""
结算效果与指令统一注册入口。导入本模块会依次加载 default（同时加载 item_effect）、
default_cloth 与 Second_effect，注册全部一阶段与二阶段结算效果。本模块同时加载
handle_instruct，填充结算逻辑与 NPC AI 读取的指令注册表。游戏启动流程与完整测试
世界等入口导入本模块。
"""

from Script.Settle import default, default_cloth, Second_effect
from Script.System.Instruct_System import handle_instruct

__all__ = ["default", "default_cloth", "Second_effect", "handle_instruct"]
