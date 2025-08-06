"""文件处理工具"""

import os
from pathlib import Path
from typing import List, Dict, Any
import tempfile

from ..config.models import Document
from .logger import rag_logger


class FileProcessor:
    """文件处理器，支持多种文档格式"""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.doc', '.md'}
    
    def __init__(self):
        self.logger = rag_logger
    
    def is_supported(self, file_path: str) -> bool:
        """检查文件格式是否支持"""
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def process_file(self, file_path: str, **kwargs) -> List[Document]:
        """
        处理单个文件，返回文档列表
        
        Args:
            file_path: 文件路径
            **kwargs: 额外参数
            
        Returns:
            List[Document]: 文档列表
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            if not self.is_supported(str(file_path)):
                raise ValueError(f"不支持的文件格式: {file_path.suffix}")
            
            self.logger.info(f"开始处理文件: {file_path}")
            
            # 根据文件类型调用相应的处理方法
            extension = file_path.suffix.lower()
            
            if extension == '.txt':
                content = self._process_txt(file_path)
            elif extension == '.pdf':
                content = self._process_pdf(file_path)
            elif extension in ['.docx', '.doc']:
                content = self._process_docx(file_path)
            elif extension == '.md':
                content = self._process_markdown(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {extension}")
            
            # 创建文档对象
            metadata = {
                "source": str(file_path),
                "filename": file_path.name,
                "file_type": extension,
                "file_size": file_path.stat().st_size,
            }
            
            document = Document(
                content=content,
                metadata=metadata
            )
            
            self.logger.info(f"文件处理完成: {file_path}, 内容长度: {len(content)}")
            return [document]
            
        except Exception as e:
            self.logger.error(f"文件处理失败: {file_path}, 错误: {str(e)}")
            raise
    
    def process_uploaded_file(self, file_content: bytes, filename: str) -> List[Document]:
        """
        处理上传的文件内容
        
        Args:
            file_content: 文件二进制内容
            filename: 文件名
            
        Returns:
            List[Document]: 文档列表
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            try:
                # 处理临时文件
                documents = self.process_file(temp_file_path)
                
                # 更新元数据中的文件名
                for doc in documents:
                    doc.metadata["filename"] = filename
                    doc.metadata["source"] = filename
                
                return documents
                
            finally:
                # 清理临时文件
                os.unlink(temp_file_path)
                
        except Exception as e:
            self.logger.error(f"上传文件处理失败: {filename}, 错误: {str(e)}")
            raise
    
    def _process_txt(self, file_path: Path) -> str:
        """处理TXT文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
    
    def _process_pdf(self, file_path: Path) -> str:
        """处理PDF文件"""
        try:
            import pypdf
            
            content = []
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    content.append(page.extract_text())
            
            return '\n'.join(content)
            
        except ImportError:
            raise ImportError("处理PDF文件需要安装pypdf: uv add pypdf")
    
    def _process_docx(self, file_path: Path) -> str:
        """处理DOCX文件"""
        try:
            import docx2txt
            return docx2txt.process(str(file_path))
            
        except ImportError:
            raise ImportError("处理DOCX文件需要安装docx2txt: uv add docx2txt")
    
    def _process_markdown(self, file_path: Path) -> str:
        """处理Markdown文件"""
        return self._process_txt(file_path)  # Markdown本质上是文本文件