---
name: headless-game-test
description: 在不启动图形界面的情况下无头运行 erArk：加载游戏配置、自建角色fixture做函数级单元测试，或加载指定存档、复刻某条指令、带护栏运行角色行为循环并逐轮内窥。用于验证新增的前提/结算器/效果链/口上是否生效，复现与定位死循环/卡死，以及修复前后的回归测试。当需要"给新增的前提或结算写单元测试"、"验证效果链顺序"、"复现某存档下的BUG"、"模拟执行某指令"、"验证行为循环收敛"、"排查NPC卡死"时使用。
---

# Skill Instructions

你是 erArk 的无头测试助手。本 skill 归纳了一套经实战验证的方法：不启动 Tk 界面，在一个 Python 进程内完整初始化游戏、读取存档、复刻玩家指令、带护栏地运行行为循环，并对任意函数插桩观察每一轮的中间状态。

本 skill 覆盖**两种模式**，先选对模式再动手，选错会绕远路：

| 模式 | 什么时候用 | 模板 | 要不要读存档 |
| --- | --- | --- | --- |
| **A. 函数级单元测试** | 验证新增/改动的前提、结算器、效果链顺序、换装函数、口上是否生效 | `unit_test_template.py` | 不用，自建角色 fixture |
| **B. 行为循环诊断** | 复现存档里的 BUG、排查死循环/卡死、验证 AI 收敛 | `harness_template.py` | 要 |

两个模板都在本目录下，按其中 `====` 分段标记修改后即可直接运行。**模式 A 请务必先读下面的「模式 A：函数级单元测试」一节**——那里的 fixture 字段清单与两条全局前置是本 skill 里最容易反复踩坑的地方。

## 铁律（每条都是踩过的坑）

1. **必须用 `./.conda/python.exe`**，裸 `python` 是 Windows 商店空壳别名（exit 49、无任何输出）。
2. **外层必须加 `timeout N`**（`timeout` 命令）。`timeout` 在 N 秒后终止仍在运行的进程。卡住的脚本（例如第 5 条说的死循环）因此不会一直跑下去。`EXIT=124` 表示进程跑满 N 秒后被 `timeout` 终止。原因可能是脚本卡住，也可能是 N 给小了。
3. **加 `-u` 取消缓冲**，且脚本开头 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`（Windows 控制台是 GBK，中文会乱码/报错）。
4. **绝不用 `| tail` / `| head` 观察可能长时间运行的进程**。管道会攒住全部输出直到进程结束，看起来和「卡死」一模一样——包括 `buildconfig.py`、`tools/lint_target_csv.py` 这类跑几分钟的脚本，以及所有 harness。正确做法是**重定向到文件再读**：
   ```bash
   LOG="<scratchpad>/run.log"
   timeout 300 ./.conda/python.exe -u <脚本> > "$LOG" 2>&1; echo "EXIT=$?"; tail -30 "$LOG"
   ```
   （`$TMPDIR` 在 Git Bash 里是空的，`> "$TMPDIR/x.log"` 会写到 `/x.log` 并 Permission denied，必须写完整的 scratchpad 路径。）
5. **不要自己写主循环**：游戏由内核一步一步推进（`Script/Kernel/core.py` 的 `core.step()`）。玩家的指令要在玩家选行动时下：用 `tests/world.py` 的 `act(指令处理函数)`，它推进到玩家选行动时跑这条指令，再推进到玩家下一次选行动时停下。要排查的 BUG 是死循环时，先给 `core.step` 包一层步数护栏（见下文与 `harness_template.py`），否则 harness 自己就会卡死。
6. **只读纪律**：读档只用 `save_handle.input_load_save(id)`（纯读入内存）；绝不调用 `establish_save()`；推进中会写文件的两处（玩家睡觉后的自动存档 `save_handle.establish_save`、临时外勤委托追加写 Commission.csv）先替换掉（见 `harness_template.py`）。所有修复先用 monkeypatch 在内存中模拟验证，确认收敛后再改源码。
7. **含中文的脚本一律写成文件再跑，不要走 heredoc/stdin**。Git Bash 把 heredoc 以 GBK 喂给 Python，脚本里的中文字符串会被解码成乱码，直接 `SyntaxError: invalid syntax`（报错行里能看到 `��` 就是这个原因）。正确做法：用 Write 工具把脚本写到 scratchpad（UTF-8），开头 `os.chdir(r"c:\code\erArk")` + `sys.path.insert(0, r"c:\code\erArk")`，再 `timeout 300 ./.conda/python.exe -u "<scratchpad>/xxx.py" > "$LOG" 2>&1`。纯 ASCII 的一次性小脚本才可以用 heredoc（`./.conda/python.exe -u - <<'EOF'`，此时 sys.path[0] 为当前目录，可直接 `import auto_build_config`）。同理，需要批量改含中文的 CSV/文档时也用脚本文件而不是 stdin。
8. **测试脚本是回归资产，改完一轮功能就重跑上一轮的测试**。同一子系统连续多个 plan 时（如 plan_14→17→18 的怀孕系统），每次实施后除了跑新测试，还要重跑前几轮留下的测试文件（scratchpad 会随会话丢失，长期要用的测试请在 plan 文档里记录其断言清单，或在用户同意后收进仓库）。

## 模式 A：函数级单元测试

不读存档、不跑行为循环，自建角色后直接调前提/结算器/换装函数做断言。模板：`unit_test_template.py`（可直接运行，自带 7 条示例断言）。

初始化链与模式 B 完全一样（见下一节），但**额外有两条全局前置**，漏了会在结算内部炸 KeyError，而且报错点离真正的原因很远：

```python
# ① 数值结算会读全局设置 normal_config.system_setting 的各项，System_Setting() 默认是空壳
normal_config.system_setting = attr_calculation.get_system_setting_zero()

