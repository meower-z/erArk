"""
把当前目录下 name.txt 里以空行分隔的段落写成当前目录下 output.csv 的行
"""

import csv

# 定义txt文件路径
txt_path = 'name.txt'
# 定义输出csv文件路径
csv_path = 'output.csv'


# 读取txt文件并按行存入列表
def read_txt_to_list(txt_path: str) -> list[str]:
  """
  按空行把文本文件分段：每段去掉首尾空白，段内换行转写成反斜杠加 n 两个字符
  Keyword arguments:
  txt_path -- 文本文件路径
  Return arguments:
  list -- 各段的字符串
  """
  with open(txt_path, 'r', encoding='utf-8') as file:
    lines = file.readlines()

  result = []
  current_element: list[str] = []

  for line in lines:
    # 如果读到完全空行，将当前元素加入结果列表
    if line == '\n':
      if current_element:
        # 将除了最后一个换行符之外的换行符都替换为 \n
        element = ''.join(current_element).strip()
        element = element.replace('\n', '\\n')
        element = element.replace('\\n\\n', '\n')
        result.append(element)
        current_element = []
    else:
      current_element.append(line)

  # 处理文件末尾没有空行的情况
  if current_element:
    element = ''.join(current_element).strip()
    element = element.replace('\n', '\\n')
    element = element.replace('\\n\\n', '\n')
    result.append(element)

  return result


# 将列表数据保存到csv文件
def save_list_to_csv(data: list[str], csv_path: str) -> None:
  """
  把每段写成 csv 的一行：从 1 起的序号、101、1、high_1、该段；覆盖原有文件
  Keyword arguments:
  data -- 各段的字符串
  csv_path -- 输出 csv 文件路径
  Return arguments:
  None
  """
  with open(csv_path, 'w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    # 初始化条目编号
    count = 1
    for element in data:
      # 按行写入csv文件
      writer.writerow([count, 101, 1, 'high_1', element])
      count += 1


if __name__ == '__main__':
  # 读取txt文件内容
  data = read_txt_to_list(txt_path)
  # 保存内容到csv文件
  save_list_to_csv(data, csv_path)
