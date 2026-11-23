"""
精液污浊与流动服务（semen_dirty_service）
=========================================
提供角色身体部位、穿着服装与衣柜服装的精液污浊更新，以及精液流动队列计算功能。
本模块不直接导入界面、Tk 或输入输出模块。
"""

from Script.Config import game_config, normal_config
from Script.Design import attr_calculation, game_time, handle_premise
from Script.Modules.domains import abilities, activity, dirty, first_record
from Script.Modules.domains import h_state, wardrobe


def update_semen_dirty(
    character_id: int,
    part_cid: int,
    part_type: int,
    semen_count: int,
    update_shoot_position_flag: bool = True,
) -> None:
    """
    更新部位的被射精污浊数据
    Keyword arguments:
    character_id -- 角色id
    part_cid -- 部位cid
    part_type -- 部位类型，0为身体，1为穿着服装，2为浴场衣柜，3为宿舍衣柜
    semen_count -- 精液量
    update_shoot_position_flag -- 是否更新射精部位
    """
    talent = abilities.talent(character_id)

    if part_type == 0:
        if part_cid == 12 and not talent[113]:
            return
        elif part_cid == 13 and not talent[112]:
            return
        elif part_cid == 14 and not talent[111]:
            return
    elif part_type == 1:
        if not len(wardrobe.of(character_id).cloth_wear[part_cid]):
            return
    elif part_type == 2:
        if not len(wardrobe.of(character_id).cloth_locker_in_shower[part_cid]):
            return
    else:
        if not wardrobe.of(character_id).cloth_locker_in_dormitory[part_cid]:
            return

    with dirty.editing(character_id) as d:
        if part_type == 0:
            now_semen_data = d.body_semen[part_cid]
        elif part_type == 1:
            now_semen_data = d.cloth_semen[part_cid]
        else:
            now_semen_data = d.cloth_locker_semen[part_cid]

        if (
            part_type == 0
            and semen_count > 0
            and now_semen_data[3] == 0
            and not first_record.has_shoot_body(character_id, part_cid)
        ):
            with first_record.editing(character_id) as fr:
                fr.first_shoot_body_dict[part_cid] = [
                    game_time.now(),
                    list(activity.position(character_id)),
                ]
        now_semen_data[1] += semen_count
        now_semen_data[1] = max(now_semen_data[1], 0)
        if semen_count > 0:
            now_semen_data[3] += semen_count
        now_semen_data[2] = attr_calculation.get_semen_now_level(
            now_semen_data[1], part_cid, part_type
        )
        if update_shoot_position_flag:
            if part_type == 0:
                h_state.set(character_id, shoot_position_body=part_cid)
                if (
                    handle_premise.handle_unconscious_flag_ge_1(character_id)
                    and part_cid not in d.body_semen_in_unconscious
                ):
                    d.body_semen_in_unconscious.append(part_cid)
            else:
                h_state.set(character_id, shoot_position_cloth=part_cid)
                if (
                    handle_premise.handle_unconscious_flag_ge_1(character_id)
                    and part_cid not in d.cloth_semen_in_unconscious
                ):
                    d.cloth_semen_in_unconscious.append(part_cid)
            if semen_count > 0:
                h_state.set(
                    0,
                    insert_position=-1,
                    pre_sex_position=h_state.get(0, "current_sex_position"),
                    current_sex_position=-1,
                )
                h_state.set(character_id, insert_position=-1)
        if (
            part_type == 0
            and part_cid == 8
            and now_semen_data[2] > 1
            and normal_config.system_setting.base_setting[8]
            and handle_premise.handle_have_clyster_tools(0)
            and handle_premise.handle_target_a_empty(0)
        ):
            d.a_clean = 3
            if now_semen_data[2] <= 3:
                d.enema_capacity = 1
            elif now_semen_data[2] <= 5:
                d.enema_capacity = 2
            elif now_semen_data[2] == 6:
                d.enema_capacity = 3
            elif now_semen_data[2] == 7:
                d.enema_capacity = 4
            else:
                d.enema_capacity = 5
            if h_state.get(character_id, "insert_position") == 8:
                h_state.set(character_id, insert_position=-1)
            if handle_premise.handle_group_sex_mode_on(0):
                with h_state.editing(0) as pl_hs:
                    now_template_data = pl_hs.group_sex_body_template_dict["A"]
                    behavior_id = now_template_data[0]["penis"][1]
                    if behavior_id == -1:
                        return
                    behavior_data = game_config.config_behavior[behavior_id]
                    if "A" in behavior_data.tag:
                        now_template_data[0]["penis"] = [-1, -1]


def calculate_semen_flow(
    character_id: int, part_cid: int, part_type: int, semen_count: int
) -> None:
    """
    计算精液流动
    Keyword arguments:
    character_id -- 角色id
    part_cid -- 部位cid
    part_type -- 部位类型，0为身体，1为穿着服装
    semen_count -- 精液量
    """
    if character_id != 0:
        flow_targets: list[dict[str, int]] = []
        all_flow_dict = {
            "source": {"type": part_type, "id": part_cid},
            "targets": flow_targets,
        }

        with dirty.editing(character_id) as d:
            if part_type == 0:
                max_volume = game_config.config_body_part[part_cid].max_volume
                if d.body_semen[part_cid][1] > max_volume:
                    flow_list = game_config.config_body_part_full_flow[part_cid]
                    semen_count = d.body_semen[part_cid][1] - max_volume
                else:
                    flow_list = game_config.config_body_part_normal_flow[
                        part_cid
                    ]
            else:
                max_volume = game_config.config_clothing_type[
                    part_cid
                ].max_volume
                if d.cloth_semen[part_cid][1] > max_volume:
                    flow_list = game_config.config_cloth_part_full_flow[
                        part_cid
                    ]
                    semen_count = d.cloth_semen[part_cid][1] - max_volume
                else:
                    flow_list = game_config.config_cloth_part_normal_flow[
                        part_cid
                    ]

            for flow_str in flow_list:
                flow_type = flow_str[0]
                flow_cid = int(flow_str[1:].split("-")[0])
                flow_rate = int(flow_str[1:].split("-")[1])
                now_flow_dict: dict[str, int] = {}
                if flow_type == "B":
                    now_flow_dict["type"] = 0
                elif flow_type == "C":
                    now_flow_dict["type"] = 1
                elif flow_type == "E":
                    now_flow_dict["type"] = 2
                now_flow_dict["id"] = flow_cid
                now_flow_dict["remaining_volume"] = max(
                    1, int(semen_count * flow_rate / 100)
                )
                flow_targets.append(now_flow_dict)

            d.semen_flow.append(all_flow_dict)
