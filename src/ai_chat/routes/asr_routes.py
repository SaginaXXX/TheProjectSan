"""
ASR Routes
==========
This module contains ASR (Automatic Speech Recognition) related routes.
"""

import json
import numpy as np
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Response
from starlette.responses import JSONResponse
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_asr_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register ASR-related routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
    @router.post("/asr")
    async def transcribe_audio(file: UploadFile = File(...)):
        """
        Endpoint for transcribing audio using the ASR engine
        """
        logger.info(f"Received audio file for transcription: {file.filename}")

        try:
            contents = await file.read()

            # Validate minimum file size
            if len(contents) < 44:  # Minimum WAV header size
                raise ValueError("Invalid WAV file: File too small")

            # Decode the WAV header and get actual audio data
            wav_header_size = 44  # Standard WAV header size
            audio_data = contents[wav_header_size:]

            # Validate audio data size
            if len(audio_data) % 2 != 0:
                raise ValueError("Invalid audio data: Buffer size must be even")

            # Convert to 16-bit PCM samples to float32
            try:
                audio_array = (
                    np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
            except ValueError as e:
                raise ValueError(
                    f"Audio format error: {str(e)}. Please ensure the file is 16-bit PCM WAV format."
                )

            # Validate audio data
            if len(audio_array) == 0:
                raise ValueError("Empty audio data")

            text = await default_context_cache.asr_engine.async_transcribe_np(
                audio_array
            )
            logger.info(f"Transcription result: {text}")
            return {"text": text}

        except ValueError as e:
            logger.error(f"Audio format error: {e}")
            return Response(
                content=json.dumps({"error": str(e)}),
                status_code=400,
                media_type="application/json",
            )
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return Response(
                content=json.dumps(
                    {"error": "Internal server error during transcription"}
                ),
                status_code=500,
                media_type="application/json",
            )

    @router.post("/api/asr-chunk")
    async def transcribe_audio_chunk(file: UploadFile = File(...)):
        """
        Low-latency endpoint for short WAV chunks (16kHz mono PCM16).
        Returns partial transcription text for each chunk.
        """
        logger.debug(f"Received ASR chunk: {file.filename}")

        try:
            contents = await file.read()

            # Minimal validation: WAV header and data length
            if len(contents) < 44:
                raise ValueError("Invalid WAV chunk: File too small")

            wav_header_size = 44
            audio_data = contents[wav_header_size:]

            if len(audio_data) % 2 != 0:
                raise ValueError("Invalid audio data: Buffer size must be even")

            try:
                audio_array = (
                    np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                )
            except ValueError as e:
                raise ValueError(
                    f"Audio format error: {str(e)}. Please ensure the chunk is 16-bit PCM WAV."
                )

            if len(audio_array) == 0:
                raise ValueError("Empty audio data in chunk")

            text = await default_context_cache.asr_engine.async_transcribe_np(audio_array)
            return {"text": text}

        except ValueError as e:
            logger.error(f"ASR chunk format error: {e}")
            return Response(
                content=json.dumps({"error": str(e)}),
                status_code=400,
                media_type="application/json",
            )
        except Exception as e:
            logger.error(f"Error during ASR chunk transcription: {e}")
            return Response(
                content=json.dumps({"error": "Internal server error during ASR chunk"}),
                status_code=500,
                media_type="application/json",
            )

    @router.post("/api/asr/settings")
    async def update_asr_settings(
        auto_stop_mic: Optional[bool] = Form(None),
        auto_start_mic_on_conv_end: Optional[bool] = Form(None),
        auto_start_mic_on: Optional[bool] = Form(None),
        positive_speech_threshold: Optional[float] = Form(None),
        negative_speech_threshold: Optional[float] = Form(None),
        redemption_frames: Optional[int] = Form(None),
        client: Optional[str] = Form(None)
    ):
        """
        ASR设置API（信号模式）
        直接更新ASR设置，无需查询当前状态
        
        Args:
            auto_stop_mic: AI说话时自动停止麦克风
            auto_start_mic_on_conv_end: 对话结束时自动开始麦克风
            auto_start_mic_on: AI中断时自动开始麦克风
            positive_speech_threshold: 语音检测阈值
            negative_speech_threshold: 静音检测阈值
            redemption_frames: 恢复帧数
            client: 客户ID (可选，默认从环境变量读取)
        
        Returns:
            更新结果
        """
        import os
        
        try:
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            logger.info(f"🎤 收到ASR设置信号 (client: {client_id})")
            
            # 构建设置数据（只包含提供的参数）
            settings_data = {}
            if auto_stop_mic is not None:
                settings_data['auto_stop_mic'] = auto_stop_mic
            if auto_start_mic_on_conv_end is not None:
                settings_data['auto_start_mic_on_conv_end'] = auto_start_mic_on_conv_end
            if auto_start_mic_on is not None:
                settings_data['auto_start_mic_on'] = auto_start_mic_on
            if positive_speech_threshold is not None:
                settings_data['positive_speech_threshold'] = positive_speech_threshold
            if negative_speech_threshold is not None:
                settings_data['negative_speech_threshold'] = negative_speech_threshold
            if redemption_frames is not None:
                settings_data['redemption_frames'] = redemption_frames
            
            if not settings_data:
                return Response(
                    content=json.dumps({"error": "至少需要提供一个设置参数"}),
                    status_code=400,
                    media_type="application/json"
                )
            
            # 通过WebSocket广播ASR设置更新（直接广播原始消息）
            if websocket_handler:
                broadcast_message = {
                    "type": "asr-settings-update",
                    **settings_data,
                    "client_id": client_id
                }
                # 直接广播原始消息，而不是包装成settings-updated
                await websocket_handler.broadcast_to_all(broadcast_message)
                logger.info(f"✅ ASR设置已广播: {settings_data}")
            
            return {
                "success": True,
                "message": "ASR设置已更新",
                "settings": settings_data,
                "client_id": client_id
            }
            
        except Exception as e:
            logger.error(f"ASR设置API错误: {e}", exc_info=True)
            return Response(
                content=json.dumps({"error": f"ASR设置更新失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
            )

