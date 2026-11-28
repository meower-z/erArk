"""
界面的临时状态
==============
界面与面板在本进程里的临时状态，包括当前面板编号以及几个面板自己的筛选、排序与列表状态。
它们不属于游戏状态，不进 GameState，也不随存档。读档与新游戏通常不重设它们，
例外是读档与新周目时面板切回场景面板并关闭隐奸中显示非H指令的开关。
玩家要长期保留的选择不在这里，存放在全局设置（normal_config.system_setting）里。
"""

now_panel_id: int = 0
""" 当前游戏面板id """
show_non_h_in_hidden_sex: bool = False
""" 是否在隐奸中显示非H类指令 """
makefood_filter_type: list[int] = []
""" 做饭筛选：菜谱类型列表，空列表表示不筛选 """
makefood_filter_difficulty: int = -1
""" 做饭筛选：难度档位（-1不限，0简单0-3，1中等4-6，2困难7+） """
makefood_filter_time: int = -1
""" 做饭筛选：时间档位（-1不限，0快速0-30，1中等31-60，2耗时61+） """
makefood_sort_type: int = 0
""" 做饭排序：排序维度（0无，1难度，2时间，3类型） """
makefood_sort_order: int = 0
""" 做饭排序：排序顺序（0升序，1降序） """
makefood_data: dict[str, int] = {}
"""
做饭区可制作的菜谱数据（延迟创建：仅记录可制作的菜谱id，食物对象在制作时才创建）
食谱id(str):食谱id(int)
"""
now_show_book_cid_of_type: dict[int, list] = {}
""" 当前展示的可借阅书籍，类别id：书籍id列表 """
back_save_panel: bool = False
""" 退出存档面板 """
npc_image_index: int = 0
""" 当前绘制人物列表的开始值 """
all_npc_position_panel_select_type: int = 0
""" 所有npc位置面板筛选类型 """
all_npc_position_panel_move_type: int = 0
""" 所有npc位置面板移动类型 """
pregnancy_panel_sort_type: int = 0
""" 怀孕总览面板排序类型（0按阶段降序，1按阶段升序） """
pregnancy_panel_filter_type: int = 0
""" 怀孕总览面板筛选类型（0全部，其余为阶段枚举值） """
