import typing

from Script.Core import game_type

if typing.TYPE_CHECKING:
  cache: game_type.Cache
  """ 游戏内缓存数据 """
else:
  # 启动流程赋上 Cache 之前为 None
  cache = None
