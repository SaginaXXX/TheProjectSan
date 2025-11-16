# ❓ S3集成常见问题 FAQ

## 🎯 配置相关

### Q1: 必须使用AWS S3吗？可以用阿里云OSS吗？

**A**: 可以！S3StorageService使用boto3库，它兼容S3协议的对象存储服务。

**阿里云OSS配置**:
```python
# src/ai_chat/storage/s3_service.py
# 修改S3客户端初始化

self.s3_client = boto3.client(
    's3',
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    endpoint_url='https://oss-cn-hangzhou.aliyuncs.com'  # ← 添加endpoint
)
```

**支持的服务商**:
- ✅ AWS S3
- ✅ 阿里云OSS（需配置endpoint）
- ✅ 腾讯云COS（需配置endpoint）
- ✅ MinIO（自建，需配置endpoint）
- ✅ Backblaze B2（需配置endpoint）
- ✅ DigitalOcean Spaces

---

### Q2: storage_type配置在哪里？如何切换？

**A**: 在`conf.yaml`文件中配置：

```yaml
system_config:
  media_server:
    storage_type: "local"  # 或 "s3"
```

**切换步骤**:
```bash
# 1. 修改配置文件
vim conf.yaml
# 将 storage_type: "local" 改为 storage_type: "s3"

# 2. 配置S3参数（首次）
# 添加 s3_bucket, s3_region 等

# 3. 重启服务器
python run_server.py

# ✅ 自动切换到S3模式
```

**无需修改代码**，只需修改配置！

---

### Q3: S3凭证应该写在配置文件还是环境变量？

**A**: 强烈推荐使用**环境变量**，避免敏感信息泄露。

**❌ 不推荐（安全风险）**:
```yaml
# conf.yaml
s3_access_key: "AKIAIOSFODNN7EXAMPLE"  # ❌ 会被提交到Git
s3_secret_key: "wJalrXUtnFEMI/..."     # ❌ 敏感信息泄露
```

**✅ 推荐**:
```yaml
# conf.yaml
s3_bucket: "my-bucket"  # ✅ 可以公开
s3_region: "us-east-1"  # ✅ 可以公开
# s3_access_key 留空
# s3_secret_key 留空
```

```bash
# .env (不提交到Git)
AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**.gitignore**:
```
.env
.env.local
.env.production
*.secret
```

---

### Q4: CDN是必须的吗？

**A**: 不必须，但**强烈推荐**。

**不使用CDN**:
```python
# S3直连URL（慢）
https://my-bucket.s3.us-east-1.amazonaws.com/client_001/ads/video.mp4

缺点:
❌ 速度慢（跨区域延迟高）
❌ S3请求成本高
❌ 无法利用边缘缓存
```

**使用CDN**:
```python
# CDN加速URL（快）
https://cdn.example.com/client_001/ads/video.mp4

优点:
✅ 全球加速（边缘节点）
✅ 降低S3成本
✅ 自动HTTPS
✅ 缓存优化
✅ 带宽优化
```

**推荐**: 生产环境必须使用CDN

---

## 🔐 安全相关

### Q5: 如何确保不同CLIENT_ID的数据隔离？

**A**: 项目采用**多层隔离机制**：

**1. S3 Key前缀隔离**:
```
client_001/ads/video1.mp4  ← 星巴克
client_002/ads/video2.mp4  ← 麦当劳

✅ 不同前缀，逻辑隔离
```

**2. API参数验证**:
```python
# 上传时验证CLIENT_ID
client_id = request.form.get('client')
if client_id != expected_client_id:
    raise PermissionError("CLIENT_ID不匹配")
```

**3. IAM策略隔离**（可选，最安全）:
```json
{
    "Effect": "Allow",
    "Action": ["s3:PutObject"],
    "Resource": ["arn:aws:s3:::bucket/client_001/*"],
    "Condition": {
        "StringLike": {"s3:prefix": ["client_001/*"]}
    }
}
```

**4. 应用层过滤**:
```python
# 列表时只返回当前CLIENT_ID的文件
async def list_files(category: str):
    prefix = f"{self.client_id}/{category}/"  # 只扫描自己的前缀
    return files
