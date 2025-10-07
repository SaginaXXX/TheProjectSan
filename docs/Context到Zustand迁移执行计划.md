# Context 到 Zustand 迁移执行计划

> **执行日期**: 2025-10-06  
> **预计时间**: 2-3 小时  
> **风险等级**: 🟡 中等（需要充分测试）

---

## 📋 执行概览

### 迁移目标

将 3 个存在状态重复的 Context 重构为从 Zustand Store 读取状态，消除数据不一致问题。

### 影响范围

- **修改文件**: 3 个 Context 文件
- **删除文件**: 3 个 LEGACY 文件
- **测试范围**: WebSocket 连接、VAD 功能、背景设置

---

## 🎯 阶段一：高优先级修复

### Task 1.1: 修复 websocket-context.tsx

**当前问题**:
```typescript
// ❌ 重复存储
const [wsUrl, setWsUrl] = useLocalStorage('wsUrl', DEFAULT_WS_URL);
const [baseUrl, setBaseUrl] = useLocalStorage('baseUrl', DEFAULT_BASE_URL);
```

**修复后**:
```typescript
// ✅ 从 Store 读取
const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();
```

**步骤**:
1. 导入 `useConfigStore`
2. 移除 `useLocalStorage` 调用
3. 使用 `updateNetworkConfig` 替代 setter
4. 添加初始化逻辑（首次启动时从 env-config 读取）

**测试点**:
- [ ] WebSocket 连接成功
- [ ] 修改配置后能正确连接
- [ ] 刷新页面配置保持
- [ ] 控制面板配置显示正确

---

### Task 1.2: 修复 vad-context.tsx

**当前问题**:
```typescript
// ❌ 5 个配置项重复存储
const [micOn, setMicOn] = useLocalStorage('micOn', false);
const [autoStopMic, setAutoStopMicState] = useLocalStorage('autoStopMic', false);
const [settings, setSettings] = useLocalStorage<VADSettings>('vadSettings', DEFAULT_VAD_SETTINGS);
const [autoStartMicOn, setAutoStartMicOnState] = useLocalStorage('autoStartMicOn', false);
const [autoStartMicOnConvEnd, setAutoStartMicOnConvEndState] = useLocalStorage('autoStartMicOnConvEnd', false);
```

**修复后**:
```typescript
// ✅ 从 Store 读取
const { 
  micOn, 
  autoStopMic, 
  settings, 
  autoStartMicOn, 
  autoStartMicOnConvEnd,
  setMicState,
  updateVADSettings 
} = useVADStore();
```

**步骤**:
1. 导入 `useVADStore` 和 `useAppStore`
2. 移除所有 `useLocalStorage` 调用
3. 使用 Store 的 setter 方法
4. 保留 VAD 实例管理逻辑（vadRef, initVAD, startMic, stopMic）
5. 更新 refs 以使用 Store 状态

**测试点**:
- [ ] 麦克风开启/关闭正常
- [ ] VAD 检测正常工作
- [ ] 配置修改后立即生效
- [ ] 刷新页面配置保持
- [ ] 广告播放时 VAD 自适应正常

---

### Task 1.3: 修复 bgurl-context.tsx

**当前问题**:
```typescript
// ❌ backgroundUrl 重复存储
const [backgroundUrl, setBackgroundUrl] = useLocalStorage<string>(
  'backgroundUrl',
  DEFAULT_BACKGROUND,
);

// ✅ 但其他状态已从 Store 读取
const {
  backgroundFiles,
  setBackgroundFiles,
  useCameraBackground,
  setUseCameraBackground,
} = useMediaStore();
```

**修复后**:
```typescript
// ✅ 完全从 Store 读取
const {
  backgroundUrl,
  backgroundFiles,
  useCameraBackground,
  setBackgroundFiles,
  setUseCameraBackground,
} = useMediaStore();

// ✅ 使用 Store 的 setter
const setBackgroundUrl = useCallback((url: string) => {
  const store = useAppStore.getState();
  store.updateMediaState({ backgroundUrl: url });
}, []);
```

