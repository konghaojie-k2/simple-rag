"""
基于RAG Core SDK的新后端API服务
"""

import os
import asyncio
import uuid
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# 导入RAG Core SDK
from rag_core import SimpleRAG, RAGConfig, Document
from rag_core.utils.logger import setup_logger

# 加载环境变量 - 从项目根目录读取.env文件
from pathlib import Path
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

# 设置日志
logger = setup_logger(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_file="logs/backend.log"
)

# 创建FastAPI应用
app = FastAPI(
    title="Simple RAG API v2",
    description="基于RAG Core SDK的知识库问答API",
    version="2.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
rag_instance: Optional[SimpleRAG] = None
progress_storage: Dict[str, Dict[str, Any]] = {}


# Pydantic模型
class QuestionRequest(BaseModel):
    question: str
    knowledge_base: Optional[str] = "default"


class ConfigRequest(BaseModel):
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    top_k: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ProgressResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    result: Optional[Any] = None
    error: Optional[str] = None


class DocumentInfo(BaseModel):
    filename: str
    size: int
    upload_time: str
    chunk_count: int


def get_rag_config() -> RAGConfig:
    """从环境变量创建RAG配置"""
    return RAGConfig(
        chat_model=os.getenv("DEFAULT_CHAT_MODEL", "qwen3-30b-a3b-2507"),
        embedding_model=os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-v2"),
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        vector_store_path=os.getenv("VECTOR_STORE_PATH", "./vector_store"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        top_k=int(os.getenv("TOP_K", "5")),
        temperature=float(os.getenv("TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("MAX_TOKENS", "2048")),
        http_proxy=os.getenv("HTTP_PROXY"),
        https_proxy=os.getenv("HTTPS_PROXY"),
        no_proxy=os.getenv("NO_PROXY")
    )


def get_rag_instance() -> SimpleRAG:
    """获取或创建RAG实例"""
    global rag_instance
    if rag_instance is None:
        config = get_rag_config()
        rag_instance = SimpleRAG(config)
        logger.info("RAG实例已初始化")
    return rag_instance


def update_progress(task_id: str, status: str, progress: float, message: str, 
                   result: Any = None, error: str = None):
    """更新任务进度"""
    progress_storage[task_id] = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "result": result,
        "error": error,
        "updated_at": time.time()
    }


async def process_file_upload(task_id: str, file_content: bytes, filename: str):
    """异步处理文件上传"""
    try:
        update_progress(task_id, "processing", 0.1, "开始处理文档...")
        
        rag = get_rag_instance()
        
        update_progress(task_id, "processing", 0.3, "解析文档内容...")
        
        # 使用RAG Core SDK处理文件
        success = rag.add_documents_from_uploaded_file(file_content, filename)
        
        if success:
            update_progress(task_id, "completed", 1.0, "文档处理完成", 
                          result={"filename": filename, "document_count": rag.get_document_count()})
        else:
            update_progress(task_id, "failed", 1.0, "文档处理失败", error="处理过程中发生错误")
    
    except Exception as e:
        logger.error(f"文件处理失败: {str(e)}")
        update_progress(task_id, "failed", 1.0, "文档处理失败", error=str(e))


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("启动Simple RAG API v2")
    
    # 创建必要的目录
    Path("logs").mkdir(exist_ok=True)
    Path("vector_store").mkdir(exist_ok=True)
    
    # 初始化RAG实例
    get_rag_instance()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("关闭Simple RAG API v2")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Simple RAG API v2",
        "version": "2.0.0",
        "description": "基于RAG Core SDK的知识库问答API"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    rag = get_rag_instance()
    return {
        "status": "healthy",
        "document_count": rag.get_document_count(),
        "config": {
            "chat_model": rag.config.chat_model,
            "embedding_model": rag.config.embedding_model
        }
    }


@app.post("/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """上传文档"""
    try:
        # 检查文件类型
        allowed_extensions = {'.txt', '.pdf', '.docx', '.doc', '.md'}
        file_extension = Path(file.filename).suffix.lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file_extension}。支持的格式: {', '.join(allowed_extensions)}"
            )
        
        # 读取文件内容
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="文件内容为空")
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化进度
        update_progress(task_id, "pending", 0.0, "任务已创建")
        
        # 添加后台任务
        background_tasks.add_task(process_file_upload, task_id, file_content, file.filename)
        
        logger.info(f"文件上传任务已创建: {file.filename}, task_id: {task_id}")
        
        return {"task_id": task_id, "message": "文件上传任务已创建"}
    
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """获取任务进度"""
    if task_id not in progress_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return ProgressResponse(**progress_storage[task_id])


@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """问答接口"""
    try:
        rag = get_rag_instance()
        
        if rag.get_document_count() == 0:
            return {
                "answer": "知识库为空，请先上传文档。",
                "sources": [],
                "processing_time": 0
            }
        
        # 查询
        response = rag.query(request.question)
        
        logger.info(f"问答完成: {request.question[:50]}...")
        
        return {
            "answer": response.answer,
            "sources": response.sources,
            "processing_time": response.processing_time
        }
    
    except Exception as e:
        logger.error(f"问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def get_documents():
    """获取文档列表"""
    try:
        rag = get_rag_instance()
        
        return {
            "document_count": rag.get_document_count(),
            "message": f"知识库包含 {rag.get_document_count()} 个文档块"
        }
    
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents")
async def clear_documents():
    """清空文档"""
    try:
        rag = get_rag_instance()
        success = rag.clear_documents()
        
        if success:
            logger.info("知识库已清空")
            return {"message": "知识库已清空"}
        else:
            raise HTTPException(status_code=500, detail="清空失败")
    
    except Exception as e:
        logger.error(f"清空文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config")
async def get_config():
    """获取当前配置"""
    try:
        rag = get_rag_instance()
        config = rag.get_config()
        
        return {
            "chat_model": config.chat_model,
            "embedding_model": config.embedding_model,
            "base_url": config.base_url,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "top_k": config.top_k,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens
        }
    
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config")
async def update_config(request: ConfigRequest):
    """更新配置"""
    try:
        global rag_instance
        
        # 获取当前配置
        current_config = get_rag_config()
        
        # 更新配置
        config_dict = current_config.__dict__.copy()
        
        for field, value in request.dict(exclude_unset=True).items():
            if value is not None:
                config_dict[field] = value
        
        new_config = RAGConfig(**config_dict)
        
        # 创建新的RAG实例
        rag_instance = SimpleRAG(new_config)
        
        logger.info("配置已更新")
        
        return {"message": "配置已更新", "config": config_dict}
    
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # 配置服务器参数
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8001"))
    
    logger.info(f"启动服务器: http://{host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )