# Supabase迁移指南

## 概述

本项目已成功迁移到基于Supabase的架构，移除了MCP Server，改为完全基于REST API的三层架构知识管理系统。

## 🏗️ 三层架构设计

本系统采用清晰的三层架构设计：

```
知识库 (Knowledge Base)
    ├── 文件 (File)
    │   ├── 分块 (Chunk)
    │   ├── 分块 (Chunk)
    │   └── ...
    ├── 文件 (File)
    └── ...
```

### 架构说明
- **知识库层**：管理整个知识库的创建、删除、统计
- **文件层**：管理单个文件的上传、存储、删除  
- **分块层**：管理文档分块的处理、向量化、查询

### 层级关系
- 删除知识库 → 删除所有文件和分块
- 删除文件 → 删除该文件的所有分块
- 删除分块 → 仅删除分块，保留原始文件

## 📊 接口与数据库血缘关系

### 数据库表关系图
```
┌─────────────────┐    ┌─────────────────┐    ┌──────────────────────┐
│ knowledge_bases │    │ document_files  │    │ langchain_pg_embedding│
│                 │    │                 │    │                      │
│ • id            │    │ • id            │    │ • uuid               │
│ • name          │◄──┤ • collection_name│    │ • document           │
│ • description   │    │ • filename      │    │ • cmetadata          │
│ • document_count│    │ • file_content  │    │ • embedding          │
│ • chunk_count   │    │ • file_size     │    │                      │
└─────────────────┘    └─────────────────┘    └──────────────────────┘
                              │                           ▲
                              │                           │
                              ▼                           │
                       ┌─────────────────┐                │
                       │document_metadata│                │
                       │                 │                │
                       │ • id            │                │
                       │ • file_id       │────────────────┘
                       │ • filename      │ (通过filename关联)
                       │ • collection_name│
                       │ • chunk_count   │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  task_status    │
                       │                 │
                       │ • task_id       │
                       │ • status        │
                       │ • progress      │
                       │ • result        │
                       └─────────────────┘
```

### API接口数据流图

#### 🏗️ 知识库层 API → 数据库操作
```
GET /api/v1/knowledge-bases
├── 📖 读取: knowledge_bases (全表)
└── 📊 返回: 知识库列表 + 统计信息

POST /api/v1/knowledge-bases
├── ✏️ 写入: knowledge_bases
│   ├── name, description
│   └── document_count: 0, chunk_count: 0
└── 📊 返回: 创建结果

DELETE /api/v1/knowledge-bases/{kb_name}
├── 🗑️ 删除: langchain_pg_embedding (按filename过滤)
├── 🗑️ 删除: document_metadata (按collection_name)
├── 🗑️ 删除: document_files (按collection_name)
├── 🗑️ 删除: knowledge_bases (按name)
└── 📊 返回: 删除结果

DELETE /api/v1/knowledge-bases/{kb_name}/clear
├── 🗑️ 清空: langchain_pg_embedding (按filename过滤)
├── 🗑️ 清空: document_metadata (按collection_name)
├── 🗑️ 清空: document_files (按collection_name)
├── ✏️ 更新: knowledge_bases (重置统计)
└── 📊 返回: 清空结果
```

#### 📁 文件层 API → 数据库操作
```
GET /api/v1/knowledge-bases/{kb_name}/files
├── 📖 读取: document_files (按collection_name)
├── 📊 计算: langchain_pg_embedding (统计chunk_count)
└── 📊 返回: 文件列表 + 分块统计

POST /api/v1/knowledge-bases/{kb_name}/files/upload
├── ✏️ 写入: document_files
│   ├── filename, file_content, file_size
│   └── collection_name, created_at
├── ✏️ 写入: task_status (任务跟踪)
└── 📊 返回: 上传任务ID

DELETE /api/v1/files/{file_id}
├── 📖 读取: document_files (获取filename)
├── 🗑️ 删除: langchain_pg_embedding (按filename)
├── 🗑️ 删除: document_metadata (按file_id)
├── 🗑️ 删除: document_files (按id)
├── ✏️ 更新: knowledge_bases (更新统计)
└── 📊 返回: 删除结果
```

