from types import FunctionType
from Script.Core import constant


def add_premise(premise: str) -> FunctionType:
  """
  前提处理函数的注册装饰器
  Keyword arguments:
  premise -- 前提id，不同前提处理函数之间不能重复
  Return arguments:
  FunctionType -- 装饰器，原样返回被装饰的前提处理函数
  """

  def decorator(func):
    """
    把 func 登记为 premise 的处理函数
    Keyword arguments:
    func -- 前提处理函数
    Return arguments:
    FunctionType -- 原样返回 func
    功能描述:
        直接登记原函数、不做包装：前提判定在热路径上，每层包装都多一次函数调用。
        同一函数（__module__ 与 __qualname__ 都相同）再次登记同一id时替换原条目，
        其他函数登记已有id时抛 ValueError
    """
    registered = constant.handle_premise_data.get(premise)
    if registered is not None:
      old_name = f"{registered.__module__}.{registered.__qualname__}"
      new_name = f"{func.__module__}.{func.__qualname__}"
      if old_name != new_name:
        raise ValueError(
            f"前提id重复注册: {premise}（{old_name} 与 {new_name}）"
        )
    constant.handle_premise_data[premise] = func
    return func

  return decorator
