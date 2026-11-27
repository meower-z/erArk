"""
前端重连屏幕投影模块。
提供 Projection 类，增量维护有界的样式、背景、面板与屏幕指令状态以生成接入快照。
"""

import dataclasses
from collections import Counter
from collections.abc import Callable, Iterable

from Script.Protocol.messages import (
    BackendEvent,
    BgColorOp,
    ButtonOp,
    Clear,
    ClearButtonsOp,
    ImageButtonOp,
    RenderChunk,
    RenderOp,
    StyleDefOp,
    SyncPanel,
    TextOp,
)

RETAINED_TEXT_OPS = 2000
RETAINED_CONTROL_OPS = 1000


class Projection:
    """
    维护可供前端重连恢复的有界屏幕投影状态。
    保留各样式名最新 StyleDefOp、最新 BgColorOp、最新 SyncPanel，
    以及最近一次清屏后的 RenderChunk。
    处理 Clear("buttons") 与 ClearButtonsOp 时直接移除对应留存按钮，
    不保留按钮清理事件本身与 Clear("input")。
    文本指令超 4000 条时裁旧至 2000 条，按钮与图片等非文本指令超 2000 条时裁旧至 1000 条，
    两类上限分别计算且互不挤占。
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._styles: dict[str, StyleDefOp] = {}
        self._background: BgColorOp | None = None
        self._looks_seq = 0
        self._panel: SyncPanel | None = None
        self._screen: list[RenderChunk] = []
        self._texts = 0
        self._controls = 0
        self._buttons: Counter[str] = Counter()

    def record(self, event: BackendEvent) -> None:
        """
        按后端事件增量更新屏幕投影，并按文本与非文本上限分别裁剪旧指令。
        该方法在清屏时清空留存块，在清按钮时移除对应留存按钮，
        并忽略 Clear("input")、输入请求、SkipPauses 与退出事件。

        参数：
        event (BackendEvent) -- 刚发布的后端事件

        返回值：None
        """
        match event:
            case RenderChunk():
                self._record_chunk(event)
            case Clear(target="screen"):
                self._screen.clear()
                self._count()
            case Clear(target="buttons"):
                self._drop_buttons(None)
            case SyncPanel():
                self._panel = event

    def snapshot(self) -> tuple[RenderChunk | Clear | SyncPanel, ...]:
        """
        按样式与背景汇总块、最新面板同步事件、留存屏幕事件的顺序生成重连快照序列。

        参数：无

        返回值：tuple[RenderChunk | Clear | SyncPanel, ...] -- 供前端按序重放以恢复界面的事件元组
        """
        head: list[RenderChunk | Clear | SyncPanel] = []
        looks: list[RenderOp] = [*self._styles.values()]
        if self._background is not None:
            looks.append(self._background)
        if looks:
            head.append(
                RenderChunk(self._session_id, self._looks_seq, tuple(looks))
            )
        if self._panel is not None:
            head.append(self._panel)
        return (*head, *self._screen)

    def _record_chunk(self, chunk: RenderChunk) -> None:
        kept: list[RenderOp] = []
        for op in chunk.ops:
            match op:
                case StyleDefOp():
                    self._styles[op.name] = op
                    self._looks_seq = chunk.seq
                case BgColorOp():
                    self._background = op
                    self._looks_seq = chunk.seq
                case ClearButtonsOp():
                    self._append(chunk, kept)
                    kept = []
                    self._drop_buttons(op.command_ids)
                case _:
                    kept.append(op)
        self._append(chunk, kept)
        if self._texts > 2 * RETAINED_TEXT_OPS:
            self._drop_oldest(_is_text, self._texts - RETAINED_TEXT_OPS)
        if self._controls > 2 * RETAINED_CONTROL_OPS:
            excess = self._controls - RETAINED_CONTROL_OPS
            self._drop_oldest(_is_control, excess)

    def _append(self, chunk: RenderChunk, ops: list[RenderOp]) -> None:
        if ops:
            self._screen.append(dataclasses.replace(chunk, ops=tuple(ops)))
            texts = sum(map(_is_text, ops))
            self._texts += texts
            self._controls += len(ops) - texts
            self._buttons.update(_button_ids(ops))

    def _drop_buttons(self, command_ids: tuple[str, ...] | None) -> None:
        stale = set(self._buttons if command_ids is None else command_ids)
        left = sum(self._buttons.pop(command, 0) for command in stale)
        index = len(self._screen)
        while left and index:
            index -= 1
            chunk = self._screen[index]
            ops = tuple(
                op
                for op in chunk.ops
                if not isinstance(op, ButtonOp | ImageButtonOp)
                or op.command_id not in stale
            )
            dropped = len(chunk.ops) - len(ops)
            left -= dropped
            self._controls -= dropped
            if not ops:
                del self._screen[index]
            elif dropped:
                self._screen[index] = dataclasses.replace(chunk, ops=ops)

    def _drop_oldest(
        self, kind: Callable[[RenderOp], bool], excess: int
    ) -> None:
        left = [excess]

        def keep(op: RenderOp) -> bool:
            if left[0] and kind(op):
                left[0] -= 1
                return False
            return True

        self._keep(keep)

    def _keep(self, keep: Callable[[RenderOp], bool]) -> None:
        screen: list[RenderChunk] = []
        for chunk in self._screen:
            ops = tuple(op for op in chunk.ops if keep(op))
            if ops:
                screen.append(dataclasses.replace(chunk, ops=ops))
        self._screen = screen
        self._count()

    def _count(self) -> None:
        ops = [op for chunk in self._screen for op in chunk.ops]
        self._texts = sum(map(_is_text, ops))
        self._controls = len(ops) - self._texts
        self._buttons = Counter(_button_ids(ops))


def _is_text(op: RenderOp) -> bool:
    return isinstance(op, TextOp)


def _is_control(op: RenderOp) -> bool:
    return not isinstance(op, TextOp)


def _button_ids(ops: Iterable[RenderOp]) -> list[str]:
    return [
        op.command_id for op in ops if isinstance(op, ButtonOp | ImageButtonOp)
    ]
