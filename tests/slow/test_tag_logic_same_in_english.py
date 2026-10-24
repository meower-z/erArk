# -*- coding: UTF-8 -*-
"""
英文环境下，按行为标签、委托文本与烹饪阶段判定的游戏逻辑与中文环境结果相同
==========================================================================
两种语言各启动两局游戏（en_US 等同 config.ini 写 language = en_US）：群交一局与其余各项一局，
除最后一局 en_US 在本进程，其余都在 fork 出的子进程里，先跑 zh_CN。每局开新游戏（助理干员阿米娅）
后走同一条路线，只记下与语言无关的结果（行为id、数值、真假），逐项比较：
    group_sex_serve     群交一局：在博士办公室与凯尔希、阿米娅群交，编辑群交行动选好肛门与侍奉后的模板
    npc_active_h        回博士房间召集阿米娅、邀请H（in_h：是否进入 H），「交给对方」前后的时间与玩家行为
    group_sex_parts     群交各部位可选的行为id
    sex_assistant       调教助手可用的行为id
    hidden_value        隐奸中玩家做各项H行为 10 分钟后的被发现度
    commission_check    每项外勤委托的需求与奖励是否满足
    commission_list     外勤委托面板列出的委托id
    commission_reward   逐项结算委托奖励里的声望与好感：项数，之后各势力的声望与阿米娅的好感
    cook_question       每道菜各阶段与各特殊调味替换阶段的题数（精细烹饪面板的查法）
某一项抛出 KeyError、IndexError 或 UnboundLocalError 时记下异常，同样参与比较。
游戏模块用 importlib 在启动后导入：慢速层的测试模块不能在顶部导入 Script 下的模块。
"""

import importlib
import json
import os
import signal
import traceback
from types import ModuleType
from typing import Any, Callable

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase

CHINESE = "zh_CN"
""" 基准语言 """
ENGLISH = "en_US"
""" 被测语言 """
AMIYA_ID = 1
""" 阿米娅的角色id，也是她的干员编号 """
KALTSIT_ID = 3
""" 凯尔希的角色id，也是她的干员编号 """
SPECIAL_SEASONING_LIST = (11, 12, 101)
""" 会替换烹饪问题阶段的特殊调味 """
HIDDEN_DURATION = 10
""" 结算被发现度的行为时长，分钟 """
HIDDEN_START = 50
""" 每次结算前的被发现度 """
HIDDEN_TAG_SET = {"猥亵", "性爱", "道具", "插入", "侍奉"}
""" hidden_value 结算的行为：标签里至少有其中一个 """
REWARD_PREFIX_SET = {"声望", "好感"}
""" commission_reward 结算的奖励项的前缀 """
GROUP_SEX_PART_LIST = ("mouth", "L_hand", "penis", "侍奉", "anal")
""" 群交面板的部位记号，侍奉为阴茎（侍奉）一栏 """
CHILD_ERROR = "子进程出错"
""" 子进程收集失败时结果里唯一的键 """


def game(name: str) -> ModuleType:
  """按模块全名 name（如 Script.Core.get_text）导入游戏模块，返回模块"""
  return importlib.import_module(name)


def set_language(language: str) -> Callable[[str], str]:
  """
  让游戏照常读 config.ini，读完把 language 设成指定语言，再载入翻译
  Keyword arguments:
  language -- 语言，如 zh_CN、en_US
  Return arguments:
  Callable -- 该语言的翻译函数 get_text._
  """
  normal_config: Any = game("Script.Config.normal_config")
  read_config_ini = normal_config.init_normal_config

  def read_config_ini_with_language() -> None:
    """读 config.ini 后设定语言"""
    read_config_ini()
    normal_config.config_normal.language = language

  normal_config.init_normal_config = read_config_ini_with_language
  # get_text 在第一次导入时按 config_normal.language 选翻译，所以先读配置
  normal_config.init_normal_config()
  translate: Callable[[str], str] = game("Script.Core.get_text")._
  return translate


