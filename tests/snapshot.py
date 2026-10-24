# -*- coding: UTF-8 -*-
"""
行为快照：逐步记下游戏状态，比较两次运行
========================================
记录：每一步调用 capture(cache, log) 取一份状态，名字 -> 值。名字固定、可读：
    clock                                   游戏时间
    chara.<id>.<字段>[.<键>...]             每个角色（含离线、未招募的）的字段（SKIPPED_CHARACTER_FIELDS 除外），如
        chara.12.position                     角色 12 所在场景
        chara.12.talent.20                    角色 12 的素质 20
        chara.12.behavior.behavior_id         角色 12 的行为id
        chara.12.pregnancy.fertilization_time 角色 12 的受精时间
    world.<区域>.<键>[...]                  游戏缓存里的世界状态（区域见 WORLD_AREAS 与 SKIPPED_CACHE_FIELDS），如
        world.commission.ongoing_field_commissions.9   进行中的委托 9
        world.vehicle.vehicles.5                       载具 5 的 [拥有数, 外勤中数]
        world.library.book_borrow_dict.12              书 12 的借阅者
        world.medical.medical_patients_today.13.state  门诊病人 13 的状态
        world.clock.game_time                          游戏时间
    scene.<场景路径>.occupants / close_flag 场景里的角色id（排序）与关门状态
    log.talk / log.event                    这一步里交去显示的口上id（含随后被显示判断挡下的）、触发的事件id（ActionLog 记下，只记id，不记文本）
角色与世界的字段按对象的属性、字典的键逐层展开到叶子：叶子是布尔、数、字符串、时间、UUID、枚举，或每一项都是叶子的列表、集合（集合排序成列表）；
时间记作「年-月-日 时:分」，UUID 记作它的字符串，枚举记作它的值。值为 0、假、空串、空容器或 None 的叶子不记，比较时这样的名字值为 null。
值只有 JSON 能表达的数据，记不下的类型抛 TypeError，不用 repr 兜底。

文件：每行「步<TAB>名字<TAB>值的 JSON」。第一步写下全部名字，之后每步只写变了、新出现或消失的名字，消失的名字值写 null，
所以文件里一行就是一处变化。步是从 0000 开始的序号（时停中游戏时间不走，序号仍各不相同）。文件名以 .gz 结尾时按 gzip 读写。

比较：python -m tests.snapshot compare <基准文件> <新文件> [--allow <放行文件>] [--limit N]
把两份文件还原成每一步的全部状态，逐步逐名比较；一处差异是 (步, 名字, 基准值, 新值)，某一边没有这个名字时值记作 null；
某一边整步缺失时只报一处名为 step 的差异，有这一步的一边值为 "present"，另一边为 null。
报告先列最早出现差异的一步的全部差异，再按步逐条列出差异（最多 --limit 条，默认 200，0 为不限），
最后是没放行的差异的两份汇总：按角色（角色id与名字、差异数、最早的步、涉及的字段）与按字段（角色id换成 *，差异数、最早的步、涉及的角色）。
每条差异写明步与这一步的基准游戏时间、名字（角色名字里带上角色的名字）、基准值与新值。
放行文件是 JSON 列表，每条放行一处差异：
    {"step": "0012", "name": "chara.12.position", "baseline": ["中枢", "走廊"], "new": ["中枢", "会议室"], "reason": "为什么允许"}
四个字段都要与差异完全相同，reason 不能为空，没有通配符。
没被放行的差异、没有用上的放行都让比较失败（退出码 1）；放行了的差异照样列出。
"""

import argparse
import datetime
import enum
import gzip
import json
import os
import pickle
import re
import sys
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
  from collections.abc import Iterable
  from typing import Any

ABSENT = None
""" 比较时，一边没有的名字或步记作这个值（记录的值不会是 None） """

