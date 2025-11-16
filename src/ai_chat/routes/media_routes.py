"""
Media Routes
===========
This module contains media upload and management related routes.
"""

import os
import json
import time
import asyncio
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Response
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_media_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register media upload and management routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
    @router.post("/api/upload")
    async def upload_media(
        file: UploadFile = File(...),
        category: str = Form("ads"),
        client: Optional[str] = Form(None)
    ):
        """
        通用媒体文件上传接口（支持多租户隔离）
        
        Args:
            file: 上传的文件
            category: 分类 (ads=广告, agent=Agent资源)
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            上传结果
        """
        try:
            from ..storage.storage_factory import create_storage_service
            
            # 1. 获取客户ID - 标准优先级逻辑
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')  # 生产环境（Docker）
            config_client_id = media_config.client_id      # 开发环境回退
            
            # 优先级：API参数 > 环境变量 > 配置文件 > 默认值
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            logger.debug(f"📤 POST /api/upload - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 2. 验证客户ID格式
            if not client_id.startswith('client_'):
                return Response(
                    content=json.dumps({"error": "无效的客户ID格式，必须以'client_'开头"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 3. 可选：验证客户ID白名单
            valid_clients = os.getenv('VALID_CLIENTS', '')
            if valid_clients:
                valid_list = [c.strip() for c in valid_clients.split(',')]
                if client_id not in valid_list:
                    return Response(
                        content=json.dumps({"error": f"客户ID '{client_id}' 未授权"}),
                        status_code=403,
                        media_type="application/json"
                    )
            
            # 4. 验证分类
            if category not in ['ads', 'agent']:
                return Response(
                    content=json.dumps({"error": f"不支持的分类: {category}。支持: ads, agent"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 5. 验证文件类型
            allowed_extensions = {
                'ads': {'.mp4', '.webm', '.avi', '.mov', '.mkv'},
                'agent': {'.mp4', '.webm', '.avi', '.mov', '.jpg', '.jpeg', '.png', '.gif'}
            }
            
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions[category]:
                return Response(
                    content=json.dumps({
                        "error": f"不支持的文件格式。{category}支持: {', '.join(allowed_extensions[category])}"
                    }),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 6. 读取并验证文件大小
            contents = await file.read()
            max_size = 500 * 1024 * 1024  # 500MB
            if len(contents) > max_size:
                return Response(
                    content=json.dumps({
                        "error": f"文件过大。最大: 500MB, 当前: {len(contents)/(1024*1024):.1f}MB"
                    }),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 7. 生成唯一文件名
            original_name = Path(file.filename).stem
            timestamp = int(time.time())
            filename = f"{original_name}_{timestamp}{file_ext}"
            
            # 8. 创建存储服务并上传
            media_config = default_context_cache.config.system_config.media_server
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 上传文件
            storage_path = await storage_service.upload_file(contents, category, filename)
            file_url = storage_service.get_file_url(category, filename)
            
            logger.info(f"[{client_id}] Uploaded {category}: {filename} to {storage_path}")
            
            # 9. 通过WebSocket广播上传成功消息（信号模式）
            if category == 'ads' and websocket_handler:
                try:
                    # 广播刷新请求到所有连接的WebSocket客户端
                    refresh_message = {
                        "type": "advertisement-refresh",
                        "action": "uploaded",
                        "filename": filename,
                        "client_id": client_id
                    }
                    asyncio.create_task(
                        websocket_handler.broadcast_settings_update(refresh_message, ["advertisement"])
                    )
                    logger.info(f"广告上传成功，已发送刷新通知")
                except Exception as e:
                    logger.warning(f"广播广告刷新失败: {e}")
            
            return {
                "status": "success",
                "message": f"文件上传成功",
                "file_info": {
                    "client_id": client_id,
                    "category": category,
                    "filename": filename,
                    "storage_path": storage_path,
                    "url": file_url,
                    "size_mb": round(len(contents) / (1024 * 1024), 2),
                    "storage_type": media_config.storage_type
                }
            }
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return Response(
                content=json.dumps({"error": f"上传失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

    @router.get("/api/media/list")
    async def list_media_files(category: str = "ads", client: Optional[str] = None):
        """
        获取媒体文件列表（支持多租户隔离）
        
        Args:
            category: 分类 (ads/agent)
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            文件列表
        """
        try:
            from ..storage.storage_factory import create_storage_service
            
            # 获取客户ID - 标准优先级逻辑
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')  # 生产环境（Docker）
            config_client_id = media_config.client_id      # 开发环境回退
            
            # 优先级：API参数 > 环境变量 > 配置文件 > 默认值
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            logger.debug(f"📂 GET /api/media/list - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 创建存储服务
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 获取文件列表
            files = await storage_service.list_files(category)
            
            return {
                "status": "success",
                "client_id": client_id,
                "category": category,
                "files": files,
                "total_count": len(files),
                "storage_type": media_config.storage_type
            }
            
        except Exception as e:
            logger.error(f"Error listing media files: {e}")
            return Response(
                content=json.dumps({"error": f"获取文件列表失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

    @router.delete("/api/media/delete")
    async def delete_media_file(
        category: str,
        filename: str,
        client: Optional[str] = None
    ):
        """
        删除媒体文件（支持多租户隔离）
        
        Args:
            category: 分类 (ads/agent)
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
            
            logger.debug(f"🗑️ DELETE /api/media/delete - API参数: {client}, 环境变量: {container_client_id}, 配置文件: {config_client_id}, 最终使用: {client_id}")
            
            # 创建存储服务
            storage_service = create_storage_service(media_config, client_id=client_id)
            
            # 删除文件
            success = await storage_service.delete_file(category, filename)
            
            if success:
                logger.info(f"[{client_id}] Deleted {category}/{filename}")
                
                # 如果是广告视频，通知MCP广告服务器刷新
                if category == 'ads' and websocket_handler:
                    try:
                        refresh_message = {
                            "type": "advertisement-refresh",
                            "action": "deleted",
                            "filename": filename,
                            "client_id": client_id
                        }
                        asyncio.create_task(
                            websocket_handler.broadcast_settings_update(refresh_message, ["advertisement"])
                        )
                        logger.info(f"广告删除成功，已发送刷新通知")
                    except Exception as e:
                        logger.warning(f"广播广告刷新失败: {e}")
                
                return {
                    "status": "success",
                    "message": f"文件 '{filename}' 删除成功",
                    "deleted_file": filename,
                    "client_id": client_id
                }
            else:
                return Response(
                    content=json.dumps({"error": f"文件不存在: {filename}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
        except Exception as e:
            logger.error(f"Error deleting media file: {e}")
            return Response(
                content=json.dumps({"error": f"删除失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

