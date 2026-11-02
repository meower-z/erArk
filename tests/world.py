# -*- coding: UTF-8 -*-
"""
测试用的游戏世界夹具
====================
MinimalWorld -- 小世界：读一次真实游戏配置，造出空的游戏状态，测试之间一键复原；不启动游戏。快速层（tests/fast）用它。
FullWorld    -- 完整的无头启动：小世界之外再载入结算器、状态机与界面流程，不复原；慢速层（tests/slow）用它，每个进程开一局新游戏。

测试向世界要角色、位置和场景：
    world.chara(cid, name, position=...)   -- 造一个穿着衣服、各异常位正常的角色，并当场核对
    world.chara(cid, name, naked=True)     -- 要裸体角色必须写明，当场核对她全裸
    world.scene(path) / world.move(cid, path)
FullWorld 另有：
    world.new_game()                       -- 走一遍开新游戏的界面流程
    world.player.press(...) / type(...)    -- 安排玩家接下来按的按钮与输入的文字（PlayerInput）

游戏模块在导入时就绑定 cache = cache_control.cache，所以缓存对象只建一次，复原时原地改写它的内容。
每次复原都重设全部随机源（random、numpy.random、uuid.uuid4），见 seed_everything；启动时让列目录的顺序固定，见 pin_listing_order。
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import io
import os
import random
import sys
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from typing import Any, Self

  from Script.Core import game_type
  from Script.UI.Moudle import draw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
""" erArk 仓库根目录 """

SEED = 20260719
""" 全部随机源的固定种子，与 PYTHONHASHSEED 的固定值相同 """

START_TIME = (2020, 12, 22, 10, 0)
""" 复原后的游戏时间（年、月、日、时、分），不读 config.ini 的开局时间 """

DEFAULT_SCENE = ["宿舍", "1区", "101"]
""" chara() 不给位置时的默认场景：一间真实宿舍 """

STANDARD_OUTFIT = {5: [501], 6: [651], 9: [951], 11: [1101]}
""" 默认穿的衣服，衣物类型: 衣服id 列表：罗德岛制服夹克、纯白色胸罩、纯白色内裤、深蓝色小皮鞋 """

SHALLOW_CACHE_FIELDS = ("map_data", "npc_tem_data")
""" 复原时只浅拷贝的字典字段（地图与角色模板）：键复原到基线，值对象共用，测试不能改这些值对象 """


class FixtureError(AssertionError):
  """夹具造出的状态不符合承诺（例如默认角色不是全部正常）时抛出"""


_uuid_rng = random.Random(SEED)
""" 确定性 uuid4 用的随机源，seed_everything 重设它 """


def _seeded_uuid4() -> uuid.UUID:
  """
  确定性的 uuid4：由固定种子的随机源生成，替换 uuid.uuid4
  Keyword arguments:
  无
  Return arguments:
  uuid.UUID -- 第 4 版 UUID
  """
  return uuid.UUID(int=_uuid_rng.getrandbits(128), version=4)


def seed_everything(seed: int = SEED) -> None:
  """
  重设全部随机源：random、numpy.random，以及替换后的 uuid.uuid4
  Keyword arguments:
  seed -- 种子
  Return arguments:
  无
  功能描述:
      游戏代码里的随机来自 random（大量）、numpy.random（value_handle.get_gauss_rand）与 uuid.uuid4（食物 uid）。
      PYTHONHASHSEED 只能在解释器启动前设定，由 tests/conftest.py 处理。
  """
  import numpy

  random.seed(seed)
  numpy.random.seed(seed % (2**32))
  _uuid_rng.seed(seed)
  uuid.uuid4 = _seeded_uuid4


def pin_listing_order() -> None:
  """
  让 os.listdir 与 glob.glob 按文件名排序返回，可重复调用
  Keyword arguments:
  无
  Return arguments:
  无
  功能描述:
      两者的顺序随文件系统而变；游戏读角色口上与事件文件（character_config.find_files_and_get_size）、读模组目录时用它们。
  """
  import glob

  if getattr(os.listdir, "sorted_listing", False):
    return
  real_listdir, real_glob = os.listdir, glob.glob

  def sorted_listdir(*args: str, **kwargs: str) -> list[str]:
    """
    排好序的 os.listdir
    Keyword arguments:
    同 os.listdir
    Return arguments:
    list -- 排序后的文件名
    """
    return sorted(real_listdir(*args, **kwargs))

  def sorted_glob(*args: str, **kwargs: Any) -> list[str]:
    """
    排好序的 glob.glob
    Keyword arguments:
    同 glob.glob
    Return arguments:
    list -- 排序后的路径
    """
    return sorted(real_glob(*args, **kwargs))

  setattr(sorted_listdir, "sorted_listing", True)
  setattr(os, "listdir", sorted_listdir)
  setattr(glob, "glob", sorted_glob)


def _mute_ui() -> list:
  """
  屏蔽全部绘制类，并给等待输入的函数打桩
  Keyword arguments:
  无
  Return arguments:
  list[str] -- WaitDraw 绘制过的文本，按绘制顺序追加
  功能描述:
      askfor_all 返回第一个可选项，面板的按钮循环才能退出；它只返回选项，不执行选中的选项。
  """
  from Script.Core import flow_handle
  from Script.UI.Moudle import draw

  wait_texts = []

  def record_wait_draw(
      self: draw.WaitDraw, *args: object, **kwargs: object
  ) -> None:
    """
    记录型 WaitDraw 桩：把绘制文本收进 wait_texts
    Keyword arguments:
    self -- 绘制对象
    Return arguments:
    无
    """
    if getattr(self, "text", None):
      wait_texts.append(str(self.text))

  for cls_name in dir(draw):
    cls = getattr(draw, cls_name)
    if isinstance(cls, type) and hasattr(cls, "draw"):
      try:
        cls.draw = lambda self, *args, **kwargs: None
      except (AttributeError, TypeError):
        pass
  setattr(draw.WaitDraw, "draw", record_wait_draw)
  flow_handle.askfor_all = (
      lambda return_list, *args, **kwargs: return_list[0] if return_list else ""
  )
  flow_handle.askfor_wait = lambda *args, **kwargs: None
  return wait_texts


class MinimalWorld:
  """
  小世界：真实游戏配置 + 空游戏状态 + 一键复原，不启动游戏
  同一进程只能载入一个世界；用 MinimalWorld.load() 取得它
  """

  _loaded: MinimalWorld | None = None
  """ 本进程已载入的世界 """

  def __init__(self) -> None:
    """
    只由 load() 调用：载入配置、造基线状态并记下快照
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self._boot()
    self.wait_texts = _mute_ui()
    """ WaitDraw 绘制过的文本，每次复原清空 """
    self._snapshot()
    self.reset()

  @classmethod
  def load(cls) -> Self:
    """
    取得本进程的世界，第一次调用时载入
    Keyword arguments:
    无
    Return arguments:
    MinimalWorld -- 世界对象
    """
    if MinimalWorld._loaded is None:
      MinimalWorld._loaded = cls()
    elif type(MinimalWorld._loaded) is not cls:
      raise RuntimeError(
          f"本进程已载入 {type(MinimalWorld._loaded).__name__}，不能再载入 {cls.__name__}：两者共用同一个游戏缓存"
      )
    return MinimalWorld._loaded

  def _boot(self) -> None:
    """
    固定随机源，载入游戏
    Keyword arguments:
    无
    Return arguments:
    无
    """
    if ROOT not in sys.path:
      sys.path.insert(0, ROOT)
    # 游戏用相对路径读 data/ 与 config.ini
    os.chdir(ROOT)
    pin_listing_order()
    seed_everything()
    self._load_game()

  def _load_game(self) -> None:
    """
    增量构建 data/ 生成物，读入真实配置，造出空的游戏状态
    Keyword arguments:
    无
    Return arguments:
    无
    功能描述:
        顺序同 game.py：缓存先于配置建好；构建与配置载入的打印被收起。
        data/SceneData 等地图预处理文件存在时游戏直接读入它们，其中的顺序取决于写出它们的版本，这里把场景字典与场景标签列表排好序。
    """
    with contextlib.redirect_stdout(io.StringIO()):
      import auto_build_config  # noqa: F401
    from Script.Core import cache_control, game_type

    if cache_control.cache is None:
      cache_control.cache = game_type.Cache()
    from Script.Config import normal_config

    normal_config.init_normal_config()
    from Script.Config import character_config, game_config, map_config
    from Script.Core import constant

    with contextlib.redirect_stdout(io.StringIO()):
      game_config.init()
      character_config.init_character_tem_data()
      map_config.init_map_data()
    from Script.Design import attr_calculation, basement, game_time

    self.cache = cache_control.cache
    """ 游戏缓存（对象一直不变，复原时原地改写） """
    cache = self.cache
    cache.scene_data = dict(sorted(cache.scene_data.items()))
    for scene_list in constant.place_data.values():
      scene_list.sort()
    cache.npc_tem_data = dict(character_config.character_tem_list)
    cache.game_time = cache.pre_game_time = game_time.to_game_time(
        datetime.datetime(*START_TIME)
    )
    cache.all_system_setting = attr_calculation.get_system_setting_zero()
    cache.rhodes_island = basement.get_base_zero()
    basement.get_base_updata()
    for clothing_type, cloth_ids in STANDARD_OUTFIT.items():
      for cloth_id in cloth_ids:
        if (
            game_config.config_clothing_tem[cloth_id].clothing_type
            != clothing_type
        ):
          raise FixtureError(f"默认服装 {cloth_id} 不是 {clothing_type} 类衣物")

  def _snapshot(self) -> None:
    """
    记下基线：SHALLOW_CACHE_FIELDS 中字段的浅拷贝，其余缓存字段（场景字典除外）的深拷贝，以及每个场景的属性
    Keyword arguments:
    无
    Return arguments:
    无
    """
    fields = {
        key: value
        for key, value in self.cache.__dict__.items()
        if key != "scene_data"
    }
    self._shallow = {key: dict(fields.pop(key)) for key in SHALLOW_CACHE_FIELDS}
    self._baseline = copy.deepcopy(fields)
    self._scene_data = self.cache.scene_data
    self._scenes = dict(self._scene_data)
    self._scene_baseline = {
        key: copy.deepcopy(scene.__dict__)
        for key, scene in self._scenes.items()
    }

  def reset(self) -> None:
    """
    把游戏状态原地复原到基线，并重设全部随机源
    Keyword arguments:
    无
    Return arguments:
    无
    功能描述:
        缓存对象与场景对象都不换，只改写内容：游戏模块与测试手里的引用一直有效。
        游戏配置（game_config 等）与模块级打桩不在复原范围内：测试不能改配置，打桩用 unittest.mock 自行恢复。
    """
    cache = self.cache
    cache.__dict__.clear()
    cache.__dict__.update(copy.deepcopy(self._baseline))
    cache.__dict__.update(
        {key: dict(value) for key, value in self._shallow.items()}
    )
    self._scene_data.clear()
    self._scene_data.update(self._scenes)
    cache.scene_data = self._scene_data
    for key, scene in self._scenes.items():
      baseline = self._scene_baseline[key]
      scene.__dict__.clear()
      scene.__dict__.update(baseline)
      scene.character_list = set(baseline["character_list"])
      scene.scene_tag = list(baseline["scene_tag"])
    self.wait_texts.clear()
    seed_everything()

  def scene(self, path: list) -> game_type.Scene:
    """
    取一个场景，路径必须是真实场景
    Keyword arguments:
    path -- 场景路径列表，如 ["中枢", "博士房间"]
    Return arguments:
    game_type.Scene -- 场景对象
    """
    from Script.Design import map_handle

    key = map_handle.get_map_system_path_str_for_list(path)
    if key not in self.cache.scene_data:
      raise FixtureError(f"没有这个场景：{path}")
    return self.cache.scene_data[key]

  def move(self, cid: int, path: list) -> None:
    """
    用游戏的移动函数把角色从当前位置移到 path
    Keyword arguments:
    cid -- 角色id
    path -- 目标场景路径列表
    Return arguments:
    无
    """
    from Script.Design import map_handle

    self.scene(path)
    map_handle.character_move_scene(
        self.cache.character_data[cid].position, list(path), cid
    )

  def chara(
      self,
      cid: int,
      name: str = "测试干员",
      position: list[str] | None = None,
      *,
      naked: bool = False,
      race: int = 0,
      adv: int = 0,
  ) -> game_type.Character:
    """
    造一个角色并登记进缓存与所在场景，然后核对她的状态
    Keyword arguments:
    cid -- 角色id（0 为玩家；造 NPC 前须先造玩家）
    name -- 角色名
    position -- 初始场景路径列表，默认 DEFAULT_SCENE
    naked -- 为真时不穿衣服（全裸）；默认穿 STANDARD_OUTFIT
    race -- 种族id
    adv -- 剧情npc编号
    Return arguments:
    game_type.Character -- 已登记的角色对象
    功能描述:
        game_type.Character() 的多数容器字段初值是空 dict，游戏代码直接下标访问，这里全部按置零函数预填。
        默认角色当场核对：穿着衣服（不是大致全裸），NPC 的异常位1~7全部正常（normal_all 为 1）。
        naked=True 的角色当场核对：全裸；NPC 还须只有位4异常（玩家的异常位恒为正常）。不符合时抛 FixtureError。
    """
    from Script.Core import game_type
    from Script.Design import attr_calculation, map_handle

    cache = self.cache
    if cid in cache.character_data:
      raise FixtureError(f"角色 {cid} 已存在")
    if cid != 0 and 0 not in cache.character_data:
      raise FixtureError("先造玩家（cid 0）再造 NPC：异常位的判定要读玩家数据")
    position = list(position if position is not None else DEFAULT_SCENE)
    scene = self.scene(position)
    cd = game_type.Character()
    cd.cid = cid
    cd.name = name
    cd.adv = adv
    cd.sex = 1
    cd.race = race
    cd.cloth = attr_calculation.get_cloth_zero()
    cd.cloth.cloth_locker_in_dormitory = (
        attr_calculation.get_cloth_locker_in_dormitory_zero()
    )
    cd.cloth.cloth_locker_in_shower = (
        attr_calculation.get_shower_cloth_locker_zero()
    )
    if not naked:
      for clothing_type, cloth_ids in STANDARD_OUTFIT.items():
        cd.cloth.cloth_wear[clothing_type] = list(cloth_ids)
    cd.dirty = attr_calculation.get_zero_dirty()
    cd.talent = attr_calculation.get_talent_zero({})
    cd.ability = attr_calculation.get_ability_zero({})
    cd.status_data = attr_calculation.get_status_zero({})
    cd.juel = attr_calculation.get_juel_zero({})
    cd.experience = attr_calculation.get_experience_zero({})
    cd.second_behavior = attr_calculation.get_second_behavior_zero({})
    cd.h_state = attr_calculation.get_h_state_reset(cd.h_state)
    cd.body_manage = attr_calculation.get_body_manage_zero()
    cd.assistant_services = attr_calculation.get_assistant_services_zero()
    cd.favorability = {0: 0}
    cd.talent[121] = 1
    cd.hit_point_max = cd.hit_point = 100
    cd.mana_point_max = cd.mana_point = 100
    cd.dormitory = map_handle.get_map_system_path_str_for_list(DEFAULT_SCENE)
    cd.behavior.start_time = cache.game_time
    cd.position = position
    cache.character_data[cid] = cd
    if cid:
      cache.npc_id_got.add(cid)
    scene.character_list.add(cid)
    self._check_chara(cid, naked)
    return cd

  def _check_chara(self, cid: int, naked: bool) -> None:
    """
    核对新角色的衣着与异常位，不符合时抛 FixtureError
    Keyword arguments:
    cid -- 角色id
    naked -- 是否应为全裸
    Return arguments:
    无
    """
    from Script.Design import handle_premise

    if naked:
      if not handle_premise.handle_cloth_off(cid):
        raise FixtureError(f"角色 {cid} 应当全裸")
      expected_abnormal = [4] if cid else []
    else:
      if handle_premise.handle_cloth_most_off(cid):
        raise FixtureError(f"角色 {cid} 应当穿着衣服")
      expected_abnormal = []
    abnormal = [
        bit
        for bit in range(1, 8)
        if not getattr(handle_premise, f"handle_normal_{bit}")(cid)
    ]
    if abnormal != expected_abnormal:
      raise FixtureError(
          f"角色 {cid} 的异常位应为 {expected_abnormal}，实际为 {abnormal}"
      )
    if not naked and not handle_premise.handle_normal_all(cid):
      raise FixtureError(f"角色 {cid} 的 normal_all 应为 1")


