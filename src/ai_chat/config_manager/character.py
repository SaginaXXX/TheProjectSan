from pydantic import Field, field_validator
from typing import Dict, ClassVar
from .i18n import I18nMixin, Description
from .agent import AgentConfig
from .asr import ASRConfig
from .tts import TTSConfig
from .vad import VADConfig
from .tts_preprocessor import TTSPreprocessorConfig

# 角色配置
class CharacterConfig(I18nMixin):
    """Character configuration settings."""

    conf_name: str = Field(..., alias="conf_name") # 配置文件名称
    conf_uid: str = Field(..., alias="conf_uid") # 配置文件UID
    live2d_model_name: str = Field(..., alias="live2d_model_name") # Live2D模型名称
    character_name: str = Field(..., alias="character_name") # 角色名称
    human_name: str = Field(..., alias="human_name") # 人类名称
    avatar: str = Field(..., alias="avatar") # 头像URL
    persona_prompt: str = Field(..., alias="persona_prompt") # 角色提示词
    agent_config: AgentConfig = Field(..., alias="agent_config") # 智能体配置
    asr_config: ASRConfig = Field(..., alias="asr_config") # ASR配置
    tts_config: TTSConfig = Field(..., alias="tts_config") # TTS配置
    vad_config: VADConfig = Field(..., alias="vad_config") # VAD配置
    tts_preprocessor_config: TTSPreprocessorConfig = Field(
        ..., alias="tts_preprocessor_config"
    ) # TTS预处理器配置

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "conf_name": Description(
            en="Configuration file name",
            zh="配置文件名称"
        ),
        "conf_uid": Description(
            en="Configuration file UID",
            zh="配置文件UID"
        ),
        "live2d_model_name": Description(
            en="Live2D model name",
            zh="Live2D模型名称"
        ),
        "character_name": Description(
            en="Character name",
            zh="角色名称"
        ),
        "human_name": Description(
            en="Human name",
            zh="人类名称"
        ),
        "avatar": Description(
            en="Avatar URL",
            zh="头像URL"
        ),
        "persona_prompt": Description(
            en="Persona prompt",
            zh="角色提示词"
        ),
        "agent_config": Description(
            en="Agent configuration",
            zh="智能体配置"
        ),
        "asr_config": Description(
            en="ASR configuration",
            zh="ASR配置"    
        ),
        "tts_config": Description(
            en="TTS configuration",
            zh="TTS配置"
        ),
        "vad_config": Description(
            en="VAD configuration",
            zh="VAD配置"
        ),
        "tts_preprocessor_config": Description(
            en="TTS preprocessor configuration",
            zh="TTS预处理器配置"
        ),
    }
    
    @field_validator("persona_prompt")
    def check_default_persona_prompt(cls, v):
        if not v:
            raise ValueError(
                "Persona_prompt cannot be empty. Please provide a persona prompt." # 角色提示词不能为空
            )
        return v
    
    @field_validator("character_name")
    def set_default_character_name(cls, v, values):
        if not v and "conf_name" in values:
            return values["conf_name"] # 如果角色名称未设置，则使用配置文件名称 
        return v
