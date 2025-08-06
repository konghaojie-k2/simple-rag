"""
RAG Core SDK 基本使用示例
"""

from pathlib import Path
from rag_core import SimpleRAG, RAGConfig, Document


def main():
    """基本使用示例"""
    
    # 1. 创建配置
    config = RAGConfig(
        chat_model="qwen3-30b-a3b-2507",
        embedding_model="text-embedding-v2",
        base_url="http://localhost:8000/v1",
        api_key="your-api-key",
        vector_store_path="./example_vector_store",
        chunk_size=500,
        chunk_overlap=100,
        top_k=3
    )
    
    # 2. 创建RAG实例
    rag = SimpleRAG(config)
    
    # 3. 添加文本内容
    document = Document(
        content="""
        Python是一种广泛使用的高级编程语言，由Guido van Rossum于1989年首次发布。
        Python具有简洁、易读的语法，被广泛应用于Web开发、数据科学、人工智能等领域。
        Python的设计哲学强调代码的可读性和简洁的语法，特别是使用空格缩进划分代码块。
        """,
        metadata={"source": "python_intro", "type": "manual"}
    )
    
    success = rag.add_documents([document])
    print(f"文档添加{'成功' if success else '失败'}")
    
    # 4. 查询
    response = rag.query("Python是什么？")
    print(f"问题: Python是什么？")
    print(f"回答: {response.answer}")
    print(f"处理时间: {response.processing_time:.2f}秒")
    print(f"参考来源数量: {len(response.sources)}")
    
    # 5. 添加更多内容
    document2 = Document(
        content="""
        机器学习是人工智能的一个重要分支，它使计算机能够在没有明确编程的情况下学习。
        机器学习算法通过训练数据来构建数学模型，以便对新数据做出预测或决策。
        常见的机器学习算法包括线性回归、决策树、神经网络等。
        """,
        metadata={"source": "ml_intro", "type": "manual"}
    )
    
    rag.add_documents([document2])
    
    # 6. 查询机器学习相关问题
    response2 = rag.query("什么是机器学习？")
    print(f"\n问题: 什么是机器学习？")
    print(f"回答: {response2.answer}")
    
    # 7. 获取统计信息
    print(f"\n知识库统计:")
    print(f"文档块数量: {rag.get_document_count()}")
    
    # 8. 清空知识库
    # rag.clear_documents()
    # print("知识库已清空")


if __name__ == "__main__":
    main()