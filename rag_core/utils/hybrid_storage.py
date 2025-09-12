"""
混合文件存储方案
小文件使用数据库存储，大文件使用Supabase Storage
"""

import hashlib
from pathlib import Path
from typing import Optional, Tuple, Union
from supabase import Client

from ..utils.logger import rag_logger


class HybridFileStorage:
    """混合文件存储管理器"""
    
    # 1MB阈值：小于此大小使用数据库存储，大于此大小使用Storage
    SIZE_THRESHOLD = 1024 * 1024  
    
    def __init__(self, supabase_client: Client, bucket_name: str = "documents"):
        """
        初始化混合存储
        
        Args:
            supabase_client: Supabase客户端
            bucket_name: Storage bucket名称
        """
        self.supabase = supabase_client
        self.bucket_name = bucket_name
        self.logger = rag_logger
        
        # 确保bucket存在
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """确保Storage bucket存在"""
        try:
            # 尝试获取bucket信息
            self.supabase.storage.get_bucket(self.bucket_name)
        except Exception:
            try:
                # bucket不存在，创建它
                self.supabase.storage.create_bucket(
                    self.bucket_name,
                    options={"public": False}  # 私有bucket
                )
                self.logger.info(f"创建Storage bucket: {self.bucket_name}")
            except Exception as e:
                self.logger.warning(f"创建bucket失败，将使用数据库存储: {e}")
    
    def should_use_storage(self, file_size: int) -> bool:
        """判断是否应该使用Storage存储"""
        return file_size > self.SIZE_THRESHOLD
    
    async def store_file(self, file_content: bytes, filename: str, 
                        collection_name: str = "default") -> dict:
        """
        存储文件（自动选择存储方式）
        
        Args:
            file_content: 文件内容
            filename: 文件名
            collection_name: 集合名称
            
        Returns:
            文件信息字典
        """
        file_size = len(file_content)
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # 检查文件是否已存在
        existing = await self._check_file_exists(file_hash)
        if existing:
            self.logger.info(f"文件已存在: {filename}")
            return existing
        
        file_info = {
            "filename": filename,
            "original_filename": filename,
            "content_type": self._guess_content_type(filename),
            "file_size": file_size,
            "file_hash": file_hash,
            "collection_name": collection_name,
            "metadata": {"upload_source": "hybrid_storage"}
        }
        
        if self.should_use_storage(file_size):
            # 大文件：使用Storage
            storage_path = await self._store_in_storage(file_content, filename, file_hash)
            file_info.update({
                "storage_path": storage_path,
                "file_content": None  # 不存储在数据库中
            })
            self.logger.info(f"大文件存储到Storage: {filename} ({file_size} bytes)")
        else:
            # 小文件：使用数据库
            file_info.update({
                "storage_path": None,
                "file_content": file_content
            })
            self.logger.info(f"小文件存储到数据库: {filename} ({file_size} bytes)")
        
        # 插入文件记录
        result = self.supabase.table("document_files").insert(file_info).execute()
        return result.data[0]
    
    async def _store_in_storage(self, file_content: bytes, filename: str, 
                              file_hash: str) -> str:
        """将文件存储到Supabase Storage"""
        # 使用哈希作为文件路径，避免重复和冲突
        file_extension = Path(filename).suffix
        storage_path = f"{file_hash[:2]}/{file_hash}{file_extension}"
        
        try:
            # 上传到Storage
            self.supabase.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_content,
                file_options={
                    "content-type": self._guess_content_type(filename),
                    "cache-control": "3600"  # 1小时缓存
                }
            )
            return storage_path
        except Exception as e:
            self.logger.error(f"Storage上传失败: {e}")
            raise
    
    async def get_file_content(self, file_id: str) -> Optional[Tuple[str, str, bytes]]:
        """
        获取文件内容
        
        Args:
            file_id: 文件ID
            
        Returns:
            (filename, content_type, file_content) 或 None
        """
        try:
            # 获取文件信息
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("id", file_id)\
                .execute()
            
            if not response.data:
                return None
            
            file_info = response.data[0]
            
            if file_info.get("storage_path"):
                # 从Storage下载
                content = await self._download_from_storage(file_info["storage_path"])
            else:
                # 从数据库获取
                content = file_info["file_content"]
            
            return (
                file_info["filename"],
                file_info["content_type"],
                content
            )
            
        except Exception as e:
            self.logger.error(f"获取文件内容失败: {e}")
            return None
    
    async def get_download_url(self, file_id: str, expires_in: int = 3600) -> Optional[str]:
        """
        获取文件下载URL（优化版本）
        
        Args:
            file_id: 文件ID
            expires_in: URL过期时间（秒）
            
        Returns:
            下载URL或None
        """
        try:
            # 获取文件信息
            response = self.supabase.table("document_files")\
                .select("storage_path", "filename", "content_type")\
                .eq("id", file_id)\
                .execute()
            
            if not response.data:
                return None
            
            file_info = response.data[0]
            
            if file_info.get("storage_path"):
                # 大文件：返回Storage的签名URL
                signed_url = self.supabase.storage.from_(self.bucket_name)\
                    .create_signed_url(file_info["storage_path"], expires_in)
                return signed_url["signedURL"]
            else:
                # 小文件：返回API端点URL（需要通过应用服务器）
                return f"/api/v1/documents/{file_id}/download"
                
        except Exception as e:
            self.logger.error(f"获取下载URL失败: {e}")
            return None
    
    async def _download_from_storage(self, storage_path: str) -> bytes:
        """从Storage下载文件"""
        try:
            response = self.supabase.storage.from_(self.bucket_name)\
                .download(storage_path)
            return response
        except Exception as e:
            self.logger.error(f"Storage下载失败: {e}")
            raise
    
    async def _check_file_exists(self, file_hash: str) -> Optional[dict]:
        """检查文件是否已存在"""
        try:
            response = self.supabase.table("document_files")\
                .select("*")\
                .eq("file_hash", file_hash)\
                .execute()
            
            return response.data[0] if response.data else None
        except Exception:
            return None
    
    def _guess_content_type(self, filename: str) -> str:
        """根据文件扩展名猜测MIME类型"""
        extension = Path(filename).suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
        }
        return content_types.get(extension, 'application/octet-stream')
    
    async def cleanup_orphaned_files(self) -> int:
        """清理孤立文件"""
        try:
            # 获取Storage中的孤立文件
            storage_files = self.supabase.storage.from_(self.bucket_name).list()
            db_paths = self.supabase.table("document_files")\
                .select("storage_path")\
                .not_.is_("storage_path", None)\
                .execute()
            
            db_paths_set = {item["storage_path"] for item in db_paths.data}
            orphaned_count = 0
            
            for file_obj in storage_files:
                if file_obj["name"] not in db_paths_set:
                    # 删除孤立文件
                    self.supabase.storage.from_(self.bucket_name)\
                        .remove([file_obj["name"]])
                    orphaned_count += 1
            
            self.logger.info(f"清理了 {orphaned_count} 个孤立文件")
            return orphaned_count
            
        except Exception as e:
            self.logger.error(f"清理孤立文件失败: {e}")
            return 0
