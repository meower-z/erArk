"""
收藏品结算服务（collection_service）
====================================
提供将临时服装藏品收进永久收藏以及刷新信物装备上限的逻辑。
本模块不直接导入界面模块，供指令处理入口与收藏品面板调用。
摆放提示经 ui_hooks.emit_notice 发出。
服装收藏成就经 achievement_service.settle_and_notify 结算。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import identity, player_collection
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def collapse_collection() -> None:
    """
    收起临时服装收藏品并写入永久收藏。
    函数依次处理 npc_panties_tem 与 npc_socks_tem，跳过角色 0 与不在服装模板表中的编号，
    将有效服装名称追加到对应的永久收藏字典并清空该临时字典。
    函数通过 ui_hooks.emit_notice 按文本宽度发出等待确认的开始与结束提示、每条新增藏品的空提示以及不等待确认的汇总提示。
    末尾调用 achievement_service.settle_and_notify 结算收藏服装类型成就。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值，直接更新玩家收藏品并触发成就结算
    """
    ui_hooks.emit_notice(_("\n开始摆放藏品\n"), wait=True, use_text_width=True)
    now_draw_text = ""

    panties_tem = player_collection.get("npc_panties_tem")
    if panties_tem:
        npc_panties = player_collection.get("npc_panties")
        for npc_id, pan_ids in panties_tem.items():
            if npc_id == 0:
                continue
            for pan_id in pan_ids:
                if pan_id not in game_config.config_clothing_tem:
                    continue
                pan_name = game_config.config_clothing_tem[pan_id].name
                npc_panties.setdefault(npc_id, []).append(pan_name)
                now_draw_text += _("增加了藏品：{0}的{1}\n").format(
                    identity.of(npc_id).name, pan_name
                )
                ui_hooks.emit_notice("", wait=False, use_text_width=True)
        player_collection.update(npc_panties=npc_panties, npc_panties_tem={})

    socks_tem = player_collection.get("npc_socks_tem")
    if socks_tem:
        npc_socks = player_collection.get("npc_socks")
        for npc_id, sock_ids in socks_tem.items():
            if npc_id == 0:
                continue
            for socks_id in sock_ids:
                if socks_id not in game_config.config_clothing_tem:
                    continue
                socks_name = game_config.config_clothing_tem[socks_id].name
                npc_socks.setdefault(npc_id, []).append(socks_name)
                now_draw_text += _("增加了藏品：{0}的{1}\n").format(
                    identity.of(npc_id).name, socks_name
                )
                ui_hooks.emit_notice("", wait=False, use_text_width=True)
        player_collection.update(npc_socks=npc_socks, npc_socks_tem={})

    ui_hooks.emit_notice(now_draw_text, wait=False, use_text_width=True)
    ui_hooks.emit_notice(_("\n摆放藏品结束\n"), wait=True, use_text_width=True)

    achievement_service.settle_and_notify(_("收藏服装"))


def refresh_all_bonus() -> None:
    """
    按已获得的信物收集奖励刷新玩家信物装备上限。
    函数按顺序遍历 config_collection_bonus_data，遇编号大于等于 10 即停止。
    对于已获得的奖励，函数将装备上限取当前值与该项 effect_2 的较大值，不降低既有上限。
    仅当上限发生变化时写回 eqip_token 并保留已装备信物列表。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值，必要时更新玩家信物装备上限
    """
    eqip = player_collection.get("eqip_token")
    limit = eqip[0]
    for bonus_id in game_config.config_collection_bonus_data:
        if bonus_id >= 10:
            break
        bonus_data = game_config.config_collection_bonus_data[bonus_id]
        if player_collection.bonus(bonus_id):
            limit = max(limit, bonus_data.effect_2)
    if limit != eqip[0]:
        player_collection.set_eqip_token(limit, eqip[1])
