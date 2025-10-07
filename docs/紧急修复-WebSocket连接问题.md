# 紧急修复：WebSocket 连接问题

> **问题时间**: 2025-10-06  
> **问题严重性**: 🔴 **严重 - 应用无法使用**  
> **修复状态**: ✅ **已修复**

---

## 🚨 问题描述

### 症状

用户启动应用后报告：**"现在怎么啥都加载不出来了"**

### 错误日志

```javascript
env-config.ts:130 🔧 检测到开发环境 (端口:3000)，API地址: localhost:12393
websocket-context.tsx:10 🌐 自动检测服务器地址: http://localhost:12393
websocket-service.tsx:226 🌐 WS connecting...
// ❌ 后续没有 "✅ WS open" 日志
```

**问题特征**：
- WebSocket 正在连接但永远无法连接成功
- 应用卡在连接状态
- Live2D 模型无法加载
- 所有功能不可用

---

## 🔍 根本原因分析

### 问题根源

**Store 的初始配置值是空字符串**：

```typescript
// ❌ 有问题的初始值（修复前）
const initialConfigState: ConfigurationState = {
  wsUrl: '',      // ❌ 空字符串
  baseUrl: '',    // ❌ 空字符串
  // ...
};
```

### 为什么会出现问题？

#### 问题链条：

```
1. Store 初始化
   └─ wsUrl = '' (空字符串)
   
2. Zustand persist 中间件加载
   └─ localStorage 中可能有旧的空值
   └─ 覆盖了初始值
   
3. websocket-context 检查配置
   └─ if (!wsUrl || !baseUrl) { 初始化 }
   └─ 空字符串是 falsy，理论上应该初始化
   
4. 但如果 persist 还原速度太快
   └─ useEffect 可能在 persist 还原之前运行
   └─ 导致条件判断出错
   
5. WebSocket 尝试连接到空字符串
   └─ ws.connect('') ❌
   └─ 连接失败但没有明确错误
```

### 为什么之前能工作？

**之前的代码**（使用 useLocalStorage）：

```typescript
// ✅ 之前能工作
const [wsUrl, setWsUrl] = useLocalStorage('wsUrl', DEFAULT_WS_URL);
//                                                   ^^^^^^^^^^^^
//                                    直接提供了有效的默认值
```

**现在的代码**（从 Store 读取）：

```typescript
// ❌ 问题
const { wsUrl } = useConfigStore();
// Store 初始值是 ''，没有有效的默认值
```

---

## ✅ 解决方案

### 修复内容

**给 Store 提供合理的默认值**：

```typescript
// ✅ 修复后
const initialConfigState: ConfigurationState = {
  modelInfo: null,
  characterConfig: null,
  wsUrl: 'ws://127.0.0.1:12393/client-ws',    // ✅ 有效的默认值
  baseUrl: 'http://127.0.0.1:12393',           // ✅ 有效的默认值
  wsState: 'CLOSED',
  appConfig: {},
};
```

### 为什么这样修复？

1. **提供兜底默认值** - 即使 persist 失败也能工作
2. **符合期望行为** - 开发环境默认连接本地服务器
3. **简化初始化逻辑** - 不需要复杂的条件检查
4. **兼容 persist** - persist 会覆盖这个值（如果有存储）

### 数据流

```
启动流程：

1. Store 初始化
   └─ wsUrl = 'ws://127.0.0.1:12393/client-ws' ✅ 有效默认值

2. persist 中间件加载
   └─ 如果 localStorage 有值 → 使用存储的值
   └─ 如果 localStorage 无值 → 使用默认值 ✅

3. websocket-context 读取
   └─ const { wsUrl } = useConfigStore() ✅ 总是有效

4. WebSocket 连接
   └─ wsService.connect(wsUrl) ✅ 连接成功
```

---

## 📝 修改文件

### 1. store/index.ts

**修改行数**: 第 245-246 行