```

---

### Q6: S3桶应该设置为公开还是私有？

**A**: 取决于是否使用CDN。

**方案A: 公开读取（推荐，简单）**
```bash
# S3桶策略
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::my-bucket/*"
        }
    ]
}

优点:
✅ CDN直接访问，无需签名
✅ 配置简单
✅ 性能好

缺点:
❌ 任何人都能访问（如果知道URL）

适用: 广告视频等公开内容
```

**方案B: 私有桶 + 预签名URL（安全）**
```python
# 生成有时效的预签名URL
def get_file_url(self, category: str, filename: str) -> str:
    s3_key = self._get_s3_key(category, filename)
    
    # 生成1小时有效的签名URL
    url = self.s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': self.bucket, 'Key': s3_key},
        ExpiresIn=3600  # 1小时
    )
    return url

优点:
✅ 完全私有，安全
✅ URL有时效性
✅ 可撤销访问

缺点:
❌ 配置复杂
❌ CDN需要特殊配置
❌ 性能稍差（每次生成URL）

适用: 敏感内容、付费内容
```

**推荐**: 广告视频使用**公开桶**，简单高效

---

## 📦 部署相关

### Q7: 可以在本地开发时使用S3吗？

**A**: 可以，但**不推荐**。

**本地开发**:
```yaml
# conf.yaml (开发环境)
storage_type: "local"  # ← 使用本地存储
```

**生产部署**:
```yaml
# conf.yaml (生产环境)
storage_type: "s3"     # ← 使用S3存储
```

**原因**:
- ✅ 本地开发快速迭代，无需网络
- ✅ 节省S3成本
- ✅ 离线开发

**测试S3**:
```bash
# 临时切换到S3测试
export STORAGE_TYPE=s3
export S3_BUCKET=test-bucket
python run_server.py

# 测试完毕切回本地
unset STORAGE_TYPE
```

---

### Q8: 多个容器可以共享一个S3桶吗？

**A**: 可以！这是推荐的部署方式。

```
3个容器 + 1个S3桶 = ✅ 完美

Container 1 (CLIENT_ID=client_001)  ─┐
Container 2 (CLIENT_ID=client_002)  ─┼→ s3://my-bucket/
Container 3 (CLIENT_ID=client_003)  ─┘    ├─ client_001/
                                           ├─ client_002/
                                           └─ client_003/

✅ 统一管理
✅ 降低成本（只需1个桶）
✅ CLIENT_ID前缀隔离，互不干扰
```

**隔离保证**:
- Container 1上传 → `client_001/ads/`
- Container 2上传 → `client_002/ads/`
- Container 3上传 → `client_003/ads/`
- ✅ 永不冲突

---

### Q9: Docker部署时CLIENT_ID如何配置？

**A**: 通过**环境变量**配置，每个容器不同。

```yaml
# docker-compose.yml
services:
  backend_client001:
    environment:
      - CLIENT_ID=client_001  # ← 容器1的CLIENT_ID
  
  backend_client002:
    environment:
      - CLIENT_ID=client_002  # ← 容器2的CLIENT_ID
```

**优先级**:
```
环境变量 CLIENT_ID  (最高，Docker使用)
    ↓
配置文件 conf.yaml  (次级，本地开发使用)
    ↓
默认值 default_client (兜底)
```

---

## 🚀 性能相关

### Q10: S3上传速度慢怎么办？

**A**: 多种优化方案。

**方案1: 使用S3传输加速**
```python
# 启用传输加速
self.s3_client = boto3.client(
    's3',
    config=Config(
        s3={'use_accelerate_endpoint': True}  # ← 传输加速
    )
)

# 需要在S3桶启用传输加速
aws s3api put-bucket-accelerate-configuration \
    --bucket my-bucket \
    --accelerate-configuration Status=Enabled

优势:
✅ 全球上传加速50-500%
✅ 自动选择最优路径

成本:
💰 每GB额外 $0.04
```

**方案2: 选择就近区域**
```yaml
# 中国用户使用中国区域
s3_region: "cn-north-1"  # AWS中国（北京）

# 或使用阿里云OSS
storage_type: "s3"
endpoint_url: "https://oss-cn-hangzhou.aliyuncs.com"
```

**方案3: 多部分上传（大文件）**
```python
# 大于5MB的文件使用多部分上传
if file_size > 5 * 1024 * 1024:
    # 分片上传，提高成功率
    s3_client.upload_fileobj(
        file_data,
        bucket,
        key,
        Config=TransferConfig(
            multipart_threshold=5 * 1024 * 1024,
            multipart_chunksize=5 * 1024 * 1024
        )
    )
```

---

### Q11: CDN缓存过期怎么办？

**A**: 使用**缓存失效API**或**版本号策略**。

**方案1: CloudFront缓存失效**
```python
# 上传新文件后，让CDN失效旧缓存
import boto3

cloudfront = boto3.client('cloudfront')
cloudfront.create_invalidation(
    DistributionId='E1234567890ABC',
    InvalidationBatch={
        'Paths': {
            'Quantity': 1,
            'Items': ['/client_001/ads/*']
        },
        'CallerReference': str(int(time.time()))
    }
)

优点:
✅ 立即生效
✅ 灵活控制

缺点:
❌ 有成本（前1000次/月免费）
❌ 需要额外API调用
```

**方案2: 版本号策略（推荐）**
```python
# 文件名包含时间戳，自动版本化
filename = f"video_{timestamp}.mp4"

# URL自动变化
# 旧: https://cdn.example.com/client_001/ads/video_1730000000.mp4
# 新: https://cdn.example.com/client_001/ads/video_1730000100.mp4

优点:
✅ 零成本
✅ 无需失效
✅ 旧文件可保留

缺点:
❌ 文件名冗长
```

**项目已采用**: 方案2（时间戳版本化）

---

### Q12: 本地缓存如何配置？

**A**: S3模式下仍可使用本地缓存提速。

```yaml
# conf.yaml
system_config:
  media_server:
    storage_type: "s3"
    
    # 缓存配置
    cache_enabled: true         # ← 启用缓存
    cache_dir: "cache"          # ← 缓存目录
    cache_size_limit: "10GB"    # ← 缓存大小限制
```

**缓存策略**:
```python
# 智能缓存（未来实现）
async def get_file_with_cache(category: str, filename: str):
    cache_path = f"cache/{client_id}/{category}/{filename}"
    
    # 1. 检查本地缓存
    if os.path.exists(cache_path):
        # 检查是否过期（例如24小时）
        if time.time() - os.path.getmtime(cache_path) < 86400:
            return cache_path  # 使用缓存
    
    # 2. 从S3下载
    file_data = await s3_client.get_object(...)
    
    # 3. 保存到缓存
    with open(cache_path, 'wb') as f:
        f.write(file_data)
    
    return cache_path
```

**优势**:
- ✅ 第一次从S3加载
- ✅ 后续从本地缓存加载（快）
- ✅ 自动清理旧缓存
- ✅ 节省S3请求成本

---

## 🔧 故障排除

### Q13: 上传到S3失败，提示"Access Denied"

**原因**: IAM权限不足

**解决**:
```bash
# 1. 检查IAM用户权限
aws iam get-user-policy --user-name ai-screen-uploader --policy-name S3FullAccess

# 2. 确保有以下权限
{
    "Action": [
        "s3:PutObject",      # 上传
        "s3:GetObject",      # 读取
        "s3:DeleteObject",   # 删除
        "s3:ListBucket"      # 列表
    ]
}

# 3. 检查桶策略
aws s3api get-bucket-policy --bucket my-bucket

# 4. 测试凭证
aws s3 ls s3://my-bucket --profile ai-screen
```

---

### Q14: CDN访问返回403 Forbidden

**原因**: CORS配置问题或桶权限问题

**解决**:
```bash
# 1. 检查S3 CORS配置
aws s3api get-bucket-cors --bucket my-bucket

# 2. 添加CORS规则
{
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["*"],
            "MaxAgeSeconds": 3600
        }
    ]
}

# 3. 检查CDN Origin配置
# 确保CDN能访问S3源站

# 4. 测试直接访问S3
curl -I https://my-bucket.s3.us-east-1.amazonaws.com/client_001/ads/test.mp4
# 应该返回 200 OK
```

---

### Q15: MCP服务器找不到广告视频

**原因**: MCP服务器未使用storage_service

**解决**:
```python
# ❌ 问题代码
self.ads_dir = Path("ads") / self.client_id
for file in self.ads_dir.iterdir():  # S3模式下目录不存在

# ✅ 修改为
self.storage_service = create_storage_service(config, client_id)
files = await self.storage_service.list_files("ads")  # 自动适配S3
```

**验证**:
```bash
# 1. 查看MCP服务器日志
# 应该显示: "使用存储服务: S3StorageService"

# 2. 检查S3中的文件
aws s3 ls s3://my-bucket/client_001/ads/

# 3. 调用MCP refresh工具
# 应该能刷新S3中的文件
```

---

## 💰 成本相关

### Q16: S3成本如何控制？

**A**: 多种优化策略。

**1. 使用智能分层存储**
```python
# 上传时设置存储类
s3_client.put_object(
    Bucket=bucket,
    Key=key,
    Body=data,
    StorageClass='INTELLIGENT_TIERING'  # ← 智能分层
)

优势:
✅ 自动优化存储类
✅ 30天未访问 → 归档层（省80%）
✅ 访问时自动恢复
```

**2. 设置生命周期规则**
```json
{
    "Rules": [
        {
            "Id": "DeleteOldAds",
            "Status": "Enabled",
            "Filter": {
                "Prefix": "client_001/ads/"
            },
            "Expiration": {
                "Days": 365  # 1年后自动删除
            }
        }
    ]
}

优势:
✅ 自动清理旧文件
✅ 降低存储成本
```

**3. 使用Cloudflare CDN**
```
S3下载流量成本: $0.09/GB
Cloudflare CDN流量: 免费（无限）

✅ 节省90%流量成本！
```

**4. 选择低成本服务商**
```
Backblaze B2:
- 存储: $0.005/GB/月 (AWS的1/5)
- 下载: 前10GB免费
- 总成本: ~$5/月（100GB）

AWS S3:
- 存储: $0.023/GB/月
- 下载: $0.09/GB
- 总成本: ~$20/月（100GB）

✅ B2省75%成本！
```

---

### Q17: 如何估算我的S3成本？

**A**: 使用以下公式。

**成本计算器**:
```python
# 输入参数
storage_gb = 100            # 存储量（GB）
downloads_gb_per_month = 200  # 月下载量（GB）
requests_per_month = 500000   # 月请求数

# AWS S3成本
storage_cost = storage_gb * 0.023                    # 存储费用
download_cost = downloads_gb_per_month * 0.09        # 流量费用
request_cost = (requests_per_month / 1000) * 0.0004  # 请求费用

total_cost = storage_cost + download_cost + request_cost

print(f"月度总成本: ${total_cost:.2f}")
# 输出: 月度总成本: $20.50

# Backblaze B2成本
storage_cost_b2 = storage_gb * 0.005
download_cost_b2 = max(0, (downloads_gb_per_month - 10)) * 0.01  # 前10GB免费

total_cost_b2 = storage_cost_b2 + download_cost_b2

print(f"B2月度总成本: ${total_cost_b2:.2f}")
# 输出: B2月度总成本: $2.40

print(f"节省: ${total_cost - total_cost_b2:.2f}")
# 输出: 节省: $18.10
```

---

## 🔄 迁移相关

### Q18: 如何从本地存储迁移到S3？

**A**: 提供自动迁移脚本。

**migrate_to_s3.py**:
```python
#!/usr/bin/env python3
"""
本地存储 → S3 迁移脚本
"""

import os
import boto3
from pathlib import Path
from tqdm import tqdm

def migrate_to_s3(
    local_base: str,
    s3_bucket: str,
    client_ids: list
):
    """
    迁移本地文件到S3
    
    Args:
        local_base: 本地基础目录（例如: "."）
        s3_bucket: S3桶名
        client_ids: 要迁移的CLIENT_ID列表
    """
    s3_client = boto3.client('s3')
    
    for client_id in client_ids:
        print(f"\n📦 开始迁移 {client_id}...")
        
        # 迁移广告视频
        ads_dir = Path(local_base) / "ads" / client_id
        if ads_dir.exists():
            files = list(ads_dir.glob("*.*"))
            
            for file_path in tqdm(files, desc=f"上传 {client_id} 广告"):
                s3_key = f"{client_id}/ads/{file_path.name}"
                
                with open(file_path, 'rb') as f:
                    s3_client.put_object(
                        Bucket=s3_bucket,
                        Key=s3_key,
                        Body=f.read(),
                        ContentType=get_content_type(file_path.name)
                    )
                
                print(f"✅ {file_path.name} → s3://{s3_bucket}/{s3_key}")
        
        # 迁移Agent资源
        agent_dir = Path(local_base) / "agent" / client_id
        if agent_dir.exists():
            # 类似处理
            pass
    
    print("\n✅ 迁移完成！")
    print(f"请修改 conf.yaml 中的 storage_type: s3")

def get_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    content_types = {
        '.mp4': 'video/mp4',
        '.jpg': 'image/jpeg',
        '.png': 'image/png'
    }
    return content_types.get(ext, 'application/octet-stream')

if __name__ == "__main__":
    migrate_to_s3(
        local_base=".",
        s3_bucket="my-ads-bucket",
        client_ids=["client_001", "client_002", "client_003"]
    )
```

**使用步骤**:
```bash
# 1. 配置AWS凭证
export AWS_ACCESS_KEY=xxx
export AWS_SECRET_KEY=xxx

# 2. 运行迁移脚本
python migrate_to_s3.py

# 3. 等待迁移完成
# 📦 开始迁移 client_001...
# ✅ video1.mp4 → s3://my-bucket/client_001/ads/video1.mp4
# ✅ video2.mp4 → s3://my-bucket/client_001/ads/video2.mp4
# ✅ 迁移完成！

# 4. 修改配置
vim conf.yaml
# storage_type: "s3"

# 5. 重启服务器
python run_server.py

# ✅ 现在使用S3存储
```

---

### Q19: S3迁移后本地文件可以删除吗？

**A**: 建议先**备份验证**再删除。

**安全迁移流程**:
```bash
# 1. 迁移到S3
python migrate_to_s3.py

# 2. 验证S3文件完整性
aws s3 ls s3://my-bucket/client_001/ads/ --recursive

# 3. 对比本地和S3数量
LOCAL_COUNT=$(find ads/client_001 -type f | wc -l)
S3_COUNT=$(aws s3 ls s3://my-bucket/client_001/ads/ | wc -l)

if [ "$LOCAL_COUNT" -eq "$S3_COUNT" ]; then
    echo "✅ 文件数量一致"
else
    echo "❌ 文件数量不一致，请检查"
    exit 1
fi

# 4. 测试S3模式能正常工作
# 切换到storage_type: "s3"，测试1周

# 5. 确认无误后，备份本地文件
tar -czf ads_backup_$(date +%Y%m%d).tar.gz ads/

# 6. 删除本地文件（可选）
rm -rf ads/client_001/*

# 保留目录结构，方便未来回滚
```

---

## 🎯 技术选型

### Q20: 如何选择S3服务商？

**A**: 根据需求和预算选择。

**选择矩阵**:

| 需求 | 推荐服务商 | 原因 |
|------|-----------|------|
| **国内用户** | 阿里云OSS | ✅ 速度快<br/>✅ 中文支持<br/>✅ 本地化 |
| **国际用户** | AWS S3 | ✅ 全球覆盖<br/>✅ 生态完善<br/>✅ 稳定可靠 |
| **成本优先** | Backblaze B2 | ✅ 价格最低<br/>✅ Cloudflare免费CDN<br/>✅ 无隐藏费用 |
| **自主可控** | MinIO (自建) | ✅ 完全掌控<br/>✅ 无外部依赖<br/>❌ 需要运维 |
| **政府/金融** | 私有云S3 | ✅ 合规要求<br/>✅ 数据本地化<br/>💰 成本高 |

**性价比排行**:
1. 🥇 **Backblaze B2 + Cloudflare CDN** - 最省钱
2. 🥈 **阿里云OSS** - 国内速度快
3. 🥉 **AWS S3 + CloudFront** - 生态最完善
4. MinIO（自建）- 完全免费，需运维
5. 腾讯云COS - 与阿里云类似

---

### Q21: 支持对象存储之外的云存储吗？

**A**: 理论上可以，但需要额外开发。

**当前支持（S3协议）**:
- ✅ AWS S3
- ✅ 阿里云OSS（S3兼容模式）
- ✅ MinIO
- ✅ Backblaze B2

**不直接支持（需要适配）**:
- ❌ 腾讯云COS（有S3兼容模式，可用）
- ❌ 七牛云Kodo（需要开发KodoStorageService）
- ❌ 又拍云USS（需要开发USSStorageService）

**扩展方法**:
```python
# 新增 KodoStorageService
class KodoStorageService(StorageInterface):
    """七牛云Kodo存储服务"""
    
    def __init__(self, client_id, bucket, access_key, secret_key):
        from qiniu import Auth, put_data
        self.qiniu_auth = Auth(access_key, secret_key)
        self.bucket = bucket
    
    async def upload_file(self, file_data, category, filename):
        # 使用七牛SDK上传
        token = self.qiniu_auth.upload_token(self.bucket)
        ret, info = put_data(token, key, file_data)
        return key

# 在storage_factory中添加
if storage_type == "kodo":
    return KodoStorageService(...)
```

---

## 📊 监控和维护

### Q22: 如何监控S3使用情况？

**A**: 使用AWS CloudWatch或自定义监控。

**AWS CloudWatch**:
```bash
# 查看S3桶指标
aws cloudwatch get-metric-statistics \
    --namespace AWS/S3 \
    --metric-name BucketSizeBytes \
    --dimensions Name=BucketName,Value=my-bucket \
    --start-time 2024-10-01T00:00:00Z \
    --end-time 2024-10-27T23:59:59Z \
    --period 86400 \
    --statistics Average

# 查看请求数
aws cloudwatch get-metric-statistics \
    --namespace AWS/S3 \
    --metric-name NumberOfObjects \
    ...
```

**自定义监控**:
```python
# 定期统计脚本
import boto3

s3 = boto3.client('s3')

def get_bucket_stats(bucket: str):
    total_size = 0
    file_count = 0
    
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            total_size += obj['Size']
            file_count += 1
    
    return {
        "file_count": file_count,
        "total_size_gb": total_size / (1024**3),
        "estimated_cost": total_size / (1024**3) * 0.023  # $0.023/GB
    }

stats = get_bucket_stats("my-bucket")
print(f"文件数: {stats['file_count']}")
print(f"总大小: {stats['total_size_gb']:.2f} GB")
print(f"估算成本: ${stats['estimated_cost']:.2f}/月")
```

---

### Q23: 如何备份S3数据？

**A**: S3本身已经高可用，但仍建议跨区域复制。

**方案1: S3跨区域复制（推荐）**
```bash
# 启用跨区域复制
aws s3api put-bucket-replication \
    --bucket my-bucket \
    --replication-configuration file://replication.json
```

**replication.json**:
```json
{
    "Role": "arn:aws:iam::123456789:role/s3-replication-role",
    "Rules": [
        {
            "Status": "Enabled",
            "Priority": 1,
            "Filter": {},
            "Destination": {
                "Bucket": "arn:aws:s3:::my-bucket-backup",
                "ReplicationTime": {
                    "Status": "Enabled",
                    "Time": {"Minutes": 15}
                }
            }
        }
    ]
}
```

**方案2: 定期同步到本地**
```bash
# 定时任务：每天备份S3到本地
#!/bin/bash
# backup_s3.sh

BACKUP_DIR="/backup/s3_$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 同步S3到本地
aws s3 sync s3://my-bucket "$BACKUP_DIR"

# 压缩备份
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"

# 删除临时目录
rm -rf "$BACKUP_DIR"

# 保留最近7天的备份
find /backup -name "s3_*.tar.gz" -mtime +7 -delete
```

**crontab配置**:
```cron
# 每天凌晨3点备份
0 3 * * * /path/to/backup_s3.sh
```

---

## 🎯 总结

### 关键要点

1. **配置优先级**: 环境变量 > 配置文件
2. **成本优化**: 使用B2+Cloudflare最省钱
3. **安全第一**: 凭证使用环境变量，不写配置文件
4. **CDN必备**: 生产环境必须使用CDN
5. **CLIENT_ID隔离**: 确保多租户数据安全
6. **渐进迁移**: 先测试再切换，保留本地备份

### 快速参考

```bash
# 切换到S3
storage_type: "s3"

# 切换到本地
storage_type: "local"

# 查看S3文件
aws s3 ls s3://my-bucket/client_001/ads/

# 上传测试
curl -F "file=@test.mp4" http://localhost:12393/api/upload?client=client_001

# 健康检查
curl http://localhost:12393/api/health
```

---

**完整系列目录**:
- [01-集成思路与架构设计](./01-集成思路与架构设计.md)
- [02-广告视频S3上传详解](./02-广告视频S3上传详解.md)
- [03-Agent资源动态上传](./03-Agent资源动态上传.md)
- [04-项目整体架构与部署](./04-项目整体架构与部署.md)
- [05-生产环境部署指南](./05-生产环境部署指南.md)
- [06-实施路线图](./06-实施路线图.md)
- [07-常见问题FAQ](./07-常见问题FAQ.md) ← 当前

