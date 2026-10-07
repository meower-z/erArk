# -*- coding: UTF-8 -*-
"""
淫纹界面：效果选择面板（函数内循环，同 instruct_filter_panel 写法）+ 结果提示 + 信息页绘制对象

只用本体抽象绘制类和 flow_handle.askfor_all，运行时按模块属性取类，web 模式下 web_draw_adapter 打过的补丁自然生效。
web 模式下面板进入受管子面板（tab_menu.enter_managed_sub_panel_mode），Tk 模式下该调用什么都不做。
"""
from typing import FrozenSet, List, Optional

from Script.Config import normal_config
from Script.Core import cache_control, flow_handle, get_text, py_cmd
from Script.UI.Moudle import draw

from . import effects, store

_ = get_text._
""" 翻译api """

SUB_PANEL_ID = "mod_lewd_tattoo_panel"
""" web 子面板id """
CONFIRM = "确认"
""" 确认按钮的响应文本 """
BACK = "返回"
""" 返回按钮的响应文本 """


def _line_feed() -> None:
    """
    绘制一个换行
    Keyword arguments:
    无
    Return arguments:
    None
    """
    line = draw.NormalDraw()
    line.text = "\n"
    line.width = 1
    line.draw()


def _text(text: str, width: int, style: str = "standard") -> None:
    """
    绘制一段普通文本
    Keyword arguments:
    text -- 文本
    width -- 宽度
    style -- 样式
    Return arguments:
    None
    """
    now_draw = draw.NormalDraw()
    now_draw.text = text
    now_draw.width = width
    now_draw.style = style
    now_draw.draw()


def _wait_text(text: str, width: int) -> None:
    """
    绘制一段文本并等待玩家确认
    Keyword arguments:
    text -- 文本
    width -- 宽度
    Return arguments:
    None
    """
    now_draw = draw.WaitDraw()
    now_draw.text = text
    now_draw.width = width
    now_draw.draw()


def ask_for_effects(character_id: int, current: Optional[FrozenSet[str]]) -> Optional[FrozenSet[str]]:
    """
    效果选择面板：逐项开关，实时显示 已用槽位/上限；放不下的项不可点；只有选择改变且不超上限时才能确认
    Keyword arguments:
    character_id -- 交互对象id
    current -- 当前效果键（None 表示还没有淫纹，即刻印）
    Return arguments:
    Optional[FrozenSet[str]] -- 确认后的新效果键；返回则为 None
    """
    from Script.System.Web_Draw_System.tab_menu import cleanup_managed_sub_panel_mode, enter_managed_sub_panel_mode

    from . import hooks

    width = normal_config.config_normal.text_width
    name = cache_control.cache.character_data[character_id].name
    title = _("刻印淫纹") if current is None else _("调整淫纹")
    base = current or frozenset()
    selected = set(base)
    # 面板只看身体结构：性别缺少的部位、没有兽耳兽角兽尾时的兽部不可新选（已选的仍可取消）
    body_parts = hooks.present_feel_parts(character_id, include_transient=False)
    context = enter_managed_sub_panel_mode(SUB_PANEL_ID, title)
    try:
        while 1:
            py_cmd.clr_cmd()
            return_list: List[str] = []
            draw.TitleLineDraw(title, width).draw()
            used = effects.slots_of(selected)
            _text(_("对象：{0}    位置：小腹    槽位：{1}/{2}\n").format(name, used, effects.SLOT_CAP), width)
            _text(_("每次刻印或调整消耗理智{0}，不消耗时间\n").format(100), width, "deep_gray")
            _line_feed()
            # 效果列表
            index_by_return = {}
            for index, effect in enumerate(effects.EFFECTS, start=1):
                on = effect.key in selected
                mark = "■" if on else "□"
                text = f"[{index:02d}]{mark}{_(effect.name)}({effect.slots}格)：{_(effect.info)}"
                lacks_part = effect.part is not None and effect.part not in body_parts
                fits = on or used + effect.slots <= effects.SLOT_CAP
                if on or (fits and not lacks_part):
                    button = draw.LeftButton(text, str(index), width)
                    button.draw()
                    return_list.append(button.return_text)
                    index_by_return[button.return_text] = effect.key
                else:
                    reason = _("(该角色没有此部位)") if lacks_part else _("(槽位不足)")
                    _text(text + reason, width, "deep_gray")
                _line_feed()
            _line_feed()
            # 确认与返回
            if effects.can_confirm(base, frozenset(selected)):
                confirm = draw.CenterButton(_("[确认]"), _(CONFIRM), width)
                confirm.draw()
                return_list.append(confirm.return_text)
            else:
                reason = _("(选择未改变)") if frozenset(selected) == base else _("(超出槽位上限)")
                _text(_("[确认]") + reason, width, "deep_gray")
            _line_feed()
            back = draw.CenterButton(_("[返回]"), _(BACK), width)
            back.draw()
            return_list.append(back.return_text)
            _line_feed()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                return None
            if yrn == _(CONFIRM):
                return frozenset(selected)
            if yrn in index_by_return:
                selected ^= {index_by_return[yrn]}
    finally:
        cleanup_managed_sub_panel_mode(context)


