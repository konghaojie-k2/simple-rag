"""
RAG Core SDK - 核心RAG功能库

一个可复用的RAG（检索增强生成）核心库，支持：
- 配置化的聊天模型和嵌入模型
- 标准化的文档处理和向量化
- 灵活的检索和生成流水线
- 完整的类型提示和错误处理

使用示例：
    from rag_core import SimpleRAG, RAGConfig
    
    config = RAGConfig(
        chat_model="qwen3-30b-a3b-2507",
        embedding_model="text-embedding-v2",
        base_url="http://localhost:8000/v1"
    )
    
    rag = SimpleRAG(config)
    
    # 添加文档
    rag.add_file_chunks_from_file("document.pdf")
    
    # 查询
    response = rag.query("你的问题")
    print(response.answer)
"""

from .config.models import RAGConfig, RAGResponse, Document
from .pipeline.supabase_rag import SupabaseRAG
from .config.supabase_config import SupabaseConfig

__version__ = "0.1.0"
__all__ = ["RAGConfig", "RAGResponse", "Document", "SupabaseRAG", "SupabaseConfig"]