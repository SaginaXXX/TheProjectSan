"""
Topic Routes
============
This module contains topic introduction management related routes.
"""

import os
import json
import asyncio
from typing import Optional
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, Form, Response
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_topic_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register topic management routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
    @router.post("/api/topics")
    async def create_topic(
        name: str = Form(...),
        description: str = Form(""),
        language: str = Form("ja"),
        client: Optional[str] = Form(None)
    ):
        """
        创建新主题
        
        Args:
            name: 主题名称（单一语言，如：兽耳夏日酒店）
            description: 整体描述（单一语言）
            language: 内容语言标记（ja/en/zh等，默认ja）
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            创建结果
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 生成主题ID
            topic_id = f"topic_{uuid4().hex[:8]}"
            
            # 使用TopicManager创建主题
            topic_manager = TopicManager()
            topic_data = topic_manager.create_topic(
                client_id=client_id,
                topic_id=topic_id,
                name=name,
                description=description,
                language=language
            )
            
            logger.info(f"✅ 创建主题成功: {topic_id} (client: {client_id}, language: {language})")
            
            # 🔄 自动触发MCP刷新（让AI能立即看到新主题）
            try:
                if hasattr(default_context_cache, 'mcp_client') and default_context_cache.mcp_client:
                    logger.info("🔄 触发主题列表刷新...")
                    asyncio.create_task(
                        default_context_cache.mcp_client.call_tool(
                            "topic-introduction-server",
                            "refresh_topics",
                            {}
                        )
                    )
            except Exception as e:
                logger.warning(f"触发MCP刷新失败（非致命）: {e}")
            
            return {
                "success": True,
                "message": "主题创建成功",
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"创建主题失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"创建主题失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.get("/api/topics")
    async def list_topics(client: Optional[str] = None):
        """
        获取主题列表
        
        Args:
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            主题列表
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager获取主题列表
            topic_manager = TopicManager()
            topics = topic_manager.list_topics(client_id)
            
            return {
                "success": True,
                "topics": topics,
                "total_count": len(topics),
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"获取主题列表失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"获取主题列表失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.get("/api/topics/{topic_id}")
    async def get_topic(topic_id: str, client: Optional[str] = None):
        """
        获取主题详情
        
        Args:
            topic_id: 主题ID
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            主题详情
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager获取主题
            topic_manager = TopicManager()
            topic_data = topic_manager.get_topic(client_id, topic_id)
            
            if not topic_data:
                return Response(
                    content=json.dumps({"error": f"主题不存在: {topic_id}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            return {
                "success": True,
                "topic": topic_data,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"获取主题详情失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"获取主题详情失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.put("/api/topics/{topic_id}")
    async def update_topic(
        topic_id: str,
        name: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        language: Optional[str] = Form(None),
        client: Optional[str] = Form(None)
    ):
        """
        更新主题
        
        Args:
            topic_id: 主题ID
            name: 主题名称（单一语言，可选）
            description: 整体描述（单一语言，可选）
            language: 内容语言标记（可选）
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            更新结果
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager更新主题
            topic_manager = TopicManager()
            success = topic_manager.update_topic(
                client_id=client_id,
                topic_id=topic_id,
                name=name,
                description=description,
                language=language
            )
            
            if not success:
                return Response(
                    content=json.dumps({"error": f"主题不存在: {topic_id}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 更新主题成功: {topic_id} (client: {client_id})")
            
            return {
                "success": True,
                "message": "主题更新成功",
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"更新主题失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"更新主题失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.delete("/api/topics/{topic_id}")
    async def delete_topic(topic_id: str, client: Optional[str] = None):
        """
        删除主题
        
        Args:
            topic_id: 主题ID
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            删除结果
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager删除主题
            topic_manager = TopicManager()
            success = topic_manager.delete_topic(client_id, topic_id)
            
            if not success:
                return Response(
                    content=json.dumps({"error": f"主题不存在: {topic_id}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 删除主题成功: {topic_id} (client: {client_id})")
            
            return {
                "success": True,
                "message": "主题删除成功",
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"删除主题失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"删除主题失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.post("/api/topics/{topic_id}/images")
    async def upload_topic_image(
        topic_id: str,
        file: UploadFile = File(...),
        description: str = Form(...),
        client: Optional[str] = Form(None)
    ):
        """
        上传主题图片
        
        Args:
            topic_id: 主题ID
            file: 图片文件
            description: 图片描述（必填，单一语言）
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            上传结果
        """
        try:
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 验证文件类型
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}:
                return Response(
                    content=json.dumps({"error": f"不支持的图片格式: {file_extension}"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 加载主题数据
            topic_json_path = Path("topics") / client_id / topic_id / "topic.json"
            if not topic_json_path.exists():
                return Response(
                    content=json.dumps({"error": f"主题不存在: {topic_id}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            with open(topic_json_path, 'r', encoding='utf-8') as f:
                topic_data = json.load(f)
            
            # 检查图片数量限制（最多10个）
            if len(topic_data.get('images', [])) >= 10:
                return Response(
                    content=json.dumps({"error": "图片数量已达上限（10个）"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 读取文件内容
            contents = await file.read()
            file_size = len(contents)
            
            # 生成唯一文件名
            image_id = f"img_{uuid4().hex[:8]}"
            safe_filename = f"{image_id}{file_extension}"
            
            # 保存文件到主题目录
            image_dir = Path("topics") / client_id / topic_id / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / safe_filename
            
            with open(image_path, 'wb') as f:
                f.write(contents)
            
            # 生成URL路径
            url_path = f"/topics/{client_id}/{topic_id}/images/{safe_filename}"
            
            # 使用TopicManager添加图片
            from ..topic_manager import TopicManager
            topic_manager = TopicManager()
            success = topic_manager.add_image(
                client_id=client_id,
                topic_id=topic_id,
                image_id=image_id,
                filename=safe_filename,
                url_path=url_path,
                description=description,  # 直接使用单一语言描述
                file_size=file_size
            )
            
            if not success:
                return Response(
                    content=json.dumps({"error": "添加图片失败"}),
                    status_code=500,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 上传主题图片成功: {topic_id}/{safe_filename} (client: {client_id})")
            
            # 🔄 自动触发MCP刷新（让AI能立即看到新上传的内容）
            try:
                if hasattr(default_context_cache, 'mcp_client') and default_context_cache.mcp_client:
                    logger.info("🔄 触发主题列表刷新...")
                    asyncio.create_task(
                        default_context_cache.mcp_client.call_tool(
                            "topic-introduction-server",
                            "refresh_topics",
                            {}
                        )
                    )
            except Exception as e:
                logger.warning(f"触发MCP刷新失败（非致命）: {e}")
            
            return {
                "success": True,
                "message": "图片上传成功",
                "image_id": image_id,
                "filename": safe_filename,
                "url_path": url_path,
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"上传主题图片失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"上传图片失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.post("/api/topics/{topic_id}/videos")
    async def upload_topic_video(
        topic_id: str,
        file: UploadFile = File(...),
        description: str = Form(...),
        client: Optional[str] = Form(None)
    ):
        """
        上传主题视频
        
        Args:
            topic_id: 主题ID
            file: 视频文件
            description: 视频描述（必填，单一语言）
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            上传结果
        """
        try:
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 验证文件类型
            file_extension = Path(file.filename).suffix.lower()
            if file_extension not in {'.mp4', '.avi', '.mov', '.webm', '.mkv'}:
                return Response(
                    content=json.dumps({"error": f"不支持的视频格式: {file_extension}"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 加载主题数据
            topic_json_path = Path("topics") / client_id / topic_id / "topic.json"
            if not topic_json_path.exists():
                return Response(
                    content=json.dumps({"error": f"主题不存在: {topic_id}"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            with open(topic_json_path, 'r', encoding='utf-8') as f:
                topic_data = json.load(f)
            
            # 检查视频数量限制（最多3个）
            if len(topic_data.get('videos', [])) >= 3:
                return Response(
                    content=json.dumps({"error": "视频数量已达上限（3个）"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 读取文件内容
            contents = await file.read()
            file_size = len(contents)
            
            # 验证文件大小（最大500MB）
            if file_size > 500 * 1024 * 1024:
                return Response(
                    content=json.dumps({"error": "文件大小超过限制（500MB）"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 生成唯一文件名
            video_id = f"vid_{uuid4().hex[:8]}"
            safe_filename = f"{video_id}{file_extension}"
            
            # 保存文件到主题目录
            video_dir = Path("topics") / client_id / topic_id / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            video_path = video_dir / safe_filename
            
            with open(video_path, 'wb') as f:
                f.write(contents)
            
            # 生成URL路径
            url_path = f"/topics/{client_id}/{topic_id}/videos/{safe_filename}"
            
            # 使用TopicManager添加视频
            from ..topic_manager import TopicManager
            topic_manager = TopicManager()
            success = topic_manager.add_video(
                client_id=client_id,
                topic_id=topic_id,
                video_id=video_id,
                filename=safe_filename,
                url_path=url_path,
                description=description,  # 直接使用单一语言描述
                file_size=file_size
            )
            
            if not success:
                return Response(
                    content=json.dumps({"error": "添加视频失败"}),
                    status_code=500,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 上传主题视频成功: {topic_id}/{safe_filename} (client: {client_id})")
            
            # 🔄 自动触发MCP刷新（让AI能立即看到新上传的内容）
            try:
                if hasattr(default_context_cache, 'mcp_client') and default_context_cache.mcp_client:
                    logger.info("🔄 触发主题列表刷新...")
                    asyncio.create_task(
                        default_context_cache.mcp_client.call_tool(
                            "topic-introduction-server",
                            "refresh_topics",
                            {}
                        )
                    )
            except Exception as e:
                logger.warning(f"触发MCP刷新失败（非致命）: {e}")
            
            # 通过WebSocket广播上传成功消息
            if websocket_handler:
                refresh_message = {
                    "type": "topic-refresh",
                    "action": "video_uploaded",
                    "topic_id": topic_id,
                    "filename": safe_filename,
                    "client_id": client_id
                }
                asyncio.create_task(
                    websocket_handler.broadcast_to_all(refresh_message)
                )
            
            return {
                "success": True,
                "message": "视频上传成功",
                "video_id": video_id,
                "filename": safe_filename,
                "url_path": url_path,
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"上传主题视频失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"上传视频失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.delete("/api/topics/{topic_id}/images/{image_id}")
    async def delete_topic_image(
        topic_id: str,
        image_id: str,
        client: Optional[str] = None
    ):
        """
        删除主题图片
        
        Args:
            topic_id: 主题ID
            image_id: 图片ID
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            删除结果
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager删除图片
            topic_manager = TopicManager()
            success = topic_manager.delete_image(client_id, topic_id, image_id)
            
            if not success:
                return Response(
                    content=json.dumps({"error": f"图片不存在或主题不存在"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 删除主题图片成功: {topic_id}/{image_id} (client: {client_id})")
            
            return {
                "success": True,
                "message": "图片删除成功",
                "image_id": image_id,
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"删除主题图片失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"删除图片失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )
    
    @router.delete("/api/topics/{topic_id}/videos/{video_id}")
    async def delete_topic_video(
        topic_id: str,
        video_id: str,
        client: Optional[str] = None
    ):
        """
        删除主题视频
        
        Args:
            topic_id: 主题ID
            video_id: 视频ID
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            删除结果
        """
        try:
            from ..topic_manager import TopicManager
            
            # 获取客户ID
            media_config = default_context_cache.config.system_config.media_server
            container_client_id = os.getenv('CLIENT_ID')
            config_client_id = media_config.client_id
            client_id = client or container_client_id or config_client_id or 'default_client'
            
            # 使用TopicManager删除视频
            topic_manager = TopicManager()
            success = topic_manager.delete_video(client_id, topic_id, video_id)
            
            if not success:
                return Response(
                    content=json.dumps({"error": f"视频不存在或主题不存在"}),
                    status_code=404,
                    media_type="application/json"
                )
            
            logger.info(f"✅ 删除主题视频成功: {topic_id}/{video_id} (client: {client_id})")
            
            return {
                "success": True,
                "message": "视频删除成功",
                "video_id": video_id,
                "topic_id": topic_id,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"删除主题视频失败: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"删除视频失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

