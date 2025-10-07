# WebSocket 配置管理重构方案

## 问题描述

当前项目中存在状态管理层次混乱的问题：

1. **Zustand Store** 中定义了 `config.wsUrl` 和 `config.baseUrl`
2. **WebSocket Context** 却使用 `useLocalStorage` 自己管理这些配置
3. 导致：重复存储、数据不同步、职责不清

## 重构目标

1. **单一数据源原则** - 配置只存储在 Zustand Store 中
2. **清晰的职责分层** - env-config.ts 只负责初始检测，不负责持久化
3. **简化 Context** - WebSocket Context 只负责 WebSocket 连接，不管理配置

---

## 方案一：完全迁移到 Zustand（推荐）

### 步骤 1: 修改 `websocket-context.tsx`

**修改前（当前）：**

```typescript
// ❌ 问题代码
export const WebSocketProvider = ({ children }) => {
  const [wsUrl, setWsUrl] = useLocalStorage('wsUrl', DEFAULT_WS_URL);
  const [baseUrl, setBaseUrl] = useLocalStorage('baseUrl', DEFAULT_BASE_URL);
  
  const value = {
    sendMessage: wsService.sendMessage.bind(wsService),
    wsState: 'CLOSED',
    reconnect: () => wsService.connect(wsUrl),
    wsUrl,
    setWsUrl: handleSetWsUrl,
    baseUrl,
    setBaseUrl,
  };
  // ...
}
```

**修改后（推荐）：**

```typescript
// ✅ 重构后的代码
import { useConfigStore } from '@/store';

export const WebSocketProvider = ({ children }) => {
  // 从 Zustand Store 读取配置
  const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();
  
  // 只在首次挂载时初始化（如果 store 中没有值）
  useEffect(() => {
    if (!wsUrl || !baseUrl) {
      const defaultConfig = getServerConfig();
      updateNetworkConfig({
        wsUrl: defaultConfig.wsUrl,
        baseUrl: defaultConfig.baseUrl
      });
    }
  }, []);

  const handleSetWsUrl = useCallback((url: string) => {
    updateNetworkConfig({ wsUrl: url });
    wsService.connect(url);
  }, [updateNetworkConfig]);

  const handleSetBaseUrl = useCallback((url: string) => {
    updateNetworkConfig({ baseUrl: url });
  }, [updateNetworkConfig]);

  const value = {
    sendMessage: wsService.sendMessage.bind(wsService),
    wsState: 'CLOSED',
    reconnect: () => wsService.connect(wsUrl),
    wsUrl,
    setWsUrl: handleSetWsUrl,
    baseUrl,
    setBaseUrl: handleSetBaseUrl,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}
```

### 步骤 2: 修改 `websocket-handler.tsx`

**修改前：**

```typescript
const WebSocketHandler = memo(({ children }) => {
  const [wsUrl, setWsUrl] = useLocalStorage<string>('wsUrl', defaultWsUrl);
  const [baseUrl, setBaseUrl] = useLocalStorage<string>('baseUrl', defaultBaseUrl);
  // ...
});
```

**修改后：**

```typescript
const WebSocketHandler = memo(({ children }) => {
  // 直接从 Zustand 读取
  const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();
  
  // 监听 WebSocket 状态变化
  const [wsState, setWsState] = useState<string>('CLOSED');
  
  // ... 其他逻辑保持不变
});
```

### 步骤 3: 确保 Zustand Store 正确持久化

**检查 `store/index.ts`：**

```typescript
persist(
  subscribeWithSelector(/* ... */),
  {
    name: 'app-store',
    partialize: (state) => ({
      // ✅ 确保网络配置被持久化
      config: {
        wsUrl: state.config.wsUrl,
        baseUrl: state.config.baseUrl,  
        appConfig: state.config.appConfig,
      },
      // ... 其他需要持久化的状态
    }),
  }
)
```

### 步骤 4: 初始化配置

**在 `App.tsx` 或主入口初始化：**

```typescript
function App() {
  const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();

  // 首次启动时初始化配置
  useEffect(() => {
    if (!wsUrl || !baseUrl) {
      const serverConfig = getServerConfig();
      updateNetworkConfig({
        wsUrl: serverConfig.wsUrl,
        baseUrl: serverConfig.baseUrl
      });
    }
  }, []);

  // ... 其他逻辑
}
```

---

## 方案二：保持 Context，但统一数据源

如果不想大改，可以让 Context 作为 Zustand 的代理：

```typescript
export const WebSocketProvider = ({ children }) => {
  // Context 只是 Zustand 的一层封装
  const store = useConfigStore();

  const value = {
    sendMessage: wsService.sendMessage.bind(wsService),
    wsState: 'CLOSED',
    reconnect: () => wsService.connect(store.wsUrl),
    wsUrl: store.wsUrl,
    setWsUrl: (url: string) => {
      store.updateNetworkConfig({ wsUrl: url });
      wsService.connect(url);
    },
    baseUrl: store.baseUrl,
    setBaseUrl: (url: string) => {
      store.updateNetworkConfig({ baseUrl: url });
    },
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}
```

---

## 完整的数据流

### ✅ 重构后的数据流：

