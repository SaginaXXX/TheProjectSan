#!/usr/bin/env python3
"""
主题介绍管理 MCP 服务器
提供主题介绍数据管理功能，支持多语言和多租户
"""

import json
import re
import sys
import asyncio
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

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
        elif directory_type == 'topics':
            return Path("topics")
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


def detect_language_simple(text: str) -> str:
    """简单的语言检测（用于MCP服务器）"""
    try:
        from langdetect import detect
        return detect(text)
    except:
        # 如果langdetect不可用，使用简单规则
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            return 'zh'
        elif any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in text):
            return 'ja'
        else:
            return 'en'


class TopicIntroductionServer:
    """主题介绍管理服务器"""
    
    def __init__(self, topics_dir: str = "topics", client_id: str = None):
        self.server = Server("topic-introduction-server")
        
        # 获取媒体配置
        self.media_config = get_media_config()
        
        # 获取CLIENT_ID
        import os
        self.client_id = client_id or os.getenv('CLIENT_ID') or getattr(self.media_config, 'client_id', 'default_client')
        
        try:
            base_topics_dir = self.media_config.get_directory_path('topics')
            # 如果是多租户模式，添加CLIENT_ID子目录
            self.topics_dir = base_topics_dir / self.client_id
        except:
            # Fallback to provided directory
            self.topics_dir = Path(topics_dir) / self.client_id
        
        self.topics = {}
        self.supported_image_formats = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        self.supported_video_formats = {'.mp4', '.avi', '.mov', '.webm', '.mkv'}
        
        # 确保主题目录存在
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载所有主题
        self._load_topics()
        
        # 注册工具和资源
        self._register_tools()
        self._register_resources()
    
    def _load_topics(self):
        """加载所有主题数据"""
        self.topics.clear()
        
        if not self.topics_dir.exists():
            print(f"⚠️ Warning: Topics directory {self.topics_dir} does not exist for CLIENT {self.client_id}")
            self.topics_dir.mkdir(parents=True, exist_ok=True)
            return
        
        print(f"📁 扫描主题目录: {self.topics_dir} (CLIENT_ID: {self.client_id})")
        
        # 扫描所有主题目录
        for topic_dir in self.topics_dir.iterdir():
            if not topic_dir.is_dir():
                continue
            
            topic_json_path = topic_dir / "topic.json"
            if not topic_json_path.exists():
                continue
            
            try:
                with open(topic_json_path, 'r', encoding='utf-8') as f:
                    topic_data = json.load(f)
                
                topic_id = topic_data.get('topic_id', topic_dir.name)
                self.topics[topic_id] = topic_data
                topic_name = topic_data.get('name', 'Unknown')
                topic_lang = topic_data.get('language', 'ja')
                print(f"✅ [{self.client_id}] 加载主题: {topic_name} (language: {topic_lang})")
                
            except Exception as e:
                print(f"❌ Error loading topic {topic_dir.name}: {e}")
        
        print(f"\n📚 主题服务器初始化完成: {len(self.topics)} 个主题已加载")
    
    def _get_topic_by_name(self, topic_name: str) -> Optional[Dict[str, Any]]:
        """根据主题名称查找主题（支持多语言模糊匹配）"""
        if not topic_name:
            return None
        
        topic_name_lower = topic_name.lower().strip()
        candidates = []
        
        # 提取关键词（支持多语言：中文、日语、英语、韩语、西班牙语、法语等）
        def extract_keywords(text):
            keywords = []
            
            # 1. 提取中文字符（连续的中文字符）
            chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
            keywords.extend(chinese_chars)
            
            # 2. 提取日文字符（平假名和片假名）
            japanese_chars = re.findall(r'[\u3040-\u309f\u30a0-\u30ff]+', text)
            keywords.extend(japanese_chars)
            
            # 3. 提取韩语字符（韩文字符）
            korean_chars = re.findall(r'[\uac00-\ud7a3]+', text)
            keywords.extend(korean_chars)
            
            # 4. 提取泰语字符
            thai_chars = re.findall(r'[\u0e00-\u0e7f]+', text)
            keywords.extend(thai_chars)
            
            # 5. 提取阿拉伯语字符
            arabic_chars = re.findall(r'[\u0600-\u06ff]+', text)
            keywords.extend(arabic_chars)
            
            # 6. 提取俄语字符（西里尔字母）
            russian_chars = re.findall(r'[\u0400-\u04ff]+', text)
            keywords.extend(russian_chars)
            
            # 7. 提取拉丁语系单词（英语、西班牙语、法语、德语、意大利语等）
            # 匹配带重音符号的拉丁字母
            latin_words = re.findall(r'[a-zA-Z\u00c0-\u017f]{2,}', text)
            # 转换为小写并过滤常见停用词（多语言停用词）
            stop_words = {
                # 英语
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 
                'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
                # 西班牙语
                'el', 'la', 'los', 'las', 'un', 'una', 'y', 'o', 'pero', 'en', 'de', 'con', 'por', 'para',
                'es', 'son', 'fue', 'fueron', 'ser', 'estar', 'tener', 'hacer',
                # 法语
                'le', 'la', 'les', 'un', 'une', 'et', 'ou', 'mais', 'dans', 'de', 'avec', 'pour',
                'est', 'sont', 'était', 'étaient', 'être', 'avoir', 'faire',
                # 德语
                'der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'aber', 'in', 'von', 'mit', 'für',
                'ist', 'sind', 'war', 'waren', 'sein', 'haben', 'machen',
                # 意大利语
                'il', 'la', 'lo', 'gli', 'le', 'un', 'una', 'e', 'o', 'ma', 'in', 'di', 'con', 'per',
                'è', 'sono', 'era', 'erano', 'essere', 'avere', 'fare',
                # 通用词汇
                'hotel', 'theme', 'topic', 'the', 'topic', 'theme'
            }
            latin_words = [w.lower() for w in latin_words if w.lower() not in stop_words and len(w) >= 3]
            keywords.extend(latin_words)
            
            # 8. 如果关键词为空，尝试提取所有非ASCII字符作为关键词（处理其他小语种）
            if not keywords:
                # 提取所有非ASCII、非标点的连续字符
                non_ascii_words = re.findall(r'[^\x00-\x7f\s\-_\.，。、]+', text)
                if non_ascii_words:
                    keywords.extend(non_ascii_words)
                else:
                    # 如果还是没有，返回原始文本（去除标点后，转为小写）
                    text_clean = re.sub(r'[\s\-_\.，。、]+', '', text).lower()
                    if text_clean:
                        keywords.append(text_clean)
            
            return keywords
        
        topic_keywords = extract_keywords(topic_name_lower)
        
        for topic in self.topics.values():
            name = topic.get('name', '')
            if not name:
                continue
            
            name_lower = name.lower().strip()
            
            # 1. 精确匹配（不区分大小写）
            if name_lower == topic_name_lower:
                return topic
            
            # 2. 包含匹配（topic_name包含在name中，或name包含在topic_name中）
            if topic_name_lower in name_lower or name_lower in topic_name_lower:
                candidates.append((topic, 1))  # 高优先级
                continue
            
            # 3. 关键词匹配（提取的关键词有重叠，支持跨语言）
            name_keywords = extract_keywords(name_lower)
            if topic_keywords and name_keywords:
                # 检查关键词重叠（直接匹配）
                common_keywords = set(topic_keywords) & set(name_keywords)
                
                # 如果直接匹配失败，尝试跨语言匹配（适用于不同语言但意思相同的情况）
                if not common_keywords:
                    # 跨语言匹配策略：
                    # 1. 检查关键词数量相似性（如果关键词数量相近，可能是翻译对等）
                    keyword_count_ratio = min(len(topic_keywords), len(name_keywords)) / max(len(topic_keywords), len(name_keywords))
                    
                    # 2. 检查关键词字符串的字符重叠度（适用于同源词或音译词）
                    topic_keywords_str = ''.join(topic_keywords)
                    name_keywords_str = ''.join(name_keywords)
                    char_overlap = 0.0
                    if topic_keywords_str and name_keywords_str:
                        topic_chars = set(topic_keywords_str.lower())
                        name_chars = set(name_keywords_str.lower())
                        common_chars = topic_chars & name_chars
                        if topic_chars and name_chars:
                            char_overlap = len(common_chars) / max(len(topic_chars), len(name_chars))
                    
                    # 3. 检查关键词长度相似性
                    if topic_keywords and name_keywords:
                        avg_topic_len = sum(len(k) for k in topic_keywords) / len(topic_keywords)
                        avg_name_len = sum(len(k) for k in name_keywords) / len(name_keywords)
                        len_ratio = min(avg_topic_len, avg_name_len) / max(avg_topic_len, avg_name_len) if max(avg_topic_len, avg_name_len) > 0 else 0
                    else:
                        len_ratio = 0
                    
                    # 综合评分：如果多个指标都较高，可能是跨语言匹配
                    cross_lang_score = (keyword_count_ratio * 0.3 + char_overlap * 0.4 + len_ratio * 0.3)
                    if cross_lang_score >= 0.35:  # 综合评分超过35%，认为是跨语言匹配
                        common_keywords = {'_cross_lang_match'}  # 标记为跨语言匹配
                
                if common_keywords:
                    # 计算关键词匹配度
                    if '_cross_lang_match' in common_keywords:
                        # 跨语言匹配，优先级较低但可接受
                        keyword_similarity = 0.4
                        candidates.append((topic, 2.5 + (1 - keyword_similarity)))
                    else:
                        keyword_similarity = len(common_keywords) / max(len(topic_keywords), len(name_keywords))
                        if keyword_similarity >= 0.3:  # 降低阈值到30%，提高匹配成功率
                            candidates.append((topic, 2 + (1 - keyword_similarity)))  # 匹配度越高，优先级数字越小
                    continue
            
            # 4. 部分匹配（去除空格和标点后的匹配）
            name_clean = re.sub(r'[\s\-_\.]+', '', name_lower)
            topic_name_clean = re.sub(r'[\s\-_\.]+', '', topic_name_lower)
            if name_clean == topic_name_clean:
                candidates.append((topic, 3))  # 中优先级
                continue
            
            # 5. 字符相似度匹配（简单的字符重叠检查）
            name_chars = set(name_lower)
            topic_name_chars = set(topic_name_lower)
            if name_chars and topic_name_chars:
                common_chars = name_chars & topic_name_chars
                similarity = len(common_chars) / max(len(name_chars), len(topic_name_chars))
                # 如果相似度超过50%，认为是可能的匹配
                if similarity >= 0.5:
                    candidates.append((topic, 4 + (1 - similarity)))  # 相似度越低，优先级数字越大
        
        # 如果有候选，返回优先级最高的（数字最小的）
        if candidates:
            # 按优先级排序：优先级数字越小越好
            candidates.sort(key=lambda x: x[1] if isinstance(x[1], (int, float)) else 999)
            best_match = candidates[0][0]
            matched_name = best_match.get('name', '')
            print(f"🔍 主题名称模糊匹配: '{topic_name}' -> '{matched_name}' (优先级: {candidates[0][1]:.2f})")
            return best_match
        
        return None
    
    def _get_content(self, content: Any) -> str:
        """获取内容（简化版本，直接返回字符串）"""
        # 直接返回字符串内容，不做翻译
        # AI会根据target_language参数自动翻译
        if isinstance(content, str):
            return content
        return str(content)
    
    def _register_tools(self):
        """注册MCP工具"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """返回可用的工具列表"""
            return [
                types.Tool(
                    name="get_topic_list",
                    description="获取所有主题列表",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "target_language": {
                                "type": "string",
                                "description": "目标语言代码 (ja/en/zh等)，可选",
                                "default": None
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_topic_info",
                    description="获取主题详细信息（名称、描述等）。注意：如果主题有图片或视频，请使用get_topic_image和get_topic_video工具来显示，不要直接说出URL。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic_name": {
                                "type": "string",
                                "description": "主题名称（支持多语言）"
                            },
                            "target_language": {
                                "type": "string",
                                "description": "目标语言代码 (ja/en/zh等)，可选"
                            }
                        },
                        "required": ["topic_name"]
                    }
                ),
                types.Tool(
                    name="get_topic_video",
                    description="获取主题的指定视频并在第二画布上播放。返回视频URL（仅用于前端显示，AI不应说出URL）。AI应保持静音，只介绍视频内容描述，绝对不要说出或提及任何URL、链接或地址。当用户询问主题的视频时，应自动调用此工具。主题名称支持多语言模糊匹配。**重要：如果用户请求'所有视频'或'主题的视频'（未指定具体索引），必须按顺序调用此工具多次，从video_index=0开始，每次递增1，直到显示完所有视频。每次调用后等待视频播放完成再调用下一个。**",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic_name": {
                                "type": "string",
                                "description": "主题名称（支持多语言模糊匹配，如：'夏日忍者酒店'、'夏日忍者ホテル'、'Summer Ninja Hotel'等）"
                            },
                            "video_index": {
                                "type": "integer",
                                "description": "视频索引（从0开始，默认0）。如果用户请求所有视频，必须从0开始按顺序调用，每次递增1",
                                "default": 0
                            },
                            "target_language": {
                                "type": "string",
                                "description": "目标语言代码 (ja/en/zh等)，可选"
                            }
                        },
                        "required": ["topic_name"]
                    }
                ),
                types.Tool(
                    name="get_topic_image",
                    description="获取主题的指定图片并显示在第二画布上。返回图片URL（仅用于前端显示，AI不应说出URL）和描述。AI应说话介绍图片内容描述，绝对不要说出或提及任何URL、链接或地址。当用户询问主题的图片时，应自动调用此工具。主题名称支持多语言模糊匹配。**重要：如果用户请求'所有图片'或'主题的图片'（未指定具体索引），必须按顺序调用此工具多次，从image_index=0开始，每次递增1，直到显示完所有图片。每次调用后等待图片显示完成再调用下一个。**",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic_name": {
                                "type": "string",
                                "description": "主题名称（支持多语言模糊匹配，如：'夏日忍者酒店'、'夏日忍者ホテル'、'Summer Ninja Hotel'等）"
                            },
                            "image_index": {
                                "type": "integer",
                                "description": "图片索引（从0开始，默认0）。如果用户请求所有图片，必须从0开始按顺序调用，每次递增1",
                                "default": 0
                            },
                            "target_language": {
                                "type": "string",
                                "description": "目标语言代码 (ja/en/zh等)，可选"
                            }
                        },
                        "required": ["topic_name"]
                    }
                ),
                types.Tool(
                    name="search_topics",
                    description="根据关键词搜索主题",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "target_language": {
                                "type": "string",
                                "description": "目标语言代码 (ja/en/zh等)，可选"
                            }
                        },
                        "required": ["keyword"]
                    }
                ),
                types.Tool(
                    name="refresh_topics",
                    description="重新扫描主题目录，刷新主题列表（用户上传新主题后自动调用）",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent]:
            """处理工具调用"""
            if name == "get_topic_list":
                return await self._get_topic_list(arguments)
            elif name == "get_topic_info":
                return await self._get_topic_info(arguments)
            elif name == "get_topic_video":
                return await self._get_topic_video(arguments)
            elif name == "get_topic_image":
                return await self._get_topic_image(arguments)
            elif name == "search_topics":
                return await self._search_topics(arguments)
            elif name == "refresh_topics":
                return await self._refresh_topics(arguments)
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
            
            for topic_id, topic_data in self.topics.items():
                topic_name = self._get_localized_content(topic_data.get('name', {}))
                resources.append(types.Resource(
                    uri=AnyUrl(f"topic://introduction/{topic_id}"),
                    name=f"Topic: {topic_name}",
                    description=f"主题介绍: {topic_name}",
                    mimeType="application/json"
                ))
            
            return resources
    
    async def _get_topic_list(self, arguments: dict) -> list[types.TextContent]:
        """获取所有主题列表"""
        target_language = arguments.get("target_language")
        
        topic_list = []
        for topic_id, topic_data in self.topics.items():
            name = self._get_content(topic_data.get('name', ''))
            description = self._get_content(topic_data.get('description', ''))
            
            # 截断长描述
            if len(description) > 100:
                description = description[:100] + "..."
            
            topic_info = {
                "topic_id": topic_id,
                "name": name,
                "description": description,
                "language": topic_data.get('language', 'ja'),
                "image_count": len(topic_data.get('images', [])),
                "video_count": len(topic_data.get('videos', [])),
                "target_language": target_language  # 传递给AI作为翻译提示
            }
            topic_list.append(topic_info)
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "topic_list",
                "topics": topic_list,
                "total_count": len(topic_list),
                "target_language": target_language
            }, ensure_ascii=False)
        )]
    
    async def _get_topic_info(self, arguments: dict) -> list[types.TextContent]:
        """获取主题详细信息"""
        topic_name = arguments.get("topic_name")
        target_language = arguments.get("target_language")
        
        topic = self._get_topic_by_name(topic_name)
        if not topic:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"未找到主题: {topic_name}"
                }, ensure_ascii=False)
            )]
        
        # 构建响应数据（保留原始语言，AI会自动翻译）
        response_data = {
            "type": "topic_info",
            "topic_id": topic.get('topic_id'),
            "name": self._get_content(topic.get('name', '')),
            "description": self._get_content(topic.get('description', '')),
            "language": topic.get('language', 'ja'),
            "target_language": target_language,  # 传递给AI作为翻译提示
            "images": [],
            "videos": []
        }
        
        # 处理图片（只返回数量和提示，不返回URL）
        image_count = len(topic.get('images', []))
        if image_count > 0:
            response_data["images"] = {
                "count": image_count,
                "hint": f"该主题有{image_count}张图片。如果用户请求所有图片，必须按顺序调用get_topic_image工具{image_count}次，从image_index=0开始，每次递增1，直到显示完所有图片。每次调用后等待图片显示完成再调用下一个。"
            }
        
        # 处理视频（只返回数量和提示，不返回URL）
        video_count = len(topic.get('videos', []))
        if video_count > 0:
            response_data["videos"] = {
                "count": video_count,
                "hint": f"该主题有{video_count}个视频。如果用户请求所有视频，必须按顺序调用get_topic_video工具{video_count}次，从video_index=0开始，每次递增1，直到播放完所有视频。每次调用后等待视频播放完成再调用下一个。"
            }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response_data, ensure_ascii=False)
        )]
    
    async def _get_topic_video(self, arguments: dict) -> list[types.TextContent]:
        """获取主题的指定视频"""
        topic_name = arguments.get("topic_name")
        video_index = arguments.get("video_index", 0)
        target_language = arguments.get("target_language")
        
        topic = self._get_topic_by_name(topic_name)
        if not topic:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"未找到主题: {topic_name}"
                }, ensure_ascii=False)
            )]
        
        videos = topic.get('videos', [])
        if not videos:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"主题 '{topic_name}' 没有视频"
                }, ensure_ascii=False)
            )]
        
        if video_index >= len(videos):
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"视频索引 {video_index} 超出范围（共 {len(videos)} 个视频）"
                }, ensure_ascii=False)
            )]
        
        video = videos[video_index]
        # 生成完整的视频URL
        url_path = video.get('url_path', '')
        if url_path.startswith('/'):
            url_path = url_path[1:]
        video_url = f"http://{self.media_config.host}:{self.media_config.port}/{url_path}"
        
        # 检查是否还有更多视频
        total_videos = len(videos)
        has_more = video_index < total_videos - 1
        next_index = video_index + 1 if has_more else None
        
        # 返回视频信息，格式化为前端可用的格式
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "video",
                "url": video_url,
                "description": self._get_content(video.get('description', '')),
                "filename": video.get('filename'),
                "topic_name": self._get_content(topic.get('name', '')),
                "language": topic.get('language', 'ja'),
                "target_language": target_language,  # 传递给AI作为翻译提示
                "video_index": video_index,
                "total_videos": total_videos,
                "has_more": has_more,
                "next_index": next_index,
                "hint": f"这是第{video_index + 1}个视频（共{total_videos}个）。{'还有更多视频，请继续调用get_topic_video工具，video_index=' + str(next_index) if has_more else '所有视频已显示完毕。'}"
            }, ensure_ascii=False)
        )]
    
    async def _get_topic_image(self, arguments: dict) -> list[types.TextContent | types.ImageContent]:
        """获取主题的指定图片"""
        topic_name = arguments.get("topic_name")
        image_index = arguments.get("image_index", 0)
        target_language = arguments.get("target_language")
        
        topic = self._get_topic_by_name(topic_name)
        if not topic:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"未找到主题: {topic_name}"
                }, ensure_ascii=False)
            )]
        
        images = topic.get('images', [])
        if not images:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"主题 '{topic_name}' 没有图片"
                }, ensure_ascii=False)
            )]
        
        if image_index >= len(images):
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": f"图片索引 {image_index} 超出范围（共 {len(images)} 张图片）"
                }, ensure_ascii=False)
            )]
        
        image = images[image_index]
        # 生成完整的图片URL
        url_path = image.get('url_path', '')
        if url_path.startswith('/'):
            url_path = url_path[1:]
        image_url = f"http://{self.media_config.host}:{self.media_config.port}/{url_path}"
        
        # 检查是否还有更多图片
        total_images = len(images)
        has_more = image_index < total_images - 1
        next_index = image_index + 1 if has_more else None
        
        # 返回图片信息，格式化为前端可用的格式
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "image",
                "url": image_url,
                "description": self._get_content(image.get('description', '')),
                "filename": image.get('filename'),
                "topic_name": self._get_content(topic.get('name', '')),
                "language": topic.get('language', 'ja'),
                "target_language": target_language,  # 传递给AI作为翻译提示
                "image_index": image_index,
                "total_images": total_images,
                "has_more": has_more,
                "next_index": next_index,
                "hint": f"这是第{image_index + 1}张图片（共{total_images}张）。{'还有更多图片，请继续调用get_topic_image工具，image_index=' + str(next_index) if has_more else '所有图片已显示完毕。'}"
            }, ensure_ascii=False)
        )]
    
    async def _search_topics(self, arguments: dict) -> list[types.TextContent]:
        """根据关键词搜索主题"""
        keyword = arguments.get("keyword", "").lower()
        target_language = arguments.get("target_language")
        
        if not keyword:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "type": "error",
                    "message": "搜索关键词不能为空"
                }, ensure_ascii=False)
            )]
        
        matched_topics = []
        for topic_id, topic_data in self.topics.items():
            # 搜索主题名称（简单字符串）
            name = self._get_content(topic_data.get('name', ''))
            description = self._get_content(topic_data.get('description', ''))
            
            if keyword in name.lower() or keyword in description.lower():
                # 截断长描述
                desc_preview = description[:100] + "..." if len(description) > 100 else description
                
                matched_topics.append({
                    "topic_id": topic_id,
                    "name": name,
                    "description": desc_preview,
                    "language": topic_data.get('language', 'ja')
                })
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "search_results",
                "keyword": keyword,
                "topics": matched_topics,
                "total_count": len(matched_topics),
                "target_language": target_language  # 传递给AI作为翻译提示
            }, ensure_ascii=False)
        )]
    
    async def _refresh_topics(self, arguments: dict) -> list[types.TextContent]:
        """刷新主题列表（重新扫描目录）"""
        old_count = len(self.topics)
        self._load_topics()
        new_count = len(self.topics)
        
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "type": "refresh_response",
                "old_count": old_count,
                "new_count": new_count,
                "message": f"主题列表已刷新: {old_count} → {new_count}",
                "topics": list(self.topics.values())
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
                        server_name="topic-introduction-server",
                        server_version="1.0.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={}
                        )
                    )
                )
        except (asyncio.CancelledError, KeyboardInterrupt) as e:
            print(f"🛑 Topic introduction server stopped: {type(e).__name__}")
        except Exception as e:
            print(f"❌ Topic introduction server error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数 - 带有自动重启机制"""
    parser = argparse.ArgumentParser(description="主题介绍MCP服务器")
    parser.add_argument("--topics-dir", type=str, default="topics", help="主题目录路径")
    parser.add_argument("--client-id", type=str, default=None, help="客户ID")
    args = parser.parse_args()
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            server = TopicIntroductionServer(topics_dir=args.topics_dir, client_id=args.client_id)
            print(f"🚀 主题介绍MCP服务器已启动 (CLIENT_ID: {server.client_id})")
            await server.run()
            break  # 正常退出，不重试
        except (asyncio.CancelledError, KeyboardInterrupt):
            print("🛑 服务器被用户中断")
            break  # 用户中断，不重试
        except Exception as e:
            retry_count += 1
            print(f"❌ 服务器崩溃 (尝试 {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                print(f"⏳ 等待 3 秒后重启...")
                await asyncio.sleep(3)
            else:
                print("❌ 达到最大重试次数，服务器停止")
                raise


if __name__ == "__main__":
    asyncio.run(main())

