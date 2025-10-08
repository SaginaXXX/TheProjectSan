from typing import Dict, List, Optional, Callable, TypedDict
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from enum import Enum
import numpy as np
import datetime
from loguru import logger

from .service_context import ServiceContext
from .message_handler import message_handler
from .chat_history_manager import (
    create_new_history,
    get_history,
    delete_history,
    get_history_list,
)
from .config_manager.utils import scan_config_alts_directory, scan_bg_directory
from .conversations.conversation_handler import (
    handle_conversation_trigger,
    handle_individual_interrupt,
)
from .conversations.wake_word_manager import wake_word_manager


# 消息类型枚举
class MessageType(Enum):
    """Enum for WebSocket message types"""

    HISTORY = [
        "fetch-history-list",
        "fetch-and-set-history",
        "create-new-history",
        "delete-history",
    ]
    CONVERSATION = ["mic-audio-end", "text-input", "ai-speak-signal"]
    CONFIG = ["fetch-configs", "switch-config"]
    CONTROL = ["interrupt-signal"]
    DATA = ["mic-audio-data"]

# 定义WebSocket消息类型
class WSMessage(TypedDict, total=False):
    """Type definition for WebSocket messages"""

    type: str
    action: Optional[str]
    text: Optional[str]
    audio: Optional[List[float]]
    images: Optional[List[str]]
    history_uid: Optional[str]
    file: Optional[str]
    display_text: Optional[dict]

