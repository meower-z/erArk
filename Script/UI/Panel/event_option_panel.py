"""事件选项面板（含多层嵌套与子事件选项），以及 Web 模式下事件选项的准备与处理"""

from types import FunctionType
from Script.Core import cache_control, game_type, get_text, flow_handle, text_handle, py_cmd, constant
from Script.Design import talk, handle_premise
from Script.UI.Moudle import draw, panel
from Script.Config import game_config, normal_config
import time

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = '\n'
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def _get_event_text_for_web(character_id: int) -> dict:
  """
  获取Web模式下的事件文本
  优先从 cache.pending_event_text 获取，如果没有则返回空
  Keyword arguments:
  character_id -- 角色id
  Return arguments:
  dict -- 包含 text, style 的字典，如果没有事件文本则返回空字典
  """
  if hasattr(cache, 'pending_event_text') and cache.pending_event_text:
    event_data = cache.pending_event_text
    # 清空缓存
    cache.pending_event_text = None
    return event_data
  return {}


def _prepare_event_options_for_web(
    son_event_list: list, character_id: int
) -> list:
  """
  为Web模式准备事件选项数据
  Keyword arguments:
  son_event_list -- 子事件列表，每个元素为 [event_id, character_id] 或 event_id
  character_id -- 角色id
  Return arguments:
  list -- 选项数据列表，每个元素为 {id, text, event_id}
  """
  options = []
  for idx, item in enumerate(son_event_list):
    # 处理不同的列表格式
    if isinstance(item, list):
      event_id = item[0]
    else:
      event_id = item

    event_config = game_config.config_event[event_id]
    option_text = event_config.text.split('|')[0]
    option_text = talk.code_text_to_draw_text(option_text, character_id)

    options.append({'id': str(idx), 'text': option_text, 'event_id': event_id})

  return options


def _handle_web_event_options(son_event_list: list, character_id: int) -> str:
  """
  在Web模式下处理事件选项
  发送选项到前端并等待用户选择
  同时处理事件文本的显示和文本缓存
  Keyword arguments:
  son_event_list -- 子事件列表
  character_id -- 角色id
  Return arguments:
  str -- 选中的事件id
  """
  from Script.Core.web_server import emit_event_options, get_event_option_response, clear_event_option_response, emit_realtime_text

  # 准备选项数据
  options = _prepare_event_options_for_web(son_event_list, character_id)

  if not options:
    return ''

  # 获取事件文本
  event_text_data = _get_event_text_for_web(character_id)
  event_text = event_text_data.get('text', '') if event_text_data else ''
  event_style = (
      event_text_data.get('style', 'standard')
      if event_text_data
      else 'standard'
  )

  # 将事件文本和选项文本添加到 web_instruct_texts 缓存
  if event_text:
    # 去除开头的换行符后添加到缓存
    clean_event_text = event_text.lstrip('\n')
    if clean_event_text:
      cache.web_instruct_texts.append(clean_event_text)
      emit_realtime_text(clean_event_text, 'instruct')

  # 将选项文本也添加到缓存
  options_text_list = [
      f"[{i+1}] {opt['text']}" for i, opt in enumerate(options)
  ]
  options_combined_text = '\n'.join(options_text_list)
  if options_combined_text:
    cache.web_instruct_texts.append(options_combined_text)
    emit_realtime_text(options_combined_text, 'instruct')

  # 清空之前的响应
  clear_event_option_response()

  # 发送事件文本和选项到前端
  emit_event_options(options, event_text, event_style)

  # 等待前端返回选择
  selected_event_id = None
  while selected_event_id is None:
    response = get_event_option_response()
    if response is not None:
      # 响应格式: {'option_id': '0', 'event_id': 'xxx'}
      selected_event_id = response.get('event_id', '')
      break
    time.sleep(0.1)

  # 关闭事件选项弹窗
  emit_event_options(None)

  return selected_event_id


def get_target_chara_diy_instruct(
    character_id: int = 0,
) -> tuple[int, list[str]]:
  """
  获得交互对象的角色自定义指令\n
  Keyword arguments:\n
  character_id -- 角色id\n
  Return arguments:\n
  int -- 子事件数量\n
  list -- 子事件列表\n
  """
  character_data: game_type.Character = cache.character_data[character_id]
  son_event_list = []  # 子事件列表
  if character_data.target_character_id:
    target_character_data = cache.character_data[
        character_data.target_character_id
    ]
    # 判断是否存在该行为对应的事件
    if (
        constant.Behavior.CHARA_DIY_INSTRUCT
        in game_config.config_event_status_data_by_chara_adv
    ):
      all_chara_diy_instruct_event_list = (
          game_config.config_event_status_data_by_chara_adv[
              constant.Behavior.CHARA_DIY_INSTRUCT
          ]
      )
      # 判断交互对象是否有该行为事件
      if target_character_data.adv in all_chara_diy_instruct_event_list:
        target_diy_instruct_event_list = all_chara_diy_instruct_event_list[
            target_character_data.adv
        ]
        # 已计算过的前提字典
        calculated_premise_dict = {}
        # 遍历事件列表
        for event_id in target_diy_instruct_event_list:
          event_config = game_config.config_event[event_id]
          # 计算总权重
          now_weight, calculated_premise_dict = (
              handle_premise.get_weight_from_premise_dict(
                  event_config.premise,
                  character_id,
                  calculated_premise_dict,
                  unconscious_pass_flag=True,
              )
          )
          # 判定通过，加入到子事件的列表中
          if now_weight:
            son_event_list.append(event_id)

  return len(son_event_list), son_event_list


