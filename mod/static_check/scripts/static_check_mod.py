# -*- coding: UTF-8 -*-
"""游戏状态自检 mod 的设置注入、回合检查挂点与载入修复 wrapper。"""

import os
import sys


_static_check = None
_original_tk_draw = None
_original_web_bind = None

# 检查包与脚本同属一个 mod；把 mod 根目录置于搜索路径首位后即可按位置无关包导入。
try:
    _mod_path = os.path.abspath(__file__)
    if _mod_path in sys.path:
        sys.path.remove(_mod_path)
    sys.path.insert(0, _mod_path)
    import static_check as _static_check
except Exception as error:
    print(f"[Mod][static_check] 检查包导入失败，已停用自检功能：{error}")

# 设置项由 mod 在游戏配置完成后注入，禁用 mod 时游戏本体不保留该声明。
try:
    from Script.Config import config_def

    if 13 not in game_config.config_system_setting:
        setting = config_def.System_Setting()
        setting.cid = 13
        setting.type = "base"
        setting.name = "是否开启游戏状态自检"
        setting.info = "开启后，每回合自动检查游戏状态是否自洽，发现异常时记录到static_check_error.log并提示（不影响游戏进行）；载入存档时会自动修复已知的存档数据异常，默认开启"
        setting.option = "否|是"
        setting.default_value = 1
        game_config.config_system_setting[13] = setting
        game_config.config_system_setting_option[13] = ["否", "是"]
        print("[Mod][static_check] 已注入系统设置 cid=13")
    elif game_config.config_system_setting[13].name != "是否开启游戏状态自检":
        print(f"[Mod][static_check] 警告：系统设置 cid=13 已被“{game_config.config_system_setting[13].name}”占用，将保留原设置并继续读取该开关")
except Exception as error:
    print(f"[Mod][static_check] 设置项注入失败，已保留游戏原配置：{error}")


def _is_static_check_enabled():
    """
    输入：无。
    返回值类型：bool，游戏状态自检是否开启。
    功能：为旧存档补上 cid 13 的默认开启值，并读取当前开关。
    """
    base_setting = cache.all_system_setting.base_setting
    base_setting.setdefault(13, 1)
    return bool(base_setting.get(13, 1))


def _run_turn_check_and_warn():
    """
    输入：无。
    返回值类型：None。
    功能：按系统设置开关执行本回合检查，并在发现新异常时绘制警告。
    """
    if _static_check is None:
        return
    try:
        if not _is_static_check_enabled():
            return
        if _static_check.run_turn_check():
            from Script.Core import io_init

            io_init.era_print(f"警告：检测到游戏逻辑状态不自洽，请把 {_static_check.LOG_PATH} 文件提交给开发者。\n", "warning")
    except Exception as error:
        print(f"[Mod][static_check] 回合检查失败，已跳过本轮检查：{error}")


# Tk 模式在指令面板绘制结束后检查，位置恰在主场景等待下一次输入之前。
try:
    if normal_config.config_normal.web_draw == 0:
        from Script.System.Instruct_System import see_instruct_panel

        if not getattr(see_instruct_panel.SeeInstructPanel.draw, "_static_check_mod_wrapped", False):
            _original_tk_draw = see_instruct_panel.SeeInstructPanel.draw

            def _static_check_tk_draw(self):
                """
                输入：self(SeeInstructPanel)，当前指令面板实例。
                返回值类型：与原 draw 方法一致。
                功能：先绘制原指令面板，再执行一次回合状态检查。
                """
                result = _original_tk_draw(self)
                _run_turn_check_and_warn()
                return result

            _static_check_tk_draw._static_check_mod_wrapped = True
            see_instruct_panel.SeeInstructPanel.draw = _static_check_tk_draw
except Exception as error:
    print(f"[Mod][static_check] Tk 回合检查挂点安装失败，已跳过：{error}")

# Web 模式在绑定面板选项并取得等待列表后检查，随后把原列表交还主流程。
try:
    if normal_config.config_normal.web_draw == 1:
        from Script.UI.Panel import in_scene_panel_web

        target_method = in_scene_panel_web.InScenePanelWeb._bind_panel_tabs_and_get_ask_list
        if not getattr(target_method, "_static_check_mod_wrapped", False):
            _original_web_bind = target_method

            def _static_check_web_bind(self):
                """
                输入：self(InScenePanelWeb)，当前 Web 主场景面板实例。
                返回值类型：list[str]，原方法生成的等待指令列表。
                功能：先取得原等待列表，再执行一次回合状态检查并原样返回列表。
                """
                ask_list = _original_web_bind(self)
                _run_turn_check_and_warn()
                return ask_list

            _static_check_web_bind._static_check_mod_wrapped = True
            in_scene_panel_web.InScenePanelWeb._bind_panel_tabs_and_get_ask_list = _static_check_web_bind
except Exception as error:
    print(f"[Mod][static_check] Web 回合检查挂点安装失败，已跳过：{error}")


def patched_input_load_save(save_id: str):
    """
    输入：save_id(str)，待载入的存档编号。
    返回值类型：与原 input_load_save 函数一致。
    功能：先完成原存档载入，再按开关执行保守修复；修复异常绝不阻断载入。
    """
    result = call_original("Script.Core.save_handle", "input_load_save", save_id)
    try:
        if _static_check is not None and _is_static_check_enabled():
            _static_check.run_load_repair()
    except Exception as error:
        print(f"[Mod][static_check] 载入后保守修复失败，已保留原载入结果：{error}")
    return result