#### 🧩 分块层 API → 数据库操作
```
POST /api/v1/knowledge-bases/{kb_name}/chunks/upload
├── 📖 处理: 文件内容 → 文本分块
├── 📊 向量化: 文本分块 → embeddings
├── ✏️ 写入: langchain_pg_embedding
│   ├── document (分块文本)
│   ├── cmetadata (元数据)
│   └── embedding (向量)
├── ✏️ 写入: document_metadata
│   ├── filename, collection_name
│   └── chunk_count, processed_content
├── ✏️ 更新: knowledge_bases (更新统计)
├── ✏️ 写入: task_status (任务跟踪)
└── 📊 返回: 处理任务ID

GET /api/v1/documents
├── 📖 读取: document_files (主表)
├── 📊 计算: langchain_pg_embedding (动态统计)
└── 📊 返回: 文档列表 + 分块关系

DELETE /api/v1/chunks/{document_id}
├── 📖 读取: document_metadata (获取filename)
├── 🗑️ 删除: langchain_pg_embedding (按filename)
├── 🗑️ 删除: document_metadata (按id)
├── ✏️ 更新: knowledge_bases (更新统计)
└── 📊 返回: 删除结果

POST /api/v1/query
├── 📊 向量化: 查询文本 → query_embedding
├── 📖 检索: langchain_pg_embedding (相似度搜索)
├── 📊 排序: 按相似度排序
└── 📊 返回: 答案 + 相关文档

GET /health (三层架构健康检查)
├── 📖 读取: knowledge_bases (全表统计)
├── 📊 统计: document_files (COUNT 文件总数)
├── 📊 统计: langchain_pg_embedding (COUNT 分块总数)
├── 📊 统计: task_status (COUNT 任务总数)
├── 📊 汇总: 按知识库分组统计
└── 📊 返回: 三层架构完整统计信息
    ├── system_stats (详细统计)
    │   ├── knowledge_bases: {total, details[]}
    │   ├── files: {total}
    │   ├── chunks: {total}
    │   └── tasks: {total}
    └── summary (简要统计)
        ├── knowledge_bases_count
        ├── files_count
        ├── chunks_count
        └── tasks_count
```

### 🔄 数据流向关系

#### 上传流程数据流
```
用户文件
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    上传处理流程                           │
├─────────────────────────────────────────────────────────┤
│ 1. POST /chunks/upload                                  │
│    ├── 文件解析 → 文本提取                                │
│    ├── 文本分割 → 多个分块                                │
│    └── 向量化处理 → embeddings                           │
├─────────────────────────────────────────────────────────┤
│ 2. 数据库写入顺序                                         │
│    ├── document_metadata ← 文档元信息                    │
│    ├── langchain_pg_embedding ← 分块+向量                │
│    └── knowledge_bases ← 统计更新                        │
├─────────────────────────────────────────────────────────┤
│ 3. POST /files/upload (可选)                           │
│    └── document_files ← 原始文件内容                      │
└─────────────────────────────────────────────────────────┘
```

#### 查询流程数据流
```
用户问题
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    查询处理流程                           │
├─────────────────────────────────────────────────────────┤
│ 1. POST /query                                         │
│    ├── 问题向量化 → query_embedding                      │
│    └── 相似度计算 → cosine_similarity                    │
├─────────────────────────────────────────────────────────┤
│ 2. 数据库查询顺序                                         │
│    ├── langchain_pg_embedding → 向量检索                 │
│    ├── 相似度排序 → Top-K 结果                           │
│    └── 上下文构建 → LLM 输入                             │
├─────────────────────────────────────────────────────────┤
│ 3. 响应生成                                              │
│    └── LLM 生成答案 + 引用来源                           │
└─────────────────────────────────────────────────────────┘
```

### 📈 统计数据更新链路

```
任何CRUD操作
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│              _update_knowledge_base_stats()              │
├─────────────────────────────────────────────────────────┤
│ 1. 统计 document_metadata                               │
│    └── COUNT(*) WHERE collection_name = kb_name        │
│                                                         │
│ 2. 统计 langchain_pg_embedding                          │
│    └── COUNT(*) (全部分块)                              │
│                                                         │
│ 3. 更新 knowledge_bases                                 │
│    ├── document_count = 统计结果1                        │
│    ├── chunk_count = 统计结果2                           │
│    └── updated_at = NOW()                               │
└─────────────────────────────────────────────────────────┘
```