# ② 场景路径必须是 cache.scene_data 里真实存在的键，["0"]、["0","0"] 这类占位值会让
#    关门(752)、移动(751/761/762)、地点判定类结算 KeyError
SCENE = ["宿舍", "1区", "101"]        # 一间真实宿舍
PREV_SCENE = ["宿舍", "1区", "0"]     # 它所在区的入口，测「推回前一场景」时用
assert map_handle.get_map_system_path_str_for_list(SCENE) in cache.scene_data
```

### fixture 字段与置零函数对照表

`game_type.Character()` 的多数容器字段初值是**空 dict**，而代码里普遍用 `xxx[key]` 直接下标访问，不预填就 KeyError。置零函数的命名和签名**不规律**，凭印象写必错，照抄下表：

| 字段 | 置零函数 | 坑 |
| --- | --- | --- |
| `cloth` | `get_cloth_zero()` | 无参 |
| `cloth.cloth_locker_in_dormitory` | `get_cloth_locker_in_dormitory_zero()` | `get_cloth_zero()` 不含两个衣柜，要单独置零 |
| `cloth.cloth_locker_in_shower` | `get_shower_cloth_locker_zero()` | 命名顺序与上一行相反（shower_cloth_locker） |
| `dirty` | **`get_zero_dirty()`** | 不是 `get_dirty_zero`；另有 `get_dirty_reset()` 是别的语义 |
| `talent` | `get_talent_zero({})`，交回的表在 `kernel_data.writing()` 里经 `abilities.talent(cid).replace(...)` 写进 GameState（`Character` 上没有这个字段） | **要传一个 dict 进去** |
| `ability` | `get_ability_zero({})`，经 `abilities.ability(cid).replace(...)` 写入，写法同 `talent` | 同上 |
| `status_data` | **`get_status_zero({})`** | 字段叫 `status_data`，函数却叫 `get_status_zero` |
| `juel` | `get_juel_zero({})`，经 `abilities.juel(cid).replace(...)` 写入，写法同 `talent` | 同上 |
| `experience` | `get_experience_zero({})`，经 `abilities.experience(cid).replace(...)` 写入，写法同 `talent` | 同上 |
| `second_behavior` | `get_second_behavior_zero({})` | 同上 |
| `h_state` | `get_h_state_reset(cd.h_state)` | **只有 reset 版**，要把旧对象传进去 |
| `body_manage` | `get_body_manage_zero()` | 无参；管理类前提（如睡前锁门）会直接取 `[24]` |
| `favorability` | 手写 `{0: 0}` | 好感/信赖类前提直接取 `[0]`；口上里的 `favorability_ge_3` 会走到 |
| `talent[121]` | 在 `kernel_data.writing()` 里手写 `abilities.talent(cid)[121] = 1` | 罩杯素质 121~125 至少要有一个为 1：胸部成长/乳汁上限之类的代码用 `for tid in [121..125]: if talent[tid]: ...; break` 找罩杯，一个都没有时循环变量不赋值 → `UnboundLocalError`（报错在 `chest_grow`/`milk_max` 处） |
| `race` | 手写 `cd.race = <种族id>` | 默认 0=博士；生育方式、种族限定判定都查 `game_config.config_race[cd.race]`，测卵生/多胎要显式给对应种族 |
| `relationship` / `pregnancy` | 默认即可 | `Character()` 已带完整默认对象；测亲子链时手写 `relationship.mother_id/father_id/child_id_list` 并**两边都要挂**（母亲与玩家的 `child_id_list` 都 append） |
| 时间类字段 | `game_time.now() - datetime.timedelta(days=N)` | 造"N 天前"的 `fertilization_time/born_time` 用 timedelta 即可；但**断言显示文本时**要按 `game_time.get_sub_date` 的季月归并（只有 3/6/9/12 月）来预期，别硬算 `t.month` |

拿不准签名时**先查再写**，一次就能定：

```bash
./.conda/python.exe -c "import inspect; from Script.Design import attr_calculation as ac; print(inspect.signature(ac.get_talent_zero))"
```

### 断言写法

```python
# 注册断言：新东西是否既进了运行时又进了生成物
"my_premise" in constant.handle_premise_data
1726 in constant.settle_behavior_effect_data
"my_behavior" in game_config.config_behavior
"my_behavior" in game_config.config_behavior_effect_data          # 缺这条口上不会触发
any(t.behavior_id == "my_behavior" for t in game_config.config_talk.values())

