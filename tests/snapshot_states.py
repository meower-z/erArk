# -*- coding: UTF-8 -*-
"""
行为快照的起始状态与玩家动作表
==============================
每个状态由开新游戏后经游戏自己的流程构建出来（build_*），再按固定的玩家动作表（PLANS）一步一步推进，每一步录一份快照（tests/snapshot.py）。
玩家的选择与输入都经 FullWorld 的 PlayerInput 按下真实按钮；动作表里没有随机，同一份代码两次运行的快照相同。

两个状态开局都选初期奖励 FIRST_BONUS。
time_stop_h -- 时停中的 H、跨午夜的睡眠、医疗部。
    构建：在「管理罗德岛」里让华法琳转住院医生、杜宾转坐诊医生；在「干员位置一览」里把阿米娅召集到博士房间，点选她，
    「时间停止流动」后「时停奸」：开始时博士与阿米娅在时停中的 H 里。
    动作表先做几样 H 指令（接吻、舔阴、爱抚胸部、插入后正常位）；理智用尽时时停与 H 一并结束，之后博士在岛上走动与等待，
    到能睡觉时在博士房间睡 8 小时：这一步里跨过午夜，跑完新一天的结算（含医疗部的每日结算），睡醒后再等一会儿。
family_commission -- 孕产、各阶段的孩子、上课与外勤委托。构建：
    - 受精：射精污浊函数（ejaculation_panel.update_semen_dirty）把精液记进子宫，生理周期（pregnancy_handle.update_reproduction_period）推进到排卵日，
      再走受精结算（get_fertilization_rate、check_fertilization）；
    - 之后的妊娠、临盆、生产（生产面板里按「焦急等待」并给每个孩子取名）、产后转育儿、婴儿长成幼女、幼女长成学员、学员长成少女，
      都走 pregnancy_handle 的结算函数。这些函数按经过的天数判断，构建时用 unittest.mock 把两个数天数的函数
      （get_pregnancy_past_day、get_child_grow_day）换成刚好达到阈值的天数，代替真的过那么多天；构建完就换回，游戏时间不跳。
      结果：特蕾西娅妊娠中；凯尔希头胎的孩子长成少女（104，在线，仍是学生岗），二胎是婴儿（101，离线），凯尔希在育儿；
      可露希尔的女儿是学员（103，在线，学生岗）；华法琳的女儿是幼女（102，离线）；
    - 在「管理罗德岛」里让可露希尔转教师，教育管理里一键排满全部教室，给可露希尔的女儿与凯尔希的长女一键选课；
    - 在基建部把机库升到 2 级，在格纳库买两辆载具，在外勤集合点派出两项委托（杜宾带补给车、华法琳带大驮兽）。
    动作表让博士去教室，等到教室里有没在上课的学生岗角色时授课；再在育儿室、食堂、图书馆之间走动与等待，跨过午夜，到委托返回之后。
    可露希尔每节课开讲时把选了这节课的学生拉进听课。
每次运行把睡醒时的自动存档换成只记下调用（run），不往检出目录的 save/ 写文件。
"""

import contextlib
from unittest import mock

FIRST_BONUS = ("窄域时停", "启动资金", "助理干员", "阿米娅")
""" 两个状态开局时选的初期奖励：初级时停素质、启动资金、助理阿米娅（好感 1000、信赖 50%） """

ASSISTANT_NAME = "阿米娅"
""" 助理的名字 """

DOCTOR_ROOM = ["中枢", "博士房间"]
DOCTOR_OFFICE = ["中枢", "博士办公室"]
NURSERY = ["教", "育儿"]
CLASSROOM = ["教", "理论教室一"]
DINING_HALL = ["生娱", "食堂"]
LIBRARY = ["书", "图书馆"]
BUILDING_ROOM = ["工程", "基建部"]
GARAGE = ["机库", "格纳库"]
ASSEMBLY_POINT = ["机库", "外勤集合点"]


class PlanError(AssertionError):
  """动作表里的指令此刻不会出现在主界面，或安排的按钮没有用掉"""


