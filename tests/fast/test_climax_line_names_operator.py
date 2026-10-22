# -*- coding: UTF-8 -*-
"""
干员高潮口上里的人名回归测试
==========================
干员高潮的口上以高潮的干员为说话人：口上里 {Name} 是她，{TargetName} 是她此刻的交互对象（H 中可能是她自己，也可能是博士），
{PlayerName} 是博士。所以写高潮的人要用 {Name}，写替她掩护的博士要用 {PlayerName}。
本测试读载入后的口上配置 game_config.config_talk，检查：
- 隐奸高潮口上（A/B/C/V_climax 中下面列出的行）与夕、澄闪、白金、歌蕾蒂娅的这几条高潮口上写了 {Name}、没写 {TargetName}；
- B_climax 里写到替她掩护的人的 11 行写了 {PlayerName}；
- 全部口上里，干员的高潮描写（行为 id 为「一个小写字母_orgasm_」开头，p_ 开头的是博士射精）都不用 {TargetName}。
"""

import re

from Script.Config import game_config
from tests.fast.base import FastTestCase

SYSTEM_ROWS = {
    "second_climax_A_climax": range(1180, 1220),
    "second_climax_B_climax": range(1220, 1240),
    "second_climax_V_climax": range(1220, 1240),
    "second_climax_C_climax": range(1200, 1220),
}
""" 隐奸高潮口上：id 前缀与行号 """
CHARA_ROWS = ["chara_2015_夕18", "chara_2015_夕19"]
CHARA_ROWS += [f"chara_0377_澄闪{row}" for row in (92, 93, 94, 105)]
CHARA_ROWS += [f"chara_0204_白金{row}" for row in (971, 1118, 1139)]
CHARA_ROWS += [f"chara_0474_歌蕾蒂娅{row}" for row in (2290, 2291, 2292)]
""" 角色高潮口上的 id """
HELPER_ROWS = [
    f"second_climax_B_climax{row}" for row in (1227, 1228, *range(1231, 1240))
]
""" B_climax 里写到替她掩护的人的行 """


class ClimaxLineNamesOperatorTest(FastTestCase):
  """高潮口上用 {Name} 写高潮的干员，用 {PlayerName} 写掩护她的博士"""

  def test_listed_lines_name_operator(self):
    """列出的隐奸与角色高潮口上都写 {Name}，不写 {TargetName}"""
    talk_ids = [
        f"{prefix}{row}" for prefix, rows in SYSTEM_ROWS.items() for row in rows
    ] + CHARA_ROWS
    missing = [
        talk_id
        for talk_id in talk_ids
        if talk_id not in game_config.config_talk
    ]
    self.assertEqual(missing, [])
    wrong = [
        talk_id
        for talk_id in talk_ids
        if "{Name}" not in game_config.config_talk[talk_id].context
        or "{TargetName}" in game_config.config_talk[talk_id].context
    ]
    self.assertEqual(wrong, [])

  def test_helper_is_doctor(self):
    """B_climax 里替她掩护的人写作 {PlayerName}"""
    wrong = [
        talk_id
        for talk_id in HELPER_ROWS
        if "{PlayerName}" not in game_config.config_talk[talk_id].context
    ]
    self.assertEqual(wrong, [])

  def test_no_operator_climax_line_uses_target_name(self):
    """全部口上里，干员的高潮描写都不用 {TargetName}"""
    left = sorted(
        talk_id
        for talk_id, talk in game_config.config_talk.items()
        if re.match(r"^[a-z]_orgasm_", talk.behavior_id)
        and not talk.behavior_id.startswith("p_")
        and "{TargetName}" in talk.context
    )
    self.assertEqual(left, [])