### 🎯 API-数据库操作映射表

| API接口 | 主要操作 | 涉及数据表 | 操作类型 | 说明 |
|---------|----------|------------|----------|------|
| **知识库层** |
| `GET /knowledge-bases` | 查询知识库列表 | `knowledge_bases` | 📖 SELECT | 获取所有知识库信息 |
| `POST /knowledge-bases` | 创建知识库 | `knowledge_bases` | ✏️ INSERT | 新建知识库记录 |
| `DELETE /knowledge-bases/{name}` | 删除知识库 | `knowledge_bases`<br>`document_files`<br>`document_metadata`<br>`langchain_pg_embedding` | 🗑️ DELETE | 级联删除所有相关数据 |
| `DELETE /knowledge-bases/{name}/clear` | 清空知识库 | `document_files`<br>`document_metadata`<br>`langchain_pg_embedding`<br>`knowledge_bases` | 🗑️ DELETE<br>✏️ UPDATE | 删除内容，重置统计 |
| **文件层** |
| `GET /knowledge-bases/{kb}/files` | 查询文件列表 | `document_files`<br>`langchain_pg_embedding` | 📖 SELECT<br>📊 COUNT | 文件信息+分块统计 |
| `POST /knowledge-bases/{kb}/files/upload` | 上传原始文件 | `document_files`<br>`task_status` | ✏️ INSERT | 存储文件+任务记录 |
| `DELETE /files/{id}` | 删除文件 | `document_files`<br>`document_metadata`<br>`langchain_pg_embedding`<br>`knowledge_bases` | 🗑️ DELETE<br>✏️ UPDATE | 删除文件+分块+更新统计 |
| **分块层** |
| `POST /knowledge-bases/{kb}/chunks/upload` | 上传分块处理 | `document_metadata`<br>`langchain_pg_embedding`<br>`knowledge_bases`<br>`task_status` | ✏️ INSERT<br>✏️ UPDATE | 分块+向量+统计+任务 |
| `GET /documents` | 查询文档列表 | `document_files`<br>`langchain_pg_embedding` | 📖 SELECT<br>📊 COUNT | 文档信息+动态统计 |
| `DELETE /chunks/{id}` | 删除分块 | `document_metadata`<br>`langchain_pg_embedding`<br>`knowledge_bases` | 🗑️ DELETE<br>✏️ UPDATE | 删除分块+更新统计 |
| `POST /query` | RAG查询 | `langchain_pg_embedding` | 📖 SELECT | 向量相似度检索 |
| **系统管理** |
| `GET /health` | 三层架构健康检查 | `knowledge_bases`<br>`document_files`<br>`langchain_pg_embedding`<br>`task_status` | 📖 SELECT<br>📊 COUNT | 全系统统计信息 |
| `GET /tasks/{id}` | 查询任务状态 | `task_status` | 📖 SELECT | 任务进度查询 |
| `DELETE /tasks/cleanup` | 清理旧任务 | `task_status` | 🗑️ DELETE | 批量删除过期任务 |

### 🔗 关键关联关系

#### 1. 知识库 ↔ 文件关联
```sql
-- 通过 collection_name 关联
document_files.collection_name = knowledge_bases.name
```

#### 2. 文件 ↔ 分块关联  
```sql
-- 通过 filename 关联（间接关系）
document_metadata.filename = document_files.filename
langchain_pg_embedding.cmetadata->>'source' LIKE '%filename%'
```

#### 3. 统计数据同步
```sql
-- 知识库统计实时计算
knowledge_bases.document_count = COUNT(document_metadata WHERE collection_name = kb_name)
knowledge_bases.chunk_count = COUNT(langchain_pg_embedding)
```

#### 4. 任务追踪关联
```sql
-- 任务状态独立存储
task_status.task_id = UUID (业务层关联)
task_status.result->>'filename' = 处理的文件名
```

#### 5. 多知识库架构 ✅
**重要更新**：系统现已支持真正的多知识库隔离：

