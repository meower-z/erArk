# -*- coding: UTF-8 -*-
"""
PRTS 立绘下载器 MCP 服务器的标准输出只留给协议
==============================================
tools/MCP/prts_character_downloader/server.py 经标准输入输出跑 MCP 协议，
客户端把它标准输出的每一行都当协议消息读，日志与进度信息只能写到标准错误。
子进程在包目录里构造 PRTSMCPServer，直接调用它登记的工具调用处理函数：
下载一个有图的角色、搜索一个查不到的角色，走过服务器的日志与下载器的各条查找路径。
检查子进程的标准输出为空，日志与进度信息出现在标准错误上，两次调用的结果正确。
测试依赖里没有 mcp，子进程的 PYTHONPATH 指向临时目录里的 mcp 替身，
替身的 Server 记下 call_tool() 登记的处理函数；子进程里 urlopen 换成按 URL 给预设回应的替身，
socket 的连接函数换成抛异常，不联网。
"""

import json
import os
import subprocess
import sys
import tempfile

from tests.fast.base import FastTestCase
from tests.world import ROOT

PACKAGE_DIR = os.path.join(ROOT, "tools", "MCP", "prts_character_downloader")
""" 包目录，子进程的工作目录 """
MCP_STUB_FILES = {
    "mcp/__init__.py": "",
    "mcp/types.py": (
        "class Tool:\n"
        "  def __init__(self, **fields):\n"
        "    self.__dict__.update(fields)\n\n\n"
        "class TextContent(Tool):\n"
        "  pass\n"
    ),
    "mcp/server/__init__.py": (
        "class NotificationOptions:\n"
        "  pass\n\n\n"
        "class Server:\n"
        "  def __init__(self, name):\n"
        "    self.handlers = {}\n\n"
        "  def list_tools(self):\n"
        "    return lambda func: self.handlers.setdefault('list_tools', func)\n\n"
        "  def call_tool(self):\n"
        "    return lambda func: self.handlers.setdefault('call_tool', func)\n"
    ),
    "mcp/server/models.py": "class InitializationOptions:\n  pass\n",
}
""" mcp 替身的文件：相对路径 -> 内容 """
CHILD_CODE = """
import asyncio, io, json, socket, sys, urllib.error, urllib.request

def refuse(*args, **kwargs):
  raise OSError('network blocked by test')

socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse

IMAGE_URL = 'https://media.prts.wiki/9/99/canned_1.png'

class Reply(io.BytesIO):
  def getcode(self):
    return 200

def urlopen(request, *args, **kwargs):
  url = request.full_url
  if url.startswith('https://prts.wiki/api.php'):
    images = []
    if '%E8%8E%B1%E4%BC%8A' in url:
      images = [{'name': '立绘_莱伊_1.png', 'url': IMAGE_URL}]
    return Reply(json.dumps({'query': {'allimages': images}}).encode('utf-8'))
  if url.startswith('https://prts.wiki/w/'):
    return Reply('<table><tr><td>别人</td></tr></table>'.encode('utf-8'))
  if url == IMAGE_URL:
    return Reply(b'png')
  raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)

urllib.request.urlopen = urlopen

import server

call_tool = server.PRTSMCPServer().server.handlers['call_tool']
calls = [
    ('download_character_image', {'character_name': '莱伊', 'save_dir': sys.argv[2]}),
    ('search_character_image_url', {'character_name': '无此人'}),
]
texts = [asyncio.run(call_tool(name, arguments))[0].text for name, arguments in calls]
with open(sys.argv[1], 'w', encoding='utf-8') as f:
  json.dump(texts, f, ensure_ascii=False)
"""
"""
子进程执行的代码：参数为结果文件与下载目录；
莱伊的 API 查询返回一张图，别的名字查不到，剧情角色一览页面里没有要找的角色，直接构建的 URL 都是 404
"""


def write_mcp_stub(root: str) -> None:
  """
  在目录里写出 mcp 替身包
  Keyword arguments:
  root -- 目录，写完后加进子进程的 PYTHONPATH
  Return arguments:
  无
  """
  for relative_path, content in MCP_STUB_FILES.items():
    path = os.path.join(root, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
      f.write(content)


class PrtsServerStdoutProtocolOnlyTest(FastTestCase):
  """PRTS 立绘下载器 MCP 服务器处理工具调用时不往标准输出写任何东西"""

  def test_tool_calls_write_nothing_to_stdout(self) -> None:
    """
    在子进程里调用下载与搜索两个工具，检查标准输出为空、日志与进度信息在标准错误上、调用结果正确
    Keyword arguments:
    无
    Return arguments:
    无
    """
    with tempfile.TemporaryDirectory() as scratch:
      stub_root = os.path.join(scratch, "stub")
      write_mcp_stub(stub_root)
      result_file = os.path.join(scratch, "result.json")
      save_dir = os.path.join(scratch, "images")
      env = dict(os.environ, PYTHONPATH=stub_root, PYTHONDONTWRITEBYTECODE="1")
      result = subprocess.run(
          [sys.executable, "-c", CHILD_CODE, result_file, save_dir],
          cwd=PACKAGE_DIR,
          env=env,
          stdin=subprocess.DEVNULL,
          capture_output=True,
          text=True,
          encoding="utf-8",
          errors="replace",
          timeout=60,
          check=False,
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(result.stdout, "")
      self.assertIn("开始下载角色立绘: 莱伊", result.stderr)
      self.assertIn("图片已保存到", result.stderr)
      self.assertIn("未能找到 无此人 的立绘图片URL", result.stderr)
      with open(result_file, encoding="utf-8") as f:
        texts = json.load(f)
      self.assertEqual(
          texts,
          [
              f"成功下载 莱伊 的立绘图片到 {save_dir} 目录",
              "未能找到 无此人 的立绘图片URL",
          ],
      )
      self.assertEqual(os.listdir(save_dir), ["莱伊_立绘.png"])
