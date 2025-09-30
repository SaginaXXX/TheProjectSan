# config_manager/asr.py
from .i18n import I18nMixin, Description
from pydantic import BaseModel, Field
from typing import ClassVar, Dict, Literal, Optional
from pydantic import model_validator, ValidationInfo





class SherpaOnnxASRConfig(I18nMixin):
    """Configuration for Sherpa Onnx ASR."""

    model_type: Literal[
        "transducer",
        "paraformer",
        "nemo_ctc",
        "wenet_ctc",
        "whisper",
        "tdnn_ctc",
        "sense_voice",
    ] = Field(..., alias="model_type")
    encoder: Optional[str] = Field(None, alias="encoder")
    decoder: Optional[str] = Field(None, alias="decoder")
    joiner: Optional[str] = Field(None, alias="joiner")
    paraformer: Optional[str] = Field(None, alias="paraformer")
    nemo_ctc: Optional[str] = Field(None, alias="nemo_ctc")
    wenet_ctc: Optional[str] = Field(None, alias="wenet_ctc")
    tdnn_model: Optional[str] = Field(None, alias="tdnn_model")
    whisper_encoder: Optional[str] = Field(None, alias="whisper_encoder")
    whisper_decoder: Optional[str] = Field(None, alias="whisper_decoder")
    sense_voice: Optional[str] = Field(None, alias="sense_voice")
    tokens: str = Field(..., alias="tokens")
    num_threads: int = Field(4, alias="num_threads")
    use_itn: bool = Field(True, alias="use_itn")
    provider: Literal["cpu", "cuda", "rocm"] = Field("cpu", alias="provider")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "model_type": Description(
            en="Type of ASR model to use", zh="要使用的 ASR 模型类型"
        ),
        "encoder": Description(
            en="Path to encoder model (for transducer)",
            zh="编码器模型路径（用于 transducer）",
        ),
        "decoder": Description(
            en="Path to decoder model (for transducer)",
            zh="解码器模型路径（用于 transducer）",
        ),
        "joiner": Description(
            en="Path to joiner model (for transducer)",
            zh="连接器模型路径（用于 transducer）",
        ),
        "paraformer": Description(
            en="Path to paraformer model", zh="Paraformer 模型路径"
        ),
        "nemo_ctc": Description(en="Path to NeMo CTC model", zh="NeMo CTC 模型路径"),
        "wenet_ctc": Description(en="Path to WeNet CTC model", zh="WeNet CTC 模型路径"),
        "tdnn_model": Description(en="Path to TDNN model", zh="TDNN 模型路径"),
        "whisper_encoder": Description(
            en="Path to Whisper encoder model", zh="Whisper 编码器模型路径"
        ),
        "whisper_decoder": Description(
            en="Path to Whisper decoder model", zh="Whisper 解码器模型路径"
        ),
        "sense_voice": Description(
            en="Path to SenseVoice model", zh="SenseVoice 模型路径"
        ),
        "tokens": Description(en="Path to tokens file", zh="词元文件路径"),
        "num_threads": Description(en="Number of threads to use", zh="使用的线程数"),
        "use_itn": Description(
            en="Enable inverse text normalization", zh="启用反向文本归一化"
        ),
        "provider": Description(
            en="Provider for inference (cpu or cuda) (cuda option needs additional settings. Please check our docs)",
            zh="推理平台（cpu 或 cuda）(cuda 需要额外配置，请参考文档)",
        ),
    }

    @model_validator(mode="after")
    def check_model_paths(cls, values: "SherpaOnnxASRConfig", info: ValidationInfo):
        model_type = values.model_type

        if model_type == "transducer":
            if not all([values.encoder, values.decoder, values.joiner, values.tokens]):
                raise ValueError(
                    "encoder, decoder, joiner, and tokens must be provided for transducer model type"
                )
        elif model_type == "paraformer":
            if not all([values.paraformer, values.tokens]):
                raise ValueError(
                    "paraformer and tokens must be provided for paraformer model type"
                )
        elif model_type == "nemo_ctc":
            if not all([values.nemo_ctc, values.tokens]):
                raise ValueError(
                    "nemo_ctc and tokens must be provided for nemo_ctc model type"
                )
        elif model_type == "wenet_ctc":
            if not all([values.wenet_ctc, values.tokens]):
                raise ValueError(
                    "wenet_ctc and tokens must be provided for wenet_ctc model type"
                )
        elif model_type == "tdnn_ctc":
            if not all([values.tdnn_model, values.tokens]):
                raise ValueError(
                    "tdnn_model and tokens must be provided for tdnn_ctc model type"
                )
        elif model_type == "whisper":
            if not all([values.whisper_encoder, values.whisper_decoder, values.tokens]):
                raise ValueError(
                    "whisper_encoder, whisper_decoder, and tokens must be provided for whisper model type"
                )
        elif model_type == "sense_voice":
            if not all([values.sense_voice, values.tokens]):
                raise ValueError(
                    "sense_voice and tokens must be provided for sense_voice model type"
                )

        return values


