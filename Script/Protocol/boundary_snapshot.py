"""
边界快照与命令计划类型（boundary_snapshot）
===========================================
定义前后端边界传递的不可变快照与行动计划数据类。
本模块仅导入 Python 标准库，不依赖游戏逻辑或界面模块。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """记录快照生成时刻与所属面板标识的不可变元数据。"""

    clock: int
    panel: str

    def __post_init__(self) -> None:
        """校验 clock 为非负 int（非 bool）且 panel 为非空 str，类型错抛 TypeError，值错抛 ValueError。"""
        if not isinstance(self.clock, int) or isinstance(self.clock, bool):
            raise TypeError(f"clock={self.clock!r}")
        if self.clock < 0:
            raise ValueError(f"clock={self.clock!r}")
        if not isinstance(self.panel, str):
            raise TypeError(f"panel={self.panel!r}")
        if not self.panel:
            raise ValueError(f"panel={self.panel!r}")


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """表示命令计划的受理结果及可选的拒绝原因码。"""

    accepted: bool
    reason: str = ""

    def __post_init__(self) -> None:
        """校验 accepted 为 bool 且 reason 为 str，类型不符时抛出 TypeError。"""
        if not isinstance(self.accepted, bool):
            raise TypeError(f"accepted={self.accepted!r}")
        if not isinstance(self.reason, str):
            raise TypeError(f"reason={self.reason!r}")


@dataclass(frozen=True, slots=True)
class ResourceStockItem:
    """记录单种资源的编号、名称与当前库存数量。"""

    resource_id: int
    name: str
    amount: int


@dataclass(frozen=True, slots=True)
class RecipeIngredient:
    """记录配方单种消耗材料的资源编号、名称与所需数量。"""

    resource_id: int
    name: str
    required: int


@dataclass(frozen=True, slots=True)
class AromatherapyRecipeOption:
    """描述单条香薰配方的展示信息、解锁状态、未解锁原因与材料消耗。"""

    recipe_id: int
    name: str
    info: str
    unlocked: bool
    lock_reasons: tuple[str, ...]
    ingredients: tuple[RecipeIngredient, ...]


@dataclass(frozen=True, slots=True)
class AromatherapySnapshot:
    """封装香薰疗愈面板展示所需的只读状态快照。"""

    meta: SnapshotMeta
    remaining_today: int
    target_cid: int
    target_name: str
    target_today_recipe_name: str | None
    resources: tuple[ResourceStockItem, ...]
    selected_recipe_id: int
    selected_recipe_name: str
    can_confirm: bool
    recipes: tuple[AromatherapyRecipeOption, ...]


@dataclass(frozen=True, slots=True)
class AromatherapyActionPlan:
    """封装香薰行动的校验结果以及受理时对应的行为编号、状态常量与配方编号。"""

    outcome: CommandOutcome
    behavior_id: str | None = None
    state: int | None = None
    recipe_id: int | None = None

    def __post_init__(self) -> None:
        """校验受理时 behavior_id、state 与 recipe_id 均非空、拒绝时三者均为 None，否则抛出 ValueError。"""
        planned = (self.behavior_id, self.state, self.recipe_id)
        if self.outcome.accepted and None in planned:
            raise ValueError(f"accepted plan={planned!r}")
        if not self.outcome.accepted and planned != (None, None, None):
            raise ValueError(f"rejected plan={planned!r}")
