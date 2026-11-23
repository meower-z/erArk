"""前端指令输入框的本地历史记录与上下键浏览管理模块。"""

HISTORY_LIMIT = 21
"""输入历史列表最多保留的记录条数。"""


class InputHistory:
    """管理最近提交的非空输入列表，支持上下方向键跳过连续重复项浏览历史并在回到末尾时恢复草稿。"""

    def __init__(self) -> None:
        """
        初始化空的历史记录列表与默认非浏览状态

        参数：无

        返回值类型：None
        """
        self.entries: list[str] = []
        """按提交先后顺序保存的非空历史输入列表。"""
        self._position = 0
        self._draft = ""
        self._browsing = False

    def remember(self, text: str) -> None:
        """
        将非空文本追加到历史末尾并在超出上限时淘汰最早记录，同时重置浏览状态与暂存草稿

        参数：
        text (str) -- 本次提交的输入文本

        返回值类型：None
        """
        if text != "":
            if len(self.entries) >= HISTORY_LIMIT:
                del self.entries[0]
            self.entries.append(text)
            self._position = 0
        self._draft = ""
        self._browsing = False

    def older(self, current: str) -> str | None:
        """
        向更早的历史移动一步并跳过连续重复项，首次开始浏览时暂存当前输入框草稿

        参数：
        current (str) -- 开始浏览前输入框中的当前文本

        返回值类型：str | None -- 命中的更早历史文本，无更早记录时返回 None
        """
        entries = self.entries
        if not entries:
            return None
        if not self._browsing:
            self._draft = current
            self._browsing = True
            self._position = len(entries)
        self._position = min(self._position, len(entries))
        if self._position == len(entries):
            self._position -= 1
            return entries[self._position]
        if self._position > 0:
            index = self._position - 1
            while index >= 0 and entries[index] == entries[self._position]:
                index -= 1
            if index >= 0:
                self._position = index
                return entries[index]
        return None

    def newer(self) -> str | None:
        """
        向更新的历史移动一步并跳过连续重复项，越过最新记录时恢复暂存草稿并结束浏览

        参数：无

        返回值类型：str | None -- 命中的更新历史或草稿文本，未在浏览或无记录时返回 None
        """
        entries = self.entries
        if not entries or not self._browsing:
            return None
        if self._position < len(entries) - 1:
            index = self._position + 1
            while (
                index < len(entries)
                and entries[index] == entries[self._position]
            ):
                index += 1
            if index < len(entries):
                self._position = index
                return entries[index]
        if self._position == len(entries) - 1:
            self._position = 0
            self._browsing = False
            draft, self._draft = self._draft, ""
            return draft
        return None
