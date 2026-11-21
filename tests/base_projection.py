# -*- coding: UTF-8 -*-
"""
快照里按旧罗德岛对象的属性名记下招募、公务、外交、宿舍管理员与图书馆的值
======================================================================
kernel_data.project_state 调用 project。快照因此能与按缓存属性录下的快照逐项比较。
"""


def project(state: dict[str, object]) -> None:
    """
    快照里按旧罗德岛对象的属性名记下招募、公务、外交、宿舍管理员与图书馆的值。借阅表与推荐阅读记在 world.library 下，
    其余记在 world.base 下。招募线记作旧的四项列表，效率一项记 0。外交记作 [外交官, 外交方针]
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import diplomacy, dormitory, library
    from Script.Modules.domains import official, recruit
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
    }
    for field, value in island.items():
        flatten(f"world.base.{field}", value, state)
    flatten("world.library.book_borrow_dict", library.holders(), state)
    name = "world.library.recommend_book_type_set"
    flatten(name, library.recommended(), state)
