# -*- coding: UTF-8 -*-
"""
测试用的游戏世界夹具
====================
MinimalWorld -- 小世界：读一次真实游戏配置，造出空的游戏状态，测试之间一键复原；不启动游戏。快速层（tests/fast）用它。
FullWorld    -- 完整的无头启动：小世界之外再载入结算器、状态机与界面流程，不复原；
慢速层（tests/slow）用它，每个进程开一局新游戏。

测试向世界要角色、位置和场景：
    world.chara(cid, name, position=...)   -- 造一个穿着衣服、各异常位正常的角色，并当场核对
    world.chara(cid, name, naked=True)     -- 要裸体角色必须写明，当场核对她全裸
    world.scene(path) / world.move(cid, path)
FullWorld 另有：
    world.new_game()                       -- 走一遍开新游戏的界面流程
    world.player.press(...) / type(...)    -- 安排玩家接下来按的按钮与输入的文字（PlayerInput）

每次复原都重设全部随机源（random、numpy.random、uuid.uuid4），见 seed_everything。
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import io
import os
import random
import sys
import uuid
from typing import TYPE_CHECKING

from tests import chara_abilities as ca, chara_data, kernel_data, outside_cache
from tests.chara_activity import place
from tests.kernel_project import activity
from tests.kernel_project import identity

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Self

    from Script.Core import game_type
    from Script.Protocol import BackendEvent, RenderOp, ScriptedUiPort
    from Script.Protocol import UiRequest, UiResponse
    from Script.UI.Moudle import draw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
""" erArk 仓库根目录 """

SEED = 20260719
""" 全部随机源的固定种子，与 PYTHONHASHSEED 的固定值相同 """

START_TIME = (2020, 12, 22, 10, 0)
""" 复原后的游戏时间（年、月、日、时、分），不读 config.ini 的开局时间 """

DEFAULT_SCENE = ["宿舍", "1区", "101"]
""" chara() 不给位置时的默认场景：一间真实宿舍 """

STANDARD_OUTFIT = {5: [501], 6: [651], 9: [951], 11: [1101]}
""" 默认穿的衣服，衣物类型: 衣服id 列表：罗德岛制服夹克、纯白色胸罩、纯白色内裤、深蓝色小皮鞋 """


class FixtureError(AssertionError):
    """夹具造出的状态不符合承诺（例如默认角色不是全部正常）时抛出"""


_uuid_rng = random.Random(SEED)
""" 确定性 uuid4 用的随机源，seed_everything 重设它 """


def _seeded_uuid4() -> uuid.UUID:
    """
    确定性的 uuid4：由固定种子的随机源生成，替换 uuid.uuid4
    Keyword arguments:
    无
    Return arguments:
    uuid.UUID -- 第 4 版 UUID
    """
    return uuid.UUID(int=_uuid_rng.getrandbits(128), version=4)


def seed_everything(seed: int = SEED) -> None:
    """
    重设全部随机源：random、numpy.random，以及替换后的 uuid.uuid4
    Keyword arguments:
    seed -- 种子
    Return arguments:
    无
    功能描述:
        游戏代码里的随机来自 random（大量）、numpy.random（value_handle.get_gauss_rand）与 uuid.uuid4（食物 uid）。
        PYTHONHASHSEED 只能在解释器启动前设定，由 tests/conftest.py 处理。
        环境变量 ERARK_KEYED_RANDOM=1 时再换上按行为结算键控的随机流（tests/keyed_random.py）。
    """
    import numpy

    random.seed(seed)
    numpy.random.seed(seed % (2**32))
    _uuid_rng.seed(seed)
    uuid.uuid4 = _seeded_uuid4
    if os.environ.get("ERARK_KEYED_RANDOM") == "1":
        from tests import keyed_random

        keyed_random.install(seed, _uuid_rng)


def set_clock(dt: datetime.datetime) -> None:
    """
    把内核时钟拨到 dt（经 core.reset_state，角色与全局数据不变）
    Keyword arguments:
    dt -- 新的游戏时间
    Return arguments:
    无
    """
    from dataclasses import replace

    from Script.Design import game_time
    from Script.Kernel import core

    core.reset_state(replace(core.state(), clock=game_time.minutes(dt)))


def start_time() -> datetime.datetime:
    """
    复原后的游戏时间：START_TIME 规整到游戏日历上
    Keyword arguments:
    无
    Return arguments:
    GameTime -- 游戏时间
    """
    from Script.Design import game_time

    return game_time.to_game_time(datetime.datetime(*START_TIME))


_left: object = None
""" 上一次 act 停下时的 GameState """


def act(fn: Callable[[], None]) -> None:
    """
    玩家做一个行动：内核一步一步推进，到玩家选行动时跑一次 fn，再推进到玩家下一次选行动时停下。
    fn 经 player_pick.choose 定下的行动随即开始。fn 没有定下行动就返回时（例如打开又退出一个面板），act 立即停下。
    内核状态不是上一次 act 停下时的那个时（例如世界刚复原、读档或拨过时钟），先用 kernel_data.reprojected
    重新投影各角色的行动，时钟不变，每个角色的数据跟着这个角色走（去掉 open）。一个测试里可以连着调用。
    Keyword arguments:
    fn -- 玩家选行动时跑的操作（无参数的函数），例如一条指令或一次寻路
    Return arguments:
    无
    """
    from Script.Kernel import core
    from Script.Modules import load_order
    from Script.Modules.tk_ui import player_pick

    ran = False

    def chooser() -> None:
        """玩家的选择：第一次跑 fn，之后（或 fn 没有定下行动时）结束脚本"""
        nonlocal ran
        if not ran:
            ran = True
            fn()
        raise player_pick.LeftGame

    global _left
    core.load(load_order.LOAD_ORDER)
    game = core.state()
    if game is not _left:
        core.reset_state(kernel_data.reprojected(game))
    saved, player_pick.chooser = player_pick.chooser, chooser
    try:
        while True:
            core.step()
    except player_pick.LeftGame:
        _left = core.state()
    finally:
        player_pick.chooser = saved


play = act
""" 同 act：玩家做 fn 里的操作，游戏推进到玩家下一次要选行动 """


def _mute_ui() -> list:
    """
    屏蔽 draw 模块中绘制类的 draw 方法，并记录 WaitDraw 绘制的文本。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- WaitDraw 绘制过的文本列表，按绘制顺序追加
    """
    from Script.UI.Moudle import draw

    wait_texts = []

    def record_wait_draw(
        self: draw.WaitDraw, *args: object, **kwargs: object
    ) -> None:
        """
        记录型 WaitDraw 桩：把绘制文本收进 wait_texts
        Keyword arguments:
        self -- 绘制对象
        Return arguments:
        无
        """
        if getattr(self, "text", None):
            wait_texts.append(str(self.text))

    for cls_name in dir(draw):
        cls = getattr(draw, cls_name)
        if isinstance(cls, type) and hasattr(cls, "draw"):
            with contextlib.suppress(AttributeError, TypeError):
                cls.draw = lambda self, *args, **kwargs: None
    setattr(draw.WaitDraw, "draw", record_wait_draw)
    return wait_texts


def quiet_port() -> ScriptedUiPort:
    """构造以 default_first_option 应答并丢弃后端事件的 ScriptedUiPort 实例。"""
    from Script.Protocol import ScriptedUiPort, default_first_option

    return ScriptedUiPort(default_first_option(), listener=lambda event: None)


def _fresh_config() -> None:
    """
    重新读 config.ini（测试改过的取值不留到下一个测试），开局时间换成 START_TIME：开新游戏的时钟从 START_TIME 起
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Config import normal_config

    normal_config.init_normal_config()
    config = normal_config.config_normal
    config.year, config.month, config.day, config.hour, config.minute = (
        START_TIME
    )


