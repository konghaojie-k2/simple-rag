"""
知识管理API服务器 - 基于Supabase的RAG系统
参考WeKnora项目的分块管理API设计
"""

import os
import asyncio
import uuid
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io
import uvicorn
from dotenv import load_dotenv

# 导入RAG Core SDK
from rag_core import RAGConfig, Document
from rag_core.config.supabase_config import SupabaseConfig
from rag_core.pipeline.supabase_rag import SupabaseRAG
from rag_core.utils.logger import setup_logger

# 加载环境变量
load_dotenv()

# 设置日志
logger = setup_logger(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_file="logs/api_server.log"
)

# 创建FastAPI应用
app = FastAPI(
    title="知识管理API",
    description="基于Supabase的知识管理和RAG系统API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
rag_instance: Optional[SupabaseRAG] = None
progress_storage: Dict[str, Dict[str, Any]] = {}
# 知识库实例缓存
rag_instances_cache: Dict[str, SupabaseRAG] = {}


# Pydantic模型定义

class DocumentChunk(BaseModel):
    """文档块模型"""
    id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None


class ChunkInfo(BaseModel):
    """分块信息模型"""
    id: str
    filename: str
    content_type: str
    file_size: int
    chunk_count: int
    collection_name: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FileInfo(BaseModel):
    """文件信息模型"""
    id: str
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    file_hash: Optional[str] = None
    collection_name: str = "default"
    chunk_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeBase(BaseModel):
    """知识库模型"""
    name: str
    description: Optional[str] = None
    file_count: int = 0
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class QueryRequest(BaseModel):
    """查询请求模型"""
    question: str
    knowledge_base: Optional[str] = "default"
    top_k: Optional[int] = 5
    threshold: Optional[float] = 0.7


class QueryResponse(BaseModel):
    """查询响应模型"""
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    processing_time: float
    knowledge_base: str


class ChunkSearchRequest(BaseModel):
    """分块搜索请求"""
    query: str
    knowledge_base: Optional[str] = "default"
    limit: Optional[int] = 10
    threshold: Optional[float] = 0.7


class ChunkSearchResponse(BaseModel):
    """分块搜索响应"""
    chunks: List[DocumentChunk]
    total: int
    query: str
    processing_time: float


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    task_id: str
    message: str
    filename: str


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: float
    message: str
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConfigRequest(BaseModel):
    """配置更新请求"""
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    top_k: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# 依赖函数

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


def get_supabase_config() -> SupabaseConfig:
    """从环境变量创建Supabase配置"""
    return SupabaseConfig.from_env(os.environ)


def get_rag_instance(knowledge_base: str = "default") -> SupabaseRAG:
    """获取RAG实例（支持多知识库，带缓存）"""
    global rag_instances_cache
    
    # 检查缓存中是否已有该知识库的实例
    if knowledge_base in rag_instances_cache:
        logger.info(f"使用缓存的RAG实例 - 知识库: {knowledge_base}")
        return rag_instances_cache[knowledge_base]
    
    # 为每个知识库创建独立的配置
    config = get_rag_config()
    supabase_config = get_supabase_config()
    supabase_config.collection_name = knowledge_base  # 设置知识库名称
    
    # 创建新实例并缓存
    try:
        instance = SupabaseRAG(config, supabase_config)
        rag_instances_cache[knowledge_base] = instance
        logger.info(f"创建并缓存新的RAG实例 - 知识库: {knowledge_base}")
        return instance
    except Exception as e:
        logger.error(f"创建RAG实例失败 - 知识库: {knowledge_base}, 错误: {str(e)}")
        raise


def update_task_progress(task_id: str, status: str, progress: float, message: str,
                        result: Any = None, error: str = None):
    """更新任务进度（存储到数据库）"""
    try:
        rag = get_rag_instance()
        now = datetime.now()
        
        # 检查任务是否已存在
        existing_task = rag.supabase.table("task_status")\
            .select("created_at")\
            .eq("task_id", task_id)\
            .execute()
        
        created_at = existing_task.data[0]["created_at"] if existing_task.data else now.isoformat()
        
        # 更新或插入任务状态到数据库
        task_data = {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "result": result,
            "error": error,
            "created_at": created_at,
            "updated_at": now.isoformat()
        }
        
        # 使用 upsert 时指定冲突字段
        rag.supabase.table("task_status").upsert(task_data, on_conflict="task_id").execute()
        
        # 同时保留内存存储作为缓存（可选，用于快速查询）
        progress_storage[task_id] = task_data
        
    except Exception as e:
        logger.error(f"更新任务进度失败: {str(e)}")
        # 降级到内存存储
        now = datetime.now()
        progress_storage[task_id] = {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "result": result,
            "error": error,
            "created_at": progress_storage.get(task_id, {}).get("created_at", now),
            "updated_at": now
        }


# 异步任务处理函数

async def process_file_for_chunks(task_id: str, file_content: bytes, filename: str, knowledge_base: str):
    """异步处理文件分块（只分块处理，不保存原始文件）"""
    try:
        update_task_progress(task_id, "processing", 0.1, "开始处理文件...")
        
        rag = get_rag_instance()
        
        update_task_progress(task_id, "processing", 0.3, "解析文件内容并分块...")
        
        # 只分块，不保存原始文件
        success = rag.add_chunks_only(file_content, filename)
        
        if success:
            chunk_count = rag.get_chunk_count()
            update_task_progress(
                task_id, "completed", 1.0, "文件分块处理完成",
                result={
                    "filename": filename,
                    "knowledge_base": knowledge_base,
                    "chunk_count": chunk_count,
                    "processing_type": "chunks_only"
                }
            )
        else:
            update_task_progress(task_id, "failed", 1.0, "文件分块处理失败", error="处理过程中发生错误")
    
    except Exception as e:
        logger.error(f"文件处理失败: {str(e)}")
        update_task_progress(task_id, "failed", 1.0, "文件分块处理失败", error=str(e))


async def process_file_upload(task_id: str, file_content: bytes, filename: str, knowledge_base: str):
    """异步处理文件上传（只保存原始文件）"""
    try:
        update_task_progress(task_id, "processing", 0.1, "开始上传文件...")
        
        rag = get_rag_instance()
        
        update_task_progress(task_id, "processing", 0.5, "保存原始文件...")
        
        # 只保存原始文件，不分块
        success = rag.store_raw_file_only(file_content, filename)
        
        if success:
            update_task_progress(
                task_id, "completed", 1.0, "文件上传完成",
                result={
                    "filename": filename,
                    "knowledge_base": knowledge_base,
                    "file_size": len(file_content)
                }
            )
        else:
            update_task_progress(task_id, "failed", 1.0, "文件上传失败", error="处理过程中发生错误")
    
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        update_task_progress(task_id, "failed", 1.0, "文件上传失败", error=str(e))


# API路由定义

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("启动知识管理API服务器")
    
    # 创建必要的目录
    Path("logs").mkdir(exist_ok=True)
    
    # 初始化RAG实例
    try:
        get_rag_instance()
        logger.info("RAG实例初始化成功")
    except Exception as e:
        logger.error(f"RAG实例初始化失败: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("关闭知识管理API服务器")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "知识管理API",
        "version": "1.0.0",
        "description": "基于Supabase的知识管理和RAG系统API"
    }


@app.get("/health")
async def health_check():
    """三层架构健康检查"""
    try:
        rag = get_rag_instance()
        
        # 获取知识库统计
        kb_response = rag.supabase.table("knowledge_bases").select("*").execute()
        knowledge_bases = kb_response.data
        
        # 获取文件统计
        files_response = rag.supabase.table("document_files").select("id", count="exact").execute()
        total_files = files_response.count or 0
        
        # 获取分块统计
        chunk_count = rag.get_chunk_count()
        
        # 获取任务统计
        tasks_response = rag.supabase.table("task_status").select("status", count="exact").execute()
        total_tasks = tasks_response.count or 0
        
        # 按知识库统计
        kb_stats = []
        for kb in knowledge_bases:
            kb_stats.append({
                "name": kb["name"],
                "description": kb["description"],
                "file_count": kb["document_count"],  # 数据库字段映射
                "chunk_count": kb["chunk_count"],
                "created_at": kb["created_at"]
            })
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_stats": {
                "knowledge_bases": {
                    "total": len(knowledge_bases),
                    "details": kb_stats
                },
                "files": {
                    "total": total_files
                },
                "chunks": {
                    "total": chunk_count
                },
                "tasks": {
                    "total": total_tasks
                }
            },
            "summary": {
                "knowledge_bases_count": len(knowledge_bases),
                "files_count": total_files,
                "chunks_count": chunk_count,
                "tasks_count": total_tasks
            }
        }
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")


