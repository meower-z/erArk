"""
游戏逻辑与前端界面之间的纯数据领域契约模块，仅依赖 Python 标准库。
定义叙述事件、数值变化事件、场景分隔标记与轻度富文本数据结构，用于后端向前端输出领域信息。
同时定义结算中模态交互提示、只读边界快照与管理指令结果等不可变数据类。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Self

type SpanRole = Literal[
    "plain",
    "heading",
    "emphasis",
    "strong",
    "character_color",
    "warning",
    "accent",
]
type BlockKind = Literal["paragraph", "heading", "divider", "quote"]
type DeltaValue = int | float | str | bool | None
type DisplayMode = Literal["scrolling_queue", "page_clear"]

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
_SCALARS = (str, int, float, bool, type(None))


@dataclass(frozen=True, slots=True)
class EventMeta:
    """
    领域事件附带的客观元数据，供前端按参与者、地点或类别筛选与折叠。
    记录涉及的角色编号元组 actors、地点 location、是否涉及玩家 involves_player 及类别 category。
    """

    actors: tuple[int, ...] = ()
    location: str | None = None
    involves_player: bool = False
    category: str = "narrative"


@dataclass(frozen=True, slots=True)
class TextSpan:
    """
    轻度富文本中的单个语义片段，携带文本内容 text、语义角色 role 与可选颜色提示 color_hint。
    color_hint 为 None 或 #RRGGBB 形式的十六进制颜色字符串，具体样式由前端决定。
    """

    text: str
    role: SpanRole = "plain"
    color_hint: str | None = None

    def __post_init__(self) -> None:
        """校验非 None 的 color_hint 必须匹配 #RRGGBB 格式，不合法时抛出 ValueError。"""
        hint = self.color_hint
        if hint is not None and _HEX_COLOR.fullmatch(hint) is None:
            raise ValueError(f"color_hint must be #RRGGBB, got {hint!r}")


@dataclass(frozen=True, slots=True)
class TextBlock:
    """
    轻度富文本中的块级元素，由多个 TextSpan 片段、块类型 kind 与标题层级 level 组成。
    kind 取值为 paragraph、heading、divider 或 quote，level 范围为 1 到 6。
    """

    spans: tuple[TextSpan, ...]
    kind: BlockKind = "paragraph"
    level: int = 1

    def __post_init__(self) -> None:
        """校验 level 处于 1 到 6 的闭区间内，越界时抛出 ValueError。"""
        if not 1 <= self.level <= 6:
            raise ValueError(f"level must be 1..6, got {self.level}")

    @classmethod
    def plain(cls, text: str) -> Self:
        """
        构造只含单个默认普通片段的段落块。

        参数：
        text (str) -- 段落文本内容

        返回值：Self -- 包含单个 plain 角色 TextSpan 的段落 TextBlock 实例
        """
        return cls((TextSpan(text),))


@dataclass(frozen=True, slots=True)
class NarrativeEvent:
    """
    不可拆分的单条叙述领域事件，携带元数据 meta、纯文本 text 与富文本块元组 blocks。
    该事件用于表达单条叙述内容，不包含前端排版或控件指令。
    """

    meta: EventMeta
    text: str = ""
    blocks: tuple[TextBlock, ...] = ()

    def __post_init__(self) -> None:
        """校验 text 与 blocks 不能同时为空，均为空时抛出 ValueError。"""
        if not self.text and not self.blocks:
            raise ValueError("NarrativeEvent needs text or blocks")


@dataclass(frozen=True, slots=True)
class DeltaEntry:
    """
    单条结构化数值或状态变化记录，标明展示用目标名称 target、字段名 field 与可选单位 unit。
    target 为向玩家展示的非空白字符串，可选的整数编号 target_id 仅用于程序标识而不作展示输出。
    delta 与 new_value 至少提供其一。
    """

    target: str
    field: str
    delta: DeltaValue = None
    new_value: DeltaValue = None
    unit: str = ""
    target_id: int | None = None

    def __post_init__(self) -> None:
        """
        校验 target 为字符串且 target_id 为 None 或纯 int（否则抛 TypeError），并校验 target 非空白、field 非空且 delta
        与 new_value 不全为 None（否则抛 ValueError）。
        """
        target_id = self.target_id
        if not isinstance(self.target, str):
            raise TypeError(
                f"DeltaEntry target must be str, got {self.target!r}"
            )
        if target_id is not None and type(target_id) is not int:
            raise TypeError(
                f"DeltaEntry target_id must be int, got {target_id!r}"
            )
        if not self.target.strip():
            raise ValueError("DeltaEntry target must not be blank")
        if not self.field:
            raise ValueError("DeltaEntry field must not be empty")
        if self.delta is None and self.new_value is None:
            raise ValueError("DeltaEntry needs delta or new_value")