# 直接调结算器
constant.settle_behavior_effect_data[<效果id>](<角色id>, add_time, change_data, now_time)
```

**`add_time` 不要传 0**：绝大多数结算器开头是 `if not add_time: return`，传 0 会静默什么都不做，断言变成假阴性。反过来，「`add_time=0` 时不生效」本身也值得单独断言一条。

更多经实战验证的断言样式：

```python
# CSV 新增列：buildconfig 会把空值字段整个删掉 → 对象缺属性，必须全表断言，而不是只看改过的几行
all(hasattr(r, "multiple_birth_num") for r in game_config.config_race.values())
sorted(c for c, r in game_config.config_race.items() if r.birth_type == 2) == [1, 7, 9, ...]   # 用户可能在实施中手改了 CSV，断言实际名单能立刻暴露

# 口上条数：按前提 token 计数，比看文件行数可靠（能顺带验证 buildconfig 已重建）
sum(1 for t in game_config.config_talk.values()
    if getattr(t, "behavior_id", "") == "give_gift" and "CVP_A1_Gift|39_G_0" in str(getattr(t, "premise", "")))

# 前提 token（带参数的通用前提）直接用 handle_premise.handle_premise(token, cid)
pl.behavior.gift_id = 39
handle_premise.handle_premise("CVP_A1_Gift|39_G_0", 0) == 1

# 面板使用条件：面板类实例化后直接调它的判定方法，配合 messages 记录拦截文案
panel = gift_panel.Gift_Panel(80); pl.target_character_id = 101
messages.clear(); panel.is_drug_effective(39, mom) is False and any("育儿室" in m for m in messages)