class UnplannedInput(AssertionError):
  """游戏在等玩家输入，测试没有安排这一步，或屏幕上没有安排的按钮"""


class PlayerInput:
  """
  无头的玩家输入：记下屏幕上画出的按钮，游戏等输入时按测试安排的顺序按下按钮或输入文字
  绘制照常执行，输出不送往界面：文字收进 self.screen，按钮收进 self.buttons。
  清屏、清除命令绑定时忘掉相应的按钮，命令id 重新绑定时只留最新的按钮；按下一个按钮后忘掉全部按钮，下一次只从之后画出的按钮里选。
  按下的按钮经游戏自己的 askfor_all 执行，所以按钮绑定的函数（如事件选项）照常生效。
  """

  SCREEN_LIMIT = 400
  """ self.screen 只留最近的这么多段文字 """

  def __init__(self) -> None:
    """
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.buttons: list[tuple[str, str]] = []
    """ 可以按的按钮：(按钮文字, 命令id)；几个按钮都含安排的文字时按最后画出的那个 """
    self.screen: list[str] = []
    """ 最近输出的文字 """
    self.planned: list[tuple[str, str]] = []
    """ 还没用掉的输入：("press", 按钮文字的一部分) 或 ("type", 输入的文字) """

  def install(self) -> None:
    """
    换掉界面输出与读输入的函数
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import flow_handle, io_init

    io_init.put_queue = lambda message: None
    io_init.era_print = self._print
    io_init.io_print_cmd = self._print_cmd
    io_init.io_print_image_cmd = self._print_cmd
    io_init.io_clear_cmd = self._clear_cmd
    io_init.clear_screen = self._clear_cmd
    io_init.clear_screen_and_history = self._clear_cmd
    setattr(flow_handle, "order_deal", self._order_deal)

  def press(self, *labels: str) -> None:
    """
    安排接下来依次按下的按钮
    Keyword arguments:
    labels -- 按钮文字的一部分，按顺序各按一次
    Return arguments:
    无
    """
    self.planned.extend(("press", label) for label in labels)

  def type(self, text: str) -> None:
    """
    安排下一次输入文字（如角色名）
    Keyword arguments:
    text -- 输入的文字
    Return arguments:
    无
    """
    self.planned.append(("type", text))

  def check_done(self) -> None:
    """
    安排的输入都已用掉，否则抛 UnplannedInput
    Keyword arguments:
    无
    Return arguments:
    无
    """
    if self.planned:
      raise UnplannedInput(
          f"安排的输入没有用掉：{self.planned}；最近的文字：{self.screen[-5:]}"
      )

  def _print(
      self,
      string: str,
      style: str | tuple[str, ...] = "standard",
      tooltip: str = "",
  ) -> None:
    """
    替换 io_init.era_print：记下文字
    Keyword arguments:
    string -- 文字
    style -- 样式，不使用
    tooltip -- 悬停提示，不使用
    Return arguments:
    无
    """
    if str(string).strip():
      self.screen.append(str(string))
      del self.screen[: -self.SCREEN_LIMIT]

  def _print_cmd(
      self, cmd_str: str, cmd_number: int | str, *args: str, **kwargs: str
  ) -> None:
    """
    替换 io_init.io_print_cmd：记下按钮（命令已由 flow_handle.print_cmd 绑定）
    Keyword arguments:
    cmd_str -- 按钮文字
    cmd_number -- 命令id
    Return arguments:
    无
    """
    self._clear_cmd(cmd_number)
    self.buttons.append((str(cmd_str), str(cmd_number)))

  def _clear_cmd(self, *cmd_numbers: int | str) -> None:
    """
    替换 io_init.io_clear_cmd、clear_screen 与 clear_screen_and_history：忘掉按钮
    Keyword arguments:
    cmd_numbers -- 要忘掉的按钮的命令id；不给时忘掉全部按钮
    Return arguments:
    无
    """
    if not cmd_numbers:
      self.buttons.clear()
      return
    gone = {str(number) for number in cmd_numbers}
    self.buttons = [
        (text, cmd) for text, cmd in self.buttons if cmd not in gone
    ]

  def _order_deal(
      self,
      flag: str = "order",
      print_order: bool = True,
      donot_return_null_str: bool = True,
  ) -> str | None:
    """
    替换 flow_handle.order_deal：给出下一项安排的输入
    Keyword arguments:
    flag -- "str" 时返回命令id；"order" 时执行按钮绑定的函数
    print_order -- 不使用
    donot_return_null_str -- 为假时是「按任意键继续」的等待：安排的下一项是文字，或是屏幕上没有的按钮时，返回空串、不用掉它
    Return arguments:
    str -- 命令id、输入的文字或空串
    功能描述:
        安排的文字交给 donot_return_null_str 为真的请求（输入文字、选择按钮都是），「按任意键继续」的等待不用掉它。
        游戏要求选择而测试没有安排、或屏幕上没有安排的按钮时抛 UnplannedInput，并列出屏幕上的按钮。
    """
    from Script.Core import flow_handle

    kind, value = self.planned[0] if self.planned else ("", "")
    if kind == "type" and donot_return_null_str:
      self.planned.pop(0)
      return value
    matches = [
        cmd
        for text, cmd in reversed(self.buttons)
        if kind == "press" and value in text
    ]
    if not matches:
      if not donot_return_null_str:
        return ""
      shown = [text for text, _ in self.buttons]
      raise UnplannedInput(
          f"游戏在等玩家选择，安排的下一步是 {value or '（没有）'!r}；屏幕上的按钮：{shown}；最近的文字：{self.screen[-5:]}"
      )
    self.planned.pop(0)
    self.buttons.clear()
    if flag == "order":
      flow_handle._cmd_deal(matches[0])
      return None
    return matches[0]


