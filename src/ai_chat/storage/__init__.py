"""
存储抽象层
支持本地存储和S3云存储的无缝切换
"""

from .storage_interface import StorageInterface
from .local_service import LocalStorageService
from .storage_factory import create_storage_service

__all__ = ['StorageInterface', 'LocalStorageService', 'create_storage_service']

# 尝试导入S3服务（可选依赖）
try:
    from .s3_service import S3StorageService
    __all__.append('S3StorageService')
except ImportError:
    pass

