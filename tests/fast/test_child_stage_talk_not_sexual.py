# -*- coding: UTF-8 -*-
"""
儿童阶段的口上与事件不含 H 内容的检查
====================================
本测试只读数据文件的 id、行为、前提、效果与类别列，不读文本列，也不启动游戏。
测试要求：挂在儿童阶段的行里没有 H 内容；通用文本里没有挂在儿童阶段的行；JUDGED_DELETED 列出的行都已不在文件里。

「挂在儿童阶段」：前提里有选中素质 101、102、103 的条件（CVP 素质条件，或阶段前提 CHILD_PREMISES）；养成事件在 CHILD_EVENT_BUCKETS 桶里也算。
「H 内容」：满足任一条——
- 行为的标签（Behavior_Data.csv 的 tag 列）首段是 SEXUAL_TAG_HEADS 之一，或含 SEXUAL_SUB_TAGS 之一；
- 行为的标签只有「二段结算」，且行为名匹配 SEXUAL_SECOND_BEHAVIOR_PATTERN；
- 行为不在 Behavior_Data.csv 里，口上文件在 H_TALK_DIRS 目录下；
- 前提里有选中性技能力（Ability.csv 里 ability_type 为 SEX_SKILL_ABILITY_TYPE）的 Course、CourseShowOff 或 A 条件；
- 前提里有 H 状态前提（is_h_premise）；
- 通用文本的类型是 H 动作分段，或是 INTIMATE_PARTS 部位的描述与短词（is_sexual_common_type）；
- 事件效果里有绝顶效果（CVE_*_Climax）。
通用文本里挂在儿童阶段、不属于 H 内容的行描写的是儿童阶段的身体，归为 child_body。
挂在儿童阶段的口上里，行为不在 Behavior_Data.csv 里、文件也不在 H_TALK_DIRS 下的行无法判定，测试要求没有这样的行。
"""

import csv
import json
import os
import re
import subprocess

from tests.fast.base import FastTestCase
from tests.world import ROOT

