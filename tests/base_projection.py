# -*- coding: UTF-8 -*-
"""
快照里按旧罗德岛对象的属性名记下招募、公务、外交、宿舍管理员、图书馆、关押区、教育区、工程部与体检的值
======================================================================================================
kernel_data.project_state 调用 project。快照因此能与按缓存属性录下的快照逐项比较。
"""


def project(state: dict[str, object]) -> None:
    """
    快照里按旧罗德岛对象的属性名记下招募、公务、外交、宿舍管理员、图书馆、关押区、教育区、工程部与体检的值。
    借阅表与推荐阅读记在 world.library 下，其余记在 world.base 下。
    招募线记作旧的四项列表，效率一项记 0。外交记作 [外交官, 外交方针]
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import diplomacy, dormitory, education, library
    from Script.Modules.domains import maintenance as m
    from Script.Modules.domains import official, prison, recruit
    from Script.Modules.domains import physical_exam as px
    from tests.snapshot import flatten

    island = {
        "recruit_line": {
            i: [v["progress"], v["strategy"], v["main"], 0]
            for i, v in recruit.lines().items()
        },
        "recruited_id": recruit.pending(),
        "office_work": official.office_work(),
        "official_event_queue": official.queue(),
        "official_event_history": official.history(),
        "diplomat_of_country": {
            c: [v["diplomat"], v["policy"]]
            for c, v in diplomacy.table().items()
        },
        "dormitory_managers": dormitory.managers(),
        "current_prisoners": prison.prisoners(),
        "confinement_training_setting": prison.settings(),
        "pre_training_cleaning": prison.cleaning(),
        "pre_training_lubrication": prison.lubrication(),
        "pre_training_tool_dict": prison.tools(),
        "sex_assistant_ai_behavior_id_list": prison.assistant_behaviors(),
        "sex_assistant_ai_ban_behavior_id_list": (
            prison.assistant_ban_behaviors()
        ),
        "class_schedule": education.class_schedule(),
        "temp_sex_class": education.temp_classes(),
        "child_schedule_template": education.templates(),
        "facility_damage_data": m.damage(),
        "maintenance_place": m.places(),
        "maintenance_equipment_chara_id": m.repairs(),
        "equipment_maintain_setting": m.settings(),
        "equipment_maintain_operator_ids": m.operators(),
        "physical_examination_setting": px.settings(),
        "today_physical_examination_chara_id_dict": px.checks(px.TODAY),
        "physical_examination_in_progress": px.checks(px.IN_PROGRESS),
        "examined_operator_ids": px.ids(px.EXAMINED),
        "waiting_for_exam_operator_ids": px.ids(px.WAITING),
        "manually_selected_exam_operator_ids": px.ids(px.CHOSEN),
        "manually_selected_exam_week_day_list": px.week_days(),
    }
    for field, value in island.items():
        flatten(f"world.base.{field}", value, state)
    flatten("world.library.book_borrow_dict", library.holders(), state)
    name = "world.library.recommend_book_type_set"
    flatten(name, library.recommended(), state)