def draw_result(character_id: int, is_new: bool, keys: FrozenSet[str]) -> None:
    """
    绘制刻印/调整完成的提示与理智消耗
    Keyword arguments:
    character_id -- 交互对象id
    is_new -- True 为刻印，False 为调整
    keys -- 新的效果键
    Return arguments:
    None
    """
    width = normal_config.config_normal.text_width
    name = cache_control.cache.character_data[character_id].name
    if is_new:
        text = _("在{0}的小腹刻下了淫纹").format(name)
    else:
        text = _("调整了{0}的淫纹").format(name)
    text += _("（{0}），理智-{1}\n").format(_effect_names(keys), 100)
    _wait_text("\n" + text, width)


def draw_refused(character_id: int, problem: str) -> None:
    """
    绘制"数据不认识，不能调整"的提示
    Keyword arguments:
    character_id -- 交互对象id
    problem -- 不激活的原因
    Return arguments:
    None
    """
    width = normal_config.config_normal.text_width
    name = cache_control.cache.character_data[character_id].name
    _wait_text(_("\n{0}的淫纹数据无法识别（{1}），可能来自更新版本的淫纹mod，现已停用且不能调整，数据原样保留\n").format(name, problem), width)


def _effect_names(keys: FrozenSet[str]) -> str:
    """
    按面板顺序列出效果显示名
    Keyword arguments:
    keys -- 效果键
    Return arguments:
    str -- 显示名，以顿号连接；没有效果时为"无效果"
    """
    names = [_(effect.name) for effect in effects.EFFECTS if effect.key in keys]
    return "、".join(names) if names else _("无效果")


class TattooInfoDraw:
    """
    肉体情况页末尾的淫纹信息块：小标题 + 槽位 + 效果列表；数据不认识时显示告警。draw() 时才读存档
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    """

    def __init__(self, character_id: int, width: int):
        """
        初始化
        Keyword arguments:
        character_id -- 角色id
        width -- 绘制宽度
        Return arguments:
        None
        """
        self.character_id = character_id
        """ 角色id """
        self.width = width
        """ 绘制宽度 """
        self.return_list: List[str] = []
        """ 本对象没有按钮（SeeCharacterThirdPanel 会读取这个列表） """

    def draw(self) -> None:
        """
        绘制淫纹信息块
        Keyword arguments:
        无
        Return arguments:
        None
        """
        result = store.view(self.character_id)
        if not result.present:
            return
        _line_feed()
        draw.LittleTitleLineDraw(_("淫纹"), self.width, ":").draw()
        if not result.active:
            _text(_("位置：小腹\n淫纹数据无法识别（{0}），已停用；数据原样保留\n").format(result.problem), self.width, "deep_gray")
            return
        used = effects.slots_of(result.keys)
        _text(_("位置：小腹    槽位：{0}/{1}\n效果：{2}\n").format(used, effects.SLOT_CAP, _effect_names(result.keys)), self.width)
