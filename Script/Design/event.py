"""状态触发事件：按行为建立事件预索引，处理角色事件触发并构建与显示事件文本。"""

import random
from dataclasses import dataclass

from Script.Config import game_config
from Script.Design import talk
from Script.Modules.domains import activity, history
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import ui_hooks

_handle_premise = None
""" handle_premise 模块的延迟导入缓存（规避循环导入，同时消除每次事件判定重复导入的开销） """
_event_index: dict[str, dict] = {}
""" 事件预索引缓存：behavior_id -> 按角色专属性分桶的事件id列表（配置在游戏运行期不变，惰性构建一次） """


def _get_event_index(behavior_id: str) -> dict:
    """
    获取指定行为的事件预索引（惰性构建并缓存）
    参数:
        behavior_id (str) -- 行为id
    返回值类型：dict -- {"universal": [事件id], "sys0": {adv: [事件id]}, "sys1": {adv: [事件id]},
                        "both": {adv: [事件id]}, "any": {adv: [事件id]}}
    功能描述：约九成事件是角色专属事件（adv_id 非空），原实现每次事件判定都要遍历该行为的
              全部事件逐个做 adv 过滤。此处按 adv 过滤规则一次性分桶：
              universal -- 非角色专属，任何角色都是候选
              sys0 -- 前提含 sys_0（玩家触发）：仅当交互对象 adv 匹配时是候选
              sys1 -- 前提含 sys_1（NPC触发）：仅当自己 adv 匹配时是候选
              both -- 前提同时含 sys_0 与 sys_1：仅当自己与交互对象 adv 都匹配时是候选（沿用原过滤链语义）
              any -- 前提不含 sys_0/sys_1：自己或交互对象 adv 匹配时是候选
    """
    index = _event_index.get(behavior_id)
    if index is None:
        index = {"universal": [], "sys0": {}, "sys1": {}, "both": {}, "any": {}}
        for event_id in game_config.config_event_status_data.get(
            behavior_id, ()
        ):
            event_config = game_config.config_event[event_id]
            if event_config.adv_id in {"", "0", 0}:
                index["universal"].append(event_id)
                continue
            event_adv_id = int(event_config.adv_id)
            has_sys0 = "sys_0" in event_config.premise
            has_sys1 = "sys_1" in event_config.premise
            if has_sys0 and has_sys1:
                bucket = "both"
            elif has_sys0:
                bucket = "sys0"
            elif has_sys1:
                bucket = "sys1"
            else:
                bucket = "any"
            index[bucket].setdefault(event_adv_id, []).append(event_id)
        _event_index[behavior_id] = index
    return index


@dataclass(frozen=True, slots=True)
class EventText:
    """不可变的事件文本结果，保存待显示的文本、样式与事件元数据。"""

    event_id: str
    """ 事件编号，在自定义事件切换生效时为角色当前记录的事件编号 """
    character_id: int
    """ 触发事件的角色编号 """
    event_type: int
    """ 传入的事件类型编号 """
    text: str
    """ 待显示的事件正文，无需显示时为空字符串 """
    style: str
    """ 绘制事件正文使用的文本样式名，默认值为 "standard" """


def build_event_text(
    event_id: str, character_id: int, event_type: int
) -> EventText:
    """
    构建事件文本，按序执行位置检查、自定义事件切换、分段截取、代码词展开与样式判定。
    玩家不在角色位置或移动目标时，返回空文本与 "standard" 样式。
    启用 chara_diy_event_flag 时取用角色记录的事件。
    该事件文本少于两个 "|" 时返回空文本且不清除标记，否则清除标记。
    含 "|" 的子事件取第二段，自定义事件取第三段，其余取全文，段首加换行符。
    随后调用 talk.code_text_to_draw_text 展开代码词。
    角色专属事件按 text_color 依次取角色名或交互对象名，否则为 "standard"。
    Keyword arguments:
    event_id -- str，事件编号
    character_id -- int，角色编号
    event_type -- int，事件类型，原样写入结果
    Return arguments:
    EventText -- 构建后的事件文本对象
    """
    text = ""
    style = "standard"
    if activity.position(0) not in (
        activity.position(character_id),
        activity.behavior(character_id).move_target,
    ):
        return EventText(event_id, character_id, event_type, text, style)
    diy_event_flag = False
    if activity.event(character_id).chara_diy_event_flag:
        event_id = activity.event(character_id).event_id
        if game_config.config_event[event_id].text.count("|") < 2:
            return EventText(event_id, character_id, event_type, text, style)
        activity.update_event(character_id, chara_diy_event_flag=False)
        diy_event_flag = True
    event_data = game_config.config_event[event_id]
    son_event_flag = "option_son" in event_data.premise or any(
        "CVP_A1_Son" in premise for premise in event_data.premise
    )
    if son_event_flag and "|" in event_data.text:
        text = "\n" + event_data.text.split("|")[1]
    elif diy_event_flag and "|" in event_data.text:
        text = "\n" + event_data.text.split("|")[2]
    else:
        text = "\n" + event_data.text
    text = talk.code_text_to_draw_text(text, character_id)
    if event_data.adv_id not in {"", "0", 0}:
        character_data = identity.of(character_id)
        target_data = identity.of(activity.target(character_id))
        if character_data.text_color:
            style = character_data.name
        elif target_data.text_color:
            style = target_data.name
    return EventText(event_id, character_id, event_type, text, style)


