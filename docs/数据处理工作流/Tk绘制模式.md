# Tk 绘制体系详解

> 适用于 Tk 模式的渲染、命令与输入处理路径。本文梳理了从入口、底层 IO、绘制组件到上层面板的完整链路，并给出扩展与排错要点。

## 1. 启动流程

- **主流程**：`game.py` 创建 `Script.Protocol.ThreadedUiPort` 与 `Script.Frontend.Tk.app.TkFrontend`，再依次执行：
  1. 调用 `Script.Core.game_init.start(start_flow.start_frame, port, frontend.init_config)` 配置端口、把前端按实际屏幕算出的尺寸配置写入 `normal_config.config_normal`，并启动名为 `"flowthread"` 的后台工作线程运行游戏主流程。
  2. 调用 `frontend.run()` 执行常用字符预热、绑定键鼠事件、启动事件泵并进入 Tk 主循环。
  3. Tk 主循环退出后调用 `port.close("window closed")` 通知端口关闭，并等待工作线程在超时内正常退出。

## 2. Tk 前端包（`Script.Frontend.Tk`）

- **窗口装配（`window.py`、`screen.py`）**：仅在实例化 `Window` 时创建 Tk 根窗口、文本输出区 `Text`、滚动条与指令输入框 `Entry`，导入前端模块不创建根窗口。`screen.init_config()` 按屏幕尺寸钳制窗口宽高并计算字号，窗口图标取自 `image/logo.png`。
- **字体加载（`fonts.py`）**：`load_local_fonts()` 扫描 `static/fonts` 并在 Tk 中注册字体与别名，本地字体文件无法被 Tk 加载时回退同名系统字体。
- **事件泵与输入门控（`app.py`、`gate.py`）**：`TkFrontend._pump()` 通过 `after(1)` 每次批量拉取最多 256 条后端事件并交给 `Renderer.render()`。输入门控状态由 `gate.InputGate` 维护，收到渲染或清屏事件时关闭门控（`disarm`），收到 `Pause`、`Choose` 或 `InputText` 请求时经 `after_idle` 开启门控（`arm`），并在 `Choose` 与 `InputText` 就绪时聚焦输入框。
- **渲染与按钮标签（`render.py`、`tooltip.py`）**：`Renderer` 处理 `TextOp`、`ButtonOp`、`ImageButtonOp`、`ImageOp`、`ImageBatchOp`、`StyleDefOp`、`BgColorOp` 与 `ClearButtonsOp`，为每个按钮创建唯一 tag 并绑定 `<1>`、`<Enter>`、`<Leave>`、`<Motion>` 事件与 350ms 延迟悬停提示。
- **输入框与历史（`app.py`、`history.py`）**：`TkFrontend.submit_input()` 在输入门控开启时读取 `Entry` 文本，记入前端 `InputHistory`（最多 21 条，支持上下键浏览），再按当前挂起请求向端口提交 `Continue`、`SubmitChoice` 或 `SubmitText` 应答并清空输入框。窗口关闭时提交 `Cancel("window closed")` 并销毁根窗口。

## 3. IO 管线（`Script.Core.io_init`）

- **统一入口**：文本、图片、样式与按钮输出经由 `io_init.*` 写入已配置的 `Script.Protocol.UiPort`。
- **协议端口**：`era_print`、`image_print`、`image_list_print`、`io_print_cmd`、`io_print_image_cmd` 与 `io_clear_cmd` 发送不可变 `RenderOp`，`clear_screen` 与 `clear_order` 发送 `Clear` 事件。
- **样式初始化**：`init_style()` 遍历 `game_config.config_font` 调用 `frame_style_def()` 发送 `StyleDefOp`，并生成 `bold`、`underline`、`italic` 及其与基础样式的组合样式。
- **阻塞输入、刷出与跳过模式**：`ask_choice()`、`ask_text()` 与 `wait_continue()` 直接通过端口等待前端应答，无定时轮询。`flush()` 与 `flushing()` 可在不触发输入等待的情况下立即刷出已缓冲的渲染操作（供 AI 流式文本等逐块显示）。`set_skip_pauses()` 直接设置端口的跳过暂停开关，模块自身不另存跳过状态，`end_session()` 发出 `Exit` 事件并抛出 `SessionCancelled` 结束工作线程。

## 4. 绘制组件层（`Script.UI.Moudle.draw`）

> 这里定义了所有可复用的绘制原件，面板层只负责装配。

