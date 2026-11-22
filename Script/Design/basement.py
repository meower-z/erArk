"""罗德岛基地的数据刷新与结算：设施数值与效率、每日资源、工作干员、母乳与精液转化、公务、粉红凭证、待办事项与设施损坏"""

import random
from types import FunctionType
from Script.Core import cache_control, game_type, get_text, constant
from Script.Config import game_config, normal_config
from Script.Design import handle_premise, map_handle
from Script.UI.Moudle import draw
from Script.Modules.domains import abilities, diplomacy, economy, facility
from Script.Modules.domains import flags, fridge, maintenance, official
from Script.Modules.domains import physical_exam, power, production, recruit
from Script.Modules.domains import roster, tallies, warehouse, work

cache: game_type.Cache = cache_control.cache
""" 游戏内缓存数据 """
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
width = normal_config.config_normal.text_width
""" 屏幕宽度 """
_: FunctionType = get_text._
""" 翻译api """


def get_base_zero() -> game_type.Rhodes_Island:
    """
    基地情况结构体，设为空。医疗部数据不在罗德岛对象上，新游戏与新周目另调 medical_service.init_medical_department_data
    """
    base_data = game_type.Rhodes_Island()

    return base_data


def get_base_updata() -> None:
    """
    先调用 facility.open_by_level 按各设施的当前等级开放够条件的待开放设施。随后按设施当前等级开放招募线与生产线。
    它还按疗养庭院的等级重置计数 tallies.AROMATHERAPY
    """
    facility.open_by_level()
    for all_cid in game_config.config_facility:
        level = facility.level(all_cid)
        facility_name = game_config.config_facility[all_cid].name

        # 按等级开放招募线：1 级 1 条，3 到 5 级每级多 1 条
        if facility_name == _("文职部"):
            recruit.open_lines(
                [i for i, need in enumerate((0, 3, 4, 5)) if level >= need]
            )
        elif facility_name == _("制造加工区"):
            # 按等级开放流水线：1 级 1 条，2 到 5 级每级多 1 条
            production.open_lines(
                "assembly",
                [i for i, need in enumerate((0, 2, 3, 4, 5)) if level >= need],
            )
        elif facility_name == _("疗养庭院"):
            production.open_lines("green_house", [0])
            # 香薰治疗室
            # 刷新香薰疗愈次数
            if level >= 5:
                tallies.set(tallies.AROMATHERAPY, 3)
            elif level == 4:
                tallies.set(tallies.AROMATHERAPY, 2)
            elif level <= 3:
                tallies.set(tallies.AROMATHERAPY, 1)
        elif facility_name == _("药田"):
            production.open_lines(
                "herb_garden",
                [i for i, need in enumerate((0, 3, 4, 5)) if level >= need],
            )