# 显示文本：把 WaitDraw 文本收进 messages 后断言关键词，同时断言「不该出现的词没出现」（如单胎文案里不含"胞胎"）
```

### 可记录、可控序列的 randint 桩

需要验证「调用了几次随机、每次的参数范围、按序命中/不命中」时，用一个记录型桩替换 `random.randint`（模块里的 `random` 就是全局 `random`，改一处全局生效，**用完必须还原**）：

```python
calls = []
class RandStub:
    def __init__(self, seq): self.seq = list(seq)
    def __call__(self, a, b):
        calls.append((a, b))
        return self.seq.pop(0) if self.seq else b      # 序列耗尽后返回上界 → 概率判定不命中

_real = random.randint
random.randint = RandStub([5, 1, 1, 100])              # 例：先抽胎数 5，再两轮命中、一轮不命中
some_module.check_xxx(cid)
check("随机调用序列", calls == [(4, 12), (1, 100), (1, 100), (1, 100)])
random.randint = _real
```

按阈值探测概率：若第 i 轮的期望概率为 `p_i`，让桩在第 i 轮返回 `int(p_i)`（应命中）或 `int(p_i)+1`（应不命中），就能在不看内部变量的前提下断言"每轮概率确实等于公式值"。

### 面板 / 事件级测试（模式 A 扩展）

生育事件、送礼面板这类"带按钮循环 + 输入 + 创建角色 + 成就结算"的重流程也能在模式 A 里跑通，关键是**让按钮循环能退出、把需要完整罗德岛 fixture 的旁路打桩**：

```python
# ① 按钮循环：面板普遍写成 `while 1: ... yrn = askfor_all(return_list); if yrn in return_list: break`，
#    默认的 `lambda *a, **k: ""` 会让它死循环。改成返回第一个可选项：
flow_handle.askfor_all = lambda return_list, *a, **k: return_list[0] if return_list else ""

# ② 调面板的 .draw()
born_event_panel.Born_Panel(mother_id).draw()

# ③ 输入框：记录询问文案并按序返回名字（可顺带断言"第N个女儿/姐姐/妹妹"之类的询问措辞）
asks = []; names = iter(["长女", "次女"])
character.input_name_func = lambda ask_text: (asks.append(ask_text), next(names))[1]

# ④ 成就结算用 warehouse.amount(1) 读 base.stock，库存里没有资源 1 时 KeyError: '1'，直接打桩（注意要打在**调用方模块**上）
born_event_panel.achievement_panel.achievement_flow = lambda *a, **k: None

# ⑤ 角色上线链 get_new_character 需要娱乐安排等完整 fixture → 只做登记的 stub
pregnancy_handle.character_handle.get_new_character = lambda cid, visitor_flag=False: cache.npc_id_got.add(cid)

# ⑥ 事件里的"随机选一名医生/干员"用 random.choice(列表)，列表空会 IndexError：
#    cache.npc_id_got 要非空，并给一个角色 profession = 3（医疗）
cache.npc_id_got = {101, 102}; cache.character_data[101].profession = 3

# ⑦ 想数"创建了几个角色"，包一层真函数而不是替换掉它：
born_calls = []; _real = character_handle.born_new_character
def stub_born(mother_id, name):
    nid = _real(mother_id, name); born_calls.append(nid); return nid
