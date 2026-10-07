# 群交功能扩展

群交模式"技艺"类别里的三个批量指令（web：arts / arts_hypnosis，身体部位 head）：

- **全员寸止**：给还没寸止的参与者开启寸止，清零其寸止次数。
- **全员戴上玩具**：给参与者戴上乳头夹、阴蒂夹、V/A 震动棒中还没戴的。
- **全员催眠增强**：给完全催眠（素质 73 或催眠度 ≥200）的参与者开启敏感度上升与苦痛快感化，不改变当前催眠状态。至少两名完全催眠参与者时才显示。

参与者 = 群交模板里的角色 ∪ 玩家所在场景里的角色，只取 H 中的 NPC。

## 文件

- `entry.py`：mod_manager 执行的唯一入口，把本目录加载成私有包后调用 `install()`
- `members.py`：参与者与完全催眠判定
- `actions.py`：三个指令的效果与提示
- `instruct.py`：前提与指令注册；cid 从 4900 起动态分配，不与其他 mod 撞

## 测试

```bash
python3 -u mod/group_sex_extension/tests/test_group_sex_extension_mod.py
```
