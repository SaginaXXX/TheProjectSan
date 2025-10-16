"""MCP Client for AI"""
import json
import asyncio
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Callable
from loguru import logger
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from anyio import ClosedResourceError
from mcp.types import Tool
from mcp.client.stdio import stdio_client

from .server_registry import ServerRegistry
from ..message_handler import message_handler

# 默认超时时间
DEFAULT_TIMEOUT = timedelta(seconds=30)

class MCPClient:
    """MCP Client ., Manages persistent connections to multiple MCP servers.
    """

    def __init__(self, server_registery: ServerRegistry, send_text: Callable = None, client_uid: str = None) -> None:
        """Initialize the MCP Client."""
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.active_sessions: Dict[str, ClientSession] = {}
        self._list_tools_cache: Dict[str, List[Tool]] = {}  # Cache for list_tools
        self._send_text: Callable = send_text
        self._client_uid: str = client_uid

        if isinstance(server_registery, ServerRegistry):
            self.server_registery = server_registery
        else:
            raise TypeError(
                "MCPC: Invalid server manager. Must be an instance of ServerRegistry."
            )
        logger.info("MCPC: Initialized MCPClient instance.")

    async def _ensure_server_running_and_get_session(
        self, server_name: str
    ) -> ClientSession:
        """Gets the existing session or creates a new one."""
        if server_name in self.active_sessions:
            return self.active_sessions[server_name]

        logger.info(f"MCPC: Starting and connecting to server '{server_name}'...")
        server = self.server_registery.get_server(server_name)
        if not server:
            raise ValueError(
                f"MCPC: Server '{server_name}' not found in available servers."
            )

        timeout = server.timeout if server.timeout else DEFAULT_TIMEOUT
        # Normalize timeout to timedelta expected by mcp client
        try:
            from datetime import timedelta as _td
            if not isinstance(timeout, _td):
                timeout = _td(seconds=float(timeout))
        except Exception:
            timeout = DEFAULT_TIMEOUT

        server_params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env,
        )

        try:
            # Add timeout to server startup
            startup_timeout = 10  # seconds
            logger.debug(f"MCPC: Starting server '{server_name}' with timeout {startup_timeout}s...")
            
            stdio_transport = await asyncio.wait_for(
                self.exit_stack.enter_async_context(stdio_client(server_params)),
                timeout=startup_timeout
            )
            read, write = stdio_transport

            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=timeout)
            )
            await session.initialize()

            self.active_sessions[server_name] = session
            logger.info(f"MCPC: Successfully connected to server '{server_name}'.")
            return session
        except asyncio.TimeoutError:
            logger.error(f"MCPC: Timeout starting server '{server_name}' after {startup_timeout}s")
            raise RuntimeError(
                f"MCPC: Timeout starting server '{server_name}'"
            )
        except Exception as e:
            logger.exception(f"MCPC: Failed to connect to server '{server_name}': {e}")
            raise RuntimeError(
                f"MCPC: Failed to connect to server '{server_name}'."
            ) from e

    async def list_tools(self, server_name: str) -> List[Tool]:
        """List all available tools on the specified server."""
        # Check cache first
        if server_name in self._list_tools_cache:
            logger.debug(f"MCPC: Cache hit for list_tools on server '{server_name}'.")
            return self._list_tools_cache[server_name]

        logger.debug(f"MCPC: Cache miss for list_tools on server '{server_name}'. Fetching...")
        
        # Retry mechanism for list_tools
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = await self._ensure_server_running_and_get_session(server_name)
                response = await session.list_tools()

                # Store in cache before returning
                self._list_tools_cache[server_name] = response.tools
                logger.debug(f"MCPC: Cached list_tools result for server '{server_name}'.")
                return response.tools
                
            except Exception as e:
                logger.warning(f"MCPC: list_tools failed for '{server_name}' (attempt {attempt + 1}/{max_retries}): {e}")
                
                # Clear cache and active session on failure
                if server_name in self._list_tools_cache:
                    del self._list_tools_cache[server_name]
                if server_name in self.active_sessions:
                    try:
                        await self.active_sessions[server_name].close()
                    except:
                        pass
                    del self.active_sessions[server_name]
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # 渐进延迟
                else:
                    raise  # 最后一次重试失败，抛出异常

    async def call_tool(
        self, server_name: str, tool_name: str, tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on the specified server.

        Returns:
            Dict containing the metadata and content_items from the tool response.
        """
        logger.info(f"MCPC: Calling tool '{tool_name}' on server '{server_name}'...")

        # Try once, and on ClosedResourceError/connection failures, reset session and retry once
        max_attempts = 2
        last_error: Exception | None = None
        response = None
        for attempt in range(1, max_attempts + 1):
            try:
                session = await self._ensure_server_running_and_get_session(server_name)
                response = await session.call_tool(tool_name, tool_args)
                last_error = None
                break
            except ClosedResourceError as cre:
                logger.warning(f"MCPC: Session closed when calling tool '{tool_name}' (attempt {attempt}/{max_attempts}). Reconnecting...")
                # Remove broken session and retry
                if server_name in self.active_sessions:
                    try:
                        await self.active_sessions[server_name].close()
                    except Exception:
                        pass
                    self.active_sessions.pop(server_name, None)
                last_error = cre
            except Exception as e:
                logger.warning(f"MCPC: Error calling tool '{tool_name}' (attempt {attempt}/{max_attempts}): {e}")
                # On generic errors, also reset and retry once
                if server_name in self.active_sessions:
                    try:
                        await self.active_sessions[server_name].close()
                    except Exception:
                        pass
                    self.active_sessions.pop(server_name, None)
                last_error = e
        if last_error is not None and response is None:
            logger.error(f"MCPC: Failed to call tool '{tool_name}' after retries: {last_error}")
            return {
                "metadata": {},
                "content_items": [{"type": "error", "text": f"{last_error}"}],
            }

        if response.isError:
            error_text = (
                response.content[0].text if response.content and hasattr(response.content[0], "text") else "Unknown server error"
            )
            logger.error(f"MCPC: Error calling tool '{tool_name}': {error_text}")
            # Return error information within the standard structure
            return {
                "metadata": getattr(response, "metadata", {}),
                "content_items": [{"type": "error", "text": error_text}]
            }

        content_items = []
        if response.content:
            for item in response.content:
                item_dict = {"type": getattr(item, "type", "text")}
                # Extract available attributes from content item
                for attr in ["text", "data", "mimeType", "url", "altText"]: # Added url and altText
                    if hasattr(item, attr) and getattr(item, attr) is not None: # Check for None
                        item_dict[attr] = getattr(item, attr)
                content_items.append(item_dict)
        else:
            logger.warning(
                f"MCPC: Tool '{tool_name}' returned no content. Returning empty content_items."
            )
            content_items.append({"type": "text", "text": ""}) # Ensure content_items is not empty

        result = {
            "metadata": getattr(response, "metadata", {}),
            "content_items": content_items,
        }
        return result

    async def aclose(self) -> None:
        """Closes all active server connections (robust to cleanup errors)."""
        logger.info(
            f"MCPC: Closing client instance and {len(self.active_sessions)} active connections..."
        )
        
        # 🔍 诊断：记录关闭前的状态
        logger.info(f"  🔍 Sessions to close: {list(self.active_sessions.keys())}")
        
        try:
            try:
                # 强制关闭所有session（确保服务器进程被终止）
                for server_name, session in list(self.active_sessions.items()):
                    try:
                        logger.debug(f"  🔄 关闭 session: {server_name}")
                        await asyncio.wait_for(session.close(), timeout=2.0)
                    except Exception as e:
                        logger.warning(f"  ⚠️  关闭session '{server_name}' 失败: {e}")
                
                # 清理exit_stack（这会终止服务器进程）
                await self.exit_stack.aclose()
                logger.info("  ✅ exit_stack已清理")
            except Exception as e:
                # Swallow cleanup errors from anyio cancel scopes to avoid breaking callers
                logger.warning(f"MCPC: exit_stack.aclose() raised during cleanup: {e}")
        finally:
            self.active_sessions.clear()
            self._list_tools_cache.clear()  # Clear cache on close
            self.exit_stack = AsyncExitStack()
            logger.info("MCPC: Client instance closed (cleanup safe).")

    async def __aenter__(self) -> "MCPClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the async context manager (robust)."""
        try:
            await self.aclose()
        except Exception as e:
            logger.warning(f"MCPC: aclose() raised during context exit: {e}")
        if exc_type:
            logger.error(f"MCPC: Exception in async context: {exc_value}")


# if __name__ == "__main__":
#     # Test the MCPClient.
#     async def main():
#         server_registery = ServerRegistry()
#         async with MCPClient(server_registery) as client:
#             # Assuming 'example' server and 'example_tool' exist
#             # The old call used: await client.call_tool("example_tool", {"arg1": "value1"})
#             # The new call needs server name:
#             try:
#                 result = await client.call_tool("example", "example_tool", {"arg1": "value1"})
#                 print(f"Tool result: {result}")
#                 # Test error handling by calling a non-existent tool
#                 await client.call_tool("example", "non_existent_tool", {})
#             except ValueError as e:
#                 print(f"Caught expected error: {e}")
#             except Exception as e:
#                 print(f"Caught unexpected error: {e}")

#     asyncio.run(main())
