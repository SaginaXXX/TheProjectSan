# Context 目录职责说明 - 迁移后的作用

> **更新日期**: 2025-10-06  
> **状态**: 迁移完成后的架构说明

---

## 🤔 核心问题：迁移后 Context 还有什么用？

### 简短回答

**Context 现在负责「业务逻辑」，而不是「状态存储」**

```
┌──────────────────────────────────────────┐
│  Zustand Store                           │
│  职责：数据的唯一来源（单一数据源）         │
│  - 存储所有应用状态                        │
│  - 管理状态更新                           │
│  - 持久化配置                             │
└────────────────┬─────────────────────────┘
                 ↓ 提供数据
┌──────────────────────────────────────────┐
│  Context API                             │
│  职责：业务逻辑封装（不存储状态）           │
│  - 管理浏览器 API 实例                    │
│  - 封装复杂业务逻辑                        │
│  - 提供方便的 API 接口                    │
│  - 向后兼容旧代码                         │
└──────────────────────────────────────────┘
```

---

## 📂 剩余 Context 文件详解（11个）

### 🟢 类型 A：浏览器 API 资源管理（4个）

这些 Context **必须保留**，因为它们管理的是**浏览器硬件资源**，不是应用状态。

#### 1. camera-context.tsx - 摄像头管理

**职责**：
```typescript
// 管理 MediaStream（摄像头硬件资源）
const streamRef = useRef<MediaStream | null>(null);

const startCamera = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 320, height: 240 }
  });
  streamRef.current = stream;  // ← 这是浏览器 API 对象
  setIsStreaming(true);
};

const stopCamera = () => {
  stream.getTracks().forEach(track => track.stop());  // ← 释放硬件资源
};
```

**为什么不能放 Store**：
- ❌ MediaStream 对象**不能序列化**
- ❌ 不能存储到 localStorage
- ❌ 不适合 Zustand 管理
- ✅ 需要 Context 管理生命周期

**Store 的作用**：
```typescript
// Store 只存储状态标志
media: {
  isStreaming: boolean,  // ← 是否在播放（状态）
  stream: MediaStream | null,  // ← 引用（不持久化）
}

// Context 负责真正的资源管理
```

---

#### 2. screen-capture-context.tsx - 屏幕捕获

**职责**：
```typescript
// 管理屏幕共享的 MediaStream
const startCapture = async () => {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true, audio: false
  });
  setStream(stream);  // ← 浏览器 API 对象
};
```

**为什么需要 Context**：
- 管理屏幕捕获流（MediaStream）
- 处理 Electron 特殊的 IPC 调用
- 资源清理（组件卸载时停止捕获）

---

#### 3. vad-context.tsx - 语音检测引擎

**职责**：
```typescript
// 管理 VAD 实例（第三方库对象）
const vadRef = useRef<MicVAD | null>(null);

const initVAD = async () => {
  const VADWeb = await import('@ricky0123/vad-web');
  const newVAD = await VADWeb.MicVAD.new({
    onSpeechStart: handleSpeechStart,
    onSpeechEnd: handleSpeechEnd,
    // ... 复杂的回调逻辑
  });
  vadRef.current = newVAD;  // ← 第三方库实例
};

const stopMic = () => {
  vadRef.current?.destroy();  // ← 释放资源
};
```

**为什么需要 Context**：
- 管理 VAD 引擎实例（不能序列化）
- 处理复杂的语音检测回调
- 动态调整 VAD 参数（广告播放时）
- 管理麦克风生命周期

**从 Store 读取什么**：
```typescript
// ✅ 配置从 Store 读取
const { micOn, autoStopMic, settings } = useVADStore();

// ✅ Context 只负责 VAD 实例管理
vadRef.current = new MicVAD({ 
  positiveSpeechThreshold: settings.positiveSpeechThreshold / 100 
});
```

---

#### 4. websocket-handler.tsx - WebSocket 消息处理

**职责**：
```typescript
// 订阅 WebSocket 消息并分发到各个状态更新
useEffect(() => {
  const messageSubscription = wsService.onMessage(handleWebSocketMessage);
  
  return () => {
    messageSubscription.unsubscribe();  // ← 清理订阅
  };
}, []);

const handleWebSocketMessage = (message) => {
  switch (message.type) {
    case 'audio': addAudioTask(...); break;
    case 'full-text': setSubtitleText(...); break;
    // ... 复杂的消息路由逻辑
  }
};
```

