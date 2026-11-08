# pre-commit 与 pre-merge-commit 共用的 lint 检查，由钩子用 `.` 读入，不单独运行。

# 用本机 lint 引擎检查暂存区里的 Python 代码
# 配了 git config erark.lintEngine 时，运行该 lint 引擎的 pre-commit，返回它的退出码
# 配了但文件不存在或不可执行时返回 2
# 没配时打印提示，返回 0
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
  return 0
}