def show_event_text(event_text: EventText) -> None:
    """
    在事件文本非空时经 ui_hooks.emit_line_wait_text 输出正文与样式，空文本时不触发回调。
    Keyword arguments:
    event_text -- EventText，待显示的事件文本对象
    Return arguments:
    None -- 无返回值
    """
    if event_text.text:
        ui_hooks.emit_line_wait_text(event_text.text, event_text.style)


def handle_event(
    character_id: int, event_before_instrust_flag: bool = False
) -> EventText | None:
    """
    处理状态触发事件
    Keyword arguments:
    character_id -- 角色id
    event_before_instrust_flag -- 是否是事件在前，指令在后（或跳过指令）
    Return arguments:
    EventText -- 触发事件时为对应的事件文本对象，未触发事件时为 None
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _handle_premise
    if _handle_premise is None:
        from Script.Design import handle_premise as _handle_premise_module

        _handle_premise = _handle_premise_module
    handle_premise = _handle_premise
    character_data: identity.Identity = identity.of(character_id)
    target_character_id = activity.target(character_id)
    target_character_data = identity.of(target_character_id)
    behavior_id = activity.behavior(character_id).behavior_id
    weighted_event_ids: list[str] = []
    weighted_values: list[float] = []
    # 已计算过的前提字典
    calculated_premise_dict: dict[str, float] = {}
    if behavior_id in game_config.config_event_status_data:
        # 从预索引中直接取出本角色/交互对象相关的候选事件，
        # 替代原先"遍历该行为全部事件后逐个做 adv 过滤"（约九成事件是其他角色的专属事件）
        event_index = _get_event_index(behavior_id)
        self_adv = character_data.adv
        target_adv = target_character_data.adv
        candidate_event_ids = list(event_index["universal"])
        candidate_event_ids += event_index["sys0"].get(target_adv, ())
        candidate_event_ids += event_index["sys1"].get(self_adv, ())
        candidate_event_ids += event_index["any"].get(self_adv, ())
        if target_adv != self_adv:
            candidate_event_ids += event_index["any"].get(target_adv, ())
        # both桶要求自己与交互对象的adv同时匹配（沿用原过滤链对 sys_0+sys_1 并存事件的语义）
        if self_adv == target_adv:
            candidate_event_ids += event_index["both"].get(self_adv, ())
        for event_id in candidate_event_ids:
            now_weight = 1
            event_config = game_config.config_event[event_id]
            # 如果是事件在前，指令在后，判断是否需要跳过
            if event_before_instrust_flag:
                if event_config.type == 1:
                    continue
            # 和触发记录相关的前提
            if "this_event_in_triggered_record" in event_config.premise:
                if not history.triggered(event_id):
                    continue
            if "this_event_not_in_triggered_record" in event_config.premise:
                if history.triggered(event_id):
                    continue
            if "this_event_in_today_triggered_record" in event_config.premise:
                if not history.triggered_today(event_id):
                    continue
            if (
                "this_event_not_in_today_triggered_record"
                in event_config.premise
            ):
                if history.triggered_today(event_id):
                    continue
            if len(event_config.premise):
                # 计算前提字典的总权重
                premise_dict = event_config.premise
                now_weight, calculated_premise_dict = (
                    handle_premise.get_weight_from_premise_dict(
                        premise_dict,
                        character_id,
                        calculated_premise_dict,
                        unconscious_pass_flag=True,
                    )
                )
            if now_weight:
                weighted_event_ids.append(event_id)
                weighted_values.append(now_weight)
    if weighted_event_ids:
        now_event_id = random.choices(
            weighted_event_ids, weights=weighted_values, k=1
        )[0]
        event_config = game_config.config_event[now_event_id]
        # 如果是事件前置指令后置类型，则判断是否存在跳过口上的结算
        if event_config.type == 2 and "10012" in event_config.effect:
            activity.update_event(character_id, skip_instruct_talk=True)
        # print(f"debug now_event_id:{now_event_id}")
        return build_event_text(now_event_id, character_id, event_config.type)
    return None