**为什么需要（虽然不是 Context Provider）**：
- 管理 WebSocket 订阅（RxJS Subscription）
- 消息路由和业务逻辑
- 统一的消息处理中心

---

### 🟡 类型 B：复杂业务逻辑封装（3个）

这些 Context **建议保留**，因为封装了复杂的业务逻辑。

#### 5. live2d-model-context.tsx - Live2D 模型实例

**职责**：
```typescript
// 管理 Live2D 模型实例（Pixi.js 对象）
const [currentModel, setCurrentModel] = useState<Live2DModel | null>(null);

const updateModelState = (updates: Partial<Live2DModel>) => {
  setCurrentModel(prev => Object.assign(prev, updates));  // ← 更新模型对象
};
```

**为什么需要 Context**：
- Live2D 模型对象不能序列化
- 需要直接操作模型 API
- 生命周期管理

**潜在问题**：
- ⚠️ Store 中也有 `media.currentModel`
- 建议：同步两者的状态

---

#### 6. live2d-config-context.tsx - Live2D 配置管理

**职责**：
```typescript
// 管理 Live2D 模型配置和缩放记忆
const [modelInfo, setModelInfo] = useLocalStorage('modelInfo', ...);
const [scaleMemory, setScaleMemory] = useLocalStorage('scale_memory', {});

// 复杂的逻辑：按角色和模式分别记忆缩放
const storageKey = `${confUid}_${isPet ? "pet" : "window"}`;
const memorizedScale = scaleMemory[storageKey];
```

**为什么还用 localStorage**：
- ✅ Live2D 配置逻辑非常复杂
- ✅ 需要按模式和角色分别记忆缩放
- ✅ 有特殊的过滤逻辑（url 不存储）
- ⚠️ 迁移风险高，暂时保留

**未来改进**：
- 评估迁移到 Store 的可行性
- 或至少与 Store 中的 `config.modelInfo` 同步

---

#### 7. proactive-speak-context.tsx - 主动发言逻辑

**职责**：
```typescript
// 管理主动发言的定时器逻辑
const idleTimerRef = useRef<NodeJS.Timeout | null>(null);

const startIdleTimer = useCallback(() => {
  idleTimerRef.current = setTimeout(() => {
    sendTriggerSignal(actualIdleTime);  // ← 复杂的定时逻辑
  }, settings.idleSecondsToSpeak * 1000);
}, [settings]);

useEffect(() => {
  if (aiState === 'idle') {
    startIdleTimer();  // AI 空闲时启动定时器
  } else {
    clearIdleTimer();  // 其他状态清除定时器
  }
}, [aiState]);
```

**为什么需要 Context**：
- 封装复杂的定时器管理逻辑
- 监听 AI 状态变化并触发定时器
- 定时器清理

**从 Store 读取什么**：
```typescript
// ✅ 配置从 Store 读取
const { allowProactiveSpeak, idleSecondsToSpeak } = useProactiveStore();

// ✅ Context 只负责定时器业务逻辑
```

---

### 🔵 类型 C：代理层/兼容层（4个）

这些 Context **可以考虑移除**，但保留也有好处。

#### 8. chat-history-context.tsx - 聊天历史代理

**职责**：
```typescript
// 完全从 Store 读取和转发
const {
  messages,
  setMessages,
  appendHumanMessage,
  // ... 所有方法都来自 Store
} = useChatStore();

// 只是转发
const contextValue = useMemo(() => ({
  messages,
  setMessages,
  // ... 完全转发
}), [dependencies]);
```

**作用**：
- ✅ 提供统一的 API 接口
- ✅ 向后兼容（很多组件还在用 `useChatHistory()`）
- ⚠️ 只是代理层，可以考虑移除

**未来**：
- 逐步让组件直接用 `useChatStore()`
- 最后删除这个 Context

---

#### 9. group-context.tsx - 群组功能代理

**职责**：
```typescript
// 从 Store 读取群组状态
const selfUid = useAppStore((s) => s.chat.selfUid);
const groupMembers = useAppStore((s) => s.chat.groupMembers);

// 提供业务逻辑方法
const sortedGroupMembers = useMemo(() => {
  // 将自己排在第一位
  return [selfUid, ...groupMembers.filter(id => id !== selfUid)];
}, [groupMembers, selfUid]);
```

**作用**：
- ✅ 提供业务逻辑（成员排序）
- ✅ 封装群组操作
- 🟡 大部分只是转发 Store

**评估**：
- 有一定业务逻辑（排序）
- 可以保留

---

