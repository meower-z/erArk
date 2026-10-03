"""时间线：每个角色至多一条待办（Entry），按"立即待办最先，其次按时刻，同一时刻玩家优先"取下一条"""

import datetime
from dataclasses import dataclass
from typing import Callable, Optional

from Script.Core import cache_control, game_type
from Script.Design.action_scheduler.action import Action

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


@dataclass
class Entry:
    """一条待办：开始时刻 at；行动 action，为 None 表示到时再定；是否立即执行 immediate；执行完后的收尾回调 after"""

    at: datetime.datetime
    action: Optional[Action] = None
    immediate: bool = False
    after: Optional[Callable[[], None]] = None


def chain_after(entry: Entry, callback: Optional[Callable[[], None]]):
    """
    在待办原有的收尾回调之后追加一个回调
    Keyword arguments:
    entry -- 待办
    callback -- 追加的回调，为 None 时不做任何事
    Return arguments:
    None
    """
    if callback is None:
        return
    previous = entry.after
    if previous is None:
        entry.after = callback
    else:
        entry.after = lambda: (previous(), callback())


class Timeline:
    """各角色的待办；同时刻同优先级时先写入的先执行"""

    def __init__(self):
        """
        建立空时间线
        Return arguments:
        None
        """
        self._entries: dict[int, Entry] = {}

    def __contains__(self, character_id: int) -> bool:
        """
        角色是否有待办
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        bool -- 是否有待办
        """
        return character_id in self._entries

    def get(self, character_id: int) -> Optional[Entry]:
        """
        取角色的待办
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        Entry | None -- 待办，没有时为 None
        """
        return self._entries.get(character_id)

    def items(self) -> list:
        """
        列出全部待办
        Return arguments:
        list -- (角色id, 待办) 列表，按写入先后
        """
        return list(self._entries.items())

    def put(self, character_id: int, entry: Entry):
        """
        写入角色的待办，替换其原有待办；新写入的排在同时刻同优先级的末尾
        Keyword arguments:
        character_id -- 角色id
        entry -- 待办
        Return arguments:
        None
        """
        self._entries.pop(character_id, None)
        self._entries[character_id] = entry

    def force(self, character_id: int, action: Action, after: Optional[Callable[[], None]] = None):
        """
        让角色此刻立即执行行动；角色已有立即待办时，排在它完成之后
        Keyword arguments:
        character_id -- 角色id
        action -- 行动
        after -- 行动完成后的收尾回调
        Return arguments:
        None
        """
        entry = self._entries.get(character_id)
        if entry is not None and entry.immediate:
            chain_after(entry, lambda: self.force(character_id, action, after))
            return
        self.put(character_id, Entry(cache.game_time, action, True, after))

    def drop(self, character_id: int):
        """
        撤销角色的待办
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        None
        """
        self._entries.pop(character_id, None)

    def has_immediate(self, character_id: int) -> bool:
        """
        角色是否有立即待办
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        bool -- 是否有立即待办
        """
        entry = self._entries.get(character_id)
        return entry is not None and entry.immediate

    def next(self) -> tuple:
        """
        查看下一条要执行的待办，不取出
        Return arguments:
        tuple -- (角色id, 待办)
        """
        return min(self._entries.items(), key=lambda item: (not item[1].immediate, item[1].at, item[0] != 0))

    def claim(self, character_id: int, entry: Entry) -> bool:
        """
        取出角色的待办，仅当它仍是 entry 时
        Keyword arguments:
        character_id -- 角色id
        entry -- 之前查看到的待办
        Return arguments:
        bool -- 是否取出；查看之后待办被替换或撤销时为 False
        """
        if self._entries.get(character_id) is not entry:
            return False
        del self._entries[character_id]
        return True