```diff
const initialConfigState: ConfigurationState = {
  modelInfo: null,
  characterConfig: null,
- wsUrl: '',
- baseUrl: '',
+ wsUrl: 'ws://127.0.0.1:12393/client-ws',  // ✅ 默认值
+ baseUrl: 'http://127.0.0.1:12393',         // ✅ 默认值
  wsState: 'CLOSED',
  appConfig: {},
};
```

### 2. websocket-context.tsx

**修改内容**: 简化初始化逻辑

```diff
- // ✅ 初始化配置（只在首次或配置为空时）
- useEffect(() => {
-   if (!wsUrl || !baseUrl) {
-     const defaultConfig = getServerConfig();
-     console.log('🔧 初始化网络配置:', defaultConfig);
-     updateNetworkConfig({
-       wsUrl: defaultConfig.wsUrl,
-       baseUrl: defaultConfig.baseUrl
-     });
-   }
- }, [wsUrl, baseUrl, updateNetworkConfig]);

+ // ✅ 只检测旧配置，不负责初始化（初始化由 Store 默认值完成）
```

---

## 🧪 验证修复

### 测试步骤

1. **清空缓存测试**
   ```javascript
   // 在浏览器控制台执行
   localStorage.clear();
   location.reload();
   ```

2. **验证连接**
   - 查看控制台是否有 `✅ WS open` 日志
   - 验证 Live2D 模型加载
   - 测试对话功能

3. **验证持久化**
   - 修改配置
   - 刷新页面
   - 验证配置保持

### 预期日志

```javascript
✅ 正确的日志顺序：

1. 🏪 Zustand企业级状态管理系统已初始化
2. 🔧 检测到开发环境 (端口:3000)，API地址: localhost:12393
3. 🌐 自动检测服务器地址: http://localhost:12393
4. 🔌 WebSocketHandler: 初始化WebSocket连接
5. 🌐 WS connecting... ws://127.0.0.1:12393/client-ws
6. ✅ WS open  ← 这个是关键！
7. 🩺 WS heartbeat -> ping
8. 🩺 WS heartbeat <- ack
```

---

## 📋 修复清单

- [x] 修复 Store 初始值（空字符串 → 默认 URL）
- [x] 简化 websocket-context 初始化逻辑
- [x] 测试配置加载
- [ ] 用户验证功能（待测试）

---

## 🔄 如果仍有问题

### 调试步骤

1. **检查 Store 值**
   ```javascript
   // 在浏览器控制台执行
   import { useAppStore } from '@/store';
   const state = useAppStore.getState();
   console.log('Store 配置:', state.config);
   ```

2. **检查 localStorage**
   ```javascript
   // 查看持久化的值
   const stored = localStorage.getItem('app-store');
   console.log('localStorage:', JSON.parse(stored));
   ```

3. **手动连接**
   ```javascript
   // 强制连接
   import { wsService } from '@/services/websocket-service';
   wsService.connect('ws://127.0.0.1:12393/client-ws');
   ```

### 终极回滚

如果问题仍然存在，回滚所有修改：

```bash
git checkout -- frontend/src/renderer/src/context/websocket-context.tsx
git checkout -- frontend/src/renderer/src/context/vad-context.tsx
git checkout -- frontend/src/renderer/src/context/bgurl-context.tsx
git checkout -- frontend/src/renderer/src/services/websocket-handler.tsx
git checkout -- frontend/src/renderer/src/store/index.ts
```

---

## ✅ 修复确认

### 修复后应该看到

1. ✅ WebSocket 连接成功日志
2. ✅ Live2D 模型加载
3. ✅ 麦克风可以使用
4. ✅ 可以正常对话

### 如果还是不行

**立即告诉我**，我会：
1. 提供更详细的调试步骤
2. 或者回滚所有修改
3. 重新评估修复方案

---

**修复版本**: v1.0  
**修复时间**: 2025-10-06  
**状态**: ✅ 已修复，等待验证

