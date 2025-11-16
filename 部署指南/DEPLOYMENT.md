# TheProjectSan 生产环境部署指南

> **快速开始**：如果你是第一次部署，建议先查看 [完整部署步骤.md](./完整部署步骤.md)，那里有更详细的逐步说明。

## 概述

本指南适用于在宝塔Linux面板服务器上，使用Docker Compose部署TheProjectSan项目，实现前后端分离，并通过Caddy自动配置HTTPS证书。

## 部署架构

```
Internet → Caddy (80/443) → Frontend (3000) + Backend (12393)
```

## 前置要求

- 宝塔Linux面板已安装
- 服务器有公网IP
- 已购买域名并完成DNS解析
- 服务器至少2GB内存（推荐4GB+）
- 至少20GB可用磁盘空间

## 第一步：服务器准备

### 1.1 检查/安装 Docker

在宝塔面板终端或SSH中执行：

```bash
# 检查Docker是否已安装
docker --version
```

#### 如果Docker未安装，根据系统类型选择安装方法：

**方法1: 标准Linux发行版（Ubuntu/Debian/CentOS/Rocky Linux）**

```bash
# 使用官方安装脚本
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

**方法2: OpenCloudOS / 其他不支持的发行版（手动安装）**

如果官方脚本不支持你的系统（如 OpenCloudOS），使用以下手动安装方法：

```bash
# 1. 安装必要的依赖
sudo yum install -y yum-utils device-mapper-persistent-data lvm2

# 2. 添加Docker官方仓库（CentOS/RHEL兼容方式）
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 3. 安装Docker Engine
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 5. 验证安装
sudo docker --version
```

**方法3: 使用宝塔面板Docker管理器**

1. 登录宝塔面板
2. 进入 **软件商店** → 搜索 **Docker管理器**
3. 点击安装
4. 安装完成后，在面板中启动Docker服务

#### 验证Docker Compose插件

从你的安装输出可以看到，`docker-compose-plugin` 已经包含在安装包中。验证是否可用：

```bash
# 验证 Docker Compose 插件（新版本使用 docker compose，注意是空格不是横线）
docker compose version

# 如果显示版本号，说明已安装成功
# 例如：Docker Compose version v2.32.1
```

**重要说明**：
- ✅ **Docker Compose 已经安装**：从你的安装输出可以看到 `docker-compose-plugin-2.32.1-2.oc9.x86_64` 已经安装
- 新版本的 Docker 使用 `docker compose`（**空格**）而不是 `docker-compose`（横线）
- 验证命令：
  ```bash
  # 验证 Docker Compose（注意是空格）
  docker compose version
  
  # 应该显示类似：Docker Compose version v2.32.1
  ```

如果 `docker compose version` 命令失败，可能需要：
```bash
# 重启Docker服务使插件生效
sudo systemctl restart docker

# 再次验证
docker compose version
```

**注意**: 如果使用 `sudo` 安装，普通用户可能无法直接使用docker命令，需要：

```bash
# 将当前用户添加到docker组（可选，推荐）
sudo usermod -aG docker $USER

# 重新登录或执行以下命令使组权限生效
newgrp docker

# 验证（不需要sudo）
docker --version
```

### 1.2 配置宝塔面板防火墙

1. 登录宝塔面板
2. 进入 **安全** → **防火墙**
3. 添加以下端口规则：
   - **端口**: 80，**协议**: TCP，**备注**: HTTP
   - **端口**: 443，**协议**: TCP，**备注**: HTTPS
   - **端口**: 22，**协议**: TCP，**备注**: SSH（如果使用）

### 1.3 配置域名DNS

在域名服务商处添加A记录：

```
类型: A
主机: @ (或 your-domain.com)
值: 你的服务器公网IP地址
TTL: 600
```

等待DNS解析生效（通常几分钟到几小时），可通过以下命令检查：

```bash
nslookup your-domain.com
```

## 第二步：从GitHub克隆项目

### 2.1 克隆项目

```bash
# 进入合适的目录（例如 /www/wwwroot）
cd /www/wwwroot

# 克隆项目（替换为你的GitHub仓库地址）
git clone https://github.com/YOUR_USERNAME/TheProjectSan.git

# 进入项目目录
cd TheProjectSan
```

### 2.2 检查项目结构

确保以下文件存在：
- `Dockerfile` - 后端Dockerfile
- `docker-compose.yml` - Docker Compose配置
- `Caddyfile` - Caddy反向代理配置
- `.env` - 环境变量文件（需要创建）
- `mcp_servers.json` - MCP服务器配置（需要创建）
- `frontend/Dockerfile.frontend` - 前端Dockerfile（需要创建）
- `frontend/nginx.conf` - 前端Nginx配置（需要创建）
- `requirements.linux.txt` - Python依赖

## 第三步：配置文件设置

### 3.1 创建环境变量文件

```bash
# 创建 .env 文件
cat > .env << 'EOF'
# 客户ID
CLIENT_ID=client_001