```sql
-- 统一架构：业务层和存储层使用相同的知识库名称
document_files.collection_name = 'kb_name'           -- 业务层知识库名
document_metadata.collection_name = 'kb_name'        -- 业务层关联
langchain_pg_collection.name = 'kb_name'             -- 存储层collection名
langchain_pg_embedding.collection_id → 'kb_name'     -- 向量存储关联
```

**多知识库隔离优势**：
- ✅ **完全隔离**: 每个知识库有独立的向量collection
- ✅ **安全删除**: 删除知识库不会影响其他知识库
- ✅ **独立查询**: 查询只在指定知识库范围内进行
- ✅ **扩展性好**: 支持创建任意数量的知识库

**查询分块的正确方式**：
```sql
-- 查询指定知识库的分块
SELECT COUNT(*) FROM langchain_pg_embedding e
JOIN langchain_pg_collection c ON e.collection_id = c.uuid
WHERE c.name = :kb_name  -- 使用业务层知识库名称
AND e.cmetadata->>'source' LIKE :filename_pattern
```

**知识库命名规范**：
- 默认知识库: `'default'`
- 自定义知识库: 用户指定名称 (如 `'project_docs'`, `'legal_files'`)

## 主要变更

### 1. 架构变更
- **移除**: MCP Server (`mcp_server/`)
- **新增**: 知识管理API服务器 (`api_server/`)
- **替换**: FAISS向量存储 → Supabase PGVector
- **新增**: Supabase数据库集成

### 2. 核心功能
- ✅ 基于Supabase PostgreSQL的向量存储
- ✅ 完整的RESTful API
- ✅ 文档上传和管理
- ✅ 分块搜索和管理
- ✅ 知识库问答
- ✅ 任务状态跟踪
- ✅ 配置管理

### 3. 三层架构API功能对比

#### 知识库层 API
- ✅ 知识库列表 (`GET /api/v1/knowledge-bases`)
- ✅ 知识库详情 (`GET /api/v1/knowledge-bases/{kb_name}`)
- ✅ 创建知识库 (`POST /api/v1/knowledge-bases`)
- ✅ 删除知识库 (`DELETE /api/v1/knowledge-bases/{kb_name}`)
- ✅ 清空知识库 (`DELETE /api/v1/knowledge-bases/{kb_name}/clear`)

#### 文件层 API
- ✅ 文件列表 (`GET /api/v1/knowledge-bases/{kb_name}/files`)
- ✅ 文件详情 (`GET /api/v1/knowledge-bases/{kb_name}/files/{file_id}`)
- ✅ 上传原始文件 (`POST /api/v1/knowledge-bases/{kb_name}/files/upload`)
- ✅ 删除文件 (`DELETE /api/v1/files/{file_id}`)

#### 分块层 API
- ✅ 上传分块处理 (`POST /api/v1/knowledge-bases/{kb_name}/chunks/upload`)
- ✅ 文档列表 (`GET /api/v1/documents`)
- ✅ 分块详情 (`GET /api/v1/chunks/{document_id}/details`)
- ✅ 删除分块 (`DELETE /api/v1/chunks/{document_id}`)
- ✅ RAG查询 (`POST /api/v1/query`)

#### 系统管理 API
- ✅ 三层架构健康检查 (`GET /health`) - 完整的系统统计信息
- ✅ 任务状态 (`GET /api/v1/tasks/{task_id}`)
- ✅ 任务列表 (`GET /api/v1/tasks`)
- ✅ 清理任务 (`DELETE /api/v1/tasks/cleanup`)
- ✅ 配置管理 (`GET /api/v1/config`)

## 设置步骤

### 1. 环境准备

```bash
# 确保Python版本3.11+
python --version

# 安装uv包管理器（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Supabase项目设置

1. 在 [Supabase](https://supabase.com) 创建新项目
2. 获取以下信息：
   - 项目URL
   - anon public key
   - service role key
   - 数据库连接信息

### 3. 配置环境变量

```bash
# 复制配置文件
cp env.example .env

# 编辑.env文件，设置Supabase配置
nano .env
```

必需的配置项：
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_HOST=db.your-project.supabase.co
SUPABASE_DB_PASSWORD=your-database-password
```

### 4. 自动设置

```bash
# 运行自动设置脚本
python scripts/setup_supabase.py
```

### 5. 手动数据库初始化（如果自动设置失败）