@dataclass(frozen=True, slots=True)
class DeltaEvent:
    """
    结构化数值变化领域事件，携带事件元数据 meta 与一条以上的 DeltaEntry 记录。
    该事件以结构化条目描述数值变动，不携带叙述正文。
    """

    meta: EventMeta
    entries: tuple[DeltaEntry, ...]

    def __post_init__(self) -> None:
        """校验 entries 至少包含一条记录，为空时抛出 ValueError。"""
        if not self.entries:
            raise ValueError("DeltaEvent needs at least one entry")


@dataclass(frozen=True, slots=True)
class SceneBreak:
    """
    后端发出的场景分隔标记，表示此处适合做明显的视觉分隔并可附带原因说明 reason。
    该标记本身不是清屏指令，具体呈现与清屏方式由前端决定。
    """

    meta: EventMeta = EventMeta(category="scene_break")
    reason: str = ""


type DomainEvent = NarrativeEvent | DeltaEvent | SceneBreak


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    """选择提示中的单个候选项，包含标识 option_id、展示文案 label、可用标记 enabled 与补充说明 detail。"""

    option_id: str
    label: str
    enabled: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        """校验 option_id 与 label 均不能为空字符串，任一为空时抛出 ValueError。"""
        if not self.option_id or not self.label:
            raise ValueError("ChoiceOption needs option_id and label")


@dataclass(frozen=True, slots=True)
class ChoicePrompt:
    """
    用于结算过程中向玩家发出的模态选择提示，携带提示标识 prompt_id、标题 title 与候选项元组 options。
    该提示通过 meta 附带事件元数据，并通过 allow_cancel 指示前端是否允许取消选择。
    """

    prompt_id: str
    title: str
    options: tuple[ChoiceOption, ...]
    meta: EventMeta = EventMeta()
    allow_cancel: bool = False

    def __post_init__(self) -> None:
        """校验 prompt_id 与 options 非空、option_id 唯一且不可取消时至少有一项可用，违反时抛出 ValueError。"""
        if not self.prompt_id:
            raise ValueError("ChoicePrompt prompt_id must not be empty")
        if not self.options:
            raise ValueError("ChoicePrompt needs at least one option")
        ids = [option.option_id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError(f"ChoicePrompt option ids repeat: {ids}")
        if not self.allow_cancel and not any(o.enabled for o in self.options):
            raise ValueError("ChoicePrompt needs an enabled option or cancel")


@dataclass(frozen=True, slots=True)
class TextPrompt:
    """
    用于结算过程中向玩家发出的模态文本输入提示，携带提示标识 prompt_id、标题 title 与默认值 default。
    该提示通过 max_length 指定最大输入长度或为 None，并通过 allow_cancel 指示是否允许取消输入。
    """

    prompt_id: str
    title: str
    default: str = ""
    max_length: int | None = None
    meta: EventMeta = EventMeta()
    allow_cancel: bool = False

    def __post_init__(self) -> None:
        """校验 prompt_id 非空且非 None 的 max_length 必须大于 0，不满足时抛出 ValueError。"""
        if not self.prompt_id:
            raise ValueError("TextPrompt prompt_id must not be empty")
        if self.max_length is not None and self.max_length <= 0:
            raise ValueError(f"max_length must be > 0, got {self.max_length}")


type ModalPrompt = ChoicePrompt | TextPrompt


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """边界快照的元信息，记录修订号 revision、是否允许存档 can_save、游戏天数 day 与时间槽位 time_slot。"""

    revision: int
    can_save: bool
    day: int
    time_slot: int

    def __post_init__(self) -> None:
        """校验 revision、day 与 time_slot 均不为负数，任一小于 0 时抛出 ValueError。"""
        if min(self.revision, self.day, self.time_slot) < 0:
            raise ValueError(f"SnapshotMeta counters must be >= 0: {self}")


@dataclass(frozen=True, slots=True)
class BoundarySnapshot:
    """
    供玩家选择下一步行动时读取的深度只读状态快照，包含元信息 meta 与不可变嵌套映射 data。
    构造时会递归复制并冻结 data 中的映射、序列与集合，外部对原容器的后续修改不会影响快照内容。
    """

    meta: SnapshotMeta
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        """
        递归冻结 data 为深度只读副本（映射转 MappingProxyType、列表转元组、集合转 frozenset），遇不支持的值类型抛出
        TypeError。
        """
        object.__setattr__(self, "data", _frozen(self.data))


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """
    玩家选择下一步行动期间执行的管理指令所返回的结果。
    记录指令是否生效 applied、最新边界快照 snapshot、附带领域事件元组 events 与错误信息 error。
    """

    applied: bool
    snapshot: BoundarySnapshot
    events: tuple[DomainEvent, ...] = ()
    error: str = ""


def _frozen(value: object) -> object:
    match value:
        case Mapping():
            return MappingProxyType({k: _frozen(v) for k, v in value.items()})
        case list() | tuple():
            return tuple(_frozen(item) for item in value)
        case set() | frozenset():
            return frozenset(_frozen(item) for item in value)
        case _ if isinstance(value, _SCALARS):
            return value
    raise TypeError(f"unsupported snapshot value type {type(value).__name__}")