# API 密钥（至少配置一个）
OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here
# GROQ_API_KEY=your_groq_api_key_here

# 域名配置
DOMAIN=your-domain.com

# 其他配置
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
EOF

# 编辑 .env 文件，填入实际值
nano .env
```

**重要**: 将 `your-domain.com` 替换为你的实际域名，将API密钥替换为实际值。

### 3.2 创建配置文件

```bash
# 复制配置文件模板
cp conf.yaml.example conf.yaml

# 编辑配置文件
nano conf.yaml
```

在 `conf.yaml` 中：
- 将 `host: 0.0.0.0` 保持不变（Docker环境需要）
- 将API密钥字段替换为实际值，或留空使用环境变量
- 确认 `client_id: 'client_001'` 与 `.env` 中的 `CLIENT_ID` 一致

### 3.3 修改 Caddyfile

```bash
# 编辑 Caddyfile
nano Caddyfile
```

将文件开头的 `your-domain.com` 替换为你的实际域名：

```caddyfile
your-actual-domain.com {
    # ... 其他配置保持不变
}
```

## 第四步：启动服务

### 4.1 构建Docker镜像

```bash
# 构建所有服务的镜像（首次部署需要较长时间）
docker compose build

# 如果构建失败，可以查看详细日志
docker compose build --progress=plain
```

### 4.2 启动服务

```bash
# 启动所有服务（后台运行）
docker compose up -d

# 查看服务状态
docker compose ps
```

### 4.3 查看日志

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f caddy
```

## 第五步：验证部署

### 5.1 检查服务健康状态

```bash
# 检查后端健康状态
curl http://localhost:12393/health

# 应该返回: ok
```

### 5.2 检查HTTPS证书

等待几分钟让Caddy自动申请Let's Encrypt证书，然后：

```bash
# 检查HTTPS访问
curl https://your-domain.com/health

# 查看Caddy日志确认证书申请状态
docker compose logs caddy | grep -i certificate
```

### 5.3 访问前端

在浏览器中访问：
- **前端界面**: `https://your-domain.com`
- **健康检查**: `https://your-domain.com/health`
- **Web控制面板**: `https://your-domain.com/web-tool/control-panel.html?client=client_001`

## 第六步：宝塔面板配置（可选）

### 6.1 使用宝塔面板管理Docker

1. 在宝塔面板安装 **Docker管理器** 插件
2. 可以通过图形界面查看容器状态、日志等

### 6.2 设置开机自启

```bash
# 确保Docker服务开机自启
sudo systemctl enable docker

# Docker Compose服务会在容器重启时自动启动（restart: unless-stopped）
```

## 常用管理命令

### 查看服务状态

```bash
# 查看所有容器状态
docker compose ps

# 查看资源使用情况
docker stats
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启特定服务
docker compose restart backend
docker compose restart frontend
docker compose restart caddy
```

### 停止服务

```bash
# 停止所有服务
docker compose stop

# 停止并删除容器
docker compose down
```

### 更新服务

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker compose up -d --build
```

### 查看日志

```bash
# 实时查看所有日志
docker compose logs -f

# 查看最近100行日志
docker compose logs --tail=100

