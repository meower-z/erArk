"""
结算效果统一注册入口。导入本模块会依次加载 default（同时加载 item_effect）、default_cloth
与 Second_effect，从而注册全部一阶段与二阶段结算效果。游戏启动流程与完整测试世界导入本模块。
"""

from Script.Settle import default, default_cloth, Second_effect

__all__ = ["default", "default_cloth", "Second_effect"]