# 知识库管理API（三层架构：知识库 -> 文件 -> 分块）

@app.get("/api/v1/knowledge-bases", response_model=List[KnowledgeBase])
async def list_knowledge_bases():
    """获取知识库列表"""
    try:
        rag = get_rag_instance()
        response = rag.supabase.table("knowledge_bases").select("*").order("created_at", desc=True).execute()
        
        knowledge_bases = []
        for kb_data in response.data:
            kb = KnowledgeBase(
                name=kb_data["name"],
                description=kb_data["description"],
                file_count=kb_data["document_count"],  # 数据库字段映射
                chunk_count=kb_data["chunk_count"],
                created_at=datetime.fromisoformat(kb_data["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(kb_data["updated_at"].replace("Z", "+00:00"))
            )
            knowledge_bases.append(kb)
        
        return knowledge_bases
    except Exception as e:
        logger.error(f"获取知识库列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/knowledge-bases/{kb_name}", response_model=KnowledgeBase)
async def get_knowledge_base_info(kb_name: str):
    """获取单个知识库详细信息"""
    try:
        rag = get_rag_instance()
        response = rag.supabase.table("knowledge_bases").select("*").eq("name", kb_name).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        kb_data = response.data[0]
        return KnowledgeBase(
            name=kb_data["name"],
            description=kb_data["description"],
            file_count=kb_data["document_count"],  # 数据库字段映射
            chunk_count=kb_data["chunk_count"],
            created_at=datetime.fromisoformat(kb_data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(kb_data["updated_at"].replace("Z", "+00:00"))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/knowledge-bases")
async def create_knowledge_base(
    request: Request,
    name: str = Form(...), 
    description: str = Form("")
):
    """创建新知识库"""
    try:
        rag = get_rag_instance()
        kb_data = {
            "name": name,
            "description": description,
            "document_count": 0,  # 数据库字段保持不变
            "chunk_count": 0
        }
        response = rag.supabase.table("knowledge_bases").insert(kb_data).execute()
        return {"message": f"知识库 '{name}' 创建成功", "data": response.data[0]}
    except Exception as e:
        logger.error(f"创建知识库失败: {str(e)}")
        if "duplicate key value" in str(e):
            raise HTTPException(status_code=400, detail="知识库名称已存在")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/knowledge-bases/{kb_name}")
async def delete_knowledge_base(kb_name: str):
    """删除整个知识库（包括所有文件和分块）"""
    try:
        rag = get_rag_instance()
        
        # 检查知识库是否存在
        kb_response = rag.supabase.table("knowledge_bases").select("*").eq("name", kb_name).execute()
        if not kb_response.data:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 删除该知识库下的所有内容
        result = rag.clear_knowledge_base(kb_name)
        
        if result:
            # 删除知识库记录
            rag.supabase.table("knowledge_bases").delete().eq("name", kb_name).execute()
            return {"message": f"知识库 '{kb_name}' 及其所有内容已删除"}
        else:
            raise HTTPException(status_code=500, detail="删除知识库失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 文件管理API（按知识库层级）

@app.get("/api/v1/knowledge-bases/{kb_name}/files", response_model=List[FileInfo])
async def list_files_in_knowledge_base(kb_name: str):
    """获取指定知识库的文件列表"""
    try:
        rag = get_rag_instance(kb_name)  # 使用指定的知识库
        files = rag.get_files_by_knowledge_base(kb_name)
        return files
    except Exception as e:
        logger.error(f"获取知识库文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/knowledge-bases/{kb_name}/files/{file_id}", response_model=FileInfo)
async def get_file_info_in_knowledge_base(kb_name: str, file_id: str):
    """获取指定知识库中的单个文件信息"""
    try:
        rag = get_rag_instance()
        file_info = rag.get_single_file_info_by_kb(file_id, kb_name)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileInfo(**file_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 兼容原有API（默认知识库）
@app.get("/api/v1/chunks", response_model=List[ChunkInfo])
async def list_chunks(knowledge_base: str = Query("default", description="知识库名称")):
    """获取分块列表（有向量分块的文件列表）"""
    try:
        rag = get_rag_instance(knowledge_base)
        chunks_info = rag.get_chunks_info()
        
        return [
            ChunkInfo(
                id=chunk["id"],
                filename=chunk["filename"],
                content_type=chunk.get("content_type", "text"),
                file_size=chunk.get("size", 0),  # 数据库字段映射
                chunk_count=chunk.get("chunk_count", 0),
                collection_name=chunk.get("collection_name", "default"),
                created_at=datetime.fromisoformat(chunk["created_at"].replace("Z", "+00:00")),
                metadata=chunk.get("metadata", {})
            )
            for chunk in chunks_info
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 分块管理API

@app.post("/api/v1/knowledge-bases/{kb_name}/chunks/upload", response_model=DocumentUploadResponse)
async def upload_file_for_chunks(
    kb_name: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """上传文件进行分块处理（用于RAG查询，不保存原始文件）"""
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
        update_task_progress(task_id, "pending", 0.0, "任务已创建")
        
        # 添加后台任务
        background_tasks.add_task(
            process_file_for_chunks, 
            task_id, 
            file_content, 
            file.filename, 
            kb_name
        )
        
        logger.info(f"文档上传任务已创建: {file.filename}, task_id: {task_id}")
        
        return DocumentUploadResponse(
            task_id=task_id,
            message="文档上传任务已创建",
            filename=file.filename
        )
    
    except Exception as e:
        logger.error(f"文档上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/files", response_model=List[FileInfo])
async def list_files(knowledge_base: str = Query("default", description="知识库名称")):
    """获取原始文件列表"""
    try:
        rag = get_rag_instance()
        files_info = rag.get_files_info()
        
        return [
            FileInfo(
                id=file["id"],
                filename=file["filename"],
                original_filename=file.get("original_filename", file["filename"]),
                content_type=file.get("content_type", "application/octet-stream"),
                file_size=file.get("file_size", 0),
                file_hash=file.get("file_hash", ""),
                collection_name=file.get("collection_name", "default"),
                created_at=datetime.fromisoformat(file["created_at"].replace("Z", "+00:00")),
                metadata=file.get("metadata", {})
            )
            for file in files_info
        ]
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 已删除不带知识库参数的文件信息获取API，统一使用 /api/v1/knowledge-bases/{kb_name}/files/{file_id}


@app.post("/api/v1/knowledge-bases/{kb_name}/files/upload", response_model=DocumentUploadResponse)
async def upload_file(
    kb_name: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """上传原始文件（只保存，不分块处理）"""
    try:
        # 检查文件类型
        allowed_extensions = {'.txt', '.pdf', '.docx', '.doc', '.md', '.xlsx', '.pptx', '.png', '.jpg', '.jpeg'}
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
        update_task_progress(task_id, "pending", 0.0, "文件上传任务已创建")
        
        # 添加后台任务
        background_tasks.add_task(
            process_file_upload, 
            task_id, 
            file_content, 
            file.filename, 
            kb_name
        )
        
        logger.info(f"文件上传任务已创建: {file.filename}, task_id: {task_id}")
        
        return DocumentUploadResponse(
            task_id=task_id,
            message="文件上传任务已创建",
            filename=file.filename
        )
    
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/files/{file_id}/download")
async def download_file(file_id: str):
    """直接下载指定文件"""
    try:
        rag = get_rag_instance()
        
        # 直接获取文件内容
        file_result = rag.get_file_content(file_id)
        
        if not file_result:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        filename, content_type, file_content = file_result
        
        # 返回文件下载响应
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(file_content))
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/chunks/{chunk_metadata_id}")
async def delete_chunks(chunk_metadata_id: str):
    """删除指定分块元数据的所有分块（保留原始文件）"""
    try:
        rag = get_rag_instance()
        success = rag.delete_chunks_only(chunk_metadata_id)
        
        if success:
            logger.info(f"分块已删除: {chunk_metadata_id}")
            return {"message": f"分块 {chunk_metadata_id} 已删除，原始文件保留"}
        else:
            raise HTTPException(status_code=500, detail="删除失败")
    
    except Exception as e:
        logger.error(f"删除分块失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/files/{file_id}")
async def delete_file(file_id: str):
    """删除原始文件及其关联的所有分块（推荐用于前端）"""
    try:
        rag = get_rag_instance()
        success = rag.delete_file_and_chunks(file_id)
        
        if success:
            logger.info(f"文件及其关联分块已删除: {file_id}")
            return {"message": f"文件 {file_id} 及其所有关联分块已删除"}
        else:
            raise HTTPException(status_code=500, detail="删除失败")
    
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/knowledge-bases/{kb_name}/clear")
async def clear_knowledge_base_content(kb_name: str):
    """清空指定知识库的所有内容（文件和分块）"""
    try:
        rag = get_rag_instance()
        success = rag.clear_knowledge_base(kb_name)
        
        if success:
            logger.info(f"知识库 {kb_name} 已清空")
            return {"message": f"知识库 '{kb_name}' 的所有内容已清空"}
        else:
            raise HTTPException(status_code=500, detail="清空知识库失败")
    
    except Exception as e:
        logger.error(f"清空文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 分块管理API

@app.post("/api/v1/chunks/search", response_model=ChunkSearchResponse)
async def search_chunks(request: ChunkSearchRequest):
    """搜索文档分块"""
    start_time = time.time()
    
    try:
        rag = get_rag_instance()
        
        # 使用向量搜索找到相似的分块
        if not rag.vector_store:
            return ChunkSearchResponse(
                chunks=[],
                total=0,
                query=request.query,
                processing_time=time.time() - start_time
            )
        
        # 执行相似性搜索
        docs = rag.vector_store.similarity_search(
            request.query,
            k=request.limit
        )
        
        chunks = []
        for doc in docs:
            chunk = DocumentChunk(
                id=doc.metadata.get("chunk_id", str(uuid.uuid4())),
                content=doc.page_content,
                metadata=doc.metadata,
                created_at=datetime.now()
            )
            chunks.append(chunk)
        
        processing_time = time.time() - start_time
        
        return ChunkSearchResponse(
            chunks=chunks,
            total=len(chunks),
            query=request.query,
            processing_time=processing_time
        )
    
    except Exception as e:
        logger.error(f"分块搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/chunks/{chunk_metadata_id}/details", response_model=ChunkSearchResponse)
async def get_chunk_details(chunk_metadata_id: str):
    """获取指定分块元数据的所有分块详情"""
    start_time = time.time()
    
    try:
        rag = get_rag_instance()
        chunks = rag.get_chunks_by_metadata_id(chunk_metadata_id)
        
        processing_time = time.time() - start_time
        
        return ChunkSearchResponse(
            chunks=chunks,
            total=len(chunks),
            query=f"chunk_metadata_id:{chunk_metadata_id}",
            processing_time=processing_time
        )
    
    except Exception as e:
        logger.error(f"获取分块详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/files/{file_id}/chunks", response_model=ChunkSearchResponse)
async def get_file_chunks(file_id: str):
    """获取指定文件的所有分块"""
    start_time = time.time()
    
    try:
        rag = get_rag_instance()
        chunks = rag.get_file_chunks(file_id)
        
        processing_time = time.time() - start_time
        
        return ChunkSearchResponse(
            chunks=chunks,
            total=len(chunks),
            query=f"file_id:{file_id}",
            processing_time=processing_time
        )
    
    except Exception as e:
        logger.error(f"获取文件分块失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 问答API

@app.post("/api/v1/query", response_model=QueryResponse)
async def query_knowledge_base(request: QueryRequest):
    """查询知识库"""
    try:
        rag = get_rag_instance()
        
        if rag.get_chunk_count() == 0:
            return QueryResponse(
                answer="知识库为空，请先上传文档。",
                sources=[],
                query=request.question,
                processing_time=0,
                knowledge_base=request.knowledge_base
            )
        
        # 查询
        response = rag.query(request.question)
        
        logger.info(f"问答完成: {request.question[:50]}...")
        
        return QueryResponse(
            answer=response.answer,
            sources=response.sources,
            query=request.question,
            processing_time=response.processing_time,
            knowledge_base=request.knowledge_base
        )
    
    except Exception as e:
        logger.error(f"问答失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 任务管理API

@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    try:
        rag = get_rag_instance()
        
        # 优先从数据库查询
        response = rag.supabase.table("task_status")\
            .select("*")\
            .eq("task_id", task_id)\
            .execute()
        
        if response.data:
            task_data = response.data[0]
            # 转换时间格式
            task_data["created_at"] = datetime.fromisoformat(task_data["created_at"].replace("Z", "+00:00"))
            task_data["updated_at"] = datetime.fromisoformat(task_data["updated_at"].replace("Z", "+00:00"))
            return TaskStatus(**task_data)
        
        # 降级到内存查询
        if task_id in progress_storage:
            return TaskStatus(**progress_storage[task_id])
        
        raise HTTPException(status_code=404, detail="任务不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        # 降级到内存查询
        if task_id in progress_storage:
            return TaskStatus(**progress_storage[task_id])
        raise HTTPException(status_code=500, detail="查询任务状态失败")


@app.get("/api/v1/tasks", response_model=List[TaskStatus])
async def list_tasks(limit: int = Query(10, description="返回数量限制")):
    """获取任务列表"""
    try:
        rag = get_rag_instance()
        
        # 从数据库查询任务列表
        response = rag.supabase.table("task_status")\
            .select("*")\
            .order("updated_at", desc=True)\
            .limit(limit)\
            .execute()
        
        tasks = []
        for task_data in response.data:
            # 转换时间格式
            task_data["created_at"] = datetime.fromisoformat(task_data["created_at"].replace("Z", "+00:00"))
            task_data["updated_at"] = datetime.fromisoformat(task_data["updated_at"].replace("Z", "+00:00"))
            tasks.append(TaskStatus(**task_data))
        
        return tasks
        
    except Exception as e:
        logger.error(f"查询任务列表失败: {str(e)}")
        # 降级到内存查询
        tasks = list(progress_storage.values())
        tasks.sort(key=lambda x: x["updated_at"], reverse=True)
        return [TaskStatus(**task) for task in tasks[:limit]]


@app.delete("/api/v1/tasks/cleanup")
async def cleanup_old_tasks(days_old: int = Query(7, description="删除多少天前的任务")):
    """清理旧任务"""
    try:
        rag = get_rag_instance()
        
        # 调用数据库清理函数
        response = rag.supabase.rpc("cleanup_old_tasks", {"days_old": days_old}).execute()
        deleted_count = response.data if response.data else 0
        
        # 同时清理内存中的旧任务
        current_time = datetime.now()
        old_task_ids = [
            task_id for task_id, task_data in progress_storage.items()
            if (current_time - task_data["updated_at"]).days >= days_old
        ]
        
        for task_id in old_task_ids:
            del progress_storage[task_id]
        
        return {
            "message": f"已清理 {deleted_count} 个旧任务",
            "deleted_count": deleted_count,
            "memory_cleaned": len(old_task_ids)
        }
        
    except Exception as e:
        logger.error(f"清理旧任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理旧任务失败: {str(e)}")


# 配置管理API

@app.get("/api/v1/config")
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


@app.post("/api/v1/config")
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
        supabase_config = get_supabase_config()
        rag_instance = SupabaseRAG(new_config, supabase_config)
        
        logger.info("配置已更新")
        
        return {"message": "配置已更新", "config": config_dict}
    
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/refresh-stats")
async def refresh_knowledge_base_stats():
    """手动刷新所有知识库统计数据"""
    try:
        rag = get_rag_instance()
        
        # 获取所有知识库
        kb_response = rag.supabase.table("knowledge_bases").select("name").execute()
        
        updated_count = 0
        for kb_data in kb_response.data:
            kb_name = kb_data["name"]
            rag._update_knowledge_base_stats(kb_name)
            updated_count += 1
        
        return {
            "message": f"已刷新 {updated_count} 个知识库的统计数据",
            "updated_knowledge_bases": updated_count
        }
        
    except Exception as e:
        logger.error(f"刷新统计数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/debug-embeddings")
async def debug_embeddings():
    """调试：查看embedding表的cmetadata内容"""
    try:
        from sqlalchemy import create_engine, text
        
        supabase_config = get_supabase_config()
        engine = create_engine(supabase_config.postgres_url)
        
        with engine.connect() as conn:
            # 查看几条embedding记录的cmetadata
            result = conn.execute(text("""
                SELECT e.id, e.cmetadata, c.name as collection_name
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                LIMIT 5
            """)).fetchall()
            
            embeddings = []
            for row in result:
                embeddings.append({
                    "id": row[0],
                    "cmetadata": row[1],
                    "collection_name": row[2]
                })
        
        engine.dispose()
        return {"embeddings": embeddings}
        
    except Exception as e:
        logger.error(f"调试embedding失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/debug-collections")
async def debug_collections():
    """调试：查看所有collection和向量数据"""
    try:
        from sqlalchemy import create_engine, text
        
        supabase_config = get_supabase_config()
        engine = create_engine(supabase_config.postgres_url)
        
        result = {}
        
        with engine.connect() as conn:
            # 1. 查看所有collection
            collections = conn.execute(text("""
                SELECT name, cmetadata 
                FROM langchain_pg_collection 
                ORDER BY name
            """)).fetchall()
            
            result["collections"] = [{"name": row[0], "metadata": row[1]} for row in collections]
            
            # 2. 查看每个collection的向量数量
            collection_counts = {}
            for collection in collections:
                count = conn.execute(text("""
                    SELECT COUNT(*) 
                    FROM langchain_pg_embedding e
                    WHERE e.collection_id = (
                        SELECT uuid FROM langchain_pg_collection WHERE name = :name
                    )
                """), {"name": collection[0]}).scalar()
                collection_counts[collection[0]] = count
            
            result["collection_counts"] = collection_counts
            
            # 3. 查看document_files表
            files = conn.execute(text("""
                SELECT id, filename, original_filename, collection_name, created_at 
                FROM document_files 
                ORDER BY created_at DESC
            """)).fetchall()
            
            result["files"] = [{"id": str(row[0]), "filename": row[1], "original_filename": row[2], "collection_name": row[3], "created_at": str(row[4])} for row in files]
            
            # 4. 查看document_metadata表
            metadata = conn.execute(text("""
                SELECT id, file_id, filename, collection_name, chunk_count, created_at 
                FROM document_metadata 
                ORDER BY created_at DESC
            """)).fetchall()
            
            result["metadata"] = [{"id": str(row[0]), "file_id": str(row[1]) if row[1] else None, "filename": row[2], "collection_name": row[3], "chunk_count": row[4], "created_at": str(row[5])} for row in metadata]
        
        engine.dispose()
        return result
        
    except Exception as e:
        logger.error(f"调试查询失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/migrate-old-vectors")
async def migrate_old_vectors():
    """迁移旧的documents collection向量到对应的知识库collection"""
    try:
        from sqlalchemy import create_engine, text
        import uuid
        
        supabase_config = get_supabase_config()
        rag = get_rag_instance()
        engine = create_engine(supabase_config.postgres_url)
        
        with engine.connect() as conn:
            # 1. 检查documents collection中的向量
            result = conn.execute(text("""
                SELECT COUNT(*) FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = 'documents'
            """))
            old_vector_count = result.scalar()
            
            if old_vector_count == 0:
                return {"message": "没有需要迁移的旧向量", "migrated_count": 0}
            
            # 2. 获取documents collection的UUID
            old_collection_uuid = conn.execute(text("""
                SELECT uuid FROM langchain_pg_collection WHERE name = 'documents'
            """)).scalar()
            
            # 3. 获取或创建default collection的UUID  
            default_collection_uuid = conn.execute(text("""
                SELECT uuid FROM langchain_pg_collection WHERE name = 'default'
            """)).scalar()
            
            if not default_collection_uuid:
                # 创建default collection
                conn.execute(text("""
                    INSERT INTO langchain_pg_collection (name, cmetadata)
                    VALUES ('default', '{}')
                """))
                default_collection_uuid = conn.execute(text("""
                    SELECT uuid FROM langchain_pg_collection WHERE name = 'default'
                """)).scalar()
            
            # 4. 将向量从documents迁移到default
            conn.execute(text("""
                UPDATE langchain_pg_embedding 
                SET collection_id = :new_collection_id
                WHERE collection_id = :old_collection_id
            """), {
                "new_collection_id": default_collection_uuid,
                "old_collection_id": old_collection_uuid
            })
            
            # 5. 为demo.pdf创建document_metadata记录
            file_response = rag.supabase.from_("document_files")\
                .select("*")\
                .eq("filename", "demo.pdf")\
                .eq("collection_name", "default")\
                .execute()
            
            if file_response.data:
                file_data = file_response.data[0]
                metadata_data = {
                    "id": str(uuid.uuid4()),
                    "file_id": file_data["id"],
                    "filename": "demo.pdf",
                    "content_type": file_data.get("content_type", "application/pdf"),
                    "size": file_data.get("file_size", 0),
                    "chunk_count": old_vector_count,
                    "collection_name": "default",
                    "metadata": {}
                }
                
                rag.supabase.table("document_metadata").insert(metadata_data).execute()
            
            conn.commit()
        
        engine.dispose()
        
        # 刷新知识库统计
        rag._update_knowledge_base_stats()
        
        return {
            "message": f"向量迁移完成",
            "migrated_count": old_vector_count,
            "from_collection": "documents",
            "to_collection": "default"
        }
        
    except Exception as e:
        logger.error(f"向量迁移失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/fix-metadata-links")
async def fix_metadata_links():
    """修复document_metadata表中缺失的file_id关联"""
    try:
        supabase_config = get_supabase_config()
        rag = get_rag_instance()
        
        fixed_count = 0
        
        # 获取所有file_id为NULL的metadata记录
        null_metadata_response = rag.supabase.table("document_metadata")\
            .select("id, filename, collection_name")\
            .is_("file_id", "null")\
            .execute()
        
        if not null_metadata_response.data:
            return {"message": "没有需要修复的metadata关联", "fixed_count": 0}
        
        for meta_record in null_metadata_response.data:
            filename = meta_record["filename"]
            collection_name = meta_record["collection_name"]
            
            # 查找对应的document_files记录
            file_response = rag.supabase.table("document_files")\
                .select("id")\
                .eq("filename", filename)\
                .eq("collection_name", collection_name)\
                .execute()
            
            if file_response.data:
                file_id = file_response.data[0]["id"]
                
                # 更新metadata记录的file_id
                update_response = rag.supabase.table("document_metadata")\
                    .update({"file_id": file_id})\
                    .eq("id", meta_record["id"])\
                    .execute()
                
                if update_response.data:
                    fixed_count += 1
                    logger.info(f"修复metadata关联: {filename} -> {file_id}")
        
        return {
            "message": f"metadata关联修复完成",
            "total_null_records": len(null_metadata_response.data),
            "fixed_count": fixed_count
        }
        
    except Exception as e:
        logger.error(f"修复metadata关联失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/clear-cache")
async def clear_rag_cache():
    """清理RAG实例缓存（用于解决连接问题）"""
    global rag_instances_cache
    
    try:
        # 清理所有缓存的实例
        cleared_count = len(rag_instances_cache)
        
        # 尝试正确关闭所有实例的连接
        for kb_name, instance in rag_instances_cache.items():
            try:
                if hasattr(instance, '_db_engine') and instance._db_engine is not None:
                    instance._db_engine.dispose()
                    logger.info(f"已清理知识库 {kb_name} 的数据库连接")
            except Exception as e:
                logger.warning(f"清理知识库 {kb_name} 连接时出错: {str(e)}")
        
        # 清空缓存
        rag_instances_cache.clear()
        
        return {
            "message": f"已清理 {cleared_count} 个RAG实例缓存",
            "cleared_instances": cleared_count
        }
        
    except Exception as e:
        logger.error(f"清理RAG缓存失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/fix-orphan-chunks")
async def fix_orphan_chunks():
    """修复孤儿分块：为已存在的分块创建缺失的document_metadata记录"""
    try:
        from sqlalchemy import create_engine, text
        import uuid
        
        # 初始化配置
        supabase_config = get_supabase_config()
        rag = get_rag_instance()
        engine = create_engine(supabase_config.postgres_url)
        
        fixed_count = 0
        
        # 获取所有文件
        files_response = rag.supabase.from_("document_files").select("*").execute()
        
        for file_data in files_response.data:
            filename = file_data["filename"]
            collection_name = file_data["collection_name"] or "default"
            file_id = file_data["id"]
            
            # 检查是否已有document_metadata记录
            metadata_response = rag.supabase.table("document_metadata")\
                .select("id")\
                .eq("filename", filename)\
                .eq("collection_name", collection_name)\
                .execute()
            
            if metadata_response.data:
                continue  # 已有记录，跳过
            
            # 查询该文件的实际分块数量
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name = :collection_name
                    AND e.cmetadata->>'source' LIKE :filename_pattern
                """), {
                    "collection_name": collection_name,
                    "filename_pattern": f"%{filename}%"
                })
                chunk_count = result.scalar() or 0
            
            # 如果有分块但没有metadata记录，创建记录
            if chunk_count > 0:
                metadata_data = {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "filename": filename,
                    "content_type": file_data.get("content_type", "application/pdf"),
                    "size": file_data.get("file_size", 0),
                    "chunk_count": chunk_count,
                    "collection_name": collection_name,
                    "metadata": {}
                }
                
                create_response = rag.supabase.table("document_metadata").insert(metadata_data).execute()
                
                if create_response.data:
                    fixed_count += 1
                    logger.info(f"为文件 {filename} 创建了document_metadata记录，分块数: {chunk_count}")
        
        engine.dispose()
        
        # 刷新知识库统计
        rag._update_knowledge_base_stats()
        
        return {
            "message": f"孤儿分块修复完成",
            "total_files": len(files_response.data),
            "fixed_count": fixed_count
        }
        
    except Exception as e:
        logger.error(f"修复孤儿分块失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # 配置服务器参数
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8002"))
    
    logger.info(f"启动知识管理API服务器: http://{host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
