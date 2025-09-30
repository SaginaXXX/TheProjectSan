
"""
Configuration management package for Open LLM VTuber.

This package provides configuration management functionality through Pydantic models
and utility functions for loading/saving configurations.
"""

# Import main configuration classes
from .main import Config
from .system import SystemConfig
from .character import CharacterConfig
from .stateless_llm import (
    OpenAICompatibleConfig,
    OpenAIConfig,
    StatelessLLMConfigs,

)
from .asr import (
    SherpaOnnxASRConfig,
    ASRConfig,
)
from .tts import (
    FishAPITTSConfig,
    TTSConfig,
)
from .tts_preprocessor import (
    TTSPreprocessorConfig,
)
from .vad import (
    VADConfig,
    SileroVADConfig,
)
from .tts_preprocessor import TTSPreprocessorConfig
from .i18n import I18nMixin, Description, MultiLingualString
from .agent import  (
    AgentConfig,
    AgentSettings,
    StatelessLLMConfigs,
    BasicMemoryAgentConfig,
)

# Import utility functions
from .utils import (
    read_yaml,
    validate_config,
    save_config,
    scan_config_alts_directory,
    scan_bg_directory,
)

__all__ = [
    # Main configuration classes
    "Config",
    "SystemConfig",
    "CharacterConfig",
    
    # LLM related classes - 只保留已实现的
    "OpenAICompatibleConfig",
    "OpenAIConfig", 
    "StatelessLLMConfigs",
    
    # Agent related classes
    "AgentConfig",
    "AgentSettings",
    "BasicMemoryAgentConfig",
    
    # ASR related classes 
    "SherpaOnnxASRConfig",
    
    # TTS related classes 
    "FishAPITTSConfig",
    
    # VAD related classes
    "VADConfig",
    "SileroVADConfig",
    
    # TTS preprocessor related classes
    "TTSPreprocessorConfig",
    "TranslatorConfig",
    "DeepLXConfig",
    
    # i18n related classes
    "I18nMixin",
    "Description",
    "MultiLingualString",
    
    # Utility functions
    "read_yaml",
    "validate_config",
    "save_config",
    "scan_config_alts_directory",
    "scan_bg_directory",
]