# 参与开发

## 准备

```bash
pip install -r requirements-dev.txt   # 固定版本的 pyink、pylint、astroid、mypy，只用于开发
git config core.hooksPath hooks       # 启用仓库自带的 git 钩子
```

提交时 `hooks/pre-commit` 用 `pyink --check` 检查暂存的 `.py` 文件（pyink 版本与 `requirements-dev.txt` 不一致时跳过并提示）。用 `git config erark.lintEngine <路径>` 指向一个可选的本机 lint 引擎（不随仓库提供）时，钩子就运行它，由它加上下面的棘轮检查。

## 代码风格

- 格式：pyink，2 空格缩进，每行 80 列，引号随文件里的多数。在仓库根目录运行 `pyink .`。生成的 `Script/Config/config_def.py` 不参与格式化，也不参与下面的各项检查。
- pylint：配置在 `.pylintrc`。函数参数最多 5 个，分支最多 12 个，局部变量最多 15 个，return 最多 6 个，语句最多 40 条；模块和函数都要有文档字符串，函数不分长短与名字；命名按配置里的规则。
- 模块长度：超过 300 行警告，超过 400 行算违规。
- mypy：配置在 `pyproject.toml` 的 `[tool.mypy]`。
- 注释与文档字符串用中文。

## 棘轮与基线

现有代码里的违规记在仓库根目录的 `.lint-baseline.tsv`，按「文件、函数全名、规则」记，不记行号。

- 新函数必须完全没有违规。
- 已有函数的各项指标（例如分支数、超长行数）不许超过基线里记的值。基线只会变小。
- 老名字不用改名。

## mypy 的老模块与新模块

- `.lint-baseline.tsv` 头部每个 `# old-module <路径>` 行是一个老模块：它用 `[tool.mypy]` 的默认参数运行，原有报错记在基线里。
- 其他 `.py` 文件都是新模块，一直用严格模式运行（不含 `disallow_untyped_calls`），不能有报错。新加的 `.py` 文件都是新模块，`tests/` 下的测试文件也一样：测试函数标注 `-> None`，夹具也要标注类型。
- 要让一个老模块改用严格模式，删掉它的 `# old-module` 行，再修掉超出基线的报错。
- 拆分一个模块时，单独提一个 PR，只把函数和类原样搬到新文件；在同一个 PR 里再加新代码，新文件就按新模块算。