born_event_panel.character_handle.born_new_character = stub_born
```

打桩的通用原则：`from X import Y` 进来的名字要打在**使用它的模块**上（`born_event_panel.character_handle.xxx`），改 `character_handle.xxx` 本体也行（同一模块对象），但 `from Script.Design import character` 后 `character.input_name_func` 这种模块属性就必须改模块属性本身。

### 新增数据后必须重建

改了 CSV（前提/效果/行为/target/口上）后**先跑全量 `buildconfig.py` 再跑测试**，否则断言读到的是旧生成物。新增口上文件还要**先删 `data/Character_Talk.json`**——`auto_build_config.py` 见它存在就跳过口上重建。

```bash
LOG="<scratchpad>/build.log"
rm -f data/Character_Talk.json
./.conda/python.exe -u buildconfig.py > "$LOG" 2>&1; echo "EXIT=$?"; tail -20 "$LOG"
```

### 常见报错 → 病因速查

| 报错 | 病因 |
| --- | --- |
| `AttributeError: module 'attr_calculation' has no attribute 'get_xxx_zero'` | 置零函数名记错，查上表 |
| `TypeError: get_xxx_zero() missing 1 required positional argument` | 该置零函数要传 dict，查上表 |
| `KeyError` 出现在 `common_default.chara_base_state_adjust` | 漏了 `normal_config.system_setting` |
| `KeyError: '0'` 出现在 `cache.scene_data[...]` | 场景路径不是真实场景 |
| `KeyError: 24` 出现在 `handle_premise_body_manage` | 漏了 `body_manage` |
| `KeyError: 0` 出现在 `handle_favorability_*` | 漏了 `favorability`（口上前提会走到） |
| 断言全过但数值没变 | `add_time` 传了 0 |
| 新前提/新口上"没注册" | 漏跑 `buildconfig.py`，或新口上没删 `Character_Talk.json` |
| 进程"卡死"、看不到任何输出 | 用了 `| tail` 管道，见铁律 4 |
| `SyntaxError: invalid syntax`，报错行里有 `��` | heredoc/stdin 里的中文被 GBK 解码，改写成脚本文件，见铁律 7 |
| `UnboundLocalError` 出现在 `chest_grow` / 乳汁上限 | fixture 没有罩杯素质，加 `talent[121] = 1` |
| `KeyError: '1'` 出现在 `achievement_panel.achievement_flow` | 成就结算用 `warehouse.amount(1)` 读 `base.stock`，库存里没有资源 1，打桩 `achievement_flow` |
| `IndexError` 出现在 `random.choice(doctor_id_list)` 之类 | 事件要随机选医生/干员，`npc_id_got` 为空或没有 profession=3 |
| 面板测试永不返回（无报错） | `askfor_all` 桩返回了不在 `return_list` 里的值，按钮循环退不出 |
| 调 `get_new_character` 后一连串 KeyError | 上线链要完整罗德岛 fixture，用只登记 `npc_id_got` 的 stub |
| 生成物里种族/道具名单与预期不符 | 用户可能在实施中手改了 CSV（本轮就遇到过追加种族），先 `awk`/grep 看实际 CSV 再改断言 |

## 模式 B：行为循环诊断

下面「第一步～第八步」是模式 B 的完整流程（模式 A 只需要第一步、第二步，再加上「模式 A」一节的两条全局前置与 fixture）。

### 第一步：初始化链（照抄 game.py 顺序，约 3 秒）

```python
import auto_build_config                       # 增量构建数据（数据已构建时约0.4s）
from Script.Config import normal_config
from Script.Core import game_type, cache_control
cache_control.cache = game_type.Cache()        # 必须在 game_config.init() 之前
normal_config.init_normal_config()
from Script.Config import game_config, character_config
game_config.init()
character_config.init_character_tem_data()
from Script.Config import map_config
map_config.init_map_data()
from Script.Design import character_handle, game_time, character_behavior, instuct_judege, map_handle
import Script.Settle, Script.StateMachine      # 注册全部结算器与状态机，缺了会 KeyError
from Script.Core import constant, save_handle, flow_handle
from Script.UI.Moudle import draw
from Script.Modules.save_load import kernel_state
character_handle.init_character_tem()
kernel_state.reset_clock(kernel_state.first_clock())
```

顺序不能乱：`cache` 先建、`normal_config` 先于 `game_config`、`Script.Settle`/`Script.StateMachine` 必须 import（装饰器注册）。Mod 系统可跳过（测试不需要）。

### 第二步：屏蔽 UI（防止任何绘制/等待阻塞）

```python
for cls_name in dir(draw):
    cls = getattr(draw, cls_name)
    if isinstance(cls, type) and hasattr(cls, 'draw'):
        try: cls.draw = lambda self, *a, **k: None
        except Exception: pass
flow_handle.askfor_all = lambda *a, **k: ""
flow_handle.askfor_wait = lambda *a, **k: None
```

需要断言"某段文本是否被绘制"（如吵醒提示）时，用记录型 stub 替换对应类：

```python
messages = []
def record_draw(self, *a, **k):
    if getattr(self, 'text', None) and '吵醒' in str(self.text):
        messages.append(str(self.text).strip())
