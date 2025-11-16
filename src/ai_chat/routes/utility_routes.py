"""
Utility Routes
==============
This module contains utility and helper routes.
"""

import os
import json
import base64
from datetime import datetime
from uuid import uuid4
from typing import Optional
from io import BytesIO
from fastapi import APIRouter, WebSocket, Response, Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler


def register_utility_routes(
    router: APIRouter,
    default_context_cache: ServiceContext,
    websocket_handler: 'WebSocketHandler' = None
) -> None:
    """
    Register utility and helper routes.
    
    Args:
        router: FastAPI router instance
        default_context_cache: Default service context cache
        websocket_handler: WebSocket handler for broadcasting (optional)
    """
    
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

    @router.get("/api/qrcode/upload")
    async def get_upload_qrcode(
        request: Request,
        client: Optional[str] = None, 
        category: str = "ads"
    ):
        """
        生成上传二维码（供控制面板使用）
        
        Args:
            request: FastAPI 请求对象（用于获取域名）
            client: 客户ID (可选，默认从环境变量读取)
            category: 分类 (ads/agent)
        
        Returns:
            base64编码的二维码图片
        """
        try:
            import qrcode
            
            # 获取客户ID
            container_client_id = os.getenv('CLIENT_ID', 'default_client')
            client_id = client or container_client_id
            
            # 获取域名配置（优先级：环境变量 > 请求头 > 配置）
            domain = os.getenv('DOMAIN')  # 独立域名（如 screen1.example.com）
            shared_domain = os.getenv('SHARED_DOMAIN')  # 共享域名（如 ads.xyz）
            client_path = os.getenv('CLIENT_PATH')  # 路径前缀（如 client1）
            
            # 从请求头获取域名（如果环境变量未设置）
            if not domain and not shared_domain:
                host_header = request.headers.get('Host', '')
                # 移除端口号（如果有）
                if ':' in host_header:
                    host_header = host_header.split(':')[0]
                # 如果 Host 头部不是 localhost 或 127.0.0.1，使用它作为域名
                if host_header and host_header not in ['localhost', '127.0.0.1', '']:
                    domain = host_header
            
            # 获取host:port用于本地测试
            media_config = default_context_cache.config.system_config.media_server
            local_host = f"{media_config.host}:{media_config.port}"
            
            # 生成Web控制面板URL
            if domain and domain not in ['localhost', '127.0.0.1'] and ':' not in domain:
                # 独立域名模式（生产环境）
                # 判断是否使用 HTTPS（通过 X-Forwarded-Proto 或请求 scheme）
                scheme = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' or str(request.url.scheme) == 'https' else 'http'
                control_panel_url = f"{scheme}://{domain}/web-tool/control-panel.html?client={client_id}"
            elif shared_domain and shared_domain not in ['localhost', '127.0.0.1'] and ':' not in shared_domain:
                # 共享域名模式（生产环境）
                scheme = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' or str(request.url.scheme) == 'https' else 'http'
                if client_path:
                    control_panel_url = f"{scheme}://{shared_domain}/{client_path}/web-tool/control-panel.html?client={client_id}"
                else:
                    control_panel_url = f"{scheme}://{shared_domain}/web-tool/control-panel.html?client={client_id}"
            else:
                # 本地测试模式（使用HTTP）
                control_panel_url = f"http://{local_host}/web-tool/control-panel.html?client={client_id}"
            
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=5
            )
            qr.add_data(control_panel_url)
            qr.make(fit=True)
            
            # 创建图片
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return {
                "status": "success",
                "client_id": client_id,
                "category": category,
                "control_panel_url": control_panel_url,
                "qrcode_base64": f"data:image/png;base64,{img_base64}",
                "display_text": f"扫码访问 {client_id} 控制面板",
                "domain_type": "独立域名" if domain else ("路径前缀" if client_path else "共享域名")
            }
            
        except ImportError:
            return Response(
                content=json.dumps({
                    "error": "qrcode library not installed. Install with: pip install qrcode[pil]"
                }),
                status_code=500,
                media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            return Response(
                content=json.dumps({"error": f"生成二维码失败: {str(e)}"}),
                status_code=500,
                media_type="application/json"
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

