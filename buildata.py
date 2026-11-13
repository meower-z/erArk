"""前提与结算代码的开发辅助脚本，按顶部的 mode 运行下面列出的一种模式。模式 1 生成一条前提的处理函数。
模式 3 和模式 5 把 tools/csv 里的 csv 表转成 constant_promise.py 或 constant_effect.py 的常量与说明行
"""

import os
import re

from Script.Config import game_config

"""
自动生成前提的文件
"""


# 运行模式：
# 0 不运行任何模式，只打印提示
# 1 生成一条前提：处理函数接到 handle_premise 包里 premise_module 模块的末尾，
#   constant_promise 的常量与说明行只打印出来
# 3 csv 转前提文件：tools/csv/premise.csv 接到 constant_promise.py 末尾
# 5 csv 转结算文件：tools/csv/Effect.csv 接到 constant_effect.py 的 BehaviorEffect 类末尾
mode = 0
command_str = "lactation_1"
capital_command = command_str.upper()
dataname = "泌乳"
datetype = "T"
premise_type_diy = "自定义内容"
premise_type_dict = {
    "A": "属性_能力",
    "S": "属性_状态",
    "T": "属性_素质",
    "X": premise_type_diy,
}
premise_type = premise_type_dict[datetype]
premise_module_dict = {
    "A": "handle_premise_ability.py",
    "S": "handle_premise_other.py",
    "T": "handle_premise_talent.py",
    "X": "handle_premise_other.py",
}
""" 各类前提的处理函数写进 handle_premise 包里的哪个模块：能力进能力模块，素质进素质模块，
状态与自定义内容进其他通用前提模块 """
premise_module = premise_module_dict[datetype]

# 数据初始化
game_config.init()


def class_indent(path: str) -> str:
    """
    读代码文件里第一条缩进行的缩进，写进去的代码照它缩进
    Keyword arguments:
    path -- 代码文件路径
    Return arguments:
    str -- 缩进的空白，文件里没有缩进行时是 4 个空格
    """
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and line[0] in " \t":
                return line[: len(line) - len(line.lstrip())]
    return "    "


def constant_line(name: str, value: str, indent: str = "    ") -> str:
    """
    生成一条类常量赋值。整行超过 80 列、缩进后的值不超过 80 列时，按 black 的排法折成「常量名 = (」「值」「)」三行
    Keyword arguments:
    name -- 常量名
    value -- 值的源码文字（带引号的字符串或整数）
    indent -- 类成员的缩进
    Return arguments:
    str -- 赋值的源码，以换行结尾
    """
    line = f"{indent}{name} = {value}"
    if len(line) > 80 and len(indent) + 4 + len(value) <= 80:
        return f"{indent}{name} = (\n{indent}    {value}\n{indent})\n"
    return line + "\n"


def appended_block(text: str) -> str:
    """
    整理要接到常量文件末尾或类末尾的一段代码，使空行合乎 black 的格式：开头留一个空行，连续空行并成一个，末尾不留空行
    Keyword arguments:
    text -- 要接上的代码
    Return arguments:
    str -- 整理后的代码
    """
    return "\n" + re.sub(r"\n{3,}", "\n\n", text.strip("\n")) + "\n"


def class_end_index(line_list: list, class_name: str) -> int:
    """
    找到类的最后一行代码之后的位置，接在这里的代码仍属于这个类
    Keyword arguments:
    line_list -- 代码文件的全部行（readlines() 的结果）
    class_name -- 类名
    Return arguments:
    int -- 类的最后一个非空行的下一行的下标
    """
    start_index = line_list.index(f"class {class_name}:\n")
    end_index = len(line_list)
    # 类体到下一个顶格的语句为止
    for index in range(start_index + 1, len(line_list)):
        if line_list[index].strip() and line_list[index][0] not in " \t":
            end_index = index
            break
    # 退过类体末尾的空行
    while not line_list[end_index - 1].strip():
        end_index -= 1
    return end_index


