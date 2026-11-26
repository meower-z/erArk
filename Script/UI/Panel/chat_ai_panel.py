"""
文本生成AI界面面板（chat_ai_panel）
===================================
提供文本生成AI的 Tk 输出实现、直接对话界面以及直接对话结果的指令结算入口。
调用方通过模块级的 OUTPUT 实例向 handle_chat_ai 传入绘制与刷新能力。
"""

from collections.abc import Iterable, Iterator
from types import FunctionType
from typing import NoReturn

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, get_text, io_init
from Script.Design import handle_chat_ai, handle_premise
from Script.System.Instruct_System.handle_instruct import (
    chara_handle_instruct_common_settle,
)
from Script.UI.Moudle import draw, panel, view

_: FunctionType = get_text._
""" 翻译函数 """
line_feed = draw.NormalDraw()
""" 宽度为 1 的换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 界面文本宽度，本模块在配置加载后按需首次导入时读取该值 """


class DrawOutput:
    """ChatAiOutput 的 Tk 绘制与刷新实现。"""

    def show(self, text: str, *, full_width: bool = False) -> None:
        """
        使用 NormalDraw 绘制一段文本。
        Keyword arguments:
        text -- str，要显示的文本
        full_width -- bool，为真时将绘制宽度设为 window_width，默认为 False
        Return arguments:
        None -- 无返回值
        """
        now_draw = draw.NormalDraw()
        now_draw.text = text
        if full_width:
            now_draw.width = window_width
        now_draw.draw()

    def line_break(self) -> None:
        """
        使用 LineFeedWaitDraw 绘制 " \n"，等待玩家确认后换行。
        Return arguments:
        None -- 无返回值
        """
        wait_draw = draw.LineFeedWaitDraw()
        wait_draw.text = " \n"
        wait_draw.draw()

    def flush(self) -> None:
        """
        调用 io_init.flush 立即刷新界面输出。
        Return arguments:
        None -- 无返回值
        """
        io_init.flush()

    def flushing[T](self, items: Iterable[T]) -> Iterator[T]:
        """
        调用 io_init.flushing 逐项产出元素并在每项处理后刷新输出。
        Keyword arguments:
        items -- Iterable[T]，待逐项产出的元素序列
        Return arguments:
        Iterator[T] -- 按原顺序逐项产出元素的迭代器
        """
        return io_init.flushing(items)


OUTPUT = DrawOutput()
""" 供调用方复用的 Tk 文本AI输出实例 """


def settle_direct_instruct(
    ai_result: handle_chat_ai.DirectModeResult,
) -> NoReturn:
    """
    根据直接对话结果写入临时指令效果表，并调用通用指令结算选择玩家动作。
    Keyword arguments:
    ai_result -- DirectModeResult，包含耗时、消耗、关系、角色状态与经验的解析结果
    Return arguments:
    NoReturn -- 选中玩家动作后直接跳出，不正常返回
    """
    tem_behavior_id = constant.Behavior.AI_CHAT_INSTRUCT
    new_duration = ai_result["time"]
    game_config.config_behavior_effect_data[tem_behavior_id] = []
    game_config.config_behavior_effect_data[tem_behavior_id].append(
        10 + ai_result["tired"]
    )
    game_config.config_behavior_effect_data[tem_behavior_id].append(
        11 + ai_result["tired"]
    )
    if ai_result["relationship"] == 1:
        game_config.config_behavior_effect_data[tem_behavior_id].append(23)
    elif ai_result["relationship"] == 3:
        game_config.config_behavior_effect_data[tem_behavior_id].append(21)
    elif ai_result["relationship"] == 4:
        game_config.config_behavior_effect_data[tem_behavior_id].append(21)
        game_config.config_behavior_effect_data[tem_behavior_id].append(22)
    if ai_result["character_state"] != -1:
        if isinstance(ai_result["character_state"], list):
            for chara_state_id in ai_result["character_state"]:
                if 9 <= chara_state_id and chara_state_id <= 20:
                    effect_id = chara_state_id + 42
                    game_config.config_behavior_effect_data[
                        tem_behavior_id
                    ].append(effect_id)
        else:
            chara_state_id = ai_result["character_state"]
            if 9 <= chara_state_id and chara_state_id <= 20:
                effect_id = chara_state_id + 42
                game_config.config_behavior_effect_data[tem_behavior_id].append(
                    effect_id
                )
    if ai_result["experience"] != -1:
        if isinstance(ai_result["experience"], list):
            for exp_id in ai_result["experience"]:
                exp_effect_id = f"CVE_A2_E|{exp_id}_G_1"
                game_config.config_behavior_effect_data[tem_behavior_id].append(
                    exp_effect_id
                )
        else:
            exp_id = ai_result["experience"]
            exp_effect_id = f"CVE_A2_E|{exp_id}_G_1"
            game_config.config_behavior_effect_data[tem_behavior_id].append(
                exp_effect_id
            )
    chara_handle_instruct_common_settle(
        tem_behavior_id, duration=new_duration, force_taget_wait=True
    )


def direct_chat_with_ai() -> str:
    """
    绘制与AI进行直接对话界面，接收玩家输入的动作文本并调用文本AI。
    模型调用完成后由 settle_direct_instruct 结算动作且不返回。
    提前返回或功能未开启时等待点击返回按钮并返回回复文本。
    Return arguments:
    str -- 提前返回或未开启时的回复文本，输入为空时返回空字符串
    """
    title_draw = draw.TitleLineDraw("与AI进行直接对话", window_width)
    while True:
        title_draw.draw()
        line_feed.draw()
        return_list = []
        if not handle_premise.handle_ai_chat_on(0):
            info_text = _(
                "\nAI对话功能未开启，请前往【系统设置】中的【文本生成AI设置】中开启。\n"
            )
            info_draw = draw.WaitDraw()
            info_draw.style = "gold_enrod"
            info_draw.text = info_text
            info_draw.draw()
            reply_text = ""
        else:
            ask_text = _("\n请描述你想要进行的动作：\n")
            ask_panel = panel.AskForOneMessage()
            ask_panel.set(ask_text, 999)
            user_input = ask_panel.draw()
            line_feed.draw()
            if not user_input:
                return ""
            character_id = 0
            behavior_id = "ai_chat_instruct"
            reply_text = handle_chat_ai.judge_use_text_ai(
                character_id,
                behavior_id,
                user_input,
                OUTPUT,
                settle=settle_direct_instruct,
            )
            if normal_config.ai_setting.ai_chat_setting[14] != 1:
                reply_text = reply_text.replace("\\n", "\n")
                reply_text = reply_text.replace("text:", "")
                reply_draw = draw.NormalDraw()
                reply_draw.text = _("\nAI回复：\n") + reply_text + _("\n")
                reply_draw.width = window_width
                reply_draw.draw()
        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        line_feed.draw()
        return_list.append(back_draw.return_text)
        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            view.now_panel_id = constant.Panel.IN_SCENE
            break
    return reply_text
