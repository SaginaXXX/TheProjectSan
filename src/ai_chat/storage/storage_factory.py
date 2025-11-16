"""
存储服务工厂
根据配置自动创建对应的存储服务实例
"""

import os
from .storage_interface import StorageInterface
from .local_service import LocalStorageService
from ..config_manager.system import MediaServerConfig


def create_storage_service(config: MediaServerConfig, client_id: str = None) -> StorageInterface:
    """
    根据配置创建存储服务
    
    Args:
        config: 媒体服务器配置
        client_id: 客户ID（可选，优先使用此参数）
        
    Returns:
        存储服务实例（LocalStorageService 或 S3StorageService）
    """
    # 优先使用传入的client_id，否则从环境变量或配置获取
    if client_id is None:
        client_id = os.getenv('CLIENT_ID') or config.client_id
    
    storage_type = config.storage_type.lower()
    
    if storage_type == "s3":
        # 使用S3存储
        from .s3_service import S3StorageService
        
        if not config.s3_bucket:
            raise ValueError(
                "S3 storage enabled but s3_bucket is not configured. "
                "Please set s3_bucket in config or S3_BUCKET environment variable."
            )
        
        return S3StorageService(
            client_id=client_id,
            bucket=config.s3_bucket or os.getenv('S3_BUCKET'),
            region=config.s3_region or os.getenv('S3_REGION', 'us-east-1'),
            access_key=config.s3_access_key or os.getenv('S3_ACCESS_KEY'),
            secret_key=config.s3_secret_key or os.getenv('S3_SECRET_KEY'),
            cdn_url=config.cdn_url or os.getenv('CDN_URL')
        )
    
    elif storage_type == "local":
        # 使用本地存储
        base_directory = config.base_directory or "."
        return LocalStorageService(
            client_id=client_id,
            base_directory=base_directory
        )
    
    else:
        raise ValueError(
            f"Unknown storage_type: {storage_type}. "
            f"Supported types: 'local', 's3'"
        )

