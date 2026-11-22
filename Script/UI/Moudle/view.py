"""
界面的临时状态
==============
Tk 界面在本进程里的临时状态：当前面板、鼠标与逐字输出、输入历史的浏览，以及几个面板自己的筛选、排序与列表。
它们不属于游戏状态，不进 GameState，也不随存档。读档与新游戏不重设它们，例外只有两处：
读档与新周目时面板回到场景面板、隐奸中显示非H指令的开关关掉，读档时鼠标状态从头开始。
玩家要长期保留的选择不在这里，在全局设置（normal_config.system_setting）里。
"""


class WFrameMouse:
    """鼠标状态结构体"""

    w_frame_up: int = 2
    """ 逐字输出状态 """
    mouse_right: int = 0
    """ 鼠标右键按下 """
    w_frame_lines_up: int = 2
    """ 逐行输出状态 """
    w_frame_re_print: int = 0
    """ 再次载入游戏界面 """
    w_frame_lines_state: int = 2
    """ 逐行输出状态 """
    w_frame_mouse_next_line: int = 0
    """ 等待玩家确认后逐行 """
    w_frame_skip_wait_mouse: int = 0
    """ 跳过等待输入后继续输出文本 """


now_panel_id: int = 0
""" 当前游戏面板id """
wframe_mouse: WFrameMouse = WFrameMouse()
""" 主页监听控制流程用变量组 """
text_wait: float = 0
""" 绘制文本输出等待时间 """
input_position: int = 0
""" 回溯输入记录用定位 """
input_cache: list[str] = []
""" 界面输入框的输入历史（最多保留 21 条，供上下键回溯与日志使用，不随存档） """
input_cache_draft: str = ""
""" 玩家正在编辑但尚未发送的输入草稿 """
input_cache_browsing: bool = False
""" 玩家是否正在浏览输入历史 """
show_non_h_in_hidden_sex: bool = False
""" 是否在隐奸中显示非H类指令 """
instruct_type_filter_cache: dict[int, bool] = {}
""" （已弃用）玩家操作指令面板指令过滤状态数据_的缓存 指令类型:是否展示"""
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