class ASRConfig(I18nMixin):
    """Configuration for Automatic Speech Recognition."""

    asr_model: Literal[

        "sherpa_onnx_asr",
        "openai_whisper_asr",

    ] = Field(..., alias="asr_model")
    sherpa_onnx_asr: Optional[SherpaOnnxASRConfig] = Field(
        None, alias="sherpa_onnx_asr"
    )

    class OpenAIWhisperASRConfig(I18nMixin, BaseModel):
        """Configuration for OpenAI Whisper cloud ASR."""
        model: str = Field("gpt-4o-transcribe", alias="model")
        base_url: str | None = Field(None, alias="base_url")
        api_key: str | None = Field(None, alias="api_key")
        language: str | None = Field(None, alias="language")
        timeout: float | None = Field(60.0, alias="timeout")

        DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
            "model": Description(en="OpenAI transcription model name", zh="OpenAI 转写模型名"),
            "base_url": Description(en="Custom base URL if using compatible proxy", zh="自定义 Base URL（兼容代理）"),
            "api_key": Description(en="OpenAI API key (fallback to env if omitted)", zh="OpenAI API 密钥（留空则用环境变量）"),
            "language": Description(en="Forced language code (optional)", zh="强制语言代码（可选）"),
            "timeout": Description(en="Request timeout in seconds", zh="请求超时（秒）"),
        }

    # OpenAI Whisper cloud config
    openai_whisper_asr: Optional[OpenAIWhisperASRConfig] = Field(
        None, alias="openai_whisper_asr"
    )

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "asr_model": Description(
            en="Speech-to-text model to use", zh="要使用的语音识别模型"
        ),
        "azure_asr": Description(en="Configuration for Azure ASR", zh="Azure ASR 配置"),
        "faster_whisper": Description(
            en="Configuration for Faster Whisper", zh="Faster Whisper 配置"
        ),
        "whisper_cpp": Description(
            en="Configuration for WhisperCPP", zh="WhisperCPP 配置"
        ),
        "whisper": Description(en="Configuration for Whisper", zh="Whisper 配置"),
        "fun_asr": Description(en="Configuration for FunASR", zh="FunASR 配置"),
        "groq_whisper_asr": Description(
            en="Configuration for Groq Whisper ASR", zh="Groq Whisper ASR 配置"
        ),
        "sherpa_onnx_asr": Description(
            en="Configuration for Sherpa Onnx ASR", zh="Sherpa Onnx ASR 配置"
        ),
    }

    @model_validator(mode="after")
    def check_asr_config(cls, values: "ASRConfig", info: ValidationInfo):
        asr_model = values.asr_model

        # Only validate the selected ASR model

        if asr_model == "SherpaOnnxASR" and values.sherpa_onnx_asr is not None:
            values.sherpa_onnx_asr.model_validate(values.sherpa_onnx_asr.model_dump())
        elif asr_model == "openai_whisper_asr" and values.openai_whisper_asr is not None:
            values.openai_whisper_asr.model_validate(values.openai_whisper_asr.model_dump())

        return values

