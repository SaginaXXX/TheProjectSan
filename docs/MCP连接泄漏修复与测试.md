# MCP连接泄漏修复与测试指南

## 🎯 问题诊断

**症状**：
- 后端持续运行
- 前端打开/关闭几次后，响应时间从3秒增加到6-9秒
- 只有重启Docker才能恢复

**根本原因**：**MCP服务器进程累积**

每次前端连接时，系统会：
1. 创建新的 `ServiceContext`
2. 初始化新的 `MCPClient`
3. 启动5个MCP服务器进程（你配置的服务器数量）
4. Warm up这5个服务器连接

如果旧的`MCPClient`没有被正确清理：
```
第1次连接：5个MCP进程 ✓
第2次连接：5个新进程 + 5个旧进程（残留）= 10个
第3次连接：15个进程  ← 响应变慢
第4次连接：20个进程  ← 响应非常慢（6-9秒）
```

## ✅ 修复内容

### 1. 增强MCP Client关闭逻辑 (`mcp_client.py`)

**修改前**：
```python
async def aclose(self):
    await self.exit_stack.aclose()  # 可能失败但不报错
    self.active_sessions.clear()
```

**修改后**：
```python
async def aclose(self):
    # ✅ 显式关闭每个session（确保服务器进程被终止）
    for server_name, session in list(self.active_sessions.items()):
        try:
            await asyncio.wait_for(session.close(), timeout=2.0)
        except Exception as e:
            logger.warning(f"关闭session '{server_name}' 失败: {e}")
    
    # 清理exit_stack
    await self.exit_stack.aclose()
    
    # 清空所有引用
    self.active_sessions.clear()
    self._list_tools_cache.clear()
```

**作用**：强制终止所有MCP服务器进程，不留残留

---

### 2. ServiceContext关闭时增加诊断 (`service_context.py`)

```python
async def close(self):
    if self.mcp_client:
        logger.info(f"🔍 活跃MCP sessions: {len(self.mcp_client.active_sessions)}")
        logger.info(f"🔍 Sessions: {list(self.mcp_client.active_sessions.keys())}")
        
        try:
            await asyncio.wait_for(self.mcp_client.aclose(), timeout=5.0)
            logger.info("✅ MCPClient已关闭")
        except asyncio.TimeoutError:
            logger.error("❌ MCPClient关闭超时！可能有服务器进程残留")
```

**作用**：监控MCP Client的清理过程，发现问题

---

### 3. 防御性检查：初始化前清理旧Client (`service_context.py`)

```python
async def _init_mcp_components(self, use_mcpp, enabled_servers):
    # ✅ 如果检测到旧MCP Client未清理，先关闭
    if self.mcp_client:
        logger.warning("⚠️ 检测到旧MCP Client未清理，先关闭...")
        logger.info(f"🔍 旧Client活跃sessions: {len(self.mcp_client.active_sessions)}")
        try:
            await asyncio.wait_for(self.mcp_client.aclose(), timeout=3.0)
        except Exception as e:
            logger.error(f"❌ 清理旧MCP Client失败: {e}")
    
    # 然后再创建新的
    self.mcp_client = MCPClient(...)
```

**作用**：防止在创建新Client前有旧Client残留

---

## 🧪 测试步骤

### 步骤1：启动后端并观察初始状态

```bash
# 进入项目目录
cd d:\Codes\AAII\TheProjectSan

# 启动后端（假设在Docker中）
docker-compose up

# 或直接启动Python
python run_server.py
```

**观察日志**：
```
✅ ServerRegistry initialized or referenced.
✅ Dynamically generated MCP prompt string (length: ...)
✅ ToolManager initialized with dynamically fetched tools.
MCPC: Initialized MCPClient instance.
```

---

### 步骤2：第一次连接测试

1. **打开网页**（假设 http://localhost:12393）
2. **说一句话**，等待回复
3. **记录时间**：___ 秒

**观察日志（关键诊断点）**：
```
♻️ 复用现有MCP组件 (client_uid: ...)
或
🔧 初始化新的MCP组件 (client_uid: ...)
```

---

### 步骤3：关闭网页（第一次）

**关闭浏览器标签页**

**观察日志（关键！）**：
```
🔌 开始清理客户端 xxx 的资源...
Closing MCPClient for context instance ...
  🔍 活跃MCP sessions: 5
  🔍 Sessions: ['laundry-assistant', 'advertisement-server', 'time', 'weather-server', 'fukuoka-transit']
  🔍 Sessions to close: [...]
  🔄 关闭 session: laundry-assistant
  🔄 关闭 session: advertisement-server
  ...
  ✅ exit_stack已清理
  ✅ MCPClient已关闭
✅ 客户端 xxx 资源清理完成
```

**❌ 如果看到错误**：
```
❌ MCPClient关闭超时！可能有服务器进程残留
或
⚠️ 关闭session 'xxx' 失败: ...
```
→ **说明清理失败，进程会累积**

---

### 步骤4：重复测试（关键！）

**重复3-5次**：
1. 打开网页
2. 说一句话
3. 记录响应时间
4. 关闭网页
5. 观察日志中的清理过程

