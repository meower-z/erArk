---
timestamp: 2026-09-09
---
# 行动调度器内部审阅

[内部草稿 PR #8](https://github.com/meower-z/erArk-fork/pull/8) 面向 `meower-z/erArk-fork:main`，等待用户审阅。设计与接口见[行动调度设计契约](../topics/projects/action-scheduler.md)。

完成条件：用户完成内部审阅，要求的修改及验证已落实。当前 PR 保持草稿，不自动合并。

## 修改与验收要求

修改集中在公共入口、递归调用点及持续动作适配，避免逐个重写普通动作。Behavior 收尾接入位置以实际代码审查为准。

实现以最新 upstream 主分支为基线，使用 meower-z 账号，向 meower-z/erArk-fork 的 main 提交内部 PR。多名 Astra、Fable 对整体进行批判性审查；每个变动函数分别由 Sonnet、Luna 提出简化建议，实施者判断采纳。验收覆盖时序交错、强制后续、占位符替换、输入优先、休息睡眠延续、双人等待、跨日、时停和读档。

## 验证状态

34 项单元测试通过。真实 Tk 已验证启动和读档；普通等待、休息的界面流程尚未完成验证。

任务结束时，将新增的长期知识折入设计页，本页整理为结果记录并移入 `history/`。