class FullWorld(MinimalWorld):
  """
  完整的无头世界：小世界之外再注册结算器、状态机与界面流程，初始化角色模板，供慢速层用
  绘制照常执行，玩家输入由 self.player（PlayerInput）给出；new_game() 走一遍开新游戏的界面流程。
  不做复原：慢速层每个测试一个新进程。
  """

  PLAYER_NAME = "多克特"
  """ new_game() 输入的玩家名字：与口上里写死的「博士」区分开 """

  def __init__(self) -> None:
    """
    只由 load() 调用：载入配置与全部游戏模块，换上 PlayerInput
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self._boot()
    self.player = PlayerInput()
    """ 玩家输入 """
    self.player.install()

  def _load_game(self) -> None:
    """
    先载入小世界，再导入 Script.Settle、Script.StateMachine、医疗系统与界面流程（靠装饰器注册），并初始化角色模板
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super()._load_game()
    import Script.Settle  # noqa: F401
    import Script.StateMachine  # noqa: F401
    import Script.System.Medical_System  # noqa: F401
    import Script.UI.Flow  # noqa: F401
    from Script.Design import character_handle

    character_handle.init_character_tem()

  def reset(self) -> None:
    """
    慢速层不复原，调用即抛 RuntimeError
    Keyword arguments:
    无
    Return arguments:
    无
    """
    raise RuntimeError("FullWorld 不复原：慢速层每个测试一个新进程")

  def new_game(self, first_bonus: tuple = ()) -> None:
    """
    走一遍开新游戏的界面流程：标题画面「初次唤醒」，读完免责声明，输入名字 PLAYER_NAME，按下 first_bonus 的按钮，「睁开双眼」
    Keyword arguments:
    first_bonus -- 在创建角色面板里依次按下的初期奖励按钮，选助理干员时紧接着按下干员的名字，
        如 ("窄域时停", "启动资金", "助理干员", "阿米娅")；默认不选
    Return arguments:
    无
    功能描述:
        初始干员、设施与设置都取创建角色面板的默认值。流程结束时重设随机源，开局之后的随机与开局流程的长短无关。
    """
    from Script.Core import constant
    from Script.UI.Flow import creator_character_flow, title_flow

    self.player.press("初次唤醒")
    title_flow.title_panel()
    if self.cache.now_panel_id != constant.Panel.CREATOR_CHARACTER:
      raise FixtureError(
          f"标题画面没有进入创建角色：now_panel_id={self.cache.now_panel_id}"
      )
    self.player.press("我读完并理解了以上8条")
    self.player.type(self.PLAYER_NAME)
    self.player.press(*first_bonus, "睁开双眼")
    creator_character_flow.creator_character_panel()
    self.player.check_done()
    seed_everything()
