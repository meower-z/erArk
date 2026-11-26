"""
玩家最近输入历史
================
本模块提供进程内保存玩家最近非空输入记录的列表 input_cache 与条数上限常量 INPUT_CACHE_LIMIT。
Script.Core.flow_handle._remember 按上限向 input_cache 追加非空输入。Script.Core.game_init 与
Script.Test.Static_Check.check_log 读取该列表，用于异常回溯与静态检查日志。本模块不导入界面模块。
"""

INPUT_CACHE_LIMIT = 21
"""input_cache 最多保留的最近非空玩家输入条数。"""
input_cache: list[str] = []
"""本进程记录的最近非空玩家输入列表，用于异常回溯与静态检查日志。"""