def calc_facility_efficiency(facility_cid: int = -1) -> float:
    """
    计算区块的工作效率（百分比）
    输入:
        facility_cid -- 设施编号，默认为-1表示计算全局效率
    输出:
        float - 效率（例如 1.1 表示 110%）
    说明:
        根据设施编号计算对应区块的工作效率，若设施编号为-1则计算全局效率
    """
    # 基地整体效率
    adjust = facility.effectiveness() / 100
    # 参数校验
    if facility_cid == -1 or facility_cid not in game_config.config_facility:
        return adjust
    # 获取设施数据
    facility_data = game_config.config_facility[facility_cid]
    facility_name = facility_data.name
    now_level = facility.level(facility_cid)
    # 设施效果数据
    facility_effect_cid = game_config.config_facility_effect_data[
        facility_name
    ][int(now_level)]
    facility_effect = game_config.config_facility_effect[
        facility_effect_cid
    ].effect
    # 子设施获得父区块的供电策略
    zone_cid = facility_cid
    if facility_data.type >= 0:
        zone_cid = facility_data.type
    # 供电策略的调整
    now_power_strategy = power.strategy_of(zone_cid)
    now_power_strategy_adjust = game_config.config_supply_strategy[
        now_power_strategy
    ].adjust
    # 设施路径名
    room_full_str_list = []
    # TODO 厨房，因为没有单独设施id所以用区块id代替
    if facility_cid == 5:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["生娱", "厨房"])
        )
    elif facility_cid == 6:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["医疗", "急诊室"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["医疗", "门诊室"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["医疗", "手术室"])
        )
    elif facility_cid == 7:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["文职", "办公室"])
        )
    elif facility_cid == 9:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["训练", "健身区"])
        )
    elif facility_cid == 12:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(
                ["制造加工", "生产车间1"]
            )
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(
                ["制造加工", "生产车间2"]
            )
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(
                ["制造加工", "生产车间3"]
            )
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(
                ["制造加工", "生产车间4"]
            )
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(
                ["制造加工", "生产车间5"]
            )
        )
    elif facility_cid == 13:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["访客", "外交办公室"])
        )
    elif facility_cid == 16:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["疗养庭院", "药田"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["疗养庭院", "温室"])
        )
    elif facility_cid == 19:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "办公室"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢1"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢2"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢3"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢4"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢5"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢6"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢7"])
        )
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["关押", "牢8"])
        )
    elif facility_cid == 22:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["中枢", "博士办公室"])
        )
    elif facility_cid == 41:
        room_full_str_list.append(
            map_handle.get_map_system_path_str_for_list(["疗养庭院", "药田"])
        )
    # 设施损坏调整
    damage = maintenance.damage() if room_full_str_list else {}
    for room_full_str in room_full_str_list:
        if room_full_str in damage:
            adjust -= damage[room_full_str] * 0.02
    # 有特殊计算公式的区块
    # 宿舍区
    if facility_cid == 4:
        adjust += now_level * 0.02
        adjust -= (1 - now_power_strategy_adjust) / 4
    # 其他直接乘以供电策略
    else:
        # 厨房、健身区、制造加工区、访客区、疗养庭院、博士办公室、药田
        if facility_cid in [5, 7, 9, 12, 13, 16, 22, 41]:
            adjust += facility_effect / 100
        adjust *= now_power_strategy_adjust
    # 效率不会小于20%
    adjust = max(adjust, 0.2)
    return adjust


def update_base_resouce_newday() -> None:
    """
    每日刷新基地资源数据\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """
    from Script.UI.Panel import (
        invite_visitor_panel,
        aromatherapy_panel,
        agriculture_production_panel,
        manage_assembly_line_panel,
        physical_check_and_manage,
        confinement_and_training,
        resource_exchange_panel,
    )
    from Script.System.Medical_System import medical_service
    from Script.System.Cooking_System import cooking

    now_draw = draw.WaitDraw()
    now_draw.width = window_width

    # 按当前在编角色重建岗位人员数据，供后续岗位结算使用
    update_work_people()
    # 结算公务工作
    settle_office_work()
    # 结算精液转化
    settle_semen()
    # 结算母乳转化
    settle_milk()
    # 结算医疗经营，并输出日报
    medical_service.settle_medical_department()
    # 结算农业生产
    agriculture_production_panel.settle_agriculture_line()
    # 结算流水线
    manage_assembly_line_panel.settle_assembly_line(newdayflag=True)
    # 结算访客抵达和离开
    invite_visitor_panel.settle_visitor_arrivals_and_departures()
    # 结算资源的供需涨跌与自动交易
    resource_exchange_panel.daily_supply_demand_fluctuation()
    # 刷新香薰疗愈次数
    aromatherapy_panel.settle_aromatherapy_sessions()
    # 结算粉红凭证
    settle_pink_certificate()
    # 结算体检
    physical_check_and_manage.settle_health_check()
    # 刷新食堂食物
    cooking.init_food_shop_data(new_day_flag=True)
    # 囚犯逃跑结算
    confinement_and_training.settle_prisoners()