```
1. 应用启动
   ↓
2. env-config.ts 检测环境
   getServerConfig() → { wsUrl, baseUrl }
   ↓
3. 初始化 Zustand Store
   如果 localStorage 中没有持久化配置：
     updateNetworkConfig(检测到的配置)
   ↓
4. WebSocket Context 从 Store 读取
   const { wsUrl, baseUrl } = useConfigStore()
   ↓
5. WebSocket Service 连接
   wsService.connect(wsUrl)
   ↓
6. 所有组件都从 Store 读取
   const { baseUrl } = useConfigStore()
   fetch(`${baseUrl}/api/ads`)
```

---

## 修改清单

### 需要修改的文件：

1. ✅ `frontend/src/renderer/src/context/websocket-context.tsx`
   - 移除 `useLocalStorage`
   - 改用 `useConfigStore()`

2. ✅ `frontend/src/renderer/src/services/websocket-handler.tsx`
   - 移除 `useLocalStorage`
   - 改用 `useConfigStore()`

3. ✅ `frontend/src/renderer/src/App.tsx`
   - 添加配置初始化逻辑

4. ✅ 所有使用 `useWebSocket()` 的组件
   - 检查是否需要调整
   - 通常不需要改，因为 Context API 保持不变

### 不需要修改的文件：

- ❌ `store/index.ts` - 已经有完整的配置管理
- ❌ `utils/env-config.ts` - 保持作为配置发现工具

---

## 优势对比

### Before (当前架构):

```
❌ 配置存储在 2 个地方
❌ 需要手动同步
❌ 容易出现不一致
❌ Context 职责过重
```

### After (重构后):

```
✅ 配置只存储在 Zustand Store
✅ 自动持久化
✅ 单一数据源，永远一致
✅ Context 只负责 WebSocket 连接逻辑
✅ 所有组件都能轻松访问配置
```

---

## 迁移步骤

### 渐进式迁移（推荐）：

1. **第一阶段** - 让新代码使用 Zustand
   - 新组件直接用 `useConfigStore()`
   - 旧代码继续用 `useWebSocket()`

2. **第二阶段** - 统一数据源
   - 修改 Context 从 Store 读取
   - 删除 Context 中的 localStorage

3. **第三阶段** - 简化（可选）
   - 考虑是否还需要 Context
   - 可以直接用 Store，去掉 Context 层

### 一次性迁移：

1. 修改所有文件
2. 充分测试
3. 部署

---

## 测试要点

重构后需要测试：

1. ✅ 首次启动时能正确检测服务器地址
2. ✅ 配置能正确持久化到 localStorage
3. ✅ 刷新页面后配置仍然有效
4. ✅ 修改配置后所有使用配置的地方都能更新
5. ✅ WebSocket 能正确连接
6. ✅ 断线重连使用正确的 URL

---

## 代码示例：完整的 websocket-context.tsx (重构版)

```typescript
import React, { useContext, useCallback, useEffect } from 'react';
import { wsService } from '@/services/websocket-service';
import { useConfigStore } from '@/store';
import { getServerConfig } from '@/utils/env-config';

export interface HistoryInfo {
  uid: string;
  latest_message: {
    role: 'human' | 'ai';
    timestamp: string;
    content: string;
  } | null;
  timestamp: string | null;
}

interface WebSocketContextProps {
  sendMessage: (message: object) => void;
  wsState: string;
  reconnect: () => void;
  wsUrl: string;
  setWsUrl: (url: string) => void;
  baseUrl: string;
  setBaseUrl: (url: string) => void;
}

export const WebSocketContext = React.createContext<WebSocketContextProps | null>(null);

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};

export const WebSocketProvider = ({ children }: { children: React.ReactNode }) => {
  // ✅ 从 Zustand Store 读取配置
  const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();

  // ✅ 初始化配置（只在首次或配置为空时）
  useEffect(() => {
    if (!wsUrl || !baseUrl) {
      const defaultConfig = getServerConfig();
      console.log('🔧 初始化网络配置:', defaultConfig);
      updateNetworkConfig({
        wsUrl: defaultConfig.wsUrl,
        baseUrl: defaultConfig.baseUrl
      });
    }
  }, []);

  // ✅ 设置 WebSocket URL
  const handleSetWsUrl = useCallback((url: string) => {
    updateNetworkConfig({ wsUrl: url });
    wsService.connect(url);
  }, [updateNetworkConfig]);

  // ✅ 设置 Base URL
  const handleSetBaseUrl = useCallback((url: string) => {
    updateNetworkConfig({ baseUrl: url });
  }, [updateNetworkConfig]);

  const value = {
    sendMessage: wsService.sendMessage.bind(wsService),
    wsState: 'CLOSED',
    reconnect: () => wsService.connect(wsUrl),
    wsUrl,
    setWsUrl: handleSetWsUrl,
    baseUrl,
    setBaseUrl: handleSetBaseUrl,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};
```

---

## 总结

这个重构解决了架构不一致的问题，遵循了：

1. **单一数据源原则** - 配置只在 Zustand Store 中
2. **关注点分离** - env-config.ts 负责检测，Store 负责管理，Context 负责连接
3. **状态持久化** - 利用 Zustand persist 中间件
4. **易于维护** - 清晰的数据流向

**推荐优先级：方案一（完全迁移到 Zustand）> 方案二（Context 作为代理）**

