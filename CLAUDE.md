# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

erArk is an R18 adult game focused on Arknights characters, developed in Python. The game is a text-based simulation with character interactions, events, and various gameplay systems.

## Core Development Commands

### Running the Game
```bash
python game.py
```
On startup, `game.py` imports `auto_build_config.py`, which performs an **incremental** rebuild of game data (it skips talk data when `data/Character_Talk.json` / `data/Talk_Common.json` already exist). So for most CSV edits, simply running the game is enough.

### Building Game Data
```bash
python buildconfig.py  # Full rebuild: CSV configurations -> JSON data + config_def.py + PO files
python init_data.py    # Pre-warm runtime caches (CI runs this after buildconfig)
python buildpo.py      # Extract translatable strings from .py files into PO files
python buildmo.py      # Compile MO files for every locale except zh_CN (needs gettext msgfmt, or polib from requirements-dev.txt); --out DIR writes elsewhere
```
Note: `buildata.py` is NOT part of the data build chain despite its name — it is a developer helper for generating premise/settlement boilerplate (inserts constants into `constant_promise` / `handle_premise`, converts CSV to premise and settle definitions via its `mode` variable).

### Dependencies Installation
```bash
pip install -r requirements.txt
```
Key dependencies: `openai` + `google-genai` (AI text generation), plus `Pillow`, `numpy`, `ephem`, `psutil`, `wcwidth`.

### Testing Individual Components
The game uses a debug mode (configured in config.ini) for testing. Set `debug = 1` to enable debug features.

Tests live under `tests/`. Install `tests/requirements.txt` and run them from the repo root:
- `pytest tests/fast`: the fast layer. It does not boot the game; test classes inherit `tests.fast.base.FastTestCase`.
- `pytest tests/slow --forked`: the slow layer. `--forked` runs each test in its own process; test classes inherit `tests.slow.base.SlowTestCase`, whose `setUp` boots the game (`FullWorld` in `tests/world.py`) and starts a new game. On systems without `os.fork` (Windows) the whole layer is skipped.
- The child-raising suite in `tests/education/` is a set of standalone scripts on its own `_bootstrap.py`. The slow-layer test `tests/slow/test_education_suite.py` runs each script in its own process: `pytest tests/slow --forked -k EducationSuiteTest -rP` (`-rP` also prints the output of passing scripts). One script also runs alone: `python -u tests/education/test_<name>.py`.

New tests go into one of the two layers. `tests/fast/test_registration.py` fails on any `test_*.py` outside them that its `NOT_IN_LAYERS` does not list.

## High-Level Architecture

### Core Game Flow
1. **Entry Point**: `game.py` - Auto-builds config data (`auto_build_config`), initializes configs (`normal_config`, `game_config`), loads the mod system (`init_mod_system()`), character templates, and map data, resets the kernel clock (`kernel_state.reset_clock`), creates `ThreadedUiPort` with a random token and `TkFrontend(port, token)`, starts the game thread with `game_init.start(start_flow.start_frame, port, frontend.init_config)`, and runs the Tk main loop with `frontend.run()`
2. **Game Initialization**: `Script/Core/game_init.py` - Sets up the game environment, styles, and main flow
3. **Main Frame Loop**: `Script/Design/start_flow.py` - Contains UI handling and panel management
4. **Main Behavior Loop**: `Script/Design/character_behavior.py` - The actual game simulation loop

### Script Directory Layout
- **`Script/Config`** - Config loading (`game_config.py`, `map_config.py`, `character_config.py`, `normal_config.py`) and the generated `config_def.py`
- **`Script/Core`** - Engine layer: save (`save_handle.py`), IO (`io_init.py`), flow handling (`flow_handle.py`), mod manager (`mod_manager.py`), game data types (`game_type.py`)
- **`Script/Design`** - Main game logic: behavior loop, NPC AI, map/navigation, talk, settlement dispatch (`settle_behavior.py`), etc.
  - **`Script/Design/handle_premise/`** - The premise (condition) system is a package, split by topic into ~20 modules (`handle_premise_H.py`, `handle_premise_place.py`, `handle_premise_ability.py`, `handle_premise_talent.py`, ...) with the main entry in `__init__.py`