在Supabase SQL编辑器中执行：
```sql
-- 执行scripts/init_supabase.sql中的内容
```

### 6. 安装依赖

```bash
# 同步项目依赖
uv sync
```

## 启动服务

### 方式1: 直接启动
```bash
cd api_server
uv run python main.py
```

### 方式2: 使用uvicorn
```bash
cd api_server
uv run uvicorn main:app --host 127.0.0.1 --port 8002 --reload
```

## API使用示例

### 快速开始
```python
# 运行快速开始示例
python examples/quick_start.py
```

这个脚本会自动检查服务状态并演示所有主要API功能。

### Python客户端示例

#### 1. 基本使用（同步）
```python
from examples.api_client_example import KnowledgeAPIClient

# 创建客户端
client = KnowledgeAPIClient("http://localhost:8002")

# 健康检查
health = client.health_check()
print(f"服务状态: {health}")
# 现在返回 chunk_count 而不是 document_count

# 方式1: 上传文件进行分块处理用于RAG查询（不保存原始文件）
upload_result = client.upload_for_chunks("document.pdf")
task_id = upload_result["task_id"]

# 方式2: 上传文件用于存储下载（只保存原始文件，不分块）
file_result = client.upload_file("document.pdf")
file_task_id = file_result["task_id"]

# 等待上传完成
final_status = client.wait_for_task_completion(task_id)

# 查询知识库
result = client.query_knowledge_base("什么是机器学习？")
print(f"回答: {result['answer']}")

# 搜索分块
chunks = client.search_chunks("机器学习", limit=5)
print(f"找到 {chunks['total']} 个相关分块")

# 获取分块列表
chunks = client.list_chunks()
print(f"分块文档数量: {len(chunks)}")

# 获取原始文件列表
files = client.list_files()
print(f"文件数量: {len(files)}")

# 获取文件详细信息
file_info = client.get_file_info("file_id")
print(f"文件信息: {file_info}")

# 获取文档的分块详情
chunk_details = client.get_chunk_details("document_id")
print(f"分块详情数: {chunk_details['total']}")

# 获取文件的所有分块
file_chunks = client.get_file_chunks("file_id")
print(f"文件分块数: {file_chunks['total']}")

# 清空知识库（如果需要）
clear_result = client.clear_all_chunks()
print(f"清空结果: {clear_result}")

# 删除文档的分块
# delete_result = client.delete_chunks("document_id")
# print(f"删除结果: {delete_result}")
```

#### 2. 异步使用
```python
import asyncio
from examples.async_api_client import AsyncKnowledgeAPIClient

async def main():
    async with AsyncKnowledgeAPIClient("http://localhost:8002") as client:
        # 批量查询
        questions = [
            "什么是机器学习？",
            "深度学习的原理是什么？",
            "人工智能的应用领域有哪些？"
        ]
        
        results = await client.batch_query(questions)
        for result in results:
            print(f"问题: {result['question']}")
            print(f"回答: {result['answer'][:100]}...")

# 运行异步代码
asyncio.run(main())
```

#### 3. 安装依赖
```bash
# 同步客户端
uv add requests

# 异步客户端
uv add aiohttp
```

### cURL示例（用于测试）

#### 1. 健康检查
```bash
curl http://localhost:8002/health
```

#### 2a. 上传文件进行分块处理（用于RAG查询）
```bash
curl -X POST "http://localhost:8002/api/v1/chunks/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@document.pdf" \
     -F "knowledge_base=default"
```

#### 2b. 上传文件（用于存储下载）
```bash
curl -X POST "http://localhost:8002/api/v1/files/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@document.pdf" \
     -F "knowledge_base=default"
```

#### 3. 查询知识库
```bash
curl -X POST "http://localhost:8002/api/v1/query" \
     -H "Content-Type: application/json" \
     -d '{"question": "什么是机器学习？", "knowledge_base": "default"}'
```

#### 4. 搜索分块
```bash
curl -X POST "http://localhost:8002/api/v1/chunks/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "机器学习", "limit": 5}'
```

#### 5. 获取分块列表
```bash
curl "http://localhost:8002/api/v1/chunks?knowledge_base=default"
```

