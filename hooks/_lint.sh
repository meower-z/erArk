# pre-commit 与 pre-merge-commit 共用的 lint 检查，由钩子用 `.` 读入，不单独运行。

# 提交前和合并提交前的检查，按下面的顺序做
# 先比较装的 black 版本与 requirements-dev.txt 固定的 black 版本
# 两个版本相同时调用 lint_format_staged，用 black 重排暂存的 Python 文件
# lint_format_staged 返回非 0 时，本函数返回同一个值，不运行 lint 引擎
# 没装 black、版本不同或读不到固定的版本时，打印一行提示，跳过重排
# 然后读 git config erark.lintEngine 的值
# 没有配这个值时打印一行提示，返回 0
# 这个值指向可执行文件时，用参数 pre-commit 运行这个文件，返回它的退出码
# 这个值指向的文件不存在或不可执行时返回 2
# 返回：退出码。0 是通过，1 是有一步中止了提交，2 是无法运行（建不了临时目录，或配置的 lint 引擎文件不可用）
own_job() {
  lint_pin=$(sed -n 's/^black==\([0-9.]*\).*/\1/p' requirements-dev.txt)
  lint_have=$(black --version 2>/dev/null | sed -n '1s/^black, \([0-9.]*\).*/\1/p')
  if [ -z "$lint_pin" ] || [ "$lint_have" != "$lint_pin" ]; then
    echo "black $lint_pin not installed, skipping auto-format. Run pip install -r requirements-dev.txt"
  else
    lint_format_staged || return $?
  fi
  lint_engine=$(git config --get erark.lintEngine)
  if [ -z "$lint_engine" ]; then
    echo "lint engine not found, skipping ratchet; see CONTRIBUTING"
    return 0
  fi
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
}

# 用 black 重排暂存区里的 .py 与 .pyi 文件，重排的是暂存的内容，不是工作区的内容
# 把这些文件、暂存的 pyproject.toml 和受 git 跟踪的各 .gitignore 导出到临时目录，在那里运行一次 `black .`
# 这样 black 挑选要重排的文件时，用的规则与在仓库根目录运行 `black .` 时相同
# black 改过的文件复制回工作区，再重新暂存
# black 运行失败时打印它的输出，不写回文件，返回 1
# 要写回的文件还有没暂存的改动时不写回，因为 git add 会把那些改动一起暂存
# 提交用的是 `git commit <路径>` 时也不写回，因为 git 这时从名为 next-index-* 的临时暂存区提交，写回进不了真正的暂存区
# 有文件没写回时打印这些文件和处理办法，返回 1
# 合并提交时写回文件后返回 1 中止合并，因为 git merge 不读钩子改过的暂存区，之后运行 git commit 完成合并
# 返回：0 是没有文件要重排，或要重排的文件都已写回并重新暂存
# 1 是 black 运行失败、有文件没写回，或合并提交时写回了文件
# 2 是建不了临时目录
lint_format_staged() {
  # 带 -z 时 git 原样输出文件名，不加引号也不转义。tr 把分隔文件名的 NUL 换成换行，下面的循环按行读
  lint_staged=$(git diff --cached --name-only -z --diff-filter=ACMR -- '*.py' '*.pyi' | tr '\0' '\n')
  if [ -z "$lint_staged" ]; then
    return 0
  fi
  lint_tmp=$(mktemp -d) || return 2
  git diff --cached --name-only -z --diff-filter=ACMR -- '*.py' '*.pyi' |
    git checkout-index -z --stdin --prefix="$lint_tmp/"
  git checkout-index --prefix="$lint_tmp/" -- pyproject.toml
  git ls-files -z -- .gitignore '*/.gitignore' |
    git checkout-index -z --stdin --prefix="$lint_tmp/"
  if ! lint_out=$(cd "$lint_tmp" && BLACK_CACHE_DIR="$lint_tmp/.black-cache" black -q . 2>&1); then
    rm -rf "$lint_tmp"
    echo "$lint_out"
    return 1
  fi
  case ${GIT_INDEX_FILE##*/} in
    next-index-*) lint_only=1 ;;
    *) lint_only="" ;;
  esac
  lint_done=""
  lint_left=""
  while IFS= read -r lint_file; do
    if [ "$(git hash-object --path="$lint_file" -- "$lint_tmp/$lint_file")" = "$(git rev-parse ":$lint_file")" ]; then
      continue
    fi
    if [ -z "$lint_only" ] && git diff --quiet -- "$lint_file" &&
      cp "$lint_tmp/$lint_file" "$lint_file" && git add -- "$lint_file"; then
      lint_done="$lint_done$lint_file "
    else
      lint_left="$lint_left$lint_file "
    fi
  done <<EOF
$lint_staged
EOF
  rm -rf "$lint_tmp"
  if [ -n "$lint_done" ]; then
    echo "black 已重排并重新暂存：$lint_done"
    if [ "$chain_name" = pre-merge-commit ]; then
      echo "运行 git commit 完成合并"
      return 1
    fi
  fi
  if [ -n "$lint_left" ]; then
    echo "black 要重排这些文件，钩子没有写回：$lint_left"
    echo "这些文件有没暂存的改动，或这次提交用的是 git commit <路径>。用 black 重排这些文件、暂存整个文件后再提交"
    return 1
  fi
  return 0
}