- **`Script/Settle`** - Settlement modules: `default.py`, `common_default.py` (universal settlement), `Second_effect.py` (second-stage effects), `default_cloth.py`, `item_effect.py`, `realtime_settle.py`, `past_day_settle.py`, `sleep_settle.py`
- **`Script/StateMachine`** - Atomic NPC behavior modules (`default.py`, e.g. movement), executed via `Script/Design/handle_state_machine.py`
- **`Script/System`** - Self-contained subsystems: `Cooking_System`, `Dormitory_System`, `Education_System` (schooling & child-raising: timetables, classes, growth), `Field_Commission_System`, `First_Record_System` (sexual first-experience record system & panel), `Instruct_System` (instruction panel & categories), `Item_System`, `Medical_System`, `Official_Event_System` (official-duty events), `Pregnancy_System`, `Sex_System`
- **`Script/UI`** - `Flow` (title/creator/normal flows), `Moudle` (draw/panel primitives), `Panel` (60+ feature panels)

### Key Systems

#### Configuration System
- **CSV Data**: Game data is stored in CSV files under `data/csv/`, plus `data/talk/`, `data/talk_common/`, `data/target/`, `data/ui_text/`, `data/event/`, `data/character/`
- **Build Process**: `buildconfig.py` (full) / `auto_build_config.py` (incremental, run on game start) read CSVs and generate:
  - JSON data files (`data/data.json`, `Character.json`, `Character_Talk.json`, `Character_Event.json`, `Talk_Common.json`, `ui_text.json`, `Cook_Question.json`)
  - Python config definitions (`Script/Config/config_def.py`)
  - Localization PO files (`data/po/`)

#### Character System
- **Character Templates**: Stored in `data/character/` as CSV files
- **Character Management**: `Script/Design/character.py` and `character_handle.py`
- **Character Behaviors**: `Script/Design/character_behavior.py`
- **AI System**: `Script/Design/handle_npc_ai.py` and `handle_npc_ai_in_h.py`

#### Event & Talk System
- **Event Data**: JSON files in `data/event/`, processed by `Script/Design/event.py`
- **Talk Data**: Per-character dialogue CSVs in `data/talk/`; generic dialogues in `data/talk_common/` organized by action type (`action_A`, `action_B1/B2`, `body_part`, ...)
- **Behavior Targets**: `data/target/` holds target definitions used by the NPC AI

#### UI System
- **Flow Management**: `Script/Core/flow_handle.py`
- **Drawing System**: `Script/UI/Moudle/draw.py`
- **Panels**: Various UI panels in `Script/UI/Panel/` and inside `Script/System/*` subsystems

#### Save System
- **Save Management**: `Script/Core/save_handle.py`
- **Kernel Save Modules**: `Script/Modules/save_load/` (`index.py`, `kernel_state.py`, `legacy_pickle.py`, `upgrade.py`, `reset.py`, `settings.py`, `autosave.py`) manages single-file `save.json` saves, read-only legacy saves, and `GameState` resets

#### Mod System
- **Manager**: `Script/Core/mod_manager.py` (`ModInfo` / `ModManager`); `init_mod_system()` is called from `game.py` at startup (failures only warn, never abort)
- **Capabilities**: mod metadata (`mod_info.json`) with dependencies / incompatibilities / load priority, script-level **function replacement** (original functions are saved and swapped), and asset overrides (e.g. replacing a CSV)
- **Configuration**: `mod/mod_config.json` (`enabled_mods`, `load_order`); sample mod in `mod/semen_boost/`

#### AI Text Generation
- **Core**: `Script/Design/handle_chat_ai.py` — supports OpenAI-compatible APIs (including DeepSeek) and Google Gemini; entry point `judge_use_text_ai()` returns the original text unless AI chat is enabled in the in-game settings
- **System prompts**: `data/ui_text/text_ai_system_promote.csv`
- **API keys**: read from `ai_chat_api_key.csv` at the repo root (`GEMINI_API_KEY` / `DEEPSEEK_API_KEY` rows) — treat this file as sensitive and never commit real keys
- **Corpora/prompts for tooling**: `tools/AI/`

## Code Guidelines

1. **Comments**: All comments should be in Chinese
2. **Function Documentation**: Every function must have Chinese comments describing:
   - Input parameters and types
   - Return values and types
   - Function purpose