SKIPPED_CHARACTER_FIELDS = {
    "sp_flag.unnormal_flag": "只为旧存档保留，游戏不读写它",
    "token_text": "角色的信物文字（文本），只从模板读入",
    "text_color": "角色的文字颜色，只从模板读入",
    "nick_name": "玩家起的昵称（文本）",
    "nick_name_to_pl": "角色对玩家的称呼（文本）",
}
""" 不记的角色字段（名字里 chara.<id>. 之后的部分）: 理由 """

WORLD_AREAS = {
    "ongoing_field_commissions": "commission",
    "finished_field_commissions_set": "commission",
    "shut_down_field_commissions_set": "commission",
    "vehicles": "vehicle",
    "book_borrow_dict": "library",
    "reader_now": "library",
    "recommend_book_type_set": "library",
    "now_show_book_cid_of_type": "library",
    "dining_hall_data": "cooking",
    "restaurant_data": "cooking",
    "makefood_data": "cooking",
    "stall_vendor_data": "cooking",
    "milk_in_fridge": "cooking",
    "urine_in_fridge": "cooking",
}
""" 罗德岛（cache.rhodes_island）字段所属的区域；没列出的字段以 MEDICAL_PREFIXES 开头的归 world.medical，其余归 world.base """

MEDICAL_PREFIXES = (
    "medical_",
    "patient_",
    "used_hospital_bed_modules",
    "player_examined_patient_ids",
)
""" 医疗部字段的名字开头：病人表、床位、医生、收入与计数 """

CACHE_AREAS = {
    "game_time": "clock",
    "pre_game_time": "clock",
    "game_round": "clock",
    "moon_phase": "clock",
    "sun_phase": "clock",
    "recipe_data": "cooking",
}
""" 游戏缓存字段所属的区域；没列出的字段以字段名为区域，如 world.country.<键> """

SKIPPED_CACHE_FIELDS = {
    "character_data": "按 chara.<id> 单独记",
    "scene_data": "按 scene.<场景路径> 单独记",
    "rhodes_island": "按 WORLD_AREAS 拆开记",
    "map_data": "地图配置，读入后不变",
    "npc_tem_data": "角色模板（配置）；生下的孩子另作为角色记在 chara.<id>",
    "daily_intsruce": "玩家当天的指令记录（文本）",
    "pending_event_text": "待显示的事件文本",
    "now_panel_id": "界面：当前面板",
    "cmd_data": "界面：按钮绑定的函数",
    "current_draw_elements": "界面：Web 绘制元素",
    "current_input_request": "界面：Web 输入请求",
    "current_interaction_type": "界面：当前交互类型",
    "current_return_list": "界面：当前可选项",
    "back_save_panel": "界面：存档面板",
    "game_update_flow_running": "界面：主循环是否在跑",
    "image_id": "界面：图片编号",
    "npc_image_index": "界面：立绘编号",
    "input_cache": "界面：输入历史",
    "input_cache_browsing": "界面：输入历史",
    "input_cache_draft": "界面：输入历史",
    "input_position": "界面：输入历史",
    "instruct_index_filter": "界面：指令面板过滤",
    "instruct_sex_type_filter": "界面：指令面板过滤",
    "instruct_type_filter": "界面：指令面板过滤",
    "instruct_type_filter_cache": "界面：指令面板过滤",
    "output_text_style": "界面：文本样式",
    "text_style_cache": "界面：文本样式",
    "text_style_position": "界面：文本样式",
    "text_wait": "界面：文本等待",
    "text_one_by_one_rich_cache": "界面：逐字显示缓存",
    "font_size": "界面：字号",
    "wframe_mouse": "界面：鼠标状态",
    "scene_panel_show": "界面：场景面板开关",
    "all_npc_position_panel_move_type": "界面：干员位置面板",
    "all_npc_position_panel_select_type": "界面：干员位置面板",
    "pregnancy_panel_filter_type": "界面：怀孕面板",
    "pregnancy_panel_sort_type": "界面：怀孕面板",
}
""" 不记的游戏缓存字段: 理由；另外以 web_ 开头的字段都是 Web 界面状态，不记 """