#### 10. bgurl-context.tsx - 背景 URL 管理

**职责**：
```typescript
// 从 Store 读取状态
const { backgroundUrl, backgroundFiles, useCameraBackground } = useMediaStore();

// 提供便捷方法
const resetBackground = useCallback(() => {
  setBackgroundUrl(DEFAULT_BACKGROUND);
}, []);

const addBackgroundFile = useCallback((file) => {
  setBackgroundFiles([...backgroundFiles, file]);
}, []);
```

**作用**：
- ✅ 提供便捷的业务方法
- ✅ 封装默认背景逻辑
- 🟡 大部分只是转发 Store

**评估**：
- 有一些业务逻辑
- 可以保留或合并到组件中

---

#### 11. websocket-context.tsx - WebSocket 配置管理

**职责**：
```typescript
// 从 Store 读取配置
const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();

// 提供 WebSocket 操作方法
const value = {
  sendMessage: wsService.sendMessage,
  wsState,
  reconnect: () => wsService.connect(wsUrl),
  // ...
};
```

**作用**：
- ✅ 提供 WebSocket 操作接口
- ✅ 封装 wsService 调用
- ✅ 向后兼容

**评估**：
- 提供了便捷的 API
- 建议保留

---

### 🟢 类型 D：独立业务模块（0个，已删除）

之前的 `character-config-context.tsx` 属于这类，但现在看它也在列表中。

#### 12. character-config-context.tsx - 角色配置

**职责**：
```typescript
// 使用 useState 管理角色配置
const [confName, setConfName] = useState<string>('');
const [confUid, setConfUid] = useState<string>('');
const [configFiles, setConfigFiles] = useState<ConfigFile[]>([]);

const getFilenameByName = (name: string) => {
  return configFiles.find(config => config.name === name)?.filename;
};
```

**特点**：
- ⚠️ 使用 useState，不持久化
- ⚠️ Store 中有 `config.characterConfig` 但未使用
- 🟡 可以考虑迁移到 Store

---

## 🎯 总结：Context 的新角色

### Context 现在的 3 种模式

#### 模式 1：资源管理器 ✅ **必须保留**

```typescript
// 示例：camera-context.tsx
export function CameraProvider({ children }) {
  const streamRef = useRef<MediaStream | null>(null);
  
  // 管理浏览器 API 资源
  const startCamera = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({...});
    streamRef.current = stream;  // ← 硬件资源
  };
  
  // 清理资源
  useEffect(() => {
    return () => {
      stream?.getTracks().forEach(track => track.stop());
    };
  }, []);
  
  return <CameraContext.Provider value={{...}} />
}
```

**特征**：
- ✅ 管理不能序列化的对象（MediaStream, VAD, Live2D）
- ✅ 处理资源生命周期
- ✅ 封装浏览器 API 调用

**适用**：
- camera-context.tsx
- screen-capture-context.tsx
- vad-context.tsx
- live2d-model-context.tsx

---

#### 模式 2：业务逻辑封装 ✅ **建议保留**

```typescript
// 示例：proactive-speak-context.tsx
export function ProactiveSpeakProvider({ children }) {
  // ✅ 从 Store 读取配置
  const { idleSecondsToSpeak } = useProactiveStore();
  
  // ✅ Context 提供复杂的定时器逻辑
  const idleTimerRef = useRef<NodeJS.Timeout>(null);
  
  useEffect(() => {
    if (aiState === 'idle') {
      idleTimerRef.current = setTimeout(() => {
        sendTriggerSignal();  // ← 业务逻辑
      }, idleSecondsToSpeak * 1000);
    }
  }, [aiState]);
  
  return <ProactiveSpeakContext.Provider value={{...}} />
}
```

**特征**：
- ✅ 从 Store 读取状态
- ✅ 封装复杂的业务逻辑（定时器、事件监听）
- ✅ 提供便捷的 API

**适用**：
- proactive-speak-context.tsx
- live2d-config-context.tsx（复杂的缩放记忆）

---

#### 模式 3：代理层/兼容层 🟡 **可选保留**

```typescript
// 示例：chat-history-context.tsx
export function ChatHistoryProvider({ children }) {
  // ✅ 完全从 Store 读取
  const {
    messages,
    setMessages,
    appendHumanMessage,
    // ... 所有都来自 Store
  } = useChatStore();
  
  // 只是转发，没有额外逻辑
  const contextValue = useMemo(() => ({
    messages,
    setMessages,
    appendHumanMessage,
    // ... 只是转发
  }), [dependencies]);
  
  return <ChatHistoryContext.Provider value={contextValue} />
}
```

