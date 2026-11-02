#!/bin/sh
# 把 game_runner_guard.py 装进 erArk 的 venv：之后该 venv 的每个 Python 进程启动时都会导入它
# 用法：sh install_guard.sh <venv 目录>；改了 game_runner_guard.py 后重新运行
set -e
venv=${1:?usage: sh install_guard.sh <venv dir>}
site=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
here=$(cd "$(dirname "$0")" && pwd)
rm -f "$site/game_runner_guard.py"
cp "$here/game_runner_guard.py" "$site/game_runner_guard.py"
echo "import game_runner_guard" > "$site/game_runner_guard.pth"
echo "installed into $site"