3. **Code Sections**: Each code section should have comments explaining its purpose
4. **Code Style**: black (`black .` at the repo root) formats the code with 4-space indent and 80 columns, and prefers double quotes. ruff (`[tool.ruff]` in `pyproject.toml`) checks the rule groups listed in `select` under `[tool.ruff.lint]`. `CONTRIBUTING.md` explains each group. pyrefly (`[tool.pyrefly]` in `pyproject.toml`) checks every module with one configuration. It also checks the bodies of functions without type annotations. It does not require annotations on functions, and honours no ignore comments. The ratchet runs pyrefly with `--min-severity=error`, and CI checks its errors against `.lint-baseline.tsv` via `python tools/pyrefly_baseline_check.py`. ruff and pyrefly check the code under a ratchet rule. New code must be fully clean. Changed code may never get worse than its entry in `.lint-baseline.tsv`. The generated `Script/Config/config_def.py` is neither formatted nor checked. When the installed black is the version pinned in `requirements-dev.txt`, the repo's `pre-commit` and `pre-merge-commit` hooks run black on the staged Python files before the commit. An optional local lint engine, not shipped with the repo, runs the ratchet check. See `CONTRIBUTING.md`.
5. **Hooks setup**: `pip install -r requirements-dev.txt` and `git config core.hooksPath hooks`

## Key Configuration Files

- `config.ini`: Main game configuration (`debug`, `language`, font, window size, in-game start date, save slots)
- `data/data.json`: Compiled game data from CSVs
- `data/Character.json`: Character template data
- `data/Character_Talk.json` / `data/Talk_Common.json`: Character and common dialogue data
- `data/Character_Event.json`: Character event data
- `data/ui_text.json`: UI text data
- `ai_chat_api_key.csv`: AI text generation API keys (sensitive)
- `package.json` / `image/package.json`: Version numbers used by CI for the game and image packages

## Development Workflow

1. Edit CSV files in `data/csv/`, `data/talk/`, `data/talk_common/`, `data/ui_text/`, or `data/character/`
2. Run `python buildconfig.py` for a full rebuild — or just run `python game.py`, which rebuilds incrementally on startup
3. Run `python game.py` to test changes
4. For localization changes, run `python buildpo.py` and `python buildmo.py`

## Tools Directory

- **`tools/AI/`**: Corpora and prompt files for AI text generation
- **`tools/map_aa_check.py`**: Pixel-level alignment checker for the AA maps in `data/map/*/Map`. Map layout is decided by the **font's real advance widths**, not by `wcwidth` — box-drawing characters and ASCII spaces belong to two incommensurable metric families that differ at some font sizes (including the size the current `config.ini` produces). Never validate an AA map by counting columns; run this instead. Supports `--tol N` and `--list-bad`, and exits non-zero on failure.
- **`tools/map_aa_build_training.py`**: Generator for `data/map/训练/Map`. That map pads with **U+2002 EN SPACE** (never ASCII space) so its walls stay aligned at every font size; U+2002 is visually identical to a normal space, so the file must be regenerated by this script rather than hand-edited.
- **Assorted scripts**: PRTS scrapers (`arknights_story_downloader.py`, `download_prts_*.py`), data maintenance (`body_part_editor.py`, ...)

## CI/CD Release Structure

The GitHub Actions workflow (`.github/workflows/python-app.yml`, PyInstaller build on push/PR to master) produces 3 release packages:

| Package | Description | Contents |
| ------- | ----------- | -------- |
| `erArk_{version}.zip` | Complete game package | Full game with all resources |
| `erArk_Lite_{version}.zip` | Lightweight game package | Game without large image assets (portraits, scenes, etc.) |
| `erArk_Images_{image_version}.zip` | Image resource package | All image folders except `image/状态条` |

The game version comes from `package.json`, the image version from `image/package.json`.

**Image folder distribution:**
- **Included in Images package only**: `image/场景`, `image/断面图`, `image/立绘`
- **Included in both Full & Lite**: `image/状态条`, `image/logo.png` and other root files

**Note:** Lite version + Images package = Full version

## Important Notes

- The game is in alpha stage with some features not yet implemented
- The game requires Sarasa Mono SC font (等距更纱黑体 SC) for proper display
- Only Windows is officially supported
- Memory requirement: ~1GB peak usage, ensure 2GB free memory

## Main Behavior Loop (`character_behavior.init_character_behavior()`)

