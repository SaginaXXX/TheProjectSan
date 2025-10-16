import os
import json
import asyncio
from typing import Callable
from loguru import logger
from fastapi import WebSocket

from prompts import prompt_loader
from .live2d_model import Live2dModel
from .asr.asr_interface import ASRInterface
from .tts.tts_interface import TTSInterface
from .vad.vad_interface import VADInterface
from .agent.agents.agent_interface import AgentInterface

from .mcpp.server_registry import ServerRegistry
from .mcpp.tool_manager import ToolManager
from .mcpp.mcp_client import MCPClient
from .mcpp.tool_executor import ToolExecutor
from .mcpp.json_detector import StreamJSONDetector
from .mcpp.tool_adapter import ToolAdapter

from .asr.asr_factory import ASRFactory
from .tts.tts_factory import TTSFactory
from .vad.vad_factory import VADFactory
from .agent.agent_factory import AgentFactory

from .config_manager import (
    Config,
    AgentConfig,
    CharacterConfig,
    SystemConfig,
    ASRConfig,
    TTSConfig,
    VADConfig,
    read_yaml,
    validate_config,
)


class ServiceContext:
    """Initializes, stores, and updates the asr, tts, and llm instances and other
    configurations for a connected client."""

    def __init__(self):
        # system configs
        self.config: Config = None
        self.system_config: SystemConfig = None
        self.character_config: CharacterConfig = None
        
        # ✅ 追踪后台任务，防止内存泄漏
        self._background_tasks: list = []
        
        # agent components
        self.live2d_model: Live2dModel = None
        self.asr_engine: ASRInterface = None
        self.tts_engine: TTSInterface = None
        self.agent_engine: AgentInterface = None
        # translate_engine can be none if translation is disabled
        self.vad_engine: VADInterface | None = None
        self.translate_engine = None  # Add translate_engine attribute
       
        # MCP components
        self.mcp_server_registery: ServerRegistry | None = None
        self.tool_adapter: ToolAdapter | None = None
        self.tool_manager: ToolManager | None = None
        self.mcp_client: MCPClient | None = None
        self.tool_executor: ToolExecutor | None = None

        # the system prompt is a combination of the persona prompt and live2d expression prompt
        self.system_prompt: str = None

        # Store the generated MCP prompt string (if MCP enabled)
        self.mcp_prompt: str = ""

        self.history_uid: str = ""  # Add history_uid field
        
        self.send_text: Callable = None
        self.client_uid: str = None

    def __str__(self):
        return (
            f"ServiceContext:\n"
            f"  System Config: {'Loaded' if self.system_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.system_config.model_dump(), indent=6) if self.system_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"
            f"  ASR Engine: {type(self.asr_engine).__name__ if self.asr_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.asr_config.model_dump(), indent=6) if self.character_config.asr_config else 'None'}\n"
            f"  TTS Engine: {type(self.tts_engine).__name__ if self.tts_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.tts_config.model_dump(), indent=6) if self.character_config.tts_config else 'None'}\n"
            f"  LLM Engine: {type(self.agent_engine).__name__ if self.agent_engine else 'Not Loaded'}\n"
            f"    Agent Config: {json.dumps(self.character_config.agent_config.model_dump(), indent=6) if self.character_config.agent_config else 'None'}\n"
            f"  VAD Engine: {type(self.vad_engine).__name__ if self.vad_engine else 'Not Loaded'}\n"
            f"    Agent Config: {json.dumps(self.character_config.vad_config.model_dump(), indent=6) if self.character_config.vad_config else 'None'}\n"
            f"  System Prompt: {self.system_prompt or 'Not Set'}\n"
            f"  MCP Enabled: {'Yes' if self.mcp_client else 'No'}"
        )

    # ==== Initializers

    async def _init_mcp_components(self, use_mcpp, enabled_servers):
        """Initializes MCP components based on configuration, dynamically fetching tool info."""
        logger.debug(
            f"Initializing MCP components: use_mcpp={use_mcpp}, enabled_servers={enabled_servers}"
        )

        # 🔍 诊断：在创建新MCP Client前，先清理旧的
        if self.mcp_client:
            logger.warning("⚠️  检测到旧MCP Client未清理，先关闭...")
            logger.info(f"  🔍 旧Client活跃sessions: {len(self.mcp_client.active_sessions)}")
            try:
                await asyncio.wait_for(self.mcp_client.aclose(), timeout=3.0)
                logger.info("  ✅ 旧MCP Client已清理")
            except Exception as e:
                logger.error(f"  ❌ 清理旧MCP Client失败: {e}")

        # Reset MCP components first
        self.mcp_server_registery = None
        self.tool_manager = None
        self.mcp_client = None
        self.tool_executor = None
        self.json_detector = None
        self.mcp_prompt = ""

        if use_mcpp and enabled_servers:
            # 1. Initialize ServerRegistry
            self.mcp_server_registery = ServerRegistry()
            logger.info("ServerRegistry initialized or referenced.")

            # 2. Use ToolAdapter to get the MCP prompt and tools
            if not self.tool_adapter:
                logger.error("ToolAdapter not initialized before calling _init_mcp_components.")
                self.mcp_prompt = "[Error: ToolAdapter not initialized]"
                return # Exit if ToolAdapter is mandatory and not initialized

            # Add retry mechanism for MCP tool construction
            max_retries = 3
            retry_delay = 1  # seconds
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 Attempting MCP tool construction (attempt {attempt + 1}/{max_retries})...")
                    
                    (
                        mcp_prompt_string,
                        openai_tools,
                        claude_tools,
                    ) = await self.tool_adapter.get_tools(enabled_servers)
                    
                    # Get raw tools dict in same call to ensure consistency
                    _, raw_tools_dict = await self.tool_adapter.get_server_and_tool_info(
                        enabled_servers
                    )
                    
                    # Validate that we actually got tools
                    if not raw_tools_dict:
                        raise ValueError("No tools retrieved from MCP servers")
                    
                    # Store the generated prompt string
                    self.mcp_prompt = mcp_prompt_string
                    logger.info(
                        f"✅ Dynamically generated MCP prompt string (length: {len(self.mcp_prompt)})."
                    )
                    logger.info(
                        f"✅ Dynamically formatted tools - OpenAI: {len(openai_tools)}, Claude: {len(claude_tools)}."
                    )
                    logger.info(f"✅ Raw tools dict contains {len(raw_tools_dict)} tools.")

                    # 3. Initialize ToolManager with the fetched formatted tools
                    self.tool_manager = ToolManager(
                        formatted_tools_openai=openai_tools,
                        formatted_tools_claude=claude_tools,
                        initial_tools_dict=raw_tools_dict,
                    )
                    logger.info("✅ ToolManager initialized with dynamically fetched tools.")
                    
                    # Success - break out of retry loop
                    break

                except Exception as e:
                    logger.error(
                        f"❌ Failed during dynamic MCP tool construction (attempt {attempt + 1}/{max_retries}): {e}", 
                        exc_info=True if attempt == max_retries - 1 else False
                    )
                    
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Final failure
                        logger.error("❌ All MCP tool construction attempts failed")
                        self.tool_manager = None
                        self.mcp_prompt = "[Error constructing MCP tools/prompt after retries]"

            # 4. Initialize MCPClient
            if self.mcp_server_registery:
                self.mcp_client = MCPClient(self.mcp_server_registery, self.send_text, self.client_uid)
                logger.info("MCPClient initialized for this session.")
            else:
                logger.error(
                    "MCP enabled but ServerRegistry not available. MCPClient not created."
                )
                self.mcp_client = None  # Ensure it's None

            # 5. Initialize ToolExecutor
            if self.mcp_client and self.tool_manager:
                self.tool_executor = ToolExecutor(self.mcp_client, self.tool_manager)
                logger.info("ToolExecutor initialized for this session.")
            else:
                logger.warning(
                    "MCPClient or ToolManager not available. ToolExecutor not created."
                )
                self.tool_executor = None  # Ensure it's None

            logger.info("StreamJSONDetector initialized for this session.")

            # 6. Warm up MCP servers (optional best-effort): list tools to establish sessions
            try:
                if self.mcp_client and enabled_servers:
                    # Warm up commonly used servers
                    for server_name in enabled_servers:
                        try:
                            await self.mcp_client.list_tools(server_name)
                            logger.debug(f"MCP warm-up completed for server '{server_name}'.")
                        except Exception as warm_err:
                            logger.warning(f"MCP warm-up failed for '{server_name}': {warm_err}")
            except Exception as warm_outer_err:
                logger.warning(f"MCP warm-up step encountered an error: {warm_outer_err}")

        elif use_mcpp and not enabled_servers:
            logger.warning(
                "use_mcpp is True, but mcp_enabled_servers list is empty. MCP components not initialized."
            )
        else:
            logger.debug(
                "MCP components not initialized (use_mcpp is False or no enabled servers)."
            )

    async def close(self, skip_shared_cleanup: bool = False):
        """Clean up resources, especially the MCPClient.
        
        Args:
            skip_shared_cleanup: If True, skip cleaning shared components (agent, mcp_client).
                                 Used in single-user scenarios where components are reused.
        """
        logger.info("Closing ServiceContext resources...")
        
        # ✅ 取消所有后台任务
        if hasattr(self, '_background_tasks'):
            for task in self._background_tasks:
                if not task.done():
                    logger.info("  ⏹️  取消后台初始化任务")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._background_tasks.clear()
            logger.info("  ✅ 所有后台任务已清理")
        
        # ✅ 单用户优化：跳过共享组件的清理
        if skip_shared_cleanup:
            logger.info("  ♻️  跳过共享组件清理（单用户模式）")
            # 只清空引用，不关闭实际组件
            self.mcp_client = None
            self.agent_engine = None
            logger.info("ServiceContext closed (shared components preserved).")
            return
        
        # 🔍 诊断：MCP Client清理（仅在非共享模式）
        if self.mcp_client:
            logger.info(f"Closing MCPClient for context instance {id(self)}...")
            logger.info(f"  🔍 活跃MCP sessions: {len(self.mcp_client.active_sessions)}")
            logger.info(f"  🔍 Sessions: {list(self.mcp_client.active_sessions.keys())}")
            try:
                await asyncio.wait_for(self.mcp_client.aclose(), timeout=5.0)
                logger.info("  ✅ MCPClient已关闭")
            except asyncio.TimeoutError:
                logger.error("  ❌ MCPClient关闭超时！可能有服务器进程残留")
            except Exception as e:
                logger.error(f"  ❌ MCPClient关闭失败: {e}")
            finally:
                self.mcp_client = None
        else:
            logger.debug("  ⏭️  无MCP Client需要关闭")
            
        if self.agent_engine and hasattr(self.agent_engine, "close"):
            await self.agent_engine.close()  # Ensure agent resources are also closed
        logger.info("ServiceContext closed.")

    async def load_cache(
        self,
        config: Config,
        system_config: SystemConfig,
        character_config: CharacterConfig,
        live2d_model: Live2dModel,
        asr_engine: ASRInterface,
        tts_engine: TTSInterface,
        vad_engine: VADInterface,
        agent_engine: AgentInterface,
        mcp_server_registery: ServerRegistry | None = None,
        tool_adapter: ToolAdapter | None = None,
        send_text: Callable = None,
        client_uid: str = None,
        # ✅ 单用户优化：允许传入已有的MCP组件
        mcp_client: MCPClient | None = None,
        tool_manager: ToolManager | None = None,
        tool_executor: ToolExecutor | None = None,
        mcp_prompt: str = "",
    ) -> None:
        """
        Load the ServiceContext with the reference of the provided instances.
        Pass by reference so no reinitialization will be done.
        """
        if not character_config:
            raise ValueError("character_config cannot be None")
        if not system_config:
            raise ValueError("system_config cannot be None")

        self.config = config
        self.system_config = system_config
        self.character_config = character_config
        self.live2d_model = live2d_model
        self.asr_engine = asr_engine
        self.tts_engine = tts_engine
        self.vad_engine = vad_engine
        self.agent_engine = agent_engine
        # Load potentially shared components by reference
        self.mcp_server_registery = mcp_server_registery
        self.tool_adapter = tool_adapter
        self.send_text = send_text
        self.client_uid = client_uid

        # ✅ 单用户优化：复用MCP组件，避免重复创建导致agent引用失效
        if mcp_client and tool_manager and tool_executor:
            logger.info(f"♻️  复用现有MCP组件 for client {client_uid}")
            self.mcp_client = mcp_client
            self.tool_manager = tool_manager
            self.tool_executor = tool_executor
            self.mcp_prompt = mcp_prompt
            # 只更新client_uid（用于WebSocket通信）
            if hasattr(self.mcp_client, '_client_uid'):
                self.mcp_client._client_uid = client_uid
        else:
            # 首次连接时才初始化MCP组件
            logger.info(f"🔧 初始化新的MCP组件 for client {client_uid}")
            await self._init_mcp_components(
                self.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp,
                self.character_config.agent_config.agent_settings.basic_memory_agent.mcp_enabled_servers
            )

        logger.debug(f"Loaded service context with cache: {character_config}")

    async def load_from_config(self, config: Config) -> None:
        """
        Load the ServiceContext with the config.
        Reinitialize the instances if the config is different.

        Parameters:
        - config (Dict): The configuration dictionary.
        """
        if not self.config:
            self.config = config

        if not self.system_config:
            self.system_config = config.system_config

        if not self.character_config:
            self.character_config = config.character_config

        # update all sub-configs

        # Offload heavy synchronous initializers to thread to keep event loop responsive
        # init live2d from character config
        await asyncio.to_thread(self.init_live2d, config.character_config.live2d_model_name)

        # init asr from character config
        await asyncio.to_thread(self.init_asr, config.character_config.asr_config)

        # init tts from character config
        await asyncio.to_thread(self.init_tts, config.character_config.tts_config)

        # init vad from character config
        await asyncio.to_thread(self.init_vad, config.character_config.vad_config)

        # Initialize shared ToolAdapter if it doesn't exist yet
        if not self.tool_adapter and config.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp:
            if not self.mcp_server_registery:
                logger.info("Initializing shared ServerRegistry within load_from_config.")
                self.mcp_server_registery = ServerRegistry()
            logger.info("Initializing shared ToolAdapter within load_from_config.")
            self.tool_adapter = ToolAdapter(server_registery=self.mcp_server_registery)

        # Initialize MCP Components before initializing Agent (best-effort, do not fail switching)
        try:
            await self._init_mcp_components(
                config.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp,
                config.character_config.agent_config.agent_settings.basic_memory_agent.mcp_enabled_servers,
            )
        except Exception as e:
            logger.warning(f"MCP initialization failed during config load, continuing without MCP: {e}")

        # init agent from character config
        await self.init_agent(
            config.character_config.agent_config,
            config.character_config.persona_prompt,
        )

        # store typed config references
        self.config = config
        self.system_config = config.system_config or self.system_config
        self.character_config = config.character_config

    def init_live2d(self, live2d_model_name: str) -> None:
        logger.info(f"Initializing Live2D: {live2d_model_name}")
        try:
            self.live2d_model = Live2dModel(live2d_model_name)
            self.character_config.live2d_model_name = live2d_model_name
        except Exception as e:
            logger.critical(f"Error initializing Live2D: {e}")
            logger.critical("Try to proceed without Live2D...")

    def init_asr(self, asr_config: ASRConfig) -> None:
        if not self.asr_engine or (self.character_config.asr_config != asr_config):
            logger.info(f"Initializing ASR: {asr_config.asr_model}")
            try:
                self.asr_engine = ASRFactory.get_asr_system(
                    asr_config.asr_model,
                    **getattr(asr_config, asr_config.asr_model).model_dump(),
                )
                # saving config should be done after successful initialization
                self.character_config.asr_config = asr_config
                logger.info("ASR initialized successfully.")
            except Exception as e:
                logger.critical(f"Error initializing ASR: {e}")
                logger.critical("Proceeding without ASR. Speech-to-text features will be disabled.")
                self.asr_engine = None
                # Do not update stored config to avoid persisting a broken state
        else:
            logger.info("ASR already initialized with the same config.")

    def init_tts(self, tts_config: TTSConfig) -> None:
        if not self.tts_engine or (self.character_config.tts_config != tts_config):
            logger.info(f"Initializing TTS: {tts_config.tts_model}")
            self.tts_engine = TTSFactory.get_tts_engine(
                tts_config.tts_model,
                **getattr(tts_config, tts_config.tts_model.lower()).model_dump(),
            )
            # saving config should be done after successful initialization
            self.character_config.tts_config = tts_config
        else:
            logger.info("TTS already initialized with the same config.")

    def init_vad(self, vad_config: VADConfig) -> None:
        if vad_config.vad_model is None:
            logger.info("VAD is disabled.")
            self.vad_engine = None
            return
            
        if not self.vad_engine or (self.character_config.vad_config != vad_config):
            logger.info(f"Initializing VAD: {vad_config.vad_model}")
            self.vad_engine = VADFactory.get_vad_engine(
                vad_config.vad_model,
                **getattr(vad_config, vad_config.vad_model.lower()).model_dump(),
            )
            # saving config should be done after successful initialization
            self.character_config.vad_config = vad_config
        else:
            logger.info("VAD already initialized with the same config.")

    async def init_agent(self, agent_config: AgentConfig, persona_prompt: str) -> None:
        """Initialize or update the LLM engine based on agent configuration."""
        logger.info(f"Initializing Agent: {agent_config.conversation_agent_choice}")

        if (
            self.agent_engine is not None
            and agent_config == self.character_config.agent_config
            and persona_prompt == self.character_config.persona_prompt
        ):
            logger.debug("Agent already initialized with the same config.")
            return

        system_prompt = await self.construct_system_prompt(persona_prompt)

        # Pass avatar to agent factory
        avatar = self.character_config.avatar or ""  # Get avatar from config

        try:
            # Offload potentially heavy agent construction to a worker thread
            self.agent_engine = await asyncio.to_thread(
                AgentFactory.create_agent,
                conversation_agent_choice=agent_config.conversation_agent_choice,
                agent_settings=agent_config.agent_settings.model_dump(),
                llm_configs=agent_config.llm_config.model_dump(),
                system_prompt=system_prompt,
                live2d_model=self.live2d_model,
                tts_preprocessor_config=self.character_config.tts_preprocessor_config,
                character_avatar=avatar,
                system_config=self.system_config.model_dump(),
                tool_manager=self.tool_manager,
                tool_executor=self.tool_executor,
                mcp_prompt_string=self.mcp_prompt,
            )

            logger.debug(f"Agent choice: {agent_config.conversation_agent_choice}")
            logger.debug(f"System prompt: {system_prompt}")

            # Save the current configuration
            self.character_config.agent_config = agent_config
            self.system_prompt = system_prompt

        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise



    # ==== utils

    async def construct_system_prompt(self, persona_prompt: str) -> str:
        """
        Append tool prompts to persona prompt.

        Parameters:
        - persona_prompt (str): The persona prompt.

        Returns:
        - str: The system prompt with all tool prompts appended.
        """
        logger.debug(f"constructing persona_prompt: '''{persona_prompt}'''")

        for prompt_name, prompt_file in self.system_config.tool_prompts.items():
            if (
                prompt_name == "group_conversation_prompt"
                or prompt_name == "proactive_speak_prompt"
            ):
                continue

            prompt_content = prompt_loader.load_util(prompt_file)

            if prompt_name == "live2d_expression_prompt":
                prompt_content = prompt_content.replace(
                    "[<insert_emomap_keys>]", self.live2d_model.emo_str
                )

            if prompt_name == "mcp_prompt":
                continue

            persona_prompt += prompt_content

        logger.debug("\n === System Prompt ===")
        logger.debug(persona_prompt)

        return persona_prompt

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """
        Handle the configuration switch request.
        Change the configuration to a new config and notify the client.

        Parameters:
        - websocket (WebSocket): The WebSocket connection.
        - config_file_name (str): The name of the configuration file.
        """
        try:
            new_character_config_data = None

            if config_file_name == "conf.yaml":
                # Load base config
                new_character_config_data = read_yaml("conf.yaml").get(
                    "character_config"
                )
            else:
                # Load alternative config and merge with base config
                characters_dir = self.system_config.config_alts_dir
                file_path = os.path.normpath(
                    os.path.join(characters_dir, config_file_name)
                )
                if not file_path.startswith(characters_dir):
                    raise ValueError("Invalid configuration file path")

                alt_config_data = read_yaml(file_path).get("character_config")

                # Start with original config data and perform a deep merge
                new_character_config_data = deep_merge(
                    self.config.character_config.model_dump(), alt_config_data
                )

            if new_character_config_data:
                new_config_dict = {
                    "system_config": self.system_config.model_dump(),
                    "character_config": new_character_config_data,
                }
                new_config = validate_config(new_config_dict)

                # Apply minimal config immediately: Live2D first, to avoid long waits
                self.config = new_config
                self.system_config = new_config.system_config or self.system_config
                self.character_config = new_config.character_config

                # Initialize Live2D on worker thread to keep loop responsive
                await asyncio.to_thread(self.init_live2d, self.character_config.live2d_model_name)

                # Immediately notify frontend with new model info
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "set-model-and-conf",
                            "model_info": self.live2d_model.model_info,
                            "conf_name": self.character_config.conf_name,
                            "conf_uid": self.character_config.conf_uid,
                        }
                    )
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "config-switched",
                            "message": f"Switched to config: {config_file_name}",
                            "conf_name": self.character_config.conf_name,
                            "conf_uid": self.character_config.conf_uid,
                        }
                    )
                )

                logger.info(f"Configuration switched to {config_file_name}")

                # Continue heavy initializations in background (ASR/TTS/VAD/MCP/Agent)
                async def _finish_heavy_init():
                    try:
                        # ASR/TTS/VAD
                        await asyncio.to_thread(self.init_asr, self.character_config.asr_config)
                        await asyncio.to_thread(self.init_tts, self.character_config.tts_config)
                        await asyncio.to_thread(self.init_vad, self.character_config.vad_config)
                        # MCP (best-effort)
                        try:
                            await self._init_mcp_components(
                                self.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp,
                                self.character_config.agent_config.agent_settings.basic_memory_agent.mcp_enabled_servers,
                            )
                        except Exception as mcp_err:
                            logger.warning(f"MCP init deferred failed: {mcp_err}")
                        # Agent init
                        await self.init_agent(
                            self.character_config.agent_config,
                            self.character_config.persona_prompt,
                        )
                    except Exception as init_err:
                        logger.warning(f"Deferred init after switch encountered error: {init_err}")

                # ✅ 取消旧的初始化任务（如果有）
                for task in self._background_tasks:
                    if not task.done():
                        logger.info("⏹️  取消旧的初始化任务")
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                self._background_tasks.clear()
                
                # ✅ 创建新任务并追踪
                task = asyncio.create_task(_finish_heavy_init())
                self._background_tasks.append(task)
                logger.info("🔧 启动后台初始化任务")
            else:
                raise ValueError(
                    f"Failed to load configuration from {config_file_name}"
                )

        except Exception as e:
            logger.error(f"Error switching configuration: {e}")
            logger.debug(self)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error switching configuration: {str(e)}",
                        "conf_name": self.character_config.conf_name if self.character_config else None,
                        "conf_uid": self.character_config.conf_uid if self.character_config else None,
                    }
                )
            )
            raise e


def deep_merge(dict1, dict2):
    """
    Recursively merges dict2 into dict1, prioritizing values from dict2.
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
