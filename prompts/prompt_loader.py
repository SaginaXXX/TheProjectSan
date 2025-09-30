import os
import chardet
from loguru import logger

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 定义提示词目录
PROMPT_DIR = current_dir
# 定义人物提示词目录
PERSONA_PROMPT_DIR = os.path.join(PROMPT_DIR, "persona")
# 定义工具提示词目录
UTIL_PROMPT_DIR = os.path.join(PROMPT_DIR, "utils")


# 加载文件内容
def _load_file_content(file_path: str) -> str:
    """
    Load the content of a file with robust encoding handling.

    Args:
        file_path: Path to the file to load

    Returns:
        str: Content of the file

    Raises:
        FileNotFoundError: If the file doesn't exist
        UnicodeError: If the file cannot be decoded with any attempted encoding
    """
    # 如果文件不存在，抛出异常
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # 尝试常见的编码
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii"]
    # 遍历编码
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue

    # 如果所有常见的编码都失败，尝试检测编码
    try:
        with open(file_path, "rb") as file:
            raw_data = file.read()
        detected = chardet.detect(raw_data)
        detected_encoding = detected["encoding"]

        if detected_encoding:
            try:
                return raw_data.decode(detected_encoding)
            except UnicodeDecodeError:
                pass
    except Exception as e:
        logger.error(f"Error detecting encoding for {file_path}: {e}")

    raise UnicodeError(f"Failed to decode {file_path} with any encoding")


# 加载人物提示词
def load_persona(persona_name: str) -> str:
    """加载特定人物的提示词文件。"""
    # 构建人物提示词文件路径
    persona_file_path = os.path.join(PERSONA_PROMPT_DIR, f"{persona_name}.txt")
    try:
        # 加载文件内容
        return _load_file_content(persona_file_path)
    except Exception as e:
        # 如果加载失败，记录错误并抛出异常
        logger.error(f"Error loading persona {persona_name}: {e}")
        raise


# 加载工具提示词
def load_util(util_name: str) -> str:
    """加载特定工具的提示词文件。"""
    # 构建工具提示词文件路径
    util_file_path = os.path.join(UTIL_PROMPT_DIR, f"{util_name}.txt")
    try:
        # 加载文件内容
        return _load_file_content(util_file_path)
    except Exception as e:
        # 如果加载失败，记录错误并抛出异常
        logger.error(f"Error loading util {util_name}: {e}")
        raise
