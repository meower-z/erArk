"""公务事件的弹出与决断界面（Plan 23 方案 §3.7）

玩家在博士办公室每次「处理公务」，弹出待处理队列里第一条有可选选项的公务事件，给2~4个选项；
选定的选项在处理公务的行动开始时结算，下一条留到下一次处理公务。

四条界面口径：
   1. 后果提示**写方向不写数值**（"倾向：坚强"而不是"坚强+2"）——写了数值，决断就变成算数题了
   2. 前提不满足的选项**置灰并标明原因**而不是隐藏——让玩家看见"这里本来有更好的选择，但我没养到"
   3. 后果提示**不写在选项上**：选项行只写选项本身。
      玩家选定并结算后，一条等待文本显示所选选项与结果。该文本由 official_prompt.result_text 构造
   4. 选项的**出现顺序每次随机**（用户要求）：CSV 里的选项顺序是固定写死的（养成事件大多是
      「严厉 / 温和 / 放任」这类同一组倾向），照原序画的话玩家几条之后就按位置选而不再读选项，
      养成倾向于是变成按键顺序的产物。序号只是画面上的编号，结算与履历一律认 CSV 里的原序号
"""

from types import FunctionType

from Script.Core import flow_handle, get_text, py_cmd, text_handle
from Script.Config import game_config
from Script.Modules.gameplay_resolution import official_prompt
from Script.System.Official_Event_System import official_event_handle
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def get_event_title(queue_data: dict) -> str:
    """
    取事件抬头

    有主体的部门可以注册自己的抬头（如养成的"薇薇安 · 学员期第 38 天"），
    没注册的一律画部门名——玩家至少要知道这件事是哪个部门的。
    Keyword arguments:
    queue_data -- 队列元素dict
    Return arguments:
    str -- 抬头文本
    """
    department = queue_data.get(
        "department",
        official_event_handle.get_event_department(queue_data["uid"]),
    )
    if department in official_event_handle.EVENT_TITLE:
        try:
            return official_event_handle.EVENT_TITLE[department](queue_data)
        except Exception as now_error:
            print(
                f"\ndebug 公务事件的部门{department}抬头提供者报错：{now_error}\n"
            )
    return official_event_handle.get_department_name(department)


class Official_Event_Draw:
    """
    单条公务事件的绘制与决断
    Keyword arguments:
    queue_data -- 队列元素dict，含 uid / department / chara_id / partner_id
    width -- 绘制宽度
    """

    def __init__(self, queue_data: dict, width: int) -> None:
        """初始化绘制对象"""
        self.queue_data: dict = queue_data
        """ 队列元素 """
        self.uid: str = queue_data["uid"]
        """ 事件uid """
        self.character_id: int = queue_data.get("chara_id", 0)
        """ 主体角色id，0为无主体（部门事务） """
        self.partner_id: int = queue_data.get("partner_id", 0)
        """ 互动对象角色id，0为博士 """
        self.width: int = width
        """ 绘制宽度 """
        self.option_list: list[dict] = official_event_handle.get_option_list(
            self.uid, self.character_id, self.partner_id
        )
        """ 本条事件的选项列表，按 CSV 原序排列，结算与履历均使用此顺序 """
        self.draw_option_list: list[dict] = list(self.option_list)
        """ 本条事件的选项显示顺序，每次弹出时重新洗牌（界面口径 4）。
            置灰的选项一起参与洗牌——只洗可选项的话，置灰项固定在原位，位置仍然泄露了原序 """
        player_pick.ui_random.shuffle(self.draw_option_list)

    def draw(self) -> int:
        """
        绘制一条事件并等待玩家决断
        Keyword arguments:
        无
        Return arguments:
        int -- 玩家选定的选项序号（1~4），没有任何可选选项时为0
        """
        event_data = game_config.config_official_event[self.uid]
        line_feed.draw()
        # count_title_width：抬头（「【公务事件】薇薇安 · 婴儿期第 8 天」）本身就有三十多个半角宽，
        #    按 LittleTitleLineDraw 的默认口径（标题不计宽）整行会画成 width + 抬头宽，行尾的线条被挤到第二行去
        draw.LittleTitleLineDraw(
            _("【公务事件】{0}").format(get_event_title(self.queue_data)),
            self.width,
            count_title_width=True,
        ).draw()
        # 事件正文
        text_draw = draw.NormalDraw()
        text_draw.width = self.width
        text_draw.text = "\n  {}\n\n".format(
            official_prompt.get_code_text(
                event_data.get("text", ""), self.character_id, self.partner_id
            )
        )
        text_draw.draw()
        # 没有任何可选选项时不该把玩家卡在这条事件上，直接跳过
        if not [one for one in self.option_list if one["can_use"]]:
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            info_draw.text = _("  （这件事已经不需要你来决定了）\n")
            info_draw.style = "deep_gray"
            info_draw.draw()
            draw.LineDraw("-", self.width).draw()
            return 0
        return_list = []
        button_index = 0
        for option in self.draw_option_list:
            option_text = official_prompt.get_code_text(
                option["text"], self.character_id, self.partner_id
            )
            # 前提不满足：置灰保留，并把原因写在后面
            if not option["can_use"]:
                reason_text = official_prompt.get_code_text(
                    option["reason"], self.character_id, self.partner_id
                )
                gray_draw = draw.NormalDraw()
                gray_draw.width = self.width
                gray_draw.style = "deep_gray"
                gray_draw.text = _("   ○ {0}").format(option_text)
                if reason_text:
                    gray_draw.text += _("（{0}）").format(reason_text)
                gray_draw.text += "\n"
                gray_draw.draw()
                continue
            button_index += 1
            button_text = f"{text_handle.id_index(button_index)}{option_text}"
            return_text = f"\nOEVENT_{option['index']}"
            now_draw = draw.LeftButton(button_text, return_text, self.width)
            now_draw.draw()
            line_feed.draw()
            return_list.append(return_text)
        draw.LineDraw("-", self.width).draw()
        yrn = flow_handle.askfor_all(return_list)
        py_cmd.clr_cmd()
        for option in self.option_list:
            if yrn == f"\nOEVENT_{option['index']}":
                return option["index"]
        return 0
