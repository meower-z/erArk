# pre-commit 与 pre-merge-commit 共用的 lint 检查，由钩子用 `.` 读入，不单独运行。

# 检查暂存区里的 Python 代码
# 配了 git config erark.lintEngine 时运行该 lint 引擎的 pre-commit 并返回它的退出码；
# 配了但文件不可执行时返回 2；没配时只在 pyink 版本与 requirements-dev.txt 一致时
# 用 pyink --check 检查暂存的 .py，有要重排的文件返回 1，否则返回 0
# 返回：退出码（0 通过，1 有违规，2 拒绝运行）
own_job() {
  lint_engine=$(git config --get erark.lintEngine)
  if [ -n "$lint_engine" ]; then
    # 不含 / 的值按钩子的工作目录（仓库根目录）下的文件处理，不去 PATH 里找
    case $lint_engine in
      */*) ;;
      *) lint_engine="./$lint_engine" ;;
    esac
    if [ -x "$lint_engine" ]; then
      "$lint_engine" pre-commit
      return $?
    fi
    echo "lint engine configured at $lint_engine but missing" >&2
    return 2
  fi
  echo "lint engine not found, skipping ratchet; see CONTRIBUTING"
  lint_pin=$(sed -n 's/^pyink==\([0-9.]*\).*/\1/p' requirements-dev.txt)
  lint_have=$(pyink --version 2>/dev/null | sed -n '1s/^pyink, \([0-9.]*\).*/\1/p')
  if [ -z "$lint_pin" ] || [ "$lint_have" != "$lint_pin" ]; then
    echo "pyink $lint_pin not installed, skipping format check; pip install -r requirements-dev.txt"
    return 0
  fi
  lint_check_staged_format
}

# 用 pyink --check 检查暂存区里（不是工作区里）的 .py 文件
# 把暂存的 .py、pyproject.toml 与各 .gitignore 导出到临时目录，在那里运行一次
# `pyink --check .`，与在仓库根目录运行 `pyink .` 查的文件相同
# 返回：0 格式都对或没有暂存的 .py；1 有文件要重排（打印文件和修复命令）或 pyink 出错（打印它的输出）
lint_check_staged_format() {
  if [ -z "$(git diff --cached --name-only --diff-filter=ACMR -- '*.py')" ]; then
    return 0
  fi
  lint_tmp=$(mktemp -d) || return 2
  git diff --cached --name-only -z --diff-filter=ACMR -- '*.py' |
    git checkout-index -z --stdin --prefix="$lint_tmp/"
  git checkout-index --prefix="$lint_tmp/" -- pyproject.toml
  git ls-files -z -- .gitignore '*/.gitignore' |
    git checkout-index -z --stdin --prefix="$lint_tmp/"
  lint_out=$(cd "$lint_tmp" && pyink --check . 2>&1)
  lint_code=$?
  rm -rf "$lint_tmp"
  if [ "$lint_code" -eq 0 ]; then
    return 0
  fi
  if [ "$lint_code" -ne 1 ]; then
    echo "$lint_out"
    return 1
  fi
  # pyink 打印的是解析后的绝对路径（macOS 上带 /private，Windows 上是反斜杠的盘符路径），按临时目录名截掉前缀
  lint_files=$(echo "$lint_out" | sed -n "s|^would reformat .*$(basename "$lint_tmp")[/\\]||p" | tr '\\\n' '/ ')
  echo "pyink 格式不对的文件：$lint_files"
  echo "修复后再提交：pyink $lint_files&& git add $lint_files"
  return 1
}
