"""
文本生成AI设置面板无界面服务（chat_ai_setting_service）
=====================================================
本模块提供文本生成AI设置项读写、发送数据开关、密钥文件管理与模型连通测试逻辑。
本模块公开常量 DEFAULT_ON、KEY_FILE、KEY_TYPES 与 TEST_SECONDS，以及数据类 SettingRow 与 SendDataRow。
本模块公开设置读写、翻译切换、发送数据、密钥存取及模型测试函数。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

import concurrent.futures
import csv
import os
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType
from typing import Any

import openai
from google import genai

from Script.Config import game_config, normal_config
from Script.Core import get_text

_: FunctionType = get_text._
""" 翻译api """

DEFAULT_ON = frozenset({7, 12, 14})
""" 默认值为 1 的文本生成AI设置项 id 集合，其余设置项默认值为 0。 """
KEY_FILE = "ai_chat_api_key.csv"
""" 相对于当前工作目录的API密钥CSV文件名。 """
KEY_TYPES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY")
""" 从密钥文件读取并识别的API密钥类型名元组。 """
TEST_SECONDS = 10
""" 模型连通测试等待响应的超时秒数上限。 """


@dataclass(frozen=True, slots=True)
class SettingRow:
    """主设置列表单行数据，含设置 id、名称、当前值标签与选项数。"""

    cid: int
    name: str
    value: str
    option_len: int


@dataclass(frozen=True, slots=True)
class SendDataRow:
    """发送数据列表单行数据，含数据 id、名称、数据量标签、必选与选中标志。"""

    cid: int
    name: str
    size: str
    required: bool
    chosen: bool


def setting_of(cid: int) -> Any:
    """
    按设置 id 读取当前设置值，未登记时返回默认值。
    Keyword arguments:
    cid -- int，设置项 id
    Return arguments:
    Any -- 设置项当前值或默认值
    """
    return normal_config.ai_setting.ai_chat_setting.get(
        cid, int(cid in DEFAULT_ON)
    )


def fill_defaults() -> None:
    """为配置表中尚未登记的文本生成AI设置项写入默认值。"""
    for cid in game_config.config_ai_chat_setting:
        normal_config.ai_setting.ai_chat_setting.setdefault(
            cid, int(cid in DEFAULT_ON)
        )


def _value_label(cid: int) -> str:
    """按设置项 cid 生成主设置列表该行的当前值显示标签字符串。"""
    value = setting_of(cid)
    if cid == 5:
        return f" [{value}] "
    if cid == 6:
        return _(" [调整发送的数据] ")
    label = f" [{game_config.config_ai_chat_setting_option[cid][value]}] "
    if cid == 10 and value == 1:
        return label + normal_config.ai_setting.now_ai_chat_base_url
    if cid == 11 and value == 1:
        proxy = normal_config.ai_setting.now_ai_chat_proxy
        label += "ip：" + proxy[0]
        if len(proxy[1]) > 0:
            label += " port：" + proxy[1]
    return label


def setting_rows() -> tuple[SettingRow, ...]:
    """
    按配置顺序返回主设置列表行，总开关为 0 时在首个非 1 项处停止。
    Return arguments:
    tuple[SettingRow, ...] -- 主设置列表展示行元组
    """
    rows = []
    for cid, data in game_config.config_ai_chat_setting.items():
        if cid != 1 and setting_of(1) == 0:
            break
        option_len = len(game_config.config_ai_chat_setting_option[cid])
        rows.append(SettingRow(cid, data.name, _value_label(cid), option_len))
    return tuple(rows)


def cycle(cid: int, option_len: int) -> None:
    """
    将指定设置项切换到下一个选项索引，到达末尾后归零。
    Keyword arguments:
    cid -- int，设置项 id
    option_len -- int，该设置项的可选数量
    """
    settings = normal_config.ai_setting.ai_chat_setting
    if settings[cid] < option_len - 1:
        settings[cid] += 1
    else:
        settings[cid] = 0


def switch_off(cid: int) -> None:
    """将指定 int 设置项 cid 的值置为 0。"""
    normal_config.ai_setting.ai_chat_setting[cid] = 0


def _one_line(text: str) -> str:
    """若字符串 text 末尾为单个换行符则去除它并返回结果字符串。"""
    return text.removesuffix("\n")


def set_model(name: str) -> None:
    """将模型名设置项（id 5）写入为字符串 name。"""
    normal_config.ai_setting.ai_chat_setting[5] = name


def set_talk_count(text: str) -> None:
    """将字符串 text 转为整数减一并限制在 0 到 9 后写入生成数量设置项。"""
    normal_config.ai_setting.ai_chat_setting[9] = min(max(int(text) - 1, 0), 9)


def set_base_url(text: str) -> None:
    """去除 text 末尾单个换行后写入自定义接口地址并开启设置项 10。"""
    normal_config.ai_setting.now_ai_chat_base_url = _one_line(text)
    normal_config.ai_setting.ai_chat_setting[10] = 1


def set_proxy_url(text: str) -> None:
    """去除 text 末尾单个换行后写入代理配置的代理地址项。"""
    normal_config.ai_setting.now_ai_chat_proxy[0] = _one_line(text)


def set_local_ip(text: str) -> None:
    """去除 text 末尾换行后写入三点格式本地 IP（否则置空）并开启设置项 11。"""
    local_ip = _one_line(text)
    if local_ip.count(".") != 3:
        local_ip = ""
    normal_config.ai_setting.now_ai_chat_proxy[1] = local_ip
    normal_config.ai_setting.ai_chat_setting[11] = 1


def translator_label() -> str | None:
    """
    返回语言翻译设置（0、1、2）对应的本地化标签，其他值返回 None。
    Return arguments:
    str | None -- 翻译状态标签，超出已知取值时为 None
    """
    return {
        0: _(" [未开启] "),
        1: _(" [仅翻译地文] "),
        2: _(" [翻译地文和口上] "),
    }.get(normal_config.ai_setting.ai_chat_translator_setting)


def next_translator() -> None:
    """将语言翻译设置值加一，超过 2 时重置为 0。"""
    ai_setting = normal_config.ai_setting
    ai_setting.ai_chat_translator_setting += 1
    if ai_setting.ai_chat_translator_setting > 2:
        ai_setting.ai_chat_translator_setting = 0


def send_data_rows() -> tuple[SendDataRow, ...]:
    """
    按发送数据配置顺序返回展示行，并为未登记项先写入配置默认开关。
    Return arguments:
    tuple[SendDataRow, ...] -- 发送数据列表展示行元组
    """
    flags = normal_config.ai_setting.send_data_flags
    sizes = {1: _("小"), 2: _("中"), 3: _("大")}
    rows = []
    for cid, data in game_config.config_ai_chat_send_data.items():
        if cid not in flags:
            flags[cid] = data.default == 1
        size = sizes.get(data.data_size, _("未知"))
        rows.append(
            SendDataRow(cid, data.name, size, data.required == 1, flags[cid])
        )
    return tuple(rows)


def toggle_send_data(cid: int) -> None:
    """翻转指定 int 发送数据项 cid 在发送开关表中的布尔值。"""
    flags = normal_config.ai_setting.send_data_flags
    flags[cid] = not flags[cid]


def load_api_keys() -> None:
    """从密钥文件读取首列属于 KEY_TYPES 的记录写入内存，缺失时忽略。"""
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            for row in csv.reader(f):
                if row[0] in KEY_TYPES:
                    normal_config.ai_setting.ai_chat_api_key[row[0]] = row[1]
    except FileNotFoundError:
        pass


def key_filled(key_type: str) -> bool:
    """
    检查指定类型的API密钥在内存中是否已设为非空字符串。
    Keyword arguments:
    key_type -- str，API密钥类型名
    Return arguments:
    bool -- 内存中对应密钥非空时为 True，否则为 False
    """
    return normal_config.ai_setting.ai_chat_api_key.get(key_type, "") != ""


def key_format_ok(key_type: str, api_key: str) -> bool:
    """
    校验API密钥格式，OpenAI 与 DeepSeek 需以 sk- 开头，其余直接通过。
    Keyword arguments:
    key_type -- str，API密钥类型名
    api_key -- str，待校验的密钥字符串
    Return arguments:
    bool -- 符合格式要求时为 True，否则为 False
    """
    if key_type in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        return api_key.startswith("sk-")
    return True


def save_api_key(key_type: str, api_key: str) -> None:
    """
    将API密钥更新或追加到密钥文件并保留其他行，写入成功后再更新内存密钥。
    Keyword arguments:
    key_type -- str，API密钥类型名
    api_key -- str，待保存的密钥字符串
    """
    rows = []
    found = False
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if row[0] == key_type:
                    row[1] = api_key
                    found = True
                rows.append(row)
    if not found:
        rows.append([key_type, api_key])
    with open(KEY_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    normal_config.ai_setting.ai_chat_api_key[key_type] = api_key


def model_key() -> tuple[str, bool] | None:
    """
    按当前模型名推断API密钥类型与是否已识别，模型为 0 或 "0" 时返回 None。
    Return arguments:
    tuple[str, bool] | None -- 密钥类型名与识别标志，未设模型时为 None
    """
    model = setting_of(5)
    if model == 0 or model == "0":
        return None
    if "gpt" in model:
        return "OPENAI_API_KEY", True
    if "deepseek" in model:
        return "DEEPSEEK_API_KEY", True
    if "gemini" in model:
        return "GEMINI_API_KEY", True
    return "OPENAI_API_KEY", False


def make_client(key_type: str) -> Any:
    """
    按内存密钥与接口、代理、协议配置构造 OpenAI 或 Gemini 客户端。
    Keyword arguments:
    key_type -- str，API密钥类型名
    Return arguments:
    Any -- 已配置的客户端实例，内存中未保存该密钥时返回 None
    """
    ai_setting = normal_config.ai_setting
    if key_type not in ai_setting.ai_chat_api_key:
        return None
    api_key = ai_setting.ai_chat_api_key[key_type]
    if key_type in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        client = openai.OpenAI(api_key=api_key)
        if key_type == "DEEPSEEK_API_KEY":
            client = client.with_options(base_url="https://api.deepseek.com")
        if setting_of(10) == 1:
            client = client.with_options(
                base_url=ai_setting.now_ai_chat_base_url
            )
        if setting_of(11) == 1:
            client = client.with_options(
                http_client=openai.DefaultHttpxClient(
                    proxy=ai_setting.now_ai_chat_proxy[0]
                )
            )
        return client
    api_version = "v1alpha" if setting_of(12) == 1 else None
    base_url = ai_setting.now_ai_chat_base_url if setting_of(10) == 1 else None
    if api_version or base_url:
        return genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(
                api_version=api_version, base_url=base_url
            ),
        )
    return genai.Client(api_key=api_key)


def _ask(client: Any, key_type: str) -> Any:
    """向当前模型发送固定测试消息，遇到未知 key_type 时抛出 ValueError。"""
    model = normal_config.ai_setting.ai_chat_setting[5]
    if key_type in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        return client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "这是一条测试消息，如果收到请指直接回复1即可，不需要思考，不要回复其他内容",
                        }
                    ],
                }
            ],
        )
    if key_type == "GEMINI_API_KEY":
        return client.models.generate_content(
            model=model,
            contents="这是一条测试消息，如果收到请指直接回复1即可，不需要思考，不需要回复其他内容",
        )
    raise ValueError(_("不支持的API密钥类型：{0}").format(key_type))


def ping(client: Any, key_type: str, show: Callable[[str], None]) -> str | None:
    """
    在工作线程执行连通测试，关闭线程池前回调 show 并返回错误文本。
    Keyword arguments:
    client -- Any，模型客户端实例
    key_type -- str，API密钥类型名
    show -- Callable[[str], None]，显示测试结果文本的回调
    Return arguments:
    str | None -- 测试通过返回 None，超时或异常返回错误文本
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_ask, client, key_type)
        try:
            future.result(timeout=TEST_SECONDS)
            info_text = _(" \n  测试通过\n")
            error = None
        except concurrent.futures.TimeoutError:
            info_text = _(" \n  测试不通过，原因：连接超时\n")
            error = _("连接超时")
        except Exception as e:
            info_text = _(" \n  测试不通过，原因：{0}\n").format(e)
            error = str(e)
        finally:
            show(info_text)
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
    return error