SCALAR_TYPES = (bool, int, float, str)
""" 快照里的标量类型 """

EXACT_TYPES = (bool, int, str)
""" 值相等即 JSON 文本相同的标量类型（浮点的 0.0 与 -0.0 相等而文本不同） """


def same(a, b) -> bool:
  """
  两个快照值是否相同：等同于比较它们的 JSON 文本，所以 true 与 1、1 与 1.0、0.0 与 -0.0 算不同
  Keyword arguments:
  a -- 快照值或 ABSENT
  b -- 快照值或 ABSENT
  Return arguments:
  bool -- JSON 文本相同时为真
  功能描述:
      布尔、整数、字符串，以及只含它们的列表，直接比类型与值；其余值（含浮点）比 JSON 文本。
  """
  if type(a) is not type(b):
    return False
  if type(a) in EXACT_TYPES:
    return a == b
  if (
      isinstance(a, list)
      and len(a) == len(b)
      and all(
          type(x) is type(y) and type(x) in EXACT_TYPES for x, y in zip(a, b)
      )
  ):
    return a == b
  return json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(
      b, ensure_ascii=False, sort_keys=True
  )


def canonical(value):
  """
  把值转成只含 JSON 数据的形式：集合排序成列表，元组转列表，字典的键转成字符串并排序
  Keyword arguments:
  value -- 任意值
  Return arguments:
  bool | int | float | str | list | dict -- 转换后的值
  功能描述:
      None 或其他对象抛 TypeError：快照只收确定、可比较的数据，不用 repr 兜底。
  """
  if isinstance(value, (bool, int, float, str)):
    return value
  if isinstance(value, (list, tuple)):
    return [canonical(item) for item in value]
  if isinstance(value, (set, frozenset)):
    return sorted(canonical(item) for item in value)
  if isinstance(value, dict):
    return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
  raise TypeError(f"快照不收 {type(value).__name__} 类型的值：{value!r}")


def _leaf(value):
  """
  把一个叶子值转成快照值；不是叶子时返回 None
  Keyword arguments:
  value -- 任意值
  Return arguments:
  object | None -- 快照值；value 是字典或对象，或是有一项不是叶子的列表、集合时为 None
  功能描述:
      时间记作「年-月-日 时:分」，UUID 记作它的字符串，枚举记作它的值；列表、元组与集合的每一项都是叶子时（可以是嵌套的列表）它本身是叶子，
      集合排序成列表；有一项是字典、对象或 None 时不是叶子。
  """
  if isinstance(value, enum.Enum):
    return _leaf(value.value)
  if isinstance(value, SCALAR_TYPES):
    return value
  if isinstance(value, datetime.datetime):
    return value.strftime("%Y-%m-%d %H:%M")
  if isinstance(value, uuid.UUID):
    return str(value)
  if isinstance(value, (list, tuple)) and all(
      type(item) in SCALAR_TYPES for item in value
  ):
    return list(value)
  if isinstance(value, (list, tuple, set, frozenset)):
    items = [_leaf(item) for item in value]
    if any(item is None for item in items):
      return None
    if isinstance(value, (set, frozenset)):
      return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return items
  return None


def flatten(
    prefix: str, value, state: dict, skipped: dict[str, str] | None = None
):
  """
  把一个值按对象的属性、字典的键逐层展开，叶子记进 state
  Keyword arguments:
  prefix -- 这个值的名字
  value -- 要展开的值
  state -- 收集结果的字典，名字: 快照值
  skipped -- 不记的完整名字: 理由
  Return arguments:
  无
  功能描述:
      值为 0、假、空串、空容器或 None 的叶子不记。字典按键、对象按属性展开（prefix.键）；
      列表含字典或对象时按下标展开（prefix.0、prefix.1……）。其他类型抛 TypeError。
  """
  if value is None:
    return
  if type(value) in SCALAR_TYPES:
    if value:
      state[prefix] = value
    return
  leaf = _leaf(value)
  if leaf is not None:
    if leaf:
      state[prefix] = leaf
    return
  items: Iterable[tuple[object, object]]
  if isinstance(value, dict):
    items = value.items()
  elif isinstance(value, (list, tuple)):
    items = enumerate(value)
  elif hasattr(value, "__dict__"):
    items = vars(value).items()
  else:
    raise TypeError(
        f"快照不收 {prefix} 的 {type(value).__name__} 类型的值：{value!r}"
    )
  for key, item in items:
    name = f"{prefix}.{key}"
    if type(item) in SCALAR_TYPES:
      if item and not (skipped and name in skipped):
        state[name] = item
    elif item is not None and not (skipped and name in skipped):
      flatten(name, item, state, skipped)


