# -*- coding: UTF-8 -*-
"""
测试里角色的道具、食物背包、服装、身体管理与状态值
==================================================
- seed 给测试造的角色写下置零的服装（含宿舍与浴室衣柜）、状态值与身体管理，再穿上给出的衣服。
- project 把缓存里每个角色的这五项记进快照，名字为 chara.<id>.item、food_bag、cloth、body_manage 与 status_data。
  快照因此能与按这些名字录下的基准快照逐项比较。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from tests.kernel_project import identity


def seed(cid: int, outfit: Mapping[int, Sequence[int]]) -> None:
    """
    给角色写下置零的服装、状态值与身体管理，再按 outfit 穿上衣服。写法同 kernel_data.put
    Keyword arguments:
    cid -- 角色id
    outfit -- 服装类型到穿着的衣服id
    """
    from Script.Design import attr_calculation
    from Script.Modules.domains import body_manage, status, wardrobe
    from tests import kernel_data

    cloth = attr_calculation.get_cloth_zero()
    cloth.cloth_locker_in_dormitory = (
        attr_calculation.get_cloth_locker_in_dormitory_zero()
    )
    cloth.cloth_locker_in_shower = (
        attr_calculation.get_shower_cloth_locker_zero()
    )
    for clothing_type, cloth_ids in outfit.items():
        cloth.cloth_wear[clothing_type] = list(cloth_ids)
    kernel_data.put(wardrobe.put, cid, cloth)
    kernel_data.put(status.replace, cid, attr_calculation.get_status_zero({}))
    zero = attr_calculation.get_body_manage_zero()
    kernel_data.put(body_manage.replace, cid, zero)


def project(state: dict[str, object]) -> None:
    """
    快照里记下缓存里每个角色的道具、食物背包、服装、身体管理与状态值，
    名字为 chara.<id>.item、food_bag、cloth、body_manage 与 status_data
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import body_manage, inventory, status
    from Script.Modules.domains import wardrobe
    from tests.snapshot import flatten

    for cid in identity.table():
        fields: dict[str, object] = {
            "item": dict(inventory.items(cid)),
            "food_bag": inventory.clone_mutable_snapshot_foods(cid),
            "cloth": wardrobe.clone_mutable_snapshot(cid),
            "body_manage": dict(body_manage.of(cid)),
            "status_data": dict(status.of(cid)),
        }
        for field, value in fields.items():
            flatten(f"chara.{cid}.{field}", value, state)