**特征**：
- 🟡 只是转发 Store 的方法
- 🟡 没有独特的业务逻辑
- 🟡 主要为了向后兼容

**适用**：
- chat-history-context.tsx
- group-context.tsx
- bgurl-context.tsx
- websocket-context.tsx（部分）

**未来**：
- 可以逐步移除
- 让组件直接用 Store

---

## 📊 Context 分类总结

| Context | 类型 | 职责 | Store 关系 | 是否保留 |
|---------|------|------|-----------|---------|
| **camera-context** | 🟢 资源管理 | MediaStream | 同步状态标志 | ✅ 必须 |
| **screen-capture-context** | 🟢 资源管理 | 屏幕捕获流 | 独立 | ✅ 必须 |
| **vad-context** | 🟢 资源管理 | VAD 引擎实例 | 读取配置 | ✅ 必须 |
| **live2d-model-context** | 🟢 资源管理 | Live2D 对象 | 可能重复 | ✅ 必须 |
| **live2d-config-context** | 🟡 业务逻辑 | 复杂配置逻辑 | 独立 localStorage | ✅ 建议保留 |
| **proactive-speak-context** | 🟡 业务逻辑 | 定时器管理 | 读取配置 | ✅ 建议保留 |
| **chat-history-context** | 🔵 代理层 | 转发 Store | 完全代理 | 🟡 可选 |
| **group-context** | 🔵 代理层 | 转发 + 排序 | 完全代理 | 🟡 可选 |
| **bgurl-context** | 🔵 代理层 | 转发 + 便捷方法 | 完全代理 | 🟡 可选 |
| **websocket-context** | 🔵 代理层 | WebSocket API | 读取配置 | 🟡 可选 |
| **character-config-context** | 🟡 独立模块 | 角色配置 | 未使用 Store | 🟡 待评估 |

---

## 🎯 Context vs Store 使用规则

### 何时使用 Context？

```
✅ 使用 Context 的场景：

1. 管理浏览器 API 对象
   - MediaStream（摄像头、屏幕捕获）
   - WebSocket 实例
   - 第三方库实例（VAD, Live2D）

2. 封装复杂业务逻辑
   - 定时器管理
   - 事件监听和回调
   - 资源生命周期

3. 不能序列化的对象
   - Canvas context
   - Web Workers
   - AudioContext

4. 向后兼容
   - 保持旧 API 接口
   - 逐步迁移
```

### 何时使用 Store？

```
✅ 使用 Zustand Store 的场景：

1. 应用状态
   - 配置（wsUrl, VAD settings）
   - UI 状态（subtitle, showAds）
   - 数据（messages, history）

2. 需要持久化的数据
   - 用户偏好
   - 缓存数据
   - 会话状态

3. 全局共享的状态
   - AI 状态
   - 聊天记录
   - 网络配置

4. 可序列化的数据
   - String, Number, Boolean
   - Plain Objects, Arrays
```

---

## 📐 正确的架构模式

### ✅ 推荐模式：Store + Context 协作

```typescript
export function VeryGoodProvider({ children }) {
  // ✅ 1. 从 Store 读取所有状态
  const { config1, config2, updateConfig } = useXxxStore();
  
  // ✅ 2. 管理浏览器 API 资源
  const resourceRef = useRef<SomeAPI | null>(null);
  
  // ✅ 3. 提供业务逻辑方法
  const doSomethingComplex = useCallback(() => {
    // 使用 config1, config2
    // 操作 resourceRef
    // 更新 Store: updateConfig(newValue)
  }, [config1, config2, updateConfig]);
  
  // ✅ 4. 资源清理
  useEffect(() => {
    return () => {
      resourceRef.current?.destroy();
    };
  }, []);
  
  // ✅ 5. 返回 Context
  return (
    <XxxContext.Provider value={{
      config1,  // 来自 Store
      config2,  // 来自 Store
      doSomethingComplex,  // Context 提供的方法
    }}>
      {children}
    </XxxContext.Provider>
  );
}
```

**关键点**：
- ✅ 状态来自 Store（读取）
- ✅ 更新也通过 Store（写入）
- ✅ Context 提供业务逻辑
- ✅ Context 管理不可序列化的资源

---

## 🔄 迁移前 vs 迁移后对比

### Before（迁移前）