This is the core game loop that manages character behaviors and time progression:

### 1. Player Phase
- Player selects an action (instruction) through UI panels
- Action sets behavior ID, duration, and start time on player character
- Kernel `_step()` (`Script/Kernel/core.py`) ends the action via `actions.wrap_up` when `action.start + action.duration <= GameState.clock`, then sets the character to `kernel.Idle`
- Time stop: `actions.time_stop` (`Script/Modules/gameplay_resolution/actions.py`) starts the player's action as 0 kernel minutes, so the clock does not advance (except for `TIME_STOP_OFF`)

### 2. NPC Phase
- Each NPC in `roster.active()` (global key `roster.active`, `Script/Modules/domains/roster.py`) picks its next action when its own action runs out; within one minute characters pick in roster order (player first, then NPCs by id)
- Each NPC's behavior is calculated based on:
  - Current state (tired, following, in H-mode, unconscious, etc.)
  - AI decision making (`handle_npc_ai.find_character_target()`)
  - Available actions and targets in their location
- NPCs continue their behaviors until all complete

### 3. Time Management
- Time progresses based on behavior durations
- Each character has `behavior.start_time` and `behavior.duration`
- When behavior completes, character enters idle state (`SHARE_BLANKLY`)
- New day triggers at midnight with `past_day_settle.update_new_day()` (in `Script/Settle/`)
- Player sleep triggers auto-save through `sleep_settle.update_save()`

### 4. Behavior Processing (`character_behavior()`)
For each character:
- **Pre-behavior checks**: tired/sleep, movement restrictions, assistant mode, follow mode, H-state
- **Status settlement**: `judge_character_status()` handles events and numerical changes
- **Real-time updates**: `realtime_settle.character_aotu_change_value()` applies time-based changes
- **State persistence**: Updates ongoing states and conditions
- **Completion check**: `judge_character_status_time_over()` determines if behavior is finished
- **Talent acquisition**: Automatic talent gains based on actions

### 5. Settlement System
- **Behavior effects**: `settle_behavior.handle_settle_behavior()` calculates numerical changes; effect implementations live in `Script/Settle/`
- **Event system**: Events can trigger before or after instructions
- **Change accumulation**: All changes are tracked in `CharacterStatusChange` objects
- **Display to player**: Changes are formatted and shown after player actions
- **Special handling**: Group activities, hidden actions, and complex interactions

### 6. Key Variables
- `GameState.characters[who].action` (`Script/Kernel/core.py`): Each character's active `Action` (`start` and `duration` in kernel minutes); `_step()` finishes it via `actions.wrap_up` when `start + duration <= GameState.clock`
- `game_time.now()` (`Script/Design/game_time.py`): Current game time, built from the kernel clock (`GameState.clock`)
- `pl_start_time`: Player's behavior start time (reference for NPC timing)
- `modes.time_stop()` (global key `mode.time_stop`, `Script/Modules/domains/modes.py`): Special mode where time doesn't advance

### 7. Loop Exit Conditions
- All characters (player + NPCs) have completed their behaviors
- Time stop mode is active (only player acts, then loop breaks)
- Special events or state changes that interrupt normal flow

## Drawing System

The game uses Tkinter for GUI rendering:

1. **Drawing Classes** (`Script/UI/Moudle/draw.py`):
   - `NormalDraw`: Basic text drawing with width constraints
   - `CenterDraw`: Center-aligned text
   - `RightDraw`: Right-aligned text
   - `Button`: Interactive button elements
   - `FullDraw`: Draw text without truncation
   - `WaitDraw`: Draw text and wait for player input
   - `LineFeedWaitDraw`: Wait on each line break

2. **IO Operations** (`Script/Core/io_init.py`):
   - Emits `Script/Protocol` render operations and clear events through the configured `UiPort`
   - Blocks on the port for choice, text, and pause requests without importing Tkinter
   - Rendered by the Tkinter frontend package (`Script/Frontend/Tk/`)

3. **Flow Control** (`Script/Core/flow_handle.py`):
   - `askfor_all()`: Wait for player to select from options
   - `askfor_wait()`: Pause for confirmation unless skip mode is active
   - Receives player responses from the port via `io_init`

### Development Considerations

- All UI components should use the abstract drawing classes
- Avoid direct Tkinter manipulation
- Use `io_init.era_print()` for all text output
