# config_manager/main.py
from pydantic import BaseModel, Field
from typing import Dict, ClassVar

from .i18n import I18nMixin, Description
from .system import SystemConfig
from .character import CharacterConfig

class Config(I18nMixin):
    """
    Main configuration for the application.
    """

    system_config: SystemConfig = Field(default=None, alias="system_config") # 系统配置
    character_config: CharacterConfig = Field(..., alias="character_config") # 角色配置

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "system_config": Description(
            en="System configuration settings",
            zh="系统配置设置"
        ),
        "character_config": Description(
            en="Character configuration settings",
            zh="角色配置设置"
        ),
        "live_config": Description(
            en="Live streaming platform integration settings",
            zh="直播平台集成设置"
        ),
    }