**步骤**:
1. 移除 `useLocalStorage('backgroundUrl')`
2. 从 `useMediaStore()` 读取 backgroundUrl
3. 创建 setBackgroundUrl 使用 Store 更新
4. 保留业务逻辑方法（resetBackground, addBackgroundFile 等）

**测试点**:
- [ ] 背景切换正常
- [ ] 重置背景功能正常
- [ ] 摄像头背景切换正常
- [ ] 刷新页面背景保持

---

## 🧹 阶段二：清理 LEGACY 文件

### Task 2.1: 删除已废弃的 Context 文件

**删除列表**:
1. `context/ai-state-context.tsx` - 已迁移到 `useAiStore`
2. `context/subtitle-context.tsx` - 已迁移到 `useChatStore`
3. `context/advertisement-context.tsx` - 已迁移到 `useMediaStore`

**步骤**:
1. 全局搜索是否有引用
2. 确认无引用后删除
3. 更新相关文档

---

## 🔍 阶段三：验证和测试

### Task 3.1: 手动测试清单

**WebSocket 功能**:
- [ ] 启动应用，WebSocket 自动连接
- [ ] 查看控制面板，配置显示正确
- [ ] 修改 WebSocket URL，能正确重连
- [ ] 修改 Base URL，资源加载正确
- [ ] 刷新页面，配置保持

**VAD 功能**:
- [ ] 点击麦克风按钮，能正常开启
- [ ] 说话，VAD 能正常检测
- [ ] 语音结束，正确触发识别
- [ ] 修改 VAD 阈值，立即生效
- [ ] 自动停止麦克风功能正常
- [ ] 对话结束自动启动麦克风功能正常
- [ ] 播放广告时，VAD 自适应调整正常
- [ ] 刷新页面，VAD 配置保持

**背景功能**:
- [ ] 切换背景图片，正常显示
- [ ] 点击重置背景，恢复默认
- [ ] 切换摄像头背景，正常工作
- [ ] 刷新页面，背景保持

**对话功能**:
- [ ] 语音对话正常
- [ ] 文本输入正常
- [ ] 中断功能正常
- [ ] 历史记录正常
- [ ] 角色切换正常

### Task 3.2: 集成测试

**场景 1: 首次启动**
1. 清空 localStorage
2. 启动应用
3. 验证：配置初始化正确，WebSocket 连接成功

**场景 2: 配置修改**
1. 修改所有可修改的配置
2. 刷新页面
3. 验证：所有配置都保持

**场景 3: 并发操作**
1. 同时修改多个配置
2. 同时进行对话和背景切换
3. 验证：无冲突，功能正常

---

## 📊 迁移检查表

### 代码质量

- [ ] 没有 ESLint 错误
- [ ] 没有 TypeScript 错误
- [ ] 没有 console.error 或 console.warn
- [ ] 代码格式化正确

### 功能完整性

- [ ] 所有现有功能保持正常
- [ ] 没有破坏性变更
- [ ] 用户体验无变化

### 性能

- [ ] 没有性能退化
- [ ] 没有内存泄漏
- [ ] 没有不必要的重渲染

---

## 🔄 回滚计划

如果出现问题，回滚步骤：

1. 使用 git 恢复修改的文件
   ```bash
   git checkout -- frontend/src/renderer/src/context/websocket-context.tsx
   git checkout -- frontend/src/renderer/src/context/vad-context.tsx
   git checkout -- frontend/src/renderer/src/context/bgurl-context.tsx
   ```

2. 恢复已删除的文件（从 git 历史）
   ```bash
   git checkout HEAD -- frontend/src/renderer/src/context/ai-state-context.tsx
   git checkout HEAD -- frontend/src/renderer/src/context/subtitle-context.tsx
   git checkout HEAD -- frontend/src/renderer/src/context/advertisement-context.tsx
   ```

3. 重启应用测试

---

## 📝 代码修改详情

### 文件 1: websocket-context.tsx

**修改前** (99 行):
```typescript
import { useLocalStorage } from '@/hooks/utils/use-local-storage';

export const WebSocketProvider = ({ children }) => {
  const [wsUrl, setWsUrl] = useLocalStorage('wsUrl', DEFAULT_WS_URL);
  const [baseUrl, setBaseUrl] = useLocalStorage('baseUrl', DEFAULT_BASE_URL);
  // ...
}
```

