"""
自适应VAD系统 - 支持在播放广告音频时进行语音检测
根据环境噪音动态调整检测阈值        
"""
import numpy as np
from typing import Optional, Tuple
from loguru import logger
from .silero import VADEngine, SileroVADConfig


class AdaptiveVADConfig(SileroVADConfig):
    """自适应VAD配置"""
    # 提高默认阈值，减少广告音对唤醒的干扰
    base_prob_threshold: float = 0.55  # 基础概率阈值（原 0.4）
    base_db_threshold: int = 65        # 基础分贝阈值（原 60）
    adaptive_factor: float = 1.5       # 自适应因子
    noise_measurement_window: int = 50 # 噪音测量窗口
    min_threshold_ratio: float = 0.7   # 最小阈值比例
    max_threshold_ratio: float = 2.0   # 最大阈值比例


class AdaptiveVADEngine(VADEngine):
    """自适应VAD引擎 - 可以在有背景音的情况下检测语音"""
    
    def __init__(self, config: Optional[AdaptiveVADConfig] = None):
        if config is None:
            config = AdaptiveVADConfig()
        
        super().__init__(
            orig_sr=config.orig_sr,
            target_sr=config.target_sr,
            prob_threshold=config.base_prob_threshold,
            db_threshold=config.base_db_threshold,
            required_hits=config.required_hits,
            required_misses=config.required_misses,
            smoothing_window=config.smoothing_window
        )
        
        self.adaptive_config = config
        self.background_noise_level = 0.0
        self.noise_samples = []
        self.is_ad_playing = False
        
        logger.info(f"AdaptiveVAD initialized with adaptive_factor={config.adaptive_factor}")
    
    def set_advertisement_status(self, is_playing: bool, volume_level: float = 0.5):
        """
        设置广告播放状态
        
        Args:
            is_playing: 是否正在播放广告
            volume_level: 广告音量级别 (0.0-1.0)
        """
        self.is_ad_playing = is_playing
        
        if is_playing:
            # 根据广告音量动态调整阈值
            volume_factor = 1.0 + (volume_level * self.adaptive_config.adaptive_factor)
            
            # 调整概率阈值
            new_prob_threshold = min(
                self.adaptive_config.base_prob_threshold * volume_factor,
                self.adaptive_config.base_prob_threshold * self.adaptive_config.max_threshold_ratio
            )
            new_prob_threshold = max(
                new_prob_threshold,
                self.adaptive_config.base_prob_threshold * self.adaptive_config.min_threshold_ratio
            )
            
            # 调整分贝阈值
            # 更保守的分贝补偿，避免过度抬高导致漏检
            db_adjustment = volume_level * 15
            new_db_threshold = min(
                self.adaptive_config.base_db_threshold + db_adjustment,
                self.adaptive_config.base_db_threshold * self.adaptive_config.max_threshold_ratio
            )
            
            self.config.prob_threshold = new_prob_threshold
            self.config.db_threshold = int(new_db_threshold)
            # 同步到运行中的状态机阈值，确保即时生效
            if hasattr(self, "state") and self.state is not None:
                self.state.prob_threshold = new_prob_threshold
                self.state.db_threshold = int(new_db_threshold)
            
            logger.info(
                f"🎵 广告播放中 - VAD阈值自适应调整: "
                f"prob_threshold={new_prob_threshold:.2f}, db_threshold={new_db_threshold:.0f}"
            )
        else:
            # 恢复原始阈值
            self.config.prob_threshold = self.adaptive_config.base_prob_threshold
            self.config.db_threshold = self.adaptive_config.base_db_threshold
            if hasattr(self, "state") and self.state is not None:
                self.state.prob_threshold = self.adaptive_config.base_prob_threshold
                self.state.db_threshold = self.adaptive_config.base_db_threshold
            
            logger.info("🔇 广告停止 - VAD阈值恢复默认值")
    
    def update_noise_level(self, audio_chunk: np.ndarray):
        """
        更新背景噪音级别
        
        Args:
            audio_chunk: 音频数据块
        """
        # 计算当前块的能量
        rms = np.sqrt(np.mean(np.square(audio_chunk)))
        db_level = 20 * np.log10(rms + 1e-7) if rms > 0 else -np.inf
        
        # 维护噪音样本窗口
        self.noise_samples.append(db_level)
        if len(self.noise_samples) > self.adaptive_config.noise_measurement_window:
            self.noise_samples.pop(0)
        
        # 计算平均背景噪音级别
        if self.noise_samples:
            self.background_noise_level = np.mean(self.noise_samples)
    
    def detect_speech_adaptive(self, audio_data: list[float]):
        """
        自适应语音检测 - 考虑背景噪音和广告播放状态
        
        Args:
            audio_data: 音频数据
            
        Yields:
            audio_chunk: 检测到的语音块
        """
        audio_np = np.array(audio_data, dtype=np.float32)
        
        # 更新噪音级别
        self.update_noise_level(audio_np)
        
        # 如果正在播放广告，进行额外的噪音抑制
        if self.is_ad_playing:
            audio_np = self._apply_noise_suppression(audio_np)
        
        # 使用原有的检测逻辑
        yield from self.detect_speech(audio_data)
    
    def _apply_noise_suppression(self, audio_np: np.ndarray) -> np.ndarray:
        """
        应用简单的噪音抑制
        
        Args:
            audio_np: 原始音频数据
            
        Returns:
            处理后的音频数据
        """
        # 简单的谱减法噪音抑制
        # 这里可以实现更复杂的算法，如维纳滤波或深度学习方法
        
        # 计算音频能量
        energy = np.mean(np.square(audio_np))
        
        # 如果能量过低，可能是噪音，进行衰减
        if energy < 0.01:  # 可调参数
            audio_np = audio_np * 0.5
        
        return audio_np


# 全局自适应VAD实例
adaptive_vad_engine: Optional[AdaptiveVADEngine] = None


def get_adaptive_vad() -> AdaptiveVADEngine:
    """获取全局自适应VAD实例"""
    global adaptive_vad_engine
    if adaptive_vad_engine is None:
        adaptive_vad_engine = AdaptiveVADEngine()
    return adaptive_vad_engine


def set_advertisement_playing(is_playing: bool, volume: float = 0.5):
    """
    设置广告播放状态的便捷函数
    
    Args:
        is_playing: 是否正在播放广告
        volume: 广告音量 (0.0-1.0)
    """
    vad = get_adaptive_vad()
    vad.set_advertisement_status(is_playing, volume)