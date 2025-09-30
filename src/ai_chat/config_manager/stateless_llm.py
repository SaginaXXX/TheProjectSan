# config_manager/stateless_llm.py
from typing import ClassVar, Literal
from pydantic import BaseModel, Field
from .i18n import I18nMixin, Description

# ==========  Base configuration for stateless LLM ==========
class StatelessLLMBaseConfig(I18nMixin):
    """Base configuration for StatelessLLM."""

    # interrupt_method. If the provider supports inserting system prompt anywhere in the chat memory, use "system". Otherwise, use "user".
    interrupt_method: Literal["system", "user"] = Field(
        "user", alias="interrupt_method"
    )
    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "interrupt_method": Description(
            en="""The method to use for prompting the interruption signal.
            If the provider supports inserting system prompt anywhere in the chat memory, use "system". 
            Otherwise, use "user". You don't need to change this setting.""",
            zh="""用于表示中断信号的方法(提示词模式)。如果LLM支持在聊天记忆中的任何位置插入系统提示词，请使用“system”。
            否则，请使用“user”。""",
        ),
    }



    

# 标准OpenAI兼容
class OpenAICompatibleConfig(StatelessLLMBaseConfig):
    """Configuration for OpenAI-compatible LLM providers."""

    base_url: str = Field(..., alias="base_url")
    llm_api_key: str = Field(..., alias="llm_api_key")
    model: str = Field(..., alias="model")
    organization_id: str | None = Field(None, alias="organization_id")
    project_id: str | None = Field(None, alias="project_id")
    temperature: float = Field(1.0, alias="temperature")

    _OPENAI_COMPATIBLE_DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "base_url": Description(en="The base URL of the LLM provider.", zh="LLM提供者的基础URL。"),
        "llm_api_key": Description(en="The API key of the LLM provider.", zh="LLM提供者的API密钥。"),
        "model": Description(en="The model name of the LLM provider.", zh="LLM提供者的模型名称。"),
        "organization_id": Description(en="The organization ID of the LLM provider.", zh="LLM提供者的组织ID(可选，一些API提供商需要此字段)。"),
        "project_id": Description(en="The project ID of the LLM provider.", zh="LLM提供者的项目ID（可选，一些API提供商需要此字段。"),
        "temperature": Description(en="What sampling temperature to use, between 0 and 2.", zh="使用的采样温度，介于 0 和 2 之间"),
    }

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        **StatelessLLMBaseConfig.DESCRIPTIONS,
        **_OPENAI_COMPATIBLE_DESCRIPTIONS,
    }
 



# OpenAI 的配置方式  （ 云端部署）
class OpenAIConfig(OpenAICompatibleConfig):
    """Configuration for Official OpenAI API."""

    base_url: str = Field("https://api.openai.com/v1", alias="base_url")
    interrupt_method: Literal["system", "user"] = Field(
        "system", alias="interrupt_method"
    )


    


# 无状态LLM配置池
class StatelessLLMConfigs(I18nMixin):
    """Pool of LLM provider configurations.
    This class contains configurations for different LLM providers."""
    

    # openai 兼容配置方式
    openai_compatible_llm: OpenAICompatibleConfig | None = Field(
        None, alias="openai_compatible_llm"
    )

    # openai 配置方式
    openai_llm: OpenAIConfig | None = Field(None, alias="openai_llm")
    

    # 配置池描述
    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
       "stateless_llm_with_template": Description(en="The configuration for the stateless LLM with template.", zh="无状态LLM配置模板。"),
       "openai_llm": Description(en="The configuration for the OpenAI LLM.", zh="OpenAI LLM配置。"),
    }