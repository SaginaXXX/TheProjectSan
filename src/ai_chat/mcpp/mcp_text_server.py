from mcp import StdioServerParameters
from mcp.server.stdio import stdio_server

"""mcp text server"""

# 默认配置路径
DEFAULT_CONFIG_PATH = "mcp_text_server.json"
# 默认配置
DEFAULT_CONFIG = {
    "name": "mcp_text_server",
    "description": "mcp text server",
    "version": "1.0.0",
    "author": "mcp_text_server",
    "license": "MIT",
    "repository": "https://github.com/mcp_text_server/mcp_text_server",
}

def deal_with_mcp_text_server():
    """deal with mcp text server"""

    # 创建MCP服务器
    server = stdio_server(StdioServerParameters(
        name=DEFAULT_CONFIG["name"], # 服务器名称
        description=DEFAULT_CONFIG["description"], # 服务器描述
        version=DEFAULT_CONFIG["version"], # 服务器版本
        author=DEFAULT_CONFIG["author"], # 服务器作者
        license=DEFAULT_CONFIG["license"], # 服务器许可证
        repository=DEFAULT_CONFIG["repository"], # 服务器仓库
    ))

# 运行MCP服务器
def Run_mcp_text_server():
    """run mcp text server"""
    deal_with_mcp_text_server()

# 
    







