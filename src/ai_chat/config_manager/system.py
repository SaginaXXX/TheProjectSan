# config_manager/system.py
from pydantic import Field,model_validator
from typing import Dict, ClassVar, Optional
from pathlib import Path
from .i18n import I18nMixin, Description

class MediaServerConfig(I18nMixin):
    """媒体服务器配置"""
    host: str = Field("127.0.0.1", alias="host")
    port: int = Field(12393, alias="port") 
    ads_directory: str = Field("ads", alias="ads_directory")
    videos_directory: str = Field("videos", alias="videos_directory")
    use_absolute_paths: bool = Field(False, alias="use_absolute_paths")
    base_directory: Optional[str] = Field(None, alias="base_directory")
    
    def get_directory_path(self, directory_type: str) -> Path:
        """获取指定类型目录的路径"""
        if directory_type == 'ads':
            directory = self.ads_directory
        elif directory_type == 'videos':
            directory = self.videos_directory
        else:
            raise ValueError(f"Unknown directory type: {directory_type}")
        
        path = Path(directory)
        
        # 如果不是绝对路径，结合基础目录
        if not path.is_absolute():
            if self.base_directory:
                base = Path(self.base_directory)
            else:
                base = Path.cwd()
            path = base / path
        
        return path.resolve()
    
    def get_video_url(self, category: str, filename: str) -> str:
        """生成视频文件的URL"""
        return f"http://{self.host}:{self.port}/{category}/{filename}"


class SystemConfig(I18nMixin):
    """System configuration settings."""

    conf_version: str = Field(..., alias="conf_version") # 配置文件版本
    host: str = Field(..., alias="host") # 服务器主机地址
    port: int = Field(..., alias="port") # 服务器端口号
    config_alts_dir: str = Field(..., alias="config_alts_dir") # 备用配置目录
    tool_prompts: Dict[str, str] = Field(..., alias="tool_prompts") # 要插入到角色提示词中的工具提示词
    enable_proxy: bool = Field(False, alias="enable_proxy") # 启用代理模式以支持多个客户端使用一个 ws 连接
    enable_history: bool = Field(True, alias="enable_history") # 是否启用对话历史存储
    media_server: MediaServerConfig = Field(default_factory=MediaServerConfig, alias="media_server") # 媒体服务器配置

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "conf_version": Description(en="Configuration version", zh="配置文件版本"),
        "host": Description(en="Server host address", zh="服务器主机地址"),
        "port": Description(en="Server port number", zh="服务器端口号"),
        "config_alts_dir": Description(
            en="Directory for alternative configurations", zh="备用配置目录"
        ),
        "tool_prompts": Description(
            en="Tool prompts to be inserted into persona prompt",
            zh="要插入到角色提示词中的工具提示词",
        ),
        "enable_proxy": Description(
            en="Enable proxy mode for multiple clients",
            zh="启用代理模式以支持多个客户端使用一个 ws 连接",
        ),
        "enable_history": Description(
            en="Enable storing local conversation history",
            zh="是否启用本地对话历史存储",
        ),
        "media_server": Description(
            en="Media server configuration for ads and videos",
            zh="广告和视频的媒体服务器配置",
        ),
    }

@model_validator(mode="after")
def check_port(cls, values):
    port = values.port  # ✅ 正确：直接访问 port 属性
    if port < 0 or port > 65535:
        raise ValueError("Port must be between 0 and 65535")
    return values