# -*- coding: UTF-8 -*-
"""日记面板真实Web绘制契约回归。"""

import copy
import os
from pathlib import Path

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once


def test_large_diary_uses_bounded_real_web_elements_and_navigation():
    """参数：无；返回：None；用途：验证真实绘制栈不会把大历史一次性交给Web且保留翻页按钮。"""
    ctx = boot_game_once(enable_debug=True)
    from Script.UI.Panel import diary_panel

    history = []
    for day in range(1, 121):
        history.append(f"\n\n时间:2026年春月{day}日\n\n")
        history.extend(f"第{day:03d}日-行动{entry:03d}\n" for entry in range(90))

    original_history = ctx.cache.daily_intsruce
    original_web_mode = ctx.cache.web_mode
    original_elements = copy.deepcopy(getattr(ctx.cache, "current_draw_elements", []))
    original_askfor_all = diary_panel.flow_handle.askfor_all
    try:
        ctx.cache.daily_intsruce = history
        ctx.cache.web_mode = True
        ctx.cache.current_draw_elements = []
        diary_panel.flow_handle.askfor_all = lambda return_list: "返回"

        diary_panel.Diary_Panel(80).draw()

        elements = ctx.cache.current_draw_elements
        text_payload = "".join(element.get("text", "") for element in elements if element.get("type") == "text")
        button_texts = [element.get("text", "") for element in elements if element.get("type") == "button"]
        assert "第120日-行动089" in text_payload
        assert "第001日-行动000" not in text_payload
        assert len(text_payload) <= diary_panel.DIARY_PAGE_MAX_CHARS + 400
        assert any("上一页" in text for text in button_texts)
        assert any("返回" in text for text in button_texts)
    finally:
        diary_panel.flow_handle.askfor_all = original_askfor_all
        ctx.cache.daily_intsruce = original_history
        ctx.cache.web_mode = original_web_mode
        ctx.cache.current_draw_elements = original_elements


@pytest.mark.skipif(not os.path.exists(os.path.join("save", "99", "1")), reason="需要用户实机存档 save/99")
def test_real_old_save_diary_browses_exports_and_reopens_without_loss(tmp_path, monkeypatch):
    """参数：tmp_path与monkeypatch为pytest夹具；返回：None；用途：验证真实旧存档日记的浏览、原子导出与重入。"""
    ctx = boot_game_once(enable_debug=True)
    from Script.Core import save_handle
    from Script.UI.Panel import diary_panel

    save_handle.input_load_save("99")
    original_history = ctx.cache.daily_intsruce
    assert len(original_history) > 100000, "存档99应提供足够大的旧日记缓存"
    full_history_text = "".join(original_history)
    original_askfor_wait = diary_panel.flow_handle.askfor_wait
    try:
        panel = diary_panel.Diary_Panel(80)
        view = panel._get_history_view()
        newest_page = view.current_page_text()
        assert newest_page
        assert len(newest_page) <= diary_panel.DIARY_PAGE_MAX_CHARS
        assert view.has_older_page()
        view.go_older()
        assert view.current_page_text()
        assert view.current_page_text() != newest_page

        diary_panel.flow_handle.askfor_wait = lambda: None
        monkeypatch.chdir(tmp_path)
        panel.all_insert_text = "真实旧存档导出验证"
        panel.save_diary()

        diary_files = list((Path("save") / "diary").glob("*.txt"))
        assert len(diary_files) == 1
        exported_text = diary_files[0].read_text(encoding="utf-8")
        assert exported_text == f"{panel.time_text}\n\n{full_history_text}\n\n真实旧存档导出验证"
        assert ctx.cache.daily_intsruce == []
        assert diary_panel.Diary_Panel(80)._get_history_view().current_page_text() == ""
    finally:
        diary_panel.flow_handle.askfor_wait = original_askfor_wait
        ctx.cache.daily_intsruce = original_history
