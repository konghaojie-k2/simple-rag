# 文件存储迁移到Supabase Storage Bucket

## 概述

本次更新将原始文件的保存方式从数据库存储迁移到Supabase Storage Bucket，提升了文件存储的性能和可扩展性。

## 修改日期
2025-10-03

## 主要改动

### 1. HybridFileStorage 增强 (`rag_core/utils/hybrid_storage.py`)

#### 修改内容：
- **阈值调整**：将 `SIZE_THRESHOLD` 从 `1024 * 1024` (1MB) 改为 `0`，意味着所有文件都将使用Storage bucket存储
- **新增同步方法**：添加了同步版本的文件操作方法，以支持非异步代码调用

#### 新增方法：
```python
# 同步版本的文件存储方法
def store_file_sync(file_content: bytes, filename: str, collection_name: str = "default") -> dict

# 同步版本的文件内容获取
def get_file_content_sync(file_id: str) -> Optional[Tuple[str, str, bytes]]

# 同步版本的Storage上传
def _store_in_storage_sync(file_content: bytes, filename: str, file_hash: str) -> str

# 同步版本的Storage下载
def _download_from_storage_sync(storage_path: str) -> bytes

# 同步版本的文件存在性检查
def _check_file_exists_sync(file_hash: str) -> Optional[dict]
```

#### 工作流程：
1. 接收文件内容和文件名
2. 计算文件SHA-256哈希值用于去重
3. 检查文件是否已存在（基于哈希）
4. 将文件上传到Supabase Storage bucket
5. 在`document_files`表中保存文件元数据（包含storage_path，不包含file_content）

### 2. SupabaseRAG 类更新 (`rag_core/pipeline/supabase_rag.py`)

#### 初始化增强：
```python
def __init__(self, config: RAGConfig, supabase_config: SupabaseConfig, bucket_name: str = "documents"):
    # ...
    # 初始化文件存储管理器
    self.file_storage = HybridFileStorage(
        supabase_client=self.supabase,
        bucket_name=bucket_name
    )
```

#### `store_raw_file_only` 方法重构：
**修改前**：
- 将文件内容Base64编码后存储到数据库的`file_content`字段
- 直接操作Supabase表

**修改后**：
```python
def store_raw_file_only(self, file_content: bytes, filename: str) -> bool:
    try:
        # 使用HybridFileStorage保存文件到Storage bucket
        file_record = self.file_storage.store_file_sync(
            file_content=file_content,
            filename=filename,
            collection_name=self.supabase_config.collection_name
        )
        
        inserted_file_id = file_record["id"]
        self.logger.info(f"原始文件已保存到Storage: {filename}, ID: {inserted_file_id}, Path: {file_record.get('storage_path')}")
        
        # 检查是否已有对应的document_metadata记录需要更新file_id
        self._update_metadata_file_link(filename, inserted_file_id)
        
        return True
        
    except Exception as e:
        self.logger.error(f"保存原始文件到Storage失败: {str(e)}")
        return False
```

#### `get_file_content` 方法增强：
**修改前**：
- 只从数据库RPC函数获取文件内容

**修改后**：
```python
def get_file_content(self, file_id: str) -> Optional[Tuple[str, str, bytes]]:
    try:
        # 优先使用HybridFileStorage获取文件内容（支持Storage）
        result = self.file_storage.get_file_content_sync(file_id)
        
        if result:
            return result
        
        # 后备方案：尝试使用旧的RPC方法（兼容旧数据）
        try:
            response = self.supabase.rpc("get_file_content", {"file_id_input": file_id}).execute()
            # ...
        except Exception as rpc_error:
            self.logger.warning(f"RPC方法获取文件失败: {str(rpc_error)}")
        
        return None
        
    except Exception as e:
        self.logger.error(f"获取文件内容失败: {str(e)}")
        return None
```

### 3. API服务器更新 (`api_server/main.py`)

#### RAG实例创建增强：
```python
def get_rag_instance(knowledge_base: str = "default") -> SupabaseRAG:
    # ...
    # 获取bucket名称配置
    bucket_name = os.getenv("SUPABASE_BUCKET_NAME", "documents")
    
    # 创建新实例并缓存
    instance = SupabaseRAG(config, supabase_config, bucket_name=bucket_name)
    logger.info(f"创建并缓存新的RAG实例 - 知识库: {knowledge_base}, Bucket: {bucket_name}")
    # ...
```

#### 配置更新API修改：
```python
@app.post("/api/v1/config")
async def update_config(request: ConfigUpdateRequest):
    # ...
    bucket_name = os.getenv("SUPABASE_BUCKET_NAME", "documents")
    rag_instance = SupabaseRAG(new_config, supabase_config, bucket_name=bucket_name)
    # ...
```

### 4. 环境变量配置 (`env.example`)

#### 新增配置项：
```env
# Storage配置
SUPABASE_BUCKET_NAME=documents
```

## 数据库表结构

### document_files 表字段说明：

| 字段名 | 类型 | 说明 | 新旧对比 |
|--------|------|------|----------|
| `storage_path` | TEXT | Storage中的文件路径 | **新**：现在必填 |
| `file_content` | BYTEA/TEXT | 数据库中的文件内容 | **旧**：现在为NULL |

