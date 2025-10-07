# WebSocket 连接泄漏修复方案

## 问题描述
网页端反复打开关闭多次后，回复速度变得很慢。

## 根本原因分析

### 1. **前端订阅累积问题**
- `websocket-handler.tsx` 中的 useEffect 依赖项包含 `wsUrl`，导致 URL 变化时会重新创建订阅
- RxJS Subject 订阅未完全清理，多次订阅后消息被重复处理
- WebSocket 连接管理不严格，可能创建重复连接

### 2. **前端连接管理问题**
- `websocket-service.tsx` 中的 `connect()` 方法没有检查是否已存在连接
- `disconnect()` 方法未彻底清理事件监听器，可能触发额外的重连
- 缺少对订阅数量的监控机制

### 3. **后端资源清理不够彻底**
- `handle_disconnect()` 中任务取消后未等待完成
- 缺少全局资源泄漏检测机制
- 日志不够详细，难以追踪清理过程

## 修复方案

### 前端修复 (frontend/src/renderer/src/)

#### 1. websocket-handler.tsx
**修改点：**
```typescript
// 分离连接管理和订阅管理
useEffect(() => {
  console.log('🔌 WebSocketHandler: 初始化WebSocket连接', wsUrl);
  wsService.connect(wsUrl);
  return () => {
    console.log('🔌 WebSocketHandler: 组件卸载，断开WebSocket连接');
    wsService.disconnect();
  };
}, [wsUrl]);

useEffect(() => {
  console.log('📡 WebSocketHandler: 设置订阅监听器');
  const stateSubscription = wsService.onStateChange(setWsState);
  const messageSubscription = wsService.onMessage(handleWebSocketMessage);
  
  // 开发环境下监控订阅数量
  if (process.env.NODE_ENV === 'development') {
    const monitorInterval = setInterval(() => {
      const counts = wsService.getSubscriptionCount();
      console.debug('📊 订阅监控:', counts);
      if (counts.message > 2 || counts.state > 2) {
        console.warn('⚠️  检测到订阅泄漏！订阅数量异常:', counts);
      }
    }, 30000);
    
    return () => {
      clearInterval(monitorInterval);
      stateSubscription.unsubscribe();
      messageSubscription.unsubscribe();
      const finalCounts = wsService.getSubscriptionCount();
      console.log('📊 清理后订阅数量:', finalCounts);
    };
  }
  
  return () => {
    stateSubscription.unsubscribe();
    messageSubscription.unsubscribe();
  };
}, [handleWebSocketMessage]); // ✅ 移除 wsUrl 依赖
```

**关键改进：**
- 分离连接管理和订阅管理为两个独立的 useEffect
- 从订阅 useEffect 中移除 wsUrl 依赖，避免重复订阅
- 添加订阅数量监控（开发环境）
- 添加详细日志便于调试

#### 2. websocket-service.tsx

**connect() 方法优化：**
```typescript
connect(url: string) {
  // ✅ 检查是否已连接到相同URL
  if (this.lastUrl === url && 
      (this.ws?.readyState === WebSocket.CONNECTING || 
       this.ws?.readyState === WebSocket.OPEN)) {
    console.warn('🔄 WS already connecting/connected - skipping duplicate');
    return;
  }

  // ✅ 先彻底清理旧连接
  if (this.ws) {
    console.info('🔄 WS closing existing connection before reconnect');
    this.disconnect();
    setTimeout(() => this._doConnect(url), 100);
    return;
  }

  this._doConnect(url);
}
```

**disconnect() 方法强化：**
```typescript
disconnect() {
  console.info('🔚 WS manual disconnect - cleaning up all resources');
  this.shouldReconnect = false;
  this.stopHeartbeat();
  
  if (this.reconnectTimer) {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
  }
  
  // ✅ 清理WebSocket连接
  if (this.ws) {
    try {
      // ✅ 移除所有事件监听器，防止触发额外的重连
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      
      if (this.ws.readyState === WebSocket.OPEN || 
          this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
    } catch (e) {
      console.warn('Error closing WebSocket:', e);
    }
    this.ws = null;
  }
  
  // ✅ 清空待发送消息队列
  this.outbox = [];
  
  // ✅ 更新状态
  this.currentState = 'CLOSED';
  this.stateSubject.next('CLOSED');
  
  console.info('✅ WS disconnect完成 - 所有资源已清理');
}
```

**订阅监控方法：**
```typescript
getSubscriptionCount() {
  return {
    message: this.messageSubject.observers.length,
    state: this.stateSubject.observers.length,
  };
}
```

### 后端修复 (src/ai_chat/)

#### websocket_handler.py

