# VAD 设置只读属性错误修复

> **错误**: Cannot assign to read only property 'autoStopMic'  
> **修复状态**: ✅ **已修复**  
> **修复时间**: 2025-10-06

---

## 🚨 错误描述

### 错误信息

```
TypeError: Cannot assign to read only property 'autoStopMic' of object '#<Object>'
TypeError: Cannot assign to read only property 'autoStartMicOn' of object '#<Object>'
TypeError: Cannot assign to read only property 'autoStartMicOnConvEnd' of object '#<Object>'
```

### 触发场景

用户在设置面板中切换 VAD 相关选项时出错：
- 自动停止麦克风
- 自动启动麦克风
- 对话结束时自动启动麦克风

---

## 🔍 根本原因

### 错误代码（vad-context.tsx）

```typescript
// ❌ 错误：直接赋值给 Zustand + Immer 生成的只读对象
const setAutoStopMic = useCallback((value: boolean) => {
  autoStopMicRef.current = value;
  const store = useAppStore.getState();
  store.vad.autoStopMic = value;  // ❌ 直接赋值 - 错误！
  forceUpdate();
}, []);
```

### 为什么会报错？

Zustand 使用了 **Immer 中间件**：

```typescript
import { immer } from 'zustand/middleware/immer';

export const useAppStore = create<AppStore>()(
  immer((set, get) => ({  // ← 使用 Immer
    // ...
  }))
);
```

**Immer 的特性**：
- 生成的状态对象是**不可变的（Immutable）**
- 不能直接赋值 `state.vad.autoStopMic = value` ❌
- 必须通过 `set` 方法更新 ✅

---

## ✅ 修复方案

### 步骤 1: 在 Store 中添加专门的 Setter 方法

**文件**: `store/index.ts`

```typescript
// ✅ 添加接口定义
export interface AppStore {
  // ...
  setAutoStopMic: (value: boolean) => void;
  setAutoStartMicOn: (value: boolean) => void;
  setAutoStartMicOnConvEnd: (value: boolean) => void;
}

// ✅ 添加 action 实现
setAutoStopMic: (value) => {
  set((draft) => {
    draft.vad.autoStopMic = value;  // ✅ 在 set 中修改
  });
},

setAutoStartMicOn: (value) => {
  set((draft) => {
    draft.vad.autoStartMicOn = value;  // ✅ 在 set 中修改
  });
},

setAutoStartMicOnConvEnd: (value) => {
  set((draft) => {
    draft.vad.autoStartMicOnConvEnd = value;  // ✅ 在 set 中修改
  });
},
```

---

### 步骤 2: 在 useVADStore Selector 中导出方法

```typescript
export const useVADStore = () => {
  // ...
  const setAutoStopMic = useAppStore((s) => s.setAutoStopMic);
  const setAutoStartMicOn = useAppStore((s) => s.setAutoStartMicOn);
  const setAutoStartMicOnConvEnd = useAppStore((s) => s.setAutoStartMicOnConvEnd);
  
  return { 
    // ...
    setAutoStopMic,
    setAutoStartMicOn,
    setAutoStartMicOnConvEnd,
  };
};
```

---

### 步骤 3: 在 vad-context.tsx 中使用 Store 的 Setter

```typescript
// ✅ 从 Store 获取 setter 方法
const { 
  // ...
  setAutoStopMic: setAutoStopMicStore,
  setAutoStartMicOn: setAutoStartMicOnStore,
  setAutoStartMicOnConvEnd: setAutoStartMicOnConvEndStore,
} = useVADStore();

// ✅ 使用 Store 的 setter
const setAutoStopMic = useCallback((value: boolean) => {
  autoStopMicRef.current = value;
  setAutoStopMicStore(value);  // ✅ 调用 Store 的 setter
  forceUpdate();
}, [setAutoStopMicStore]);
```

---

## 📊 修改文件

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `store/index.ts` | 添加 3 个 setter 方法 | ✅ |
| `store/index.ts` | 扩展 useVADStore selector | ✅ |
| `context/vad-context.tsx` | 使用 Store 的 setter | ✅ |
| `context/vad-context.tsx` | 移除直接赋值代码 | ✅ |

---

## ✅ 修复验证

### 测试步骤

1. 刷新页面
2. 打开设置面板
3. 切换以下选项：
   - [ ] "AI发話時にマイクを自動停止"
   - [ ] "会話終了時にマイクを自動開始"
   - [ ] "AI中断時にマイクを自動開始"

### 预期结果

- ✅ 无错误提示
- ✅ 选项正常切换
- ✅ 配置正确保存
- ✅ 刷新页面配置保持

---

## 🎓 技术要点

### Zustand + Immer 的正确使用方式

#### ❌ 错误方式

```typescript
// 直接修改状态 - 会报错
const store = useAppStore.getState();
store.vad.autoStopMic = value;  // ❌ Cannot assign to read only property
```

#### ✅ 正确方式

```typescript
// 方式 1: 使用 set 方法
set((draft) => {
  draft.vad.autoStopMic = value;  // ✅ 在 draft 中修改
});

// 方式 2: 创建 action 方法
setAutoStopMic: (value) => {
  set((draft) => {
    draft.vad.autoStopMic = value;
  });
}
```

### 为什么 Immer 状态是只读的？

**Immer 的设计理念**：

1. **不可变更新** - 保证状态不被意外修改
2. **时间旅行** - 支持 undo/redo
3. **性能优化** - 只有改变的部分才重新渲染
4. **调试友好** - 状态变化可追踪

**使用 Immer 的好处**：

```typescript
// ✅ Immer 让不可变更新变简单
set((draft) => {
  draft.vad.autoStopMic = true;
  draft.vad.settings.positiveSpeechThreshold = 60;
  // 看起来像可变更新，实际是不可变的
});

// ❌ 不用 Immer 需要这样写
set({
  ...state,
  vad: {
    ...state.vad,
    autoStopMic: true,
    settings: {
      ...state.vad.settings,
      positiveSpeechThreshold: 60
    }
  }
});
```

---

## 📋 检查清单

- [x] 添加 Store setter 方法
- [x] 扩展 Selector
- [x] 修复 vad-context 中的直接赋值
- [x] 移除未使用的导入
- [x] 无 Linter 错误

---

**修复状态**: ✅ **完成**  
**测试状态**: ⏳ **等待用户验证**