draw.WaitDraw.draw = record_draw
```

### 第三步：读档与状态体检

```python
save_handle.input_load_save("5")     # 存档目录 save/5/，纯读入内存
cache = cache_control.cache
pl = cache.character_data[0]
```

- 按名字找角色：遍历 `cache.character_data.items()` 比对 `cd.name`。
- 体检清单（排查行为类 BUG 时先打印这些）：`behavior.behavior_id / duration / start_time`、`state`、`position`、`target_character_id`、`needs.of(cid)`（疲劳 `tired`、饥饿 `hunger`、尿意 `urine`、乳汁 `milk`、熟睡值 `sleep`、体力 `hit` 与上限 `hit_max`、气力 `mana` 与上限 `mana_max`）、`sp_flag` 全量（`sleep / rest / tired / sleep_h_awake / unconscious_h / imprisonment / is_follow / is_h / hidden_sex_mode`）、醉酒等级 `drunk_sex_common.get_drunk_level(cid)`、安眠药 `h_state.body_item[9][1]`、`work.work_type`、`entertainment.entertainment_type`。
- 需要移动角色到某场景：`map_handle.character_move_scene(旧位置, 新位置, cid)`。

### 第四步：下玩家的指令，带护栏地推进内核（核心）

玩家的指令经 `tests/world.py` 的 `act` 下：内核一步一步推进（`core.step()`），玩家选行动时跑指令的处理函数（`Script/System/Instruct_System/handle_instruct.py` 里 `@add_instruct` 的函数，按指令中文名搜），推进到玩家下一次选行动时停下。时钟由内核推进，当前时刻用 `game_time.now()` 读。

给 `core.step` 包一层护栏：时钟停在同一分钟推进太多步就是死循环，抛出异常中止推进，并报告这一分钟开始行动最多的角色：

```python
from Script.Kernel import core
from Script.Design import character_behavior, game_time
from Script.System.Instruct_System import handle_instruct
from tests.world import act

STEP_LIMIT = 500
class StepLimitReached(Exception): pass
starts, same_minute, stalled = {}, {}, 0
real_settle_start, real_step = character_behavior.settle_start, core.step

def counted_settle_start(cid, minutes):        # 每个角色开始行动都经过这里
    starts[cid] = starts.get(cid, 0) + 1
    same_minute[cid] = same_minute.get(cid, 0) + 1
    real_settle_start(cid, minutes)

def guarded_step():
    global stalled
    if stalled >= STEP_LIMIT:
        raise StepLimitReached(f"时钟停在 {game_time.now()}：{sorted(same_minute.items(), key=lambda kv: -kv[1])[:5]}")
    clock = core.state().clock
    real_step()
    if core.state().clock == clock:
        stalled += 1
    else:
        stalled = 0
        same_minute.clear()

character_behavior.settle_start = counted_settle_start
core.step = guarded_step
act(handle_instruct.handle_play_instrument)
```

判读标准：各角色开始行动的次数随指令时长增长；时钟停在同一分钟超过上限即为活锁，报告里开始行动最多的角色就是卡死角色。是否异常以同一存档、同一指令的未修复基线为准。

### 第六步：逐轮内窥（定位循环形态）

对可疑角色，在每次开始行动（`character_behavior.settle_start`）前后打印行为四元组（behavior_id / duration / start_time / state）。若同一分钟里反复开始行动、前后打印完全相同，说明**发生了赋予→掐死的隐形循环**，需要包装中间函数看到其中的状态。`harness_template.py` 的 `probe` 一次包好下面这几处：

```python
orig_choose = handle_npc_ai.choose_state_machine
def wrap_choose(cid):
    r = orig_choose(cid)
    if cid in WATCH:
        cd = cache.character_data[cid]
        print(f"    [选状态机] cid={cid} 返回={r} bhv={cd.behavior.behavior_id} dur={cd.behavior.duration} state={cd.state}")
    return r