**存储路径格式**：`{hash[:2]}/{hash}{extension}`
- 例如：`ab/abcdef1234567890.pdf`
- 使用文件哈希的前2个字符作为子目录，避免单目录文件过多

## Storage Bucket 配置

### Bucket 创建
系统会自动创建名为 `documents` 的 Storage bucket（如果不存在）：

```python
self.supabase.storage.create_bucket(
    self.bucket_name,
    options={"public": False}  # 私有bucket
)
```

### 权限设置
- **类型**：私有bucket
- **访问**：需要通过签名URL或API端点访问
- **安全**：文件内容不公开，需要认证

## 文件操作流程

### 上传流程：
```
用户上传文件
    ↓
计算文件哈希（SHA-256）
    ↓
检查是否已存在（去重）
    ↓
上传到Storage bucket
    ↓
在document_files表中保存元数据
    ├── storage_path: "ab/abcdef...pdf"
    ├── file_content: NULL
    └── file_hash: "abcdef..."
```

### 下载流程：
```
用户请求下载
    ↓
查询document_files表
    ↓
检查storage_path字段
    ↓
从Storage bucket下载文件
    ↓
返回文件内容
```

## 优势

### 1. 性能提升
- ✅ **数据库负载降低**：不再存储大型二进制文件
- ✅ **查询速度提升**：document_files表大小显著减小
- ✅ **并发处理能力增强**：Storage专门优化文件访问

### 2. 可扩展性
- ✅ **存储容量无限**：不受PostgreSQL表大小限制
- ✅ **支持大文件**：可存储任意大小的文件
- ✅ **CDN加速**：可配置CDN加速文件下载

### 3. 成本优化
- ✅ **降低数据库成本**：数据库只存储元数据
- ✅ **存储分层**：Storage通常比数据库存储更便宜
- ✅ **按需计费**：Storage按实际使用量计费

### 4. 维护性
- ✅ **文件去重**：基于哈希自动去重
- ✅ **独立备份**：文件和数据库可分别备份
- ✅ **易于迁移**：文件存储位置独立于应用逻辑

## 向后兼容性

### 旧数据支持
系统仍然支持从数据库中读取旧的文件内容：

```python
# get_file_content 方法的后备逻辑
if file_info.get("storage_path"):
    # 新数据：从Storage下载
    content = self._download_from_storage_sync(file_info["storage_path"])
else:
    # 旧数据：从数据库获取
    import base64
    content = base64.b64decode(file_info["file_content"])
```

### 迁移建议
对于已有的数据库文件，可以选择：
1. **保持现状**：旧文件继续从数据库读取
2. **批量迁移**：编写脚本将旧文件迁移到Storage
3. **渐进迁移**：在访问时自动迁移到Storage

## 测试验证

### 测试清单
- [ ] 上传新文件到Storage
- [ ] 下载Storage中的文件
- [ ] 下载数据库中的旧文件（向后兼容）
- [ ] 文件去重验证
- [ ] 大文件上传测试（>10MB）
- [ ] 并发上传测试

### 测试命令
```python
# 使用API客户端测试
from examples.api_client_example import KnowledgeAPIClient

client = KnowledgeAPIClient("http://localhost:8002")

# 测试文件上传
result = client.upload_file_in_kb("default", "test.pdf")
print(f"上传结果: {result}")

# 测试文件下载
file_content = client.download_file(file_id)
print(f"下载成功，文件大小: {len(file_content)} bytes")
```

## 常见问题

### Q: 如何查看Storage中的文件？
A: 在Supabase Dashboard → Storage → documents bucket 中查看

### Q: 文件是否会重复存储？
A: 不会。系统使用SHA-256哈希进行去重，相同内容的文件只存储一次

### Q: 如何修改bucket名称？
A: 在`.env`文件中设置 `SUPABASE_BUCKET_NAME=your-bucket-name`

### Q: 旧文件会自动迁移吗？
A: 不会自动迁移。新上传的文件使用Storage，旧文件保持在数据库中

### Q: Storage失败时会怎样？
A: 上传会失败并返回错误，不会降级到数据库存储

## 注意事项

1. **Bucket权限**：确保Supabase项目的Storage服务已启用
2. **存储配额**：注意Supabase Storage的存储配额限制
3. **网络延迟**：Storage访问可能比数据库稍慢（但更适合大文件）
4. **清理机制**：删除文件时需要同时清理Storage和数据库记录

## 后续优化建议

1. **CDN配置**：配置CDN加速文件下载
2. **自动迁移**：实现旧文件自动迁移到Storage的后台任务
3. **清理任务**：实现孤立文件清理（Storage中但数据库无记录）
4. **分层存储**：小文件使用数据库，大文件使用Storage
5. **访问统计**：记录文件访问次数，优化缓存策略

## 回滚方案

如果需要回滚到数据库存储：

1. 修改 `HybridFileStorage.SIZE_THRESHOLD = 1024 * 1024 * 1024`（设为很大的值）
2. 修改 `store_file_sync` 方法，强制使用数据库存储
3. 重启API服务器

## 总结

本次更新成功将文件存储从数据库迁移到Supabase Storage Bucket，提升了系统的性能、可扩展性和维护性。同时保持了向后兼容性，不影响已有数据的访问。

