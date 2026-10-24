from functools import wraps
from typing import Callable, ParamSpec, TypeVar
from Script.Core import constant

PanelParams = ParamSpec("PanelParams")
""" 面板绘制函数的参数 """
PanelReturn = TypeVar("PanelReturn")
""" 面板绘制函数的返回值 """


def add_panel(
    panel: int,
) -> Callable[
    [Callable[PanelParams, PanelReturn]], Callable[PanelParams, PanelReturn]
]:
  """
  添加面板
  Keyword arguments:
  panel -- 面板id
  Return arguments:
  Callable -- 把面板绘制函数包装后注册到面板id下并返回包装函数的装饰器
  """

  def decoraror(
      func: Callable[PanelParams, PanelReturn],
  ) -> Callable[PanelParams, PanelReturn]:
    @wraps(func)
    def return_wrapper(
        *args: PanelParams.args, **kwargs: PanelParams.kwargs
    ) -> PanelReturn:
      return func(*args, **kwargs)

    constant.panel_data[panel] = return_wrapper
    return return_wrapper

  return decoraror