def instruct(world, instruct_id: str, presses: tuple = ()):
  """
  像玩家在主界面点下指令一样执行它：先安排之后要按的按钮，确认指令的前提都成立，交给 handle_instruct；
  指令打开了面板时显示面板（与 start_flow.start_frame 每一轮做的相同）
  Keyword arguments:
  world -- FullWorld
  instruct_id -- 指令id
  presses -- 之后依次按下的按钮文字
  Return arguments:
  无
  功能描述:
      前提不成立、安排的按钮没有用掉时抛 PlanError。
  """
  from Script.Core import constant
  from Script.Design import handle_premise
  from Script.System.Instruct_System import handle_instruct

  cache = world.cache
  failed = [
      premise
      for premise in constant.instruct_premise_data.get(instruct_id, ())
      if not handle_premise.handle_premise(premise, 0)
  ]
  if failed:
    raise PlanError(
        f"指令 {instruct_id} 此刻不会出现在主界面，不成立的前提：{failed}"
    )
  world.player.press(*presses)
  handle_instruct.handle_instruct(instruct_id)
  if cache.now_panel_id != constant.Panel.IN_SCENE:
    constant.panel_data[cache.now_panel_id]()
  if cache.now_panel_id != constant.Panel.IN_SCENE:
    raise PlanError(
        f"指令 {instruct_id} 打开的面板退出后没有回到主界面：now_panel_id={cache.now_panel_id}"
    )
  if world.player.planned:
    raise PlanError(
        f"指令 {instruct_id} 之后安排的按钮没有用掉：{world.player.planned}"
    )


def instruct_ready(instruct_id: str) -> bool:
  """
  指令此刻是否会出现在主界面（它的前提全部成立）
  Keyword arguments:
  instruct_id -- 指令id
  Return arguments:
  bool -- 前提全部成立时为真
  """
  from Script.Core import constant
  from Script.Design import handle_premise

  return all(
      handle_premise.handle_premise(premise, 0)
      for premise in constant.instruct_premise_data.get(instruct_id, ())
  )


def walk(world, path: list):
  """
  像玩家在地图上点选目的地一样让博士走过去，每一段路都经主循环结算
  Keyword arguments:
  world -- FullWorld
  path -- 目标场景路径列表
  Return arguments:
  无
  """
  from Script.Design import character_move

  world.scene(path)
  character_move.own_charcter_move(list(path))


def npc_id(world, name: str) -> int:
  """
  按名字找本局已有的干员
  Keyword arguments:
  world -- FullWorld
  name -- 干员名字
  Return arguments:
  int -- 角色id
  """
  found = [
      cid
      for cid in world.cache.npc_id_got
      if world.cache.character_data[cid].name == name
  ]
  if len(found) != 1:
    raise PlanError(f"本局应有一名「{name}」，找到 {found}")
  return found[0]


def summon(world, name: str):
  """
  在「干员位置一览」里把干员召集到博士所在的场景，等她走到，再在场景里点选她
  Keyword arguments:
  world -- FullWorld
  name -- 干员名字
  Return arguments:
  无
  """
  from Script.Core import constant

  cid = npc_id(world, name)
  pl = world.cache.character_data[0]
  instruct(
      world,
      constant.Instruct.ALL_NPC_POSITION,
      ("召集到自己当前位置", name, "返回"),
  )
  for _ in range(24):
    if world.cache.character_data[cid].position == pl.position:
      break
    instruct(world, constant.Instruct.WAIT)
  if world.cache.character_data[cid].position != pl.position:
    raise PlanError(f"{name} 两小时内没有走到博士身边")
  # 在场景里点选她：场景面板的点选只改这一个字段
  pl.target_character_id = cid


def build_time_stop_h(world):
  """
  构建 time_stop_h：召集阿米娅到博士房间，开时停，时停奸
  Keyword arguments:
  world -- 选 FIRST_BONUS 刚开新游戏的 FullWorld
  Return arguments:
  无
  """
  from Script.Core import constant
  from Script.Design import handle_premise

  # 医疗部：华法琳转住院医生，杜宾转坐诊医生
  walk(world, DOCTOR_OFFICE)
  instruct(
      world,
      constant.Instruct.MANAGE_BASEMENT,
      (
          "各部门工作概况",
          "调整干员岗位",
          "展开所有类别",
          "华法琳",
          "[062]住院医生",
          "杜宾",
          "[061]坐诊医生",
          "返回",
          "返回",
      ),
  )
  walk(world, DOCTOR_ROOM)
  summon(world, ASSISTANT_NAME)
  instruct(world, constant.Instruct.TIME_STOP_ON)
  instruct(world, constant.Instruct.TIME_STOP_H)
  if not (world.cache.time_stop_mode and handle_premise.handle_is_h(0)):
    raise PlanError("没有进入时停中的 H")


@contextlib.contextmanager
def days_passed(day: int):
  """
  在 with 块里，孕期天数与孩子的成长天数都按 day 天计
  Keyword arguments:
  day -- 经过的天数
  Return arguments:
  无
  """
  from Script.System.Pregnancy_System import pregnancy_handle

  with mock.patch.object(
      pregnancy_handle, "get_pregnancy_past_day", return_value=day
  ), mock.patch.object(
      pregnancy_handle, "get_child_grow_day", return_value=day
  ):
    yield