**记录响应时间**：
```
第1次: ___ 秒
第2次: ___ 秒
第3次: ___ 秒
第4次: ___ 秒
第5次: ___ 秒
```

**预期结果**：
- ✅ **修复成功**：时间保持稳定（3-4秒）
- ❌ **仍有问题**：时间逐渐增加（3→4→6→8秒）

---

### 步骤5：进程检查（Linux/Mac）

```bash
# 查找MCP服务器进程
ps aux | grep -E "(laundry|advertisement|time|weather|fukuoka)"

# 统计进程数量
ps aux | grep -E "(laundry|advertisement|time|weather|fukuoka)" | wc -l
```

**预期**：
- 第1次连接后：5个进程
- 关闭网页后：0个进程（或很快降到0）
- 第2次连接后：5个进程
- 关闭网页后：0个进程

**❌ 问题情况**：
- 关闭网页后进程数不减少
- 每次连接后进程数累积增加

---

### 步骤6：Docker环境检查（如果使用Docker）

```bash
# 查看Docker容器的进程
docker exec <container_name> ps aux

# 查看容器资源占用
docker stats <container_name>
```

观察CPU和内存是否随着连接次数增加而增长。

---

## 📊 诊断结果判断

### 情况A：修复成功 ✅

**日志表现**：
```
每次关闭网页时：
  ✅ MCPClient已关闭
  ✅ exit_stack已清理
  所有sessions正常关闭
```

**性能表现**：
- 响应时间稳定（3-4秒）
- 进程数稳定（连接时5个，断开后0个）
- 内存占用稳定

**结论**：MCP连接泄漏已修复 ✅

---

### 情况B：部分修复 ⚠️

**日志表现**：
```
偶尔出现：
  ⚠️ 关闭session 'xxx' 失败
  但大部分sessions正常关闭
```

**性能表现**：
- 响应时间轻微增加（3→4→5秒）
- 进程偶尔残留

**需要**：
- 检查特定MCP服务器的稳定性
- 可能需要增加超时时间或重试机制

---

### 情况C：仍有问题 ❌

**日志表现**：
```
频繁出现：
  ❌ MCPClient关闭超时
  ⚠️ 多个sessions关闭失败
  或者根本没有看到清理日志
```

**性能表现**：
- 响应时间持续增加（3→6→9秒）
- 进程数累积（5→10→15→20）

**可能原因**：
1. `context.close()` 没有被正确调用
2. `handle_disconnect` 逻辑有问题
3. 某个MCP服务器无法正常关闭

**下一步诊断**：需要检查 `websocket_handler.handle_disconnect` 的调用流程

---

## 🔧 如果修复失败的备选方案

### 方案1：复用MCP组件（单用户优化）

对于单用户LED屏幕场景，可以让所有连接共享同一套MCP组件：

```python
# websocket_handler.py
async def _init_service_context(self, send_text, client_uid):
    # 复用default_context的MCP组件，避免重复创建
    await session_service_context.load_cache(
        # ... 其他组件
        mcp_client=self.default_context_cache.mcp_client,  # ← 复用
        tool_manager=self.default_context_cache.tool_manager,
        tool_executor=self.default_context_cache.tool_executor,
    )
```

**优点**：
- 完全避免MCP连接累积
- 连接速度更快（无需重新初始化）
- 适合单用户场景

**缺点**：
- 多用户场景可能有状态冲突
- 需要修改 `load_cache` 方法签名

---

### 方案2：禁用不必要的MCP服务器

如果某些MCP服务器不常用，可以暂时禁用：

```yaml
# conf.yaml
mcp_enabled_servers: ["time", "weather-server"]  # 只启用必需的
```

**减少**：
- 每次连接只启动2个进程而非5个
- 降低泄漏风险

---

### 方案3：增加MCP服务器健康检查和自动重启

```python
# 定期检查并清理僵尸MCP进程
async def health_check_mcp_servers(self):
    for server_name, session in self.active_sessions.items():
        try:
            await session.ping()  # 如果支持
        except:
            # 重启该服务器
            await self._restart_server(server_name)
```

---

## 📝 测试记录模板

```
测试日期：2025-10-08
后端版本：[commit hash]
Docker环境：是/否

| 连接次数 | 响应时间 | 进程数 | MCPClient关闭状态 | 备注 |
|---------|---------|--------|------------------|------|
| 1       | 3s      | 5      | ✅ 成功          |      |
| 2       | 3s      | 5      | ✅ 成功          |      |
| 3       | 4s      | 5      | ⚠️ 部分失败      |      |
| 4       | 6s      | 10     | ❌ 超时          | 有残留|
| 5       | 9s      | 15     | ❌ 超时          | 严重累积|

结论：[修复成功/部分成功/失败]
```

---

## 🎉 预期效果

修复后，你应该能：
1. ✅ 重复打开/关闭网页10+次，响应时间保持稳定
2. ✅ 无需重启Docker，系统可持续运行数天
3. ✅ 每次断开连接后，所有MCP服务器进程被正确终止
4. ✅ 内存和CPU占用保持稳定

---

**准备好测试了吗？请按照步骤1-5进行测试，并告诉我结果！** 🚀

