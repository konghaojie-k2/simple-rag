"""RAG配置数据模型"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class RAGConfig:
    """RAG系统配置类"""
    
    # 模型配置
    chat_model: str = "qwen3-30b-a3b-2507"
    embedding_model: str = "text-embedding-v2"
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "your-api-key"
    
    # 检索配置
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    
    # 向量库配置
    vector_store_type: str = "faiss"  # faiss, chroma, etc.
    vector_store_path: str = "./vector_store"
    
    # 系统配置
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30
    
    # 代理配置
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    
    def __post_init__(self):
        """配置验证和路径处理"""
        # 使用pathlib处理路径
        self.vector_store_path = str(Path(self.vector_store_path).resolve())
        
        # 确保chunk_overlap < chunk_size
        if self.chunk_overlap >= self.chunk_size:
            self.chunk_overlap = self.chunk_size // 4


@dataclass
class Document:
    """文档数据模型"""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    
    def __post_init__(self):
        """文档内容预处理"""
        # 确保内容是字符串且非空
        if not isinstance(self.content, str):
            self.content = str(self.content)
        
        # 清理内容
        self.content = self.content.strip()
        
        if not self.content:
            raise ValueError("文档内容不能为空")


@dataclass
class RAGResponse:
    """RAG查询响应数据模型"""
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    query: str = ""
    confidence: float = 0.0
    processing_time: float = 0.0
    
    def __post_init__(self):
        """响应数据验证"""
        if not isinstance(self.answer, str):
            self.answer = str(self.answer)
        
        # 确保confidence在有效范围内
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class ProcessingProgress:
    """处理进度数据模型"""
    task_id: str
    status: str = "pending"  # pending, processing, completed, failed
    progress: float = 0.0  # 0.0 - 1.0
    message: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        """进度数据验证"""
        self.progress = max(0.0, min(1.0, self.progress))
        
        if self.status not in ["pending", "processing", "completed", "failed"]:
            self.status = "pending"