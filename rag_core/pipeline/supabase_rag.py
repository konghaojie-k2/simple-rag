"""基于Supabase的RAG流水线实现"""

import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres import PGVector, PGEngine
from langchain.schema import Document as LangchainDocument
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from supabase import create_client, Client

from ..config.models import RAGConfig, RAGResponse, Document, ProcessingProgress
from ..config.supabase_config import SupabaseConfig
from ..utils.file_processor import FileProcessor
from ..utils.text_splitter import SmartTextSplitter
from ..utils.hybrid_storage import HybridFileStorage
from ..utils.logger import rag_logger


class SupabaseRAG:
    """基于Supabase的RAG实现类"""
    
    def __init__(self, config: RAGConfig, supabase_config: SupabaseConfig):
        """
        初始化RAG系统
        
        Args:
            config: RAG配置
            supabase_config: Supabase配置（包含bucket_name）
        """
        self.config = config
        self.supabase_config = supabase_config
        self.logger = rag_logger
        self.file_processor = FileProcessor()
        self.text_splitter = SmartTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        
        # 设置代理（如果配置了）
        self._setup_proxy()
        
        # 初始化模型
        self.chat_model = self._init_chat_model()
        self.embedding_model = self._init_embedding_model()
        
        # 初始化Supabase客户端
        self.supabase: Client = create_client(
            supabase_config.url,
            supabase_config.key
        )
        
        # 初始化文件存储管理器
        self.file_storage = HybridFileStorage(
            supabase_client=self.supabase,
            bucket_name=supabase_config.bucket_name
        )
        
        # 初始化PostgreSQL引擎
        self.pg_engine = PGEngine.from_connection_string(
            url=supabase_config.postgres_url
        )
        
        # 初始化向量存储
        self.vector_store = None
        self.retrieval_chain = None
        self._db_engine = None  # 保存数据库引擎引用
        
        # 初始化向量存储
        self._init_vector_store()
        
        self.logger.info("Supabase RAG系统初始化完成")
    
    def __del__(self):
        """析构函数，清理数据库连接"""
        try:
            if hasattr(self, '_db_engine') and self._db_engine is not None:
                self._db_engine.dispose()
                self.logger.info("SupabaseRAG析构时已清理数据库连接")
        except Exception as e:
            # 析构函数中不应该抛出异常
            pass
    
    def _setup_proxy(self):
        """设置代理配置"""
        if self.config.http_proxy:
            os.environ['HTTP_PROXY'] = self.config.http_proxy
        if self.config.https_proxy:
            os.environ['HTTPS_PROXY'] = self.config.https_proxy
        if self.config.no_proxy:
            os.environ['NO_PROXY'] = self.config.no_proxy
    
    def _init_chat_model(self) -> ChatOpenAI:
        """初始化聊天模型"""
        try:
            return ChatOpenAI(
                model=self.config.chat_model,
                openai_api_key=self.config.api_key,
                openai_api_base=self.config.base_url,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout
            )
        except Exception as e:
            self.logger.error(f"聊天模型初始化失败: {str(e)}")
            raise
    
    def _init_embedding_model(self) -> OpenAIEmbeddings:
        """初始化嵌入模型"""
        try:
            # 确定是否需要禁用上下文长度检查
            check_embedding_ctx_length = True
            
            # 阿里云DashScope或本地服务特殊处理
            if ("dashscope" in self.config.base_url.lower() or 
                "localhost" in self.config.base_url.lower() or
                "127.0.0.1" in self.config.base_url):
                check_embedding_ctx_length = False
            
            return OpenAIEmbeddings(
                model=self.config.embedding_model,
                openai_api_key=self.config.api_key,
                openai_api_base=self.config.base_url,
                timeout=self.config.timeout,
                check_embedding_ctx_length=check_embedding_ctx_length  # 直接作为参数
            )
        except Exception as e:
            self.logger.error(f"嵌入模型初始化失败: {str(e)}")
            raise
    
    def _init_vector_store(self):
        """初始化向量存储"""
        try:
            # 清理旧的engine连接，避免prepared statement冲突
            if hasattr(self, '_db_engine') and self._db_engine is not None:
                try:
                    self._db_engine.dispose()
                    self.logger.info("已清理旧的数据库连接")
                except Exception as e:
                    self.logger.warning(f"清理旧连接时出错: {str(e)}")
            
            # 使用PGVector连接到Supabase，使用动态知识库collection
            connection_string = self.supabase_config.postgres_url
            
            # 创建带有连接池配置的引擎
            from sqlalchemy import create_engine
            self._db_engine = create_engine(
                connection_string,
                pool_pre_ping=True,  # 连接前检查
                pool_recycle=3600,   # 1小时后回收连接
                pool_size=15,         # 连接池大小
                max_overflow=10,     # 最大溢出连接数
                echo=False           # 关闭SQL日志，避免过多输出
            )
            
            # 使用业务层知识库名称作为collection，实现真正的多知识库隔离
            collection_name = self.supabase_config.collection_name or "default"
            
            self.vector_store = PGVector(
                embeddings=self.embedding_model,
                collection_name=collection_name,  # 使用业务层知识库名称
                connection=self._db_engine,  # 使用配置好的引擎
                use_jsonb=True,
                pre_delete_collection=False,  # 不要删除已存在的表
                distance_strategy="cosine"  # 使用余弦相似度
            )
            
            # 初始化检索链
            self._init_retrieval_chain()
            
            self.logger.info(f"Supabase向量存储初始化完成（知识库: {collection_name}）")
            
        except Exception as e:
            self.logger.error(f"向量存储初始化失败: {str(e)}")
            raise
    
    def _init_retrieval_chain(self):
        """初始化检索链"""
        if not self.vector_store:
            return
        
        try:
            # 自定义提示模板
            prompt_template = """
使用以下上下文信息回答用户的问题。如果上下文中没有相关信息，请直接说明无法找到相关信息。

上下文信息:
{context}

问题: {question}

回答:"""
            
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            
            # 创建检索器
            retriever = self.vector_store.as_retriever(
                search_kwargs={"k": self.config.top_k}
            )
            
            # 创建检索问答链
            self.retrieval_chain = RetrievalQA.from_chain_type(
                llm=self.chat_model,
                chain_type="stuff",
                retriever=retriever,
                chain_type_kwargs={"prompt": prompt},
                return_source_documents=True
            )
            
            self.logger.info("检索链初始化完成")
            
        except Exception as e:
            self.logger.error(f"检索链初始化失败: {str(e)}")
            raise
    
    def add_file_chunks(self, file_documents: List[Document]) -> bool:
        """
        添加文件分块到知识库
        
        Args:
            file_documents: 从文件解析的文档列表
            
        Returns:
            bool: 是否成功
        """
        try:
            if not file_documents:
                return False
            
            # 分割文档
            self.logger.info(f"开始处理 {len(file_documents)} 个文档")
            split_documents = self.text_splitter.split_documents(file_documents)
            
            # 转换为langchain格式并添加唯一ID
            langchain_docs = []
            for doc in split_documents:
                # 为每个文档块生成唯一ID
                doc_id = str(uuid.uuid4())
                metadata = doc.metadata.copy()
                metadata["doc_id"] = doc_id
                metadata["chunk_id"] = doc_id
                metadata["collection_name"] = self.supabase_config.collection_name
                
                langchain_doc = LangchainDocument(
                    page_content=doc.content,
                    metadata=metadata
                )
                langchain_docs.append(langchain_doc)
            
            # 分批添加到向量存储（避免批处理大小限制）
            batch_size = 5  # 减少批次大小以减少prepared statement冲突
            ids = []
            
            for i in range(0, len(langchain_docs), batch_size):
                batch = langchain_docs[i:i + batch_size]
                self.logger.info(f"处理批次 {i//batch_size + 1}/{(len(langchain_docs) + batch_size - 1)//batch_size}，文档数: {len(batch)}")
                batch_ids = self.vector_store.add_documents(batch)
                if batch_ids:
                    ids.extend(batch_ids)
            
            # 存储文件元数据到Supabase表（不包含原始文件）
            self._store_file_metadata(file_documents, split_documents)
            
            self.logger.info(f"文档添加完成，总计 {len(langchain_docs)} 个文档块")
            return True
            
        except Exception as e:
            self.logger.error(f"添加文档失败: {str(e)}")
            return False
    
    def _store_file_metadata(self, original_docs: List[Document], split_docs: List[Document], 
                                file_content: bytes = None, filename: str = None):
        """存储文件元数据和原始文件到Supabase表"""
        import hashlib
        import base64
        
        try:
            # 为每个原始文档创建记录
            for orig_doc in original_docs:
                # 计算该文档的分块数量
                chunk_count = sum(1 for split_doc in split_docs 
                                if split_doc.metadata.get("source") == orig_doc.metadata.get("source"))
                
                file_id = None
                
                # 如果有原始文件内容，先存储到文件表
                if file_content and filename:
                    # 计算文件哈希
                    file_hash = hashlib.sha256(file_content).hexdigest()
                    
                    # 检查文件是否已存在
                    existing_file = self.supabase.rpc("check_file_exists", {"file_hash_input": file_hash}).execute()
                    
                    if existing_file.data:
                        # 文件已存在，使用现有文件ID
                        file_id = existing_file.data[0]["file_id"]
                        self.logger.info(f"文件已存在，使用现有文件: {file_id}")
                    else:
                        # 创建新文件记录
                        file_record = {
                            "id": str(uuid.uuid4()),
                            "filename": filename,
                            "original_filename": filename,
                            "content_type": orig_doc.metadata.get("content_type", "application/octet-stream"),
                            "file_size": len(file_content),
                            "file_hash": file_hash,
                            "file_content": base64.b64encode(file_content).decode('utf-8'),  # 编码为base64字符串
                            "collection_name": self.supabase_config.collection_name,
                            "metadata": {"upload_source": "api"}
                        }
                        
                        file_result = self.supabase.table("document_files").insert(file_record).execute()
                        file_id = file_result.data[0]["id"]
                        self.logger.info(f"新文件已存储: {file_id}")
                
                # 创建文档元数据记录
                doc_record = {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "filename": orig_doc.metadata.get("source", filename or "unknown"),
                    "content_type": orig_doc.metadata.get("content_type", "text"),
                    "size": len(orig_doc.content),
                    "chunk_count": chunk_count,
                    "processed_content": orig_doc.content,
                    "collection_name": self.supabase_config.collection_name,
                    "metadata": orig_doc.metadata
                }
                
                # 插入到Supabase
                self.supabase.table("document_metadata").insert(doc_record).execute()
                
        except Exception as e:
            self.logger.warning(f"存储文档元数据失败: {str(e)}")
    
    def add_file_chunks_from_file(self, file_path: str) -> bool:
        """
        从文件路径添加文件分块
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            documents = self.file_processor.process_file(file_path)
            return self.add_file_chunks(documents)
        except Exception as e:
            self.logger.error(f"从文件添加文档失败: {str(e)}")
            return False
    
    def add_file_and_chunks(self, file_content: bytes, filename: str) -> bool:
        """
        从上传的文件添加原始文件和分块
        
        Args:
            file_content: 文件二进制内容
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        try:
            # 处理文件内容
            documents = self.file_processor.process_uploaded_file(file_content, filename)
            
            if not documents:
                return False
            
            # 分割文档
            self.logger.info(f"开始处理上传文件: {filename}")
            split_documents = self.text_splitter.split_documents(documents)
            
            # 转换为langchain格式并添加唯一ID
            langchain_docs = []
            for doc in split_documents:
                # 为每个文档块生成唯一ID
                doc_id = str(uuid.uuid4())
                metadata = doc.metadata.copy()
                metadata["doc_id"] = doc_id
                metadata["chunk_id"] = doc_id
                metadata["collection_name"] = self.supabase_config.collection_name
                
                langchain_doc = LangchainDocument(
                    page_content=doc.content,
                    metadata=metadata
                )
                langchain_docs.append(langchain_doc)
            
            # 分批添加到向量存储（避免批处理大小限制）
            batch_size = 5  # 减少批次大小以减少prepared statement冲突
            ids = []
            
            for i in range(0, len(langchain_docs), batch_size):
                batch = langchain_docs[i:i + batch_size]
                self.logger.info(f"处理批次 {i//batch_size + 1}/{(len(langchain_docs) + batch_size - 1)//batch_size}，文档数: {len(batch)}")
                batch_ids = self.vector_store.add_documents(batch)
                if batch_ids:
                    ids.extend(batch_ids)
            
            # 存储文件元数据和原始文件到Supabase表
            self._store_file_metadata(documents, split_documents, file_content, filename)
            
            # 分块统计通过document_metadata表维护
            
            # 更新知识库统计
            kb_name = self.supabase_config.collection_name or "default"
            self._update_knowledge_base_stats(kb_name)
            
            self.logger.info(f"上传文件处理完成: {filename}，总计 {len(langchain_docs)} 个文档块")
            return True
            
        except Exception as e:
            self.logger.error(f"从上传文件添加文档失败: {str(e)}")
            return False
    
    def add_chunks_only(self, file_content: bytes, filename: str) -> bool:
        """
        从上传的文件只添加分块（不保存原始文件）
        
        Args:
            file_content: 文件二进制内容
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        try:
            # 确保向量存储已初始化
            if self.vector_store is None:
                self.logger.info("向量存储未初始化，开始初始化...")
                self._init_vector_store()
            else:
                self.logger.debug("使用已存在的向量存储实例")
            
            # 处理文件内容
            documents = self.file_processor.process_uploaded_file(file_content, filename)
            
            if not documents:
                return False
            
            # 分割文档
            self.logger.info(f"开始处理上传文件: {filename}")
            split_documents = self.text_splitter.split_documents(documents)
            
            # 转换为langchain格式并添加唯一ID
            langchain_docs = []
            for doc in split_documents:
                # 为每个文档块生成唯一ID
                doc_id = str(uuid.uuid4())
                metadata = doc.metadata.copy()
                metadata["doc_id"] = doc_id
                metadata["chunk_id"] = doc_id
                metadata["collection_name"] = self.supabase_config.collection_name
                
                langchain_doc = LangchainDocument(
                    page_content=doc.content,
                    metadata=metadata
                )
                langchain_docs.append(langchain_doc)
            
            # 分批添加到向量存储（避免批处理大小限制）
            batch_size = 5  # 减少批次大小以减少prepared statement冲突
            ids = []
            
            for i in range(0, len(langchain_docs), batch_size):
                batch = langchain_docs[i:i + batch_size]
                self.logger.info(f"处理批次 {i//batch_size + 1}/{(len(langchain_docs) + batch_size - 1)//batch_size}，文档数: {len(batch)}")
                batch_ids = self.vector_store.add_documents(batch)
                if batch_ids:
                    ids.extend(batch_ids)
            
            # 只存储分块元数据（不包含原始文件）
            self._store_chunk_metadata_only(documents, split_documents, filename)
            
            # 分块统计通过document_metadata表维护
            
            self.logger.info(f"上传文件处理完成: {filename}，总计 {len(langchain_docs)} 个文档块（仅分块）")
            return True
            
        except Exception as e:
            self.logger.error(f"从上传文件添加文档失败: {str(e)}")
            
            # 如果是prepared statement错误，清理连接状态以避免后续冲突
            if "DuplicatePreparedStatement" in str(e):
                self.logger.warning("检测到prepared statement冲突，清理数据库连接...")
                try:
                    if hasattr(self, '_db_engine') and self._db_engine:
                        self._db_engine.dispose()
                        self.logger.info("已清理数据库连接以解决prepared statement冲突")
                except Exception as cleanup_error:
                    self.logger.warning(f"清理连接时出错: {str(cleanup_error)}")
            
            return False
    
    def store_raw_file_only(self, file_content: bytes, filename: str) -> bool:
        """
        只保存原始文件到Storage bucket（不分块处理）
        
        Args:
            file_content: 文件二进制内容
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
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
    
    def _store_chunk_metadata_only(self, original_docs: List[Document], split_docs: List[Document], filename: str):
        """存储分块元数据（不包含原始文件）"""
        try:
            # 检查是否已存在对应的原始文件
            file_id = None
            try:
                file_response = self.supabase.table("document_files")\
                    .select("id")\
                    .eq("original_filename", filename)\
                    .eq("collection_name", self.supabase_config.collection_name)\
                    .execute()
                
                if file_response.data:
                    file_id = file_response.data[0]["id"]
                    self.logger.info(f"找到对应的原始文件: {file_id}")
            except Exception as e:
                self.logger.warning(f"查找原始文件失败: {str(e)}")
            
            # 为每个原始文档创建记录
            for orig_doc in original_docs:
                # 计算该文档的分块数量
                chunk_count = sum(1 for doc in split_docs 
                                if doc.metadata.get("source") == orig_doc.metadata.get("source", filename))
                
                # 创建文档元数据记录
                doc_record = {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,  # 关联到原始文件（如果存在）
                    "filename": orig_doc.metadata.get("source", filename or "unknown"),
                    "content_type": orig_doc.metadata.get("content_type", "text"),
                    "size": len(orig_doc.content),
                    "chunk_count": chunk_count,
                    "processed_content": orig_doc.content,
                    "collection_name": self.supabase_config.collection_name,
                    "metadata": orig_doc.metadata
                }
                
                # 插入到Supabase
                self.supabase.table("document_metadata").insert(doc_record).execute()
                
                # 更新知识库统计
                kb_name = self.supabase_config.collection_name or "default"
                self._update_knowledge_base_stats(kb_name)
                
        except Exception as e:
            self.logger.warning(f"存储文档元数据失败: {str(e)}")
    
    def _update_knowledge_base_stats(self, kb_name: str = "default"):
        """更新知识库统计信息"""
        try:
            # 统计文档数量
            doc_response = self.supabase.table("document_metadata")\
                .select("id", count="exact")\
                .eq("collection_name", kb_name)\
                .execute()
            
            document_count = doc_response.count or 0
            
            # 统计分块数量（直接从document_metadata表汇总）
            chunk_response = self.supabase.table("document_metadata")\
                .select("chunk_count")\
                .eq("collection_name", kb_name)\
                .execute()
            
            chunk_count = 0
            if chunk_response.data:
                chunk_count = sum(record["chunk_count"] or 0 for record in chunk_response.data)
            
            # 更新或创建知识库记录
            kb_response = self.supabase.table("knowledge_bases")\
                .select("id")\
                .eq("name", kb_name)\
                .execute()
            
            if kb_response.data:
                # 更新现有记录
                self.supabase.table("knowledge_bases")\
                    .update({
                        "document_count": document_count,
                        "chunk_count": chunk_count,
                        "updated_at": datetime.now().isoformat()
                    })\
                    .eq("name", kb_name)\
                    .execute()
            else:
                # 创建新记录
                self.supabase.table("knowledge_bases")\
                    .insert({
                        "name": kb_name,
                        "description": f"知识库 {kb_name}",
                        "document_count": document_count,
                        "chunk_count": chunk_count
                    })\
                    .execute()
                    
            self.logger.info(f"知识库 '{kb_name}' 统计已更新: 文件数={document_count}, 分块数={chunk_count}")
            
        except Exception as e:
            self.logger.warning(f"更新知识库统计失败: {str(e)}")
    
    def _update_metadata_file_link(self, filename: str, file_id: str):
        """
        更新document_metadata记录的file_id关联
        
        Args:
            filename: 文件名
            file_id: 文件ID
        """
        try:
            collection_name = self.supabase_config.collection_name or "default"
            
            # 查找所有匹配的document_metadata记录（file_id为NULL的）
            response = self.supabase.table("document_metadata")\
                .update({"file_id": file_id})\
                .eq("filename", filename)\
                .eq("collection_name", collection_name)\
                .is_("file_id", "null")\
                .execute()
            
            if response.data:
                updated_count = len(response.data)
                self.logger.info(f"已更新 {updated_count} 个document_metadata记录的file_id关联: {filename} -> {file_id}")
            else:
                self.logger.info(f"没有找到需要更新file_id的document_metadata记录: {filename}")
                
        except Exception as e:
            self.logger.warning(f"更新metadata文件关联失败: {str(e)}")
    
    def query(self, question: str, **kwargs) -> RAGResponse:
        """
        查询知识库
        
        Args:
            question: 用户问题
            **kwargs: 额外参数
            
        Returns:
            RAGResponse: 查询响应
        """
        start_time = time.time()
        
        try:
            # 检查向量存储是否存在文档
            doc_count = self.get_chunk_count()
            self.logger.info(f"当前文档数量: {doc_count}")
            
            if doc_count == 0 or not self.retrieval_chain:
                # 尝试重新初始化检索链
                if self.vector_store and doc_count > 0:
                    self.logger.info("尝试重新初始化检索链")
                    self._init_retrieval_chain()
                
                if not self.retrieval_chain:
                    return RAGResponse(
                        answer="知识库为空，请先上传文档。",
                        query=question,
                        processing_time=time.time() - start_time
                    )
            
            # 执行检索问答
            result = self.retrieval_chain.invoke({"query": question})
            
            # 处理源文档
            sources = []
            if "source_documents" in result:
                for doc in result["source_documents"]:
                    source_info = {
                        "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                        "metadata": doc.metadata
                    }
                    sources.append(source_info)
            
            processing_time = time.time() - start_time
            
            response = RAGResponse(
                answer=result["result"],
                sources=sources,
                query=question,
                processing_time=processing_time
            )
            
            self.logger.info(f"查询完成，耗时: {processing_time:.2f}秒")
            return response
            
        except Exception as e:
            self.logger.error(f"查询失败: {str(e)}")
            return RAGResponse(
                answer=f"查询过程中发生错误: {str(e)}",
                query=question,
                processing_time=time.time() - start_time
            )
    
    def get_chunk_count(self) -> int:
        """获取分块数量（从langchain_pg_embedding表）"""
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(self.supabase_config.postgres_url)
            
            # 直接统计langchain_pg_embedding表中的分块数量
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM langchain_pg_embedding
                """))
                count = result.scalar()
            
            engine.dispose()  # 释放连接池
            return count if count is not None else 0
            
        except Exception as e:
            self.logger.warning(f"获取文档数量失败: {str(e)}")
            # 备用方法：从document_metadata表获取
            try:
                response = self.supabase.table("document_metadata")\
                    .select("chunk_count")\
                    .eq("collection_name", self.supabase_config.collection_name)\
                    .execute()
                
                total_chunks = sum(doc.get("chunk_count", 0) for doc in response.data)
                return total_chunks
            except:
                return 0
    
    def get_chunks_info(self) -> List[Dict[str, Any]]:
        """获取分块信息列表（有向量分块的文件列表）"""
        try:
            # 直接查询document_files表，获取已上传的文件
            response = self.supabase.from_("document_files")\
                .select("*")\
                .eq("collection_name", self.supabase_config.collection_name)\
                .execute()
            
            # 通过document_metadata表获取分块统计
            files_with_chunks = []
            for file_data in response.data:
                filename = file_data.get("original_filename", file_data.get("filename"))
                
                # 查询对应的document_metadata记录
                metadata_response = self.supabase.table("document_metadata")\
                    .select("id, chunk_count")\
                    .eq("filename", filename)\
                    .eq("collection_name", self.supabase_config.collection_name or "default")\
                    .execute()
                
                # 获取分块数量和文档ID
                chunk_count = 0
                document_id = None
                if metadata_response.data:
                    chunk_count = metadata_response.data[0].get("chunk_count", 0)
                    document_id = metadata_response.data[0].get("id")
                
                # 只有当有document_metadata记录时才返回（因为这是文档列表）
                if document_id is None:
                    continue  # 跳过没有文档元数据的文件
                
                # 构造返回数据
                file_info = {
                    "id": document_id,  # 返回document_metadata.id，用于删除操作
                    "filename": filename,
                    "content_type": file_data.get("content_type", "application/octet-stream"),
                    "size": file_data.get("file_size", 0),
                    "chunk_count": chunk_count,  # 从document_metadata表获取
                    "collection_name": file_data.get("collection_name", "default"),
                    "created_at": file_data.get("created_at"),
                    "metadata": file_data.get("metadata", {})
                }
                files_with_chunks.append(file_info)
            
            return files_with_chunks
            
        except Exception as e:
            self.logger.error(f"获取文档信息失败: {str(e)}")
            return []
    
    def get_files_info(self) -> List[Dict[str, Any]]:
        """获取原始文件信息列表"""
        try:
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("collection_name", self.supabase_config.collection_name)\
                .execute()
            
            return response.data
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败: {str(e)}")
            return []
    
    def get_single_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取单个文件信息"""
        try:
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("id", file_id)\
                .execute()
            
            if response.data:
                return response.data[0]
            return None
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败: {str(e)}")
            return None
    
    def get_chunks_by_metadata_id(self, metadata_id: str) -> List[Dict[str, Any]]:
        """根据document_metadata.id获取分块"""
        try:
            # 首先获取文档信息
            doc_info = self.supabase.table("document_metadata")\
                .select("filename")\
                .eq("id", metadata_id)\
                .execute()
            
            if not doc_info.data:
                return []
            
            filename = doc_info.data[0].get("filename")
            
            # 从向量存储中查询相关分块
            from sqlalchemy import create_engine, text
            engine = create_engine(self.supabase_config.postgres_url)
            
            chunks = []
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT document, cmetadata 
                    FROM langchain_pg_embedding 
                    WHERE document LIKE :filename_pattern
                """), {"filename_pattern": f"%{filename}%"})
                
                for row in result:
                    chunk = {
                        "id": row.cmetadata.get("chunk_id", str(uuid.uuid4())),
                        "content": row.document,
                        "metadata": row.cmetadata,
                        "created_at": datetime.now()
                    }
                    chunks.append(chunk)
            
            engine.dispose()
            return chunks
            
        except Exception as e:
            self.logger.error(f"根据元数据ID获取分块失败: {str(e)}")
            return []
    
    def get_file_chunks(self, file_id: str) -> List[Dict[str, Any]]:
        """获取指定文件的所有分块"""
        try:
            # 首先获取文件信息
            file_info = self.supabase.table("document_files")\
                .select("filename")\
                .eq("id", file_id)\
                .execute()
            
            if not file_info.data:
                return []
            
            filename = file_info.data[0].get("filename")
            
            # 从向量存储中查询相关分块
            from sqlalchemy import create_engine, text
            engine = create_engine(self.supabase_config.postgres_url)
            
            chunks = []
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT document, cmetadata 
                    FROM langchain_pg_embedding 
                    WHERE document LIKE :filename_pattern
                """), {"filename_pattern": f"%{filename}%"})
                
                for row in result:
                    chunk = {
                        "id": row.cmetadata.get("chunk_id", str(uuid.uuid4())),
                        "content": row.document,
                        "metadata": row.cmetadata,
                        "created_at": datetime.now()
                    }
                    chunks.append(chunk)
            
            engine.dispose()
            return chunks
            
        except Exception as e:
            self.logger.error(f"获取文件分块失败: {str(e)}")
            return []
    
    def get_file_content(self, file_id: str) -> Optional[Tuple[str, str, bytes]]:
        """
        获取原始文件内容（支持从Storage或数据库获取）
        
        Args:
            file_id: 文件ID
            
        Returns:
            Tuple[filename, content_type, file_content] 或 None
        """
        try:
            # 使用HybridFileStorage获取文件内容
            result = self.file_storage.get_file_content_sync(file_id)
            
            if result:
                return result
            
            # 如果新方法失败，尝试使用旧的RPC方法作为后备
            try:
                response = self.supabase.rpc("get_file_content", {"file_id_input": file_id}).execute()
                
                if response.data:
                    file_info = response.data[0]
                    import base64
                    file_content = base64.b64decode(file_info["file_content"]) if isinstance(file_info["file_content"], str) else file_info["file_content"]
                    return (
                        file_info["filename"],
                        file_info["content_type"],
                        file_content
                    )
            except Exception as rpc_error:
                self.logger.warning(f"RPC方法获取文件失败: {str(rpc_error)}")
            
            return None
            
        except Exception as e:
            self.logger.error(f"获取文件内容失败: {str(e)}")
            return None
    
    def check_file_exists_by_hash(self, file_content: bytes) -> Optional[str]:
        """
        检查文件是否已存在（基于哈希）
        
        Args:
            file_content: 文件内容
            
        Returns:
            文件ID（如果存在）或 None
        """
        import hashlib
        
        try:
            file_hash = hashlib.sha256(file_content).hexdigest()
            response = self.supabase.rpc("check_file_exists", {"file_hash_input": file_hash}).execute()
            
            if response.data:
                return response.data[0]["file_id"]
            
            return None
            
        except Exception as e:
            self.logger.error(f"检查文件是否存在失败: {str(e)}")
            return None
    
    def delete_chunks_only(self, metadata_id: str) -> bool:
        """
        只删除分块数据（保留原始文件和元数据记录）
        
        Args:
            metadata_id: 分块元数据ID (document_metadata.id)
            
        Returns:
            bool: 是否成功
        """
        try:
            # 1. 获取分块元数据信息
            metadata_info = self.supabase.table("document_metadata")\
                .select("filename")\
                .eq("id", metadata_id)\
                .execute()
            
            if not metadata_info.data:
                self.logger.warning(f"分块元数据不存在: {metadata_id}")
                return False
            
            filename = metadata_info.data[0].get("filename")
            
            # 2. 删除向量存储中的相关分块
            try:
                from sqlalchemy import create_engine, text
                engine = create_engine(self.supabase_config.postgres_url)
                
                with engine.begin() as conn:  # 使用 begin() 确保自动提交事务
                    # 使用cmetadata中的filename和collection_name精确删除
                    collection_name = self.supabase_config.collection_name or "default"
                    result = conn.execute(text("""
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid 
                        AND c.name = :collection_name
                        AND e.cmetadata->>'filename' = :filename
                    """), {
                        "collection_name": collection_name,
                        "filename": filename
                    })
                    
                    self.logger.info(f"删除了 {result.rowcount} 个向量记录（文件: {filename}，知识库: {collection_name}）")
                
                
            except Exception as e:
                self.logger.warning(f"删除向量存储失败: {str(e)}")
            
            # 3. 更新分块元数据，将chunk_count设为0（保留元数据记录和原始文件）
            self.supabase.table("document_metadata")\
                .update({"chunk_count": 0})\
                .eq("id", metadata_id)\
                .execute()
            
            # 4. 更新知识库统计
            kb_name = self.supabase_config.collection_name or "default"
            self._update_knowledge_base_stats(kb_name)
            
            self.logger.info(f"分块已删除（保留原始文件和元数据）: {metadata_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除分块失败: {str(e)}")
            return False
    
    def delete_file_and_chunks(self, file_id: str) -> bool:
        """
        删除原始文件及其关联的所有分块（推荐用于前端）
        
        Args:
            file_id: 文件ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # 1. 获取文件信息
            file_info = self.supabase.table("document_files")\
                .select("filename")\
                .eq("id", file_id)\
                .execute()
            
            if not file_info.data:
                self.logger.warning(f"文件不存在: {file_id}")
                return False
            
            filename = file_info.data[0].get("filename")
            
            # 2. 删除向量存储中的相关分块
            try:
                from sqlalchemy import create_engine, text
                engine = create_engine(self.supabase_config.postgres_url)
                
                with engine.begin() as conn:  # 使用 begin() 确保自动提交事务
                    # 使用cmetadata中的filename和collection_name精确删除
                    collection_name = self.supabase_config.collection_name or "default"
                    result = conn.execute(text("""
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid 
                        AND c.name = :collection_name
                        AND e.cmetadata->>'filename' = :filename
                    """), {
                        "collection_name": collection_name,
                        "filename": filename
                    })
                    
                    self.logger.info(f"删除了 {result.rowcount} 个向量记录（文件: {filename}，知识库: {collection_name}）")
                
                
            except Exception as e:
                self.logger.warning(f"删除向量存储失败: {str(e)}")
            
            # 3. 删除关联的文档元数据
            self.supabase.table("document_metadata")\
                .delete()\
                .eq("file_id", file_id)\
                .execute()
            
            # 4. 删除原始文件
            self.supabase.table("document_files")\
                .delete()\
                .eq("id", file_id)\
                .execute()
            
            # 4. 更新知识库统计
            kb_name = self.supabase_config.collection_name or "default"
            self._update_knowledge_base_stats(kb_name)
            
            self.logger.info(f"文件及其关联分块删除完成: {file_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除文件失败: {str(e)}")
            return False
    
    # 已删除 delete_document 方法，使用更明确的 delete_chunks_only 或 delete_file_and_chunks
    
    def clear_chunks(self) -> bool:
        """清空知识库的所有分块"""
        try:
            # 1. 清空向量存储表
            try:
                # 直接删除documents表中指定collection的所有记录
                from sqlalchemy import create_engine, text
                engine = create_engine(self.supabase_config.postgres_url)
                
                with engine.connect() as conn:
                    # 开始事务
                    trans = conn.begin()
                    try:
                        # 删除向量存储中的文档
                        result = conn.execute(text("""
                            DELETE FROM langchain_pg_embedding 
                            WHERE collection_id IN (
                                SELECT uuid FROM langchain_pg_collection 
                                WHERE name = :collection_name
                            )
                        """), {"collection_name": self.supabase_config.collection_name or "default"})  # 使用动态知识库名称
                        
                        # 提交事务
                        trans.commit()
                        self.logger.info(f"删除了 {result.rowcount} 个向量记录")
                        
                    except Exception as e:
                        trans.rollback()
                        raise e
                
                engine.dispose()
                
            except Exception as e:
                self.logger.warning(f"清空向量存储失败: {str(e)}")
            
            # 2. 清空元数据表
            self.supabase.table("document_metadata")\
                .delete()\
                .eq("collection_name", self.supabase_config.collection_name)\
                .execute()
            
            # 3. 清空文件表
            self.supabase.table("document_files")\
                .delete()\
                .eq("collection_name", self.supabase_config.collection_name)\
                .execute()
            
            # 4. 重新初始化向量存储和检索链以反映清空后的状态
            self._init_retrieval_chain()
            
            # 5. 更新知识库统计
            kb_name = self.supabase_config.collection_name or "default"
            self._update_knowledge_base_stats(kb_name)
            self.logger.info(f"知识库 '{kb_name}' 清空完成")
            return True
            
        except Exception as e:
            self.logger.error(f"清空知识库失败: {str(e)}")
            return False
    
    def get_config(self) -> RAGConfig:
        """获取当前配置"""
        return self.config
    
    def update_config(self, new_config: RAGConfig) -> bool:
        """
        更新配置
        
        Args:
            new_config: 新配置
            
        Returns:
            bool: 是否成功
        """
        try:
            self.config = new_config
            
            # 重新初始化模型
            self.chat_model = self._init_chat_model()
            self.embedding_model = self._init_embedding_model()
            
            # 更新文本分割器
            self.text_splitter = SmartTextSplitter(
                chunk_size=new_config.chunk_size,
                chunk_overlap=new_config.chunk_overlap
            )
            
            # 重新初始化向量存储和检索链
            self._init_vector_store()
            
            self.logger.info("配置更新完成")
            return True
            
        except Exception as e:
            self.logger.error(f"配置更新失败: {str(e)}")
            return False
    
    # 知识库管理方法
    
    def get_files_by_knowledge_base(self, kb_name: str) -> List[Dict[str, Any]]:
        """获取指定知识库的文件列表"""
        try:
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("collection_name", kb_name)\
                .order("created_at", desc=True)\
                .execute()
            
            files = []
            for file_data in response.data:
                # 动态计算chunk_count
                chunk_count = 0
                try:
                    from sqlalchemy import create_engine, text
                    engine = create_engine(self.supabase_config.postgres_url)
                    
                    with engine.connect() as conn:
                        # 使用业务层知识库名称作为collection名称
                        result = conn.execute(text("""
                            SELECT COUNT(*)
                            FROM langchain_pg_embedding e
                            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                            WHERE c.name = :collection_name
                            AND e.cmetadata->>'filename' = :filename
                        """), {
                            "collection_name": kb_name,
                            "filename": file_data['filename']
                        })
                        
                        chunk_count = result.scalar() or 0
                    
                    engine.dispose()
                except Exception as e:
                    self.logger.warning(f"计算分块数量失败: {str(e)}")
                
                file_info = {
                    "id": file_data["id"],
                    "filename": file_data["filename"],
                    "original_filename": file_data["original_filename"],
                    "content_type": file_data["content_type"],
                    "file_size": file_data["file_size"],
                    "file_hash": file_data.get("file_hash", ""),
                    "collection_name": file_data.get("collection_name", kb_name),
                    "chunk_count": chunk_count,
                    "created_at": file_data["created_at"],
                    "updated_at": file_data["updated_at"]
                }
                files.append(file_info)
            
            return files
            
        except Exception as e:
            self.logger.error(f"获取知识库文件列表失败: {str(e)}")
            return []
    
    def get_single_file_info_by_kb(self, file_id: str, kb_name: str) -> Optional[Dict[str, Any]]:
        """获取指定知识库中的单个文件信息"""
        try:
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("id", file_id)\
                .eq("collection_name", kb_name)\
                .execute()
            
            if not response.data:
                return None
            
            file_data = response.data[0]
            
            # 动态计算chunk_count
            chunk_count = 0
            try:
                from sqlalchemy import create_engine, text
                engine = create_engine(self.supabase_config.postgres_url)
                    
                with engine.connect() as conn:
                    # 使用业务层知识库名称作为collection名称
                    result = conn.execute(text("""
                        SELECT COUNT(*)
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = :collection_name
                        AND e.cmetadata->>'filename' = :filename
                    """), {
                        "collection_name": kb_name,
                        "filename": file_data['filename']
                    })
                    
                    chunk_count = result.scalar() or 0
                
                engine.dispose()
                
            except Exception as e:
                self.logger.warning(f"计算分块数量失败: {str(e)}")
            
            return {
                "id": file_data["id"],
                "filename": file_data["filename"],
                "original_filename": file_data["original_filename"],
                "content_type": file_data["content_type"],
                "file_size": file_data["file_size"],
                "file_hash": file_data.get("file_hash", ""),
                "collection_name": file_data.get("collection_name", kb_name),
                "chunk_count": chunk_count,
                "created_at": file_data["created_at"],
                "updated_at": file_data["updated_at"]
            }
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败: {str(e)}")
            return None
    
    def clear_knowledge_base(self, kb_name: str) -> bool:
        """清空指定知识库的所有内容"""
        try:
            self.logger.info(f"开始清空知识库: {kb_name}")
            
            from sqlalchemy import create_engine, text
            engine = create_engine(self.supabase_config.postgres_url)
            
            with engine.connect() as conn:
                trans = conn.begin()
                try:
                    # 1. 删除该知识库的所有向量数据
                    # 直接删除整个collection的数据，实现真正的知识库隔离
                    conn.execute(text("""
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid 
                        AND c.name = :collection_name
                    """), {"collection_name": kb_name})
                    
                    # 2. 删除文档元数据
                    self.supabase.table("document_metadata")\
                        .delete()\
                        .eq("collection_name", kb_name)\
                        .execute()
                    
                    # 3. 删除原始文件
                    self.supabase.table("document_files")\
                        .delete()\
                        .eq("collection_name", kb_name)\
                        .execute()
                    
                    trans.commit()
                    
                except Exception as e:
                    trans.rollback()
                    raise e
            
            engine.dispose()
            
            # 4. 重新初始化检索链以反映清空后的状态
            if hasattr(self, 'vector_store') and self.vector_store:
                self._init_retrieval_chain()
            
            # 5. 更新知识库统计
            self._update_knowledge_base_stats(kb_name)
            
            self.logger.info(f"知识库 {kb_name} 清空完成")
            return True
            
        except Exception as e:
            self.logger.error(f"清空知识库失败: {str(e)}")
            return False
