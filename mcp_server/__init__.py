"""
RAG MCP Server - 提供标准化的RAG工具接口

基于RAG Core SDK构建的MCP服务器，提供以下工具：
- rag_query: RAG查询
- rag_add_document: 添加文档到知识库
- rag_add_text: 添加文本到知识库
- rag_get_stats: 获取知识库统计信息
- rag_clear: 清空知识库
- rag_configure: 配置RAG参数
"""

from .server import create_rag_mcp_server

__version__ = "0.1.0"
__all__ = ["create_rag_mcp_server"]