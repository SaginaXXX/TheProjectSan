#!/usr/bin/env python3
"""
广告轮播管理 MCP 服务器
提供广告视频查询和播放列表功能
与唤醒词系统配合，实现智能广告轮播
"""

import json
import sys
import re
import asyncio
import argparse
import random
from pathlib import Path
from typing import Dict, List, Optional, Any

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import mcp.types as types
from pydantic import AnyUrl


try:
    # Force UTF-8 output to avoid Windows GBK console crashes
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

class SimpleMediaConfig:
    """简化的媒体配置类，用于独立MCP服务器"""
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 12393
        self.ads_directory = "ads"
        self.videos_directory = "videos"
    
    def get_directory_path(self, directory_type: str):
        """获取指定类型目录的路径"""
        if directory_type == 'ads':
            return Path(self.ads_directory)
        elif directory_type == 'videos':
            return Path(self.videos_directory)
        else:
            raise ValueError(f"Unknown directory type: {directory_type}")
    
    def get_video_url(self, category: str, filename: str) -> str:
        """生成视频文件的URL"""
        return f"http://{self.host}:{self.port}/{category}/{filename}"


def get_media_config():
    """获取媒体服务器配置"""
    try:
        # 尝试从系统配置加载
        from ..config_manager.utils import Config
        config = Config()
        return config.system_config.media_server
    except Exception as e:
        print(f"Warning: Failed to load full system config: {e}")
        
        # 尝试直接从YAML加载媒体服务器配置
        try:
            import yaml
            from pathlib import Path
            
            config_path = Path("conf.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                    system_config = yaml_config.get('system_config', {})
                    media_server_config = system_config.get('media_server', {})
                    
                    # 创建简化配置对象
                    config = SimpleMediaConfig()
                    config.host = media_server_config.get('host', '127.0.0.1')
                    config.port = media_server_config.get('port', 12393)
                    config.ads_directory = media_server_config.get('ads_directory', 'ads')
                    config.videos_directory = media_server_config.get('videos_directory', 'videos')
                    
                    print(f"Loaded media config from YAML: host={config.host}, port={config.port}")
                    return config
        except Exception as yaml_error:
            print(f"Warning: Failed to load YAML config: {yaml_error}")
        
        # 最后的fallback
        print("Using default media configuration")
        return SimpleMediaConfig()


class AdvertisementServer:
    """广告轮播管理服务器"""
    
    def __init__(self, ads_dir: str = "ads"):
        self.server = Server("advertisement-server")
        
        # 获取媒体配置
        self.media_config = get_media_config()
        try:
            self.ads_dir = self.media_config.get_directory_path('ads')
        except:
            # Fallback to provided directory
            self.ads_dir = Path(ads_dir)
        
        self.advertisements = {}
        self.supported_formats = {'.mp4', '.avi', '.mov', '.webm', '.mkv'}
        self.current_index = 0
        
        # 播放配置
        self.config = {
            "shuffle_mode": True,
            "auto_advance": True,
            "advance_mode": "on_video_end",  # 视频播放完毕后切换
            "loop_playlist": True
        }
        
        # 统计信息
        self.stats = {
            "total_ads": 0,
            "session_plays": 0,
            "total_plays": 0
        }
        
        # 欢迎信息
        self.welcome_messages = {
            "zh": "广告轮播系统已启动，正在准备精彩内容...",
            "en": "Advertisement carousel system activated, preparing exciting content..."
        }
        
        # 确保广告目录存在
        self.ads_dir.mkdir(exist_ok=True)
        
        # 扫描可用的广告视频
        self._scan_advertisements()
        
        # 注册工具和资源
        self._register_tools()
        self._register_resources()

    def _scan_advertisements(self):
        """扫描广告目录中的视频文件"""
        self.advertisements.clear()
        
        if not self.ads_dir.exists():
            print(f"Warning: Ads directory {self.ads_dir} does not exist")
            return
        
        ad_count = 0
        for file_path in self.ads_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                try:
                    file_size = file_path.stat().st_size
                    ad_id = f"ad_{ad_count:03d}"
                    
                    ad_info = {
                        "id": ad_id,
                        "name": file_path.stem,
                        "filename": file_path.name,
                        "path": str(file_path),
                        "url_path": f"/ads/{file_path.name}",  # 使用相对路径，自动适应任何域名
                        "size_bytes": file_size,
                        "size_mb": round(file_size / (1024 * 1024), 2),
                        "format": file_path.suffix.lower(),
                        "category": "advertisement"
                    }
                    
                    self.advertisements[ad_id] = ad_info
                    ad_count += 1
                    print(f"Loaded advertisement: {ad_info['name']}")
                    
                except Exception as e:
                    print(f"Error loading advertisement {file_path}: {e}")
        
        self.stats["total_ads"] = len(self.advertisements)
        print(f"Advertisement server initialized: {len(self.advertisements)} ads found")
        
        # 如果没有广告，创建说明文件
        if not self.advertisements:
            self._create_ads_documentation()

    def _create_ads_documentation(self):
        """创建广告系统说明文档"""
        readme_content = """# 🎬 广告轮播系统

## 📂 目录说明
此 `ads/` 文件夹专门用于存放广告轮播视频，与 `videos/` 洗衣机教学视频完全独立。

## 🔄 工作原理
1. **应用启动** → 自动播放广告轮播
2. **用户唤醒** (说"心海"等) → 停止广告，显示VTuber对话
3. **对话进行** → VTuber正常工作，广告隐藏
4. **对话结束** (说"再见"等) → 恢复广告轮播

## 📁 文件夹功能对比
| 文件夹 | 用途 | 控制方式 | 显示时机 |
|--------|------|----------|----------|
| `videos/` | 洗衣机教学视频 | MCP工具调用 | 询问洗衣机使用方法时 |
| `ads/` | 广告轮播视频 | 唤醒状态控制 | 未唤醒待机状态时 |

## 🎥 支持格式
- MP4 (.mp4) - 推荐
- AVI (.avi)
- MOV (.mov)
- WebM (.webm)
- MKV (.mkv)

## 📏 建议规格
- **时长**: 15-60秒
- **分辨率**: 1920x1080 或 1280x720
- **文件大小**: < 50MB
- **编码**: H.264 + AAC

## 📝 命名建议
```
ad_001_品牌介绍.mp4
ad_002_产品展示.mp4
ad_003_特别优惠.mp4
ad_004_用户评价.mp4
```

## 🚀 使用步骤
1. 将广告视频文件放入此文件夹
2. 重启服务器: `python run_server.py`
3. 广告系统会自动扫描并轮播视频

## ⚙️ MCP工具
- `get_advertisement_playlist` - 获取广告播放列表
- `get_next_advertisement` - 获取下一个广告
- `get_current_advertisement` - 获取当前广告
- `refresh_advertisements` - 刷新广告列表
- `get_advertisement_stats` - 获取播放统计
"""
        
        readme_path = self.ads_dir / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        # 创建配置文件
        config_data = {
            "advertisement_settings": {
                "shuffle_mode": True,
                "auto_advance": True,
                "advance_interval_seconds": 15,
                "loop_playlist": True
            },
            "instructions": "将广告视频文件放入此目录，系统会自动检测并播放",
            "supported_formats": list(self.supported_formats)
        }
        
        config_path = self.ads_dir / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        print(f"Created ads documentation: {readme_path}")

    def _register_tools(self):
        """注册MCP工具"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """返回可用的工具列表"""
            return [
                types.Tool(
                    name="get_advertisement_playlist",
                    description="获取完整的广告播放列表",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "shuffle": {
                                "type": "boolean",
                                "description": "是否随机打乱播放列表",
                                "default": True
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_next_advertisement",
                    description="获取下一个广告视频",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "advance": {
                                "type": "boolean", 
                                "description": "是否自动前进到下一个",
                                "default": True
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_current_advertisement",
                    description="获取当前应该播放的广告",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="refresh_advertisements",
                    description="重新扫描广告目录，刷新广告列表",
                    inputSchema={
                        "type": "object", 
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_advertisement_stats",
                    description="获取广告播放统计信息",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="welcome_message",
                    description="获取广告系统欢迎消息",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "language": {
                                "type": "string",
                                "description": "语言代码 (zh/en)",
                                "default": "zh"
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="delete_advertisement",
                    description="删除指定的广告视频文件",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "要删除的广告视频文件名",
                            }
                        },
                        "required": ["filename"]
                    }
                ),
                types.Tool(
                    name="get_advertisement_management_info",
                    description="获取广告管理系统的详细信息和统计数据",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "include_file_details": {
                                "type": "boolean",
                                "description": "是否包含详细的文件信息",
                                "default": True
                            }
                        },
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """处理工具调用"""
            if name == "get_advertisement_playlist":
                return await self._get_advertisement_playlist(arguments)
            elif name == "get_next_advertisement":
                return await self._get_next_advertisement(arguments)
            elif name == "get_current_advertisement":
                return await self._get_current_advertisement(arguments)
            elif name == "refresh_advertisements":
                return await self._refresh_advertisements(arguments)
            elif name == "get_advertisement_stats":
                return await self._get_advertisement_stats(arguments)
            elif name == "welcome_message":
                return await self._welcome_message(arguments)
            elif name == "delete_advertisement":
                return await self._delete_advertisement(arguments)
            elif name == "get_advertisement_management_info":
                return await self._get_advertisement_management_info(arguments)
            else:
                return [types.TextContent(
                    type="text",
                    text=f"Unknown tool: {name}"
                )]

    def _register_resources(self):
        """注册MCP资源"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> list[types.Resource]:
            """返回可用的资源列表"""
            resources = []
            
            for ad_id, ad_info in self.advertisements.items():
                resources.append(types.Resource(
                    uri=AnyUrl(f"ads://advertisement/{ad_id}"),
                    name=f"Advertisement: {ad_info['name']}",
                    description=f"广告视频: {ad_info['filename']} ({ad_info['size_mb']}MB)",
                    mimeType=f"video/{ad_info['format'][1:]}"
                ))
            
            return resources
        
        @self.server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            """读取资源内容"""
            uri_str = str(uri)
            
            if uri_str.startswith("ads://advertisement/"):
                ad_id = uri_str.split("/")[-1]
                
                if ad_id in self.advertisements:
                    ad_info = self.advertisements[ad_id]
                    return json.dumps({
                        "id": ad_id,
                        "name": ad_info["name"],
                        "url_path": ad_info["url_path"],
                        "size_mb": ad_info["size_mb"],
                        "format": ad_info["format"],
                        "description": f"广告视频: {ad_info['name']}"
                    }, ensure_ascii=False)
            
            raise ValueError(f"Unknown resource: {uri}")

    async def _get_advertisement_playlist(self, arguments: dict) -> list[types.TextContent]:
        """获取广告播放列表"""
        shuffle = arguments.get("shuffle", True)
        
        if not self.advertisements:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "advertisement_playlist",
                    "playlist": [],
                    "total_count": 0,
                    "message": "暂无广告内容，请在 ads/ 文件夹中添加视频文件"
                }, ensure_ascii=False)
            )]
        
        playlist = list(self.advertisements.values())
        if shuffle:
            random.shuffle(playlist)
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "advertisement_playlist",
                "playlist": playlist,
                "total_count": len(playlist),
                "shuffle_mode": shuffle,
                "config": self.config
            }, ensure_ascii=False)
        )]

    async def _get_next_advertisement(self, arguments: dict) -> list[types.TextContent]:
        """获取下一个广告"""
        advance = arguments.get("advance", True)
        
        if not self.advertisements:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "advertisement_response",
                    "advertisement": None,
                    "message": "暂无广告内容"
                }, ensure_ascii=False)
            )]
        
        if advance:
            # 自动前进到下一个
            if self.config["shuffle_mode"]:
                self.current_index = random.randint(0, len(self.advertisements) - 1)
            else:
                self.current_index = (self.current_index + 1) % len(self.advertisements)
            
            self.stats["session_plays"] += 1
            self.stats["total_plays"] += 1
        
        current_ad = list(self.advertisements.values())[self.current_index]
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "advertisement_response",
                "advertisement": current_ad,
                "index": self.current_index,
                "total": len(self.advertisements),
                "stats": self.stats
            }, ensure_ascii=False)
        )]

    async def _get_current_advertisement(self, arguments: dict) -> list[types.TextContent]:
        """获取当前广告"""
        if not self.advertisements:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "advertisement_response",
                    "advertisement": None,
                    "message": "暂无广告内容"
                }, ensure_ascii=False)
            )]
        
        current_ad = list(self.advertisements.values())[self.current_index]
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "advertisement_response",
                "advertisement": current_ad,
                "index": self.current_index,
                "total": len(self.advertisements)
            }, ensure_ascii=False)
        )]

    async def _refresh_advertisements(self, arguments: dict) -> list[types.TextContent]:
        """刷新广告列表"""
        old_count = len(self.advertisements)
        self._scan_advertisements()
        new_count = len(self.advertisements)
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "refresh_response",
                "old_count": old_count,
                "new_count": new_count,
                "message": f"广告列表已刷新: {old_count} → {new_count}",
                "advertisements": list(self.advertisements.values())
            }, ensure_ascii=False)
        )]

    async def _get_advertisement_stats(self, arguments: dict) -> list[types.TextContent]:
        """获取统计信息"""
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "stats_response",
                "stats": self.stats,
                "config": self.config,
                "directory": str(self.ads_dir),
                "supported_formats": list(self.supported_formats)
            }, ensure_ascii=False)
        )]

    async def _welcome_message(self, arguments: dict) -> list[types.TextContent]:
        """返回欢迎消息"""
        language = arguments.get("language", "zh")
        message = self.welcome_messages.get(language, self.welcome_messages["zh"])
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "welcome_response",
                "message": message,
                "total_ads": len(self.advertisements),
                "system_ready": True
            }, ensure_ascii=False)
        )]

    async def _delete_advertisement(self, arguments: dict) -> list[types.TextContent]:
        """删除指定的广告视频文件"""
        filename = arguments.get("filename")
        
        if not filename:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error_response",
                    "error": "缺少文件名参数",
                    "success": False
                }, ensure_ascii=False)
            )]
        
        try:
            file_path = self.ads_dir / filename
            
            # 验证文件是否存在
            if not file_path.exists() or not file_path.is_file():
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "type": "error_response",
                        "error": f"文件不存在: {filename}",
                        "success": False
                    }, ensure_ascii=False)
                )]
            
            # 验证文件在ads目录中（安全检查）
            try:
                file_path.resolve().relative_to(self.ads_dir.resolve())
            except ValueError:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "type": "error_response",
                        "error": "非法的文件路径",
                        "success": False
                    }, ensure_ascii=False)
                )]
            
            # 删除文件
            file_path.unlink()
            
            # 重新扫描广告目录
            self._scan_advertisements()
            
            print(f"Successfully deleted advertisement: {filename}")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "delete_response",
                    "message": f"广告视频 '{filename}' 删除成功",
                    "deleted_file": filename,
                    "success": True,
                    "total_ads_remaining": len(self.advertisements)
                }, ensure_ascii=False)
            )]
            
        except Exception as e:
            error_msg = f"删除失败: {str(e)}"
            print(f"Error deleting advertisement: {e}")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error_response",
                    "error": error_msg,
                    "success": False
                }, ensure_ascii=False)
            )]

    async def _get_advertisement_management_info(self, arguments: dict) -> list[types.TextContent]:
        """获取广告管理系统的详细信息和统计数据"""
        include_file_details = arguments.get("include_file_details", True)
        
        try:
            # 基础统计信息
            total_count = len(self.advertisements)
            total_size_bytes = sum(ad_info["size_bytes"] for ad_info in self.advertisements.values())
            total_size_mb = round(total_size_bytes / (1024 * 1024), 2)
            
            # 格式统计
            format_stats = {}
            for ad_info in self.advertisements.values():
                format_type = ad_info["format"]
                format_stats[format_type] = format_stats.get(format_type, 0) + 1
            
            # 构建响应数据
            management_info = {
                "type": "advertisement_management_info",
                "status": "success",
                "statistics": {
                    "total_advertisements": total_count,
                    "total_size_bytes": total_size_bytes,
                    "total_size_mb": total_size_mb,
                    "format_distribution": format_stats,
                    "supported_formats": list(self.supported_formats),
                    "ads_directory": str(self.ads_dir),
                    "current_index": self.current_index,
                    "shuffle_mode": self.config.get("shuffle_mode", True),
                    "auto_advance": self.config.get("auto_advance", True),
                    "advance_interval": self.config.get("advance_interval", 15)
                },
                "session_stats": self.stats.copy(),
                "system_status": {
                    "ads_directory_exists": self.ads_dir.exists(),
                    "ads_directory_writable": self.ads_dir.exists() and 
                                             (self.ads_dir.stat().st_mode & 0o200) != 0,
                    "last_scan_time": "N/A"  # 可以添加时间戳
                }
            }
            
            # 如果需要详细文件信息
            if include_file_details and total_count > 0:
                detailed_files = []
                for ad_id, ad_info in self.advertisements.items():
                    file_detail = {
                        "id": ad_id,
                        "name": ad_info["name"],
                        "filename": ad_info["filename"],
                        "size_bytes": ad_info["size_bytes"],
                        "size_mb": ad_info["size_mb"],
                        "format": ad_info["format"],
                        "url_path": ad_info["url_path"],
                        "category": ad_info["category"],
                        "is_current": self.current_index < len(self.advertisements) and 
                                    list(self.advertisements.keys())[self.current_index] == ad_id
                    }
                    detailed_files.append(file_detail)
                
                management_info["file_details"] = detailed_files
            
            return [types.TextContent(
                type="text",
                text=json.dumps(management_info, ensure_ascii=False, indent=2)
            )]
            
        except Exception as e:
            error_msg = f"获取管理信息失败: {str(e)}"
            print(f"Error getting management info: {e}")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error_response",
                    "error": error_msg,
                    "success": False
                }, ensure_ascii=False)
            )]

    async def run(self):
        """运行服务器"""
        from mcp.server.stdio import stdio_server
        
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="advertisement-server",
                        server_version="1.0.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={}
                        )
                    )
                )
        except (asyncio.CancelledError, KeyboardInterrupt) as e:
            print(f"🛑 Advertisement server stopped: {type(e).__name__}")
        except Exception as e:
            print(f"❌ Advertisement server error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数 - 带有自动重启机制"""
    parser = argparse.ArgumentParser(description="广告轮播管理 MCP 服务器")
    parser.add_argument("--ads-dir", default="ads", help="广告视频目录")
    args = parser.parse_args()
    
    # 自动重启机制
    max_retries = 10
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            print(f"🚀 启动广告MCP服务器 (尝试 {attempt + 1}/{max_retries})")
            server = AdvertisementServer(ads_dir=args.ads_dir)
            await server.run()
            break  # 正常退出，不重启
            
        except (asyncio.CancelledError, KeyboardInterrupt):
            print("🛑 广告MCP服务器被手动停止")
            break
            
        except Exception as e:
            print(f"❌ 广告MCP服务器错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                print(f"⏳ {retry_delay}秒后重试...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)  # 指数退避，最大30秒
            else:
                print("💀 广告MCP服务器重试次数用尽，退出")
                raise


if __name__ == "__main__":
    asyncio.run(main())