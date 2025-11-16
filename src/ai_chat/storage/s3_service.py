"""
S3云存储服务实现
支持CLIENT_ID前缀隔离
"""

import os
from typing import List, Dict, Optional
from pathlib import Path
from .storage_interface import StorageInterface

try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False


class S3StorageService(StorageInterface):
    """S3对象存储服务"""
    
    def __init__(
        self, 
        client_id: str,
        bucket: str,
        region: str = "us-east-1",
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        cdn_url: Optional[str] = None
    ):
        """
        初始化S3存储服务
        
        Args:
            client_id: 客户标识
            bucket: S3存储桶名称
            region: AWS区域
            access_key: 访问密钥（可选，优先从环境变量读取）
            secret_key: 密钥（可选，优先从环境变量读取）
            cdn_url: CDN URL（可选）
        """
        if not S3_AVAILABLE:
            raise ImportError(
                "boto3 is not installed. Install it with: pip install boto3"
            )
        
        super().__init__(client_id)
        self.bucket = bucket
        self.region = region
        self.cdn_url = cdn_url
        
        # 初始化S3客户端
        self.s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key or os.getenv('AWS_ACCESS_KEY') or os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=secret_key or os.getenv('AWS_SECRET_KEY') or os.getenv('S3_SECRET_KEY')
        )
    
    def _get_s3_key(self, category: str, filename: str) -> str:
        """
        获取S3 key（含CLIENT_ID前缀）
        
        Args:
            category: 分类 (ads/agent)
            filename: 文件名
            
        Returns:
            S3 key: client_001/ads/video.mp4
        """
        return f"{self.client_id}/{category}/{filename}"
    
    def _get_content_type(self, filename: str) -> str:
        """根据文件扩展名获取Content-Type"""
        ext = Path(filename).suffix.lower()
        content_types = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif'
        }
        return content_types.get(ext, 'application/octet-stream')
    
    async def upload_file(
        self, 
        file_data: bytes, 
        category: str, 
        filename: str
    ) -> str:
        """
        上传文件到S3
        
        Returns:
            S3 key: client_001/ads/video.mp4
        """
        s3_key = self._get_s3_key(category, filename)
        
        # 上传到S3
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=file_data,
            ContentType=self._get_content_type(filename)
        )
        
        return s3_key
    
    async def list_files(self, category: str) -> List[Dict]:
        """
        列出S3中指定分类下的所有文件
        """
        prefix = f"{self.client_id}/{category}/"
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                filename = obj['Key'].split('/')[-1]
                files.append({
                    "filename": filename,
                    "path": obj['Key'],
                    "size_bytes": obj['Size'],
                    "size_mb": round(obj['Size'] / (1024 * 1024), 2),
                    "modified_time": obj['LastModified'].timestamp(),
                    "category": category,
                    "client_id": self.client_id
                })
            
            return files
        except ClientError as e:
            print(f"Error listing S3 files: {e}")
            return []
    
    async def delete_file(self, category: str, filename: str) -> bool:
        """
        删除S3文件
        """
        s3_key = self._get_s3_key(category, filename)
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket,
                Key=s3_key
            )
            return True
        except ClientError as e:
            print(f"Error deleting S3 file: {e}")
            return False
    
    async def file_exists(self, category: str, filename: str) -> bool:
        """
        检查S3文件是否存在
        """
        s3_key = self._get_s3_key(category, filename)
        
        try:
            self.s3_client.head_object(
                Bucket=self.bucket,
                Key=s3_key
            )
            return True
        except ClientError:
            return False
    
    def get_file_url(self, category: str, filename: str) -> str:
        """
        获取文件访问URL
        
        Returns:
            CDN URL或S3 URL
        """
        s3_key = self._get_s3_key(category, filename)
        
        if self.cdn_url:
            # 使用CDN URL
            return f"{self.cdn_url}/{s3_key}"
        else:
            # 生成S3直接URL
            return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"

