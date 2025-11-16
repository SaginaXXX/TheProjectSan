"""
本地存储服务实现
支持CLIENT_ID目录隔离
"""

import os
from pathlib import Path
from typing import List, Dict
from .storage_interface import StorageInterface


class LocalStorageService(StorageInterface):
    """本地文件系统存储服务"""
    
    def __init__(self, client_id: str, base_directory: str = "."):
        """
        初始化本地存储服务
        
        Args:
            client_id: 客户标识
            base_directory: 基础目录
        """
        super().__init__(client_id)
        self.base_directory = Path(base_directory)
    
    def _get_client_dir(self, category: str) -> Path:
        """
        获取客户的存储目录
        
        Args:
            category: 分类 (ads/agent)
            
        Returns:
            客户目录路径
        """
        # 路径格式: ads/client_001/ 或 agent/client_001/
        client_dir = self.base_directory / category / self.client_id
        client_dir.mkdir(parents=True, exist_ok=True)
        return client_dir
    
    async def upload_file(
        self, 
        file_data: bytes, 
        category: str, 
        filename: str
    ) -> str:
        """
        上传文件到本地存储
        
        Returns:
            相对路径: ads/client_001/video.mp4
        """
        client_dir = self._get_client_dir(category)
        file_path = client_dir / filename
        
        # 写入文件
        with open(file_path, "wb") as f:
            f.write(file_data)
        
        # 返回相对路径
        relative_path = f"{category}/{self.client_id}/{filename}"
        return relative_path
    
    async def list_files(self, category: str) -> List[Dict]:
        """
        列出客户在指定分类下的所有文件
        """
        client_dir = self._get_client_dir(category)
        
        # 调试日志
        print(f"🔍 LocalStorageService.list_files:")
        print(f"  - client_id: {self.client_id}")
        print(f"  - category: {category}")
        print(f"  - base_directory: {self.base_directory}")
        print(f"  - client_dir: {client_dir}")
        print(f"  - client_dir.exists(): {client_dir.exists()}")
        
        if not client_dir.exists():
            print(f"  - ❌ 目录不存在，返回空列表")
            return []
        
        files = []
        for file_path in client_dir.iterdir():
            print(f"  - 发现: {file_path.name} (is_file: {file_path.is_file()})")
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "filename": file_path.name,
                    "path": f"{category}/{self.client_id}/{file_path.name}",
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_time": stat.st_mtime,
                    "category": category,
                    "client_id": self.client_id
                })
        
        print(f"  - ✅ 返回 {len(files)} 个文件")
        return files
    
    async def delete_file(self, category: str, filename: str) -> bool:
        """
        删除文件
        """
        client_dir = self._get_client_dir(category)
        file_path = client_dir / filename
        
        if not file_path.exists():
            return False
        
        # 安全检查：确保文件在客户目录中
        try:
            file_path.resolve().relative_to(client_dir.resolve())
        except ValueError:
            raise ValueError("非法的文件路径")
        
        file_path.unlink()
        return True
    
    async def file_exists(self, category: str, filename: str) -> bool:
        """
        检查文件是否存在
        """
        client_dir = self._get_client_dir(category)
        file_path = client_dir / filename
        return file_path.exists() and file_path.is_file()
    
    def get_file_url(self, category: str, filename: str) -> str:
        """
        获取文件访问URL（本地路径）
        
        Returns:
            URL路径: /ads/client_001/video.mp4
        """
        return f"/{category}/{self.client_id}/{filename}"

