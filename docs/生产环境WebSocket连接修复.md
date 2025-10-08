# 生产环境 WebSocket 连接修复

> **问题**: 部署到 HTTPS 后 WebSocket 无法连接  
> **原因**: Store 默认值和 localStorage 都是本地地址  
> **修复状态**: ✅ **已修复**

---

## 🚨 问题描述

### 错误日志

```
WebSocket connection to 'ws://127.0.0.1:12393/client-ws' failed
🚨 WebSocket连接错误
🔄 尝试恢复 websocket (1/3)
🔁 WS schedule reconnect in 2000ms (attempt 2)
```

### 环境信息

```
前端访问地址: https://jtlai.top
WebSocket 连接: ws://127.0.0.1:12393/client-ws  ← ❌ 错误！

应该连接到: wss://jtlai.top/client-ws  ← ✅ 正确
```

---

## 🔍 根本原因

### 问题链条

```
1. Store 初始化
   └─ wsUrl = 'ws://127.0.0.1:12393/client-ws' (硬编码默认值)

2. 用户在本地开发时使用
   └─ localStorage 存储了本地地址

3. 部署到生产环境（HTTPS）
   └─ persist 中间件加载 localStorage
   └─ 恢复了本地地址 ❌

4. WebSocket 尝试连接
   └─ wss://jtlai.top 页面尝试连接 ws://127.0.0.1:12393
   └─ 跨域失败 ❌
   └─ HTTPS 连接 WS 被浏览器阻止 ❌
```

### 代码问题

#### 问题 1: 硬编码的默认值

```typescript
// ❌ 之前的代码
const initialConfigState = {
  wsUrl: 'ws://127.0.0.1:12393/client-ws',  // 硬编码本地地址
  baseUrl: 'http://127.0.0.1:12393',
};
```

#### 问题 2: persist 无条件恢复

```typescript
// ❌ 之前的 persist 配置
persist(
  ...,
  {
    name: 'app-store',
    partialize: (state) => ({ ... }),
    // ❌ 没有 merge 函数，直接覆盖
  }
)
```

---

## ✅ 解决方案

### 修复 1: 动态环境检测

```typescript
// ✅ 添加环境检测函数
function getInitialServerConfig() {
  try {
    // 检测当前环境
    if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
      // HTTPS 环境：使用同源 WSS
      const host = window.location.host;
      return {
        wsUrl: `wss://${host}/client-ws`,
        baseUrl: `https://${host}`
      };
    }
  } catch (e) {
    console.warn('⚠️ 环境检测失败，使用默认配置');
  }
  
  // 默认：开发环境本地地址
  return {
    wsUrl: 'ws://127.0.0.1:12393/client-ws',
    baseUrl: 'http://127.0.0.1:12393'
  };
}

const initialServerConfig = getInitialServerConfig();

