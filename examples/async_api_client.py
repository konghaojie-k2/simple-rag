#!/usr/bin/env python3
"""
异步知识管理API Python客户端示例
使用aiohttp进行异步HTTP请求
"""

import asyncio
import aiohttp
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List


class AsyncKnowledgeAPIClient:
    """异步知识管理API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8002"):
        """
        初始化异步API客户端
        
        Args:
            base_url: API服务器地址
        """
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        async with self.session.get(f"{self.base_url}/health") as response:
            response.raise_for_status()
            return await response.json()
    
    async def upload_document(self, file_path: str, knowledge_base: str = "default") -> Dict[str, Any]:
        """
        上传文档
        
        Args:
            file_path: 文件路径
            knowledge_base: 知识库名称
            
        Returns:
            上传响应，包含task_id
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        data = aiohttp.FormData()
        data.add_field('knowledge_base', knowledge_base)
        
        with open(file_path, 'rb') as f:
            data.add_field('file', f, filename=file_path.name)
            
            async with self.session.post(
                f"{self.base_url}/api/v1/documents/upload",
                data=data
            ) as response:
                response.raise_for_status()
                return await response.json()
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息
        """
        async with self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}") as response:
            response.raise_for_status()
            return await response.json()
    
    async def wait_for_task_completion(self, task_id: str, timeout: int = 300) -> Dict[str, Any]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
            
        Returns:
            最终任务状态
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.get_task_status(task_id)
            
            print(f"任务状态: {status['status']}, 进度: {status['progress']:.1%}, 消息: {status['message']}")
            
            if status['status'] in ['completed', 'failed']:
                return status
            
            await asyncio.sleep(2)
        
        raise TimeoutError(f"任务 {task_id} 在 {timeout} 秒内未完成")
    
    async def query_knowledge_base(self, question: str, knowledge_base: str = "default", 
                                 top_k: int = 5) -> Dict[str, Any]:
        """
        查询知识库
        
        Args:
            question: 问题
            knowledge_base: 知识库名称
            top_k: 返回结果数量
            
        Returns:
            查询结果
        """
        data = {
            "question": question,
            "knowledge_base": knowledge_base,
            "top_k": top_k
        }
        
        async with self.session.post(
            f"{self.base_url}/api/v1/query",
            json=data
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def search_chunks(self, query: str, knowledge_base: str = "default", 
                          limit: int = 10, threshold: float = 0.7) -> Dict[str, Any]:
        """
        搜索文档分块
        
        Args:
            query: 搜索查询
            knowledge_base: 知识库名称
            limit: 返回数量限制
            threshold: 相似度阈值
            
        Returns:
            搜索结果
        """
        data = {
            "query": query,
            "knowledge_base": knowledge_base,
            "limit": limit,
            "threshold": threshold
        }
        
        async with self.session.post(
            f"{self.base_url}/api/v1/chunks/search",
            json=data
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def list_documents(self, knowledge_base: str = "default") -> List[Dict[str, Any]]:
        """
        获取文档列表
        
        Args:
            knowledge_base: 知识库名称
            
        Returns:
            文档列表
        """
        params = {"knowledge_base": knowledge_base}
        
        async with self.session.get(
            f"{self.base_url}/api/v1/documents",
            params=params
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def batch_query(self, questions: List[str], knowledge_base: str = "default") -> List[Dict[str, Any]]:
        """
        批量查询（并发执行）
        
        Args:
            questions: 问题列表
            knowledge_base: 知识库名称
            
        Returns:
            查询结果列表
        """
        tasks = [
            self.query_knowledge_base(question, knowledge_base)
            for question in questions
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "question": questions[i],
                    "error": str(result),
                    "answer": None
                })
            else:
                processed_results.append(result)
        
        return processed_results


async def main():
    """异步示例用法"""
    async with AsyncKnowledgeAPIClient("http://localhost:8002") as client:
        try:
            # 1. 健康检查
            print("1. 健康检查...")
            health = await client.health_check()
            print(f"服务状态: {health}")
            
            # 2. 批量查询示例
            print("\n2. 批量查询...")
            questions = [
                "什么是机器学习？",
                "深度学习的原理是什么？",
                "人工智能的应用领域有哪些？"
            ]
            
            start_time = time.time()
            results = await client.batch_query(questions)
            end_time = time.time()
            
            print(f"批量查询完成，耗时: {end_time - start_time:.2f}秒")
            
            for i, result in enumerate(results):
                if "error" in result:
                    print(f"问题 {i+1}: {result['question']} - 错误: {result['error']}")
                else:
                    print(f"问题 {i+1}: {result['question']}")
                    print(f"回答: {result['answer'][:100]}...")
                    print()
            
            # 3. 并发搜索分块
            print("\n3. 并发搜索分块...")
            search_queries = ["机器学习", "深度学习", "神经网络"]
            
            search_tasks = [
                client.search_chunks(query)
                for query in search_queries
            ]
            
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            for i, result in enumerate(search_results):
                if isinstance(result, Exception):
                    print(f"搜索 '{search_queries[i]}' 失败: {result}")
                else:
                    print(f"搜索 '{search_queries[i]}': 找到 {result['total']} 个分块")
            
        except aiohttp.ClientError as e:
            print(f"HTTP请求失败: {e}")
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    # 运行异步示例
    asyncio.run(main())