CHILD_TALENTS = (101, 102, 103)
""" 儿童阶段素质：婴儿、幼女与旧的萝莉阶段 """
CHILD_EVENT_BUCKETS = frozenset({"101", "102", "103", "200"})
""" 只派给儿童阶段的养成事件桶（sub_key）：婴儿、幼女、旧萝莉阶段与期末 """
CHILD_PREMISES = frozenset(
    {
        "baby_1",
        "child_1",
        "loli_1",
        "self_child_or_loli_1",
        "t_child_or_loli_1",
        "self_underage",
        "t_baby_1",
    }
)
""" 只在角色处于儿童阶段时成立的具名前提 """
SEXUAL_TAG_HEADS = frozenset({"猥亵", "性爱"})
""" 行为标签首段：猥亵与性爱两类指令 """
SEXUAL_SUB_TAGS = frozenset({"侍奉", "H装备", "H药物"})
""" 二段结算行为里属于 H 的子标签 """
SEXUAL_SECOND_BEHAVIOR_PATTERN = re.compile(
    r"^(?:\w+_orgasm_\w+|plural_orgasm_\d+|extra_orgasm|semen_drinking_climax|p_no_semen_climax|"
    r"first_(?:a_|u_|w_)?sex|first_kiss(?:_but_penis)?|\w+_mark_\d+|in_unconscious_(?:cum_on_\w+|stolen_\w+)|be_invited_join_group_sex|(?:join|watch)_sex_class)$"
)
""" 标签只有「二段结算」的行为里属于 H 的：绝顶、初次记录（含初吻）、刻印、无意识射精与偷取、群交邀请、实操课 """
H_TALK_DIRS = ("data/talk/obscenity/", "data/talk/sex/")
""" 猥亵与性爱指令的口上目录：行为不在 Behavior_Data.csv 里时按目录判定 """
H_PREMISE_EXTRA = frozenset(
    {
        "is_h",
        "self_is_h",
        "t_is_h",
        "group_sex_mode_on",
        "hypnosis_active_h",
        "t_hypnosis_active_h",
    }
)
""" 类别不以 H_ 开头的 H 状态前提 """
H_PREMISE_CATEGORIES = ("H_", "特殊flag_隐奸", "特殊flag_露出")
""" 前提说明首词以这些开头的前提属于 H 状态（取反的除外） """
INTIMATE_PARTS = frozenset({"anal", "clitoris", "urethra", "vagina", "womb"})
""" 私密部位：通用文本里这些部位的描述（类型即部位名）与短词（body_part_部位_s_A/B）属于 H """
SEX_SKILL_ABILITY_TYPE = "5"
""" Ability.csv 里性技能力的 ability_type """
CVP_ABILITY = re.compile(r"^cvp_a[12]_(?:course|courseshowoff|a)\|(\d+)_")
""" 选中某项能力的 CVP 条件：课程、学习炫耀与能力等级 """
CVP_TALENT = re.compile(r"^cvp_a[12]_t\|(\d+)_([a-z]+)_(-?\d+)$")
""" CVP 素质条件：CVP_A1/A2_T|素质id_比较符_值 """
JUDGED_DELETED = {
    "data/talk/daily/apologize.csv": "1005-1009",
    "data/talk/daily/apologize_failed.csv": "1005-1009",
    "data/talk/daily/check_report_card.csv": "1002-1003,1010-1013,1016-1017",
    "data/talk/daily/follow.csv": "1003-1005",
    "data/talk/daily/free_play.csv": "1004-1007",
    "data/talk/daily/get_up.csv": "1001,1005-1009",
    "data/talk/daily/gift/give_gift_age_expansion.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_age_shrinking.csv": "1000-1004",
    "data/talk/daily/gift/give_gift_apology.csv": "1000-1019",
    "data/talk/daily/gift/give_gift_breast_expansion.csv": "1000-1039",
    "data/talk/daily/gift/give_gift_breast_shrinking.csv": "1000-1039",
    "data/talk/daily/gift/give_gift_butt_expansion.csv": "1000-1019",
    "data/talk/daily/gift/give_gift_butt_shrinking.csv": "1000-1019",
    "data/talk/daily/gift/give_gift_fake_pregnancy.csv": "1030-1039",
    "data/talk/daily/gift/give_gift_fake_pregnancy_end.csv": "1030-1039",
    "data/talk/daily/gift/give_gift_favorability.csv": "1000-1134,2000-2134",
    "data/talk/daily/gift/give_gift_feet_expansion.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_feet_shrinking.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_growth_accelerate.csv": "1035-1039",
    "data/talk/daily/gift/give_gift_growth_resume.csv": "1005-1009",
    "data/talk/daily/gift/give_gift_growth_stop.csv": "1002,1005-1009",
    "data/talk/daily/gift/give_gift_hatch_accelerate.csv": "1030-1039",
    "data/talk/daily/gift/give_gift_lactation_medicine.csv": "1000-1024,1030-1054",
    "data/talk/daily/gift/give_gift_leg_expansion.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_leg_shrinking.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_milkblock_medicine.csv": "1000-1009",
    "data/talk/daily/gift/give_gift_penis_mold.csv": "1000-1019",
    "data/talk/daily/gift/give_gift_pregnancy_accelerate.csv": "1060-1079",
    "data/talk/daily/listen_complaint.csv": "1005-1009",
    "data/talk/play/interest_class/interest_cards.csv": "1002",
    "data/talk/play/interest_class/interest_chess.csv": "1002",
    "data/talk/play/interest_class/interest_classic_instrument.csv": "1002-1003",
    "data/talk/play/interest_class/interest_coffee.csv": "1003",
    "data/talk/play/interest_class/interest_dance.csv": "1003",
    "data/talk/play/interest_class/interest_dessert.csv": "1002",
    "data/talk/play/interest_class/interest_mahjong.csv": "1002",
    "data/talk/play/interest_class/interest_modern_instrument.csv": "1003",
    "data/talk/play/interest_class/interest_movie.csv": "1002",
    "data/talk/play/interest_class/interest_photography.csv": "1002",
    "data/talk/play/interest_class/interest_play_house.csv": "1000-1003",
    "data/talk/play/interest_class/interest_reading.csv": "1002-1003",
    "data/talk/play/interest_class/interest_singing.csv": "1003",
    "data/talk/play/interest_class/interest_tea.csv": "1003",
    "data/talk/play/interest_class/interest_water.csv": "1002-1003",
    "data/talk/system/second_caught_skip_class.csv": "1006-1013",
    "data/talk/system/second_fall/love_1.csv": "1000-1009",
    "data/talk/system/second_fall/love_2.csv": "1000-1009",
    "data/talk/system/second_fall/love_3.csv": "1000-1009",
    "data/talk/system/second_fall/love_4.csv": "1000-1009",
    "data/talk/system/second_fall/obey_1.csv": "1000-1009",
    "data/talk/system/second_fall/obey_2.csv": "1000-1009",
    "data/talk/system/second_fall/obey_3.csv": "1000-1009",
    "data/talk/system/second_fall/obey_4.csv": "1000-1009",
    "data/talk/system/second_pregnancy.csv": "2-3,2001-2008,2029-2038,2064-2073,2099-2108,2134-2143,2169-2178,2204-2213,2239-2248,2274-2283,2309-2318,2344-2353,2394-2403,2434-2443,2474-2483",
    "data/talk/system/second_show_off_study/show_off_combat.csv": "1002-1003",
    "data/talk/system/second_show_off_study/show_off_command.csv": "1003",
    "data/talk/system/second_show_off_study/show_off_cooking.csv": "1003",
    "data/talk/system/second_show_off_study/show_off_farming.csv": "1003",
    "data/talk/system/second_show_off_study/show_off_knowledge.csv": "1002",
    "data/talk/system/second_show_off_study/show_off_manufacture.csv": "1002-1003",
    "data/talk/system/second_show_off_study/show_off_medical.csv": "1003",
    "data/talk/system/second_show_off_study/show_off_music.csv": "1003",
    "data/talk/system/second_show_off_study/show_off_painting.csv": "1002",
    "data/talk/work/attent_class/attent_class_combat.csv": "1002-1003,1006",
    "data/talk/work/attent_class/attent_class_command.csv": "1003,1007,1009-1010",
    "data/talk/work/attent_class/attent_class_cooking.csv": "1002-1003,1006-1007,1010",
    "data/talk/work/attent_class/attent_class_farming.csv": "1002-1003,1006,1009-1010",
    "data/talk/work/attent_class/attent_class_knowledge.csv": "1003-1005,1008-1009,1012",
    "data/talk/work/attent_class/attent_class_manufacture.csv": "1002,1006",
    "data/talk/work/attent_class/attent_class_medical.csv": "1002-1003,1006",
    "data/talk/work/attent_class/attent_class_music.csv": "1002-1003,1006,1009-1010",
    "data/talk/work/attent_class/attent_class_painting.csv": "1003,1006",
    "data/talk/work/attent_class/attent_class_speech.csv": "1002-1003,1006-1007,1009-1010",
    "data/talk/work/intern_class/intern_bath_rest.csv": "1002-1003",
    "data/talk/work/intern_class/intern_blacksmith.csv": "1003",
    "data/talk/work/intern_class/intern_clinic.csv": "1002-1003",
    "data/talk/work/intern_class/intern_diplomatic.csv": "1002",
    "data/talk/work/intern_class/intern_dormitory.csv": "1002-1003",
    "data/talk/work/intern_class/intern_greenhouse.csv": "1003",
    "data/talk/work/intern_class/intern_hr.csv": "1003",
    "data/talk/work/intern_class/intern_kitchen.csv": "1002-1003",
    "data/talk/work/intern_class/intern_maintenance.csv": "1002",
    "data/talk/work/intern_class/intern_nursery.csv": "1002-1003",
    "data/talk/work/intern_class/intern_power.csv": "1003",
    "data/talk/work/intern_class/intern_production.csv": "1002",
    "data/talk/work/intern_class/intern_training.csv": "1002-1003",
    "data/talk/work/intern_class/intern_ward.csv": "1003",
    "data/talk/work/pe_class/pe_fight_room.csv": "1003-1004",
    "data/talk/work/pe_class/pe_gym.csv": "1004",
    "data/talk/work/pe_class/pe_swimming.csv": "1004",
    "data/talk/work/self_study/self_study_combat.csv": "1002-1004",
    "data/talk/work/self_study/self_study_command.csv": "1002-1004",
    "data/talk/work/self_study/self_study_cooking.csv": "1002-1003",
    "data/talk/work/self_study/self_study_farming.csv": "1002,1004",
    "data/talk/work/self_study/self_study_knowledge.csv": "1003-1006",
    "data/talk/work/self_study/self_study_manufacture.csv": "1003-1004",
    "data/talk/work/self_study/self_study_medical.csv": "1002-1004",
    "data/talk/work/self_study/self_study_music.csv": "1002-1004",
    "data/talk/work/self_study/self_study_painting.csv": "1002-1004",
    "data/talk/work/self_study/self_study_speech.csv": "1002-1004",
    "data/talk/work/skip_class.csv": "1002-1003",
}
""" 挂在儿童阶段、按规则不属于 H、经逐行判定删除的口上行：{文件: cid 区间}，区间写作「起-止」，以逗号分隔 """


