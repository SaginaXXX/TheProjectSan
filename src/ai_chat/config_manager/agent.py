"""
This module contains the pydantic model for the configurations of
different types of agents.
"""

from pydantic import BaseModel, Field
from typing import Dict, ClassVar, Optional, Literal, List
from .i18n import I18nMixin, Description
from .stateless_llm import StatelessLLMConfigs

# ==========  Config for different type of agents ========

# 基础记忆智能体配置
class BasicMemoryAgentConfig(I18nMixin):
    """Configuration for the Basic Memory Agent."""

    llm_provider: Literal[
        "stateless_llm_with_template", 
        "openai_compatible_llm", 
        "llama_cpp_llm", 
        "ollama_llm", 
        "lmstudio_llm", 
        "openai_llm"
        ] = Field(..., alias="llm_provider")
     
    # 是否使用更快的首次响应
    faster_first_response: Optional[bool] = Field(False, alias="faster_first_response")
    # 分割句子的方法
    segment_method: Literal["regex", "pysbd"] = Field("pysbd", alias="segment_method")
    # 是否使用mcpp
    use_mcpp: Optional[bool] = Field(False, alias="use_mcpp")
    # 为agent 启用 MCP 的服务器列表
    mcp_enabled_servers: Optional[List[str]] = Field([], alias="mcp_enabled_servers")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        # 大语言模型提供者  
        "llm_provider": Description(en="LLM provider to use for this agent", zh="Basic Memory Agent 智能体使用的大语言模型选项"),
        "faster_first_response": Description(en="Whether to use faster first response", zh="是否使用更快的首次响应"),
        "segment_method": Description(en="Method for segmenting sentences: 'regex' or 'pysbd' (default: 'pysbd')", zh="分割句子的方法：'regex' 或 'pysbd'（默认：'pysbd'）"),
        "use_mcpp": Description(en="Whether to use mcpp", zh="是否使用mcpp"),
        "mcp_enabled_servers": Description(en="List of MCP enabled servers", zh="为agent 启用 MCP 的服务器列表"),
    }

# 智能体设置
class AgentSettings(I18nMixin):
    """Settings for different types of agents."""
    # 基础记忆智能体配置
    basic_memory_agent: Optional[BasicMemoryAgentConfig] = Field(None, alias="basic_memory_agent")
    # 描述
    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "basic_memory_agent": Description(en="Basic Memory Agent", zh="基础记忆智能体"),
    }


# 智能体配置
class AgentConfig(I18nMixin):
    """This class contains all of the configurations related to agent."""

    # 对话智能体类型
    conversation_agent_choice: Literal["basic_memory_agent"] = Field(..., alias="conversation_agent_choice")
    # 智能体设置
    agent_settings: AgentSettings = Field(..., alias="agent_settings")
    # 大语言模型配置
    llm_config: StatelessLLMConfigs = Field(..., alias="llm_config")
    # 描述
    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        # 对话智能体类型
        "conversation_agent_choice": Description(en="The type of conversation agent to use.", zh="要使用的对话智能体类型。"),
        # 智能体设置
        "agent_settings": Description(en="Settings for different types of agents.", zh="不同类型智能体的设置。"),
        # 大语言模型配置
        "llm_config": Description(en="Configuration for the LLM.", zh="LLM的配置。"),
        # 描述
        "DESCRIPTIONS": Description(en="Descriptions for the agent configuration.", zh="智能体配置的描述。"),
    }