class LanguageRun:
  """以一种语言启动并开新游戏的游戏，各项结果由它的方法取得"""

  def __init__(self, language: str) -> None:
    """
    启动游戏，开新游戏
    Keyword arguments:
    language -- 语言
    """
    # 不绑定成 _：buildpo.py 的 xgettext 只抽 _() 里的字符串，
    # 测试里的按钮文字不进翻译模板
    self.translate = set_language(language)
    self.world: Any = game("tests.world").FullWorld.load()
    self.cache: Any = self.world.cache
    self.constant: Any = game("Script.Core.constant")
    self.config: Any = game("Script.Config.game_config")
    self.new_game()
    self.player: Any = self.cache.character_data[0]
    self.amiya: Any = self.cache.character_data[AMIYA_ID]
    self.summon_mode_chosen = False

  def press(self, *msgid_list: str) -> None:
    """安排按下当前语言下的这些按钮（msgid_list：按钮文字的原文）"""
    self.world.player.press(*[self.translate(text) for text in msgid_list])

  def instruct(self, instruct_id: str, presses: tuple[str, ...] = ()) -> None:
    """
    像玩家一样点下指令
    Keyword arguments:
    instruct_id -- 指令id
    presses -- 之后依次按下的按钮文字（当前语言）
    """
    game("tests.snapshot_states").instruct(self.world, instruct_id, presses)

  def new_game(self) -> None:
    """与 FullWorld.new_game 相同的开新游戏流程，按钮文字取当前语言下的文字"""
    flow: Any = game("Script.UI.Flow.creator_character_flow")
    self.press(" -【初次唤醒】-")
    game("Script.UI.Flow.title_flow").title_panel()
    now_panel_id = self.cache.now_panel_id
    if now_panel_id != self.constant.Panel.CREATOR_CHARACTER:
      raise AssertionError(f"标题画面没有进入创建角色：{now_panel_id}")
    self.press("我读完并理解了以上8条，我对自己负责，我不删，我要玩")
    self.world.player.type(self.world.PLAYER_NAME)
    self.press("助理干员")
    self.world.player.press(f"[{AMIYA_ID:04d}]")
    self.press("睁开双眼")
    flow.creator_character_panel()
    self.world.player.check_done()
    game("tests.world").seed_everything()

  def summon(self, chara_id: int) -> None:
    """
    在干员位置一览里召集干员到博士身边，等她走到
    Keyword arguments:
    chara_id -- 角色id
    """
    chara = self.cache.character_data[chara_id]
    # 面板记住上次选的召集方式，只在第一次按
    mode = () if self.summon_mode_chosen else ("召集到自己当前位置",)
    self.summon_mode_chosen = True
    presses = tuple(self.translate(text) for text in mode)
    presses += (chara.name, self.translate("返回"))
    self.instruct(self.constant.Instruct.ALL_NPC_POSITION, presses)
    for _ in range(24):
      if chara.position == self.player.position:
        break
      self.instruct(self.constant.Instruct.WAIT)
    # 好感与信赖的上限，日常互动能攒到，够邀请群交与邀请H的判定
    chara.favorability[0] = 100000
    chara.trust = 300

  def group_sex_serve(self) -> list[Any]:
    """
    在博士办公室召集凯尔希与阿米娅，邀请群交；编辑群交行动：
    肛门选阿米娅与她的第一个可选指令，侍奉选凯尔希与 handjob，退出面板后结束群交
    Return arguments:
    list -- 退出面板后的群交模板 A
    """
    instruct = self.constant.Instruct
    game("tests.snapshot_states").walk(self.world, ["中枢", "博士办公室"])
    self.summon(KALTSIT_ID)
    self.summon(AMIYA_ID)
    self.player.target_character_id = AMIYA_ID
    self.instruct(instruct.ASK_GROUP_SEX)
    behavior = self.config.config_behavior
    panel = game("Script.System.Sex_System.group_sex_panel")
    anal_status = panel.get_status_id_list_from_group_sex_body_part("anal")[0]
    no_chara = self.translate("未选择角色")
    no_status = self.translate("未选择指令")
    presses: tuple[str, ...] = (no_chara, f"[{AMIYA_ID:04d}]", no_status)
    presses += (behavior[anal_status].name, no_chara, f"[{KALTSIT_ID:04d}]")
    presses += (no_status, behavior["handjob"].name, self.translate("[返回]"))
    template = self.player.h_state.group_sex_body_template_dict["A"]
    try:
      self.instruct(instruct.EDIT_GROUP_SEX_TEMPLE, presses)
      return [dict(template[0]), template[1]]
    finally:
      # 面板中途出错时清掉没用掉的按钮，回到主界面再结束群交
      self.world.player.planned.clear()
      self.cache.now_panel_id = self.constant.Panel.IN_SCENE
      self.instruct(instruct.GROUP_SEX_END)

  def enter_h(self) -> bool:
    """
    回博士房间，召集阿米娅，点选她，邀请H
    Return arguments:
    bool -- 是否进入了 H
    """
    game("tests.snapshot_states").walk(self.world, ["中枢", "博士房间"])
    self.summon(AMIYA_ID)
    self.player.target_character_id = AMIYA_ID
    self.instruct(self.constant.Instruct.DO_H)
    in_h: bool = game("Script.Design.handle_premise").handle_is_h(0)
    return in_h

  def npc_active_h(self) -> list[Any]:
    """「交给对方」前后的游戏时间与之后的玩家行为"""
    time_before = str(self.cache.game_time)
    self.instruct(self.constant.Instruct.CHANGE_TOP_AND_BOTTOM)
    behavior = self.player.behavior.behavior_id
    return [time_before, str(self.cache.game_time), behavior, self.player.state]

  def group_sex_parts(self) -> dict[str, list[str]]:
    """群交各部位可选的行为id"""
    panel: Any = game("Script.System.Sex_System.group_sex_panel")
    find = panel.get_status_id_list_from_group_sex_body_part
    return {part: sorted(find(part)) for part in GROUP_SEX_PART_LIST}

  def sex_assistant(self) -> list[str]:
    """调教助手可用的行为id"""
    panel: Any = game("Script.UI.Panel.confinement_and_training")
    return sorted(panel.get_all_can_use_behavior_id_for_sex_assistant())

  def hidden_value(self) -> dict[str, int]:
    """隐奸中玩家做各项H行为后的被发现度"""
    panel: Any = game("Script.System.Sex_System.hidden_sex_panel")
    h_state = self.player.h_state
    value_dict = {}
    now_behavior_id = self.player.behavior.behavior_id
    for behavior_id, behavior_data in self.config.config_behavior.items():
      if not HIDDEN_TAG_SET & set(behavior_data.tag.split("|")):
        continue
      self.player.behavior.behavior_id = behavior_id
      h_state.hidden_sex_discovery_dregree = HIDDEN_START
      panel.settle_hidden_value_by_action(0, now_duration=HIDDEN_DURATION)
      value_dict[behavior_id] = h_state.hidden_sex_discovery_dregree
    self.player.behavior.behavior_id = now_behavior_id
    return value_dict

  def commission_check(self) -> dict[str, list[bool]]:
    """每项委托的需求与奖励是否满足"""
    function: Any = game(
        "Script.System.Field_Commission_System.field_commission_function"
    )
    check = function.get_commission_demand_and_reward
    return {
        str(cid): [check(cid)[0], check(cid, [], True)[0]]
        for cid in sorted(self.config.config_commission)
    }

  def commission_list(self) -> list[int]:
    """外勤委托面板列出的委托id"""
    panel_module: Any = game(
        "Script.System.Field_Commission_System.field_commission_panel"
    )
    panel = panel_module.Field_Commission_Panel(100)
    self.press("[返回]")
    panel.draw()
    self.world.player.check_done()
    return list(panel.handle_panel.text_list)

  def commission_reward(self) -> list[Any]:
    """逐项结算前缀在 REWARD_PREFIX_SET 里的委托奖励：项数、声望与阿米娅的好感"""
    function: Any = game(
        "Script.System.Field_Commission_System.field_commission_function"
    )
    settled = 0
    for commission in self.config.config_commission.values():
      for text in commission.reward.split("&"):
        if text.split("_")[0] in REWARD_PREFIX_SET:
          function.process_commission_text(
              text, True, True, [AMIYA_ID], "", "", True
          )
          settled += 1
    reputation = self.cache.country.nation_reputation
    reputation_dict = {str(key): reputation[key] for key in sorted(reputation)}
    return [settled, reputation_dict, self.amiya.favorability[0]]

  def cook_question(self) -> dict[str, list[int]]:
    """每道菜各阶段与各特殊调味替换阶段的题数"""
    cooking: Any = game("Script.System.Cooking_System.cooking")
    stage_list = list(cooking.COOK_QUESTION_STAGES)
    for seasoning in SPECIAL_SEASONING_LIST:
      stage_list.append(
          cooking.get_special_seasoning_question_stage(seasoning)[1]
      )
    count_dict = {}
    for food_id in sorted(self.config.config_cook_question):
      question_lib = cooking.get_food_cook_questions(food_id)
      count_dict[str(food_id)] = [
          len(question_lib.get(stage, [])) for stage in stage_list
      ]
    return count_dict