def constand_2_handle() -> str:
    """
    输出constand_promise里的标准格式，以及把前提处理函数接到 handle_premise 包里 premise_module 模块的末尾
    """

    # 判断数据编号
    data_index: int | str
    if datetype == "A":
        datetype_str = "ability"
        for config_data_index in game_config.config_ability:
            if game_config.config_ability[config_data_index].name == dataname:
                data_index = config_data_index
                break
    elif datetype == "S":
        datetype_str = "status_data"
        for config_data_index in game_config.config_character_state:
            if (
                game_config.config_character_state[config_data_index].name
                == dataname
            ):
                data_index = config_data_index
                break
    elif datetype == "T":
        datetype_str = "talent"
        for config_data_index in game_config.config_talent:
            if game_config.config_talent[config_data_index].name == dataname:
                data_index = config_data_index
                break
    else:
        datetype_str, data_index = "数据类型", "数据序号"
    print(f"数据名 = {dataname}，类型 = {datetype_str}，id = {data_index}")

    command_list = command_str.split("_")

    # 判断运算符号
    operation = "=="
    for str_part in command_list:
        if str_part == "ge":
            operation = ">="
            break
        elif str_part == "le":
            operation = "<="
            break
        elif str_part == "g":
            operation = ">"
            break
        elif str_part == "l":
            operation = "<"
            break

    # 判断是否为交互对象
    target_flag = False
    for str_part in command_list:
        if str_part == "t":
            target_flag = True
            break

    # 生成constant_promise的out_str
    indent = class_indent(os.path.join("Script", "Core", "constant_promise.py"))
    out_str = "\n" + constant_line(capital_command, f'"{command_str}"', indent)
    out_str += f'{indent}""" {premise_type} '
    if target_flag:
        out_str += "交互对象"
    else:
        out_str += "自己"
    out_str += f'{dataname}{operation}{command_list[-1]} """\n'
    print(out_str)

    # 输出到constant_promise里，还没写出来
    """
    break_flag = 0
    with open(os.path.join("Script", "Core", "constant_promise.py"), "r+",encoding="utf-8") as f:
        while 1:
            a=f.readline() # 逐行读取
            if len(a) >= 3 and a[-3] == "\"": # 锁定到文字行
                promise_text = a.split("\"")[-4].strip()
                if promise_text != "前提id":
                    # print(f"debug promise_text = {promise_text}")
                    promise_type,promise_info = promise_text.split(" ")[0],promise_text.split(" ")[1]
                    if promise_type == premise_type:
                        break_flag = 1
                    if break_flag == 1 and promise_type != premise_type:
                        f.write(out_str)
                        break
        f.close()
    out_str = "\n"
    """

    # 进行前提输出，函数体照目标模块的缩进
    premise_path = os.path.join(
        "Script", "Design", "handle_premise", premise_module
    )
    indent = class_indent(premise_path)
    out_str = "\n\n"
    out_str += f"@add_premise(constant_promise.Premise.{capital_command})\n"
    out_str += f"def handle_{command_str}(character_id: int) -> int:\n"
    out_str += f'{indent}"""\n'
    if not target_flag:
        out_str += (
            f"{indent}校验角色是否{dataname}{operation}{command_list[-1]}\n"
        )
    else:
        out_str += (
            f"{indent}校验交互对象是否{dataname}{operation}{command_list[-1]}\n"
        )
    out_str += f"{indent}Keyword arguments:\n"
    out_str += f"{indent}character_id -- 角色id\n"
    out_str += f"{indent}Return arguments:\n"
    out_str += f"{indent}int -- 权重\n"
    out_str += f'{indent}"""\n'
    out_str += f"{indent}character_data = cache.character_data[character_id]\n"
    if target_flag:
        out_str += f"{indent}target_data = cache.character_data[character_data.target_character_id]\n"
        out_str += f"{indent}if target_data.{datetype_str}[{data_index}] {operation} {command_list[-1]}:\n"
    else:
        out_str += f"{indent}if character_data.{datetype_str}[{data_index}] {operation} {command_list[-1]}:\n"
    out_str += f"{indent}{indent}return 1\n"
    out_str += f"{indent}return 0\n"

    # 开始保存
    with open(premise_path, "a", encoding="utf-8") as f:
        f.write(out_str)
        f.close()
    print(f"已写入{premise_path}末尾")

    return out_str


def csv_2_constand() -> str:
    """
    csv转前提文件（mode 3）：读 tools/csv/premise.csv，把每个前提写成常量与说明行，接到 constant_promise.py 末尾
    Keyword arguments:
    无
    Return arguments:
    str -- 接到文件末尾的文本
    """
    with open(
        os.path.join("tools", "csv", "premise.csv"), encoding="utf-8"
    ) as f:
        a = f.readlines()
        f.close()

    indent = class_indent(os.path.join("Script", "Core", "constant_promise.py"))
    out_str = "\n"
    for line in a:
        promise_text = line.strip().split(",")
        print(f"debug promise_text = {promise_text}")
        if len(promise_text) == 1:
            out_str += "\n"
        elif promise_text[0] != "cid" and len(promise_text) == 4:
            out_str += constant_line(
                promise_text[1], f'"{promise_text[0]}"', indent
            )
            out_str += f'{indent}""" {promise_text[2]} {promise_text[3]} """\n'

    out_str = appended_block(out_str)

    # 开始保存
    with open(
        os.path.join("Script", "Core", "constant_promise.py"),
        "a",
        encoding="utf-8",
    ) as f:
        f.write(out_str)
        f.close()
    print("已写入前提文件末尾")

    return out_str


def csv_2_constand_effect() -> str:
    """
    csv转结算文件（mode 5）：读 tools/csv/Effect.csv，把每个结算写成常量与说明行，接到 constant_effect.py 里
    BehaviorEffect 类的末尾
    Keyword arguments:
    无
    Return arguments:
    str -- 接到类末尾的文本
    """
    with open(
        os.path.join("tools", "csv", "Effect.csv"), encoding="utf-8"
    ) as f:
        a = f.readlines()
        f.close()

    indent = class_indent(os.path.join("Script", "Core", "constant_effect.py"))
    out_str = "\n"
    for line in a:
        effect_text = line.strip().split(",")
        if len(effect_text) == 1:
            out_str += "\n"
        elif effect_text[0] != "cid":
            out_str += constant_line(effect_text[1], effect_text[0], indent)
            out_str += f'{indent}""" {effect_text[2]} {effect_text[3]} """\n'

    out_str = appended_block(out_str)

    # 开始保存：接到 BehaviorEffect 类的末尾，类后面的内容原样保留
    effect_path = os.path.join("Script", "Core", "constant_effect.py")
    with open(effect_path, encoding="utf-8") as f:
        line_list = f.readlines()
    insert_index = class_end_index(line_list, "BehaviorEffect")
    line_list.insert(insert_index, out_str)
    with open(effect_path, "w", encoding="utf-8") as f:
        f.writelines(line_list)
    print("已写入结算文件 BehaviorEffect 类末尾")

    return out_str


if __name__ == "__main__":
    if mode == 1:
        out_str = constand_2_handle()
    elif mode == 3:
        csv_2_constand()
    elif mode == 5:
        csv_2_constand_effect()
    else:
        print("把 buildata.py 顶部的 mode 改成 1、3 或 5 再运行")
