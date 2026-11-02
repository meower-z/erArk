#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fast_report.py 开始前的 data/ 检查：checkout 的 data/ 下有被 git 忽略的未跟踪文件就拒绝运行。"""

from __future__ import annotations

import os
import pathlib
import shlex
import subprocess

# 拒绝运行时最多列出 data/ 下多少个被忽略的文件
SAMPLE_SIZE = 5


class DataCheckError(Exception):
  """git 列不出 checkout 的 data/ 下被忽略的文件。"""


def ignored_data_files(checkout: pathlib.Path) -> list[str]:
  """返回 checkout 的 data/ 下被 git 忽略的未跟踪文件。

  只运行 `git ls-files`，它不改动 checkout。传入 GIT_OPTIONAL_LOCKS=0，git 就跳过要加锁的可选步骤，
  这项检查不会占着 checkout 里别的 git 命令在等的锁。

  Args:
    checkout: erArk checkout 的根目录。

  Returns:
    这些文件相对 checkout 的路径，按 git 给出的顺序。

  Raises:
    DataCheckError: git 不存在、出错或超时，例如 checkout 不在 git 仓库里。
  """
  ls_files = ['ls-files', '--others', '--ignored', '--exclude-standard']
  cmd = ['git', '-C', str(checkout), *ls_files, '--', 'data/']
  env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
  try:
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True, check=False, timeout=60
    )
  except (OSError, subprocess.TimeoutExpired) as exc:
    raise DataCheckError(f'{type(exc).__name__}: {exc}') from exc
  if proc.returncode != 0:
    detail = proc.stderr.strip() or proc.stdout.strip()
    raise DataCheckError(f'git ls-files exited {proc.returncode}: {detail}')
  return proc.stdout.splitlines()


def refuse_reason(checkout: pathlib.Path) -> str:
  """返回不能开始运行的原因；data/ 干净时返回空串。"""
  data = checkout / 'data'
  try:
    files = ignored_data_files(checkout)
  except DataCheckError as exc:
    return (
        f'refused: cannot check {data}/ for build output, so the run did not'
        f' start: {exc}'
    )
  if not files:
    return ''
  sample = ', '.join(files[:SAMPLE_SIZE])
  more = ', ...' if len(files) > SAMPLE_SIZE else ''
  return (
      f'refused: {len(files)} git-ignored untracked files under {data}/'
      f' ({sample}{more}). The game reads these prebuilt files instead of'
      ' running the code that builds them, so the run would measure fewer'
      ' mutants. Clean them first, then rerun:\n'
      f'  git -C {shlex.quote(str(checkout))} clean -fdX data/'
  )
