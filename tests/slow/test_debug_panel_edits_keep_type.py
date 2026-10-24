# -*- coding: UTF-8 -*-
"""
debug数值调整面板的修改保持字段的类型，读这些字段的游戏代码照常工作
==================================================================
开新游戏后打开设置里的 debug，执行「开启DEBUG模式」与「debug数值调整」两个指令，用面板的按钮与输入框修改：
全局变量 [007] 派对计划输入「星期,娱乐id」，只改这一天，当天刷新娱乐时干员的三项娱乐都是派对的娱乐；
全局变量 [008] 招募进度输入「招募线id,进度」，只改这条线的进度，进度满 100 时招募刷新把它清零；
全局变量 [009] 已招募待确认的干员输入干员id，待确认的只有这一名，确认招募后这名干员入职；
NPC角色 [013] 本次H 输入「6,部位,第几项」与新值，只改这个部位的这一项计数，前提「交互对象本次H中S绝顶次数>3」照新值判断。
"""

from tests.slow.base import SlowTestCase

PARTY_ENTERTAINMENT = 101
""" 派对用的娱乐：读书（图书馆的读书会也排这个娱乐） """
RECRUIT_LINE = 0
""" 新游戏就有的招募线 """
S_PART = 0
""" 部位 0 皮肤：前提「交互对象本次H中S绝顶次数>3」读它的总次计数 """


class DebugPanelEditKeepTypeTest(SlowTestCase):
  """debug数值调整面板的这四项修改后，字段保持声明的类型，读它的游戏代码照常工作"""

  def setUp(self) -> None:
    """
    开新游戏，打开设置里的 debug，执行「开启DEBUG模式」与「debug数值调整」两个指令
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    from Script.Config import normal_config
    from Script.Core import constant

    normal_config.config_normal.debug = True
    self.instruct(constant.Instruct.DEBUG_MODE_ON)
    self.instruct(constant.Instruct.DEBUG_ADJUST)
    self.ri = self.cache.rhodes_island

  def use_panel(self, *steps: tuple) -> None:
    """
    显示debug面板，依次按下按钮、输入文字，最后按面板的「[返回]」离开
    Keyword arguments:
    steps -- ("press", 按钮文字的一部分) 或 ("type", 输入的文字)
    Return arguments:
    无
    """
    for kind, value in steps:
      getattr(self.world.player, kind)(value)
    self.world.player.press("[返回]")
    self.show_panel()
    self.world.player.check_done()

  def other_npc(self) -> int:
    """
    本局任意一名干员（不是玩家）
    Keyword arguments:
    无
    Return arguments:
    int -- 角色id
    """
    return min(cid for cid in self.cache.npc_id_got if cid)

  def test_party_day(self) -> None:
    """[007] 改一天的派对娱乐，当天刷新娱乐时干员的娱乐都是它"""
    from Script.Design import handle_npc_ai

    week_day = self.cache.game_time.weekday()
    before = dict(self.ri.party_day_of_week)
    self.use_panel(
        ("press", "[全局变量]"),
        ("press", "[007]"),
        ("type", f"{week_day},{PARTY_ENTERTAINMENT}"),
    )
    self.assertEqual(
        self.ri.party_day_of_week,
        {**before, week_day: PARTY_ENTERTAINMENT},
        "派对计划只改输入的这一天",
    )
    npc_id = self.other_npc()
    handle_npc_ai.get_chara_entertainment(npc_id)
    self.assertEqual(
        self.cache.character_data[npc_id].entertainment.entertainment_type,
        [PARTY_ENTERTAINMENT] * 3,
        "当天有派对时干员的三项娱乐都是派对的娱乐",
    )

  def test_recruit_progress(self) -> None:
    """[008] 改一条招募线的进度，进度满 100 时招募刷新把它清零"""
    from Script.UI.Panel import recruit_panel

    line = list(self.ri.recruit_line[RECRUIT_LINE])
    self.use_panel(
        ("press", "[全局变量]"),
        ("press", "[008]"),
        ("type", f"{RECRUIT_LINE},100"),
    )
    self.assertEqual(
        self.ri.recruit_line[RECRUIT_LINE],
        [100] + line[1:],
        "招募线只改进度一项",
    )
    recruit_panel.update_recruit()
    self.assertEqual(
        self.ri.recruit_line[RECRUIT_LINE][0], 0, "进度满 100 后招募刷新清零"
    )

  def test_recruited_id(self) -> None:
    """[009] 输入一名干员为已招募待确认，确认招募后这名干员入职"""
    from Script.UI.Panel import recruit_panel

    chara_id = min(
        cid
        for cid in self.cache.character_data
        if cid and cid not in self.cache.npc_id_got
    )
    self.use_panel(
        ("press", "[全局变量]"),
        ("press", "[009]"),
        ("type", str(chara_id)),
    )
    self.assertEqual(self.ri.recruited_id, {chara_id}, "待确认的只有这一名")
    self.assertTrue(recruit_panel.recruit_new_chara(), "确认招募成功")
    self.assertIn(chara_id, self.cache.npc_id_got, "确认后这名干员入职")
    self.assertEqual(self.ri.recruited_id, set(), "确认后没有待确认的干员")

  def test_orgasm_count(self) -> None:
    """[013] 本次H 改一个部位的一项高潮计数，前提照新值判断"""
    from Script.Design.handle_premise import handle_premise_H

    npc_id = self.other_npc()
    npc = self.cache.character_data[npc_id]
    count = list(npc.h_state.orgasm_count[S_PART])
    self.use_panel(
        ("press", "[NPC角色]"),
        ("press", f"[{str(npc.adv).rjust(4, '0')}]：{npc.name}"),
        ("press", "[013]"),
        ("type", f"6,{S_PART},1"),
        ("type", "5"),
        ("press", "[返回]"),
        ("press", "[返回]"),
    )
    self.assertEqual(
        npc.h_state.orgasm_count[S_PART],
        [count[0], 5],
        "只改这个部位的总次计数",
    )
    self.cache.character_data[0].target_character_id = npc_id
    self.assertEqual(
        handle_premise_H.handle_t_turn_s_orgasm_g_3(0),
        1,
        "S绝顶总次数 5 > 3，前提成立",
    )