def compare(op: str, value: int, x: int) -> bool:
  """
  计算 CVP 比较
  Keyword arguments:
  op -- 比较符（e/ne/g/ge/l/le）
  value -- 条件里的值
  x -- 角色的数值
  Return arguments:
  bool -- 条件是否成立
  """
  return {
      "e": x == value,
      "ne": x != value,
      "g": x > value,
      "ge": x >= value,
      "l": x < value,
      "le": x <= value,
  }[op]


def load_premise_categories() -> dict:
  """
  读 constant_promise.py 里每个前提的说明首词（类别）
  Keyword arguments:
  无
  Return arguments:
  dict -- {前提键(小写): 类别}
  """
  with open(
      os.path.join(ROOT, "Script", "Core", "constant_promise.py"),
      encoding="utf-8",
  ) as f:
    text = f.read()
  # pyink 把超过 80 列的常量赋值折成「常量名 = (」「值」「)」三行，先并回一行
  lines = re.sub(r'= \(\n\s*("[^"\n]*")\n\s*\)\n', r"= \1\n", text).split("\n")
  categories = {}
  for i, line in enumerate(lines[:-1]):
    match = re.match(r'\s+[A-Z0-9_]+ = "([^"]+)"$', line)
    if match:
      doc = lines[i + 1].strip().strip('"').split()
      categories[match.group(1).lower()] = doc[0] if doc else ""
  return categories