def update_work_people() -> None:
    """
    刷新各干员的职位和当前正在工作的干员
    """
    from Script.System.Medical_System import medical_constant, medical_service

    # 各岗位的干员名单，按遍历在编干员的顺序重建
    rosters: dict[int, list[int]] = {}
    warden_id = work.warden()
    # 重置各岗位当前人员名单，后续按在编角色重建
    line_workers: dict[str, list[int]] = {kind: [] for kind in production.KINDS}

    clinic_doctors = []
    hospital_doctors = []
    clinic_power_total = 0.0
    hospital_power_total = 0.0
    clinic_work_id = medical_constant.MedicalDoctorProfession.CLINICIAN.value
    hospital_work_id = (
        medical_constant.MedicalDoctorProfession.HOSPITALIST.value
    )

    # 检查各资源类型主交易员有效性
    economy.drop_invalid_traders()

    # 已经不是招聘专员的，撤销主招聘专员
    recruit_lines = recruit.lines()
    for line in recruit_lines.values():
        main_id = line["main"]
        if main_id and main_id in cache.character_data:
            if cache.character_data[main_id].work.work_type != 71:
                line["main"] = 0
    recruit.put_lines(recruit_lines)
    # 撤下职位与生产线不对应的主负责人
    for kind in production.KINDS:
        production.release_mains(kind)

    # 遍历在编干员，把每人加进所在岗位的名单（无岗位的进岗位 0）
    roster.discard(0)
    for chara_id in roster.active():
        character_data = cache.character_data[chara_id]
        work_type = character_data.work.work_type

        rosters.setdefault(work_type, []).append(chara_id)
        if work_type:
            # 外交官丢失了驻在国信息时的数据修复
            if (
                work_type == 131
                and flags.get(character_data.cid, "in_diplomatic_visit") == 0
            ):
                for country_id, post in diplomacy.table().items():
                    # 仍在外交官名册上的，补回驻在国信息
                    if post["diplomat"] == chara_id:
                        flags.set(
                            character_data.cid, in_diplomatic_visit=country_id
                        )
                        break
                else:
                    # 名册上没有的，视为旧版本的外交官数据，改为新的邀请专员
                    character_data.work.work_type = 132

        if work_type == clinic_work_id:
            clinic_doctors.append(chara_id)
            clinic_power_total += float(
                abilities.ability(chara_id).get(
                    medical_constant.MEDICAL_ABILITY_ID, 0
                )
                or 0
            )
        elif work_type == hospital_work_id:
            hospital_doctors.append(chara_id)
            hospital_power_total += float(
                abilities.ability(chara_id).get(
                    medical_constant.MEDICAL_ABILITY_ID, 0
                )
                or 0
            )

        # 如果不是检修工程师，则清空该角色的检修目标
        if work_type != 21:
            maintenance.drop_place(chara_id)

        # 如果不是铁匠，则清空该角色的维修装备
        if work_type != 22:
            maintenance.drop_repair(chara_id)

        # 生产工人与种植员按遍历顺序排进对应生产线的工人名单
        for kind, kind_work in production.KINDS.items():
            if work_type == kind_work:
                line_workers[kind].append(chara_id)

        # 如果是监狱长，则更新监狱长id
        if work_type == 191:
            warden_id = chara_id

    work.set_rosters(rosters)
    work.set_warden(warden_id)
    for kind, cids in line_workers.items():
        production.set_workers(kind, cids)
    clinic_doctors.sort()
    hospital_doctors.sort()
    medical_service.update_doctor_assignments(
        clinic_doctors=clinic_doctors,
        hospital_doctors=hospital_doctors,
        clinic_power=clinic_power_total,
        hospital_power=hospital_power_total,
        target_base=cache.rhodes_island,
    )


def library_reader_count() -> int:
    """
    当前图书馆中的读者数量
    Return arguments:
    int -- 在图书馆里的干员数（不含玩家）
    """
    return sum(
        1
        for id in roster.active() - {0}
        if handle_premise.handle_in_library(id)
    )


