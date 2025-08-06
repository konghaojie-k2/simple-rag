"""简单RAG流水线实现"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import tempfile
import uuid

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document as LangchainDocument
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

from ..config.models import RAGConfig, RAGResponse, Document, ProcessingProgress
from ..utils.file_processor import FileProcessor
from ..utils.text_splitter import SmartTextSplitter
from ..utils.logger import rag_logger


class SimpleRAG:
    """简单RAG实现类"""
    
    def __init__(self, config: RAGConfig):
        """
        初始化RAG系统
        
        Args:
            config: RAG配置
        """
        self.config = config
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
        
        # 初始化向量存储
        self.vector_store = None
        self.retrieval_chain = None
        
        # 文档存储路径
        self.vector_store_path = Path(config.vector_store_path)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        
        # 加载已有的向量存储（如果存在）
        self._load_existing_vector_store()
        
        self.logger.info("RAG系统初始化完成")
    
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
            model_kwargs = {}
            
            # 阿里云DashScope特殊处理
            if "dashscope" in self.config.base_url.lower():
                model_kwargs["check_embedding_ctx_length"] = False
            
            return ChatOpenAI(
                model=self.config.chat_model,
                openai_api_key=self.config.api_key,
                openai_api_base=self.config.base_url,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
                model_kwargs=model_kwargs
            )
        except Exception as e:
            self.logger.error(f"聊天模型初始化失败: {str(e)}")
            raise
    
    def _init_embedding_model(self) -> OpenAIEmbeddings:
        """初始化嵌入模型"""
        try:
            model_kwargs = {}
            
            # 阿里云DashScope特殊处理
            if "dashscope" in self.config.base_url.lower():
                model_kwargs["check_embedding_ctx_length"] = False
            
            return OpenAIEmbeddings(
                model=self.config.embedding_model,
                openai_api_key=self.config.api_key,
                openai_api_base=self.config.base_url,
                timeout=self.config.timeout,
                model_kwargs=model_kwargs
            )
        except Exception as e:
            self.logger.error(f"嵌入模型初始化失败: {str(e)}")
            raise
    
    def _load_existing_vector_store(self):
        """加载已有的向量存储"""
        try:
            faiss_index_path = self.vector_store_path / "index.faiss"
            faiss_pkl_path = self.vector_store_path / "index.pkl"
            
            if faiss_index_path.exists() and faiss_pkl_path.exists():
                self.vector_store = FAISS.load_local(
                    str(self.vector_store_path),
                    embeddings=self.embedding_model,
                    allow_dangerous_deserialization=True
                )
                self._init_retrieval_chain()
                self.logger.info(f"加载已有向量存储: {self.vector_store_path}")
            else:
                self.logger.info("未找到已有向量存储，将创建新的")
                
        except Exception as e:
            self.logger.warning(f"加载向量存储失败: {str(e)}")
            self.vector_store = None
    
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
    
    def add_documents(self, documents: List[Document]) -> bool:
        """
        添加文档到知识库
        
        Args:
            documents: 文档列表
            
        Returns:
            bool: 是否成功
        """
        try:
            if not documents:
                return False
            
            # 分割文档
            self.logger.info(f"开始处理 {len(documents)} 个文档")
            split_documents = self.text_splitter.split_documents(documents)
            
            # 转换为langchain格式
            langchain_docs = []
            for doc in split_documents:
                langchain_doc = LangchainDocument(
                    page_content=doc.content,
                    metadata=doc.metadata
                )
                langchain_docs.append(langchain_doc)
            
            # 创建或更新向量存储
            if self.vector_store is None:
                self.vector_store = FAISS.from_documents(
                    langchain_docs,
                    embedding=self.embedding_model
                )
                self.logger.info("创建新的向量存储")
            else:
                self.vector_store.add_documents(langchain_docs)
                self.logger.info(f"向现有向量存储添加 {len(langchain_docs)} 个文档块")
            
            # 保存向量存储
            self.vector_store.save_local(str(self.vector_store_path))
            
            # 重新初始化检索链
            self._init_retrieval_chain()
            
            self.logger.info(f"文档添加完成，总计 {len(langchain_docs)} 个文档块")
            return True
            
        except Exception as e:
            self.logger.error(f"添加文档失败: {str(e)}")
            return False
    
    def add_documents_from_file(self, file_path: str) -> bool:
        """
        从文件添加文档
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            documents = self.file_processor.process_file(file_path)
            return self.add_documents(documents)
        except Exception as e:
            self.logger.error(f"从文件添加文档失败: {str(e)}")
            return False
    
    def add_documents_from_uploaded_file(self, file_content: bytes, filename: str) -> bool:
        """
        从上传的文件添加文档
        
        Args:
            file_content: 文件二进制内容
            filename: 文件名
            
        Returns:
            bool: 是否成功
        """
        try:
            documents = self.file_processor.process_uploaded_file(file_content, filename)
            return self.add_documents(documents)
        except Exception as e:
            self.logger.error(f"从上传文件添加文档失败: {str(e)}")
            return False
    
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
    
    def get_document_count(self) -> int:
        """获取文档数量"""
        if not self.vector_store:
            return 0
        try:
            return self.vector_store.index.ntotal
        except:
            return 0
    
    def clear_documents(self) -> bool:
        """清空知识库"""
        try:
            # 删除向量存储文件
            for file_path in self.vector_store_path.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
            
            # 重置向量存储
            self.vector_store = None
            self.retrieval_chain = None
            
            self.logger.info("知识库清空完成")
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
            
            # 如果向量存储路径改变，需要重新加载
            if str(self.vector_store_path) != new_config.vector_store_path:
                self.vector_store_path = Path(new_config.vector_store_path)
                self.vector_store_path.mkdir(parents=True, exist_ok=True)
                self._load_existing_vector_store()
            else:
                # 重新初始化检索链（使用新的聊天模型）
                self._init_retrieval_chain()
            
            self.logger.info("配置更新完成")
            return True
            
        except Exception as e:
            self.logger.error(f"配置更新失败: {str(e)}")
            return False