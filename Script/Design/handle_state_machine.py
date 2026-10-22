from functools import wraps
from types import FunctionType
from Script.Core import constant
from Script.Design import child_stage_gate


def handle_state_machine(state_machine_id: int, character_id: int):
  """
  创建角色状态机
  Keyword arguments:
  state_machine_id -- 状态机id
  character_id -- 角色id
  """
  if state_machine_id in constant.handle_state_machine_data:
    constant.handle_state_machine_data[state_machine_id](character_id)


def add_state_machine(state_machine_id: int):
  """
  添加角色状态机函数
  Keyword arguments:
  state_machine_id -- 状态机id
  """

  def decorator(func: FunctionType):
    @wraps(func)
    def return_wrapper(character_id: int, *args, **kwargs):
      result = func(character_id, *args, **kwargs)
      # 状态机选出的H类行为若涉及幼年阶段角色，则换成发呆
      if child_stage_gate.blocks_behavior(character_id):
        child_stage_gate.reset_to_idle(character_id)
      return result

    constant.handle_state_machine_data[state_machine_id] = return_wrapper
    return return_wrapper

  return decorator
