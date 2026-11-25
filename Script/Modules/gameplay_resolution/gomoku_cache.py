"""
五子棋缓存与哈希（gomoku_cache）
================================
提供定容缓存 Gomoku_Cache 与 64 位局面哈希器 ZobristCache。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING

from Script.Modules.gameplay_resolution.gomoku_shapes import config

if TYPE_CHECKING:
    from typing import Any


class Gomoku_Cache:
    """按写入顺序淘汰最早键的定容缓存，受 config 缓存开关控制。"""

    def __init__(self, capacity: int = 1000000) -> None:
        """
        初始化缓存对象
        Keyword arguments:
        capacity -- 最多保存的键数 (default 1000000)
        """
        self.capacity = capacity
        self.gomoku_cache: deque[int] = deque()
        self.map: dict[int, Any] = {}

    def get(self, key: int) -> Any:
        """
        读取缓存中某个键的值
        Keyword arguments:
        key -- 要查询的键
        Return arguments:
        object -- 键对应的值，键不存在时为 None，缓存开关关闭时为 False
        """
        if not config["enable_cache"]:
            return False
        return self.map.get(key, None)

    def put(self, key: int, value: object) -> bool | None:
        """
        缓存开关打开时写入或更新某个键的值
        Keyword arguments:
        key -- 要写入的键
        value -- 要写入的值
        Return arguments:
        bool | None -- 缓存开关关闭时为 False，否则为 None
        """
        if not config["enable_cache"]:
            return False
        if len(self.gomoku_cache) >= self.capacity:
            oldest_key = self.gomoku_cache.popleft()
            del self.map[oldest_key]

        if key not in self.map:
            self.gomoku_cache.append(key)
        self.map[key] = value
        return None


class ZobristCache:
    """用外部随机源生成 64 位键表并维护棋盘异或哈希的哈希器。"""

    def __init__(self, size: int, rng: random.Random) -> None:
        """
        初始化 Zobrist 哈希表并将当前哈希置零
        Keyword arguments:
        size -- 棋盘边长
        rng -- 用于生成 64 位随机键的 random.Random 实例
        """
        self.size = size
        self.rng = rng
        self.zobrist_table = self.initialize_zobrist_table(size)
        self.hash = 0

    def initialize_zobrist_table(self, size: int) -> list[list[dict[int, int]]]:
        """
        为棋盘每个位置生成双方的随机哈希值
        Keyword arguments:
        size -- 棋盘边长
        Return arguments:
        list -- 二维哈希表
        """
        table = []
        for _i in range(size):
            row = []
            for _j in range(size):
                row.append(
                    {
                        1: self.random_bit_string(64),
                        -1: self.random_bit_string(64),
                    }
                )
            table.append(row)
        return table

    def random_bit_string(self, length: int) -> int:
        """
        把 length 位随机二进制串转成整数
        Keyword arguments:
        length -- 二进制串的位数
        Return arguments:
        int -- 转成的整数
        """
        return self.rng.getrandbits(length)

    def toggle_piece(self, x: int, y: int, role: int) -> None:
        """
        把某位置某一方棋子的哈希值异或进当前哈希
        Keyword arguments:
        x -- 行号
        y -- 列号
        role -- 棋子方，1 或 -1
        """
        self.hash ^= self.zobrist_table[x][y][role]

    def get_hash(self) -> int:
        """
        获取当前哈希值
        Return arguments:
        int -- 哈希值
        """
        return self.hash