# 查看特定服务的日志
docker compose logs -f backend
```

## 故障排查

### 问题1: Docker安装失败（不支持的发行版）

**症状**: 执行 `sudo sh get-docker.sh` 时提示 "Unsupported distribution"

**解决方案**:
1. **OpenCloudOS / 其他不支持的发行版**，使用手动安装方法（见步骤1.1的方法2）
2. **检查系统版本**：
   ```bash
   cat /etc/os-release
   ```
3. **如果系统基于CentOS/RHEL**，可以使用CentOS的Docker仓库：
   ```bash
   sudo yum install -y yum-utils
   sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
   sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
   sudo systemctl start docker
   sudo systemctl enable docker
   ```
4. **如果系统基于Debian/Ubuntu**，可以使用Debian的Docker仓库：
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

### 问题2: HTTPS证书申请失败

**症状**: Caddy日志显示证书申请错误

**解决方案**:
1. 检查DNS解析是否正确：
   ```bash
   nslookup your-domain.com
   ```
2. 检查端口80和443是否开放：
   ```bash
   sudo netstat -tulpn | grep :80
   sudo netstat -tulpn | grep :443
   ```
3. 检查宝塔面板是否占用了80/443端口，如果是，需要：
   - 停止宝塔面板的Nginx/Apache服务
   - 或修改Caddy使用其他端口

### 问题3: 后端服务无法启动

**症状**: `docker compose ps` 显示backend状态为 unhealthy 或 exited

**解决方案**:
1. 查看后端日志：
   ```bash
   docker compose logs backend
   ```
2. 检查配置文件是否正确：
   ```bash
   cat conf.yaml | grep -A 5 "host:\|port:"
   ```
3. 检查环境变量：
   ```bash
   docker compose exec backend env | grep CLIENT_ID
   ```

### 问题4: 前端无法访问后端API

**症状**: 前端页面加载但API请求失败

**解决方案**:
1. 检查网络连接：
   ```bash
   docker compose exec frontend ping backend
   ```
2. 检查后端健康状态：
   ```bash
   docker compose exec frontend curl http://backend:12393/health
   ```
3. 检查Caddy配置是否正确代理了 `/api/*` 路径

### 问题5: WebSocket连接失败

**症状**: 前端无法建立WebSocket连接

**解决方案**:
1. 检查Caddyfile中的WebSocket配置：
   ```bash
   cat Caddyfile | grep -A 10 "client-ws"
   ```
2. 检查后端WebSocket端点：
   ```bash
   curl http://localhost:12393/client-ws
   ```
3. 查看浏览器控制台错误信息

### 问题6: 端口冲突

**症状**: 容器启动失败，提示端口被占用

**解决方案**:
1. 检查端口占用：
   ```bash
   sudo netstat -tulpn | grep -E ":(80|443|12393|3000)"
   ```
2. 如果宝塔面板占用了80/443，需要：
   - 停止宝塔的Web服务
   - 或修改docker-compose.yml中的端口映射

## 数据备份

### 备份重要数据

```bash
# 创建备份目录
mkdir -p /backup/theproject-san

# 备份数据目录
tar -czf /backup/theproject-san/backup-$(date +%Y%m%d).tar.gz \
  cache/ logs/ topics/ ads/ conf.yaml .env

# 备份Docker卷（如果需要）
docker run --rm -v theproject-san_caddy_data:/data -v /backup:/backup \
  alpine tar czf /backup/caddy-data-$(date +%Y%m%d).tar.gz -C /data .
```

### 恢复数据

```bash
# 停止服务
docker compose down

# 恢复数据
tar -xzf /backup/theproject-san/backup-YYYYMMDD.tar.gz

# 重新启动服务
docker compose up -d
```

## 性能优化

### 1. 调整资源限制

在 `docker-compose.yml` 中为服务添加资源限制：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 2. 启用日志轮转

在 `docker-compose.yml` 中配置日志：

```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 安全建议

1. **定期更新**: 
   ```bash
   git pull
   docker compose pull
   docker compose up -d --build
   ```

2. **保护敏感信息**: 
   - 确保 `.env` 和 `conf.yaml` 不在Git仓库中
   - 使用强密码和API密钥

3. **防火墙配置**: 
   - 只开放必要端口（80, 443, 22）
   - 使用宝塔面板的安全功能

4. **定期备份**: 
   - 设置自动备份脚本
   - 将备份存储到安全位置

## 监控和维护

### 查看资源使用

```bash
# 查看容器资源使用
docker stats

# 查看磁盘使用
df -h
docker system df
```

### 清理无用资源

```bash
# 清理未使用的镜像、容器、网络
docker system prune -a

# 清理构建缓存
docker builder prune
```

## 联系和支持

如遇到问题，请：
1. 查看日志文件：`logs/debug_*.log`
2. 查看Docker日志：`docker compose logs`
3. 检查GitHub Issues
4. 查看项目文档

## 附录：完整文件清单

部署完成后，项目目录应包含：

```
TheProjectSan/
├── Dockerfile                 # 后端Dockerfile
├── docker-compose.yml         # Docker Compose配置
├── Caddyfile                  # Caddy反向代理配置
├── .env                       # 环境变量（不提交到Git）
├── conf.yaml                  # 配置文件（不提交到Git）
├── requirements.linux.txt     # Python依赖
├── run_server.py              # 启动脚本
├── frontend/
│   ├── Dockerfile.frontend    # 前端Dockerfile
│   └── nginx.conf             # 前端Nginx配置
├── cache/                     # 缓存目录
├── logs/                      # 日志目录
├── topics/                    # 主题数据
├── ads/                       # 广告数据
└── 部署指南/
    └── DEPLOYMENT.md          # 本文档
```

---

**部署完成后，请访问 `https://your-domain.com` 验证系统是否正常运行。**