def settle_milk() -> None:
    """
    结算母乳转化
    """

    all_milk = 0

    # 结算冰箱中的母乳
    for now_milk in fridge.table(fridge.MILK).values():
        warehouse.add(31, now_milk)
        all_milk += now_milk
    fridge.clear(fridge.MILK)

    # 结算所有角色携带的母乳
    chara_id_list = list(cache.character_data.keys())
    chara_id_list.append(0)
    for character_id in chara_id_list:
        character_data: game_type.Character = cache.character_data[character_id]

        # 遍历角色背包
        for food_id in character_data.food_bag.copy():
            food: game_type.Food = character_data.food_bag[food_id]
            # 如果是母乳，则转化，并删掉原物品
            if food.milk_ml > 0:
                warehouse.add(31, food.milk_ml)
                all_milk += food.milk_ml
                # print(f"debug {character_data.name}携带的母乳（{food.ml}ml）已转化为罗德岛的母乳")
                del character_data.food_bag[food.uid]

    # 输出提示信息
    if all_milk > 0:
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _(
            "\n今日共有{0}ml母乳未使用，已全部转化为【鲜母乳】\n"
        ).format(all_milk)
        now_draw.draw()

    # 检测是否超出仓库容量上限
    if warehouse.amount(31) > warehouse.capacity():
        warehouse.set(31, warehouse.capacity())
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _(
            "\n由于仓库容量不足，【鲜母乳】已达上限数量{0}\n"
        ).format(warehouse.capacity())
        now_draw.draw()


def settle_semen() -> None:
    """
    结算精液转化
    """

    today_semen = tallies.get(tallies.SEMEN)
    warehouse.add(12, today_semen)
    tallies.set(tallies.SEMEN, 0)

    # 输出提示信息
    if today_semen:
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _(
            "\n今日共射出{0}ml精液，已全部转化为【矿石病药材】\n"
        ).format(today_semen)
        now_draw.draw()

    # 检测是否超出仓库容量上限
    if warehouse.amount(12) > warehouse.capacity():
        warehouse.set(12, warehouse.capacity())
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _(
            "\n由于仓库容量不足，【矿石病药材】已达上限数量{0}\n"
        ).format(warehouse.capacity())
        now_draw.draw()


def settle_office_work() -> None:
    """
    结算公务
    """

    now_work = official.office_work()
    # 全设施等级的和
    all_facility_level = sum(facility.levels().values())
    # 总工作量为设施等级和*10+干员数量
    all_work = all_facility_level * 10 + roster.count()
    # 根据当前剩余工作量和总工作量的比例，计算效率
    effectiveness_change = ((all_work / 2) - now_work) / all_work * 100
    if effectiveness_change > 0:
        effectiveness_change *= 2
    # 计算设施损坏
    max_damage_down = 0
    for damage_count in maintenance.damage().values():
        if max_damage_down < damage_count:
            max_damage_down = damage_count
    # 如果没有设备出现严重损坏，则增加全局效率
    if max_damage_down < 5:
        effectiveness_change += 5
    # 否则减少全局效率
    else:
        effectiveness_change -= max_damage_down
    # 结算能源系统
    from Script.Settle import power_settle

    shortage_ratio, __ = power_settle.settle_power_system(draw_flag=True)
    # # 如果能源系统出现供电不足，则降低效率
    effectiveness_change -= shortage_ratio / 2
    # 效率不会小于50，也不会大于200
    effectiveness = min(100 + int(effectiveness_change), 200)
    facility.set_effectiveness(round(max(effectiveness, 50), 1))
    # 取0.3~0.7的随机数，作为新增的工作量
    add_work = random.randint(30, 70) / 100 * all_work
    # 把新增的工作量加入当前剩余工作量，工作量不会小于0，也不会大于总工作量
    official.set_office_work(max(min(now_work + add_work, all_work), 0))
    # 输出提示信息
    now_draw_text = _("\n今日剩余待处理公务量为{0:.1f}，").format(now_work)
    if max_damage_down < 5:
        now_draw_text += _("且各区块设施运行基本正常，")
    else:
        now_draw_text += _("且部分区块设施出现较大故障，")
    # if shortage_ratio == 0:
    #     now_draw_text += _("能源系统供电充足，")
    # else:
    #     now_draw_text += _("但能源系统出现供电不足，")
    now_draw_text += _("因此今日罗德岛的各设施的总效率为{0}%\n").format(
        facility.effectiveness()
    )
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = now_draw_text
    now_draw.draw()


