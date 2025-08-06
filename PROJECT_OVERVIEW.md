# Simple RAG 项目概览

## 项目简介

这是一个基于LangChain的简单本地化知识库问答系统，采用分层设计架构，旨在提供可复用的RAG（检索增强生成）解决方案。

## 核心特性

- ✅ **配置化模型支持**：支持配置不同的聊天模型和嵌入模型
- ✅ **标准OpenAI接口**：兼容OpenAI API格式
- ✅ **多文档格式**：支持TXT、PDF、DOCX、Markdown等格式
- ✅ **分层架构设计**：RAG Core SDK + MCP Server + 应用层
- ✅ **前后端分离**：Next.js前端 + FastAPI后端
- ✅ **可复用组件**：可作为SDK或MCP工具在不同项目中复用

## 项目架构

```
simple_rag/
├── rag_core/                  # 核心RAG SDK（可复用）
│   ├── config/                # 配置管理
│   │   └── models.py          # 数据模型定义
│   ├── pipeline/              # RAG流水线
│   │   └── simple_rag.py      # 主要RAG实现
│   ├── utils/                 # 工具函数
│   │   ├── file_processor.py  # 文件处理
│   │   ├── text_splitter.py   # 文本分割
│   │   └── logger.py          # 日志配置
│   └── __init__.py
├── mcp_server/                # MCP服务器实现
│   ├── server.py              # MCP工具实现
│   ├── main.py                # 服务器启动脚本
│   └── __init__.py
├── backend_v2/                # 基于RAG Core的后端API服务
│   └── main.py                # FastAPI应用
├── frontend/                  # Next.js前端
├── examples/                  # 使用示例
│   ├── basic_usage.py         # 基本使用示例
│   ├── file_processing.py     # 文件处理示例
│   └── mcp_usage.py           # MCP使用示例
└── docs/                      # 项目文档
```

## 三层使用方式

### 1. RAG Core SDK（推荐用于Python项目）

直接使用核心SDK，性能最优，调试友好：

```python
from rag_core import SimpleRAG, RAGConfig

config = RAGConfig(
    chat_model="qwen3-30b-a3b-2507",
    embedding_model="text-embedding-v2",
    base_url="http://localhost:8000/v1"
)

rag = SimpleRAG(config)
rag.add_documents_from_file("document.pdf")
response = rag.query("你的问题")
```

### 2. MCP Server（推荐用于AI Agent工具）

提供标准化的MCP工具接口，支持跨语言调用：

```bash
# 启动MCP服务器
python -m mcp_server.main

# 在支持MCP的客户端中使用
rag_query("什么是机器学习？")
rag_add_document("path/to/document.pdf")
```

### 3. HTTP API（Web应用集成）

基于FastAPI的RESTful接口：

```bash
# 启动API服务器
cd backend_v2
python main.py

# 使用HTTP接口
curl -X POST "http://localhost:8001/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "你的问题"}'
```

## 默认配置

- **聊天模型**：qwen3-30b-a3b-2507
- **嵌入模型**：text-embedding-v2
- **API端点**：http://localhost:8000/v1
- **文档分块**：1000字符，重叠200字符
- **检索数量**：top-k=5

## 环境要求

- Python 3.12+
- Node.js（前端开发）
- uv包管理器（推荐）

## 快速开始

### 1. 环境设置

```bash
# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑.env文件设置你的API配置
```

### 2. 使用RAG Core SDK

```bash
cd examples
python basic_usage.py
```

### 3. 启动MCP服务器

```bash
python -m mcp_server.main
```

### 4. 启动Web应用

```bash
# 后端API服务
cd backend_v2  
python main.py

# 前端
cd frontend
npm install
npm run dev
```

## 核心组件说明

### RAG Core SDK

- **SimpleRAG**：主要RAG实现类
- **RAGConfig**：配置管理
- **FileProcessor**：文件处理器
- **SmartTextSplitter**：智能文本分割器

### MCP Server

- **rag_query**：查询工具
- **rag_add_document**：添加文档工具
- **rag_add_text**：添加文本工具
- **rag_get_stats**：统计信息工具
- **rag_clear**：清空知识库工具
- **rag_configure**：配置工具

### API服务

- **POST /upload**：上传文档
- **POST /ask**：问答查询
- **GET /documents**：获取文档列表
- **DELETE /documents**：清空文档
- **GET /config**：获取配置
- **POST /config**：更新配置

## 开发状态

- ✅ RAG Core SDK实现完成
- ✅ MCP Server实现完成
- ✅ 新版API服务实现完成
- 🔄 前端适配新API（进行中）
- ⏳ 完整测试和文档（待完成）

## 下一步计划

1. 完成前端适配新API
2. 添加完整的单元测试
3. 创建Docker部署配置
4. 完善文档和使用指南
5. 添加更多文档格式支持
6. 实现多知识库管理

## 贡献指南

1. 使用uv管理依赖
2. 遵循Python代码规范
3. 使用loguru进行日志记录
4. 使用pathlib处理文件路径
5. 保持向后兼容性

## 许可证

MIT License