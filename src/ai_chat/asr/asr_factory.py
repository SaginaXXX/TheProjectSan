from typing import Type
from .asr_interface import ASRInterface

# ASR Factory
class ASRFactory:
    @staticmethod
    def get_asr_system(system_name: str, **kwargs) -> Type[ASRInterface]:

        if system_name == "sherpa_onnx_asr":
            from .sherpa_onnx_asr import VoiceRecognition as SherpaOnnxASR

            return SherpaOnnxASR(**kwargs)
        elif system_name == "openai_whisper_asr":
            from .openai_whisper_asr import OpenAIWhisperASR

            return OpenAIWhisperASR(**kwargs)
        else:
            raise ValueError(f"Unknown ASR system: {system_name}")
