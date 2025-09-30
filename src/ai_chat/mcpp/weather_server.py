#!/usr/bin/env python3
"""
天气查询 MCP 服务器（Open‑Meteo）
默认位置：东京 (lat=35.6895, lon=139.6917)

工具:
- get_weather: 获取当前天气/简要预测
"""

import json
import asyncio
import argparse
from urllib import request, parse
from typing import Optional, Tuple, Dict
import time as _time

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.types as types


DEFAULT_LAT = 35.6895
DEFAULT_LON = 139.6917
DEFAULT_TZ = "Asia/Tokyo"

# 简单内存缓存：key=(rounded_lat, rounded_lon, tz), value=(timestamp, data)
_CACHE: Dict[Tuple[float, float, str], Tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 120.0  # 2 分钟


def _fetch_open_meteo(
    latitude: float,
    longitude: float,
    timezone: str = DEFAULT_TZ,
) -> dict:
    """同步请求 Open‑Meteo 当前天气数据。"""
    base = "https://api.open-meteo.com/v1/forecast"
    query = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "wind_speed_10m",
            "is_day",
            "weather_code",
        ]),
    }
    url = f"{base}?{parse.urlencode(query)}"
    with request.urlopen(url, timeout=8) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data)


def _get_weather_cached(latitude: float, longitude: float, timezone: str) -> dict:
    # 位置粗粒度归一化，避免轻微坐标差造成缓存击穿
    key = (round(latitude, 2), round(longitude, 2), timezone)
    now = _time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    data = _fetch_open_meteo(latitude, longitude, timezone)
    _CACHE[key] = (now, data)
    return data


def _code_to_desc(weather_code: Optional[int]) -> str:
    """简易天气代码映射（可按需扩展）。"""
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        80: "Rain showers",
        81: "Heavy rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
    }
    return mapping.get(int(weather_code) if weather_code is not None else -1, "Unknown")


class WeatherServer:
    def __init__(self):
        self.server = Server("weather-server")
        self._register_tools()

    def _register_tools(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="get_weather",
                    description="Get current weather for a location (default: Tokyo).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude (default Tokyo)"},
                            "longitude": {"type": "number", "description": "Longitude (default Tokyo)"},
                            "timezone": {"type": "string", "description": "IANA timezone", "default": DEFAULT_TZ},
                        },
                        "required": [],
                    },
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            if name == "get_weather":
                lat = float(arguments.get("latitude", DEFAULT_LAT))
                lon = float(arguments.get("longitude", DEFAULT_LON))
                tz = arguments.get("timezone", DEFAULT_TZ)

                try:
                    data = await asyncio.to_thread(_get_weather_cached, lat, lon, tz)
                    current = data.get("current", {})
                    code = current.get("weather_code")
                    desc = _code_to_desc(code)
                    payload = {
                        "type": "weather_response",
                        "location": {
                            "latitude": lat,
                            "longitude": lon,
                            "timezone": tz,
                        },
                        "current": {
                            "temperature_2m": current.get("temperature_2m"),
                            "apparent_temperature": current.get("apparent_temperature"),
                            "relative_humidity_2m": current.get("relative_humidity_2m"),
                            "wind_speed_10m": current.get("wind_speed_10m"),
                            "weather_code": code,
                            "weather_desc": desc,
                            "is_day": current.get("is_day"),
                            "time": current.get("time"),
                        },
                    }
                    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
                except Exception as e:
                    err = {
                        "type": "weather_error",
                        "message": f"Failed to fetch weather: {e}",
                    }
                    return [types.TextContent(type="text", text=json.dumps(err, ensure_ascii=False))]

            return [types.TextContent(type="text", text=json.dumps({"type": "error", "message": f"Unknown tool: {name}"}))]

    async def run(self):
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="weather-server",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def main():
    parser = argparse.ArgumentParser(description="Weather MCP Server (Open‑Meteo)")
    parser.add_argument("--latitude", type=float, default=DEFAULT_LAT)
    parser.add_argument("--longitude", type=float, default=DEFAULT_LON)
    parser.add_argument("--timezone", type=str, default=DEFAULT_TZ)
    _ = parser.parse_args()

    server = WeatherServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())


