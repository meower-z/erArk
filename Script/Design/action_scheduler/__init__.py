"""行动调度器：按开始时刻先后执行玩家和各 NPC 的行动，直到再次轮到玩家输入。

每个角色在时间线上最多一条待办。每一步取最早的待办：同一时刻立即待办先行，其次是玩家。
待办要么带一个具体行动（开始时一次结算完整段效果），要么不带行动，表示到时再定：玩家等待输入，NPC 由 AI 选择。
行动执行完后，若结算过程中没有为该角色写入新待办，就在行动结束时刻为它安排一条"到时再定"。
结算代码要某角色立刻做某事时，用 submit_current 写入立即待办；它不会被调度器覆盖。
本调度器不随存档保存，新开局或读档后丢弃，首次推进时按各角色当前的行为重建。

对外只用本文件的函数；包内 action（行动与时间工具）、timeline（时间线）、settle（结算）、npc、player 各管一块。
"""

from typing import Callable, Optional

from Script.Core import cache_control, constant, game_type
from Script.Design import game_time
from Script.Design.action_scheduler import npc, player
from Script.Design.action_scheduler.action import Action, behavior_end, minutes_between, wait_action
from Script.Design.action_scheduler.timeline import Entry, Timeline, chain_after

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_scheduler = None
""" 本局的调度器；不随存档保存 """


class Scheduler:
    """本局的行动调度器：timeline 为各角色的待办，after_input 为玩家回到输入前要执行的接续"""

    def __init__(self):
        """
        建立空调度器，并为在队 NPC 建立待办
        Return arguments:
        None
        """
        self.timeline = Timeline()
        self.running = False
        self.after_input: Optional[Callable[[], None]] = None
        self.sync_characters()

    def sync_characters(self):
        """
        为没有待办的在队 NPC 建立待办：进行中的行为已在开始时结算，到期后再由 AI 选择
        Return arguments:
        None
        """
        for character_id in sorted(set(cache.npc_id_got) - {0}):
            character = cache.character_data[character_id]
            if character_id in self.timeline or character.dead:
                continue
            at = cache.game_time
            behavior = character.behavior
            if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY and behavior.start_time.year > 1:
                at = max(at, behavior_end(behavior))
            self.timeline.put(character_id, Entry(at))

    def sync_world(self, character_id: int, entry: Entry):
        """
        执行待办前同步世界：游戏时间设为待办时刻，跨天先日结，再按此刻结算随时间到期的状态
        Keyword arguments:
        character_id -- 角色id
        entry -- 待办
        Return arguments:
        None
        """
        from Script.Settle import past_day_settle, realtime_settle

        cache.game_time = entry.at
        if cache.pre_game_time.date() != entry.at.date():
            past_day_settle.update_new_day()
            self.sync_characters()
        # 回到玩家输入前结算全员，其余待办结算本人
        is_input = character_id == 0 and entry.action is None
        for now_id in ({0} | cache.npc_id_got) if is_input else (character_id,):
            realtime_settle.change_character_persistent_state(now_id)

    def take_after_input(self) -> Optional[Callable[[], None]]:
        """
        取出登记的接续并清空登记
        Return arguments:
        Callable | None -- 登记的接续
        """
        callback, self.after_input = self.after_input, None
        return callback

    def execute(self, character_id: int, action: Action) -> Optional[float]:
        """
        把行动写成角色的行为并结算；离队或死亡的角色只占用行动时长
        Keyword arguments:
        character_id -- 角色id
        action -- 行动
        Return arguments:
        float | None -- 占用的分钟数；行动前置结算为该角色写入了立即待办时返回 None，本次让位
        """
        character = cache.character_data[character_id]
        if character.dead or (character_id and character_id not in cache.npc_id_got):
            return action.behavior.duration
        if character_id == 0:
            return player.act(action, self.timeline)
        return npc.act(character_id, action, self.timeline)

    def run_until_input(self):
        """
        按时刻先后执行待办，直到轮到玩家输入
        Return arguments:
        None
        """
        while True:
            character_id, entry = self.timeline.next()
            self.sync_world(character_id, entry)
            if entry.action is None:
                if character_id == 0:
                    player.prepare(self.take_after_input)
                else:
                    npc.prepare(character_id, self.timeline)
            # 执行前的处理可能替换或撤销了这条待办
            if not self.timeline.claim(character_id, entry):
                continue
            if character_id == 0 and entry.action is None:
                return
            action = entry.action or npc.decide(character_id, self.timeline)
            minutes = None if action is None else self.execute(character_id, action)
            if minutes is None:
                # 让位给新写入的立即待办，收尾回调排在它之后
                chain_after(self.timeline.get(character_id), entry.after)
                continue
            if entry.after is not None:
                entry.after()
            if character_id not in self.timeline:
                self.timeline.put(character_id, Entry(game_time.get_sub_date(minute=minutes, old_date=entry.at)))

    def advance(self, minutes: int):
        """
        执行玩家已写好的行动并推进时间，直到再次轮到玩家输入；结算过程中被调用时，改为让玩家立即执行该行动
        Keyword arguments:
        minutes -- 玩家行动的分钟数
        Return arguments:
        None
        """
        action = Action.of(cache.character_data[0])
        action.behavior.duration = max(minutes, 1)
        if self.running:
            self.timeline.force(0, action)
            return
        self.sync_characters()
        self.timeline.put(0, Entry(cache.game_time, action, True))
        with player.turn_session(self):
            self.run_until_input()