def check_son_event_list_from_event_list(
    event_list: list,
    character_id: int,
    event_parent_chid_id: int,
    event_parent_value: int,
) -> list[str]:
  """
  检查事件列表中是否有子事件\n
  Keyword arguments:\n
  event_list -- 事件列表\n
  character_id -- 角色id\n
  event_parent_chid_id -- 子事件的序号id（非事件id）\n
  event_parent_value -- 子事件的值\n
  Return arguments:\n
  son_event_list -- 子事件列表\n
  """
  son_event_list = []  # 子事件列表
  # 已计算过的前提字典
  calculated_premise_dict = {}

  # 开始遍历当前行为的事件表
  for event_id in event_list:
    event_config = game_config.config_event[event_id]
    # 需要含有综合数值前提中的子嵌套事件前提
    son_premise = 'CVP_A1_Son|{0}_E_{1}'.format(
        event_parent_chid_id, event_parent_value
    )
    # 需要有该子事件的前提
    if son_premise in event_config.premise:
      premise_dict = event_config.premise.copy()
      # 从前提集中去掉子事件前提
      premise_dict.pop(son_premise)
      # 如果前提集不为空
      if len(premise_dict):
        # 计算总权重
        now_weight, calculated_premise_dict = (
            handle_premise.get_weight_from_premise_dict(
                premise_dict,
                character_id,
                calculated_premise_dict,
                unconscious_pass_flag=True,
            )
        )
        # 判定通过，加入到子事件的列表中
        if now_weight:
          son_event_list.append(event_id)
      # 前提集为空，直接加入到子事件的列表中
      else:
        son_event_list.append(event_id)
  return son_event_list


class Event_option_Panel:
  """
  总面板对象
  Keyword arguments:
  width -- 绘制宽度
  """

  def __init__(self, character_id: int, width: int):
    """初始化绘制对象"""
    self.character_id = character_id
    """ 绘制的角色id """
    self.width: int = width
    """ 绘制的最大宽度 """
    self.handle_panel: panel.PageHandlePanel = None
    """ 当前名字列表控制面板 """

  def draw(self):
    """绘制对象"""
    character_data: game_type.Character = cache.character_data[
        self.character_id
    ]
    behavior_id = character_data.behavior.behavior_id
    father_event_id = character_data.event.event_id

    # 获取父事件的前提信息
    father_event_data: game_type.Event = game_config.config_event[
        father_event_id
    ]
    father_promise = father_event_data.premise

    son_event_list = []

    # 开始遍历当前行为的事件表
    if behavior_id in game_config.config_event_status_data:
      for event_id in game_config.config_event_status_data[behavior_id]:
        event_config = game_config.config_event[event_id]
        son_flag = True
        # 需要含有子事件前提
        if len(event_config.premise) and 'option_son' in event_config.premise:
          for premise in father_promise:
            # 子事件的前提必须完全包含父事件的前提
            if premise not in event_config.premise:
              son_flag = False
              break
          # 加入到子事件的列表中
          if son_flag:
            son_event_list.append([event_id, self.character_id])

    # 如果子事件列表为空，则直接返回
    if not len(son_event_list):
      return

    # Web 模式处理
    if hasattr(cache, 'web_mode') and cache.web_mode:
      selected_event_id = _handle_web_event_options(
          son_event_list, self.character_id
      )
      if selected_event_id:
        character_data.event.son_event_id = selected_event_id
      return

    # 非 Web 模式，使用传统绘制方式
    line_feed.draw()
    self.handle_panel = panel.PageHandlePanel(
        [], SonEventDraw, 20, 1, self.width, 1, 1, 0
    )

    while 1:
      py_cmd.clr_cmd()

      self.handle_panel.text_list = son_event_list
      self.handle_panel.update()
      return_list = []
      self.handle_panel.draw()
      return_list.extend(self.handle_panel.return_list)
      line_feed.draw()
      yrn = flow_handle.askfor_all(return_list)
      if yrn in return_list:
        break