handle_npc_ai.choose_state_machine = wrap_choose   # 内核按 handle_npc_ai.xxx 调用，替换模块属性即生效

orig_int = handle_npc_ai.judge_interrupt_character_behavior
def wrap_int(cid):
    pre = (cache.character_data[cid].behavior.behavior_id, cache.character_data[cid].behavior.duration)
    r = orig_int(cid)
    if cid in WATCH:
        cd = cache.character_data[cid]
        print(f"    [中断判定] cid={cid} 前={pre} 返回={r} 后=({cd.behavior.behavior_id},{cd.behavior.duration})")
    return r
handle_npc_ai.judge_interrupt_character_behavior = wrap_int

# 学生赶去上课的截短（Plan 32 起）不在 judge_interrupt_character_behavior 里：
#    character_behavior 的 NPC 分支在实时结算之前调 judge_student_leave_truncate，要记截短就一并包它
orig_trunc = handle_npc_ai.judge_student_leave_truncate
def wrap_trunc(cid):
    pre = cache.character_data[cid].behavior.duration
    r = orig_trunc(cid)
    if cid in WATCH and r:
        print(f"    [学生截短] cid={cid} 时长 {pre} → {cache.character_data[cid].behavior.duration}")
    return r
handle_npc_ai.judge_student_leave_truncate = wrap_trunc
```

同法可包装 `judge_character_status`、`realtime_settle.character_aotu_change_value` 等任意环节。

### 第七步：控制随机分支

概率判定（如吵醒 `weak_rate >= random.randint(1,100)`）会让复现不稳定。强制命中：

```python
random.seed(1)
random.randint = lambda a, b: a    # 所有 randint 返回下界 → 概率判定必中
```

注意这会影响全部随机（AI 选择、数值浮动）；只需固定可复现时用 `random.seed` 即可，需要"必中/必不中"某判定时才整体替换 `randint`。

### 第八步：内存模拟修复 → 确认收敛 → 再改源码

改源码前，先把候选修复以 monkeypatch 形式打在内存里重跑护栏循环，收敛了才动手：

```python
_orig = handle_npc_ai.judge_interrupt_character_behavior
def patched(cid):
    cd = cache.character_data[cid]
    if <候选修复条件>: return 0
    return _orig(cid)
