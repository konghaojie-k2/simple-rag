"""智能文本分割工具"""

import re
from typing import List
from ..config.models import Document
from .logger import rag_logger


class SmartTextSplitter:
    """智能文本分割器，支持按段落、句子和字符数分割"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        初始化文本分割器
        
        Args:
            chunk_size: 分块大小
            chunk_overlap: 分块重叠大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.logger = rag_logger
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        分割文档列表
        
        Args:
            documents: 原始文档列表
            
        Returns:
            List[Document]: 分割后的文档列表
        """
        result = []
        
        for doc in documents:
            try:
                chunks = self.split_text(doc.content)
                
                for i, chunk in enumerate(chunks):
                    # 创建新的文档块
                    chunk_metadata = doc.metadata.copy()
                    chunk_metadata.update({
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "chunk_size": len(chunk)
                    })
                    
                    chunk_doc = Document(
                        content=chunk,
                        metadata=chunk_metadata
                    )
                    result.append(chunk_doc)
                    
                self.logger.info(f"文档分割完成: {doc.metadata.get('filename', '未知')}, "
                               f"原长度: {len(doc.content)}, 分块数: {len(chunks)}")
                
            except Exception as e:
                self.logger.error(f"文档分割失败: {str(e)}")
                # 如果分割失败，保留原文档
                result.append(doc)
        
        return result
    
    def split_text(self, text: str) -> List[str]:
        """
        分割文本
        
        Args:
            text: 原始文本
            
        Returns:
            List[str]: 分割后的文本块列表
        """
        if not text or len(text) <= self.chunk_size:
            return [text] if text else []
        
        # 首先尝试按段落分割
        paragraphs = self._split_by_paragraphs(text)
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # 如果单个段落就超过chunk_size，需要进一步分割
            if len(paragraph) > self.chunk_size:
                # 先保存当前chunk（如果有内容）
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # 分割大段落
                sub_chunks = self._split_large_paragraph(paragraph)
                chunks.extend(sub_chunks)
                
            elif len(current_chunk) + len(paragraph) + 1 <= self.chunk_size:
                # 段落可以加入当前chunk
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                    
            else:
                # 当前chunk已满，开始新chunk
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
        
        # 添加最后一个chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # 处理重叠
        if self.chunk_overlap > 0:
            chunks = self._add_overlap(chunks)
        
        return [chunk for chunk in chunks if chunk.strip()]
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割文本"""
        # 按双换行符分割段落
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_large_paragraph(self, paragraph: str) -> List[str]:
        """分割大段落"""
        # 首先尝试按句子分割
        sentences = self._split_by_sentences(paragraph)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(sentence) > self.chunk_size:
                # 单个句子就超过限制，按字符强制分割
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # 强制按字符分割
                for i in range(0, len(sentence), self.chunk_size):
                    chunk = sentence[i:i + self.chunk_size]
                    chunks.append(chunk)
                    
            elif len(current_chunk) + len(sentence) + 1 <= self.chunk_size:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 中英文句子分割正则
        sentence_pattern = r'[.!?。！？；;]\s+'
        sentences = re.split(sentence_pattern, text)
        
        # 处理分割后的句子
        result = []
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if sentence:
                # 为句子添加标点符号（除了最后一个）
                if i < len(sentences) - 1:
                    # 尝试从原文本中找到对应的标点
                    next_start = text.find(sentence) + len(sentence)
                    if next_start < len(text):
                        punct = text[next_start:next_start + 1]
                        if punct in '.!?。！？；;':
                            sentence += punct
                
                result.append(sentence)
        
        return result
    
    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """为文本块添加重叠内容"""
        if len(chunks) <= 1:
            return chunks
        
        overlapped_chunks = []
        
        for i, chunk in enumerate(chunks):
            new_chunk = chunk
            
            # 添加前一个chunk的结尾部分
            if i > 0:
                prev_chunk = chunks[i - 1]
                overlap_text = prev_chunk[-self.chunk_overlap:]
                new_chunk = overlap_text + "\n\n" + new_chunk
            
            # 添加下一个chunk的开始部分
            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                overlap_text = next_chunk[:self.chunk_overlap]
                new_chunk = new_chunk + "\n\n" + overlap_text
            
            overlapped_chunks.append(new_chunk)
        
        return overlapped_chunks