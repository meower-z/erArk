"""前提注册装饰器：handle_premise 包与其各子模块共用的 add_premise"""

from typing import Callable, TypeVar
from Script.Core import constant

PremiseFunc = TypeVar("PremiseFunc", bound=Callable[[int], float])
""" 前提处理函数：参数为角色id，返回前提权重 """


def add_premise(premise: str) -> Callable[[PremiseFunc], PremiseFunc]:
  """
  添加前提
  Keyword arguments:
  premise -- 前提id
  Return arguments:
  Callable[[PremiseFunc], PremiseFunc] -- 把前提处理函数注册到前提id下并原样返回的装饰器
  """

  def decoraror(func: PremiseFunc) -> PremiseFunc:
    # 直接注册原函数，不包转发层：前提判定在热路径上，每多一层调用都有开销
    constant.handle_premise_data[premise] = func
    return func

  return decoraror
