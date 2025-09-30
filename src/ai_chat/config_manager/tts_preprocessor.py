# config_manager/translate.py
from typing import Literal, Optional, Dict, ClassVar
from pydantic import ValidationInfo, Field, model_validator
from .i18n import I18nMixin, Description

# --- Sub-models for specific Translator providers ---
class TTSPreprocessorConfig(I18nMixin):
    """Configuration for TTS preprocessor."""
    
    # --- TTS Preprocessor ---
    # 移除特殊字符
    remove_special_char: bool = Field(..., alias="remove_special_char")
    # 忽略括号
    ignore_brackets: bool = Field(default=True, alias="ignore_brackets")
    # 忽略括号
    ignore_parentheses: bool = Field(default=True, alias="ignore_parentheses")
    # 忽略星号
    ignore_asterisks: bool = Field(default=True, alias="ignore_asterisks")
    # 忽略尖括号
    ignore_angle_brackets: bool = Field(default=True, alias="ignore_angle_brackets")
    # 忽略连字符
    ignore_hyphens: bool = Field(default=True, alias="ignore_hyphens")
    # 忽略斜杠
    ignore_slashes: bool = Field(default=True, alias="ignore_slashes")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "remove_special_char": Description(
            en="Remove special characters from the input text",
            zh="从输入文本中删除特殊字符",
        )
    }
