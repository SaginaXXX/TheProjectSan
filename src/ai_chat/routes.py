"""
Routes Module (Legacy Entry Point)
===================================
This file is kept for backward compatibility. All route functions are now in routes/__init__.py
"""

# Re-export from routes package
from .routes import (
    init_client_ws_route,
    init_proxy_route,
    init_webtool_routes
)

__all__ = [
    'init_client_ws_route',
    'init_proxy_route',
    'init_webtool_routes'
]
