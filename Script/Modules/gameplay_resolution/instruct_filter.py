"""
指令过滤服务（instruct_filter）
===============================
提供单个指令的过滤开关、子类筛选、前提条件、调试覆盖与儿童阶段门禁判定。
不直接导入界面模块，供操作菜单面板、调教助手与相关行为筛选逻辑调用。
"""

from Script.Config import normal_config
from Script.Core import constant
from Script.Design import child_stage_gate, handle_premise
from Script.Modules.domains import modes


def judge_single_instruct_filter(
    instruct_id: str,
    now_premise_data: dict,
    now_type: int,
    use_type_filter_flag: bool = True,
    skip_h_judge: bool = False,
    skip_not_h_judge: bool = False,
) -> tuple:
    """
    判定单个指令是否通过过滤并更新前提缓存。
    先查 instruct_index_filter（缺项补写为 True），启用类型过滤、显示 H 指令且类型为 SEX 时再查子类开关。
    再按排序后的前提编号依次求值并写入 now_premise_data，排序使求值时的随机抽取不受集合遍历顺序影响。
    未开类型过滤且 t_npc_active_h 成立时跳过 t_npc_not_active_h，调试模式强制通过，但 child_stage_gate 拦截始终生效。
    Keyword arguments:
    instruct_id -- str，指令编号
    now_premise_data -- dict，前提缓存
    now_type -- int，指令类型
    use_type_filter_flag -- bool，是否启用类型过滤
    skip_h_judge -- bool，是否将 is_h 记为 1
    skip_not_h_judge -- bool，是否将 not_h 记为 1
    Return arguments:
    tuple -- (是否通过, now_premise_data)
    """
    filter_judge = True
    if instruct_id not in normal_config.system_setting.instruct_index_filter:
        normal_config.system_setting.instruct_index_filter[instruct_id] = True
    if not normal_config.system_setting.instruct_index_filter[instruct_id]:
        filter_judge = False
    if (
        use_type_filter_flag
        and handle_premise.handle_now_show_h_instruct(0)
        and now_type == constant.InstructType.SEX
    ):
        now_sub_type = constant.instruct_sub_type_data[instruct_id]
        if (
            normal_config.system_setting.instruct_sex_type_filter[now_sub_type]
            == 0
        ):
            filter_judge = False
    if filter_judge:
        premise_judge = True
        if instruct_id in constant.instruct_premise_data:
            for premise in sorted(constant.instruct_premise_data[instruct_id]):
                if (
                    not use_type_filter_flag
                    and handle_premise.handle_t_npc_active_h(0)
                    and premise == "t_npc_not_active_h"
                ):
                    continue
                if premise in now_premise_data:
                    if now_premise_data[premise]:
                        continue
                    premise_judge = False
                    break
                elif skip_h_judge and premise == "is_h":
                    now_premise_data[premise] = 1
                elif skip_not_h_judge and premise == "not_h":
                    now_premise_data[premise] = 1
                else:
                    now_premise_value = handle_premise.handle_premise(
                        premise, 0
                    )
                    now_premise_data[premise] = now_premise_value
                    if not now_premise_value:
                        premise_judge = False
                        break
        if not premise_judge:
            filter_judge = False
    if modes.debug():
        filter_judge = True
    if child_stage_gate.blocks_instruct(instruct_id):
        filter_judge = False

    return filter_judge, now_premise_data