class ActionLog:
  """
  记下游戏在两次 capture 之间交给 talk.handle_talk_draw 的口上id与触发的事件id
  install() 包住 talk.handle_talk_draw 与 event.handle_event；capture 用 take() 取走并清空记录。
  只记id：口上记 [角色id, 口上id（纸娃娃地文为它的行为id）, 二段行为id]，事件记 [角色id, 行为id, 事件id]，不记文本。
  """

  def __init__(self) -> None:
    """
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.talk: list[list[int | str]] = []
    """ 这一步交去显示的口上 """
    self.event: list[list[int | str]] = []
    """ 这一步触发的事件 """

  def install(self):
    """
    包住显示口上与选事件的两个函数，记下它们的id后照常执行；口上在进 handle_talk_draw 时就记下，不管它随后的显示判断是否挡下
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import cache_control
    from Script.Design import event, talk

    cache = cache_control.cache
    real_talk_draw = talk.handle_talk_draw
    real_handle_event = event.handle_event

    def handle_talk_draw(
        character_id,
        talk_text,
        now_talk_id,
        second_behavior_id="",
        common_behavior_id=None,
    ):
      """
      记下口上id后照常交给原函数显示
      Keyword arguments:
      character_id -- 角色id
      talk_text -- 口上文本（不记）
      now_talk_id -- 口上id
      second_behavior_id -- 二段行为id
      common_behavior_id -- 纸娃娃地文的行为id
      Return arguments:
      object -- 原函数的返回值
      """
      talk_id = now_talk_id or common_behavior_id or ""
      if talk_id:
        self.talk.append([character_id, str(talk_id), second_behavior_id])
      return real_talk_draw(
          character_id,
          talk_text,
          now_talk_id,
          second_behavior_id,
          common_behavior_id,
      )

    def handle_event(character_id, *args, **kwargs):
      """
      照常选事件，选中时记下事件id
      Keyword arguments:
      character_id -- 角色id
      Return arguments:
      object -- 原函数的返回值：选中事件时为事件绘制面板（它的 event_id 是事件id），否则为 None
      """
      result = real_handle_event(character_id, *args, **kwargs)
      event_id = getattr(result, "event_id", "")
      if event_id:
        behavior_id = cache.character_data[character_id].behavior.behavior_id
        self.event.append([character_id, str(behavior_id), str(event_id)])
      return result

    talk.handle_talk_draw = handle_talk_draw
    event.handle_event = handle_event

  def take(self) -> dict:
    """
    取走记录并清空
    Keyword arguments:
    无
    Return arguments:
    dict[str, list] -- log.talk 与 log.event 的值；没有记录的不给
    """
    taken = {}
    if self.talk:
      taken["log.talk"] = self.talk
    if self.event:
      taken["log.event"] = self.event
    self.talk, self.event = [], []
    return taken