def load_behavior_tags() -> dict:
  """
  读 Behavior_Data.csv 的行为标签
  Keyword arguments:
  无
  Return arguments:
  dict -- {行为英文名: 标签串}
  """
  with open(
      os.path.join(ROOT, "data", "csv", "Behavior_Data.csv"),
      encoding="utf-8-sig",
      newline="",
  ) as f:
    return {row[1]: row[5] for row in list(csv.reader(f))[5:] if len(row) == 6}


def load_sex_skill_abilities() -> set:
  """
  读 Ability.csv 里的性技能力
  Keyword arguments:
  无
  Return arguments:
  set -- 性技能力 id
  """
  with open(
      os.path.join(ROOT, "data", "csv", "Ability.csv"),
      encoding="utf-8-sig",
      newline="",
  ) as f:
    return {
        int(row[0])
        for row in list(csv.reader(f))[5:]
        if len(row) > 1
        and row[0].isdigit()
        and row[1] == SEX_SKILL_ABILITY_TYPE
    }


PREMISE_CATEGORIES = load_premise_categories()
""" 前提类别表 """
BEHAVIOR_TAGS = load_behavior_tags()
""" 行为标签表 """
SEX_SKILL_ABILITIES = load_sex_skill_abilities()
""" 性技能力 id """


def child_keys(premises) -> set:
  """
  取出前提里选中儿童阶段的条件
  Keyword arguments:
  premises -- 前提键列表
  Return arguments:
  set -- 选中素质 101/102/103 的前提键（小写）
  """
  keys = set()
  for premise in premises:
    key = premise.strip().lower()
    if key in CHILD_PREMISES:
      keys.add(key)
    match = CVP_TALENT.match(key)
    if match and int(match.group(1)) in CHILD_TALENTS:
      op, value = match.group(2), int(match.group(3))
      if compare(op, value, 1) and not compare(op, value, 0):
        keys.add(key)
  return keys