class MinimalWorld:
    """
    小世界：真实游戏配置 + 空游戏状态 + 一键复原，不启动游戏
    同一进程只能载入一个世界；用 MinimalWorld.load() 取得它
    """

    _loaded: MinimalWorld | None = None
    """ 本进程已载入的世界 """

    def __init__(self) -> None:
        """
        只由 load() 调用：载入配置、造基线状态并记下快照
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._boot()
        self.wait_texts = _mute_ui()
        """ WaitDraw 绘制过的文本，每次复原清空 """
        self._snapshot()
        self.reset()

    @classmethod
    def load(cls) -> Self:
        """
        取得本进程的世界，第一次调用时载入
        Keyword arguments:
        无
        Return arguments:
        MinimalWorld -- 世界对象
        """
        if MinimalWorld._loaded is None:
            MinimalWorld._loaded = cls()
        elif type(MinimalWorld._loaded) is not cls:
            raise RuntimeError(
                f"本进程已载入 {type(MinimalWorld._loaded).__name__}，不能再载入 {cls.__name__}：两者共用同一个游戏缓存"
            )
        return MinimalWorld._loaded

    def _boot(self) -> None:
        """
        固定随机源，载入游戏
        Keyword arguments:
        无
        Return arguments:
        无
        """
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        # 游戏用相对路径读 data/ 与 config.ini
        os.chdir(ROOT)
        seed_everything()
        self._load_game()

    def _load_game(self) -> None:
        """
        增量构建 data/ 生成物，读入真实配置，造出空的游戏状态
        Keyword arguments:
        无
        Return arguments:
        无
        功能描述:
            顺序同 game.py：基础配置先于游戏配置初始化，再载入角色模板与地图并重设内核时钟；
            构建与配置载入的打印被收起。
        """
        with contextlib.redirect_stdout(io.StringIO()):
            import auto_build_config  # noqa: F401
        _fresh_config()
        from Script.Config import character_config, game_config, map_config

        with contextlib.redirect_stdout(io.StringIO()):
            game_config.init()
            character_config.init_character_tem_data()
            map_config.init_map_data()
        from Script.Design import basement
        from Script.Modules.domains import playthrough

        kernel_data.reset_clock(start_time(), {})
        kernel_data.written(playthrough.reset_difficulty_and_birth)
        kernel_data.reset_medical()
        kernel_data.written(basement.get_base_updata)
        for clothing_type, cloth_ids in STANDARD_OUTFIT.items():
            for cloth_id in cloth_ids:
                if (
                    game_config.config_clothing_tem[cloth_id].clothing_type
                    != clothing_type
                ):
                    raise FixtureError(
                        f"默认服装 {cloth_id} 不是 {clothing_type} 类衣物"
                    )

    def _snapshot(self) -> None:
        """
        记下基线：GameState 的全局数据（_boot 里 get_base_updata 开放的房间在其中）与每个场景的属性深拷贝
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.Kernel import core

        self._data = core.state().data
        self._scene_data = constant.scene_data
        self._scenes = dict(self._scene_data)
        self._scene_baseline = {
            key: copy.deepcopy(scene.__dict__)
            for key, scene in self._scenes.items()
        }

    def reset(self) -> None:
        """
        把游戏状态原地复原到基线，并重设全部随机源
        Keyword arguments:
        无
        Return arguments:
        无
        功能描述:
            场景对象不换，只改写内容；内核状态按基线重置，核外模块状态一并清零。
            游戏配置（game_config 等）与模块级打桩不在复原范围内：
            测试不能改配置，打桩用 unittest.mock 自行恢复。
        """
        from Script.Core import constant, io_init

        io_init.configure(quiet_port())
        constant.cmd_map.clear()
        self._scene_data.clear()
        self._scene_data.update(self._scenes)
        constant.scene_data = self._scene_data
        for key, scene in self._scenes.items():
            baseline = self._scene_baseline[key]
            scene.__dict__.clear()
            scene.__dict__.update(baseline)
            scene.scene_tag = list(baseline["scene_tag"])
        self.wait_texts.clear()
        _fresh_config()
        outside_cache.fresh()
        from Script.Kernel import core
        from Script.Modules import load_order

        core.load(load_order.LOAD_ORDER)
        kernel_data.reset_clock(start_time(), self._data)
        seed_everything()

    def scene(self, path: list) -> game_type.Scene:
        """
        取一个场景，路径必须是真实场景
        Keyword arguments:
        path -- 场景路径列表，如 ["中枢", "博士房间"]
        Return arguments:
        game_type.Scene -- 场景对象
        """
        from Script.Core import constant
        from Script.Design import map_handle

        key = map_handle.get_map_system_path_str_for_list(path)
        if key not in constant.scene_data:
            raise FixtureError(f"没有这个场景：{path}")
        return constant.scene_data[key]

    def move(self, cid: int, path: list) -> None:
        """用游戏的移动函数把角色从当前位置移到 path（cid: 角色id；path: 目标场景路径列表）"""
        from Script.Design import map_handle
        from Script.Modules.gameplay_resolution import working

        self.scene(path)
        pos = activity.position(cid)
        with (
            contextlib.nullcontext()
            if working.active()
            else kernel_data.writing()
        ):
            map_handle.character_move_scene(pos, list(path), cid)

    def chara(
        self,
        cid: int,
        name: str = "测试干员",
        position: list[str] | None = None,
        *,
        naked: bool = False,
        race: int = 0,
        adv: int = 0,
    ) -> identity.Identity:
        """
        造一个角色写入身份表（identity.characters），核对她的状态，通过后登记进在编名单
        Keyword arguments:
        cid -- 角色id（0 为玩家，造 NPC 前须先造玩家）
        name -- 角色名
        position -- 初始场景路径列表，默认 DEFAULT_SCENE
        naked -- 为真时不穿衣服（全裸），默认穿 STANDARD_OUTFIT
        race -- 种族id
        adv -- 剧情npc编号
        Return arguments:
        identity.Identity -- 已登记的角色身份
        功能描述:
            角色在 GameState 里的多项字典默认是空的，游戏代码直接下标访问，这里全部按置零函数预填。
            默认角色当场核对：穿着衣服（不是大致全裸），NPC 的异常位 1~7 全部正常（normal_all 为 1）。
            naked=True 的角色当场核对：全裸，NPC 还须只有位 4 异常（玩家的异常位恒为正常）。
            不符合时把她从身份表里删掉，再抛 FixtureError。这时她还没登记进在编名单。
        """
        from Script.Modules.domains import chara_life, relations
        from Script.Core import game_type
        from Script.Design import attr_calculation, game_time, map_handle

        if identity.exists(cid):
            raise FixtureError(f"角色 {cid} 已存在")
        if cid != 0 and not identity.exists(0):
            raise FixtureError(
                "先造玩家（cid 0）再造 NPC：异常位的判定要读玩家数据"
            )
        position = list(position if position is not None else DEFAULT_SCENE)
        self.scene(position)
        services = attr_calculation.get_assistant_services_zero()
        kernel_data.put(relations.assistant_services.set, cid, services)
        kernel_data.put(relations.favorability.set, cid, {0: 0})
        ca.zero_tables(cid)
        ca.talent(cid)[121] = 1
        dormitory = map_handle.get_map_system_path_str_for_list(DEFAULT_SCENE)
        kernel_data.put(chara_life.dormitory.set, cid, dormitory)
        place(cid, position, start_time=game_time.now())
        kernel_data.put(
            identity.put,
            identity.Identity(cid, name=name, sex=1, adv=adv, race=race),
        )
        chara_data.seed(cid, {} if naked else STANDARD_OUTFIT)
        kernel_data.set_needs(cid, hit_max=100, hit=100, mana_max=100, mana=100)
        try:
            self._check_chara(cid, naked)
        except FixtureError:
            kernel_data.put(identity.discard, cid)
            raise
        if cid:
            kernel_data.put(kernel_data.domain("roster").add, cid)
        return identity.of(cid)

    def _check_chara(self, cid: int, naked: bool) -> None:
        """
        核对新角色的衣着与异常位，不符合时抛 FixtureError
        Keyword arguments:
        cid -- 角色id
        naked -- 是否应为全裸
        Return arguments:
        无
        """
        from Script.Design import handle_premise

        if naked:
            if not handle_premise.handle_cloth_off(cid):
                raise FixtureError(f"角色 {cid} 应当全裸")
            expected_abnormal = [4] if cid else []
        else:
            if handle_premise.handle_cloth_most_off(cid):
                raise FixtureError(f"角色 {cid} 应当穿着衣服")
            expected_abnormal = []
        abnormal = [
            bit
            for bit in range(1, 8)
            if not getattr(handle_premise, f"handle_normal_{bit}")(cid)
        ]
        if abnormal != expected_abnormal:
            raise FixtureError(
                f"角色 {cid} 的异常位应为 {expected_abnormal}，实际为 {abnormal}"
            )
        if not naked and not handle_premise.handle_normal_all(cid):
            raise FixtureError(f"角色 {cid} 的 normal_all 应为 1")