def collect(language: str, group_sex: bool) -> dict[str, Any]:
  """
  以指定语言启动游戏，按模块说明里的各项记下结果
  Keyword arguments:
  language -- 语言
  group_sex -- 为真时只取 group_sex_serve，否则取其余各项
  Return arguments:
  dict -- 项目名 -> 结果或异常；另有 "性爱"：get_text._("性爱") 的结果
  """
  run = LanguageRun(language)
  results: dict[str, Any] = {"性爱": run.translate("性爱")}
  item_dict: dict[str, Callable[[], Any]] = {
      "in_h": run.enter_h,
      "npc_active_h": run.npc_active_h,
      "group_sex_parts": run.group_sex_parts,
      "sex_assistant": run.sex_assistant,
      "hidden_value": run.hidden_value,
      "commission_check": run.commission_check,
      "commission_list": run.commission_list,
      "commission_reward": run.commission_reward,
      "cook_question": run.cook_question,
  }
  if group_sex:
    item_dict = {"group_sex_serve": run.group_sex_serve}
  for key, item in item_dict.items():
    try:
      results[key] = item()
    except (KeyError, IndexError, UnboundLocalError) as error:
      results[key] = f"异常 {type(error).__name__}: {error}"
  return results


class TagLogicSameInEnglishTest(SlowTestCase):
  """英文环境下按标签、委托文本与烹饪阶段判定的结果与中文环境相同"""

  time_limit = 600
  """ 四次启动游戏，比默认时限长 """

  def setUp(self) -> None:
    """只设时限；各局游戏在测试里各自启动"""
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()

  def collect_in_child(self, language: str, group_sex: bool) -> dict[str, Any]:
    """
    在 fork 出的子进程里以指定语言收集结果，经管道传回
    Keyword arguments:
    language -- 语言
    group_sex -- 交给 collect
    Return arguments:
    dict -- collect 的结果；子进程出错时为 {CHILD_ERROR: 堆栈}
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
      os.close(read_fd)
      signal.alarm(self.time_limit)
      result: dict[str, Any] = {CHILD_ERROR: "没有结果"}
      try:
        result = collect(language, group_sex)
      finally:
        # 出错时 finally 里仍能取到正在传出的异常
        if CHILD_ERROR in result:
          result[CHILD_ERROR] = traceback.format_exc()
        with os.fdopen(write_fd, "w", encoding="utf-8") as pipe:
          json.dump(result, pipe, ensure_ascii=False)
        os._exit(0)
    os.close(write_fd)
    killed = True
    try:
      with os.fdopen(read_fd, "r", encoding="utf-8") as pipe:
        child_result: dict[str, Any] = json.load(pipe)
      killed = False
    finally:
      if killed:
        os.kill(pid, signal.SIGKILL)
      os.waitpid(pid, 0)
    return child_result

  def test_same_as_chinese(self) -> None:
    """en_US 下每一项的结果都与 zh_CN 相同"""
    chinese = self.collect_in_child(CHINESE, False)
    chinese.update(self.collect_in_child(CHINESE, True))
    english = self.collect_in_child(ENGLISH, True)
    for result in (chinese, english):
      self.assertNotIn(CHILD_ERROR, result, result.get(CHILD_ERROR))
    english.update(collect(ENGLISH, False))
    self.assertNotEqual(
        english.pop("性爱"), chinese.pop("性爱"), "en_US 下 _() 给出译文"
    )
    # 基准本身要走到被比较的分支，比较才有意义
    self.assertTrue(chinese.pop("in_h"), "zh_CN 下邀请H 进入了 H")
    self.assertTrue(english.pop("in_h"), "en_US 下邀请H 进入了 H")
    time_before, time_after = chinese["npc_active_h"][:2]
    self.assertNotEqual(time_before, time_after, "zh_CN 下逆推选了行为")
    serve = [[KALTSIT_ID], "handjob"]
    self.assertEqual(chinese["group_sex_serve"][1], serve, "侍奉选好了")
    self.assertTrue(any(chinese["group_sex_parts"].values()), "群交有可选行为")
    value_count = len(set(chinese["hidden_value"].values()))
    self.assertGreater(value_count, 2, "不同强度的行为结算出不同的被发现度")
    self.assertIsInstance(chinese["commission_reward"], list, "结算奖励没出错")
    cook = chinese["cook_question"].values()
    self.assertTrue(any(all(count) for count in cook), "有菜每个阶段都有题")
    differ_list = [key for key in chinese if english.get(key) != chinese[key]]
    detail = "\n".join(
        f"{key}：en_US {str(english.get(key))[:300]}，"
        f"zh_CN {str(chinese[key])[:300]}"
        for key in differ_list
    )
    self.assertEqual(differ_list, [], f"en_US 与 zh_CN 不同的项：\n{detail}")