def is_h_premise(premise: str) -> bool:
  """
  前提是否要求 H 状态
  Keyword arguments:
  premise -- 前提键
  Return arguments:
  bool -- 是否为 H 状态前提
  """
  key = premise.strip().lower()
  if key in H_PREMISE_EXTRA:
    return True
  category = PREMISE_CATEGORIES.get(key, "")
  if category == "初次_时间":
    return "_sex_in_today" in key
  if not category.startswith(H_PREMISE_CATEGORIES):
    return False
  return not re.search(r"not|_off$|_0$", key)


def selects_sex_skill(premises) -> bool:
  """
  前提里是否有选中性技能力的条件
  Keyword arguments:
  premises -- 前提键列表
  Return arguments:
  bool -- 是否选中性技能力
  """
  for premise in premises:
    match = CVP_ABILITY.match(premise.strip().lower())
    if match and int(match.group(1)) in SEX_SKILL_ABILITIES:
      return True
  return False


def is_sexual_behavior(behavior_id: str) -> bool:
  """
  行为是否属于 H 内容
  Keyword arguments:
  behavior_id -- 行为英文名
  Return arguments:
  bool -- 是否属于 H 内容
  """
  tags = BEHAVIOR_TAGS.get(behavior_id, "").split("|")
  if tags[0] in SEXUAL_TAG_HEADS or SEXUAL_SUB_TAGS & set(tags):
    return True
  return tags == ["二段结算"] and bool(
      SEXUAL_SECOND_BEHAVIOR_PATTERN.match(behavior_id)
  )


def is_sexual_common_type(type_id: str) -> bool:
  """
  通用文本类型是否属于 H：H 动作分段（插入与绝顶），或私密部位的描述与短词
  Keyword arguments:
  type_id -- 通用文本类型
  Return arguments:
  bool -- 是否属于 H
  """
  if type_id.startswith("action_part_penis_in_body_") or re.match(
      r"^action_part_\w+_orgasm_\w+$", type_id
  ):
    return True
  return re.sub(r"^body_part_(\w+)_s_[AB]$", r"\1", type_id) in INTIMATE_PARTS


def classify(
    kind: str,
    behavior_or_type: str,
    premises,
    effects=(),
    child_bucket: bool = False,
    path: str = "",
) -> str:
  """
  给一行数据分类
  Keyword arguments:
  kind -- talk（口上）、talk_common（通用文本）、event（JSON 事件）或 official_event（养成事件，没有行为）
  behavior_or_type -- 口上与 JSON 事件的行为英文名，通用文本的类型；养成事件不用
  premises -- 前提键列表
  effects -- 事件的效果键列表
  child_bucket -- 养成事件是否在 CHILD_EVENT_BUCKETS 桶里
  path -- 口上文件相对仓库根目录的路径
  Return arguments:
  str -- other（不挂在儿童阶段）、sexual（挂在儿童阶段且属于 H）、child_body（通用文本挂在儿童阶段、不属于 H）、undecided（挂在儿童阶段、无法判定）、kept（挂在儿童阶段、不属于 H）
  """
  keys = child_keys(premises)
  if not keys and not child_bucket:
    return "other"
  if any(is_h_premise(premise) for premise in premises):
    return "sexual"
  if any(re.match(r"^cve_a\d_climax\|", effect.lower()) for effect in effects):
    return "sexual"
  if kind == "official_event":
    return "kept"
  if kind == "talk_common":
    if is_sexual_common_type(behavior_or_type):
      return "sexual"
    return "child_body"
  if is_sexual_behavior(behavior_or_type) or selects_sex_skill(premises):
    return "sexual"
  if behavior_or_type not in BEHAVIOR_TAGS:
    return "sexual" if path.startswith(H_TALK_DIRS) else "undecided"
  return "kept"


def expand_ranges(text: str) -> set:
  """
  把「起-止」区间串展开成 cid 集合
  Keyword arguments:
  text -- 以逗号分隔的区间，单个 cid 也可
  Return arguments:
  set -- cid 字符串集合
  """
  cids: set[str] = set()
  for part in text.split(","):
    start, _, end = part.partition("-")
    cids.update(str(cid) for cid in range(int(start), int(end or start) + 1))
  return cids


