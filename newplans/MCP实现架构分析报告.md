# MCP 实现架构分析报告

## 📋 目录
1. [概述](#概述)
2. [前端MCP画布实现](#前端mcp画布实现)
3. [后端MCP系统实现](#后端mcp系统实现)
4. [数据流与通信机制](#数据流与通信机制)
5. [关键组件详解](#关键组件详解)
6. [实现准备建议](#实现准备建议)

---

## 概述

### MCP (Model Context Protocol) 系统架构

MCP系统是一个完整的工具调用框架，允许AI Agent通过标准化的协议调用外部工具，并将结果以可视化方式展示在Live2D人物上方的第二块画布上。

### 核心设计理念

1. **双层画布架构**
   - **主画布**：Live2D人物渲染
   - **MCP画布**：浮动在人物上方，展示工具返回的内容（图片/视频/地图）

2. **信号模式通信**
   - 前端直接发送工具调用请求
   - 后端执行并返回结果
   - 前端自动显示内容，无需查询状态

3. **内容类型支持**
   - `image`: 图片内容
   - `video`: 视频内容
   - `map`: 地图内容（待实现）

---

## 前端MCP画布实现

### 1. 核心组件结构

```
frontend/src/renderer/src/components/mcp/
├── mcp-canvas.tsx          # 主画布组件
├── mcp-canvas-content.tsx  # 内容渲染组件
└── mcp-canvas-controls.tsx  # 调试模式控制组件
```

### 2. MCP Canvas 主组件 (`mcp-canvas.tsx`)

#### 功能特性

- **自动显示/隐藏**：根据MCP状态和广告播放状态自动控制
- **智能定位**：默认定位在Live2D胸口位置（容器高度的35%，水平55%）
- **vpDebug模式**：支持拖拽调整位置和尺寸（按住Shift键激活）
- **事件穿透控制**：无内容时事件穿透，有内容时可交互

#### 关键状态管理

```typescript
// 从Zustand Store订阅的状态
const isVisible = useAppStore((s) => s.mcp?.isVisible ?? false);
const contentType = useAppStore((s) => s.mcp?.contentType);
const contentData = useAppStore((s) => s.mcp?.contentData);
const position = useAppStore((s) => s.mcp?.position ?? { x: 0, y: 0 });
const size = useAppStore((s) => s.mcp?.size ?? { width: 400, height: 300 });
```

#### 渲染条件

```typescript
const shouldRender = useMemo(() => {
  // vpDebug模式：即使无内容也显示（用于调试定位）
  if (vpDebug && modelInfo !== null && !showAdvertisements) {
    return true;
  }
  
  // 正常模式：只有有内容时才显示
  return (
    isVisible &&
    !showAdvertisements &&  // 广告不播放时才显示
    modelInfo !== null      // Live2D已加载
  );
}, [vpDebug, isVisible, showAdvertisements, modelInfo]);
```

#### vpDebug模式控制

- **Shift键激活**：按住Shift键时激活拖拽模式
- **控制手柄**：显示四角和中心拖拽点
- **位置持久化**：调整后的位置和尺寸保存到Zustand Store

### 3. MCP Canvas 内容组件 (`mcp-canvas-content.tsx`)

#### 支持的内容类型

**图片内容 (`ImageContent`)**
- 支持加载状态和错误处理
- 自动适应容器尺寸 (`objectFit: contain`)
- 可选的标题和描述文字

**视频内容 (`VideoContent`)**
- 自动播放控制
- 播放时暂停AI说话（`setAiState('waiting')`）
- 播放结束后自动关闭画布
- 支持循环播放和静音

**地图内容 (`MapContent`)**
- 当前为占位实现
- TODO: 集成Leaflet地图库
- 支持经纬度、缩放级别、标记点

### 4. 状态管理 (`store/slices/mcp-slice.ts`)

#### MCP状态结构

```typescript
interface MCPState {
  // 画布显示状态
  isVisible: boolean;
  contentType: MCPContentType;  // 'image' | 'video' | 'map' | null
  contentData: MCPContentData | null;
  
  // 位置和尺寸（vpDebug模式下可调整）
  position: { x: number; y: number };
  size: { width: number; height: number };
  
  // 视频播放状态
  isVideoPlaying: boolean;
}
```

#### 关键方法

- `showMCPContent(contentType, contentData)`: 显示MCP内容
- `hideMCPContent()`: 隐藏MCP内容（延迟清空，保持动画）
- `updateMCPPosition(x, y)`: 更新画布位置
- `updateMCPSize(width, height)`: 更新画布尺寸
- `setMCPVideoPlaying(playing)`: 设置视频播放状态

### 5. 定位Hook (`hooks/mcp/use-mcp-position.ts`)

#### 定位逻辑

1. **优先使用存储位置**：如果`storedPosition`有有效值（vpDebug调整过），使用存储位置
2. **默认计算位置**：
   - 水平：容器宽度的55%（居中偏右）
   - 垂直：容器高度的35%（胸口位置）
3. **响应式更新**：监听窗口和容器大小变化

### 6. 拖拽调整Hook (`hooks/mcp/use-mcp-resize.ts`)

#### 功能

- **移动**：拖拽中心区域移动画布
- **调整尺寸**：拖拽四角调整大小
  - `tl`: 左上角
  - `tr`: 右上角
  - `bl`: 左下角
  - `br`: 右下角
- **最小尺寸限制**：宽度200px，高度150px
- **位置持久化**：调整后保存到Zustand Store

---

## 后端MCP系统实现

### 1. 核心组件架构

```
src/ai_chat/mcpp/
├── mcp_client.py          # MCP客户端（管理服务器连接）
├── tool_executor.py       # 工具执行器（执行工具调用）
├── tool_manager.py        # 工具管理器（管理工具信息）
├── tool_adapter.py        # 工具适配器（格式化工具信息）
├── server_registry.py     # 服务器注册表（管理MCP服务器）
├── advertisement_server.py # 广告服务器（示例MCP服务器）
├── time_server.py         # 时间服务器（示例MCP服务器）
├── weather_server.py      # 天气服务器（示例MCP服务器）
└── mcp_text_server.py     # 文本服务器（示例MCP服务器）
```

### 2. MCP Client (`mcp_client.py`)

#### 核心功能

- **多服务器管理**：维护多个MCP服务器的连接
- **连接池管理**：复用连接，避免重复创建
- **工具缓存**：缓存`list_tools`结果，提高性能
- **错误重试**：自动重试失败的连接和调用

#### 关键方法

```python
async def list_tools(server_name: str) -> List[Tool]:
    """列出指定服务器的所有工具（带缓存）"""
    
async def call_tool(
    server_name: str, 
    tool_name: str, 
    tool_args: Dict[str, Any]
) -> Dict[str, Any]:
    """调用工具并返回结果"""
    # 返回格式：
    # {
    #     "metadata": {...},
    #     "content_items": [
    #         {"type": "text", "text": "..."},
    #         {"type": "image", "data": "...", "mimeType": "..."},
    #         ...
    #     ]
    # }
```

#### 连接管理

- **延迟连接**：首次调用工具时才建立连接
- **连接复用**：同一服务器的多个工具调用复用连接
- **自动清理**：连接失败时自动清理并重试

### 3. Tool Executor (`tool_executor.py`)

#### 核心功能

- **工具调用解析**：支持多种格式的工具调用
- **异步执行**：使用`AsyncIterator`流式返回状态更新
- **结果格式化**：为不同LLM模式（Claude/OpenAI/Prompt）格式化结果
- **内容类型处理**：处理文本、图片、视频等多种内容类型

#### 执行流程

```python
async def execute_tools(
    tool_calls: List[Dict],
    caller_mode: Literal["Claude", "OpenAI", "Prompt"]
) -> AsyncIterator[Dict]:
    """执行工具并流式返回状态更新"""
    
    for call in tool_calls:
        # 1. 解析工具调用
        tool_name, tool_id, tool_input = parse_tool_call(call)
        
        # 2. 发送"running"状态
        yield {"type": "tool_call_status", "status": "running", ...}
        
        # 3. 执行工具
        is_error, text_content, metadata, content_items = await run_single_tool(...)
        
        # 4. 发送"completed"或"error"状态
        yield {"type": "tool_call_status", "status": "completed", ...}
        
        # 5. 格式化结果供LLM使用
        formatted_result = format_tool_result(...)
    
    # 6. 发送最终结果
    yield {"type": "final_tool_results", "results": [...]}
```

#### 内容类型处理

- **文本内容**：直接返回文本
- **图片内容**：
  - Claude模式：转换为base64图片块
  - OpenAI/Prompt模式：返回文本描述
- **错误处理**：统一的错误格式和状态更新

### 4. Tool Manager (`tool_manager.py`)

#### 功能

- **工具注册**：管理所有可用工具的信息
- **服务器映射**：维护工具到服务器的映射关系
- **工具查询**：根据工具名查找工具信息和服务器

### 5. Tool Adapter (`tool_adapter.py`)

#### 功能

- **工具格式化**：将MCP工具格式转换为LLM可用的格式
- **Prompt生成**：生成MCP工具说明的Prompt字符串
- **多格式支持**：支持OpenAI和Claude两种格式

### 6. Server Registry (`server_registry.py`)

#### 功能

- **服务器注册**：注册MCP服务器配置
- **服务器查询**：根据名称查询服务器配置
- **配置管理**：管理服务器的启动参数、环境变量等

### 7. WebSocket处理 (`websocket_handler.py`)

#### MCP工具调用处理

```python
async def _handle_mcp_tool_call(
    self, websocket: WebSocket, client_uid: str, data: WSMessage
) -> None:
    """处理前端发起的MCP工具调用"""
    
    tool_name = data.get("tool_name")
    arguments = data.get("arguments", {})
    
    # 获取服务上下文
    context = self.client_contexts.get(client_uid)
    
    # 执行工具调用
    tool_calls = [{
        "name": tool_name,
        "args": arguments,
        "id": f"ws_{tool_name}_{timestamp}"
    }]
    
    # 使用ToolExecutor执行
    async for update in context.tool_executor.execute_tools(
        tool_calls=tool_calls,
        caller_mode="Prompt"
    ):
        if update.get("type") == "final_tool_results":
            # 发送最终结果
            await websocket.send_json({
                "type": "mcp-tool-response",
                "tool_name": tool_name,
                "result": update.get("results", [])
            })
```

---

## 数据流与通信机制

### 1. 工具调用流程

```
前端 (React)
  ↓ WebSocket发送
  {
    "type": "mcp-tool-call",
    "tool_name": "get_weather",
    "arguments": {"location": "北京"}
  }
  ↓
后端 WebSocketHandler
  ↓ 路由到_handle_mcp_tool_call
  ↓
ToolExecutor.execute_tools()
  ↓ 解析工具调用
  ↓
MCPClient.call_tool()
  ↓ 调用MCP服务器
  ↓
MCP服务器执行工具
  ↓ 返回结果
  {
    "metadata": {...},
    "content_items": [
      {"type": "text", "text": "..."},
      {"type": "image", "data": "...", "mimeType": "image/png"}
    ]
  }
  ↓
ToolExecutor格式化结果
  ↓
WebSocket发送响应
  {
    "type": "mcp-tool-response",
    "tool_name": "get_weather",
    "result": {
      "content": {
        "type": "image",
        "data": {...}
      }
    }
  }
  ↓
前端 WebSocketHandler
  ↓ 处理mcp-tool-response消息
  ↓
调用showMCPContent(type, data)
  ↓
更新Zustand Store
  ↓
MCPCanvas自动显示内容
```

### 2. 前端消息处理

```typescript
case "mcp-tool-response":
  const { tool_name, result, error } = message;
  
  if (error) {
    // 显示错误提示
    toaster.create({...});
    break;
  }
  
  if (result && result.content) {
    const { type, data } = result.content;
    
    // 调用Store方法显示MCP内容
    showMCPContent(type, data);
  }
  break;
```

### 3. 内容显示流程

```
showMCPContent(contentType, contentData)
  ↓
更新Zustand Store
  {
    mcp: {
      isVisible: true,
      contentType: 'image',
      contentData: {...}
    }
  }
  ↓
MCPCanvas订阅状态变化
  ↓
自动渲染对应内容组件
  - ImageContent (图片)
  - VideoContent (视频)
  - MapContent (地图)
```

---

## 关键组件详解

### 1. ServiceContext中的MCP初始化

```python
async def _init_mcp_components(self, use_mcpp, enabled_servers):
    """初始化MCP组件"""
    
    # 1. 创建ServerRegistry
    self.mcp_server_registery = ServerRegistry()
    
    # 2. 通过ToolAdapter获取工具信息
    mcp_prompt_string, openai_tools, claude_tools = \
        await self.tool_adapter.get_tools(enabled_servers)
    
    # 3. 创建ToolManager
    self.tool_manager = ToolManager(
        formatted_tools_openai=openai_tools,
        formatted_tools_claude=claude_tools,
        initial_tools_dict=raw_tools_dict,
    )
    
    # 4. 创建MCPClient
    self.mcp_client = MCPClient(
        self.mcp_server_registery,
        send_text=self._send_text,
        client_uid=self.client_uid
    )
    
    # 5. 创建ToolExecutor
    self.tool_executor = ToolExecutor(
        self.mcp_client,
        self.tool_manager
    )
    
    # 6. 预热MCP服务器
    for server_name in enabled_servers:
        await self.mcp_client.list_tools(server_name)
```

### 2. MCP服务器示例：广告服务器

```python
# advertisement_server.py
# 提供广告视频查询和播放列表功能

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="get_advertisement_list",
            description="获取广告视频列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            }
        ),
        Tool(
            name="refresh_advertisements",
            description="刷新广告列表",
            inputSchema={"type": "object", "properties": {}}
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent | ImageContent]:
    if name == "get_advertisement_list":
        # 返回广告列表
        return [TextContent(...)]
    elif name == "refresh_advertisements":
        # 刷新广告列表
        return [TextContent(...)]
```

### 3. 工具调用在对话中的集成

在Agent对话流程中，当LLM决定调用工具时：

```python
# 在Agent的流式输出中
for output in agent.chat(batch_input):
    if isinstance(output, ToolCallOutput):
        # 工具调用
        tool_calls = output.tool_calls
        
        # 使用ToolExecutor执行
        async for status in tool_executor.execute_tools(
            tool_calls=tool_calls,
            caller_mode="Claude"  # 或 "OpenAI"
        ):
            # 发送工具状态更新
            await websocket.send_json({
                "type": "tool_call_status",
                **status
            })
            
            # 如果是最终结果，继续对话
            if status.get("type") == "final_tool_results":
                # 将工具结果添加到对话上下文
                # 继续生成回复
```

---

## 实现准备建议

### 1. 前端实现准备

#### ✅ 已完成的基础设施

- [x] MCP Canvas组件（显示/隐藏、定位、拖拽）
- [x] 内容渲染组件（图片/视频/地图）
- [x] Zustand状态管理（MCP状态、位置、尺寸）
- [x] WebSocket消息处理（mcp-tool-response）
- [x] 定位和拖拽Hooks

#### 🔧 需要完善的功能

1. **地图功能实现**
   - [ ] 集成Leaflet地图库
   - [ ] 实现地图标记和交互
   - [ ] 支持地图样式自定义

2. **内容类型扩展**
   - [ ] 支持更多内容类型（如HTML、Markdown）
   - [ ] 支持内容组合（图片+文字、视频+文字）

3. **交互增强**
   - [ ] 支持内容点击事件
   - [ ] 支持内容滚动（长内容）
   - [ ] 支持内容缩放

4. **性能优化**
   - [ ] 图片懒加载
   - [ ] 视频预加载控制
   - [ ] 内容缓存机制

### 2. 后端实现准备

#### ✅ 已完成的基础设施

- [x] MCP Client（多服务器管理、连接池）
- [x] Tool Executor（工具执行、结果格式化）
- [x] Tool Manager（工具注册、查询）
- [x] Tool Adapter（工具格式化、Prompt生成）
- [x] Server Registry（服务器注册、配置管理）
- [x] WebSocket处理（mcp-tool-call消息处理）

#### 🔧 需要完善的功能

1. **工具调用优化**
   - [ ] 工具调用超时控制
   - [ ] 工具调用重试机制
   - [ ] 工具调用结果缓存

2. **内容类型支持**
   - [ ] 支持更多MCP内容类型
   - [ ] 内容URL验证和安全性检查
   - [ ] 内容大小限制

3. **错误处理**
   - [ ] 更详细的错误信息
   - [ ] 错误恢复机制
   - [ ] 错误日志记录

4. **性能优化**
   - [ ] 工具调用并发控制
   - [ ] 连接池大小优化
   - [ ] 工具列表缓存策略

### 3. MCP服务器开发准备

#### 示例服务器结构

```python
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent

server = Server("my-server")

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="my_tool",
            description="工具描述",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"}
                },
                "required": ["param1"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent | ImageContent]:
    if name == "my_tool":
        # 执行工具逻辑
        result = do_something(arguments["param1"])
        
        # 返回内容
        return [
            TextContent(type="text", text=result["text"]),
            ImageContent(
                type="image",
                data=result["image_data"],
                mimeType="image/png"
            )
        ]
```

#### 开发新MCP服务器的步骤

1. **创建服务器文件**（如`my_server.py`）
2. **定义工具列表**（`@server.list_tools()`）
3. **实现工具调用**（`@server.call_tool()`）
4. **注册到ServerRegistry**（在配置文件中）
5. **测试工具调用**（通过WebSocket或直接调用）

### 4. 测试建议

#### 前端测试

1. **组件测试**
   - MCP Canvas显示/隐藏
   - 内容渲染（图片/视频）
   - 拖拽调整（vpDebug模式）

2. **集成测试**
   - WebSocket消息处理
   - 状态管理更新
   - 内容显示流程

#### 后端测试

1. **单元测试**
   - MCP Client连接管理
   - Tool Executor工具执行
   - 结果格式化

2. **集成测试**
   - 完整工具调用流程
   - WebSocket消息处理
   - 错误处理

### 5. 文档建议

1. **API文档**
   - MCP工具调用接口
   - WebSocket消息格式
   - 内容类型定义

2. **开发指南**
   - 如何开发新MCP服务器
   - 如何在前端显示新内容类型
   - 如何调试工具调用

3. **使用示例**
   - 常见工具调用场景
   - 内容显示最佳实践
   - 性能优化建议

---

## 总结

MCP系统已经具备了完整的基础架构：

### 前端
- ✅ 完整的画布组件和内容渲染
- ✅ 状态管理和位置控制
- ✅ WebSocket消息处理

### 后端
- ✅ MCP Client和工具执行框架
- ✅ 多服务器管理和连接池
- ✅ WebSocket集成

### 下一步工作重点

1. **完善地图功能**：集成Leaflet，实现地图显示和交互
2. **扩展内容类型**：支持更多内容类型和组合
3. **优化性能**：缓存、懒加载、并发控制
4. **增强错误处理**：更详细的错误信息和恢复机制
5. **开发新工具**：根据需求开发新的MCP服务器和工具

系统已经为MCP功能的完整实现做好了充分准备！