def capture(
    cache,
    log: ActionLog | None = None,
    memo: dict[int, tuple[bytes | None, dict[str, object]]] | None = None,
) -> dict:
  """
  取当前游戏状态的一份快照
  Keyword arguments:
  cache -- 游戏缓存
  log -- 口上与事件的记录；给出时取走它此前的记录
  memo -- 逐步调用时传同一个空字典：记下每个角色上一次的 pickle 字节与展开结果，字节相同的角色直接沿用结果
  Return arguments:
  dict[str, object] -- 名字: 值
  功能描述:
      时钟；每个角色的全部字段（SKIPPED_CHARACTER_FIELDS 除外）；游戏缓存的世界状态（SKIPPED_CACHE_FIELDS 与 web_ 字段除外，
      罗德岛的字段按 WORLD_AREAS 分区）；有人的场景里的角色，关着门的场景的关门状态；口上与事件的id。
      memo 只省时间：pickle 字节相同的对象状态相同，展开结果也相同；字节不同时照常展开。
  """
  state: dict[str, object] = {
      "clock": cache.game_time.strftime("%Y-%m-%d %H:%M")
  }
  for cid in sorted(cache.character_data):
    character = cache.character_data[cid]
    pickled = pickle.dumps(character, protocol=4) if memo is not None else None
    if memo is not None and cid in memo and memo[cid][0] == pickled:
      state.update(memo[cid][1])
      continue
    prefix = f"chara.{cid}"
    skipped = {
        f"{prefix}.{field}": why
        for field, why in SKIPPED_CHARACTER_FIELDS.items()
    }
    names: dict[str, object] = {}
    flatten(prefix, character, names, skipped)
    state.update(names)
    if memo is not None:
      memo[cid] = (pickled, names)
  for field in sorted(vars(cache)):
    if field in SKIPPED_CACHE_FIELDS or field.startswith("web_"):
      continue
    flatten(
        f"world.{CACHE_AREAS.get(field, field)}.{field}",
        getattr(cache, field),
        state,
    )
  for field in sorted(vars(cache.rhodes_island)):
    area = WORLD_AREAS.get(
        field, "medical" if field.startswith(MEDICAL_PREFIXES) else "base"
    )
    flatten(f"world.{area}.{field}", getattr(cache.rhodes_island, field), state)
  for scene in cache.scene_data.values():
    prefix = f"scene.{scene.scene_path.replace(os.sep, '/')}."
    if scene.character_list:
      state[prefix + "occupants"] = canonical(scene.character_list)
    if scene.close_flag:
      state[prefix + "close_flag"] = scene.close_flag
  if log is not None:
    state.update(log.take())
  return state


