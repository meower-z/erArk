"""前提注册装饰器：handle_premise 包与其各子模块共用的 add_premise"""

from typing import Callable, TypeVar
from Script.Core import constant

PremiseFunc = TypeVar("PremiseFunc", bound=Callable[[int], float])
""" 前提处理函数：参数为角色id，返回前提权重 """


def add_premise(premise: str) -> Callable[[PremiseFunc], PremiseFunc]:
  """
  按前提id注册前提处理函数。
  每个前提id只能注册一次。
  Keyword arguments:
  premise -- 前提id
  Return arguments:
  Callable[[PremiseFunc], PremiseFunc] -- 注册前提处理函数的装饰器。
  这个装饰器把传入的函数存入 constant.handle_premise_data。
  这个装饰器原样返回传入的函数。
  premise 已注册时，这个装饰器抛 ValueError。
  """

  def decoraror(func: PremiseFunc) -> PremiseFunc:
    registered = constant.handle_premise_data.get(premise)
    if registered is not None:
      raise ValueError(
          f"前提id {premise} 已注册给 {registered.__module__}.{registered.__qualname__}，"
          f"不能再注册给 {func.__module__}.{func.__qualname__}"
      )
    # 直接注册原函数，不包转发层：前提判定在热路径上，每多一层调用都有开销
    constant.handle_premise_data[premise] = func
    return func

  return decoraror
