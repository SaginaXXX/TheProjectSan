"""
主题介绍管理服务
提供主题数据的创建、读取、更新、删除（CRUD）操作
支持多语言和多租户
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger


class TopicManager:
    """主题管理器 - 负责主题数据的CRUD操作"""
    
    def __init__(self, base_dir: str = "topics"):
        """
        初始化主题管理器
        
        Args:
            base_dir: 主题基础目录
        """
        self.base_dir = Path(base_dir)
        self.supported_image_formats = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        self.supported_video_formats = {'.mp4', '.avi', '.mov', '.webm', '.mkv'}
    
    def _get_client_dir(self, client_id: str) -> Path:
        """获取客户的主题目录"""
        client_dir = self.base_dir / client_id
        client_dir.mkdir(parents=True, exist_ok=True)
        return client_dir
    
    def _get_topic_dir(self, client_id: str, topic_id: str) -> Path:
        """获取主题目录"""
        return self._get_client_dir(client_id) / topic_id
    
    def _get_topic_json_path(self, client_id: str, topic_id: str) -> Path:
        """获取主题JSON文件路径"""
        return self._get_topic_dir(client_id, topic_id) / "topic.json"
    
    def create_topic(
        self,
        client_id: str,
        topic_id: str,
        name: str,
        description: str = "",
        language: str = "ja"
    ) -> Dict[str, Any]:
        """
        创建新主题
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            name: 主题名称（单一语言）
            description: 主题描述（单一语言）
            language: 内容语言标记（如：ja/en/zh）
        
        Returns:
            创建的主题数据
        """
        # 创建主题目录结构
        topic_dir = self._get_topic_dir(client_id, topic_id)
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "images").mkdir(exist_ok=True)
        (topic_dir / "videos").mkdir(exist_ok=True)
        
        # 创建主题数据
        topic_data = {
            "topic_id": topic_id,
            "name": name,
            "description": description,
            "language": language,
            "images": [],
            "videos": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 保存主题JSON
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 创建主题: {topic_id} (client: {client_id}, language: {language})")
        return topic_data
    
    def get_topic(self, client_id: str, topic_id: str) -> Optional[Dict[str, Any]]:
        """
        获取主题数据
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
        
        Returns:
            主题数据，如果不存在返回None
        """
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        
        if not topic_json_path.exists():
            return None
        
        try:
            with open(topic_json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取主题失败 {topic_id}: {e}")
            return None
    
    def update_topic(
        self,
        client_id: str,
        topic_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None
    ) -> bool:
        """
        更新主题数据
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            name: 主题名称（单一语言，可选）
            description: 主题描述（单一语言，可选）
            language: 内容语言标记（可选）
        
        Returns:
            是否更新成功
        """
        topic_data = self.get_topic(client_id, topic_id)
        if not topic_data:
            return False
        
        # 更新字段
        if name is not None:
            topic_data['name'] = name
        if description is not None:
            topic_data['description'] = description
        if language is not None:
            topic_data['language'] = language
        
        topic_data['updated_at'] = datetime.now().isoformat()
        
        # 保存更新
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 更新主题: {topic_id} (client: {client_id})")
        return True
    
    def delete_topic(self, client_id: str, topic_id: str) -> bool:
        """
        删除主题
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
        
        Returns:
            是否删除成功
        """
        import shutil
        
        topic_dir = self._get_topic_dir(client_id, topic_id)
        if not topic_dir.exists():
            return False
        
        try:
            shutil.rmtree(topic_dir)
            logger.info(f"✅ 删除主题: {topic_id} (client: {client_id})")
            return True
        except Exception as e:
            logger.error(f"删除主题失败 {topic_id}: {e}")
            return False
    
    def list_topics(self, client_id: str) -> List[Dict[str, Any]]:
        """
        列出客户的所有主题
        
        Args:
            client_id: 客户ID
        
        Returns:
            主题列表
        """
        client_dir = self._get_client_dir(client_id)
        topics = []
        
        if not client_dir.exists():
            return topics
        
        for topic_dir in client_dir.iterdir():
            if not topic_dir.is_dir():
                continue
            
            topic_json_path = topic_dir / "topic.json"
            if topic_json_path.exists():
                try:
                    with open(topic_json_path, 'r', encoding='utf-8') as f:
                        topic_data = json.load(f)
                    
                    # 获取主题名称（简单字符串）
                    topic_name = topic_data.get('name', 'Unknown')
                    
                    topics.append({
                        "topic_id": topic_data.get('topic_id', topic_dir.name),
                        "name": topic_name,
                        "description": topic_data.get('description', ''),
                        "language": topic_data.get('language', 'ja'),
                        "image_count": len(topic_data.get('images', [])),
                        "video_count": len(topic_data.get('videos', [])),
                        "created_at": topic_data.get('created_at'),
                        "updated_at": topic_data.get('updated_at')
                    })
                except Exception as e:
                    logger.warning(f"加载主题 {topic_dir.name} 失败: {e}")
        
        return topics
    
    def add_image(
        self,
        client_id: str,
        topic_id: str,
        image_id: str,
        filename: str,
        url_path: str,
        description: str,
        file_size: int
    ) -> bool:
        """
        添加图片到主题
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            image_id: 图片ID
            filename: 文件名
            url_path: URL路径
            description: 图片描述（单一语言，必填）
            file_size: 文件大小（字节）
        
        Returns:
            是否添加成功
        """
        topic_data = self.get_topic(client_id, topic_id)
        if not topic_data:
            return False
        
        # 验证描述不能为空
        if not description or not description.strip():
            logger.warning(f"图片描述不能为空: {image_id}")
            return False
        
        # 检查图片数量限制
        if len(topic_data.get('images', [])) >= 10:
            logger.warning(f"主题 {topic_id} 图片数量已达上限")
            return False
        
        # 添加图片信息
        if 'images' not in topic_data:
            topic_data['images'] = []
        
        image_info = {
            "id": image_id,
            "filename": filename,
            "url_path": url_path,
            "description": description,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "format": Path(filename).suffix.lower()
        }
        
        topic_data['images'].append(image_info)
        topic_data['updated_at'] = datetime.now().isoformat()
        
        # 保存更新
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 添加图片到主题: {topic_id}/{image_id}")
        return True
    
    def add_video(
        self,
        client_id: str,
        topic_id: str,
        video_id: str,
        filename: str,
        url_path: str,
        description: str,
        file_size: int
    ) -> bool:
        """
        添加视频到主题
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            video_id: 视频ID
            filename: 文件名
            url_path: URL路径
            description: 视频描述（单一语言，必填）
            file_size: 文件大小（字节）
        
        Returns:
            是否添加成功
        """
        topic_data = self.get_topic(client_id, topic_id)
        if not topic_data:
            return False
        
        # 验证描述不能为空
        if not description or not description.strip():
            logger.warning(f"视频描述不能为空: {video_id}")
            return False
        
        # 检查视频数量限制
        if len(topic_data.get('videos', [])) >= 3:
            logger.warning(f"主题 {topic_id} 视频数量已达上限")
            return False
        
        # 添加视频信息
        if 'videos' not in topic_data:
            topic_data['videos'] = []
        
        video_info = {
            "id": video_id,
            "filename": filename,
            "url_path": url_path,
            "description": description,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "format": Path(filename).suffix.lower()
        }
        
        topic_data['videos'].append(video_info)
        topic_data['updated_at'] = datetime.now().isoformat()
        
        # 保存更新
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 添加视频到主题: {topic_id}/{video_id}")
        return True
    
    def delete_image(self, client_id: str, topic_id: str, image_id: str) -> bool:
        """
        删除主题图片
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            image_id: 图片ID
        
        Returns:
            是否删除成功
        """
        topic_data = self.get_topic(client_id, topic_id)
        if not topic_data:
            return False
        
        # 查找并删除图片
        images = topic_data.get('images', [])
        image_to_delete = None
        for img in images:
            if img.get('id') == image_id:
                image_to_delete = img
                break
        
        if not image_to_delete:
            return False
        
        # 删除文件
        image_path = self._get_topic_dir(client_id, topic_id) / "images" / image_to_delete['filename']
        if image_path.exists():
            image_path.unlink()
        
        # 从列表中移除
        topic_data['images'] = [img for img in images if img.get('id') != image_id]
        topic_data['updated_at'] = datetime.now().isoformat()
        
        # 保存更新
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 删除图片: {topic_id}/{image_id}")
        return True
    
    def delete_video(self, client_id: str, topic_id: str, video_id: str) -> bool:
        """
        删除主题视频
        
        Args:
            client_id: 客户ID
            topic_id: 主题ID
            video_id: 视频ID
        
        Returns:
            是否删除成功
        """
        topic_data = self.get_topic(client_id, topic_id)
        if not topic_data:
            return False
        
        # 查找并删除视频
        videos = topic_data.get('videos', [])
        video_to_delete = None
        for vid in videos:
            if vid.get('id') == video_id:
                video_to_delete = vid
                break
        
        if not video_to_delete:
            return False
        
        # 删除文件
        video_path = self._get_topic_dir(client_id, topic_id) / "videos" / video_to_delete['filename']
        if video_path.exists():
            video_path.unlink()
        
        # 从列表中移除
        topic_data['videos'] = [vid for vid in videos if vid.get('id') != video_id]
        topic_data['updated_at'] = datetime.now().isoformat()
        
        # 保存更新
        topic_json_path = self._get_topic_json_path(client_id, topic_id)
        with open(topic_json_path, 'w', encoding='utf-8') as f:
            json.dump(topic_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 删除视频: {topic_id}/{video_id}")
        return True


# 已移除parse_multilingual_field函数 - 不再需要多语言字典解析


def get_client_id_from_context(
    request_client: Optional[str],
    media_config: Any
) -> str:
    """
    从上下文获取客户ID
    
    Args:
        request_client: 请求中的客户ID参数
        media_config: 媒体配置对象
    
    Returns:
        客户ID
    """
    container_client_id = os.getenv('CLIENT_ID')
    config_client_id = getattr(media_config, 'client_id', None)
    return request_client or container_client_id or config_client_id or 'default_client'

