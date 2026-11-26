"""
选择学生界面组件（student_select）
为「个人课表」与「养成总览」页签绘制选人行，并通过通用 NPC 选择面板执行选人循环。
当前学生校验、展示文本、候选列表构造与结果判定由 student_select_service 提供。
当测试输入桩未触发角色名按钮回调时，选人结果按返回姓名反查首个同名角色编号。
"""

from Script.Config import normal_config
from Script.Core import flow_handle
from Script.Modules.gameplay_resolution import student_select_service
from Script.System.Education_System import education_constant
from Script.UI.Moudle import draw, panel

line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def draw_select_student_line(
    width: int, now_student: int, return_list: list[str]
) -> bool:
    """
    绘制选人行与分隔线，并将「选择学生」按钮返回值追加到返回值列表。
    已选学生时在左半显示当前学生，并在右半居中绘制按钮。
    未选学生时在行首左对齐绘制按钮，并在分隔线下以深灰样式绘制提示。
    Keyword arguments:
    width -- int，选人行与分隔线的绘制总宽度
    now_student -- int，当前选中的角色编号，未选择时为 -1
    return_list -- list[str]，调用方传入的返回值列表，用于追加「选择学生」按钮返回值
    Return arguments:
    bool -- 当前学生有效时返回 True，未选或角色不存在时返回 False
    """
    half_width = int(width / 2)
    selected_flag = student_select_service.has_student(now_student)
    if selected_flag:
        now_draw = draw.LeftDraw()
        now_draw.width = half_width
        now_draw.text = student_select_service.current_student_text(now_student)
        now_draw.draw()
        button_draw = draw.CenterButton(
            student_select_service.select_button_text(),
            education_constant.SELECT_STUDENT_RETURN,
            half_width,
        )
    else:
        button_draw = draw.LeftButton(
            student_select_service.select_button_text(),
            education_constant.SELECT_STUDENT_RETURN,
            half_width,
        )
    button_draw.draw()
    return_list.append(button_draw.return_text)
    line_feed.draw()
    draw.LineDraw("-", width).draw()
    if not selected_flag:
        info_draw = draw.NormalDraw()
        info_draw.width = width
        info_draw.text = student_select_service.select_hint_text()
        info_draw.style = "deep_gray"
        info_draw.draw()
        return False
    return True


def select_student(
    candidate_list: list[int], title_text: str, info_text: str, now_student: int
) -> int:
    """
    打开通用 NPC 选择面板展示候选学生，并返回最终选中的角色编号。
    每轮循环按候选名单重建列表行，翻页与筛选等附加返回值会继续循环。
    Keyword arguments:
    candidate_list -- list[int]，调用方传入的候选学生角色编号列表
    title_text -- str，选人面板的标题文本
    info_text -- str，选人面板标题下的说明文本
    now_student -- int，当前选中的角色编号，用于列表高亮及未选人时的返回值
    Return arguments:
    int -- 选中的角色编号，取消或未选中角色时返回 now_student
    """
    from Script.UI.Panel import common_select_NPC

    pick = student_select_service.StudentPick(now_student)
    now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
        [],
        common_select_NPC.CommonSelectNPCButtonList,
        80,
        8,
        window_width,
        True,
        False,
        0,
    )
    select_state: dict = {}
    name_to_id: dict[str, int] = {}
    yrn = ""
    while 1:
        now_draw_panel.text_list, name_to_id = (
            student_select_service.candidate_rows(
                candidate_list, pick.pick, now_student
            )
        )
        return_list, other_return_list, select_state = (
            common_select_NPC.common_select_npc_button_list_func(
                now_draw_panel, title_text, info_text, select_state
            )
        )
        yrn = flow_handle.askfor_all(return_list)
        if yrn in return_list and yrn not in other_return_list:
            break
    return pick.result(yrn, name_to_id)