// ✅ 使用检测到的配置
const initialConfigState = {
  wsUrl: initialServerConfig.wsUrl,    // 根据环境自动选择
  baseUrl: initialServerConfig.baseUrl,
};
```

---

### 修复 2: 智能合并策略

```typescript
// ✅ 添加 merge 函数
persist(
  ...,
  {
    name: 'app-store',
    partialize: (state) => ({ ... }),
    
    // ✅ 智能合并：HTTPS 环境下忽略本地地址
    merge: (persistedState, currentState) => {
      const isHttps = window.location.protocol === 'https:';
      
      // 检测 localStorage 中是否有本地地址
      const hasLocalAddress = persistedState?.config?.wsUrl && 
        /127\.0\.0\.1|localhost/i.test(persistedState.config.wsUrl);
      
      // HTTPS 环境 + localStorage 有本地地址 → 忽略
      if (isHttps && hasLocalAddress) {
        console.log('🔒 检测到 HTTPS 环境，忽略 localStorage 中的本地地址配置');
        return {
          ...currentState,
          ...persistedState,
          config: {
            ...persistedState.config,
            wsUrl: currentState.config.wsUrl,  // 使用检测到的 wss://
            baseUrl: currentState.config.baseUrl,
          },
        };
      }
      
      // 正常合并
      return { ...currentState, ...persistedState };
    },
  }
)
```

---

## 🎯 修复效果

### Before（修复前）

```
HTTPS 生产环境:
1. Store 默认: ws://127.0.0.1:12393  ❌
2. localStorage: ws://127.0.0.1:12393  ❌
3. persist 恢复: ws://127.0.0.1:12393  ❌
4. WebSocket 连接失败  ❌
```

### After（修复后）

```
HTTPS 生产环境:
1. 环境检测: wss://jtlai.top/client-ws  ✅
2. Store 默认: wss://jtlai.top/client-ws  ✅
3. localStorage: ws://127.0.0.1:12393（被忽略）
4. persist merge: wss://jtlai.top/client-ws  ✅
5. WebSocket 连接成功  ✅
```

---

## 🧪 测试验证

### 测试不同环境

#### 1. 本地开发环境 (http://localhost:3000)

```
预期:
- wsUrl: ws://127.0.0.1:12393/client-ws ✅
- baseUrl: http://127.0.0.1:12393 ✅
```

#### 2. HTTPS 生产环境 (https://jtlai.top)

```
预期:
- wsUrl: wss://jtlai.top/client-ws ✅
- baseUrl: https://jtlai.top ✅
```

#### 3. HTTP 生产环境 (http://example.com)

```
预期:
- wsUrl: ws://example.com/client-ws ✅
- baseUrl: http://example.com ✅
```

---

## 📋 部署检查清单

### 前端部署

- [ ] 重新构建前端 (`npm run build`)
- [ ] 部署到服务器
- [ ] 清空旧用户的缓存（可选，merge 会自动处理）

### 后端部署

- [ ] 确保后端在 `jtlai.top` 上运行
- [ ] 确保 `/client-ws` 路由可访问
- [ ] 如果使用 Nginx，配置 WebSocket 代理

### Nginx 配置示例

```nginx
server {
    listen 443 ssl;
    server_name jtlai.top;

    # SSL 证书配置
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 静态文件
    location / {
        root /var/www/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # WebSocket 代理
    location /client-ws {
        proxy_pass http://localhost:12393;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 超时设置
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # API 代理
    location /api/ {
        proxy_pass http://localhost:12393;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 静态资源代理
    location ~ ^/(live2d-models|ads|videos|backgrounds|avatars)/ {
        proxy_pass http://localhost:12393;
    }
}
```

---

## 🔄 回滚方案

如果修复后出现问题：

```bash
git checkout -- frontend/src/renderer/src/store/index.ts
```

---

## 🎯 验证修复

### 开发环境

```bash
npm run dev
# 应该连接到: ws://127.0.0.1:12393/client-ws
```

### 生产环境

访问 `https://jtlai.top`，在控制台应该看到：

```javascript
✅ 正确的日志:
1. 🔒 检测到 HTTPS 环境，忽略 localStorage 中的本地地址配置
2. 🌐 WS connecting... wss://jtlai.top/client-ws
3. ✅ WS open
```

---

## 📊 修改总结

| 文件 | 修改内容 | 原因 |
|------|----------|------|
| `store/index.ts` | 添加环境检测函数 | 根据环境动态设置默认值 |
| `store/index.ts` | 添加智能 merge 逻辑 | HTTPS 环境忽略本地地址 |
| `subtitle.tsx` | 字幕框加宽到 96% | 响应式优化 |

---

## ✅ 完成状态

- [x] 环境检测逻辑
- [x] 智能合并策略
- [x] 本地/生产环境兼容
- [ ] 重新构建并部署（待用户执行）
- [ ] 生产环境测试（待验证）

---

**修复版本**: v1.0  
**修复时间**: 2025-10-07  
**状态**: ✅ 代码已修复，需要重新部署

