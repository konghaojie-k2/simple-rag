"""RAG MCP服务器启动脚本"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from rag_core import RAGConfig
from .server import create_rag_mcp_server


async def main():
    """主函数"""
    # 加载根目录下的.env文件
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    
    # 从环境变量读取配置
    config = RAGConfig(
        chat_model=os.getenv("DEFAULT_CHAT_MODEL", "qwen3-30b-a3b-2507"),
        embedding_model=os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-v2"),
        base_url=os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        vector_store_path=os.getenv("VECTOR_STORE_PATH", "./vector_stores/default"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        top_k=int(os.getenv("TOP_K", "5")),
        temperature=float(os.getenv("TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("MAX_TOKENS", "2048")),
        http_proxy=os.getenv("HTTP_PROXY"),
        https_proxy=os.getenv("HTTPS_PROXY"),
        no_proxy=os.getenv("NO_PROXY")
    )
    
    # 创建MCP服务器
    rag_server = create_rag_mcp_server(config)
    
    # 运行服务器
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await rag_server.server.run(
            read_stream,
            write_stream,
            rag_server.server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())