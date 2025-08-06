"""
RAG MCP Server 使用示例

注意：这个示例展示了如何配置和启动MCP Server，
实际的MCP工具调用需要通过支持MCP的客户端进行。
"""

import asyncio
import json
from pathlib import Path
from rag_core import RAGConfig
from mcp_server import create_rag_mcp_server


async def demonstrate_mcp_tools():
    """演示MCP工具的使用方法"""
    
    # 1. 创建配置
    config = RAGConfig(
        chat_model="qwen3-30b-a3b-2507",
        embedding_model="text-embedding-v2",
        base_url="http://localhost:8000/v1",
        api_key="your-api-key",
        vector_store_path="./mcp_vector_store",
        chunk_size=1000,
        chunk_overlap=200,
        top_k=5
    )
    
    # 2. 创建MCP服务器
    mcp_server = create_rag_mcp_server(config)
    
    print("RAG MCP服务器已创建")
    print("可用的MCP工具:")
    
    # 3. 列出可用工具（模拟）
    tools = [
        "rag_query - 查询RAG知识库",
        "rag_add_document - 添加文档到RAG知识库", 
        "rag_add_text - 添加文本内容到RAG知识库",
        "rag_get_stats - 获取RAG知识库统计信息",
        "rag_clear - 清空RAG知识库",
        "rag_configure - 配置RAG参数"
    ]
    
    for i, tool in enumerate(tools, 1):
        print(f"{i}. {tool}")
    
    print("\n=== MCP工具调用示例 ===")
    
    # 4. 模拟添加文本内容
    print("1. 添加文本内容到知识库:")
    add_text_args = {
        "content": "RAG（检索增强生成）是一种结合了信息检索和文本生成的AI技术。它首先从知识库中检索相关信息，然后基于这些信息生成回答。",
        "source": "rag_definition",
        "knowledge_base": "default"
    }
    print(f"   参数: {json.dumps(add_text_args, ensure_ascii=False, indent=2)}")
    
    # 实际调用（在真实MCP环境中会通过网络调用）
    try:
        result = await mcp_server._handle_add_text(add_text_args)
        print(f"   结果: {result[0].text}")
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    print("\n2. 查询知识库:")
    query_args = {
        "question": "什么是RAG？",
        "knowledge_base": "default"
    }
    print(f"   参数: {json.dumps(query_args, ensure_ascii=False, indent=2)}")
    
    try:
        result = await mcp_server._handle_query(query_args)
        print(f"   结果: {result[0].text}")
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    print("\n3. 获取统计信息:")
    stats_args = {"knowledge_base": "default"}
    print(f"   参数: {json.dumps(stats_args, ensure_ascii=False, indent=2)}")
    
    try:
        result = await mcp_server._handle_get_stats(stats_args)
        print(f"   结果: {result[0].text}")
    except Exception as e:
        print(f"   错误: {str(e)}")
    
    print("\n=== MCP服务器配置文件示例 ===")
    
    # 5. 生成MCP配置文件示例
    mcp_config = {
        "mcpServers": {
            "rag-server": {
                "command": "python",
                "args": ["-m", "mcp_server.main"],
                "env": {
                    "DEFAULT_CHAT_MODEL": "qwen3-30b-a3b-2507",
                    "DEFAULT_EMBEDDING_MODEL": "text-embedding-v2",
                    "OPENAI_API_BASE": "http://localhost:8000/v1",
                    "OPENAI_API_KEY": "your-api-key",
                    "VECTOR_STORE_PATH": "./vector_stores/default",
                    "CHUNK_SIZE": "1000",
                    "CHUNK_OVERLAP": "200",
                    "TOP_K": "5"
                }
            }
        }
    }
    
    print("将以下配置添加到你的MCP客户端配置中:")
    print(json.dumps(mcp_config, ensure_ascii=False, indent=2))
    
    print("\n=== 启动MCP服务器 ===")
    print("要启动MCP服务器，运行以下命令:")
    print("python -m mcp_server.main")
    print("\n或者使用环境变量:")
    print("OPENAI_API_KEY=your-key python -m mcp_server.main")


def create_mcp_start_script():
    """创建MCP服务器启动脚本"""
    
    # Windows批处理脚本
    bat_content = """@echo off
echo 启动RAG MCP服务器...

REM 设置环境变量（根据需要修改）
set DEFAULT_CHAT_MODEL=qwen3-30b-a3b-2507
set DEFAULT_EMBEDDING_MODEL=text-embedding-v2
set OPENAI_API_BASE=http://localhost:8000/v1
set OPENAI_API_KEY=your-api-key
set VECTOR_STORE_PATH=./vector_stores/default
set CHUNK_SIZE=1000
set CHUNK_OVERLAP=200
set TOP_K=5

REM 启动MCP服务器
python -m mcp_server.main

pause
"""
    
    with open("start_mcp_server.bat", "w", encoding="utf-8") as f:
        f.write(bat_content)
    
    # Shell脚本（Linux/Mac）
    sh_content = """#!/bin/bash
echo "启动RAG MCP服务器..."

# 设置环境变量（根据需要修改）
export DEFAULT_CHAT_MODEL="qwen3-30b-a3b-2507"
export DEFAULT_EMBEDDING_MODEL="text-embedding-v2"
export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="your-api-key"
export VECTOR_STORE_PATH="./vector_stores/default"
export CHUNK_SIZE="1000"
export CHUNK_OVERLAP="200"
export TOP_K="5"

# 启动MCP服务器
python -m mcp_server.main
"""
    
    with open("start_mcp_server.sh", "w", encoding="utf-8") as f:
        f.write(sh_content)
    
    # 设置可执行权限（仅限Unix系统）
    import stat
    try:
        Path("start_mcp_server.sh").chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    except:
        pass
    
    print("MCP服务器启动脚本已创建:")
    print("- Windows: start_mcp_server.bat")
    print("- Linux/Mac: start_mcp_server.sh")


async def main():
    """主函数"""
    await demonstrate_mcp_tools()
    create_mcp_start_script()


if __name__ == "__main__":
    asyncio.run(main())