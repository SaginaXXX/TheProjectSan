import io
import wave
from typing import Optional

import numpy as np
from loguru import logger

from .asr_interface import ASRInterface


class OpenAIWhisperASR(ASRInterface):
    def __init__(
        self,
        model: str = "gpt-4o-transcribe",  # or "whisper-1"
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        language: Optional[str] = None,
        timeout: Optional[float] = 60.0,
    ) -> None:
        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError(
                "openai package is required for OpenAIWhisperASR. Please install it first."
            ) from e

        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.language = language
        self.timeout = timeout

        # Initialize client
        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = OpenAI(**client_kwargs)  # type: ignore[arg-type]
        logger.info(
            f"OpenAIWhisperASR initialized with model={self.model}, base_url={self.base_url or 'default'}"
        )

    def _numpy_to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> io.BytesIO:
        # Ensure float32 in [-1, 1]
        audio = audio.astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        pcm16 = (audio * 32767.0).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())

        buffer.seek(0)
        # Some SDKs require a filename-like attribute
        if not hasattr(buffer, "name"):
            buffer.name = "audio.wav"  # type: ignore[attr-defined]
        return buffer

    def transcribe_np(self, audio: np.ndarray) -> str:
        wav_bytes = self._numpy_to_wav_bytes(audio, self.SAMPLE_RATE)

        try:
            # OpenAI Python SDK v1.x
            # Prefer the new transcribe model name if available; fallback to whisper-1
            kwargs = {"model": self.model, "file": wav_bytes}
            if self.language:
                kwargs["language"] = self.language

            resp = self._client.audio.transcriptions.create(**kwargs)  # type: ignore[call-arg]
            text = getattr(resp, "text", None)
            if not isinstance(text, str):
                raise ValueError("Invalid response from OpenAI transcription API: missing text")
            return text
        except Exception as e:
            logger.error(f"OpenAIWhisperASR transcription failed: {e}")
            raise

        
  