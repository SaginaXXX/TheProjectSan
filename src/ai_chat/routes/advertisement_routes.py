"""
Advertisement Routes
===================
This module contains advertisement management related routes.
"""

import os
import json
import asyncio
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Response
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_advertisement_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register advertisement management routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
    @router.get("/api/ads")
    async def get_advertisement_list(client: Optional[str] = None):
        """
        获取广告视频列表（支持多租户隔离）
        
        Args:
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            广告视频列表
        """
        try:
            from ..storage.storage_factory import create_storage_service
            
            # 获取客户ID - 标准优先级逻辑
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')  # 生产环境（Docker）
            config_client_id = media_config.client_id      # 开发环境回退
            
            # 优先级：API参数 > 环境变量 > 配置文件 > 默认值
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            logger.debug(f"📂 GET /api/ads - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 创建存储服务
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 获取文件列表
            files = await storage_service.list_files("ads")
            
            # 转换为旧格式（兼容前端）
            advertisements = []
            for idx, file in enumerate(files):
                advertisements.append({
                    "id": f"ad_{idx:03d}",
                    "name": Path(file["filename"]).stem,
                    "filename": file["filename"],
                    "path": file["path"],
                    "url_path": f"/ads/{client_id}/{file['filename']}",  # 包含CLIENT_ID的路径
                    "size_bytes": file["size_bytes"],
                    "size_mb": file.get("size_mb", round(file["size_bytes"] / (1024 * 1024), 2)),
                    "format": Path(file["filename"]).suffix.lower(),
                    "category": "advertisement"
                })
            
            return {
                "advertisements": advertisements,
                "total_count": len(advertisements),
                "status": "success",
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"Error getting advertisement list: {e}")
            return Response(
                content=json.dumps({"error": f"Failed to get advertisement list: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.post("/api/ads/upload")
    async def upload_advertisement(file: UploadFile = File(...), client: Optional[str] = None):
        """
        上传广告视频文件（支持多租户隔离）
        
        Args:
            file: 上传的视频文件
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            上传结果
        """
        try:
            from ..storage.storage_factory import create_storage_service
            
            # 获取客户ID - 标准优先级逻辑
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')  # 生产环境（Docker）
            config_client_id = media_config.client_id      # 开发环境回退
            
            # 优先级：API参数 > 环境变量 > 配置文件 > 默认值
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            logger.debug(f"📤 POST /api/ads/upload - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 验证文件类型
            allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                return Response(
                    content=json.dumps({
                        "error": f"不支持的文件格式: {file_extension}。支持的格式: {', '.join(allowed_extensions)}"
                    }),
                    status_code=400,
                    media_type="application/json",
                )
            
            # 验证文件大小（限制为500MB）
            max_size = 500 * 1024 * 1024  # 500MB
            contents = await file.read()
            if len(contents) > max_size:
                return Response(
                    content=json.dumps({
                        "error": f"文件太大。最大允许大小: 500MB，当前文件: {len(contents)/(1024*1024):.1f}MB"
                    }),
                    status_code=400,
                    media_type="application/json",
                )
            
            # 创建存储服务
            media_config = default_context_cache.config.system_config.media_server
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 使用存储服务上传文件
            file_path = await storage_service.upload_file(contents, "ads", file.filename)
            
            # 获取文件信息
            file_size = len(contents)
            original_name = Path(file.filename).stem
            
            logger.info(f"Successfully uploaded advertisement for {client_id}: {file.filename} ({file_size/(1024*1024):.2f}MB)")
            
            # 通过WebSocket广播上传成功消息（信号模式）
            if websocket_handler:
                refresh_message = {
                    "type": "advertisement-refresh",
                    "action": "uploaded",
                    "filename": file.filename,
                    "client_id": client_id
                }
                asyncio.create_task(
                    websocket_handler.broadcast_settings_update(refresh_message, ["advertisement"])
                )
            
            return {
                "status": "success",
                "message": f"广告视频 '{file.filename}' 上传成功",
                "client_id": client_id,
                "file_info": {
                    "name": original_name,
                    "filename": file.filename,
                    "path": file_path,
                    "url_path": f"/ads/{client_id}/{file.filename}",
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "format": file_extension,
                    "category": "advertisement"
                }
            }
            
        except Exception as e:
            logger.error(f"Error uploading advertisement: {e}")
            return Response(
                content=json.dumps({"error": f"上传失败: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.delete("/api/ads/{filename}")
    async def delete_advertisement(filename: str, client: Optional[str] = None):
        """
        删除广告视频文件（支持多租户隔离）
        
        Args:
            filename: 文件名
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            删除结果
        """
        try:
            from ..storage.storage_factory import create_storage_service
            
            # 获取客户ID - 标准优先级逻辑
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')  # 生产环境（Docker）
            config_client_id = media_config.client_id      # 开发环境回退
            
            # 优先级：API参数 > 环境变量 > 配置文件 > 默认值
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            logger.debug(f"🗑️ DELETE /api/ads/{filename} - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 创建存储服务
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 使用存储服务删除文件
            success = await storage_service.delete_file("ads", filename)
            
            if success:
                logger.info(f"Successfully deleted advertisement for {client_id}: {filename}")
                return {
                    "status": "success",
                    "message": f"广告视频 '{filename}' 删除成功",
                    "client_id": client_id,
                    "deleted_file": filename
                }
            else:
                return Response(
                    content=json.dumps({"error": f"文件不存在: {filename}"}),
                    status_code=404,
                    media_type="application/json",
                )
            
        except Exception as e:
            logger.error(f"Error deleting advertisement: {e}")
            return Response(
                content=json.dumps({"error": f"删除失败: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.post("/api/media/audio-mode")
    async def update_audio_mode(
        audio_mode: str = Form(...),
        client: Optional[str] = Form(None)
    ):
        """
        广告音频模式API（信号模式）
        直接设置广告音频播放模式，无需查询当前状态
        
        Args:
            audio_mode: 音频模式 ("muted" | "audio" | "audio_vad")
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            更新结果
        """
        try:
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            # 验证音频模式
            valid_modes = ["muted", "audio", "audio_vad"]
            if audio_mode not in valid_modes:
                return Response(
                    content=json.dumps({
                        "error": f"无效的音频模式: {audio_mode}。有效模式: {', '.join(valid_modes)}"
                    }),
                    status_code=400,
                    media_type="application/json"
                )
            
            logger.info(f"🎵 收到广告音频模式信号: {audio_mode} (client: {client_id})")
            
            # 通过WebSocket广播广告音频模式更新（直接广播原始消息）
            if websocket_handler:
                broadcast_message = {
                    "type": "advertisement-audio-mode-update",
                    "audio_mode": audio_mode,
                    "client_id": client_id
                }
                # 直接广播原始消息，而不是包装成settings-updated
                await websocket_handler.broadcast_to_all(broadcast_message)
                logger.info(f"✅ 广告音频模式已广播: {audio_mode}")
            
            return {
                "success": True,
                "message": f"广告音频模式已设置为: {audio_mode}",
                "audio_mode": audio_mode,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"广告音频模式API错误: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"广告音频模式更新失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

