"""事件描述文本的绘制面板与子事件检查"""

from Script.Core import cache_control, game_type
from Script.Design import talk
from Script.UI.Moudle import draw
from Script.Config import normal_config, game_config

window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def _check_has_son_events(character_id: int, event_id: str) -> bool:
  """
  检查指定事件是否有子事件选项
  Keyword arguments:
  character_id -- 角色id
  event_id -- 事件id
  Return arguments:
  bool -- 是否有子事件选项
  """
  character_data: game_type.Character = cache.character_data[character_id]
  behavior_id = character_data.behavior.behavior_id

  # 获取父事件的前提信息
  if event_id not in game_config.config_event:
    return False
  father_event_data = game_config.config_event[event_id]
  father_promise = father_event_data.premise

  # 遍历当前行为的事件表，检查是否有子事件
  if behavior_id in game_config.config_event_status_data:
    for check_event_id in game_config.config_event_status_data[behavior_id]:
      event_config = game_config.config_event[check_event_id]
      # 需要含有子事件前提
      if len(event_config.premise) and "option_son" in event_config.premise:
        son_flag = True
        for premise in father_promise:
          # 子事件的前提必须完全包含父事件的前提
          if premise not in event_config.premise:
            son_flag = False
            break
        # 找到一个有效的子事件
        if son_flag:
          return True

  return False


class DrawEventTextPanel(draw.LineFeedWaitDraw):
  """
  用于绘制事件描述文本的面板对象
  Keyword arguments:
  event_id -- 事件id
  character_id -- 触发事件的角色id
  """

  def __init__(self, event_id: str, character_id: int, event_type: int) -> None:
    """初始化绘制对象"""
    self.width: int = window_width
    """ 绘制的最大宽度 """
    self.event_id: str = event_id
    """ 事件id """
    self.character_id: int = character_id
    """ 触发事件的角色id """
    self.event_type: int = event_type
    """ 事件的类型 """
    self.text: str = ""
    """ 当前绘制的文本 """
    self.style: str = "standard"
    """ 绘制文本的样式 """
    self.tooltip: str = ""
    """ 绘制文本的悬停提示 """
    player_data: game_type.Character = cache.character_data[0]
    if cache.is_collection:
      if character_id and character_id not in player_data.collection_character:
        return
    character_data: game_type.Character = cache.character_data[character_id]
    if player_data.position not in [
        character_data.position,
        character_data.behavior.move_target,
    ]:
      return

    self.son_event_flag = False  # 子事件标记
    self.diy_event_flag = False  # diy事件标记

    event_data = game_config.config_event[self.event_id]

    # 如果玩家身上有角色diy事件标记
    if character_data.event.chara_diy_event_flag:
      # 更新事件id
      self.event_id = character_data.event.event_id
      event_data = game_config.config_event[self.event_id]
      # 如果文本中没有两个|，则不是diy事件，不触发
      if event_data.text.count("|") < 2:
        return
      # 清除角色的diy事件标记
      character_data.event.chara_diy_event_flag = False
      # 触发diy事件标记
      self.diy_event_flag = True

    # 检查是否是子事件
    if "option_son" in event_data.premise:
      self.son_event_flag = True
    for primise in event_data.premise:
      if "CVP_A1_Son" in primise:
        self.son_event_flag = True
        break

    # 子事件的文本里去掉选项内容
    if self.son_event_flag and "|" in event_data.text:
      now_event_text: str = "\n" + event_data.text.split("|")[1]
    # diy事件的文本里去掉选项和行动事件内容
    elif self.diy_event_flag and "|" in event_data.text:
      now_event_text = "\n" + event_data.text.split("|")[2]
    else:
      now_event_text = "\n" + event_data.text

    # 代码词语
    now_event_text = talk.code_text_to_draw_text(now_event_text, character_id)
    self.text = now_event_text

    # 口上颜色
    if event_data.adv_id not in {"", "0", 0}:
      character_data = cache.character_data[character_id]
      target_character_data: game_type.Character = cache.character_data[
          character_data.target_character_id
      ]
      text_color = character_data.text_color
      tar_text_color = target_character_data.text_color
      if text_color:
        self.style = character_data.name
      elif tar_text_color:
        self.style = target_character_data.name

  def draw(self) -> None:
    """
    绘制事件文本
    在Web模式下：
    - 对于子事件/diy事件（选择选项后的输出），作为对话文本输出
    - 对于有选项的事件（父事件），保存供事件选项面板使用
    - 对于纯文本事件（无选项），作为对话文本输出
    在普通模式下保持原有的换行等待行为
    """
    # 如果没有文本则不绘制
    if not self.text:
      return

    # Web模式下的处理
    if cache.web_mode:
      # 子事件/diy事件 或 纯文本事件（无子事件选项）都作为对话文本输出
      # 只有带选项的父事件才保存供事件选项面板使用
      has_son_events = False
      if not self.son_event_flag and not self.diy_event_flag:
        # 检查这个事件是否有子事件选项
        has_son_events = _check_has_son_events(self.character_id, self.event_id)

      if has_son_events:
        # 有选项的父事件，保存供事件选项面板使用
        cache.pending_event_text = {
            "text": self.text,
            "style": self.style,
            "event_id": self.event_id,
            "character_id": self.character_id,
        }
      else:
        # 子事件/diy事件/纯文本事件，作为对话文本输出
        self._output_as_dialog_text()
      return
    else:
      # 非Web模式下使用父类的draw方法（包含等待逻辑）
      super().draw()

  def _output_as_dialog_text(self) -> None:
    """
    将事件文本作为对话文本输出
    包括：添加到文本回溯缓存、实时推送到前端、添加到对话框队列
    """
    from Script.Core.web_server import emit_realtime_text
    from Script.System.Web_Draw_System.dialog_box import add_dialog_text

    # 构造输出文本（去掉开头的换行符）
    output_text = self.text.lstrip("\n")

    # 添加到Web指令文本缓存，用于文本回溯功能
    if output_text:
      cache.web_instruct_texts.append(output_text)
      # 实时推送文本到前端
      emit_realtime_text(output_text, "instruct")

    # 添加对话文本到对话框队列
    # 获取说话者信息
    character_data: game_type.Character = cache.character_data[
        self.character_id
    ]
    speaker_name = character_data.name
    final_color = self.style

    # 获取当前角色的交互对象ID
    current_target_id = (
        character_data.target_character_id
        if character_data.target_character_id != character_data.cid
        else -1
    )

    # 判断是否为当前交互对象或玩家
    player_data = cache.character_data[0]
    player_target_id = player_data.target_character_id

    if self.character_id == 0 or self.character_id == player_target_id:
      # 主对话框：显示当前交互对象或玩家的台词
      add_dialog_text(
          speaker_name,
          output_text,
          final_color,
          wait_input=True,
          target_character_id=current_target_id,
      )
    else:
      # 其他角色：显示在头像下方的小对话框
      add_dialog_text(
          speaker_name,
          output_text,
          final_color,
          wait_input=False,
          is_minor=True,
          character_id=self.character_id,
          target_character_id=current_target_id,
      )