**修改后** (~120 行):
```typescript
import { useConfigStore } from '@/store';
import { getServerConfig } from '@/utils/env-config';

export const WebSocketProvider = ({ children }) => {
  const { wsUrl, baseUrl, updateNetworkConfig } = useConfigStore();
  
  // 初始化配置
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
  // ...
}
```

---

### 文件 2: vad-context.tsx

**修改前** (484 行，使用 5 个 useLocalStorage):
```typescript
const [micOn, setMicOn] = useLocalStorage('micOn', false);
const [autoStopMic, setAutoStopMicState] = useLocalStorage('autoStopMic', false);
const [settings, setSettings] = useLocalStorage('vadSettings', DEFAULT_VAD_SETTINGS);
const [autoStartMicOn, setAutoStartMicOnState] = useLocalStorage('autoStartMicOn', false);
const [autoStartMicOnConvEnd, setAutoStartMicOnConvEndState] = useLocalStorage('autoStartMicOnConvEnd', false);
```

**修改后** (~450 行):
```typescript
// 从 Store 读取所有状态
const vadStore = useVADStore();
const { 
  micOn, 
  autoStopMic, 
  settings, 
  autoStartMicOn, 
  autoStartMicOnConvEnd,
  setMicState,
  updateVADSettings 
} = vadStore;

// 使用 Store 的 setter
const setAutoStopMic = useCallback((value: boolean) => {
  const store = useAppStore.getState();
  store.vad.autoStopMic = value;
}, []);
```

---

### 文件 3: bgurl-context.tsx

**修改前** (120 行):
```typescript
const [backgroundUrl, setBackgroundUrl] = useLocalStorage<string>(
  'backgroundUrl',
  DEFAULT_BACKGROUND,
);
```

**修改后** (~115 行):
```typescript
// 完全从 Store 读取
const mediaStore = useMediaStore();
const {
  backgroundUrl,
  backgroundFiles,
  useCameraBackground,
  setBackgroundFiles,
  setUseCameraBackground,
} = mediaStore;

// 使用 Store 更新背景 URL
const setBackgroundUrl = useCallback((url: string) => {
  const store = useAppStore.getState();
  store.updateMediaState({ backgroundUrl: url });
}, []);
```

---

## 📦 删除的文件

1. `frontend/src/renderer/src/context/ai-state-context.tsx` (4 行，已废弃)
2. `frontend/src/renderer/src/context/subtitle-context.tsx` (4 行，已废弃)
3. `frontend/src/renderer/src/context/advertisement-context.tsx` (39 行，已废弃)

---

## 🎉 完成标准

迁移完成的标准：

1. ✅ 所有 3 个 Context 不再使用 `useLocalStorage`
2. ✅ 所有状态从 Zustand Store 读取
3. ✅ 所有 LEGACY 文件已删除
4. ✅ 手动测试清单全部通过
5. ✅ 没有 linter 错误
6. ✅ 没有 TypeScript 错误
7. ✅ 代码审查通过

---

## 📅 执行时间表

| 阶段 | 任务 | 预计时间 | 负责人 |
|------|------|----------|--------|
| 阶段一 | websocket-context.tsx | 30 分钟 | AI |
| 阶段一 | vad-context.tsx | 45 分钟 | AI |
| 阶段一 | bgurl-context.tsx | 20 分钟 | AI |
| 阶段二 | 删除 LEGACY 文件 | 10 分钟 | AI |
| 阶段三 | 手动测试 | 30 分钟 | 用户 |
| 阶段三 | 修复问题（如有） | 15 分钟 | AI |
| **总计** | | **~2.5 小时** | |

---

## 🔗 相关文档

- [Context迁移状态分析报告](./Context迁移状态分析报告.md)
- [WebSocket配置管理重构方案](./WebSocket配置管理重构方案.md)
- [前后端架构与WebSocket通信指南](./前后端架构与WebSocket通信指南.md)

---

**执行计划版本**: v1.0  
**创建日期**: 2025-10-06  
**审核状态**: ✅ 待执行