def get_scheduler() -> Scheduler:
    """
    取本局的调度器，首次使用时按角色当前行为建立
    Return arguments:
    Scheduler -- 调度器
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def advance(minutes: int):
    """
    执行玩家已写好的行动并推进时间，直到再次轮到玩家输入；结算过程中被调用时，改为让玩家立即执行该行动
    Keyword arguments:
    minutes -- 玩家行动的分钟数
    Return arguments:
    None
    """
    get_scheduler().advance(minutes)


def is_running() -> bool:
    """
    调度器是否正在推进（即当前代码运行在某次结算之中）
    Return arguments:
    bool -- 是否正在推进
    """
    return _scheduler is not None and _scheduler.running


def reset():
    """
    新开局或读档后丢弃调度器，首次推进时重建
    Return arguments:
    None
    """
    global _scheduler
    _scheduler = None


def submit_current(character_id: int, after: Optional[Callable[[], None]] = None):
    """
    让角色立即执行身上已写好的行为
    Keyword arguments:
    character_id -- 角色id
    after -- 行动完成后的收尾回调
    Return arguments:
    None
    """
    get_scheduler().timeline.force(character_id, Action.of(cache.character_data[character_id]), after)


def continue_after_input(callback: Callable[[], None]):
    """
    登记玩家本次行动结束、回到输入之前执行的接续（如分段寻路的下一段）
    Keyword arguments:
    callback -- 无参回调
    Return arguments:
    None
    """
    get_scheduler().after_input = callback


def replan(character_id: int):
    """
    别人改写了 NPC 的行为后，让它从此刻起按新行为执行；不打断此刻的其他行动
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    None
    """
    get_scheduler().timeline.put(character_id, Entry(cache.game_time))


def reset_character(character_id: int):
    """
    角色上下线时重排待办：离队者撤销，在队者按当前行为重新入队
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    None
    """
    if _scheduler is None:
        return
    _scheduler.timeline.drop(character_id)
    if character_id in cache.npc_id_got:
        _scheduler.sync_characters()


def wait_on(character_id: int, owner_id: int, behavior_id: str):
    """
    让参与者等待主体的双人行为：NPC 分段复查，主体只是在等待时陪等其时长；玩家等完全程
    Keyword arguments:
    character_id -- 参与者id
    owner_id -- 主体id
    behavior_id -- 主体的行为id
    Return arguments:
    None
    """
    if cache.time_stop_mode:
        return
    scheduler = get_scheduler()
    if character_id == 0:
        remaining = minutes_between(cache.game_time, behavior_end(cache.character_data[owner_id].behavior))
        scheduler.timeline.force(0, wait_action(owner_id, max(remaining, 1)))
        return
    scheduler.timeline.put(character_id, Entry(cache.game_time, npc.companion_wait(owner_id, behavior_id)))
