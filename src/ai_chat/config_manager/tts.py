# config_manager/tts.py
from pydantic import ValidationInfo, Field, model_validator
from typing import Literal, Optional, Dict, ClassVar
from .i18n import I18nMixin, Description


class FishAPITTSConfig(I18nMixin):
    """Configuration for Fish API TTS."""
    # --- Fish API TTS --- 
    # API密钥
    api_key: str = Field(..., alias="api_key")
    # 参考ID
    reference_id: str = Field(..., alias="reference_id")
    # 延迟
    latency: Literal["normal", "balanced"] = Field(..., alias="latency")
    # 基础URL
    base_url: str = Field(..., alias="base_url")
    
    # --- Descriptions ---
    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "api_key": Description(
            en="API key for Fish TTS service", zh="Fish TTS 服务的 API 密钥"
        ),
        "reference_id": Description(
            en="Voice reference ID from Fish Audio website",
            zh="来自 Fish Audio 网站的语音参考 ID",
        ),
        "latency": Description(
            en="Latency mode (normal or balanced)", zh="延迟模式（normal 或 balanced）"
        ),
        "base_url": Description(
            en="Base URL for Fish TTS API", zh="Fish TTS API 的基础 URL"
        ),
    }


class TTSConfig(I18nMixin):
    """Configuration for Text-to-Speech."""

    tts_model: Literal[
        
        "fish_api_tts",
        "openai_tts",  # Add openai_tts here

    ] = Field(..., alias="tts_model")


    fish_api_tts: Optional[FishAPITTSConfig] = Field(None, alias="fish_api_tts")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "tts_model": Description(
            en="Text-to-speech model to use", zh="要使用的文本转语音模型"
        ),
        "fish_api_tts": Description(
            en="Configuration for Fish API TTS", zh="Fish API TTS 配置"
        ),

    }

    @model_validator(mode="after")
    def check_tts_config(cls, values: "TTSConfig", info: ValidationInfo):
        tts_model = values.tts_model

        # Only validate the selected TTS model

        if tts_model == "fish_api_tts" and values.fish_api_tts is not None:
            values.fish_api_tts.model_validate(values.fish_api_tts.model_dump())
        

        return values
