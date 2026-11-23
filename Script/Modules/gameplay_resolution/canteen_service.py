"""
食堂上架服务（canteen_service）
===============================
提供将玩家背包中的正常调味食物放入食堂取餐区的逻辑。
本模块不直接导入界面模块，供指令处理入口调用。
提示文本通过 ui_hooks.emit_notice 发出。
"""

from types import FunctionType

from Script.Core import get_text
from Script.Modules.domains import identity, inventory, kitchen
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def put_selfmade_food_in() -> None:
    """
    将角色 0 背包中正常调味的食物放入食堂取餐区。
    函数按背包顺序取出 special_seasoning 为 0 的食物，将其上架到对应食谱编号的食堂货架。
    其他调味类型的食物留在背包中。
    开场提示与逐份上架提示通过 ui_hooks.emit_notice 按文本宽度发出，不等待玩家确认。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值，直接更新玩家食物背包与食堂货架
    """
    character_data: identity.Identity = identity.of(0)

    id_list_normal = []
    for i, food_data in inventory.foods(0).items():
        if food_data.special_seasoning == 0:
            id_list_normal.append(i)

    if len(id_list_normal):
        info_draw_text = _(
            "{0}开始将身上没有调味的食物放进食堂取餐区里\n"
        ).format(character_data.name)
    else:
        info_draw_text = _("{0}身上没有正常调味的食物\n").format(
            character_data.name
        )
    ui_hooks.emit_notice(info_draw_text, wait=False, use_text_width=True)

    for uid in id_list_normal:
        food_data = inventory.foods(0)[uid]
        recipes_id = str(food_data.recipe)
        food_name = food_data.name
        kitchen.stock(recipes_id, inventory.take_food(0, uid))
        ui_hooks.emit_notice(
            _("{0}已放入食堂\n").format(food_name),
            wait=False,
            use_text_width=True,
        )
