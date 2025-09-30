from typing import Optional
from .vad_interface import VADInterface


class VADFactory:
    @staticmethod
    def get_vad_engine(engine_type, **kwargs) -> Optional[VADInterface]:
        if not engine_type:
            return None
        if engine_type == "silero_vad":
            from .silero import VADEngine as SileroVADEngine

            return SileroVADEngine(
                kwargs.get("orig_sr") or 16000,
                kwargs.get("target_sr") or 16000,
                kwargs.get("prob_threshold") or 0.4,
                kwargs.get("db_threshold") or 60,
                kwargs.get("required_hits") or 3,
                kwargs.get("required_misses") or 24,
                kwargs.get("smoothing_window") or 5,
            )
        return None
