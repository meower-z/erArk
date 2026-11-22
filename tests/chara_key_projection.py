# -*- coding: UTF-8 -*-
"""
快照里的角色键
==============
project 把 relations、chara_life 与 chara_profile 的角色键记进快照，名字为 chara.<角色id>.<旧属性路径>。
旧属性路径是旧存档里这项数据在角色对象上的路径（CharaKey.old）。
快照因此能与按角色对象的属性录下的基准逐项比较。SKIPPED 里的旧属性路径不记。
tests/snapshot.py 的 capture 调用 project。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from tests.kernel_project import identity

if TYPE_CHECKING:
    from Script.Core import game_type

SKIPPED = {
    "nick_name": "玩家起的昵称（文本）",
    "nick_name_to_pl": "角色对玩家的称呼（文本）",
}
""" 不记的角色键（旧属性路径）: 理由 """


def project(cache: game_type.Cache, state: dict[str, object]) -> None:
    """
    把每个角色的角色键记进快照，名字为 chara.<角色id>.<旧属性路径>，值经 tests.snapshot.flatten 逐项展开
    Keyword arguments:
    cache -- 游戏缓存，取其中的角色id
    state -- 快照，原地补上
    """
    from Script.Modules.domains import chara_life, chara_profile, relations
    from tests.snapshot import flatten

    every = (*relations.KEYS, *chara_life.KEYS, *chara_profile.KEYS)
    keys = [key for key in every if key.old not in SKIPPED]
    for cid in identity.table():
        for key in keys:
            flatten(f"chara.{cid}.{key.old}", key(cid), state)
