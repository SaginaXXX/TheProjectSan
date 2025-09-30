from abc import ABC, abstractmethod


class VADInterface(ABC):
    @abstractmethod
    def detect_speech(self, audio_data: list[float]):
        """
        Detect if there is voice activity in the audio data.
        :param audio_data: PCM float32 list at target_sr
        :return: Iterator of audio bytes for detected human speech segments
        """
        pass