class multi_layer_event_option_Panel:
  """
  多层嵌套的面板对象
  Keyword arguments:
  width -- 绘制宽度
  """

  def __init__(
      self,
      character_id: int,
      width: int,
      event_parent_chid_id: int,
      event_parent_value: int,
  ):
    """初始化绘制对象"""
    self.character_id = character_id
    """ 绘制的角色id """
    self.width: int = width
    """ 绘制的最大宽度 """
    self.event_parent_chid_id = event_parent_chid_id
    """ 嵌套父子事件的序号id（非事件id） """
    self.event_parent_value = event_parent_value
    """ 嵌套父子事件的值 """
    self.handle_panel: panel.PageHandlePanel = panel.PageHandlePanel(
        [], SonEventDraw, 20, 1, self.width, 1, 1, 0
    )
    """ 当前名字列表控制面板 """

  def draw(self):
    """绘制对象"""
    character_data: game_type.Character = cache.character_data[
        self.character_id
    ]
    target_character_data = cache.character_data[
        character_data.target_character_id
    ]
    behavior_id = character_data.behavior.behavior_id

    tem_event_list = []  # 临时事件列表
    son_event_list = []  # 子事件列表

    # 开始遍历当前行为的事件表
    if behavior_id in game_config.config_event_status_data_by_chara_adv:
      if (
          character_data.adv
          in game_config.config_event_status_data_by_chara_adv[behavior_id]
      ):
        tem_event_list += game_config.config_event_status_data_by_chara_adv[
            behavior_id
        ][character_data.adv]
      if (
          target_character_data.adv
          in game_config.config_event_status_data_by_chara_adv[behavior_id]
      ):
        tem_event_list += game_config.config_event_status_data_by_chara_adv[
            behavior_id
        ][target_character_data.adv]

    # 从临时事件列表中筛选出子事件
    son_event_list = check_son_event_list_from_event_list(
        tem_event_list,
        self.character_id,
        self.event_parent_chid_id,
        self.event_parent_value,
    )

    # 如果没有子事件，直接返回
    if len(son_event_list) == 0:
      return

    # Web 模式处理
    if hasattr(cache, 'web_mode') and cache.web_mode:
      selected_event_id = _handle_web_event_options(
          son_event_list, self.character_id
      )
      if selected_event_id:
        character_data.event.son_event_id = selected_event_id
      return

    # 非 Web 模式，使用传统绘制方式
    line_feed.draw()
    draw_event_list = []
    for son_event_id in son_event_list:
      draw_event_list.append([son_event_id, self.character_id])

    # 如果有子事件，继续绘制
    while 1:
      py_cmd.clr_cmd()

      self.handle_panel.text_list = draw_event_list
      self.handle_panel.update()
      return_list = []
      self.handle_panel.draw()
      return_list.extend(self.handle_panel.return_list)
      line_feed.draw()
      yrn = flow_handle.askfor_all(return_list)
      if yrn in return_list:
        break


class SonEventDraw:
  """
  显示子事件选项对象
  Keyword arguments:
  value_list -- 事件id,人物id
  width -- 最大宽度
  is_button -- 绘制按钮
  num_button -- 绘制数字按钮
  button_id -- 数字按钮id
  """

  def __init__(
      self,
      value_list: list,
      width: int,
      is_button: bool,
      num_button: bool,
      button_id: int,
  ):
    """初始化绘制对象"""
    self.event_id = value_list[0]
    """ 事件id """
    self.character_id = value_list[1]
    """ 绘制的角色id """
    self.son_event = game_config.config_event[self.event_id]
    """ 子事件 """
    self.draw_text: str = ''
    """ 绘制文本 """
    self.width: int = width
    """ 最大宽度 """
    self.num_button: bool = num_button
    """ 绘制数字按钮 """
    self.button_id: int = button_id
    """ 数字按钮的id """
    self.button_return: str = str(button_id)
    """ 按钮返回值 """
    name_draw = draw.NormalDraw()
    # print("text :",text)
    option_text = self.son_event.text.split('|')[0]
    option_text = talk.code_text_to_draw_text(option_text, self.character_id)
    if is_button:
      if num_button:
        index_text = text_handle.id_index(button_id)
        button_text = f'{index_text}{option_text}'
        name_draw = draw.LeftButton(
            button_text,
            self.button_return,
            self.width,
            cmd_func=self.run_son_event,
        )
      else:
        button_text = f'[{option_text}]'
        name_draw = draw.CenterButton(
            button_text, option_text, self.width, cmd_func=self.run_son_event
        )
        self.button_return = option_text
      self.draw_text = button_text
    else:
      name_draw = draw.CenterDraw()
      name_draw.text = f'[{option_text}]'
      name_draw.width = self.width
      self.draw_text = name_draw.text
    self.now_draw = name_draw
    """ 绘制的对象 """

  def draw(self) -> None:
    """绘制对象"""
    self.now_draw.draw()

  def run_son_event(self) -> None:
    """点击后运行对应的子事件"""
    character_data: game_type.Character = cache.character_data[
        self.character_id
    ]
    character_data.event.son_event_id = self.event_id
