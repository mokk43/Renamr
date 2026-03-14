import sys
import re

def looks_like_chapter_title(line):
    """
    判断一行文本是否看起来像章节标题，如“第一章xxx”。
    """
    stripped = line.strip()
    return bool(re.match(r"^第[0-9一二三四五六七八九十百千零两]+[章节回卷部篇][^\n]*$", stripped))


def should_start_new_paragraph(previous_line, next_line):
    """
    根据上下文判断是否应在两行之间保留段落分隔。
    """
    # 标题后面通常开启新段落
    if looks_like_chapter_title(previous_line):
        return True

    # 以句末标点结束时，倾向于视作段落结束
    if re.search(r'[。！？!?…]["”’」』）】》]*$', previous_line):
        return True

    # 下一行是章节标题，也应开启新段落
    if looks_like_chapter_title(next_line):
        return True

    return False


def join_wrapped_lines(previous_line, next_line):
    """
    拼接折行文本。
    - 中文连续文本直接拼接
    - 英文/数字单词边界之间补一个空格
    """
    if (
        previous_line
        and next_line
        and previous_line[-1].isascii()
        and previous_line[-1].isalnum()
        and next_line[0].isascii()
        and next_line[0].isalnum()
    ):
        return f"{previous_line} {next_line}"
    return f"{previous_line}{next_line}"


def extract_fullwidth_indent(raw_line):
    """
    提取行首全角空格缩进（\u3000）。
    """
    match = re.match(r"^(\u3000+)", raw_line)
    return match.group(1) if match else ""


def looks_like_indented_paragraph(raw_line):
    """
    判断一行是否像段落开头（至少两个空白字符缩进）。
    """
    return bool(re.match(r"^[ \t\u3000]{2,}\S", raw_line))


def normalize_text_layout(text):
    """
    规范化文本布局：
    1. 清理行首缩进和行尾空白；
    2. 合并被折行拆开的句子；
    3. 保留段落之间的空行。
    """
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    raw_lines = normalized.split('\n')

    paragraphs = []
    separators = []
    current = ""
    has_pending_blank_line = False

    for raw_line in raw_lines:
        line = raw_line.strip(" \t\u3000")
        fullwidth_indent = extract_fullwidth_indent(raw_line)
        line_with_indent = f"{fullwidth_indent}{line}" if fullwidth_indent else line

        if not line:
            has_pending_blank_line = True
            continue

        if not current:
            current = line_with_indent
            has_pending_blank_line = False
            continue

        if has_pending_blank_line and should_start_new_paragraph(current, line):
            paragraphs.append(current)
            separators.append("\n\n")
            current = line_with_indent
        elif looks_like_indented_paragraph(raw_line) and should_start_new_paragraph(current, line):
            paragraphs.append(current)
            separators.append("\n")
            current = line_with_indent
        else:
            current = join_wrapped_lines(current, line)

        has_pending_blank_line = False

    if current:
        paragraphs.append(current)

    if not paragraphs:
        return ""

    output = paragraphs[0]
    for idx in range(1, len(paragraphs)):
        output += separators[idx - 1] + paragraphs[idx]
    return output


def normalize_text_file(input_filepath, output_filepath="output.txt"):
    """
    处理指定的文本文件，移除所有前后为字符的换行符，
    并将处理后的内容输出到新文件。
    会自动尝试 UTF-8 和 GBK 编码读取输入文件。

    Args:
        input_filepath (str): 输入文本文件的路径。
        output_filepath (str): 输出文本文件的路径。
    """
    content = None
    possible_encodings = ['utf-8', 'gbk', 'gb2312'] # 常用编码列表

    for encoding_to_try in possible_encodings:
        try:
            with open(input_filepath, 'r', encoding=encoding_to_try) as f_in:
                content = f_in.read()
            print(f"文件成功以 {encoding_to_try} 编码读取。")
            break  # 如果成功读取，就跳出循环
        except UnicodeDecodeError:
            print(f"尝试使用 {encoding_to_try} 编码读取文件失败...")
        except FileNotFoundError:
            print(f"错误：输入文件 '{input_filepath}' 未找到。")
            return # 文件都找不到，直接退出函数
        except Exception as e:
            print(f"尝试使用 {encoding_to_try} 编码读取时发生其他错误：{e}")
            # 对于其他未知错误，也可能需要中断

    if content is None:
        print(f"错误：无法使用尝试的编码 ({', '.join(possible_encodings)}) 打开文件 '{input_filepath}'。请确认文件编码。")
        return

    try:
        processed_content = normalize_text_layout(content)

        with open(output_filepath, 'w', encoding='utf-8') as f_out: # 输出文件统一为 UTF-8
            f_out.write(processed_content)

        print(f"文件处理成功！结果已保存到 {output_filepath} (UTF-8 编码)。")

    except Exception as e:
        print(f"处理文件内容或写入输出文件时发生错误：{e}")