def fertilize(world, mother_id: int):
  """
  让母亲受精：射精到子宫，生理周期推进到排卵日，走受精结算
  Keyword arguments:
  world -- FullWorld
  mother_id -- 母亲角色id
  Return arguments:
  无
  """
  from Script.Design import handle_premise
  from Script.System.Pregnancy_System import pregnancy_handle
  from Script.UI.Panel import ejaculation_panel

  mother = world.cache.character_data[mother_id]
  # 部位 7 为子宫，类型 0 为身体
  ejaculation_panel.update_semen_dirty(mother_id, 7, 0, 1000)
  for _ in range(7):
    if mother.pregnancy.ovulation_flag:
      break
    pregnancy_handle.update_reproduction_period(mother_id)
  pregnancy_handle.get_fertilization_rate(mother_id)
  pregnancy_handle.check_fertilization(mother_id)
  if not handle_premise.handle_fertilization_1(mother_id):
    raise PlanError(f"{mother.name} 没有受精")


def give_birth(world, mother_id: int, name: str) -> list:
  """
  受精的母亲转妊娠、临盆、生产，给每个孩子取名，产后转育儿
  Keyword arguments:
  world -- FullWorld
  mother_id -- 母亲角色id
  name -- 孩子名字的前缀，第 n 个孩子叫 name + n
  Return arguments:
  list[int] -- 这一胎的孩子id
  """
  from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

  mother = world.cache.character_data[mother_id]
  with days_passed(pregnancy_constant.PREGNANCY_DAY):
    pregnancy_handle.check_pregnancy(mother_id)
  with days_passed(pregnancy_constant.PARTURIENT_DAY):
    pregnancy_handle.check_near_born(mother_id)
  before = list(mother.relationship.child_id_list)
  world.player.press("焦急等待")
  for index in range(max(1, mother.pregnancy.fetus_count)):
    world.player.type(f"{name}{index + 1}")
  # 临盆后第 5 天的生产概率为 100%
  with days_passed(pregnancy_constant.PARTURIENT_DAY + 5):
    pregnancy_handle.check_born(mother_id)
  world.player.check_done()
  with days_passed(pregnancy_constant.POSTPARTUM_REST_DAY):
    pregnancy_handle.check_rearing(mother_id)
  return [cid for cid in mother.relationship.child_id_list if cid not in before]


def build_family_commission(world):
  """
  构建 family_commission：孕产与孩子的成长，安排教师与课表，升级机库、买载具、派外勤委托
  Keyword arguments:
  world -- 选 FIRST_BONUS 刚开新游戏的 FullWorld
  Return arguments:
  无
  """
  from Script.Core import constant
  from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

  kaltsit, closure, theresa, warfarin = (
      npc_id(world, name)
      for name in ("凯尔希", "可露希尔", "特蕾西娅", "华法琳")
  )
  for mother_id in (kaltsit, closure, theresa, warfarin):
    fertilize(world, mother_id)
  with days_passed(pregnancy_constant.PREGNANCY_DAY):
    pregnancy_handle.check_pregnancy(theresa)
  first_children = {
      mother_id: give_birth(world, mother_id, prefix)
      for mother_id, prefix in (
          (kaltsit, "凯女"),
          (closure, "可女"),
          (warfarin, "华女"),
      )
  }
  for mother_id in first_children:
    with days_passed(pregnancy_constant.REARING_COMPLETE_DAY):
      pregnancy_handle.check_rearing_complete(mother_id)
  with days_passed(pregnancy_constant.GROW_TO_LOLI_DAY):
    for child_id in first_children[kaltsit] + first_children[closure]:
      pregnancy_handle.check_grow_to_loli(child_id)
  with days_passed(pregnancy_constant.GROW_TO_GIRL_DAY):
    for child_id in first_children[kaltsit]:
      pregnancy_handle.check_grow_to_girl(child_id)
  fertilize(world, kaltsit)
  give_birth(world, kaltsit, "凯次女")
  # 学员要有教师、有课表才上课：可露希尔转教师，教育管理里一键排满全部教室
  walk(world, DOCTOR_OFFICE)
  instruct(
      world,
      constant.Instruct.MANAGE_BASEMENT,
      (
          "各部门工作概况",
          "调整干员岗位",
          "展开所有类别",
          "可露希尔",
          "[151]教师",
          "返回",
          "教育管理系统",
          "一键排满全部教室",
          "个人课表",
          "选择学生",
          "可女1",
          "一键选课",
          "选择学生",
          "凯女1",
          "一键选课",
          "返回",
          "返回",
      ),
  )
  walk(world, BUILDING_ROOM)
  instruct(world, constant.Instruct.BUILDING, ("机库", "升级", "返回"))
  walk(world, GARAGE)
  instruct(
      world,
      constant.Instruct.MANAGE_VEHICLE,
      (
          "温顺的武装大驮兽",
          "购买载具",
          "返回",
          "萨卡兹子裔改装补给车",
          "购买载具",
          "返回",
          "返回",
      ),
  )
  walk(world, ASSEMBLY_POINT)
  # 两个载具的「+1」按钮文字相同，按下的是最后画出的那个：先派补给车，大驮兽留给第二项委托
  instruct(
      world,
      constant.Instruct.FIELD_COMMISSION,
      (
          "日常补给（小）",
          "调整派遣人员",
          "杜宾",
          "完成 / 返回",
          "调整使用载具",
          "+1",
          "返回",
          "执行委托",
          "采集周围的药草",
          "调整派遣人员",
          "华法琳",
          "完成 / 返回",
          "调整使用载具",
          "+1",
          "返回",
          "执行委托",
          "返回",
      ),
  )
  if len(world.cache.rhodes_island.ongoing_field_commissions) != 2:
    raise PlanError(
        f"应有两项进行中的委托：{world.cache.rhodes_island.ongoing_field_commissions}"
    )