class UnplannedInput(AssertionError):
    """游戏在等玩家输入，测试没有安排这一步，或屏幕上没有安排的按钮"""


class PlayerInput:
    """
    无头玩家输入驱动，通过 ScriptedUiPort 监听后端输出并按计划应答输入请求。
    监听回调把非空文本记入 screen 与捕获列表，并维护 buttons 中的当前按钮。
    同命令编号的按钮只保留最新项。清屏、清除按钮或按下按钮时移除相应按钮。
    应答器按 planned 顺序消费文字输入或匹配按钮。非等待请求未匹配计划时抛 UnplannedInput。
    应答经协议端口返回真实 flow_handle，由后者执行绑定命令并记录输入。
    """

    SCREEN_LIMIT = 400
    """ self.screen 只留最近的这么多段文字 """

    def __init__(self) -> None:
        """
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.buttons: list[tuple[str, str]] = []
        """ 可以按的按钮：(按钮文字, 命令id)；几个按钮都含安排的文字时按最后画出的那个 """
        self.screen: list[str] = []
        """ 最近输出的文字 """
        self.planned: list[tuple[str, str]] = []
        """ 还没用掉的输入：("press", 按钮文字的一部分) 或 ("type", 输入的文字) """
        self._captures: list[tuple[str | None, list[str]]] = []

    def install(self) -> None:
        """向 io_init 安装使用 self._answer 应答、self._see 监听的 ScriptedUiPort。"""
        from Script.Core import io_init
        from Script.Protocol import ScriptedUiPort

        io_init.configure(ScriptedUiPort(self._answer, listener=self._see))

    def press(self, *labels: str) -> None:
        """
        安排接下来依次按下的按钮
        Keyword arguments:
        labels -- 按钮文字的一部分，按顺序各按一次
        Return arguments:
        无
        """
        self.planned.extend(("press", label) for label in labels)

    def type(self, text: str) -> None:
        """
        安排下一次输入文字（如角色名）
        Keyword arguments:
        text -- 输入的文字
        Return arguments:
        无
        """
        self.planned.append(("type", text))

    def capture(self, keyword: str | None = None) -> list[str]:
        """
        注册一个文本捕获列表，持续收集之后输出的非空屏幕文本，不受 SCREEN_LIMIT 截断。
        Keyword arguments:
        keyword -- 过滤关键词，为空或 None 时收集全部非空文本
        Return arguments:
        list[str] -- 随输出持续追加的文本列表
        """
        texts: list[str] = []
        self._captures.append((keyword, texts))
        return texts

    def check_done(self) -> None:
        """
        安排的输入都已用掉，否则抛 UnplannedInput
        Keyword arguments:
        无
        Return arguments:
        无
        """
        if self.planned:
            raise UnplannedInput(
                f"安排的输入没有用掉：{self.planned}；最近的文字：{self.screen[-5:]}"
            )

    def _see(self, event: BackendEvent) -> None:
        """端口监听回调：把 RenderChunk 里的操作交给 _draw，在清除 screen 或 buttons 时清空 buttons。"""
        from Script.Protocol import Clear, RenderChunk

        match event:
            case RenderChunk(ops=ops):
                for op in ops:
                    self._draw(op)
            case Clear(target="screen" | "buttons"):
                self.buttons.clear()

    def _draw(self, op: RenderOp) -> None:
        """处理单条渲染操作：记录非空文本与文本/图片按钮，并按 ClearButtonsOp 移除对应按钮。"""
        from Script.Protocol import (
            ButtonOp,
            ClearButtonsOp,
            ImageButtonOp,
            TextOp,
        )

        match op:
            case TextOp(text=text) if str(text).strip():
                self.screen.append(str(text))
                del self.screen[: -self.SCREEN_LIMIT]
                for keyword, texts in self._captures:
                    if not keyword or keyword in str(text):
                        texts.append(str(text))
            case ButtonOp(label=label, command_id=cmd) | ImageButtonOp(
                asset_id=label, command_id=cmd
            ):
                self._forget((cmd,))
                self.buttons.append((str(label), cmd))
            case ClearButtonsOp(command_ids=cmd_ids):
                self._forget(cmd_ids)

    def _forget(self, cmd_ids: tuple[str, ...] | None) -> None:
        """从 buttons 中移除 cmd_ids 指定的按钮，cmd_ids 为 None 时清空全部按钮。"""
        if cmd_ids is None:
            self.buttons.clear()
            return
        self.buttons = [
            (text, cmd) for text, cmd in self.buttons if cmd not in cmd_ids
        ]

    def _answer(self, request: UiRequest) -> UiResponse:
        """
        队首为 type 且非等待请求（Pause 或可空 InputText）时消费它，否则匹配最新按钮的 press。
        命中按钮时消费并清空 buttons。未命中时等待请求不消费并返回默认应答，其余抛 UnplannedInput。
        Keyword arguments:
        request -- 待应答的 UiRequest
        Return arguments:
        UiResponse -- 对应的 Continue、SubmitChoice 或 SubmitText 响应
        """
        from Script.Protocol import InputText, Pause, reply

        kind, value = self.planned[0] if self.planned else ("", "")
        waiting = isinstance(request, Pause) or (
            isinstance(request, InputText) and request.allow_empty
        )
        if kind == "type" and not waiting:
            self.planned.pop(0)
            return reply(request, value)
        matches = [
            cmd
            for text, cmd in reversed(self.buttons)
            if kind == "press" and value in text
        ]
        if not matches:
            if waiting:
                return reply(request)
            shown = [text for text, _ in self.buttons]
            raise UnplannedInput(
                f"游戏在等玩家选择，安排的下一步是 {value or '（没有）'!r}；屏幕上的按钮：{shown}；最近的文字："
                f"{self.screen[-5:]}"
            )
        self.planned.pop(0)
        self.buttons.clear()
        return reply(request, matches[0])


class FullWorld(MinimalWorld):
    """
    完整的无头世界：小世界之外再注册结算器、状态机与界面流程，供慢速层用。
    绘制照常执行，玩家输入由 self.player（PlayerInput）给出，new_game() 走一遍开新游戏的界面流程。
    不做复原：慢速层每个测试一个新进程。
    """

    PLAYER_NAME = "多克特"
    """ new_game() 输入的玩家名字：与口上里写死的「博士」区分开 """

    def __init__(self) -> None:
        """
        只由 load() 调用：载入配置与全部游戏模块，换上 PlayerInput
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._boot()
        self.player = PlayerInput()
        """ 玩家输入 """
        self.player.install()

    def _load_game(self) -> None:
        """
        先载入小世界，再导入 Script.Settle、Script.StateMachine、医疗系统与界面流程（靠装饰器注册），
        随后重置核外状态并加载内核模块
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super()._load_game()
        import Script.Settle  # noqa: F401
        import Script.StateMachine  # noqa: F401
        import Script.System.Medical_System  # noqa: F401
        import Script.UI.Flow  # noqa: F401
        from Script.Kernel import core
        from Script.Modules import load_order

        outside_cache.fresh()
        core.load(load_order.LOAD_ORDER)

    def reset(self) -> None:
        """
        慢速层不复原，调用即抛 RuntimeError
        Keyword arguments:
        无
        Return arguments:
        无
        """
        raise RuntimeError("FullWorld 不复原：慢速层每个测试一个新进程")

    def new_game(self, first_bonus: tuple = ()) -> None:
        """
        走一遍开新游戏的界面流程：标题画面「初次唤醒」，读完免责声明，输入名字 PLAYER_NAME，按下 first_bonus
        的按钮，「睁开双眼」
        Keyword arguments:
        first_bonus -- 在创建角色面板里依次按下的初期奖励按钮，选助理干员时紧接着按下干员的名字，
            如 ("窄域时停", "启动资金", "助理干员", "阿米娅")；默认不选
        Return arguments:
        无
        功能描述:
            初始干员、设施与设置都取创建角色面板的默认值。流程结束时重设随机源，开局之后的随机与开局流程的长短无关。
        """
        from Script.Core import constant
        from Script.UI.Flow import creator_character_flow, title_flow
        from Script.UI.Moudle import view

        self.player.press("初次唤醒")
        title_flow.title_panel()
        if view.now_panel_id != constant.Panel.CREATOR_CHARACTER:
            raise FixtureError(
                f"标题画面没有进入创建角色：now_panel_id={view.now_panel_id}"
            )
        self.player.press("我读完并理解了以上8条")
        self.player.type(self.PLAYER_NAME)
        self.player.press(*first_bonus, "睁开双眼")
        creator_character_flow.creator_character_panel()
        self.player.check_done()
        seed_everything()
