# 主程序执行文件
import os
import sys
import argparse
import atexit
import asyncio
import subprocess
import uvicorn

from loguru import logger
from pathlib import Path

# 添加项目相关的导入
from src.ai_chat.server import WebSocketServer
from src.ai_chat.config_manager import Config, validate_config, read_yaml

os.environ['HF_HOME'] = str(Path(__file__).parent / 'models') # 设置模型缓存路径
os.environ['MODELSCOPE_CACHE'] = str(Path(__file__).parent / 'models') # 设置模型缓存路径


def get_version() -> str:
    return "1.0.0"  # 简化版本获取


def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()
    # Console output
    logger.add(
        sys.stderr,
        level=console_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | {message}",
        colorize=True,
    )

    # File output
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
        backtrace=True,
        diagnose=True,
    )


def check_frontend_submodule():
    """
    Check if the frontend submodule is initialized. If not, attempt to initialize it.
    If initialization fails, log an error message.
    """
    frontend_path = Path(__file__).parent / "frontend" / "index.html"
    if not frontend_path.exists():
        logger.warning("Frontend submodule not found, attempting to initialize submodules...")

        try:
            subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive"], check=True
            )
            if frontend_path.exists():
                logger.info("Frontend submodule initialized successfully.")
            else:
                logger.error(
                    "Frontend files are still missing after submodule initialization.\n"
                    + "Did you manually change or delete the `frontend` folder?\n"
                    + "It's a Git submodule — you shouldn't modify it directly.\n"
                    + "If you did, discard your changes with `git restore frontend`, then try again.\n"
                )
        except Exception as e:
            logger.error(f"Failed to initialize submodules: {e}")


def parse_args():
    parser = argparse.ArgumentParser(description="TheProjectYin Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--hf_mirror", action="store_true", help="Use Hugging Face mirror"
    )
    return parser.parse_args()


@logger.catch
def run(console_log_level: str):
    init_logger(console_log_level)
    logger.info(f"TheProjectYin, version v{get_version()}")

    # Check if the frontend submodule is initialized
    check_frontend_submodule()

    atexit.register(WebSocketServer.clean_cache)

    # Load configurations from yaml file
    config: Config = validate_config(read_yaml("conf.yaml"))
    server_config = config.system_config

    if server_config.enable_proxy:
        logger.info("Proxy mode enabled - /proxy-ws endpoint will be available")

    # Initialize the WebSocket server (synchronous part)
    server = WebSocketServer(config=config)

    # Perform asynchronous initialization (loading context, etc.)
    logger.info("Initializing server context...")
    try:
        asyncio.run(server.initialize())
        logger.info("Server context initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize server context: {e}")
        sys.exit(1)  # Exit if initialization fails

    # Run the Uvicorn server
    logger.info(f"Starting server on {server_config.host}:{server_config.port}")
    uvicorn.run(
        app=server.app,
        host=server_config.host,
        port=server_config.port,
        log_level=console_log_level.lower(),
    )


if __name__ == "__main__":
    args = parse_args()
    console_log_level = "DEBUG" if args.verbose else "INFO"
    if args.verbose:
        logger.info("Running in verbose mode")
    else:
        logger.info(
            "Running in standard mode. For detailed debug logs, use: python run_server.py --verbose"
        )
    if args.hf_mirror:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    run(console_log_level=console_log_level)