#### 5.5. 获取原始文件列表
```bash
curl "http://localhost:8002/api/v1/files?knowledge_base=default"
```

#### 5.6. 获取单个文件信息
```bash
curl "http://localhost:8002/api/v1/files/{file_id}"
```

#### 5.7. 获取文档的分块详情
```bash
curl "http://localhost:8002/api/v1/chunks/{document_id}/details"
```

#### 5.8. 获取文件的所有分块
```bash
curl "http://localhost:8002/api/v1/files/{file_id}/chunks"
```

#### 6. 清空知识库
```bash
curl -X DELETE "http://localhost:8002/api/v1/chunks?knowledge_base=default"
```

#### 7a. 删除文档的所有分块（保留原始文件）
```bash
curl -X DELETE "http://localhost:8002/api/v1/chunks/{document_id}"
```

#### 7b. 删除原始文件及其关联的所有分块（推荐用于前端）
```bash
curl -X DELETE "http://localhost:8002/api/v1/files/{file_id}"
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8002/docs
- ReDoc: http://localhost:8002/redoc

## 数据库表结构与关系

### 数据库表结构概览

| 表名 | 类型 | 主要功能 | 关联关系 | 备注 |
|------|------|----------|----------|------|
| **knowledge_bases** | 业务表 | 知识库管理 | 通过collection_name关联其他表 | 多租户支持 |
| **document_files** | 业务表 | 原始文件存储 | 主表，被document_metadata引用 | 支持文件下载 |
| **document_metadata** | 业务表 | 文档元数据管理 | file_id → document_files.id | 连接文件和分块 |
| **documents** | 业务表 | 标准向量存储 | 独立表，官方推荐结构 | 预留，未使用 |
| **langchain_pg_collection** | 系统表 | LangChain集合管理 | 被langchain_pg_embedding引用 | LangChain自动创建 |
| **langchain_pg_embedding** | 系统表 | 实际向量存储 | collection_id → langchain_pg_collection | 当前主要使用 |
| **task_status** | 系统表 | 异步任务跟踪 | 独立表 | 任务状态管理 |
| **document_details** | 视图 | 文档完整信息 | 连接files和metadata表 | 前端展示用 |
| **knowledge_base_stats** | 视图 | 知识库统计 | 聚合多表数据 | 管理界面用 |

### 核心表关系图

```
knowledge_bases (知识库配置)
    ↓ collection_name
document_files (原始文件) → document_metadata (文档元数据)
                                ↓ 文件名关联
langchain_pg_collection → langchain_pg_embedding (向量存储)

documents (备用向量表)    task_status (任务状态)
    ↑ 独立                    ↑ 独立