class Recorder:
  """逐步收集快照，写成「步<TAB>名字<TAB>值」的文件，只写每步变了、新出现或消失的名字"""

  def __init__(self) -> None:
    """
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.lines: list[tuple[str, str, str]] = []
    """ 已记下的行：(步, 名字, 值的 JSON) """
    self._last: dict[str, object] = {}
    """ 上一步的全部状态 """
    self._steps: set[str] = set()
    """ 已记下的步 """

  def record(self, step: str, state: dict) -> None:
    """
    记下一步：写出与上一步相比变了、新出现或消失的名字，消失的名字值为 null
    Keyword arguments:
    step -- 步名（序号）
    state -- capture() 的结果
    Return arguments:
    无
    功能描述:
        步名重复抛 ValueError：还原时一步只能对应一份状态。
    """
    if step in self._steps:
      raise ValueError(f"步 {step} 记了两次")
    self._steps.add(step)
    last = self._last
    changed = [
        name
        for name, value in state.items()
        if not same(last.get(name, ABSENT), value)
    ]
    changed += [name for name in last if name not in state]
    for name in sorted(changed):
      value = state.get(name, ABSENT)
      self.lines.append(
          (step, name, json.dumps(value, ensure_ascii=False, sort_keys=True))
      )
    self._last = dict(state)

  def write(self, path: str) -> None:
    """
    写出快照文件；文件名以 .gz 结尾时写成 gzip（不带时间戳，同样的内容写出同样的字节）
    Keyword arguments:
    path -- 文件路径
    Return arguments:
    无
    """
    text = "".join("\t".join(line) + "\n" for line in self.lines)
    if path.endswith(".gz"):
      with open(path, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as g:
          g.write(text.encode("utf-8"))
    else:
      with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _open_text(path: str):
  """
  打开快照文件读文本；.gz 结尾的按 gzip 读
  Keyword arguments:
  path -- 文件路径
  Return arguments:
  TextIO -- 文本文件对象
  """
  if path.endswith(".gz"):
    return gzip.open(path, "rt", encoding="utf-8")
  return open(path, encoding="utf-8")


def load(path: str) -> dict:
  """
  读快照文件，还原每一步的全部状态
  Keyword arguments:
  path -- 文件路径
  Return arguments:
  dict[str, dict[str, object]] -- 步: (名字: 值)，按文件里的顺序
  """
  steps: dict[str, dict[str, object]] = {}
  state: dict[str, object] = {}
  with _open_text(path) as f:
    for number, line in enumerate(f, 1):
      parts = line.rstrip("\n").split("\t")
      if len(parts) != 3:
        raise ValueError(f"{path}:{number} 不是「步<TAB>名字<TAB>值」")
      step, name, value = parts
      if step in steps and steps[step] is not state:
        raise ValueError(f"{path}:{number} 步 {step} 的行不连续")
      if step not in steps:
        state = dict(state)
        steps[step] = state
      value = json.loads(value)
      if value is ABSENT:
        state.pop(name, None)
      else:
        state[name] = value
  return steps


def diff(baseline: dict, new: dict) -> list:
  """
  逐步逐名比较两次运行
  Keyword arguments:
  baseline -- load() 读出的基准
  new -- load() 读出的新运行
  Return arguments:
  list[tuple[str, str, object, object]] -- 差异 (步, 名字, 基准值, 新值)，按基准的步序，新运行多出的步排在最后
  功能描述:
      一边没有的步或名字，值记作 ABSENT；整步缺失时报一处 (步, "step", ...) 差异，不逐名展开。
  """
  differences = []
  for step in list(baseline) + [step for step in new if step not in baseline]:
    if step not in baseline or step not in new:
      differences.append(
          (
              step,
              "step",
              "present" if step in baseline else ABSENT,
              "present" if step in new else ABSENT,
          )
      )
      continue
    old_state, new_state = baseline[step], new[step]
    for name in sorted(set(old_state) | set(new_state)):
      old_value, new_value = old_state.get(name, ABSENT), new_state.get(
          name, ABSENT
      )
      if not same(old_value, new_value):
        differences.append((step, name, old_value, new_value))
  return differences


def load_allowances(path: str) -> list:
  """
  读放行文件并核对格式
  Keyword arguments:
  path -- 文件路径
  Return arguments:
  list[dict] -- 放行条目，每条有 step、name、baseline、new、reason
  """
  with open(path, encoding="utf-8") as f:
    allowances = json.load(f)
  if not isinstance(allowances, list):
    raise ValueError(f"{path} 应是 JSON 列表")
  for index, allowance in enumerate(allowances):
    if not isinstance(allowance, dict) or set(allowance) != {
        "step",
        "name",
        "baseline",
        "new",
        "reason",
    }:
      raise ValueError(
          f"{path} 第 {index} 条放行应正好有 step、name、baseline、new、reason 五个字段"
      )
    if (
        not isinstance(allowance["reason"], str)
        or not allowance["reason"].strip()
    ):
      raise ValueError(f"{path} 第 {index} 条放行没写 reason")
  return allowances


def compare(baseline: dict, new: dict, allowances: list) -> tuple:
  """
  比较两次运行并套用放行
  Keyword arguments:
  baseline -- load() 读出的基准
  new -- load() 读出的新运行
  allowances -- load_allowances() 读出的放行
  Return arguments:
  tuple[list, list, list] -- (没放行的差异, 放行了的差异及其理由, 没用上的放行)
  功能描述:
      一条放行只放行与它四个字段完全相同的一处差异（值按 same 比较）。
  """
  unused = list(allowances)
  unexpected, allowed = [], []
  for difference in diff(baseline, new):
    step, name, old, value = difference
    match = next(
        (
            a
            for a in unused
            if (a["step"], a["name"]) == (step, name)
            and same(a["baseline"], old)
            and same(a["new"], value)
        ),
        None,
    )
    if match is None:
      unexpected.append(difference)
    else:
      unused.remove(match)
      allowed.append((difference, match["reason"]))
  return unexpected, allowed, unused


def _show(value) -> str:
  """
  差异里的值的显示形式
  Keyword arguments:
  value -- 值
  Return arguments:
  str -- JSON 文本
  """
  return json.dumps(value, ensure_ascii=False, sort_keys=True)


CHARA_NAME = re.compile(r"^chara\.(\d+)\.(.+)$")
""" 角色名字的形式：chara.<id>.<字段> """


class Report:
  """
  把差异写成人能读的报告：每条差异带上步的游戏时间与角色的名字，另有按角色、按字段的汇总
  """

  def __init__(self, baseline: dict, new: dict) -> None:
    """
    Keyword arguments:
    baseline -- load() 读出的基准
    new -- load() 读出的新运行
    Return arguments:
    无
    """
    self.baseline = baseline
    """ 基准 """
    self.new = new
    """ 新运行 """

  def clock(self, step: str) -> str:
    """
    这一步的游戏时间：取基准的，基准没有这一步时取新运行的
    Keyword arguments:
    step -- 步名
    Return arguments:
    str -- 游戏时间，两边都没有时为空串
    """
    state = self.baseline.get(step) or self.new.get(step) or {}
    return str(state.get("clock", ""))

  def chara_label(self, cid: str, step: str) -> str:
    """
    角色的标签：id 与名字
    Keyword arguments:
    cid -- 角色id
    step -- 取名字的步（名字取这一步的基准，没有时取新运行，再没有时取任何一步）
    Return arguments:
    str -- 如 "130(杜宾)"；找不到名字时只有 id
    """
    name_key = f"chara.{cid}.name"
    for runs in (self.baseline.get(step), self.new.get(step)):
      if runs and name_key in runs:
        return f"{cid}({runs[name_key]})"
    for run in (self.baseline, self.new):
      for state in run.values():
        if name_key in state:
          return f"{cid}({state[name_key]})"
    return cid

  def label(self, step: str, name: str) -> str:
    """
    差异名字的显示形式：角色名字带上角色的名字
    Keyword arguments:
    step -- 步名
    name -- 差异名字
    Return arguments:
    str -- 如 "chara.130(杜宾).position"
    """
    match = CHARA_NAME.match(name)
    if not match:
      return name
    return f"chara.{self.chara_label(match.group(1), step)}.{match.group(2)}"

  def line(self, kind: str, difference: tuple) -> str:
    """
    一条差异的报告行
    Keyword arguments:
    kind -- 行首的种类：差异、已放行
    difference -- (步, 名字, 基准值, 新值)
    Return arguments:
    str -- 报告行：种类、步（游戏时间）、名字、基准值 -> 新值
    """
    step, name, old, value = difference
    return f"{kind}\t步 {step}（{self.clock(step)}）\t{self.label(step, name)}\t{_show(old)} -> {_show(value)}"

  def by_chara(self, differences: list) -> list:
    """
    按角色汇总差异
    Keyword arguments:
    differences -- 差异列表
    Return arguments:
    list[str] -- 每个角色一行：角色、差异数、最早的步、涉及的字段（最多 8 个）
    """
    groups: dict[str, list[Any]] = {}
    for step, name, _old, _value in differences:
      match = CHARA_NAME.match(name)
      if not match:
        continue
      group = groups.setdefault(match.group(1), [0, step, []])
      group[0] += 1
      if match.group(2) not in group[2]:
        group[2].append(match.group(2))
    lines = []
    for cid, (count, first, fields) in sorted(
        groups.items(), key=lambda item: (item[1][1], int(item[0]))
    ):
      shown = "、".join(fields[:8]) + (
          f" 等 {len(fields)} 个字段" if len(fields) > 8 else ""
      )
      lines.append(
          f"按角色\tchara.{self.chara_label(cid, first)}\t{count} 处\t最早 步 {first}（{self.clock(first)}）\t{shown}"
      )
    return lines

  def by_field(self, differences: list) -> list:
    """
    按字段汇总差异：角色名字里的 id 换成 *
    Keyword arguments:
    differences -- 差异列表
    Return arguments:
    list[str] -- 每个字段一行：字段、差异数、最早的步、涉及的角色（最多 8 个）
    """
    groups: dict[str, list[Any]] = {}
    for step, name, _old, _value in differences:
      match = CHARA_NAME.match(name)
      field = f"chara.*.{match.group(2)}" if match else name
      group = groups.setdefault(field, [0, step, []])
      group[0] += 1
      if match and match.group(1) not in group[2]:
        group[2].append(match.group(1))
    lines = []
    for field, (count, first, cids) in sorted(
        groups.items(), key=lambda item: (item[1][1], item[0])
    ):
      shown = "、".join(self.chara_label(cid, first) for cid in cids[:8])
      if len(cids) > 8:
        shown += f" 等 {len(cids)} 个角色"
      lines.append(
          f"按字段\t{field}\t{count} 处\t最早 步 {first}（{self.clock(first)}）\t{shown}"
      )
    return lines

  def render(
      self, unexpected: list, allowed: list, unused: list, limit: int
  ) -> list:
    """
    整份报告
    Keyword arguments:
    unexpected -- 没放行的差异
    allowed -- 放行了的差异及其理由
    unused -- 没用上的放行
    limit -- 逐条列出的差异的上限，0 为不限
    Return arguments:
    list[str] -- 报告的各行
    """
    lines = []
    if unexpected:
      first = unexpected[0][0]
      lines.append(f"最早的差异：步 {first}（{self.clock(first)}）")
      lines += [self.line("最早", d) for d in unexpected if d[0] == first]
    shown = unexpected if not limit else unexpected[:limit]
    lines += [self.line("差异", d) for d in shown]
    if len(shown) < len(unexpected):
      lines.append(
          f"另有 {len(unexpected) - len(shown)} 处差异没有逐条列出（--limit 0 列出全部）"
      )
    for difference, reason in allowed:
      lines.append(f"{self.line('已放行', difference)}\t{reason}")
    for allowance in unused:
      lines.append(
          f"未用的放行\t步 {allowance['step']}\t{allowance['name']}\t{_show(allowance['baseline'])} -> {_show(allowance['new'])}"
      )
    lines += self.by_chara(unexpected)
    lines += self.by_field(unexpected)
    lines.append(
        f"差异 {len(unexpected)}，已放行 {len(allowed)}，未用的放行 {len(unused)}"
    )
    return lines


def main(argv=None) -> int:
  """
  命令行入口：compare <基准文件> <新文件> [--allow <放行文件>] [--limit N]
  Keyword arguments:
  argv -- 命令行参数，默认 sys.argv[1:]
  Return arguments:
  int -- 退出码：0 没有未放行的差异也没有未用的放行，1 其他情况
  """
  parser = argparse.ArgumentParser(prog="python -m tests.snapshot")
  sub = parser.add_subparsers(dest="command", required=True)
  cmp_parser = sub.add_parser("compare", help="比较两次运行的快照")
  cmp_parser.add_argument("baseline")
  cmp_parser.add_argument("new")
  cmp_parser.add_argument("--allow", help="放行文件（JSON 列表）")
  cmp_parser.add_argument(
      "--limit", type=int, default=200, help="逐条列出的差异的上限，0 为不限"
  )
  args = parser.parse_args(argv)
  allowances = load_allowances(args.allow) if args.allow else []
  baseline, new = load(args.baseline), load(args.new)
  unexpected, allowed, unused = compare(baseline, new, allowances)
  for line in Report(baseline, new).render(
      unexpected, allowed, unused, args.limit
  ):
    print(line)
  return 1 if unexpected or unused else 0


if __name__ == "__main__":
  sys.exit(main())
