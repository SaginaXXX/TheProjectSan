"""
存储接口定义
提供统一的存储抽象，支持本地存储和S3云存储
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pathlib import Path


class StorageInterface(ABC):
    """存储服务接口"""
    
    def __init__(self, client_id: str):
        """
        初始化存储服务
        
        Args:
            client_id: 客户标识
        """
        self.client_id = client_id
    
    @abstractmethod
    async def upload_file(
        self, 
        file_data: bytes, 
        category: str, 
        filename: str
    ) -> str:
        """
        上传文件
        
        Args:
            file_data: 文件二进制数据
            category: 分类 (ads/agent)
            filename: 文件名
            
        Returns:
            存储路径或URL
        """
        pass
    
    @abstractmethod
    async def list_files(self, category: str) -> List[Dict]:
        """
        列出指定分类下的所有文件
        
        Args:
            category: 分类 (ads/agent)
            
        Returns:
            文件列表
        """
        pass
    
    @abstractmethod
    async def delete_file(self, category: str, filename: str) -> bool:
        """
        删除文件
        
        Args:
            category: 分类 (ads/agent)
            filename: 文件名
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def file_exists(self, category: str, filename: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            category: 分类 (ads/agent)
            filename: 文件名
            
        Returns:
            文件是否存在
        """
        pass
    
    @abstractmethod
    def get_file_url(self, category: str, filename: str) -> str:
        """
        获取文件访问URL
        
        Args:
            category: 分类 (ads/agent)
            filename: 文件名
            
        Returns:
            文件访问URL
        """
        pass

