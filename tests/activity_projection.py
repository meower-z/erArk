# -*- coding: UTF-8 -*-
"""
快照里按角色对象上的旧属性名记下角色的活动
==========================================
kernel_project.project_rest 调用 project。记下的名字同角色对象上的旧属性名，
所以新录的快照能与按角色属性录下的快照逐项比较。
"""

from __future__ import annotations

from tests.kernel_project import identity


def project(state: dict[str, object]) -> None:
    """
    快照里按旧角色对象的属性名记下每个角色的十项活动：state、last_behavior_id_list、behavior、second_behavior、
    must_settle_second_behavior_id_list、must_show_second_behavior_id_list、event、position、target_character_id
    与 dead，都记在 chara.<id> 下。行为与事件按字段展开，二段行为按id展开（值为 0 的不记，同快照的规则）
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import activity
    from tests.snapshot import flatten

    for cid in identity.table():
        fields: dict[str, object] = {
            "state": activity.state(cid),
            "last_behavior_id_list": activity.last_behaviors(cid),
            "behavior": activity.behavior(cid).as_dict(),
            "second_behavior": activity.second_behaviors(cid),
            "must_settle_second_behavior_id_list": activity.must_settle(cid),
            "must_show_second_behavior_id_list": activity.must_show(cid),
            "event": activity.event(cid).as_dict(),
            "position": activity.position(cid),
            "target_character_id": activity.target(cid),
            "dead": activity.dead(cid),
        }
        for field, value in fields.items():
            flatten(f"chara.{cid}.{field}", value, state)