### 4.1 文本类
- `NormalDraw`：基础文本绘制，使用 `text_handle.get_text_index` 计算宽度，按 `self.width` 自动换行。
- `FullDraw`：不处理换行，直接输出。
- `WaitDraw`：绘制完成后调用 `flow_handle.askfor_wait()`；用于需要暂停的剧情输出。
- `LineFeedWaitDraw`：以 `\n` 分段并逐行调用 `flow_handle.askfor_wait()` 等待。
- `CenterDraw`/`RightDraw`/`LeftDraw`：对齐变种，内部调用 `text_handle.align()`。
- `CenterMergeDraw`/`LeftMergeDraw`：合并多个 `NormalDraw` 并控制整体宽度。

### 4.2 图形类
- `ImageDraw`：透传图片 ID 给 `io_init.image_print`。
- `BarDraw`：根据配置 `game_config.config_bar` 拼装若干 `ImageDraw` 构成进度条。
- `CharaDraw`：同理，根据角色立绘配置生成 `ImageDraw` 序列。
- `InfoBarDraw`/`InfoCharaDraw`：在进度条/立绘前后额外挂载文本。

### 4.3 按钮类
- `Button`：核心按钮控件，内部调用 `py_cmd.pcmd()` 完成命令绑定。
- `ImageButton`、`CenterButton`、`LeftButton`：分别处理图片按钮、固定宽度按钮、左对齐按钮。
- `LineDraw`、`TitleLineDraw`、`LittleTitleLineDraw`：绘制分隔线与标题装饰。
- `ExpLevelDraw`、`StatusLevelDraw`：根据数值计算评级并输出对应样式文本。

所有 `draw` 对象的 `draw()` 最终都会调用 `io_init`。

## 5. 面板与流程装配层

- `Script.UI.Moudle.panel` 提供通用面板骨架，例如：
  - `SingleColumnButton`：将若干 `draw.Button` 竖向排列。
  - `OneMessageAndSingleColumnButton`：常见的“上方文本 + 下方选项”组合。
  - `CenterDrawTextListPanel`、`LeftDrawTextListPanel`：按列对齐输出列表。
  - `LeftDrawTextListWaitPanel`：绘制完成后调用 `flow_handle.askfor_wait()` 等待确认。
- 业务面板位于 `Script/UI/Panel/*`，多数 `draw()` 函数中：
  1. 收集数据并实例化 `draw.*` 元素。
  2. 调用 `io_init.clear_cmd()`/`io_init.clear_screen()` 等更新 UI。
  3. 使用 `flow_handle` 监听按钮结果或等待输入。
- 面板入口映射由 `Script.UI.Flow` 系列注册（例如 `normal_flow.py` 通过 `handle_panel.add_panel` 指定面板 ID → 绘制函数），供行为循环或指令调用。

## 6. 命令绑定与输入调度

- **绑定阶段**：`py_cmd.pcmd()` -> `flow_handle.print_cmd()` -> `flow_handle.bind_cmd()` 将命令编号与处理函数写入 `constant.cmd_map`。
- **渲染阶段**：`flow_handle.print_cmd()` 同时调用 `io_init.io_print_cmd()`，由 Tk 侧转为带事件的 tag。
- **输入阶段**：
  1. 玩家点击按钮或在输入框按回车，`TkFrontend.submit_input()` 经 `InputGate.submit()` 校验并向会话端口提交对应协议应答。
  2. `flow_handle.order_deal()` 按输入类别请求端口：`askfor_all` 与 `askfor_int` 通过 `_offering()` 传入各自可接受选项并发出 `Choose`，`"order"` 模式发出包含 `cmd_map` 全部键的 `Choose`，`askfor_str` 与 `"console"` 模式发出 `InputText`（`allow_empty = not donot_return_null_str`），`askfor_wait` 发出 `Pause`。非空输入会记入 `view.input_cache` 与 `orders.accept`，`"order"` 模式中命令存在于 `cmd_map` 时执行绑定函数，否则调用尾处理函数。
  3. `askfor_all`、`askfor_int` 与 `askfor_str` 基于 `order_deal()` 循环等待合法输入。
- **默认流程**：`flow_handle.set_default_flow()` 可以注册默认逻辑（常用于绘制后的刷新）。`game_init.init()` 会在主循环中 `call_default_flow()`。

## 7. 等待控制与跳过模式

- **事件绑定（`Script.Frontend.Tk.app`）**：`TkFrontend.run()` 在 Tk 根窗口上绑定鼠标与键盘事件：
  - 左键：聚焦输入框，处于暂停等待时提交 `Continue(skip_pauses=False)`，否则在未命中按钮时提交当前输入框内容。
  - 右键：仅在无挂起请求或当前请求为 `Pause` 时经 `InputGate.right_click()` 预排跳过，已就绪且处于暂停等待时提交 `Continue(skip_pauses=True)`，处于选项或文本等待且未命中按钮时提交当前输入框内容而不预排跳过。
  - 上/下方向键：通过 `InputHistory` 浏览最近 21 条输入记录并支持恢复草稿。
  - 回车：调用 `submit_input()`，暂停期间输入空文本则提交 `Continue`，输入非空文本则清空输入框并继续等待。
