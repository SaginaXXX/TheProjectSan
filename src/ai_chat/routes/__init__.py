"""
Routes Module
============
This module contains all route handlers organized by functionality.
"""

from uuid import uuid4
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from loguru import logger
from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler
from ..proxy_handler import ProxyHandler

# Note: Sub-modules are imported lazily in init_webtool_routes() to avoid
# loading all route handlers at module import time, improving startup performance.


def init_client_ws_route(default_context_cache: ServiceContext) -> tuple[APIRouter, WebSocketHandler]:
    """
    Create and return API routes for handling the `/client-ws` WebSocket connections.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        tuple: (APIRouter, WebSocketHandler) - Router and handler instance for broadcasting
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

    return router, ws_handler


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


def init_webtool_routes(default_context_cache: ServiceContext, websocket_handler: 'WebSocketHandler' = None) -> APIRouter:
    """
    Create and return API routes for handling web tool interactions.

    Args:
        default_context_cache: Default service context cache for new sessions.
        websocket_handler: WebSocket handler for broadcasting config updates (optional).

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """
    # Lazy import: Only load route modules when this function is called
    # This improves startup performance by avoiding loading all route handlers at module import time
    from . import (
        asr_routes,
        advertisement_routes,
        media_routes,
        topic_routes,
        config_routes,
        utility_routes
    )
    
    router = APIRouter()
    
    # Register all route modules
    utility_routes.register_utility_routes(router, default_context_cache, websocket_handler)
    asr_routes.register_asr_routes(router, default_context_cache, websocket_handler)
    advertisement_routes.register_advertisement_routes(router, default_context_cache, websocket_handler)
    media_routes.register_media_routes(router, default_context_cache, websocket_handler)
    topic_routes.register_topic_routes(router, default_context_cache, websocket_handler)
    config_routes.register_config_routes(router, default_context_cache, websocket_handler)
    
    return router


__all__ = [
    'init_client_ws_route',
    'init_proxy_route',
    'init_webtool_routes'
]
