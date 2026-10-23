# 各钩子共用的串接逻辑，由钩子用 `.` 读入，不单独运行。
#
# 用法：钩子先定义 own_job（本钩子自己的检查），再调用 run_chain <钩子名> "$@"。
# own_job 的标准输入接 /dev/null。随后若 <git 公共目录>/hooks/<钩子名>.local
# 可执行，就把原参数和标准输入原样交给它运行；本钩子自己的检查失败时它也照样运行。
# 退出码取（自己的检查，.local）里第一个非零的。

# 运行本钩子自己的检查，再串接到同名的 .local 钩子并退出
# 参数：$1 钩子名；其余为 git 传给钩子的参数
# 返回：不返回，以上述退出码结束进程
run_chain() {
  chain_name=$1
  shift
  chain_local="$(git rev-parse --git-common-dir)/hooks/$chain_name.local"
  own_job </dev/null
  chain_own=$?
  if [ -e "$chain_local" ] && [ ! -x "$chain_local" ]; then
    echo "hooks: $chain_local 不可执行，跳过" >&2
  elif [ -x "$chain_local" ]; then
    if [ "$chain_own" -eq 0 ]; then
      exec "$chain_local" "$@"
    fi
    "$chain_local" "$@"
  fi
  exit "$chain_own"
}
