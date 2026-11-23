"""
角色自定义指令服务（diy_instruct_service）
==========================================
提供按交互对象查询可用角色自定义指令事件的后端逻辑。
本模块不直接导入界面、Tk 或 IO 模块，供前提判定与指令面板调用。
"""

from Script.Config import game_config
from Script.Core import constant
from Script.Design import handle_premise
from Script.Modules.domains import activity, identity


def get_target_chara_diy_instruct(
    character_id: int = 0,
) -> tuple[int, list[str]]:
    """
    获得交互对象当前满足前提的角色自定义指令子事件。
    函数按交互对象的剧情 npc 编号（adv）查找配置表中的自定义指令事件列表。
    各事件共用同一前提结果字典，避免重复计算前提。
    调用前提判定时传入 unconscious_pass_flag=True，跳过无意识目标拦截。
    无交互对象或无对应事件配置时返回 (0, [])。
    Keyword arguments:
    character_id -- int，发起交互的角色编号，默认为 0
    Return arguments:
    tuple[int, list[str]] -- 依次为权重非零的子事件数量与按配置顺序排列的子事件编号列表
    """
    son_event_list = []
    if activity.target(character_id):
        target_character_data = identity.of(activity.target(character_id))
        if (
            constant.Behavior.CHARA_DIY_INSTRUCT
            in game_config.config_event_status_data_by_chara_adv
        ):
            all_chara_diy_instruct_event_list = (
                game_config.config_event_status_data_by_chara_adv[
                    constant.Behavior.CHARA_DIY_INSTRUCT
                ]
            )
            if target_character_data.adv in all_chara_diy_instruct_event_list:
                target_diy_instruct_event_list = (
                    all_chara_diy_instruct_event_list[target_character_data.adv]
                )
                calculated_premise_dict: dict[str, float] = {}
                for event_id in target_diy_instruct_event_list:
                    event_config = game_config.config_event[event_id]
                    now_weight, calculated_premise_dict = (
                        handle_premise.get_weight_from_premise_dict(
                            event_config.premise,
                            character_id,
                            calculated_premise_dict,
                            unconscious_pass_flag=True,
                        )
                    )
                    if now_weight:
                        son_event_list.append(event_id)

    return len(son_event_list), son_event_list
