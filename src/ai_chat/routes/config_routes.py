"""
Config Routes
=============
This module contains configuration and settings management related routes.
"""

import os
import json
import yaml
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Form, Response
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_config_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register configuration and settings management routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
    @router.get("/api/debug/paths")
    async def debug_paths():
        """调试API：检查服务器工作目录和文件路径"""
        cwd = os.getcwd()
        ads_exists = Path("ads").exists()
        ads_client_exists = Path("ads/client_001").exists()
        config_dir_exists = Path(os.getenv('CONFIG_ALTS_DIR', 'config_alts')).exists()
        
        ads_files = []
        if ads_client_exists:
            ads_files = [f.name for f in Path("ads/client_001").iterdir() if f.is_file()]
        
        return {
            "cwd": cwd,
            "ads_exists": ads_exists,
            "ads_client_001_exists": ads_client_exists,
            "ads_client_001_files": ads_files,
            "config_dir": os.getenv('CONFIG_ALTS_DIR', 'config_alts'),
            "config_dir_exists": config_dir_exists
        }
    
    @router.get("/api/config-files")
    async def get_config_files():
        """
        获取配置文件列表
        
        Returns:
            配置文件列表
        """
        try:
            # ✅ 从default_context_cache获取正确的配置目录
            config_dir = default_context_cache.config.system_config.config_alts_dir
            if not os.path.exists(config_dir):
                return {
                    "success": True,
                    "configs": []
                }
            
            configs = []
            for filename in os.listdir(config_dir):
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    try:
                        # 读取配置文件获取名称
                        config_path = os.path.join(config_dir, filename)
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f)
                        
                        # 获取角色名称
                        character_name = "未知角色"
                        if config_data and 'character_config' in config_data:
                            character_config = config_data['character_config']
                            if isinstance(character_config, dict) and 'conf_name' in character_config:
                                character_name = character_config['conf_name']
                        
                        configs.append({
                            "name": character_name,
                            "filename": filename
                        })
                    except Exception as e:
                        logger.warning(f"读取配置文件 {filename} 失败: {e}")
                        configs.append({
                            "name": filename.replace('.yaml', '').replace('.yml', ''),
                            "filename": filename
                        })
            
            return {
                "success": True,
                "configs": configs
            }
            
        except Exception as e:
            logger.error(f"获取配置文件列表失败: {e}")
            return Response(
                content=json.dumps({"error": f"获取配置文件列表失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

    @router.get("/api/settings/load")
    async def load_settings(client: Optional[str] = None):
        """
        加载当前设置接口
        
        Args:
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            当前设置数据
        """
        try:
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            # 从default_context_cache获取当前设置
            settings = {}
            
            if hasattr(default_context_cache, 'character_config') and default_context_cache.character_config:
                char_config = default_context_cache.character_config
                
                # 一般设置
                settings['language'] = 'zh'  # 默认语言
                settings['use_camera_background'] = False  # 默认不使用摄像头背景
                settings['show_subtitle'] = True  # 默认显示字幕
                
                # Live2D设置
                settings['pointer_interactive'] = getattr(char_config, 'live2d_pointer_interactive', True)
                settings['scroll_to_resize'] = getattr(char_config, 'live2d_scroll_to_resize', True)
                
                # Agent设置
                if hasattr(char_config, 'agent_config') and char_config.agent_config:
                    agent_config = char_config.agent_config
                    settings['allow_proactive_speak'] = getattr(agent_config, 'allow_proactive_speak', True)
                    settings['idle_seconds_to_speak'] = getattr(agent_config, 'idle_seconds_to_speak', 5.0)
                    settings['allow_button_trigger'] = getattr(agent_config, 'allow_button_trigger', True)
                
                # ASR设置
                if hasattr(char_config, 'asr_config') and char_config.asr_config:
                    asr_config = char_config.asr_config
                    settings['auto_stop_mic'] = getattr(asr_config, 'auto_stop_mic', True)
                    settings['auto_start_mic_on_conv_end'] = getattr(asr_config, 'auto_start_mic_on_conv_end', True)
                    settings['auto_start_mic_on'] = getattr(asr_config, 'auto_start_mic_on', True)
                
                # VAD设置
                if hasattr(char_config, 'vad_config') and char_config.vad_config:
                    vad_config = char_config.vad_config
                    settings['positive_speech_threshold'] = getattr(vad_config, 'positive_speech_threshold', 0.5)
                    settings['negative_speech_threshold'] = getattr(vad_config, 'negative_speech_threshold', 0.3)
                    settings['redemption_frames'] = getattr(vad_config, 'redemption_frames', 8)
                
                # TTS设置
                if hasattr(char_config, 'tts_config') and char_config.tts_config:
                    tts_config = char_config.tts_config
                    settings['tts_model'] = getattr(tts_config, 'model', 'fish_api_tts')
                    settings['tts_reference_id'] = getattr(tts_config, 'reference_id', '')
                    settings['tts_latency'] = getattr(tts_config, 'latency', 'balanced')
            
            # 只返回技术设置，不包含UI设置
            # UI设置（字幕、语言等）由前端本地管理
            
            return {
                "success": True,
                "settings": settings,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
            return Response(
                content=json.dumps({"error": f"加载设置失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

    @router.post("/api/settings/save")
    async def save_settings(request: dict):
        """
        保存设置接口（简化版 - 只处理角色预设切换）
        
        Args:
            request: 请求数据，包含settings_data和client
        
        Returns:
            保存结果
        """
        try:
            # ✅ 解析请求数据结构
            settings_data = request.get('settings_data', {})
            client = request.get('client')
            
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            # ✅ 调试：打印收到的设置数据
            logger.info(f"🔍 收到设置保存请求: {settings_data.keys()}")
            
            # === 只处理角色预设切换 ===
            if 'character_preset' in settings_data and settings_data['character_preset']:
                config_filename = settings_data['character_preset']
                logger.info(f"🔍 检测到角色预设切换请求: {config_filename}")
                logger.info(f"🔍 websocket_handler 是否可用: {websocket_handler is not None}")
                
                # 直接调用配置切换逻辑
                if websocket_handler and websocket_handler.client_connections:
                    logger.info(f"🔍 准备为所有客户端切换配置...")
                    try:
                        # 为每个连接的客户端执行配置切换
                        for client_uid, ws in websocket_handler.client_connections.items():
                            try:
                                context = websocket_handler.client_contexts.get(client_uid)
                                if context:
                                    # ✅ 直接调用配置切换方法
                                    await context.handle_config_switch(ws, config_filename)
                                    logger.info(f"✅ 已为客户端 {client_uid} 切换配置: {config_filename}")
                            except Exception as e:
                                logger.error(f"❌ 客户端 {client_uid} 配置切换失败: {e}")
                        
                        # 同步default_context_cache
                        try:
                            if websocket_handler.default_context_cache:
                                # 加载新配置到default_context
                                await websocket_handler.default_context_cache.load_from_config(
                                    websocket_handler.client_contexts[list(websocket_handler.client_contexts.keys())[0]].config
                                )
                                logger.info(f"✅ 已同步default_context_cache到新配置")
                        except Exception as e:
                            logger.warning(f"⚠️ 同步default_context失败: {e}")
                        
                        logger.info(f"✅ 角色切换完成: {config_filename}")
                        
                        return {
                            "success": True,
                            "message": f"角色已切换为: {config_filename}",
                            "client_id": client_id,
                            "character_preset": config_filename
                        }
                    except Exception as e:
                        logger.error(f"❌ 角色切换失败: {e}", exc_info=True)
                        return {
                            "success": False,
                            "error": f"角色切换失败: {str(e)}",
                            "client_id": client_id
                        }
                else:
                    # 没有WebSocket连接时返回错误
                    logger.warning(f"⚠️ 无WebSocket连接，无法切换角色")
                    return {
                        "success": False,
                        "error": "无WebSocket连接，无法切换角色。请确保前端已连接。",
                        "client_id": client_id
                    }
            else:
                return {
                    "success": False,
                    "error": "未提供有效的角色预设",
                    "client_id": client_id
                }
            
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            return Response(
                content=json.dumps({"error": f"保存设置失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

    @router.post("/api/live2d/switch")
    async def switch_character_preset(
        character_preset: str = Form(...),
        client: Optional[str] = Form(None)
    ):
        """
        角色切换API（信号模式）
        直接切换角色预设，无需查询当前状态
        
        Args:
            character_preset: 角色预设文件名（如 "character1.yaml"）
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            切换结果
        """
        try:
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            logger.info(f"🔄 收到角色切换信号: {character_preset} (client: {client_id})")
            
            if not character_preset:
                return Response(
                    content=json.dumps({"error": "角色预设不能为空"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 直接调用配置切换逻辑
            if websocket_handler and websocket_handler.client_connections:
                try:
                    # 为每个连接的客户端执行配置切换
                    for client_uid, ws in websocket_handler.client_connections.items():
                        try:
                            context = websocket_handler.client_contexts.get(client_uid)
                            if context:
                                # 直接调用配置切换方法
                                await context.handle_config_switch(ws, character_preset)
                                logger.info(f"✅ 已为客户端 {client_uid} 切换配置: {character_preset}")
                        except Exception as e:
                            logger.error(f"❌ 客户端 {client_uid} 配置切换失败: {e}")
                    
                    # 同步default_context_cache
                    try:
                        if websocket_handler.default_context_cache and websocket_handler.client_contexts:
                            first_client_uid = list(websocket_handler.client_contexts.keys())[0]
                            if first_client_uid in websocket_handler.client_contexts:
                                await websocket_handler.default_context_cache.load_from_config(
                                    websocket_handler.client_contexts[first_client_uid].config
                                )
                                logger.info(f"✅ 已同步default_context_cache到新配置")
                    except Exception as e:
                        logger.warning(f"⚠️ 同步default_context失败: {e}")
                    
                    # 通过WebSocket广播配置切换消息
                    if websocket_handler:
                        broadcast_message = {
                            "type": "character-switched",
                            "character_preset": character_preset,
                            "client_id": client_id
                        }
                        await websocket_handler.broadcast_settings_update(
                            broadcast_message, 
                            ["character"]
                        )
                    
                    logger.info(f"✅ 角色切换完成: {character_preset}")
                    
                    return {
                        "success": True,
                        "message": f"角色已切换为: {character_preset}",
                        "client_id": client_id,
                        "character_preset": character_preset
                    }
                except Exception as e:
                    logger.error(f"❌ 角色切换失败: {e}", exc_info=True)
                    return Response(
                        content=json.dumps({
                            "success": False,
                            "error": f"角色切换失败: {str(e)}",
                            "client_id": client_id
                        }),
                        status_code=500,
                        media_type="application/json"
                    )
            else:
                # 没有WebSocket连接时返回错误
                logger.warning(f"⚠️ 无WebSocket连接，无法切换角色")
                return Response(
                    content=json.dumps({
                        "success": False,
                        "error": "无WebSocket连接，无法切换角色。请确保前端已连接。",
                        "client_id": client_id
                    }),
                    status_code=503,
                    media_type="application/json"
                )
            
        except Exception as e:
            logger.error(f"角色切换API错误: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"角色切换失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