```

### 主要字段说明

| 表名 | 关键字段 | 数据类型 | 说明 |
|------|----------|----------|------|
| **document_files** | id, filename, file_content, file_hash | UUID, TEXT, TEXT(Base64), VARCHAR | 原始文件存储，支持去重和下载 |
| **document_metadata** | id, file_id, chunk_count, processed_content | UUID, UUID(FK), INTEGER, TEXT | 文档处理信息，连接文件和分块 |
| **documents** | id, content, embedding, metadata | UUID, TEXT, VECTOR(1536), JSONB | 标准向量存储结构（预留） |
| **langchain_pg_collection** | uuid, name, cmetadata | UUID, VARCHAR, JSONB | LangChain集合管理 |
| **langchain_pg_embedding** | id, collection_id, document, embedding | BIGINT, UUID(FK), TEXT, VECTOR | 实际向量数据存储 |
| **knowledge_bases** | id, name, document_count, chunk_count | UUID, VARCHAR, INTEGER, INTEGER | 知识库配置和统计 |
| **task_status** | task_id, status, progress, result | VARCHAR, VARCHAR, REAL, JSONB | 异步任务状态跟踪 |

### 数据流向关系

#### 上传流程:
1. **文件上传** → `document_files` (存储原始文件)
2. **文档处理** → `document_metadata` (存储元数据，关联file_id)
3. **分块处理** → `langchain_pg_embedding` (存储向量分块)
4. **任务跟踪** → `task_status` (记录处理状态)

#### 删除流程:
- **删除文件** (`DELETE /api/v1/files/{file_id}`):
  1. 删除 `document_files` 记录
  2. 级联删除 `document_metadata` 记录 (ON DELETE CASCADE)
  3. 清理相关的 `langchain_pg_embedding` 记录

- **删除文档** (`DELETE /api/v1/documents/{document_id}`):
  1. 删除 `document_metadata` 记录
  2. 清理相关的 `langchain_pg_embedding` 记录
  3. **保留** `document_files` 记录

### 视图和函数

#### 视图
1. **knowledge_base_stats** - 知识库统计信息
   - 聚合统计各知识库的文档数、分块数、总大小
2. **document_details** - 文档详细信息
   - 连接文件表和元数据表，提供完整的文档信息

#### 核心函数
1. **match_documents()** - 向量相似度搜索
2. **get_knowledge_base_stats()** - 获取知识库统计
3. **check_file_exists()** - 文件哈希去重检查
4. **get_file_content()** - 获取原始文件内容

### 索引优化
- **文件表**: filename, file_hash, collection_name, created_at
- **元数据表**: file_id, collection_name, filename, created_at
- **向量表**: metadata字段 (collection_name, source, doc_id)
- **向量索引**: HNSW索引用于高效向量搜索

## 与WeKnora API的对比

| WeKnora功能 | 本项目API | 状态 |
|------------|----------|------|
| 知识库管理 | `/api/v1/knowledge-bases` | ✅ |
| 分块上传 | `/api/v1/chunks/upload` | ✅ |
| 文件上传 | `/api/v1/files/upload` | ✅ |
| 分块列表 | `/api/v1/chunks` | ✅ |
| 文件列表 | `/api/v1/files` | ✅ |
| 分块删除 | `/api/v1/chunks/{id}` | ✅ |
| 文件删除 | `/api/v1/files/{id}` | ✅ |
| 清空知识库 | `/api/v1/chunks` (DELETE) | ✅ |
| 分块搜索 | `/api/v1/chunks/search` | ✅ |
| 问答查询 | `/api/v1/query` | ✅ |
| 任务状态 | `/api/v1/tasks/{id}` | ✅ |
| 配置管理 | `/api/v1/config` | ✅ |

## Supabase功能支持分析

### ✅ 完全支持的功能
- PostgreSQL数据库存储
- pgvector扩展向量搜索
- 用户认证（通过Supabase Auth）
- 实时订阅（可扩展）
- 文件存储（可扩展）
- REST API自动生成

### ⚠️ 需要额外实现的功能
- 复杂的RBAC权限控制（需要自定义实现）
- 高级搜索过滤器（部分支持）
- 批量操作优化

### ❌ Supabase不直接支持的功能
- 原生OIDC提供者（需要第三方集成）
- 复杂的图形化查询界面（需要前端实现）

## 迁移后的优势

1. **云原生**: 基于Supabase云数据库，无需本地向量存储
2. **可扩展**: PostgreSQL支持大规模数据存储
3. **标准化**: 完全基于REST API，易于集成
4. **实时性**: 支持实时数据更新
5. **安全性**: Supabase提供企业级安全保障

## 故障排除

### 常见问题

1. **连接失败**
   - 检查Supabase配置是否正确
   - 确认网络连接正常
   - 验证数据库密码

2. **向量搜索失败**
   - 确认pgvector扩展已启用
   - 检查embedding模型配置

3. **文档上传失败**
   - 检查文件格式支持
   - 确认文件大小限制
   - 验证存储空间

4. **批处理大小限制错误**
   - 错误信息：`batch size is invalid, it should not be larger than 25`
   - 原因：嵌入服务（如阿里云DashScope）限制单次批处理最多25个文档
   - 解决方案：系统已自动分批处理，无需手动干预

5. **PostgreSQL连接冲突**
   - 错误信息：`prepared statement already exists`
   - 原因：多次连接同一数据库导致的连接池冲突
   - 解决方案：重启API服务器或清空知识库重新开始

6. **JSON序列化错误**
   - 错误信息：`Object of type bytes is not JSON serializable`
   - 原因：文件内容未正确编码
   - 解决方案：系统已自动使用base64编码处理文件内容

### 日志查看
```bash
tail -f logs/api_server.log
```

### 清空文档的使用方法

如果遇到PostgreSQL连接冲突或需要重新开始，可以使用以下方法清空知识库：

#### 方法1：使用Python客户端
```python
from examples.api_client_example import KnowledgeAPIClient

