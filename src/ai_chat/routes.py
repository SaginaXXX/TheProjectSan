import os
import json
import re
from uuid import uuid4
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, WebSocket, UploadFile, File, Response
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect
from loguru import logger
from .service_context import ServiceContext
from .websocket_handler import WebSocketHandler
from .proxy_handler import ProxyHandler


def init_client_ws_route(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling the `/client-ws` WebSocket connections.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()
    ws_handler = WebSocketHandler(default_context_cache)

    @router.websocket("/client-ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for client connections"""
        await websocket.accept()
        client_uid = str(uuid4())

        try:
            await ws_handler.handle_new_connection(websocket, client_uid)
            await ws_handler.handle_websocket_communication(websocket, client_uid)
        except WebSocketDisconnect:
            await ws_handler.handle_disconnect(client_uid)
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}")
            await ws_handler.handle_disconnect(client_uid)
            raise

    return router


def init_proxy_route(server_url: str) -> APIRouter:
    """
    Create and return API routes for handling proxy connections.

    Args:
        server_url: The WebSocket URL of the actual server

    Returns:
        APIRouter: Configured router with proxy WebSocket endpoint
    """
    router = APIRouter()
    proxy_handler = ProxyHandler(server_url)

    @router.websocket("/proxy-ws")
    async def proxy_endpoint(websocket: WebSocket):
        """WebSocket endpoint for proxy connections"""
        try:
            await proxy_handler.handle_client_connection(websocket)
        except Exception as e:
            logger.error(f"Error in proxy connection: {e}")
            raise

    return router


def init_webtool_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling web tool interactions.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()

    @router.get("/web-tool")
    async def web_tool_redirect():
        """Redirect /web-tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/web_tool")
    async def web_tool_redirect_alt():
        """Redirect /web_tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/live2d-models/info")
    async def get_live2d_folder_info():
        """Get information about available Live2D models"""
        live2d_dir = "live2d-models"
        if not os.path.exists(live2d_dir):
            return JSONResponse(
                {"error": "Live2D models directory not found"}, status_code=404
            )

        valid_characters = []
        supported_extensions = [".png", ".jpg", ".jpeg"]

        for entry in os.scandir(live2d_dir):
            if entry.is_dir():
                folder_name = entry.name.replace("\\", "/")
                model3_file = os.path.join(
                    live2d_dir, folder_name, f"{folder_name}.model3.json"
                ).replace("\\", "/")

                if os.path.isfile(model3_file):
                    # Find avatar file if it exists
                    avatar_file = None
                    for ext in supported_extensions:
                        avatar_path = os.path.join(
                            live2d_dir, folder_name, f"{folder_name}{ext}"
                        )
                        if os.path.isfile(avatar_path):
                            avatar_file = avatar_path.replace("\\", "/")
                            break

                    valid_characters.append(
                        {
                            "name": folder_name,
                            "avatar": avatar_file,
                            "model_path": model3_file,
                        }
                    )
        return JSONResponse(
            {
                "type": "live2d-models/info",
                "count": len(valid_characters),
                "characters": valid_characters,
            }
        )

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

    # ==================== 广告视频管理API端点 ====================
    
    @router.get("/api/ads")
    async def get_advertisement_list():
        """获取广告视频列表"""
        try:
            ads_dir = Path("ads")
            if not ads_dir.exists():
                ads_dir.mkdir(parents=True, exist_ok=True)
                return {"advertisements": [], "total_count": 0}
            
            advertisements = []
            supported_formats = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
            
            for video_file in ads_dir.iterdir():
                if video_file.is_file() and video_file.suffix.lower() in supported_formats:
                    file_size = video_file.stat().st_size
                    advertisements.append({
                        "id": f"ad_{len(advertisements):03d}",
                        "name": video_file.stem,
                        "filename": video_file.name,
                        "path": str(video_file),
                        "url_path": f"/ads/{video_file.name}",
                        "size_bytes": file_size,
                        "size_mb": round(file_size / (1024 * 1024), 2),
                        "format": video_file.suffix.lower(),
                        "category": "advertisement"
                    })
            
            return {
                "advertisements": advertisements,
                "total_count": len(advertisements),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error getting advertisement list: {e}")
            return Response(
                content=json.dumps({"error": f"Failed to get advertisement list: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.post("/api/ads/upload")
    async def upload_advertisement(file: UploadFile = File(...)):
        """上传广告视频文件"""
        try:
            # 验证文件类型
            allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                return Response(
                    content=json.dumps({
                        "error": f"不支持的文件格式: {file_extension}。支持的格式: {', '.join(allowed_extensions)}"
                    }),
                    status_code=400,
                    media_type="application/json",
                )
            
            # 验证文件大小（限制为500MB）
            max_size = 500 * 1024 * 1024  # 500MB
            contents = await file.read()
            if len(contents) > max_size:
                return Response(
                    content=json.dumps({
                        "error": f"文件太大。最大允许大小: 500MB，当前文件: {len(contents)/(1024*1024):.1f}MB"
                    }),
                    status_code=400,
                    media_type="application/json",
                )
            
            # 确保ads目录存在
            ads_dir = Path("ads")
            ads_dir.mkdir(parents=True, exist_ok=True)
            
            # 防止文件名冲突
            original_name = Path(file.filename).stem
            file_extension = Path(file.filename).suffix.lower()
            counter = 1
            filename = f"{original_name}{file_extension}"
            file_path = ads_dir / filename
            
            while file_path.exists():
                filename = f"{original_name}_{counter}{file_extension}"
                file_path = ads_dir / filename
                counter += 1
            
            # 保存文件
            with open(file_path, "wb") as f:
                f.write(contents)
            
            # 获取文件信息
            file_size = len(contents)
            
            logger.info(f"Successfully uploaded advertisement: {filename} ({file_size/(1024*1024):.2f}MB)")
            
            return {
                "status": "success",
                "message": f"广告视频 '{filename}' 上传成功",
                "file_info": {
                    "name": original_name,
                    "filename": filename,
                    "path": str(file_path),
                    "url_path": f"/ads/{filename}",
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "format": file_extension,
                    "category": "advertisement"
                }
            }
            
        except Exception as e:
            logger.error(f"Error uploading advertisement: {e}")
            return Response(
                content=json.dumps({"error": f"上传失败: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.delete("/api/ads/{filename}")
    async def delete_advertisement(filename: str):
        """删除广告视频文件"""
        try:
            ads_dir = Path("ads")
            file_path = ads_dir / filename
            
            # 验证文件是否存在
            if not file_path.exists() or not file_path.is_file():
                return Response(
                    content=json.dumps({"error": f"文件不存在: {filename}"}),
                    status_code=404,
                    media_type="application/json",
                )
            
            # 验证文件在ads目录中（安全检查）
            try:
                file_path.resolve().relative_to(ads_dir.resolve())
            except ValueError:
                return Response(
                    content=json.dumps({"error": "非法的文件路径"}),
                    status_code=400,
                    media_type="application/json",
                )
            
            # 删除文件
            file_path.unlink()
            
            logger.info(f"Successfully deleted advertisement: {filename}")
            
            return {
                "status": "success",
                "message": f"广告视频 '{filename}' 删除成功",
                "deleted_file": filename
            }
            
        except Exception as e:
            logger.error(f"Error deleting advertisement: {e}")
            return Response(
                content=json.dumps({"error": f"删除失败: {str(e)}"}),
                status_code=500,
                media_type="application/json",
            )

    @router.websocket("/tts-ws")
    async def tts_endpoint(websocket: WebSocket):
        """WebSocket endpoint for TTS generation"""
        await websocket.accept()
        logger.info("TTS WebSocket connection established")

        try:
            while True:
                data = await websocket.receive_json()
                text = data.get("text")
                if not text:
                    continue

                logger.info(f"Received text for TTS: {text}")

                # Split text into sentences
                sentences = [s.strip() for s in text.split(".") if s.strip()]

                try:
                    # Generate and send audio for each sentence
                    for sentence in sentences:
                        sentence = sentence + "."  # Add back the period
                        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"
                        audio_path = (
                            await default_context_cache.tts_engine.async_generate_audio(
                                text=sentence, file_name_no_ext=file_name
                            )
                        )
                        logger.info(
                            f"Generated audio for sentence: {sentence} at: {audio_path}"
                        )

                        await websocket.send_json(
                            {
                                "status": "partial",
                                "audioPath": audio_path,
                                "text": sentence,
                            }
                        )

                    # Send completion signal
                    await websocket.send_json({"status": "complete"})

                except Exception as e:
                    logger.error(f"Error generating TTS: {e}")
                    await websocket.send_json({"status": "error", "message": str(e)})

        except WebSocketDisconnect:
            logger.info("TTS WebSocket client disconnected")
        except Exception as e:
            logger.error(f"Error in TTS WebSocket connection: {e}")
            await websocket.close()

    return router