**handle_disconnect() 方法强化：**
```python
async def handle_disconnect(self, client_uid: str) -> None:
    """Handle client disconnection - 彻底清理所有资源防止泄漏"""
    logger.info(f"🔌 开始清理客户端 {client_uid} 的资源...")
    
    # 1. ✅ 先取消所有进行中的任务
    if client_uid in self.current_conversation_tasks:
        task = self.current_conversation_tasks[client_uid]
        if task and not task.done():
            logger.info(f"  ⏹️  取消进行中的对话任务 for {client_uid}")
            task.cancel()
            try:
                # ✅ 等待任务完全取消（最多2秒）
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"  ⚠️  任务取消时出错: {e}")
        self.current_conversation_tasks.pop(client_uid, None)
    
    # 2. ✅ 清理ServiceContext
    context = self.client_contexts.get(client_uid)
    if context:
        logger.info(f"  🗑️  清理 ServiceContext for {client_uid}")
        try:
            await context.close()
        except Exception as e:
            logger.error(f"  ❌ ServiceContext清理失败: {e}")
    
    # 3. ✅ 清理所有客户端相关状态
    self.client_connections.pop(client_uid, None)
    self.client_contexts.pop(client_uid, None)
    self.received_data_buffers.pop(client_uid, None)
    self._last_heartbeat.pop(client_uid, None)
    
    # 4. ✅ 清理外部管理器状态
    try:
        message_handler.cleanup_client(client_uid)
        logger.info(f"  ✅ 清理 message_handler for {client_uid}")
    except Exception as e:
        logger.warning(f"  ⚠️  message_handler清理失败: {e}")
    
    try:
        wake_word_manager.cleanup_client(client_uid)
        logger.info(f"  ✅ 清理 wake_word_manager for {client_uid}")
    except Exception as e:
        logger.warning(f"  ⚠️  wake_word_manager清理失败: {e}")

    logger.info(f"✅ 客户端 {client_uid} 资源清理完成. 剩余活跃连接: {len(self.client_connections)}")
    
    # 5. ✅ 全局清理检查
    if len(self.client_connections) == 0:
        logger.info("📊 所有客户端已断开，检查是否有残留资源...")
        if self.current_conversation_tasks:
            logger.warning(f"⚠️  发现残留任务: {list(self.current_conversation_tasks.keys())}")
            self.current_conversation_tasks.clear()
        if self.received_data_buffers:
            logger.warning(f"⚠️  发现残留音频缓冲: {list(self.received_data_buffers.keys())}")
            self.received_data_buffers.clear()
        if self._last_heartbeat:
            logger.warning(f"⚠️  发现残留心跳记录: {list(self._last_heartbeat.keys())}")
            self._last_heartbeat.clear()
```

**关键改进：**
- 任务取消后等待完成，避免资源继续被使用
- 详细的分步清理日志
- 全局资源泄漏检测
- 异常容错处理

## 验证方法

### 1. 开发环境监控
打开浏览器控制台，观察日志：
```
🔌 WebSocketHandler: 初始化WebSocket连接
📡 WebSocketHandler: 设置订阅监听器
📊 订阅监控: { message: 1, state: 1 }  // 正常
```

### 2. 反复打开/关闭测试
1. 打开网页，等待连接建立
2. 关闭网页
3. 重复 5-10 次
4. 观察日志中的订阅数量和清理过程

### 3. 后端日志检查
查看后端日志，确认每次断开都有完整的清理过程：
```
🔌 开始清理客户端 xxx 的资源...
  ⏹️  取消进行中的对话任务 for xxx
  🗑️  清理 ServiceContext for xxx
  ✅ 清理 message_handler for xxx
  ✅ 清理 wake_word_manager for xxx
✅ 客户端 xxx 资源清理完成. 剩余活跃连接: 0
```

## 预期效果

1. ✅ 不再有订阅累积
2. ✅ WebSocket 连接不会重复创建
3. ✅ 后端资源完全清理
4. ✅ 多次打开关闭后性能保持稳定
5. ✅ 回复速度不会变慢

## 监控指标

### 前端
- 订阅数量应保持在 1-2 个（message + state）
- 清理后订阅数应为 0 或 1（取决于是否有其他页面）
- WebSocket 连接状态应正确转换

### 后端
- 客户端断开后所有相关资源应被清理
- 活跃连接数应准确反映实际连接数
- 无残留任务、缓冲、心跳记录

## 注意事项

1. **不要在 useEffect 中混合连接和订阅管理** - 应分离为独立的 useEffect
2. **清理时顺序很重要** - 先取消任务，再清理上下文，最后清理状态
3. **事件监听器必须清除** - 防止触发意外的重连
4. **使用日志追踪** - 所有关键操作都应有日志

## 相关文件

### 前端
- `frontend/src/renderer/src/services/websocket-handler.tsx`
- `frontend/src/renderer/src/services/websocket-service.tsx`

### 后端
- `src/ai_chat/websocket_handler.py`
- `src/ai_chat/service_context.py`

## 未来优化建议

1. 考虑使用连接池管理 WebSocket 连接
2. 添加连接健康度检查
3. 实现更精细的资源使用监控
4. 添加自动化测试验证清理逻辑