def waits(count: int) -> list:
  """
  动作表里连续 count 次「等待五分钟」
  Keyword arguments:
  count -- 次数
  Return arguments:
  list[tuple] -- 动作
  """
  return [("instruct", "wait", ())] * count


PLANS = {
    "time_stop_h": [
        ("instruct", "kiss_h", ("确定",)),
        ("instruct", "cunnilingus", ()),
        ("instruct", "breast_caress", ()),
        ("instruct", "vaginal_sex", ("正常位", "确定")),
        ("instruct", "normal_sex", ()),
    ]
    + waits(12)
    + [("walk", DINING_HALL)]
    + waits(24)
    + [("walk", LIBRARY)]
    + waits(36)
    + [("walk", DOCTOR_ROOM)]
    + [("until", "sleep", ("8小时", "确定"), 150)]
    + waits(36),
    "family_commission": waits(6)
    + [("walk", CLASSROOM)]
    + [("until", "teach", (), 36)]
    + waits(12)
    + [("walk", NURSERY)]
    + waits(24)
    + [("walk", DINING_HALL)]
    + waits(36)
    + [("walk", LIBRARY)]
    + waits(60)
    + [("walk", DOCTOR_ROOM)]
    + waits(180),
}
""" 状态名: 玩家动作表。动作是 ("instruct", 指令id, 之后按下的按钮)、("walk", 目标场景路径)，
或 ("until", 指令id, 之后按下的按钮, 最多等待的次数)：指令的前提不成立时「等待五分钟」再看，成立时执行它；每次等待与最后的指令各算一步 """

BUILDERS = {
    "time_stop_h": build_time_stop_h,
    "family_commission": build_family_commission,
}
""" 状态名: 构建函数 """


def run(world, state_name: str):
  """
  构建状态并按动作表推进，每一步录一份快照
  Keyword arguments:
  world -- 选 FIRST_BONUS 刚开新游戏的 FullWorld
  state_name -- 状态名（BUILDERS 的键）
  Return arguments:
  tests.snapshot.Recorder -- 录下的快照；第 0000 步是构建完的状态，第 n 步是第 n 个动作之后的状态
  """
  from tests.snapshot import ActionLog, Recorder, capture
  from tests.world import seed_everything

  from Script.Core import constant, save_handle

  # 睡醒时的自动存档会往检出目录的 save/ 写文件：换成只记下调用
  saves = []
  save_handle.establish_save = lambda *args, **kwargs: saves.append(args)
  BUILDERS[state_name](world)
  seed_everything()
  log = ActionLog()
  log.install()
  recorder = Recorder()
  memo = {}
  recorder.record("0000", capture(world.cache, log, memo))
  step = 0

  def record() -> None:
    """
    录下一步
    Keyword arguments:
    无
    Return arguments:
    无
    """
    nonlocal step
    step += 1
    recorder.record(f"{step:04d}", capture(world.cache, log, memo))

  for action in PLANS[state_name]:
    if action[0] == "walk":
      walk(world, action[1])
    elif action[0] == "until":
      _, instruct_id, presses, max_waits = action
      for _ in range(max_waits):
        if instruct_ready(instruct_id):
          break
        instruct(world, constant.Instruct.WAIT)
        record()
      instruct(world, instruct_id, presses)
    else:
      instruct(world, action[1], action[2])
    record()
  return recorder
