"""
洗衣店智能客服处理器
负责处理洗衣店相关的对话和视频播放请求
"""

import json
import re
from typing import Dict, Any, Optional
from loguru import logger


class LaundryHandler:
    """洗衣店智能客服处理器"""
    
    def __init__(self):
        self.enabled = True
        # 从配置文件读取开关
        try:
            import yaml
            from pathlib import Path
            config_path = Path("conf.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                    laundry_cfg = yaml_config.get('system_config', {}).get('laundry_system', {})
                    if isinstance(laundry_cfg.get('enabled'), bool):
                        self.enabled = laundry_cfg['enabled']
        except Exception as _e:
            # 读取失败时保持默认 True，不影响其他功能
            pass
        self.video_base_path = "videos"
        
    def is_laundry_related_query(self, user_input: str) -> bool:
        """
        判断用户输入是否与洗衣店相关
        
        Args:
            user_input: 用户输入的文本
            
        Returns:
            bool: 是否为洗衣店相关查询
        """
        if not user_input or not self.enabled:
            return False
            
        user_input_lower = user_input.lower()
            
        # 洗衣店相关关键词（包含日语关键词）
        # 核心洗衣相关词汇
        core_laundry_keywords = [
            '洗衣机', '洗衣', '洗濯機', '洗濯', 'washing'
        ]
        
        # 操作相关词汇（只有与核心词汇组合时才有效）
        action_keywords = [
            '怎么用', '如何使用', '使用方法', '教程', '操作', '步骤', '流程',
            '使い方', 'やり方', 'チュートリアル', '操作方法', '手順', 'ステップ',
            'how to use', 'how to operate', 'tutorial'
        ]
        
        # 机器编号相关词汇
        machine_keywords = [
            '号机', '台机器', '哪台', '几号',
            '番機', '台目', 'どちら', '何番'
        ]
        
        # 首先检查是否包含核心洗衣关键词
        has_core_keyword = any(keyword in user_input_lower for keyword in core_laundry_keywords)
        
        if has_core_keyword:
            return True
            
        # 检查是否有机器相关词汇与动作词汇的组合
        has_machine_keyword = any(keyword in user_input_lower for keyword in machine_keywords)
        has_action_keyword = any(keyword in user_input_lower for keyword in action_keywords)
        
        if has_machine_keyword and has_action_keyword:
            return True
            
        # 检查英文machine但只有在有数字/字母编号时才算
        if 'machine' in user_input_lower:
            # 检查是否有 machine + 编号的模式
            if re.search(r'machine\s*[A-Z]?\d+', user_input, re.IGNORECASE):
                return True
                
        # 检查是否包含机器编号模式（包含日语模式）
        machine_patterns = [
            # 中文模式 - 要求明确的号台标识
            r'\d+[号台]',
            r'[A-Z]\d*[号台]',  # 移除 ? 使号台成为必需
            r'第\d+台',
            # 日语模式 - 要求明确的番标识
            r'\d+番',
            r'[A-Z]\d*番',     # 保持不变，因为"番"是必需的
            r'\d+台目',
            # 英语模式 - 要求明确的machine标识
            r'no\.\s*[A-Z]?\d+'
        ]
        
        for pattern in machine_patterns:
            if re.search(pattern, user_input, re.IGNORECASE):
                return True
                
        return False
    
    def extract_machine_number(self, user_input: str) -> Optional[str]:
        """
        从用户输入中提取机器编号
        
        Args:
            user_input: 用户输入的文本
            
        Returns:
            Optional[str]: 提取到的机器编号，如果没有则返回None
        """
        if not user_input:
            return None
            
        # 匹配模式（包含日语模式和中文数字）
        patterns = [
            # 中文模式
            r'(\d+)[号台](?:洗衣机|机器)?',
            r'([A-Z]\d*)[号台](?:洗衣机|机器)?',
            r'(?:洗衣机|机器)[号台]?[_-]?([A-Z]?\d+)',
            r'第(\d+)台',
            r'(\d+)号',
            # 中文数字匹配
            r'([一二三四五六七八九十]+)号(?:洗衣机|机器)?',
            r'([一二三四五六七八九十]+)台(?:洗衣机|机器)?',
            # 日语模式
            r'(\d+)番(?:洗濯機|機械)?',
            r'([A-Z]\d*)番(?:洗濯機|機械)?',
            r'(?:洗濯機|機械)(\d+)番?',
            r'(\d+)台目',
            r'([一二三四五六七八九十]+)番(?:目)?',
            # 英语模式
            r'machine[_-]?([A-Z]?\d+)',
            r'no\.?\s*([A-Z]?\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                result = match.group(1)
                # 如果是中文数字，转换为阿拉伯数字
                if any(ch in result for ch in '一二三四五六七八九十'):
                    result = self._chinese_to_arabic(result)
                return str(result).upper()
        
        # 如果找不到明确的编号，尝试提取纯数字或字母
        simple_patterns = [
            r'\b([A-Z]\d+)\b',
            r'\b(\d+)\b'
        ]
        
        for pattern in simple_patterns:
            matches = re.findall(pattern, user_input, re.IGNORECASE)
            if matches:
                return matches[0].upper()
        
        return None
    
    def _chinese_to_arabic(self, chinese_num: str) -> int:
        """将中文数字转换为阿拉伯数字"""
        chinese_digits = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                         '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        
        if chinese_num in chinese_digits:
            return chinese_digits[chinese_num]
        
        # 处理"十一"、"十二"等
        if chinese_num.startswith('十'):
            if len(chinese_num) == 1:
                return 10
            else:
                return 10 + chinese_digits.get(chinese_num[1], 0)
        
        # 处理"二十"、"三十"等
        if chinese_num.endswith('十'):
            if len(chinese_num) == 2:
                return chinese_digits.get(chinese_num[0], 0) * 10
        
        # 处理"二十一"、"三十五"等
        if '十' in chinese_num and len(chinese_num) == 3:
            tens = chinese_digits.get(chinese_num[0], 0) * 10
            ones = chinese_digits.get(chinese_num[2], 0)
            return tens + ones
            
        return 1  # 默认返回1
    
    def format_mcp_tool_call(self, user_input: str, machine_id: Optional[str] = None, language: str = "auto") -> Dict[str, Any]:
        """
        格式化MCP工具调用
        
        Args:
            user_input: 用户输入
            machine_id: 机器编号（如果已提取）
            language: 响应语言模式
            
        Returns:
            Dict: MCP工具调用格式
        """
        if machine_id:
            # 如果有具体的机器编号，调用查询工具
            return {
                "type": "tool_call",
                "tool_name": "query_machine_tutorial",
                "arguments": {
                    "user_input": user_input,
                    "language": language
                }
            }
        else:
            # 如果没有具体编号，可能是询问可用机器（包含日语关键词）
            list_keywords = [
                # 中文
                '有哪些', '有哪几个', '哪几个', '几台', '多少', '几个教程', '教程有哪些', '有哪些教程',
                '哪些', '哪些可以', '能播放的画面', '画面有哪几个', '视频有哪些', '视频有哪几个', '有哪些视频',
                # 日文
                'どちら', '何台', 'いくつ', '一覧', 'リスト', 'いくつある', 'どれがある', 'どの動画', '動画は何個', '何種類',
                # 英文
                'list', 'available', 'which', 'what are available'
            ]
            if any(keyword in user_input.lower() for keyword in list_keywords):
                return {
                    "type": "tool_call", 
                    "tool_name": "list_available_machines",
                    "arguments": {}
                }
            else:
                # 默认查询处理
                return {
                    "type": "tool_call",
                    "tool_name": "query_machine_tutorial", 
                    "arguments": {
                        "user_input": user_input,
                        "language": language
                    }
                }
    
    def process_mcp_tool_result(self, tool_result: str) -> Dict[str, Any]:
        """
        处理MCP工具的返回结果
        
        Args:
            tool_result: MCP工具返回的JSON字符串
            
        Returns:
            Dict: 处理后的结果
        """
        try:
            result_data = json.loads(tool_result)
            
            if result_data.get("type") == "video_response":
                # 视频响应（移除静默模式与口头文本返回，前端负责抑制TTS）
                return {
                    "type": "laundry-video-response",
                    "machine_id": result_data.get("machine_id"),
                    "video_path": result_data.get("video_path"),
                    "video_name": result_data.get("video_name", "使用方法チュートリアル"),
                    "auto_close": result_data.get("auto_close", True)
                }
            else:
                # 文本响应
                return {
                    "type": "laundry_text_response",
                    "content": result_data.get("content", ""),
                    "available_machines": result_data.get("available_machines", []),
                    "machines": result_data.get("machines", [])
                }
                
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"处理MCP工具结果时出错: {e}")
            return {
                "type": "laundry_error_response",
                "content": "申し訳ございません。リクエストの処理中にエラーが発生しました。もう一度お試しください。"
            }
    
    def generate_welcome_message(self) -> str:
        """
        生成欢迎消息
        
        Returns:
            str: 欢迎消息
        """
        return "セルフランドリーへようこそ！私はスマートアシスタントです。各種洗濯機の使用方法をご案内いたします。どちらの洗濯機の使用方法をお知りになりたいですか？"
    
    def detect_language_mode(self, user_input: str = "", system_config: Optional[Dict] = None) -> str:
        """
        检测应该使用的语言模式
        
        Args:
            user_input: 用户输入文本
            system_config: 系统配置
            
        Returns:
            str: 语言模式 ('auto', 'zh', 'ja', 'en')
        """
        # 首先尝试从YAML配置读取（不再支持静默模式）
        try:
            import yaml
            from pathlib import Path
            
            config_path = Path("conf.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                    laundry_config = yaml_config.get('system_config', {}).get('laundry_system', {})
                    configured_mode = laundry_config.get('language_mode', 'auto')
                    
                    # 如果配置了具体语言模式，则返回该模式
                    if configured_mode in ["zh", "ja", "en"]:
                        return configured_mode
        except Exception as e:
            print(f"Warning: Could not read laundry language config: {e}")
        
        # 如果系统配置传入了特定模式，使用系统配置
        if system_config and system_config.get("laundry_language_mode"):
            return system_config["laundry_language_mode"]
        
        # 基于用户输入检测语言
        if user_input:
            # 检测日语字符 - 包括平假名、片假名、日语汉字和日语表达
            japanese_chars = ['の', 'を', 'に', 'は', 'が', 'と', 'で', 'から', 'まで', 'する', 'です', 'だ']
            japanese_words = ['番', '洗濯機', '機械', '使い方', 'マシン', 'みて', 'どう', 'どうやって', '教えて', 'ください']
            
            # 检查平假名范围 (ひらがな)
            has_hiragana = any('\u3040' <= char <= '\u309F' for char in user_input)
            # 检查片假名范围 (カタカナ)
            has_katakana = any('\u30A0' <= char <= '\u30FF' for char in user_input)
            # 检查日语助词和单词
            has_japanese_words = any(char in user_input for char in japanese_chars) or \
                                any(word in user_input for word in japanese_words)
            
            if has_hiragana or has_katakana or has_japanese_words:
                return "ja"
            
            # 检测英语
            if any(word in user_input.lower() for word in ['machine', 'washing', 'how', 'use', 'tutorial']):
                return "en"
        
        # 默认自动模式，但倾向于保持系统原有语言
        return "auto"
    
    def generate_fallback_response(self, user_input: str) -> str:
        """
        生成兜底回复
        
        Args:
            user_input: 用户输入
            
        Returns:
            str: 兜底回复
        """
        return f"申し訳ございません。ご質問の内容がわかりませんでした：'{user_input}'。どちらの洗濯機の使用方法をお知りになりたいか教えてください。例：'1番洗濯機の使い方'"


# 全局实例
laundry_handler = LaundryHandler()