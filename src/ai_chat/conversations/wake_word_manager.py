"""
多语言唤醒词管理器 - 优雅的零侵入设计
支持中文、英文、日文唤醒词和结束词
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from loguru import logger
from .types import WebSocketSend


class WakeWordManager:
    """多语言唤醒词管理器 - 独立模块，不依赖其他组件"""
    
    def __init__(self):
        # 多语言唤醒词配置
        self.wake_words = {
            # 中文唤醒词
            "chinese": [
                "艾莉亚", "嘿艾莉亚", "你好艾莉亚", "艾莉亚同学", 
                "艾莉亚酱", "小雅", "小助手", "Aria"
            ],
            # 英文唤醒词  
            "english": [
                "Aria", "Hey Aria", "Hello Aria", "Assistant",
                "Hey assistant", "Computer", "AI"
            ],
            # 日文唤醒词
            "japanese": [
                "こんにちは", "アリア", "アリアちゃん", "アシスタント", "こんにちはアリア",
                "助手", "おーい", "ねえ"
            ]
        }
        
        # 多语言结束词配置
        self.end_words = {
            # 中文结束词
            "chinese": [
                "结束", "再见", "拜拜", "停止", "结束对话", "谢谢",
                "不聊了", "够了", "好了", "结束吧", "下次见"
            ],
            # 英文结束词
            "english": [
                "goodbye", "bye", "end", "stop", "finish", "thanks",
                "that's all", "see you", "later", "quit", "exit"
            ],
            # 日文结束词
            "japanese": [
                "さようなら", "バイバイ", "終わり", "停止", "やめて",
                "ありがとう", "また今度", "じゃあね", "おつかれ", "終了"
            ]
        }
        
        # 客户端状态: client_uid -> 'listening' | 'active'
        self._client_states: Dict[str, str] = {}
        
        # 启用/禁用唤醒词功能
        self.enabled = True
        
        # 统计信息
        self.stats = {
            "wake_count": 0,
            "end_count": 0,
            "ignored_count": 0
        }
        
        # 创建所有唤醒词和结束词的扁平列表
        self._all_wake_words = []
        self._all_end_words = []
        for lang_words in self.wake_words.values():
            self._all_wake_words.extend(lang_words)
        for lang_words in self.end_words.values():
            self._all_end_words.extend(lang_words)
    
    def get_client_state(self, client_uid: str) -> str:
        """获取客户端当前状态"""
        return self._client_states.get(client_uid, 'listening')
    
    def set_client_state(self, client_uid: str, state: str) -> None:
        """设置客户端状态"""
        old_state = self._client_states.get(client_uid, 'listening')
        self._client_states[client_uid] = state
        logger.debug(f"WakeWord: Client {client_uid} state {old_state} -> {state}")
    
    def check_wake_words(self, text: str) -> Optional[Tuple[str, str]]:
        """
        检查文本中是否包含唤醒词
        Returns: (matched_word, language) or None
        """
        text_lower = text.lower()
        
        # 按语言检查唤醒词
        for language, words in self.wake_words.items():
            for word in words:
                # 使用更智能的匹配 - 支持部分匹配和大小写不敏感
                if language == "chinese" or language == "japanese":
                    if word in text:
                        return (word, language)
                else:  # English
                    if word.lower() in text_lower:
                        return (word, language)
        
        return None
    
    def check_end_words(self, text: str) -> Optional[Tuple[str, str]]:
        """
        检查文本中是否包含结束词
        Returns: (matched_word, language) or None
        """
        text_lower = text.lower()
        
        # 按语言检查结束词
        for language, words in self.end_words.items():
            for word in words:
                if language == "chinese" or language == "japanese":
                    if word in text:
                        return (word, language)
                else:  # English
                    if word.lower() in text_lower:
                        return (word, language)
        
        return None
    
    def get_welcome_message(self, wake_word: str, language: str) -> str:
        """根据语言返回适当的欢迎消息"""
        messages = {
            "chinese": f"你好！我是{wake_word.replace('嘿', '').replace('你好', '')}，有什么可以帮你的吗？",
            "english": f"Hello! I'm {wake_word.replace('Hey ', '').replace('Hello ', '')}, how can I help you?",
            "japanese": f"こんにちは！{wake_word.replace('こんにちは', '')}です。何かお手伝いできることはありますか？"
        }
        return messages.get(language, messages["chinese"])
    
    def get_goodbye_message(self, end_word: str, language: str) -> str:
        """根据语言返回适当的告别消息"""
        messages = {
            "chinese": "好的，再见！有需要随时叫我。",
            "english": "Alright, goodbye! Call me anytime you need help.",
            "japanese": "はい、さようなら！何かあったらいつでも呼んでくださいね。"
        }
        return messages.get(language, messages["chinese"])
    
    async def process_transcription(
        self, 
        text: str, 
        client_uid: str, 
        websocket_send: WebSocketSend
    ) -> Tuple[bool, str]:
        """
        处理转录文本，返回是否应该继续对话处理
        
        Returns:
            (should_process: bool, processed_text: str)
        """
        if not self.enabled:
            return True, text
        
        current_state = self.get_client_state(client_uid)
        original_text = text.strip()
        
        # 状态机处理
        if current_state == 'listening':
            # 寻找唤醒词
            wake_result = self.check_wake_words(original_text)
            if wake_result:
                wake_word, language = wake_result
                self.set_client_state(client_uid, 'active')
                self.stats["wake_count"] += 1
                
                await self._send_state_update(
                    client_uid, 'wake_up', wake_word, language, websocket_send
                )
                
                # 如果用户在唤醒词后还说了其他内容，处理剩余部分
                remaining_text = self._extract_remaining_text(original_text, wake_word)
                if remaining_text:
                    logger.info(f"WakeWord: Processing remaining text after wake: '{remaining_text}'")
                    return True, remaining_text
                else:
                    # 只说了唤醒词，返回欢迎消息
                    welcome_msg = self.get_welcome_message(wake_word, language)
                    return True, welcome_msg
            else:
                # 没有唤醒词，忽略
                self.stats["ignored_count"] += 1
                await self._send_state_update(
                    client_uid, 'ignored', original_text[:50] + "..." if len(original_text) > 50 else original_text, 
                    'unknown', websocket_send
                )
                return False, ""
        
        elif current_state == 'active':
            # 已激活，检查结束词
            end_result = self.check_end_words(original_text)
            if end_result:
                end_word, language = end_result
                self.set_client_state(client_uid, 'listening')
                self.stats["end_count"] += 1
                
                await self._send_state_update(
                    client_uid, 'sleep', end_word, language, websocket_send
                )
                
                goodbye_msg = self.get_goodbye_message(end_word, language)
                return True, goodbye_msg
            else:
                # 正常对话
                return True, original_text
        
        return True, original_text
    
    def _extract_remaining_text(self, original_text: str, wake_word: str) -> str:
        """提取唤醒词后的剩余文本"""
        # 简单替换方法，可以根据需要改进
        remaining = original_text.replace(wake_word, "", 1).strip()
        # 清理常见的连接词
        remaining = re.sub(r'^[,，。、\s]+', '', remaining)
        return remaining
    
    async def _send_state_update(
        self, 
        client_uid: str, 
        action: str, 
        matched_word: str,
        language: str,
        websocket_send: WebSocketSend
    ) -> None:
        """发送状态更新到前端"""
        current_state = self.get_client_state(client_uid)
        state_info = {
            "type": "wake-word-state",
            "client_uid": client_uid,
            "action": action,  # 'wake_up', 'sleep', 'ignored'
            "matched_word": matched_word,
            "language": language,
            "current_state": current_state,
            "stats": self.stats.copy(),
            # 🎬 广告轮播控制信号
            "advertisement_control": {
                "should_show_ads": current_state == 'listening',
                "control_action": "start_ads" if current_state == 'listening' else "stop_ads",
                "trigger_reason": action
            }
        }
        
        await websocket_send(json.dumps(state_info))
        
        # 根据动作记录不同级别的日志
        if action == 'wake_up':
            logger.info(f"✨ WakeWord: ACTIVATED by '{matched_word}' ({language}) - Client {client_uid}")
        elif action == 'sleep':
            logger.info(f"💤 WakeWord: DEACTIVATED by '{matched_word}' ({language}) - Client {client_uid}")
        elif action == 'ignored':
            logger.debug(f"🔇 WakeWord: IGNORED '{matched_word}' - Client {client_uid} (listening mode)")
    
    def cleanup_client(self, client_uid: str) -> None:
        """清理客户端状态"""
        if client_uid in self._client_states:
            logger.debug(f"WakeWord: Cleaning up client {client_uid}")
            self._client_states.pop(client_uid, None)
    
    def get_status(self) -> Dict:
        """获取当前状态和统计信息"""
        return {
            "enabled": self.enabled,
            "active_clients": len([s for s in self._client_states.values() if s == 'active']),
            "listening_clients": len([s for s in self._client_states.values() if s == 'listening']),
            "total_clients": len(self._client_states),
            "stats": self.stats.copy(),
            "supported_languages": list(self.wake_words.keys()),
            "wake_words_count": {lang: len(words) for lang, words in self.wake_words.items()},
            "end_words_count": {lang: len(words) for lang, words in self.end_words.items()}
        }
    
    def set_enabled(self, enabled: bool) -> None:
        """启用或禁用唤醒词功能"""
        self.enabled = enabled
        logger.info(f"WakeWord: Feature {'enabled' if enabled else 'disabled'}")
        
        if not enabled:
            # 禁用时将所有客户端设为active状态（允许所有对话）
            for client_uid in self._client_states:
                self._client_states[client_uid] = 'active'


# 全局唤醒词管理器实例
wake_word_manager = WakeWordManager()