- **跳过模式**：游戏侧通过 `flow_handle.set_skip_pauses(True)`（转调 `io_init.set_skip_pauses` 设置端口开关）或玩家右键推进暂停开启跳过模式。期间 `flow_handle.askfor_wait()` 调用 `io_init.wait_continue()`，端口会在刷出缓冲输出后对可跳过暂停立即返回。按协议规则，跳过模式会在下一次 `Choose`、`InputText` 或 `sync_panel` 请求时自动关闭，主场景面板也会显式调用 `flow_handle.set_skip_pauses(False)`。

## 8. 样式、文本宽度与对齐

- `Script.Core.text_handle`：
  - `get_text_index()` 使用 `wcwidth` 计算字符显示宽度，并去除类似 `<style>` 的样式标签。
  - `align()` 根据列数和宽度生成左右/居中对齐文本，广泛用于 `CenterDraw`/`LeftButton` 等。
- 样式数据来源于 `game_config.config_font` & `config_font_data`，`io_init.init_style()` 会注册所有组合样式（含 bold/underline/italic 修饰符）。
- `normal_config.config_normal.text_width` 决定单行宽度，是大多数 `draw` 对象的默认 `width`。

## 9. 图片与资源处理

- **图片加载**：`Script.Core.image_catalog` 在导入时通过 `Script.Core.image_path_index` 扫描 `image/` 目录，建立图片名到路径索引（`image_path_data`）与角色索引（`image_data_index_by_chara`），不解码图片。`Script.Frontend.Tk.image_cache.image_data` 在某张 `.png` 首次取图时按 `set_font_scaling()` 设置的系数（前端初始化设为 `window.normal_font.measure("A") / 11`，未设置时为 `1.0`）缩放并缓存为 `PhotoImage`（解码失败时缓存 1x1 透明图），并保留至进程结束。
- **图片绘制**：
  - `draw.ImageDraw.draw()` 调用 `io_init.image_print()` 发送 `ImageOp`。
  - `Script.Frontend.Tk.render.Renderer` 在 `textbox` 中调用 `image_create` 显示图片。
  - 图片按钮（`ImageButton`）通过 `io_print_image_cmd()` 发送 `ImageButtonOp` 并由渲染器绑定点击事件。

## 10. 扩展指引

1. **新增文本/组件**：
   - 优先复用 `draw.py` 中的基础类；若需自定义，保持 `draw()` 中只调用 `io_init`/`py_cmd` 等抽象层，避免直接引用 Tk API。
2. **新增面板**：
   - 在 `Script/UI/Panel` 下建模块，组合 `draw.*` 与 `panel.*` 组件。
   - 通过 `handle_panel.add_panel` 注册到对应 Flow，或在行为循环中直接调用。
3. **新增样式**：更新 `data/csv` → `buildconfig.py` 生成配置，再调用 `io_init.init_style()` 时自动注册。
4. **新增图片**：将 `.png` 文件放入 `image/` 并保持命名与配置一致。需要差分立绘时按 `角色名_xxx.png` 命名。`Script.Core.image_catalog` 导入时会自动建立路径索引与角色索引。

## 11. 调试与排错建议

- **输出异常/乱码**：检查 `io_init.init_style()` 是否执行；确认字体文件是否被 `load_local_fonts()` 正常加载（查看控制台日志）。
- **命令点击无反应**：确认 `py_cmd.pcmd()` 绑定的 `cmd_id` 是否唯一，`flow_handle.cmd_map` 有对应条目；`io_init.clear_cmd()` 是否被提前清空。
- **等待卡死**：检查前端 `InputGate.armed` 与 `InputGate.request`，并排查游戏侧是否存在未响应的 `askfor_wait()` 或未关闭的跳过状态。
- **图片不显示**：确认 `image/*.png` 名称与 `game_config.config_image` 中一致，首次显示该图片时控制台是否输出「加载图片失败」。

---

通过上述链路可以快速定位 Tk 渲染的各个环节：配置 → IO → 绘制组件 → 面板 → 行为循环。在开发新 UI 或排查显示问题时，优先确认是否遵循了这些抽象层，借助 `cache` 与 `flow_handle` 维护的状态避免直接操作底层 Tk 控件，从而简化维护。