# 定义WebSocket处理类
class WebSocketHandler:
    """Handles WebSocket connections and message routing"""

    def __init__(self, default_context_cache: ServiceContext):
        """Initialize the WebSocket handler with default context"""
        self.client_connections: Dict[str, WebSocket] = {}
        self.client_contexts: Dict[str, ServiceContext] = {}
        self.current_conversation_tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.default_context_cache = default_context_cache
        self.received_data_buffers: Dict[str, np.ndarray] = {}
        self._last_heartbeat: Dict[str, float] = {}
        self._sweeper_task: Optional[asyncio.Task] = None

        # Message handlers mapping
        self._message_handlers = self._init_message_handlers()

    def _init_message_handlers(self) -> Dict[str, Callable]:
        """Initialize message type to handler mapping"""
        return {
            "fetch-history-list": self._handle_history_list_request,
            "fetch-and-set-history": self._handle_fetch_history,
            "create-new-history": self._handle_create_history,
            "delete-history": self._handle_delete_history,
            "interrupt-signal": self._handle_interrupt,
            "mic-audio-data": self._handle_audio_data,
            "mic-audio-end": self._handle_conversation_trigger,
            "raw-audio-data": self._handle_raw_audio_data,
            "text-input": self._handle_conversation_trigger,
            "ai-speak-signal": self._handle_conversation_trigger,
            "fetch-configs": self._handle_fetch_configs,
            "switch-config": self._handle_config_switch,
            "fetch-backgrounds": self._handle_fetch_backgrounds,
            "request-init-config": self._handle_init_config_request,
            "heartbeat": self._handle_heartbeat,
            "mcp-tool-call": self._handle_mcp_tool_call,
            "adaptive-vad-control": self._handle_adaptive_vad_control,
            # Frontend playback start notification - ignore to avoid noise
            "audio-play-start": self._ignore_message,
        }

    async def _ignore_message(self, *_args, **_kwargs) -> None:
        """No-op handler for benign frontend notifications."""
        return None

    async def handle_new_connection(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle new WebSocket connection setup

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client

        Raises:
            Exception: If initialization fails
        """
        try:
            session_service_context = await self._init_service_context(websocket.send_text, client_uid)

            await self._store_client_data(
                websocket, client_uid, session_service_context
            )

            # Ensure sweeper starts when we have an event loop
            if not self._sweeper_task or self._sweeper_task.done():
                self._sweeper_task = asyncio.create_task(self._sweep_stale())

            await self._send_initial_messages(
                websocket, client_uid, session_service_context
            )

            logger.info(f"Connection established for client {client_uid}. Active: {len(self.client_connections)}")

        except Exception as e:
            logger.error(
                f"Failed to initialize connection for client {client_uid}: {e}"
            )
            await self._cleanup_failed_connection(client_uid)
            raise

    async def _store_client_data(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Store client data and initialize group status"""
        self.client_connections[client_uid] = websocket
        self.client_contexts[client_uid] = session_service_context
        self.received_data_buffers[client_uid] = np.array([])


    async def _send_initial_messages(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Send initial connection messages to the client"""
        await websocket.send_text(
            json.dumps({"type": "full-text", "text": "Connection established"})
        )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": session_service_context.live2d_model.model_info,
                    "conf_name": session_service_context.character_config.conf_name,
                    "conf_uid": session_service_context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

        # Start microphone
        await websocket.send_text(json.dumps({"type": "control", "text": "start-mic"}))

    async def _init_service_context(self, send_text: Callable, client_uid: str) -> ServiceContext:
        """Initialize service context for a new session by cloning the default context"""
        session_service_context = ServiceContext()
        await session_service_context.load_cache(
            config=self.default_context_cache.config.model_copy(deep=True),
            system_config=self.default_context_cache.system_config.model_copy(
                deep=True
            ),
            character_config=self.default_context_cache.character_config.model_copy(
                deep=True
            ),
            live2d_model=self.default_context_cache.live2d_model,
            asr_engine=self.default_context_cache.asr_engine,
            tts_engine=self.default_context_cache.tts_engine,
            vad_engine=self.default_context_cache.vad_engine,
            agent_engine=self.default_context_cache.agent_engine,
            mcp_server_registery=self.default_context_cache.mcp_server_registery,
            tool_adapter=self.default_context_cache.tool_adapter,
            send_text=send_text,
            client_uid=client_uid,
        )
        return session_service_context

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle ongoing WebSocket communication

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client
        """
        try:
            while True:
                try:
                    data = await websocket.receive_json()
                    message_handler.handle_message(client_uid, data)
                    await self._route_message(websocket, client_uid, data)
                except WebSocketDisconnect:
                    raise
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                    continue

        except WebSocketDisconnect:
            logger.info(f"Client {client_uid} disconnected")
            raise
        except Exception as e:
            logger.error(f"Fatal error in WebSocket communication: {e}")
            raise

    async def _route_message(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """
        Route incoming message to appropriate handler

        Args:
            websocket: The WebSocket connection
            client_uid: Client identifier
            data: Message data
        """
        msg_type = data.get("type")
        if not msg_type:
            logger.warning("Message received without type")
            return

        handler = self._message_handlers.get(msg_type)
        if handler:
            await handler(websocket, client_uid, data)
        else:
            if msg_type != "frontend-playback-complete":
                logger.warning(f"Unknown message type: {msg_type}")

    async def handle_disconnect(self, client_uid: str) -> None:
        """Handle client disconnection - 彻底清理所有资源防止泄漏"""
        logger.info(f"🔌 开始清理客户端 {client_uid} 的资源...")
        
        # 1. 先取消所有进行中的任务，避免任务继续使用即将被清理的资源
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                logger.info(f"  ⏹️  取消进行中的对话任务 for {client_uid}")
                task.cancel()
                try:
                    # 等待任务完全取消（最多等待2秒）
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception as e:
                    logger.warning(f"  ⚠️  任务取消时出错: {e}")
            self.current_conversation_tasks.pop(client_uid, None)
        
        # 2. 清理ServiceContext（包含 MCP Client 和 Agent Engine）
        context = self.client_contexts.get(client_uid)
        if context:
            logger.info(f"  🗑️  清理 ServiceContext for {client_uid}")
            try:
                await context.close()
            except Exception as e:
                logger.error(f"  ❌ ServiceContext清理失败 for {client_uid}: {e}")
        
        # 3. 清理所有客户端相关的状态字典
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self._last_heartbeat.pop(client_uid, None)
        
        # 4. 清理外部管理器中的状态
        try:
            message_handler.cleanup_client(client_uid)
            logger.info(f"  ✅ 清理 message_handler for {client_uid}")
        except Exception as e:
            logger.warning(f"  ⚠️  message_handler清理失败: {e}")
        
        try:
            wake_word_manager.cleanup_client(client_uid)
            logger.info(f"  ✅ 清理 wake_word_manager for {client_uid}")
        except Exception as e:
            logger.warning(f"  ⚠️  wake_word_manager清理失败: {e}")

        logger.info(f"✅ 客户端 {client_uid} 资源清理完成. 剩余活跃连接: {len(self.client_connections)}")
        
        # 5. 如果没有活跃连接了，做一次全局清理检查
        if len(self.client_connections) == 0:
            logger.info("📊 所有客户端已断开，检查是否有残留资源...")
            
            # 清理可能泄漏的数据
            if self.current_conversation_tasks:
                logger.warning(f"⚠️  发现残留任务: {list(self.current_conversation_tasks.keys())}")
                self.current_conversation_tasks.clear()
            if self.received_data_buffers:
                logger.warning(f"⚠️  发现残留音频缓冲: {list(self.received_data_buffers.keys())}")
                self.received_data_buffers.clear()
            if self._last_heartbeat:
                logger.warning(f"⚠️  发现残留心跳记录: {list(self._last_heartbeat.keys())}")
                self._last_heartbeat.clear()
            
            # ✅ 添加全局任务统计（帮助诊断性能问题）
            all_tasks = asyncio.all_tasks()
            active_tasks = [t for t in all_tasks if not t.done()]
            logger.info(f"📊 全局任务统计: 总任务={len(all_tasks)}, 活跃={len(active_tasks)}, 已完成={len(all_tasks)-len(active_tasks)}")
            
            if len(active_tasks) > 20:
                logger.warning(f"⚠️  活跃任务数量较多: {len(active_tasks)}")
                logger.warning("前 5 个活跃任务:")
                for task in list(active_tasks)[:5]:
                    logger.warning(f"  - {task.get_name() or 'unnamed'}")

    async def _handle_interrupt(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle conversation interruption"""
        heard_response = data.get("text", "")
        context = self.client_contexts[client_uid]
        await handle_individual_interrupt(
            client_uid=client_uid,
            current_conversation_tasks=self.current_conversation_tasks,
            context=context,
            heard_response=heard_response,
        )

    async def _handle_history_list_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for chat history list"""
        context = self.client_contexts[client_uid]
        # 如果禁用了历史，直接返回空列表
        if not getattr(context.system_config, "enable_history", True):
            await websocket.send_text(
                json.dumps({"type": "history-list", "histories": []})
            )
            return
        histories = get_history_list(context.character_config.conf_uid)
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )

    async def _handle_fetch_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle fetching and setting specific chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        if not getattr(context.system_config, "enable_history", True):
            # 历史关闭：不加载、不设置、直接返回空
            context.history_uid = None
            await websocket.send_text(
                json.dumps({"type": "history-data", "messages": []})
            )
            return

        # Update history_uid in service context
        context.history_uid = history_uid
        context.agent_engine.set_memory_from_history(
            conf_uid=context.character_config.conf_uid,
            history_uid=history_uid,
        )

        messages = [
            msg
            for msg in get_history(
                context.character_config.conf_uid,
                history_uid,
            )
            if msg["role"] != "system"
        ]
        await websocket.send_text(
            json.dumps({"type": "history-data", "messages": messages})
        )

    async def _handle_create_history(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle creation of new chat history"""
        context = self.client_contexts[client_uid]
        # 禁用历史：直接返回不创建
        if not getattr(context.system_config, "enable_history", True):
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "new-history-created",
                        "history_uid": "",
                    }
                )
            )
            return
        history_uid = create_new_history(context.character_config.conf_uid)
        if history_uid:
            context.history_uid = history_uid
            context.agent_engine.set_memory_from_history(
                conf_uid=context.character_config.conf_uid,
                history_uid=history_uid,
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "new-history-created",
                        "history_uid": history_uid,
                    }
                )
            )

    async def _handle_delete_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle deletion of chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        if not getattr(context.system_config, "enable_history", True):
            # 历史关闭时，认为删除成功（幂等）
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "history-deleted",
                        "success": True,
                        "history_uid": history_uid,
                    }
                )
            )
            if history_uid == context.history_uid:
                context.history_uid = None
            return
        success = delete_history(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "history-deleted",
                    "success": success,
                    "history_uid": history_uid,
                }
            )
        )
        if history_uid == context.history_uid:
            context.history_uid = None

    async def _handle_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming audio data"""
        audio_data = data.get("audio", [])
        if audio_data:
            self.received_data_buffers[client_uid] = np.append(
                self.received_data_buffers[client_uid],
                np.array(audio_data, dtype=np.float32),
            )

    async def _handle_raw_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming raw audio data for VAD processing"""
        context = self.client_contexts[client_uid]
        chunk = data.get("audio", [])
        if chunk:
            for audio_bytes in context.vad_engine.detect_speech(chunk):
                if audio_bytes == b"<|PAUSE|>":
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "interrupt"})
                    )
                elif audio_bytes == b"<|RESUME|>":
                    pass
                elif len(audio_bytes) > 1024:
                    # ⚠️ 这里可能是重复触发的源头!
                    # raw-audio-data 的VAD检测已经触发了 mic-audio-end
                    # 但前端的VAD也会发送 mic-audio-end
                    logger.debug(f"🎤 Raw audio VAD detected speech for {client_uid}, buffering...")
                    self.received_data_buffers[client_uid] = np.append(
                        self.received_data_buffers[client_uid],
                        np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32),
                    )
                    # ✅ 修复：不要在这里发送 mic-audio-end，让前端VAD控制
                    # await websocket.send_text(
                    #     json.dumps({"type": "control", "text": "mic-audio-end"})
                    # )

    async def _handle_conversation_trigger(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle triggers that start a conversation"""
        await handle_conversation_trigger(
            msg_type=data.get("type", ""),
            data=data,
            client_uid=client_uid,
            context=self.client_contexts[client_uid],
            websocket=websocket,
            client_contexts=self.client_contexts,
            client_connections=self.client_connections,
            received_data_buffers=self.received_data_buffers,
            current_conversation_tasks=self.current_conversation_tasks,
        )

    async def _handle_fetch_configs(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available configurations"""
        context = self.client_contexts[client_uid]
        config_files = scan_config_alts_directory(context.system_config.config_alts_dir)
        await websocket.send_text(
            json.dumps({"type": "config-files", "configs": config_files})
        )

    async def _handle_config_switch(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle switching to a different configuration"""
        config_file_name = data.get("file")
        if config_file_name:
            context = self.client_contexts[client_uid]
            await context.handle_config_switch(websocket, config_file_name)
            # Keep default context in sync so new connections use latest selection
            try:
                if self.default_context_cache and context and context.config:
                    await self.default_context_cache.load_from_config(context.config)
            except Exception as e:
                # Best-effort; do not break current session if updating default cache fails
                logger.warning(f"Failed to sync default context after config switch: {e}")

    async def _handle_fetch_backgrounds(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available background images"""
        bg_files = scan_bg_directory()
        await websocket.send_text(
            json.dumps({"type": "background-files", "files": bg_files})
        )

    

    async def _handle_init_config_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for initialization configuration"""
        context = self.client_contexts.get(client_uid)
        if not context:
            context = self.default_context_cache

        # Check if live2d_model is properly initialized
        if not context.live2d_model:
            logger.error(f"Live2D model not initialized for client {client_uid}")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "Live2D model not initialized",
                    }
                )
            )
            return

        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "set-model-and-conf",
                        "model_info": context.live2d_model.model_info,
                        "conf_name": context.character_config.conf_name,
                        "conf_uid": context.character_config.conf_uid,
                        "client_uid": client_uid,
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error sending model configuration: {e}")
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error", 
                        "message": f"Error loading model configuration: {e}",
                    }
                )
            )

    async def _handle_heartbeat(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle heartbeat messages from clients"""
        try:
            self._last_heartbeat[client_uid] = asyncio.get_event_loop().time()
            await websocket.send_json({"type": "heartbeat-ack"})
        except Exception as e:
            logger.error(f"Error sending heartbeat acknowledgment: {e}")

    async def _sweep_stale(self, ttl: float = 60.0):
        """Periodically disconnect clients that stopped heartbeating."""
        while True:
            try:
                await asyncio.sleep(30)
                now = asyncio.get_event_loop().time()
                stale = [uid for uid, ts in list(self._last_heartbeat.items()) if now - ts > ttl]
                for uid in stale:
                    try:
                        await self.handle_disconnect(uid)
                    except Exception as e:
                        logger.warning(f"Failed to drop stale client {uid}: {e}")
                    finally:
                        self._last_heartbeat.pop(uid, None)
            except Exception as e:
                logger.warning(f"Sweeper loop error: {e}")

    async def _handle_mcp_tool_call(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle MCP tool calls from frontend"""
        try:
            tool_name = data.get("tool_name")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                await websocket.send_json({
                    "type": "mcp-tool-response",
                    "tool_name": None,
                    "error": "Missing tool_name"
                })
                return
            
            logger.info(f"🔧 处理MCP工具调用: {tool_name} with args: {arguments}")
            
            # 获取客户端的服务上下文
            context = self.client_contexts.get(client_uid)
            if not context:
                await websocket.send_json({
                    "type": "mcp-tool-response", 
                    "tool_name": tool_name,
                    "error": "No service context available"
                })
                return
            
            # 调用MCP工具
            if hasattr(context, 'tool_executor') and context.tool_executor:
                try:
                    # 创建工具调用参数 - 包装为列表，因为execute_tools期望列表
                    tool_calls = [{
                        "name": tool_name,
                        "args": arguments,
                        "id": f"ws_{tool_name}_{datetime.datetime.now().timestamp()}"
                    }]
                    
                    # 执行工具调用 - 使用正确的方法名和参数
                    tool_executor_iterator = context.tool_executor.execute_tools(
                        tool_calls=tool_calls,
                        caller_mode="Prompt"  # 使用Prompt模式
                    )
                    
                    # 收集结果
                    final_results = None
                    async for update in tool_executor_iterator:
                        if update.get("type") == "final_tool_results":
                            final_results = update.get("results", [])
                            break
                    
                    logger.info(f"✅ MCP工具调用成功: {tool_name}")
                    
                    # 发送成功响应
                    await websocket.send_json({
                        "type": "mcp-tool-response",
                        "tool_name": tool_name,
                        "result": final_results
                    })
                    
                except Exception as tool_error:
                    logger.error(f"❌ MCP工具调用失败: {tool_name} - {tool_error}")
                    await websocket.send_json({
                        "type": "mcp-tool-response",
                        "tool_name": tool_name,
                        "error": f"Tool execution failed: {str(tool_error)}"
                    })
            else:
                await websocket.send_json({
                    "type": "mcp-tool-response",
                    "tool_name": tool_name,
                    "error": "MCP tool executor not available"
                })
                
        except Exception as e:
            logger.error(f"❌ 处理MCP工具调用时发生错误: {e}")
            await websocket.send_json({
                "type": "mcp-tool-response",
                "tool_name": data.get("tool_name"),
                "error": f"Handler error: {str(e)}"
            })

    async def _handle_adaptive_vad_control(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle adaptive VAD control messages for advertisement audio"""
        try:
            from .vad.adaptive_vad import get_adaptive_vad, set_advertisement_playing
            
            action = data.get("action")
            volume = data.get("volume", 0.5)
            
            if action == "start":
                # 开始播放广告，启用自适应VAD
                set_advertisement_playing(True, volume)
                logger.info(f"🎵 启用自适应VAD - 客户端: {client_uid}, 音量: {volume}")
                
            elif action == "adjust":
                # 调整VAD参数，根据广告音量
                set_advertisement_playing(True, volume)
                logger.debug(f"🔧 调整VAD阈值 - 客户端: {client_uid}, 音量: {volume}")
                
            elif action == "reset":
                # 重置VAD到正常状态
                set_advertisement_playing(False, 0.0)
                logger.debug(f"🔄 重置VAD阈值 - 客户端: {client_uid}")
                
            elif action == "stop":
                # 停止广告，恢复正常VAD
                set_advertisement_playing(False, 0.0)
                logger.info(f"🔇 停用自适应VAD - 客户端: {client_uid}")
                
            else:
                logger.warning(f"⚠️ 未知的VAD控制动作: {action}")
                await websocket.send_json({
                    "type": "adaptive-vad-response",
                    "error": f"Unknown action: {action}"
                })
                return
            
            # 发送成功响应
            await websocket.send_json({
                "type": "adaptive-vad-response",
                "action": action,
                "success": True,
                "message": f"VAD control '{action}' applied successfully"
            })
            
        except Exception as e:
            logger.error(f"❌ 处理自适应VAD控制时发生错误: {e}")
            await websocket.send_json({
                "type": "adaptive-vad-response",
                "error": f"VAD control error: {str(e)}"
            })