def tracked_files(*paths) -> list:
  """
  列出 git 跟踪的文件
  Keyword arguments:
  paths -- 仓库内的目录
  Return arguments:
  list -- 相对仓库根目录的路径
  """
  result = subprocess.run(
      ["git", "-c", "core.quotepath=off", "ls-files", *paths],
      cwd=ROOT,
      capture_output=True,
      text=True,
      check=True,
  )
  return [path for path in result.stdout.split("\n") if path]


def iter_rows():
  """
  逐行给出口上、通用文本与事件的分类
  Keyword arguments:
  无
  Return arguments:
  iterator -- (文件, cid 或 uid, 分类)
  """
  for path in tracked_files(
      "data/talk", "data/talk_common", "data/official_event"
  ):
    if not path.endswith(".csv"):
      continue
    with open(os.path.join(ROOT, path), encoding="utf-8-sig", newline="") as f:
      rows = list(csv.reader(f))
    header = rows[0]
    for row in rows[5:]:
      if not row or not row[0].strip():
        continue
      values = dict(zip(header, row))
      if path.startswith("data/official_event/"):
        premise_columns = ["premise"] + [
            f"option_{i}_premise" for i in range(1, 5)
        ]
        premises = [
            p
            for column in premise_columns
            for p in values.get(column, "").split("&")
            if p
        ]
        effects = [
            e
            for i in range(1, 5)
            for e in values.get(f"option_{i}_effect", "").split("&")
            if e
        ]
        yield path, values["cid"], classify(
            "official_event",
            "",
            premises,
            effects,
            values["sub_key"] in CHILD_EVENT_BUCKETS,
        )
      elif path.startswith("data/talk_common/"):
        yield path, values["cid"], classify(
            "talk_common", values["type_id"], values["premise"].split("&")
        )
      else:
        yield path, values["cid"], classify(
            "talk",
            values["behavior_id"],
            values["premise"].split("&"),
            path=path,
        )
  for path in tracked_files("data/event"):
    if not path.endswith(".json"):
      continue
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
      events = json.load(f)
    for uid, event in events.items():
      yield path, uid, classify(
          "event",
          event.get("behavior_id", ""),
          list(event.get("premise", {})),
          list(event.get("effect", {})),
      )


class ChildStageTalkNotSexualTest(FastTestCase):
  """挂在儿童阶段的口上与事件里没有 H 内容，也没有无法判定的行"""

  rows: list[tuple[str, str, str]]

  @classmethod
  def setUpClass(cls) -> None:
    """
    给全部行分类一次
    Keyword arguments:
    无
    Return arguments:
    无
    """
    cls.rows = list(iter_rows())

  def test_no_sexual_child_stage_rows(self) -> None:
    """没有既挂在儿童阶段、又属于 H 内容的行"""
    sexual = [
        f"{path}:{cid}" for path, cid, kind in self.rows if kind == "sexual"
    ]
    self.assertEqual(len(sexual), 0, sexual[:20])

  def test_no_child_body_common_rows(self) -> None:
    """通用文本里没有挂在儿童阶段的行"""
    child_body = [
        f"{path}:{cid}" for path, cid, kind in self.rows if kind == "child_body"
    ]
    self.assertEqual(len(child_body), 0, child_body[:20])

  def test_judged_rows_deleted(self) -> None:
    """JUDGED_DELETED 列出的行都已不在文件里"""
    present = {(path, cid) for path, cid, _ in self.rows}
    remaining = [
        f"{path}:{cid}"
        for path, text in JUDGED_DELETED.items()
        for cid in sorted(expand_ranges(text))
        if (path, cid) in present
    ]
    self.assertEqual(len(remaining), 0, remaining[:20])

  def test_no_undecided_child_stage_rows(self) -> None:
    """没有挂在儿童阶段、又无法判定的行"""
    undecided = [
        f"{path}:{cid}" for path, cid, kind in self.rows if kind == "undecided"
    ]
    self.assertEqual(len(undecided), 0, undecided[:20])
