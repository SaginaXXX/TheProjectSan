#!/usr/bin/env python3
"""
时间查询 MCP 服务器
默认时区：Asia/Tokyo

工具:
- get_time: 获取指定时区（默认东京）的当前时间
"""

import json
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.types as types


DEFAULT_TZ = "Asia/Tokyo"


def _now_in_timezone(tz_name: str) -> dict:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    utc_now = datetime.now(timezone.utc)
    return {
        "timezone": tz_name,
        "local_iso": now.isoformat(),
        "local_str": now.strftime("%Y-%m-%d %H:%M:%S (%Z)"),
        "epoch_ms": int(now.timestamp() * 1000),
        "utc_iso": utc_now.isoformat(),
    }


class TimeServer:
    def __init__(self, default_tz: str = DEFAULT_TZ):
        self.server = Server("time")
        self.default_tz = default_tz
        self._register_tools()

    def _register_tools(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="get_time",
                    description="Get current time for a timezone (default: Asia/Tokyo)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string", "description": "IANA timezone", "default": self.default_tz},
                        },
                        "required": [],
                    },
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            if name == "get_time":
                tz = arguments.get("timezone", self.default_tz) or self.default_tz
                try:
                    payload = {
                        "type": "time_response",
                        **_now_in_timezone(tz),
                    }
                    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
                except Exception as e:
                    err = {"type": "time_error", "message": f"Failed to get time: {e}"}
                    return [types.TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]

            return [types.TextContent(type="text", text=json.dumps({"type": "error", "message": f"Unknown tool: {name}"}))]

    async def run(self):
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="time",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def main():
    parser = argparse.ArgumentParser(description="Time MCP Server")
    parser.add_argument("--timezone", type=str, default=DEFAULT_TZ)
    args = parser.parse_args()

    server = TimeServer(default_tz=args.timezone)
    await server.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


