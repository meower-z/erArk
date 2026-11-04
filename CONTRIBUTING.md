# 参与开发

## 准备

```bash
pip install -r requirements-dev.txt    # 只用于开发。除 ruff 外各包都固定版本
git config core.hooksPath hooks        # 启用仓库自带的 git 钩子
pip install -r requirements-lint.txt   # 可选，做棘轮检查时装。它也装上 requirements-dev.txt 里的包
```

提交时 `hooks/pre-commit` 用 `pyink --check` 检查暂存的 `.py` 文件。装的 pyink 版本与 `requirements-dev.txt` 不一致时，钩子跳过这项检查并给出提示。本机 lint 引擎是可选的，不随仓库提供。用 `git config erark.lintEngine <路径>` 指向它以后，钩子改为运行它，由它做下面的棘轮检查。

## 代码风格

- 格式：pyink，2 空格缩进，每行 80 列，引号随文件里的多数。在仓库根目录运行 `pyink .`。生成的 `Script/Config/config_def.py` 不参与格式化，也不参与下面的各项检查。
- ruff：配置在 `pyproject.toml` 的 `[tool.ruff]`。`[tool.ruff.lint]` 选用这些规则组：pyflakes（F），pycodestyle 的 E4、E7、E9、E501 与 W，bugbear（B），pylint 的错误与警告（PLE、PLW，不含查 `global` 语句的 PLW0603），缺文档字符串（D1）与空文档字符串（D419），pyupgrade（UP）。在仓库根目录运行 `ruff check --ignore-noqa` 时，受 git 跟踪的 `.py` 文件得到的报告与棘轮运行 ruff 时相同。报告里也有基线里记着的老问题。手动运行的 ruff 还会查没被 git 跟踪、也没被 `.gitignore` 忽略的 `.py` 文件。棘轮不查这些文件。
- 行长：ruff 按显示宽度查行长，一个汉字算 2 列。ruff 的行长上限是 120 列。pyink 按 80 列排版。
- 模块长度：超过 300 行警告，超过 400 行算违规。
- 文档字符串：模块和包（`__init__.py`）要有文档字符串，没有代码的文件也要有。公开的类和公开的函数要有文档字符串。公开的类里的公开方法和公开的嵌套类也要有。`__init__` 和 `__eq__` 这类前后都有双下划线的方法也算公开方法。写了的文档字符串不能是空的。下面这些不要求文档字符串：
  - 名字以 `_` 开头的模块和包，以及其中的一切。前后都有双下划线的模块和包（如 `__main__.py`）不在此列。
  - 名字以 `_` 开头的类，以及其中的一切。
  - 名字以 `_` 开头的函数和方法。前后都有双下划线的方法不在此列。
  - 嵌套在函数里的函数和类，以及这些类里的方法。
  - 带 `@overload` 装饰器的函数，即 typing 的重载声明。
  - 带 `@override` 装饰器的方法。
  - 属性的 setter，即带 `@x.setter` 装饰器的方法（x 是属性名）。
  - 模块定义了 `__all__` 时，没列进 `__all__` 的函数和类，以及这些类里的方法。
- `# noqa`：棘轮运行 ruff 时带 `--ignore-noqa`，所以 `# noqa` 注释压不下棘轮报出的问题。已有 `# noqa` 注释的行上的问题记在基线里。不带 `--ignore-noqa` 运行时，ruff 不报这些注释压下的问题。
- mypy：配置在 `pyproject.toml` 的 `[tool.mypy]`。棘轮对每个模块都用这一套参数。mypy 也检查没有类型标注的函数的函数体。它还报出执行不到的代码、可能未赋值就用到的名字和永远不成立的比较等问题。这一套不要求函数写类型标注。mypy 推断不出一个变量的类型时，仍要求给这个变量写类型标注。在装了 `requirements-lint.txt` 的环境里，从仓库根目录运行 `git ls-files -z '*.py' ':!Script/Config/config_def.py' | xargs -0 mypy` 时，得到的报错与棘轮运行 mypy 时相同。
- 加严：先清掉基线里记着的问题，再加严规则。加严的做法是在 `pyproject.toml` 里加规则组或 mypy 参数，然后重算基线。
- 注释与文档字符串用中文。

## 棘轮与基线

现有代码里的违规记在仓库根目录的 `.lint-baseline.tsv`，按「文件、函数全名、规则」记，不记行号。

- 新函数必须完全没有违规。
- 已有函数的各项指标（例如某条规则的违规数、最长一行的长度）不许超过基线里记的值。
- 改代码时，基线只会变小。加严规则后重算的基线可能变大。