def settle_pink_certificate() -> None:
    """
    结算粉红凭证
    """

    # 根据好感度结算粉红凭证增加
    favorability = tallies.get(tallies.FAVORABILITY)
    fallen = tallies.get(tallies.FALLEN)
    pink_certificate_add = max(int(favorability / 100), 0)
    warehouse.add(4, pink_certificate_add)
    # 结算陷落角色提供的的粉红凭证
    warehouse.add(4, fallen)
    # 输出提示信息
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = _(
        "\n今日全角色总好感度上升为：{0}，折合为 {1} 粉红凭证\n"
    ).format(
        int(favorability),
        pink_certificate_add,
    )
    if fallen:
        now_draw.text += _("本周全陷落角色提供的粉红凭证为：{0}\n").format(
            fallen
        )
    now_draw.draw()
    # 清零计数
    tallies.set(tallies.FAVORABILITY, 0)
    tallies.set(tallies.FALLEN, 0)


def draw_todo() -> None:
    """
    绘制待办事项
    """
    from Script.UI.Panel import (
        manage_assembly_line_panel,
        agriculture_production_panel,
        invite_visitor_panel,
    )
    from Script.Modules.domains import power_supply

    # 如果系统设置中关闭了待办事项，直接返回
    if normal_config.system_setting.draw_setting[5] == 0:
        return

    draw_text = ""

    # 供电是否不足
    power_generation = power_supply.power_generation()
    power_consumption = power_supply.power_consumption()
    if power_generation < power_consumption:
        draw_text += _("  当前供电不足，可能影响基地正常运转\n")

    # 是否有已招募待确认的干员
    if recruit.pending():
        draw_text += _("  当前有干员已招募，等待确认\n")

    # 是否有人正在等待体检
    if len(physical_exam.ids(physical_exam.WAITING)):
        draw_text += _("  当前有干员正在体检科等待体检\n")

    # 流水线生产是否正常
    un_normal, now_text = manage_assembly_line_panel.settle_assembly_line(
        draw_flag=False
    )
    if un_normal:
        draw_text += now_text[1:] + " "

    # 农业生产是否正常
    un_normal, now_text = agriculture_production_panel.settle_agriculture_line(
        draw_flag=False
    )
    if un_normal:
        draw_text += now_text[1:] + " "

    # 检查今日是否有访客离开
    departing_visitors = invite_visitor_panel.get_today_departing_visitors()
    if len(departing_visitors):
        draw_text += _("  今日有访客要离开罗德岛，且其留下意愿较低\n")

    # 如果有待办事项，输出待办事项
    if draw_text:
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = "\n" + draw_text
        now_draw.style = "gold_enrod"
        now_draw.draw()


def find_facility_damage() -> str:
    """
    检查设施损坏
    """
    tem_data = maintenance.damage()
    # 去掉已经有人在修理的地点
    for place in maintenance.places().values():
        if place in tem_data:
            tem_data.pop(place)
    target_scene_str = ""
    # 如果当前有损坏地点，则根据每个地点的数值大小作为权重选择一个
    if len(tem_data):
        # 计算总权重
        total_weight = 0
        for place_str in tem_data:
            total_weight += tem_data[place_str]
        # 随机一个数
        rand_num = random.randint(1, total_weight)
        # 遍历地点，减去权重，当权重小于0时，选中该地点
        for place_str in tem_data:
            rand_num -= tem_data[place_str]
            if rand_num <= 0:
                target_scene_str = place_str
                break
    # 否则随机选一个地点
    if not target_scene_str:
        # 指定的地点需要是可进入的
        while 1:
            target_scene_str = random.choice(constant.place_data["Room"])
            close_type = map_handle.judge_scene_accessible(
                target_scene_str, 0, draw_flag=False
            )
            if close_type == "open":
                break
    return target_scene_str
