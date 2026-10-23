"""
初始化缓存对象与基础配置，载入游戏配置与地图数据；
地图缓存文件不全时，地图载入会重新生成它们
"""

from Script.Core import game_type, cache_control
from Script.Config import normal_config

cache_control.cache = game_type.Cache()
normal_config.init_normal_config()


from Script.Config import game_config, name_config

game_config.init()
# name_config.init_name_data()


from Script.Config import map_config

map_config.init_map_data()


print("Cache Building End")