handle_npc_ai.judge_interrupt_character_behavior = patched
# 重跑第四步，断言推进到了玩家下一次选行动、各角色开始行动的次数正常
```

改完源码后**去掉补丁重跑同一 harness** 做最终验证，再补一组回归（如：修复烂醉豁免后，验证非烂醉浅睡者仍会被吵醒且收敛）。

## 死循环排查心法

行为循环卡死 = 时钟停在同一分钟，某些角色反复开始行动。下面是旧主循环（`judge_character_status_time_over`）时代归纳的成因，内核里的对应判断见 `Script/Modules/gameplay_resolution/`。`judge_character_status_time_over()` 只有两条 return 0 路径：

- **A 路径**（`add_time <= 0`）：行为时长为 0/负 → 重置为空闲、duration=1、start=now、返回 0；
- **B 路径**（`time_judge == 1`，结束时间早于当前时间）：重置行为、start_time=end_time、返回 0。

单次 return 0 是正常的（给 AI 一轮重选机会）；**死循环 = 每一轮重新选出的行为的"结束时间 ≤ 当前时间"且前提永不变化**。已知的三类成因：

1. **同轮掐死类**：`find_character_target` 赋予行为后，同轮的 `judge_interrupt_character_behavior`（休息/睡眠/工作淋浴三个分支）或 `settle_sleep` 自然醒用 `end_now=2` 立即终止它，而选择前提（如烂醉 `drunk_level_3`、安眠药、特殊 flag）不受终止影响 → 每轮重复。排查点：中断分支的豁免条件是否与所有可重选该行为的目标前提互斥（目标清单查 `data/target/default/target.csv`，按状态机 id 搜 `,44,` 这类）。
2. **无效时长类**：状态机算出 duration ≤ 0（如"睡到玩家醒来时间"的减法）且 `add_time=0` 的结算会跳过全部 flag 效果（`if not add_time: return` 模式），前提永不失效。
3. **start_time 回拨类**：B 路径或某处把 start_time 设回过去，且每轮被重新回拨。

对应的结构性护栏（已在代码中，排查时先确认它们还在）：`judge_interrupt_character_behavior` 开头的"本轮刚赋予的行为不打断"（学生截短 `judge_student_leave_truncate` 开头是同一道守卫，Plan 32）；`find_character_target` 状态机执行后的 duration≥1 钳制；`judge_character_status_time_over` 的 `add_time <= 0` 拦截。

## 快速查表

| 要找什么 | 位置 |
| --- | --- |
| 主循环/时间结算 | `Script/Kernel/core.py`（`step`）、`Script/Modules/gameplay_resolution/`、`Script/Design/character_behavior.py`（`settle_start`） |
| NPC AI 选择/打断 | `Script/Design/handle_npc_ai.py`（`choose_state_machine`、`judge_interrupt_character_behavior`、学生截短 `judge_student_leave_truncate`（Plan 32，排在实时结算之前）） |
| 实时数值/睡眠/吵醒 | `Script/Settle/realtime_settle.py`（`settle_sleep`、`settle_sleep_h`） |
| AI 目标配置 | `data/target/default/target.csv`（格式：id,状态机id,前提管道,类型,注释） |
| 状态机 id ↔ 名称 | `Script/Core/constant/StateMachine.py`；实现在 `Script/StateMachine/default.py` |
| 行为时长/标签 | `data/csv/Behavior_Data.csv`；行为→结算效果 `data/csv/Behavior_Effect.csv` |
| 前提函数 | `Script/Design/handle_premise/`（按主题分模块） |
| 结算效果实现 | `Script/Settle/default.py`（`@add_settle_behavior_effect(效果id)`） |
| 读档 API | `Script/Core/save_handle.py`（`input_load_save(save_id)`） |
| 置零/初始化函数 | `Script/Design/attr_calculation.py`（`get_*_zero` / `get_zero_dirty` / `get_*_reset`，签名不规律，用 `inspect.signature` 查） |
| 前提常量与分组 | `Script/Core/constant_promise.py` |
| 结算器常量与分号段 | `Script/Core/constant_effect.py`（`BehaviorEffect` 按分类分号段，新号要落在本类段末） |
| 本 skill 的两个模板 | `unit_test_template.py`（模式A，可直接跑）、`harness_template.py`（模式B） |

## 运行方式

统一用**重定向到文件**，不要接管道（见铁律 4）。`<scratchpad>` 换成本会话的 scratchpad 目录。

```bash
# 直接跑模板文件
LOG="<scratchpad>/run.log"
timeout 300 ./.conda/python.exe -u .agents/skills/headless-game-test/unit_test_template.py > "$LOG" 2>&1
echo "EXIT=$?"; tail -40 "$LOG"

# 或写自己的脚本到 scratchpad 再跑（脚本开头要 sys.path.insert(0, r"c:\code\erArk") 与 os.chdir 到仓库根）
timeout 300 ./.conda/python.exe -u "<scratchpad>/my_test.py" > "$LOG" 2>&1
echo "EXIT=$?"; tail -40 "$LOG"
```

`EXIT=124` 表示进程被 `timeout` 终止，见铁律 2。`unit_test_template.py` 末尾调用 `os._exit(0 if not FAIL else 1)`。断言全部通过时它以退出码 0 结束，有断言失败时以 1 结束。不设退出码的脚本正常跑完时，退出码为 0，与断言结果无关。要让自己脚本的退出码反映断言结果，就在脚本末尾也这样调用。

**读中文输出**：Git Bash 的 `cat`/`grep` 在 GBK 控制台下会把中文显示成乱码（文件本身没问题）。要看清楚就转一道：

```bash
grep -n "关键词" 某文件 | ./.conda/python.exe -c "import sys;print(sys.stdin.buffer.read().decode('utf-8'))"
```
