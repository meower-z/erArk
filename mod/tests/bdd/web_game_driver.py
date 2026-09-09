#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Web模式端到端游戏驱动器

通过真实启动 game.py（web_draw=1），用 HTTP API + SocketIO 驱动一局真实游戏会话：
点击按钮、输入文本、执行指令、应答结算/事件弹窗、读取界面状态。
这是 BDD 场景（openspec bdd-scenarios.md）的执行基础，不 mock 任何 Script 模块。

依赖（仅测试环境需要）：requests、python-socketio[client]（游戏本体 requirements 已含 python-socketio 服务端）。
"""

import configparser
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

import requests
import socketio

# 端口发现输出行样式，来自 Script/Core/web_server.py 与 Werkzeug 的启动日志
_PORT_PATTERNS = [
    re.compile(r"已找到可用端口[:：]\s*(\d+)"),
    re.compile(r"https?://(?:localhost|127\.0\.0\.1):(\d+)"),
]
# 主场景新UI容器元素类型，出现即代表已进入 IN_SCENE 主循环
_NEW_UI_CONTAINER = "new_ui_container"


def _extract_port_from_line(line: str) -> Optional[int]:
    """
    从启动日志行中提取 Web 服务端口

    参数:
    line (str): 子进程输出的一行日志

    返回值类型：Optional[int]，无法识别时为 None
    功能描述：兼容中文端口发现日志与 Flask/Werkzeug 的 ASCII URL 日志。
    """
    for pattern in _PORT_PATTERNS:
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    return None


class DriverError(RuntimeError):
    """驱动器错误：启动失败、超时、协议异常等"""


class WebGameDriver:
    """
    真实游戏进程的 Web 模式驱动器

    功能描述：负责游戏子进程生命周期（启动/停止/日志收集）、HTTP 输入通道
    （按钮点击/等待应答/字符串与整数输入）、SocketIO 事件通道（指令执行、
    结算按钮、事件选项、对话推进）以及状态轮询断言辅助。
    """

    def __init__(self, repo_root: str, python_exe: Optional[str] = None, boot_timeout: float = 120.0):
        """
        初始化驱动器

        参数:
        repo_root (str): 游戏仓库根目录（game.py 所在目录）
        python_exe (Optional[str]): 用于启动游戏的解释器路径，默认取当前解释器
        boot_timeout (float): 启动并等待 Web API 就绪的超时秒数

        返回值类型：无
        """
        self.repo_root = os.path.abspath(repo_root)
        self.python_exe = python_exe or sys.executable
        self.boot_timeout = boot_timeout
        self.process: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.base_url: Optional[str] = None
        self.stdout_lines: List[str] = []
        self._stdout_thread: Optional[threading.Thread] = None
        self._config_backup: Optional[str] = None
        self._error_log_offset: int = 0
        # SocketIO 客户端与其收到的最近事件缓存
        self.sio: Optional[socketio.Client] = None
        self._sio_lock = threading.Lock()
        self.last_settlement_buttons: Optional[dict] = None
        self.last_event_options: Optional[dict] = None
        self.last_instruct_result: Optional[dict] = None
        self.sio_events: List[dict] = []

    # ------------------------------------------------------------------
    # 进程生命周期
    # ------------------------------------------------------------------

    def _ensure_web_mode(self):
        """
        确保 config.ini 的 web_draw=1（保留原始内容以便停止时还原）

        返回值类型：无
        功能描述：读取 config.ini，若 web_draw 不为 1 则临时改写；原始文本保存在
        self._config_backup，stop() 时恢复，避免污染用户配置。
        """
        config_path = os.path.join(self.repo_root, "config.ini")
        with open(config_path, "r", encoding="utf-8") as f:
            original = f.read()
        parser = configparser.ConfigParser()
        parser.read_string(original)
        section = parser.sections()[0] if parser.sections() else "game"
        if parser.get(section, "web_draw", fallback="0") != "1":
            self._config_backup = original
            new_text = re.sub(r"^(\s*web_draw\s*=\s*)\d+", r"\g<1>1", original, count=1, flags=re.M)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(new_text)

    def _restore_config(self):
        """
        还原被临时改写的 config.ini

        返回值类型：无
        """
        if self._config_backup is not None:
            config_path = os.path.join(self.repo_root, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(self._config_backup)
            self._config_backup = None

    def _pump_stdout(self):
        """
        后台线程：持续读取游戏进程 stdout 行并缓存

        返回值类型：无
        功能描述：既用于解析实际监听端口，也在失败时提供启动日志证据。
        """
        assert self.process is not None and self.process.stdout is not None
        for raw in self.process.stdout:
            line = raw.rstrip("\n")
            self.stdout_lines.append(line)

    def start(self):
        """
        启动游戏子进程并等待 Web API 就绪

        返回值类型：无
        功能描述：改写 web_draw、记录 error.log 偏移、启动 game.py、解析端口、
        轮询 /api/get_state 直至标题面板可用，随后建立 SocketIO 连接。
        """
        self._ensure_web_mode()
        error_log = os.path.join(self.repo_root, "error.log")
        self._error_log_offset = os.path.getsize(error_log) if os.path.exists(error_log) else 0
        self.process = subprocess.Popen(
            [self.python_exe, "game.py"],
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self._stdout_thread = threading.Thread(target=self._pump_stdout, daemon=True)
        self._stdout_thread.start()

        deadline = time.time() + self.boot_timeout
        # 第一步：从启动日志中解析实际端口
        while time.time() < deadline and self.port is None:
            for line in list(self.stdout_lines):
                port = _extract_port_from_line(line)
                if port is not None:
                    self.port = port
                    break
            if self.process.poll() is not None:
                raise DriverError("游戏进程提前退出:\n" + "\n".join(self.stdout_lines[-40:]))
            time.sleep(0.2)
        if self.port is None:
            raise DriverError("超时未发现Web端口:\n" + "\n".join(self.stdout_lines[-40:]))
        self.base_url = f"http://127.0.0.1:{self.port}"
        # 第二步：等待标题面板的按钮出现在状态里
        while time.time() < deadline:
            try:
                state = self.get_state()
                if state.get("buttons"):
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        else:
            raise DriverError("超时未等到标题面板")
        self._connect_socketio()

    def _connect_socketio(self):
        """
        建立 SocketIO 客户端连接并注册事件缓存回调

        返回值类型：无
        功能描述：缓存 settlement_buttons / event_options 弹窗的最近负载，
        供 auto_advance 与场景断言使用。
        """
        self.sio = socketio.Client(reconnection=True)

        @self.sio.on("settlement_buttons")
        def _on_settlement(data):
            with self._sio_lock:
                self.last_settlement_buttons = data
                self.sio_events.append({"event": "settlement_buttons", "data": data})

        @self.sio.on("event_options")
        def _on_event_options(data):
            with self._sio_lock:
                self.last_event_options = data
                self.sio_events.append({"event": "event_options", "data": data})

        @self.sio.on("instruct_executed")
        def _on_instruct_executed(data):
            with self._sio_lock:
                self.last_instruct_result = data
                self.sio_events.append({"event": "instruct_executed", "data": data})

        self.sio.connect(self.base_url, wait_timeout=15)

    def stop(self):
        """
        停止游戏进程并清理

        返回值类型：无
        功能描述：断开 SocketIO、终止子进程（先 terminate 后 kill）、还原 config.ini。
        """
        if self.sio is not None:
            try:
                self.sio.disconnect()
            except Exception:
                pass
            self.sio = None
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process = None
        self._restore_config()

    def new_error_log_text(self) -> str:
        """
        读取自 start() 以来 error.log 新增的内容

        返回值类型：str
        功能描述：BDD 断言"运行期间无异常写入"用；文件不存在时返回空串。
        """
        error_log = os.path.join(self.repo_root, "error.log")
        if not os.path.exists(error_log):
            return ""
        with open(error_log, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self._error_log_offset)
            return f.read()

    # ------------------------------------------------------------------
    # HTTP 输入通道
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """
        获取当前游戏状态快照

        返回值类型：dict
        功能描述：GET /api/get_state，包含 text_content/buttons/panel_id/input_request 等。
        """
        resp = requests.get(f"{self.base_url}/api/get_state", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def click(self, button_id: str):
        """
        点击按钮（对应 askfor_all 的按钮响应）

        参数:
        button_id (str): 按钮的 return_text / id

        返回值类型：无
        """
        resp = requests.post(f"{self.base_url}/api/button_click", json={"button_id": str(button_id)}, timeout=10)
        resp.raise_for_status()

    def wait_response(self):
        """
        应答一次"任意键继续"等待（askfor_wait）

        返回值类型：无
        """
        resp = requests.post(f"{self.base_url}/api/wait_response", json={}, timeout=10)
        resp.raise_for_status()

    def input_string(self, value: str):
        """
        提交字符串输入（askfor_str）

        参数:
        value (str): 输入内容

        返回值类型：无
        """
        resp = requests.post(f"{self.base_url}/api/string_input", json={"value": value}, timeout=10)
        resp.raise_for_status()

    def input_integer(self, value: int):
        """
        提交整数输入（askfor_int）

        参数:
        value (int): 输入内容

        返回值类型：无
        """
        resp = requests.post(f"{self.base_url}/api/integer_input", json={"value": value}, timeout=10)
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # SocketIO 通道
    # ------------------------------------------------------------------

    def execute_instruct(self, instruct_id: str):
        """
        通过 SocketIO 执行游戏指令（触发行为结算主循环的正规路径）

        参数:
        instruct_id (str): constant.Instruct 中的指令 id

        返回值类型：无
        """
        assert self.sio is not None
        with self._sio_lock:
            self.last_instruct_result = None
        self.sio.emit("execute_instruct", {"instruct_id": instruct_id})

    def game_time_text(self, state: Optional[dict] = None) -> str:
        """
        读取主场景信息栏中的游戏时间文本

        参数:
        state (Optional[dict]): 已有状态快照

        返回值类型：str，未在主场景时为空串
        """
        scene = self.in_scene_state(state)
        if not scene:
            return ""
        return ((scene.get("scene_info_bar") or {}).get("game_time")) or ""

    def run_instruct(self, instruct_id: str, timeout: float = 120.0, expect_time_advance: bool = True) -> dict:
        """
        执行指令并等待其结算完成

        参数:
        instruct_id (str): constant.Instruct 中的指令 id
        timeout (float): 等待结算完成的超时秒数
        expect_time_advance (bool): 是否要求游戏时间前进后才视为完成

        返回值类型：dict，instruct_executed 事件负载
        功能描述：发出指令后循环应答等待元素/结算弹窗/事件弹窗，直到收到
        instruct_executed 事件且（若要求）游戏时间前进。指令执行失败
        （success=False）时抛出 DriverError。
        """
        before_time = self.game_time_text()
        self.execute_instruct(instruct_id)
        deadline = time.time() + timeout
        result: Optional[dict] = None
        while time.time() < deadline:
            self.auto_advance(rounds=5)
            with self._sio_lock:
                result = self.last_instruct_result
            if result is not None and not result.get("success", False):
                raise DriverError(f"指令执行失败: {instruct_id}: {result}")
            if result is not None:
                if not expect_time_advance:
                    return result
                now_time = self.game_time_text()
                if now_time and now_time != before_time:
                    return result
            time.sleep(0.4)
        raise DriverError(
            f"指令结算超时: {instruct_id}; instruct_executed={result}; "
            f"time {before_time!r} -> {self.game_time_text()!r}"
        )

    def click_panel_tab(self, tab_id: str):
        """
        点击主界面面板选项卡（打开子面板类指令）

        参数:
        tab_id (str): 面板类指令 id

        返回值类型：无
        """
        assert self.sio is not None
        self.sio.emit("click_panel_tab", {"tab_id": tab_id})

    def switch_target(self, character_id: int):
        """
        切换交互对象

        参数:
        character_id (int): 目标角色 id

        返回值类型：无
        """
        assert self.sio is not None
        self.sio.emit("switch_target", {"character_id": character_id})

    def settlement_select(self, return_text: str):
        """
        应答结算选项弹窗

        参数:
        return_text (str): 目标按钮的 return_text

        返回值类型：无
        """
        assert self.sio is not None
        with self._sio_lock:
            self.last_settlement_buttons = None
        self.sio.emit("settlement_button_selected", {"return_text": return_text})

    def event_option_select(self, option: dict):
        """
        应答事件选项弹窗

        参数:
        option (dict): event_options 负载中的一个选项（含 id/event_id 等字段）

        返回值类型：无
        """
        assert self.sio is not None
        with self._sio_lock:
            self.last_event_options = None
        self.sio.emit("event_option_selected", option)

    def advance_dialog(self):
        """
        推进主对话框一页

        返回值类型：无
        """
        assert self.sio is not None
        self.sio.emit("advance_dialog", {})

    def skip_all_dialogs(self):
        """
        跳过全部排队对话

        返回值类型：无
        """
        assert self.sio is not None
        self.sio.emit("skip_all_dialogs", {})

    # ------------------------------------------------------------------
    # 状态查询与轮询辅助
    # ------------------------------------------------------------------

    def buttons(self, state: Optional[dict] = None) -> List[dict]:
        """
        列出当前状态中的按钮

        参数:
        state (Optional[dict]): 已有状态快照；缺省则重新拉取

        返回值类型：List[dict]，每项含 id/text/style
        """
        state = state or self.get_state()
        return state.get("buttons") or []

    def find_button(self, pattern: str, state: Optional[dict] = None) -> Optional[dict]:
        """
        按文本正则查找按钮

        参数:
        pattern (str): 作用于按钮文本的正则表达式
        state (Optional[dict]): 已有状态快照

        返回值类型：Optional[dict]
        """
        regex = re.compile(pattern)
        for btn in self.buttons(state):
            if regex.search(btn.get("text") or ""):
                return btn
        return None

    def click_button_matching(self, pattern: str, timeout: float = 20.0) -> dict:
        """
        等待并点击文本匹配的按钮

        参数:
        pattern (str): 按钮文本正则
        timeout (float): 等待按钮出现的超时秒数

        返回值类型：dict，被点击的按钮
        功能描述：轮询状态直到按钮出现，随后 POST 其 id。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            btn = self.find_button(pattern)
            if btn is not None:
                self.click(btn["id"])
                return btn
            time.sleep(0.3)
        raise DriverError(f"等待按钮超时: {pattern}\n当前按钮: {[b.get('text') for b in self.buttons()]}")

    def wait_until(self, predicate: Callable[[dict], bool], timeout: float = 30.0, interval: float = 0.3) -> dict:
        """
        轮询状态直到谓词为真

        参数:
        predicate (Callable[[dict], bool]): 状态谓词
        timeout (float): 超时秒数
        interval (float): 轮询间隔秒数

        返回值类型：dict，使谓词为真的状态快照
        """
        deadline = time.time() + timeout
        last_state: dict = {}
        while time.time() < deadline:
            last_state = self.get_state()
            if predicate(last_state):
                return last_state
            time.sleep(interval)
        raise DriverError(f"wait_until 超时; 最后按钮: {[b.get('text') for b in (last_state.get('buttons') or [])]}; input_request={last_state.get('input_request')}")

    def in_scene_state(self, state: Optional[dict] = None) -> Optional[dict]:
        """
        提取主场景新UI容器内的 game_state

        参数:
        state (Optional[dict]): 已有状态快照

        返回值类型：Optional[dict]，未进入主场景时为 None
        功能描述：主场景绘制时会推送 type=new_ui_container 的元素，其 game_state
        字段含场景信息栏/玩家信息/交互对象信息等，是 BDD 断言的主要数据源。
        """
        state = state or self.get_state()
        for elem in state.get("text_content") or []:
            if isinstance(elem, dict) and elem.get("type") == _NEW_UI_CONTAINER:
                return elem.get("game_state")
        return None

    def has_wait_element(self, state: Optional[dict] = None) -> bool:
        """
        判断当前是否存在等待点击的 wait 元素

        参数:
        state (Optional[dict]): 已有状态快照

        返回值类型：bool
        """
        state = state or self.get_state()
        for elem in state.get("text_content") or []:
            if isinstance(elem, dict) and elem.get("type") in {"wait", "line_wait"}:
                return True
        return False

    def visible_text(self, state: Optional[dict] = None) -> str:
        """
        拼接当前状态的可见文本（便于断言与调试）

        参数:
        state (Optional[dict]): 已有状态快照

        返回值类型：str
        """
        state = state or self.get_state()
        parts: List[str] = []
        for elem in state.get("text_content") or []:
            if isinstance(elem, dict):
                text = elem.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    # ------------------------------------------------------------------
    # 高层流程辅助
    # ------------------------------------------------------------------

    def auto_advance(self, rounds: int = 10, settle_chooser: Optional[Callable[[dict], str]] = None):
        """
        自动推进：应答等待元素、结算弹窗、事件弹窗与排队对话

        参数:
        rounds (int): 最多处理的推进轮数
        settle_chooser (Optional[Callable[[dict], str]]): 结算弹窗按钮选择器，
            缺省选第一个按钮的 return_text

        返回值类型：无
        功能描述：结算主循环中会出现 wait 元素/结算按钮/事件选项；本方法逐轮
        检查并按缺省策略应答，让流程走到下一个稳定面板。
        """
        for _ in range(rounds):
            acted = False
            with self._sio_lock:
                settlement = self.last_settlement_buttons
                event_opts = self.last_event_options
            if settlement and settlement.get("visible") and settlement.get("buttons"):
                chooser = settle_chooser or (lambda payload: payload["buttons"][0]["return_text"])
                self.settlement_select(chooser(settlement))
                acted = True
            elif event_opts and event_opts.get("visible") and event_opts.get("options"):
                self.event_option_select(event_opts["options"][0])
                acted = True
            elif self.has_wait_element():
                self.wait_response()
                acted = True
            if not acted:
                return
            time.sleep(0.4)

    def wait_main_scene(self, timeout: float = 120.0) -> dict:
        """
        推进流程直到主场景容器出现

        参数:
        timeout (float): 超时秒数

        返回值类型：dict，主场景 new_ui_container 的 game_state
        功能描述：循环应答"返回/回到游戏/继续"按钮与 wait 元素（开局成就面板、
        读档迁移提示等），直到 type=new_ui_container 元素出现。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.get_state()
            scene = self.in_scene_state(state)
            if scene is not None:
                return scene
            btn = self.find_button(r"^返回$|回到游戏|继续", state)
            if btn is not None:
                self.click(btn["id"])
            elif self.has_wait_element(state):
                self.wait_response()
            time.sleep(0.5)
        raise DriverError("等待主场景超时")

    def load_save(self, slot: str, timeout: float = 120.0) -> dict:
        """
        从标题画面读取指定存档槽位直至进入主场景

        参数:
        slot (str): 存档槽位目录名（"0"~"99" 或 "auto"）
        timeout (float): 整个流程的超时秒数

        返回值类型：dict，进入主场景后的 new_ui_container game_state
        功能描述：标题[001]神经重载 -> 分页查找文本含 No.<slot> 的存档按钮
        （必要时翻页）-> [000]读取 -> [000]确认读取存档 -> 等待主场景容器。
        跨版本存档会在读取时执行迁移，因此超时需给足。
        """
        slot = str(slot)
        self.click_button_matching(r"神经重载")
        # 存档按钮文本形如 "No.<slot> <版本> 游戏时间:..."，据此跨页定位；
        # 自动存档行（No.auto）在每页顶部都会绘制，可作为列表就绪标志
        slot_pattern = rf"No\.{re.escape(slot)}\s"
        self.wait_until(lambda s: self.find_button(r"No\.", s) is not None, timeout=30)
        found = False
        for _ in range(12):
            # 当前页内轮询查找目标槽位（页面重绘需要时间）
            page_deadline = time.time() + 3.0
            btn = None
            while time.time() < page_deadline:
                btn = self.find_button(slot_pattern)
                if btn is not None:
                    break
                time.sleep(0.3)
            if btn is not None:
                self.click(btn["id"])
                found = True
                break
            next_btn = self.find_button(r"下一页")
            if next_btn is None:
                raise DriverError(f"存档列表中未找到槽位 {slot} 且无下一页按钮")
            self.click(next_btn["id"])
        if not found:
            raise DriverError(f"翻页后仍未找到槽位 {slot}")
        # 存档操作子菜单：读取 -> 二次确认
        self.click_button_matching(r"读取", timeout=15)
        self.click_button_matching(r"确认读取存档", timeout=15)
        return self.wait_main_scene(timeout=timeout)

    def new_game(self, player_name: str = "Doctor", enable_debug: bool = True, timeout: float = 120.0) -> dict:
        """
        从标题画面开新档直至进入主场景

        参数:
        player_name (str): 玩家名
        enable_debug (bool): 是否在创建角色时开启 debug 模式（要求 config.ini debug=1）
        timeout (float): 整个流程的超时秒数

        返回值类型：dict，进入主场景后的 new_ui_container game_state
        功能描述：标题[000]初次唤醒 -> 免责声明确认 -> 姓名输入 -> （可选）开启
        debug -> 确认"睁开双眼" -> 应答开局等待/成就面板 -> 等待主场景容器出现。
        """
        deadline = time.time() + timeout
        # 标题面板：初次唤醒
        self.click_button_matching(r"初次唤醒")
        # 免责声明确认（按钮文本含"我读完并理解"）
        self.click_button_matching(r"我读完并理解|理解了以上")
        # 姓名输入：等待 input_request 出现
        self.wait_until(lambda s: (s.get("input_request") or {}).get("type") == "string", timeout=30)
        self.input_string(player_name)
        # 创建面板：可选开启 debug 模式
        if enable_debug:
            try:
                self.click_button_matching(r"开启debug模式", timeout=15)
            except DriverError:
                # config.ini debug=0 时该按钮不存在，忽略
                pass
        # 确认创建：睁开双眼
        self.click_button_matching(r"睁开双眼", timeout=30)
        # 开局阶段可能有成就面板/等待元素/对话，循环推进直到主场景容器出现
        while time.time() < deadline:
            state = self.get_state()
            scene = self.in_scene_state(state)
            if scene is not None:
                return scene
            btn = self.find_button(r"^返回$|回到游戏|继续", state)
            if btn is not None:
                self.click(btn["id"])
            elif self.has_wait_element(state):
                self.wait_response()
            time.sleep(0.5)
        raise DriverError("开新档超时，未进入主场景")
