from typing import Type
from .tts_interface import TTSInterface


class TTSFactory:
    @staticmethod
    def get_tts_engine(engine_type, **kwargs) -> Type[TTSInterface]:

        if engine_type == "fish_api_tts":
            from .fish_api_tts import TTSEngine as FishAPITTSEngine

            return FishAPITTSEngine(
                api_key=kwargs.get("api_key"),
                reference_id=kwargs.get("reference_id"),
                latency=kwargs.get("latency", "balanced"),
                base_url=kwargs.get("base_url", "https://api.fish.audio"),
            )
        else:
            raise ValueError(f"Unknown TTS engine type: {engine_type}")


# Example usage:
# tts_engine = TTSFactory.get_tts_engine("azure", api_key="your_api_key", region="your_region", voice="your_voice")
# tts_engine.speak("Hello world")
if __name__ == "__main__":
    print("开始创建TTS引擎...")
    tts_engine = TTSFactory.get_tts_engine(
        "fish_api_tts",
        api_key="4e36f61d223344b886e772c705f95c95",
        reference_id="5ddc5d5dcdec4d59b278f5f4777182aa"
    )
    print("TTS引擎创建成功，开始生成音频...")
    result = tts_engine.generate_audio("Hello world")
    print(f"音频生成结果: {result}")