```typescript
// ❌ Context 自己存储状态
export function VadProvider({ children }) {
  const [micOn, setMicOn] = useLocalStorage('micOn', false);
  const [settings, setSettings] = useLocalStorage('vadSettings', {...});
  
  // Context 管理一切
  const vadRef = useRef<VAD>(null);
  
  return <VadContext.Provider value={{
    micOn,      // ← Context 自己的状态
    setMicOn,   // ← Context 自己的 setter
    // ...
  }} />
}
```

**问题**：
- ❌ 状态分散（Context 和 Store 各有一份）
- ❌ 可能不同步
- ❌ 难以维护

---

### After（迁移后）

```typescript
// ✅ Context 从 Store 读取状态
export function VadProvider({ children }) {
  // ✅ 状态从 Store 读取
  const { micOn, settings, setMicState } = useVADStore();
  
  // ✅ Context 只管理 VAD 实例
  const vadRef = useRef<VAD>(null);
  
  // ✅ Context 提供业务逻辑
  const startMic = async () => {
    await initVAD();
    setMicState(true);  // ← 更新 Store
  };
  
  return <VadContext.Provider value={{
    micOn,      // ← 来自 Store
    startMic,   // ← Context 的业务逻辑
    // ...
  }} />
}
```

**优点**：
- ✅ 单一数据源（Store）
- ✅ Context 职责清晰（业务逻辑 + 资源管理）
- ✅ 数据流清晰
- ✅ 易于维护和调试

---

## 🎓 设计哲学

### 为什么不全部迁移到 Store？

**反例：不适合放 Store 的东西**

```typescript
// ❌ 不要这样做
export interface BadStore {
  // ❌ 不能序列化的对象
  cameraStream: MediaStream;  // 无法存储到 localStorage
  vadInstance: MicVAD;        // 第三方库实例
  live2dModel: Live2DModel;   // Pixi.js 对象
  
  // ❌ 复杂的业务逻辑
  idleTimer: NodeJS.Timeout;  // 定时器 ID
  eventListeners: Map<...>;   // 事件监听器
}
```

**正确做法**：

```typescript
// ✅ Store：只存储可序列化的状态
export interface GoodStore {
  isStreaming: boolean;       // ✅ 状态标志
  micOn: boolean;             // ✅ 状态标志
  modelLoaded: boolean;       // ✅ 状态标志
}

// ✅ Context：管理资源和逻辑
export function CameraProvider() {
  const { isStreaming } = useMediaStore();  // 读取状态
  const streamRef = useRef<MediaStream>();  // 管理资源
  
  const startCamera = async () => {
    const stream = await navigator.mediaDevices.getUserMedia();
    streamRef.current = stream;
    setIsStreaming(true);  // 更新 Store 状态
  };
}
```

---

## 📖 类比说明

把架构想象成一个**图书馆系统**：

### Zustand Store = 图书目录数据库

```
存储：
- 书籍信息（书名、作者、位置）
- 借阅状态（是否已借出）
- 配置（开放时间、规则）

特点：
- 持久化存储
- 可以查询
- 可以备份
```

### Context = 图书管理员

```
职责：
- 帮你找书（业务逻辑）
- 管理借还流程（复杂操作）
- 维护设备（打印机、电脑）
- 提供咨询服务

特点：
- 不存储书籍信息（查数据库）
- 提供便捷服务
- 管理物理资源
```

### 你不会让管理员记住所有书的信息（那是数据库的事）
### 但你需要管理员提供服务（那是业务逻辑）

---

## ✅ 最佳实践总结

### DO（应该做的）

```typescript
✅ 状态 → Zustand Store
✅ 配置 → Zustand Store
✅ 浏览器 API → Context 管理
✅ 业务逻辑 → Context 封装
✅ 从 Store 读取 → Context
✅ 更新 Store → Context 调用 Store 的方法
```

### DON'T（不应该做的）

```typescript
❌ 在 Context 中用 useLocalStorage
❌ 在 Context 中用 useState 存储全局状态
❌ 浏览器 API 对象放 Store
❌ 直接赋值给 Store 对象（Immer）
❌ 状态重复存储
❌ Context 和 Store 状态不同步
```

---

## 📚 推荐阅读顺序

1. **本文档** - 理解 Context 的新角色
2. **前端架构深度审查报告** - 了解完整架构
3. **前后端架构与WebSocket通信指南** - 学习通信机制

---

**总结**: Context 现在是**业务逻辑层和资源管理层**，而不是状态存储层！

**文档版本**: v1.0  
**最后更新**: 2025-10-06

