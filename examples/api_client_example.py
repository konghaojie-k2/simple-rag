#!/usr/bin/env python3
"""
知识管理API Python客户端示例
演示如何使用Python requests库调用API
"""

import requests
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List


class KnowledgeAPIClient:
    """
    知识库管理客户端
    
    三层架构：知识库 -> 文件 -> 分块
    - 知识库层：管理整个知识库的创建、删除、查询
    - 文件层：管理单个文件的上传、删除、查询
    - 分块层：管理文档分块的处理、删除、查询
    """
    """知识管理API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        """
        初始化API客户端
        
        Args:
            base_url: API服务器地址
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def upload_for_chunks(self, file_path: str, knowledge_base: str = "default") -> Dict[str, Any]:
        """
        上传文件进行分块处理（用于RAG查询，不保存原始文件）
        
        Args:
            file_path: 文件路径
            knowledge_base: 知识库名称
            
        Returns:
            上传响应，包含task_id
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/octet-stream')}
            
            response = self.session.post(
                f"{self.base_url}/api/v1/knowledge-bases/{knowledge_base}/chunks/upload",
                files=files
            )
            response.raise_for_status()
            return response.json()
    
    def upload_file(self, file_path: str, knowledge_base: str = "default") -> Dict[str, Any]:
        """
        上传原始文件（只保存，不分块处理）
        
        Args:
            file_path: 文件路径
            knowledge_base: 知识库名称
            
        Returns:
            上传响应，包含task_id
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/octet-stream')}
            
            response = self.session.post(
                f"{self.base_url}/api/v1/knowledge-bases/{knowledge_base}/files/upload",
                files=files
            )
            response.raise_for_status()
            return response.json()
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
        response.raise_for_status()
        return response.json()
    
    # 知识库管理方法
    
    def list_knowledge_bases(self) -> List[Dict[str, Any]]:
        """
        获取知识库列表
        
        Returns:
            知识库列表
        """
        response = self.session.get(f"{self.base_url}/api/v1/knowledge-bases")
        response.raise_for_status()
        return response.json()
    
    def get_knowledge_base_info(self, kb_name: str) -> Dict[str, Any]:
        """
        获取单个知识库信息
        
        Args:
            kb_name: 知识库名称
            
        Returns:
            知识库详细信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/knowledge-bases/{kb_name}")
        response.raise_for_status()
        return response.json()
    
    def create_knowledge_base(self, name: str, description: str = "") -> Dict[str, Any]:
        """
        创建新知识库
        
        Args:
            name: 知识库名称
            description: 知识库描述
            
        Returns:
            创建结果
        """
        data = {"name": name, "description": description}
        response = self.session.post(f"{self.base_url}/api/v1/knowledge-bases", data=data)
        response.raise_for_status()
        return response.json()
    
    def delete_knowledge_base(self, kb_name: str) -> Dict[str, Any]:
        """
        删除整个知识库（包括所有文件和分块）
        
        Args:
            kb_name: 知识库名称
            
        Returns:
            删除结果
        """
        response = self.session.delete(f"{self.base_url}/api/v1/knowledge-bases/{kb_name}")
        response.raise_for_status()
        return response.json()
    
    def clear_knowledge_base(self, kb_name: str) -> Dict[str, Any]:
        """
        清空知识库内容（保留知识库，删除所有文件和分块）
        
        Args:
            kb_name: 知识库名称
            
        Returns:
            清空结果
        """
        response = self.session.delete(f"{self.base_url}/api/v1/knowledge-bases/{kb_name}/clear")
        response.raise_for_status()
        return response.json()
    
    # 文件管理方法（按知识库）
    
    def list_files_in_kb(self, kb_name: str) -> List[Dict[str, Any]]:
        """
        获取指定知识库的文件列表
        
        Args:
            kb_name: 知识库名称
            
        Returns:
            文件列表
        """
        response = self.session.get(f"{self.base_url}/api/v1/knowledge-bases/{kb_name}/files")
        response.raise_for_status()
        return response.json()
    
    def get_file_info_in_kb(self, kb_name: str, file_id: str) -> Dict[str, Any]:
        """
        获取指定知识库中的单个文件信息
        
        Args:
            kb_name: 知识库名称
            file_id: 文件ID
            
        Returns:
            文件详细信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/knowledge-bases/{kb_name}/files/{file_id}")
        response.raise_for_status()
        return response.json()
    
    # 上传方法（按知识库）
    
    def upload_for_chunks_in_kb(self, kb_name: str, file_path: str) -> Dict[str, Any]:
        """
        上传文件到指定知识库进行分块处理（用于RAG查询，不保存原始文件）
        
        Args:
            kb_name: 知识库名称
            file_path: 文件路径
            
        Returns:
            上传任务信息
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            response = self.session.post(
                f"{self.base_url}/api/v1/knowledge-bases/{kb_name}/chunks/upload",
                files=files
            )
        
        response.raise_for_status()
        return response.json()
    
    def upload_file_in_kb(self, kb_name: str, file_path: str) -> Dict[str, Any]:
        """
        上传原始文件到指定知识库（只保存，不分块处理）
        
        Args:
            kb_name: 知识库名称
            file_path: 文件路径
            
        Returns:
            上传任务信息
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            response = self.session.post(
                f"{self.base_url}/api/v1/knowledge-bases/{kb_name}/files/upload",
                files=files
            )
        
        response.raise_for_status()
        return response.json()
    
    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取任务列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            任务列表
        """
        params = {"limit": limit}
        response = self.session.get(f"{self.base_url}/api/v1/tasks", params=params)
        response.raise_for_status()
        return response.json()
    
    def cleanup_old_tasks(self, days_old: int = 7) -> Dict[str, Any]:
        """
        清理旧任务
        
        Args:
            days_old: 删除多少天前的任务
            
        Returns:
            清理结果
        """
        params = {"days_old": days_old}
        response = self.session.delete(f"{self.base_url}/api/v1/tasks/cleanup", params=params)
        response.raise_for_status()
        return response.json()
    
    def wait_for_task_completion(self, task_id: str, timeout: int = 300) -> Dict[str, Any]:
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
            status = self.get_task_status(task_id)
            
            print(f"任务状态: {status['status']}, 进度: {status['progress']:.1%}, 消息: {status['message']}")
            
            if status['status'] in ['completed', 'failed']:
                return status
            
            time.sleep(2)
        
        raise TimeoutError(f"任务 {task_id} 在 {timeout} 秒内未完成")
    
    def query_knowledge_base(self, question: str, knowledge_base: str = "default", 
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
        
        response = self.session.post(
            f"{self.base_url}/api/v1/query",
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def search_chunks(self, query: str, knowledge_base: str = "default", 
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
        
        response = self.session.post(
            f"{self.base_url}/api/v1/chunks/search",
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def list_chunks(self, knowledge_base: str = "default") -> List[Dict[str, Any]]:
        """
        获取分块列表（有向量分块的文件列表）
        
        Args:
            knowledge_base: 知识库名称
            
        Returns:
            分块列表
        """
        params = {"knowledge_base": knowledge_base}
        
        response = self.session.get(
            f"{self.base_url}/api/v1/chunks",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def download_file(self, file_id: str, save_path: Optional[str] = None) -> str:
        """
        下载原始文件
        
        Args:
            file_id: 文件ID
            save_path: 保存路径（可选）
            
        Returns:
            保存的文件路径
        """
        response = self.session.get(f"{self.base_url}/api/v1/files/{file_id}/download")
        response.raise_for_status()
        
        # 从响应头获取文件名
        content_disposition = response.headers.get('Content-Disposition', '')
        filename = "downloaded_file"
        
        if 'filename=' in content_disposition:
            filename = content_disposition.split('filename=')[1].strip()
        
        # 确定保存路径
        if save_path is None:
            save_path = Path.cwd() / filename
        else:
            save_path = Path(save_path)
            if save_path.is_dir():
                save_path = save_path / filename
        
        # 保存文件
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return str(save_path)
    
    def delete_chunks(self, chunk_metadata_id: str) -> Dict[str, Any]:
        """
        删除分块元数据的所有分块（保留原始文件）
        
        Args:
            chunk_metadata_id: 分块元数据ID
            
        Returns:
            删除结果
        """
        response = self.session.delete(f"{self.base_url}/api/v1/chunks/{chunk_metadata_id}")
        response.raise_for_status()
        return response.json()
    
    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """
        删除原始文件及其关联的所有分块（推荐用于前端）
        
        Args:
            file_id: 文件ID
            
        Returns:
            删除结果
        """
        response = self.session.delete(f"{self.base_url}/api/v1/files/{file_id}")
        response.raise_for_status()
        return response.json()
    
    def list_files(self, knowledge_base: str = "default") -> List[Dict[str, Any]]:
        """
        获取原始文件列表
        
        Args:
            knowledge_base: 知识库名称
            
        Returns:
            文件列表
        """
        params = {"knowledge_base": knowledge_base}
        
        response = self.session.get(
            f"{self.base_url}/api/v1/files",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """
        获取单个文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/files/{file_id}")
        response.raise_for_status()
        return response.json()
    
    def get_chunk_details(self, chunk_metadata_id: str) -> Dict[str, Any]:
        """
        获取指定分块元数据的所有分块详情
        
        Args:
            chunk_metadata_id: 分块元数据ID
            
        Returns:
            分块信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/chunks/{chunk_metadata_id}/details")
        response.raise_for_status()
        return response.json()
    
    def get_file_chunks(self, file_id: str) -> Dict[str, Any]:
        """
        获取指定文件的所有分块
        
        Args:
            file_id: 文件ID
            
        Returns:
            分块信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/files/{file_id}/chunks")
        response.raise_for_status()
        return response.json()
    
    def clear_all_chunks(self, knowledge_base: str = "default") -> Dict[str, Any]:
        """
        清空所有分块
        
        Args:
            knowledge_base: 知识库名称
            
        Returns:
            清空结果
        """
        params = {"knowledge_base": knowledge_base}
        
        response = self.session.delete(
            f"{self.base_url}/api/v1/chunks",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取当前配置
        
        Returns:
            配置信息
        """
        response = self.session.get(f"{self.base_url}/api/v1/config")
        response.raise_for_status()
        return response.json()
    
    def update_config(self, **config_updates) -> Dict[str, Any]:
        """
        更新配置
        
        Args:
            **config_updates: 配置更新项
            
        Returns:
            更新结果
        """
        response = self.session.post(
            f"{self.base_url}/api/v1/config",
            json=config_updates
        )
        response.raise_for_status()
        return response.json()


def main():
    """三层架构演示用法"""
    # 创建API客户端
    client = KnowledgeAPIClient("http://localhost:8001")
    
    print("=== 知识库管理系统三层架构演示 ===")
    print("架构：知识库 -> 文件 -> 分块\n")
    
    try:
        # 1. 健康检查
        print("1. 健康检查...")
        health = client.health_check()
        print(f"服务状态: {health}")
        
        # 2. 获取知识库列表
        print("\n2. 获取知识库列表...")
        kb_list = client.list_knowledge_bases()
        print(f"知识库列表: {kb_list}")
        
        # 3. 上传文档示例（两种方式）
        print("\n3. 上传文档示例...")
        print("两种上传方式:")
        print("  - upload_for_chunks(): 分块处理用于RAG查询，不保存原始文件")
        print("  - upload_file(): 只保存原始文件用于下载，不分块处理")
        
        # 尝试上传一个测试文件（如果存在的话）
        test_files = ["README.md", "test.txt", "demo.pdf", "document.pdf"]
        uploaded_file = None
        
        for test_file in test_files:
            try:
                from pathlib import Path
                if Path(test_file).exists():
                    print(f"找到测试文件: {test_file}")
                    print("尝试上传文档进行分块处理...")
                    
                    upload_result = client.upload_for_chunks(test_file)
                    task_id = upload_result["task_id"]
                    print(f"上传任务已创建: {task_id}")
                    
                    # 等待任务完成
                    final_status = client.wait_for_task_completion(task_id)
                    print(f"上传结果: {final_status['status']}")
                    
                    if final_status['status'] == 'completed':
                        uploaded_file = test_file
                        print(f"✅ 文档上传成功: {test_file}")
                    break
                    
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"上传失败: {str(e)}")
                break
        
        if not uploaded_file:
            print("❌ 未找到可用的测试文件，跳过上传演示")
        
        # 4. 查询知识库
        print("\n4. 查询知识库...")
        try:
            query_result = client.query_knowledge_base("什么是机器学习？")
            print(f"查询结果: {query_result['answer'][:100]}...")
            print(f"来源数量: {len(query_result['sources'])}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500:
                print("知识库为空，请先上传文档")
            else:
                raise
        
        # 5. 搜索分块
        print("\n5. 搜索分块...")
        try:
            search_result = client.search_chunks("机器学习")
            print(f"找到 {search_result['total']} 个相关分块")
            for i, chunk in enumerate(search_result['chunks'][:3]):
                print(f"分块 {i+1}: {chunk['content'][:50]}...")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500:
                print("知识库为空，无法搜索分块")
            else:
                raise
        
        # 6. 获取文档列表
        print("\n6. 获取文档列表...")
        chunks = client.list_chunks()
        print(f"分块文件数量: {len(chunks)}")
        for chunk in chunks[:3]:
            print(f"- {chunk['filename']} ({chunk['chunk_count']} 个分块)")
        
        # 6.5. 获取原始文件列表
        print("\n6.5. 获取原始文件列表...")
        try:
            files = client.list_files()
            print(f"文件数量: {len(files)}")
            for file in files[:3]:
                print(f"- {file['filename']} ({file['file_size']} 字节)")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500:
                print("暂无文件数据")
            else:
                raise
        
        # 7. 删除功能演示
        print("\n7. 删除功能演示...")
        print("两种删除方式:")
        print("  - delete_chunks(): 删除分块元数据和分块（保留原始文件）")
        print("  - delete_file(): 删除原始文件及其关联的所有分块（推荐用于前端）")
        
        # 如果有文档，演示删除功能
        if chunks and len(chunks) > 0:
            print("\n尝试删除功能演示...")
            
            # 获取最后一个文档进行删除演示
            last_chunk = chunks[-1]
            chunk_id = last_chunk['id']
            
            try:
                print(f"准备删除分块: {last_chunk['filename']} (ID: {chunk_id})")
                
                # 用户确认
                print("⚠️  注意: 这将删除文档的元数据和分块，但保留原始文件")
                print("是否继续? (这是演示，实际会执行删除)")
                
                # 为了安全，这里只演示API调用，不实际删除
                print("演示API调用: client.delete_chunks(chunk_metadata_id)")
                print("💡 如需实际删除，请取消注释下面的代码:")
                print("# delete_result = client.delete_chunks(chunk_metadata_id)")
                print("# print(f'删除结果: {delete_result}')")
                
            except Exception as e:
                print(f"删除演示失败: {str(e)}")
        
        # 如果有文件，演示文件删除功能
        if files and len(files) > 0:
            print("\n文件删除演示...")
            last_file = files[-1]
            file_id = last_file['id']
            
            try:
                print(f"准备删除文件: {last_file['filename']} (ID: {file_id})")
                print("⚠️  注意: 这将删除原始文件及其所有关联的分块")
                print("演示API调用: client.delete_file(file_id)")
                print("💡 如需实际删除，请取消注释下面的代码:")
                print("# delete_result = client.delete_file(file_id)")
                print("# print(f'删除结果: {delete_result}')")
                
            except Exception as e:
                print(f"文件删除演示失败: {str(e)}")
        
        if not chunks and not files:
            print("❌ 没有可用的文档或文件进行删除演示")
        
        # 7.5. 详细查询功能演示
        print("\n7.5. 详细查询功能...")
        if chunks:
            # 演示获取第一个文档的分块
            chunk_id = chunks[0]['id']
            try:
                chunk_details = client.get_chunk_details(chunk_id)
                print(f"分块文件 '{chunks[0]['filename']}' 的分块数: {chunk_details['total']}")
                if chunk_details['chunks']:
                    print(f"第一个分块预览: {chunk_details['chunks'][0]['content'][:100]}...")
            except requests.exceptions.HTTPError:
                print("无法获取文档分块")
        
        if files:
            # 演示获取第一个文件的详细信息
            file_id = files[0]['id']
            try:
                file_info = client.get_file_info(file_id)
                print(f"文件详细信息: {file_info['filename']} - {file_info['content_type']}")
                
                file_chunks = client.get_file_chunks(file_id)
                print(f"文件 '{file_info['filename']}' 的分块数: {file_chunks['total']}")
            except requests.exceptions.HTTPError:
                print("无法获取文件详细信息")
        
        # 8. 获取配置
        print("\n8. 获取配置...")
        config = client.get_config()
        print(f"当前模型: {config['chat_model']}")
        print(f"嵌入模型: {config['embedding_model']}")
        
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")


if __name__ == "__main__":
    main()