client = KnowledgeAPIClient("http://localhost:8001")
clear_result = client.clear_all_documents()
print(f"清空结果: {clear_result}")
```

#### 方法2：使用cURL
```bash
curl -X DELETE "http://localhost:8001/api/v1/documents"
```

#### 方法3：在Jupyter Notebook中
```python
# 在test_upload.ipynb中运行
clear_result = client.clear_all_documents()
print(f"清空结果: {clear_result}")
```

**注意**：清空操作会删除：
- 所有向量嵌入数据
- 文档元数据
- 原始文件内容
- 相关的任务状态记录

## 🐛 常见问题与解决方案

### DuplicatePreparedStatement 错误

#### 问题描述
在处理大文件（超过5个batch，即25个以上分块）时，系统会出现以下错误：
```
(psycopg.errors.DuplicatePreparedStatement) prepared statement "_pg3_0" already exists
[SQL: SELECT langchain_pg_collection.uuid, langchain_pg_collection.name, langchain_pg_collection.cmetadata 
FROM langchain_pg_collection 
WHERE langchain_pg_collection.name = %(name_1)s::VARCHAR 
LIMIT %(param_1)s::INTEGER]
```

#### 错误原因分析
1. **LangChain 内部机制**：LangChain 的 PGVector 组件使用 SQLAlchemy 的 prepared statements 来优化数据库查询
2. **批次处理冲突**：当处理超过5个batch时，LangChain 会重复查询 `langchain_pg_collection` 表
3. **Prepared Statement 重复**：PostgreSQL 不允许在同一会话中创建同名的 prepared statement
4. **触发时机**：错误总是在第6个batch开始时出现

#### 解决方案

**核心原理**：避免多个数据库操作共享同一个 SQLAlchemy 引擎，让每个方法使用独立的临时引擎。

**修复前的问题代码**：
```python
# ❌ 错误：多个方法共享同一个引擎
def some_method(self):
    with self._db_engine.connect() as conn:  # 共享引擎导致冲突
        # ... 数据库操作
```

**修复后的正确代码**：
```python
# ✅ 正确：每个方法使用独立引擎
def some_method(self):
    from sqlalchemy import create_engine, text
    engine = create_engine(self.supabase_config.postgres_url)  # 独立引擎
    
    with engine.connect() as conn:
        # ... 数据库操作
    
    engine.dispose()  # 释放连接池
```

#### 修复涉及的文件
- `rag_core/pipeline/supabase_rag.py`：所有数据库查询方法
- 修复的方法包括：
  - `get_chunk_count()`
  - `get_chunks_by_metadata_id()`
  - `get_file_chunks()`
  - `delete_chunks_only()`
  - `delete_file_and_chunks()`
  - `clear_chunks()`
  - `get_files_by_knowledge_base()`
  - `get_single_file_info_by_kb()`
  - `clear_knowledge_base()`

#### 验证修复效果
```python
# 测试大文件上传（确保产生>5个batch）
from examples.api_client_example import KnowledgeAPIClient

client = KnowledgeAPIClient("http://localhost:8001")

# 清空知识库
client.clear_knowledge_base('default')

# 上传大文件（>25个分块）
upload_result = client.upload_for_chunks_in_kb('default', 'large_file.txt')
# 应该成功完成，不再出现 DuplicatePreparedStatement 错误
```

#### 技术要点
1. **引擎隔离**：LangChain 使用自己的引擎，其他方法使用独立引擎
2. **连接管理**：每个方法创建临时引擎，使用后立即释放
3. **批次大小**：保持5个分块/batch的设置，减少单次处理复杂度
4. **错误处理**：在异常处理中清理数据库连接状态

#### 预防措施
- 避免在多个方法间共享 SQLAlchemy 引擎
- 确保每个数据库操作后正确调用 `engine.dispose()`
- 监控日志中的 prepared statement 相关警告
- 定期测试大文件上传功能

## 下一步计划

1. 前端界面适配新API
2. 添加用户认证和权限管理
3. 实现批量文档处理
4. 添加更多文档格式支持
5. 性能优化和缓存策略
