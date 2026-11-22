"""
初始化基础配置，载入游戏配置与地图数据；
地图缓存文件不全时，地图载入会重新生成它们
"""

from Script.Config import normal_config

normal_config.init_normal_config()


from Script.Config import game_config

game_config.init()


from Script.Config import map_config

map_config.init_map_data()


print("Cache Building End")
