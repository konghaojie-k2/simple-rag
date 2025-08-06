"""RAG MCP Server实现"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent

from rag_core import SimpleRAG, RAGConfig, Document
from rag_core.utils.logger import rag_logger


class RAGMCPServer:
    """RAG MCP服务器"""
    
    def __init__(self, default_config: Optional[RAGConfig] = None):
        """
        初始化MCP服务器
        
        Args:
            default_config: 默认配置
        """
        self.server = Server("rag-server")
        self.rag_instances: Dict[str, SimpleRAG] = {}
        self.default_config = default_config or RAGConfig()
        self.logger = rag_logger
        
        # 注册工具
        self._register_tools()
        
        self.logger.info("RAG MCP服务器初始化完成")
    
    def _register_tools(self):
        """注册MCP工具"""
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """列出可用工具"""
            return [
                Tool(
                    name="rag_query",
                    description="查询RAG知识库",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "要查询的问题"
                            },
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        },
                        "required": ["question"]
                    }
                ),
                Tool(
                    name="rag_add_document",
                    description="添加文档到RAG知识库",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "文档文件路径"
                            },
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="rag_add_text",
                    description="添加文本内容到RAG知识库",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "要添加的文本内容"
                            },
                            "source": {
                                "type": "string",
                                "description": "内容来源标识",
                                "default": "manual_input"
                            },
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        },
                        "required": ["content"]
                    }
                ),
                Tool(
                    name="rag_get_stats",
                    description="获取RAG知识库统计信息",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        }
                    }
                ),
                Tool(
                    name="rag_clear",
                    description="清空RAG知识库",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        }
                    }
                ),
                Tool(
                    name="rag_configure",
                    description="配置RAG参数",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "config_json": {
                                "type": "string",
                                "description": "JSON格式的配置参数"
                            },
                            "knowledge_base": {
                                "type": "string",
                                "description": "知识库名称",
                                "default": "default"
                            }
                        },
                        "required": ["config_json"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """调用工具"""
            try:
                if name == "rag_query":
                    return await self._handle_query(arguments)
                elif name == "rag_add_document":
                    return await self._handle_add_document(arguments)
                elif name == "rag_add_text":
                    return await self._handle_add_text(arguments)
                elif name == "rag_get_stats":
                    return await self._handle_get_stats(arguments)
                elif name == "rag_clear":
                    return await self._handle_clear(arguments)
                elif name == "rag_configure":
                    return await self._handle_configure(arguments)
                else:
                    raise ValueError(f"未知工具: {name}")
                    
            except Exception as e:
                self.logger.error(f"工具调用失败 {name}: {str(e)}")
                return [TextContent(type="text", text=f"错误: {str(e)}")]
    
    def get_rag_instance(self, knowledge_base: str = "default") -> SimpleRAG:
        """获取或创建RAG实例"""
        if knowledge_base not in self.rag_instances:
            # 为不同知识库创建独立的配置
            config = RAGConfig(
                chat_model=self.default_config.chat_model,
                embedding_model=self.default_config.embedding_model,
                base_url=self.default_config.base_url,
                api_key=self.default_config.api_key,
                vector_store_path=f"./vector_stores/{knowledge_base}",
                chunk_size=self.default_config.chunk_size,
                chunk_overlap=self.default_config.chunk_overlap,
                top_k=self.default_config.top_k,
                temperature=self.default_config.temperature,
                max_tokens=self.default_config.max_tokens
            )
            
            self.rag_instances[knowledge_base] = SimpleRAG(config)
            self.logger.info(f"创建RAG实例: {knowledge_base}")
        
        return self.rag_instances[knowledge_base]
    
    async def _handle_query(self, arguments: dict) -> list[TextContent]:
        """处理查询请求"""
        question = arguments["question"]
        knowledge_base = arguments.get("knowledge_base", "default")
        
        rag = self.get_rag_instance(knowledge_base)
        
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, rag.query, question)
        
        # 格式化响应
        result = {
            "answer": response.answer,
            "sources": response.sources,
            "processing_time": response.processing_time,
            "knowledge_base": knowledge_base
        }
        
        return [TextContent(
            type="text", 
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    async def _handle_add_document(self, arguments: dict) -> list[TextContent]:
        """处理添加文档请求"""
        file_path = arguments["file_path"]
        knowledge_base = arguments.get("knowledge_base", "default")
        
        if not Path(file_path).exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        rag = self.get_rag_instance(knowledge_base)
        
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, rag.add_documents_from_file, file_path)
        
        result = {
            "success": success,
            "file_path": file_path,
            "knowledge_base": knowledge_base,
            "document_count": rag.get_document_count()
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    async def _handle_add_text(self, arguments: dict) -> list[TextContent]:
        """处理添加文本请求"""
        content = arguments["content"]
        source = arguments.get("source", "manual_input")
        knowledge_base = arguments.get("knowledge_base", "default")
        
        rag = self.get_rag_instance(knowledge_base)
        
        # 创建文档对象
        document = Document(
            content=content,
            metadata={"source": source, "type": "text"}
        )
        
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, rag.add_documents, [document])
        
        result = {
            "success": success,
            "content_length": len(content),
            "source": source,
            "knowledge_base": knowledge_base,
            "document_count": rag.get_document_count()
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    async def _handle_get_stats(self, arguments: dict) -> list[TextContent]:
        """处理获取统计信息请求"""
        knowledge_base = arguments.get("knowledge_base", "default")
        
        if knowledge_base in self.rag_instances:
            rag = self.rag_instances[knowledge_base]
            stats = {
                "knowledge_base": knowledge_base,
                "document_count": rag.get_document_count(),
                "config": {
                    "chat_model": rag.config.chat_model,
                    "embedding_model": rag.config.embedding_model,
                    "chunk_size": rag.config.chunk_size,
                    "chunk_overlap": rag.config.chunk_overlap,
                    "top_k": rag.config.top_k
                }
            }
        else:
            stats = {
                "knowledge_base": knowledge_base,
                "document_count": 0,
                "status": "not_initialized"
            }
        
        return [TextContent(
            type="text",
            text=json.dumps(stats, ensure_ascii=False, indent=2)
        )]
    
    async def _handle_clear(self, arguments: dict) -> list[TextContent]:
        """处理清空知识库请求"""
        knowledge_base = arguments.get("knowledge_base", "default")
        
        if knowledge_base in self.rag_instances:
            rag = self.rag_instances[knowledge_base]
            
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, rag.clear_documents)
            
            if success:
                # 删除实例
                del self.rag_instances[knowledge_base]
        else:
            success = True  # 如果实例不存在，认为已经清空
        
        result = {
            "success": success,
            "knowledge_base": knowledge_base,
            "message": "知识库已清空" if success else "清空失败"
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    async def _handle_configure(self, arguments: dict) -> list[TextContent]:
        """处理配置请求"""
        config_json = arguments["config_json"]
        knowledge_base = arguments.get("knowledge_base", "default")
        
        try:
            config_dict = json.loads(config_json)
            
            # 创建新配置
            new_config = RAGConfig(**config_dict)
            
            if knowledge_base in self.rag_instances:
                rag = self.rag_instances[knowledge_base]
                
                # 在线程池中执行同步操作
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, rag.update_config, new_config)
            else:
                # 如果实例不存在，更新默认配置
                if knowledge_base == "default":
                    self.default_config = new_config
                success = True
            
            result = {
                "success": success,
                "knowledge_base": knowledge_base,
                "new_config": config_dict
            }
            
        except Exception as e:
            result = {
                "success": False,
                "knowledge_base": knowledge_base,
                "error": str(e)
            }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]


def create_rag_mcp_server(config: Optional[RAGConfig] = None) -> RAGMCPServer:
    """
    创建RAG MCP服务器
    
    Args:
        config: 默认配置
        
    Returns:
        RAGMCPServer: MCP服务器实例
    """
    return RAGMCPServer(config)