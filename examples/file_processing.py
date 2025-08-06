"""
RAG Core SDK 文件处理示例
"""

from pathlib import Path
from rag_core import SimpleRAG, RAGConfig


def create_sample_files():
    """创建示例文件"""
    sample_data_dir = Path("examples/sample_data")
    sample_data_dir.mkdir(exist_ok=True)
    
    # 创建示例文本文件
    with open(sample_data_dir / "python_guide.txt", "w", encoding="utf-8") as f:
        f.write("""
Python编程语言指南

Python是一种解释型、面向对象的高级编程语言。它由Guido van Rossum在1989年底发明，
第一个公开发行版发行于1991年。

Python的特点：
1. 简单易学：Python具有简洁的语法结构
2. 开源免费：Python是开源的，任何人都可以使用
3. 可移植性：Python程序可以在不同的操作系统上运行
4. 丰富的库：Python拥有大量的第三方库

Python的应用领域：
- Web开发：使用Django、Flask等框架
- 数据科学：使用pandas、numpy、matplotlib等库
- 人工智能：使用tensorflow、pytorch、scikit-learn等库
- 自动化运维：编写脚本自动化日常任务
        """)
    
    # 创建示例Markdown文件
    with open(sample_data_dir / "ml_basics.md", "w", encoding="utf-8") as f:
        f.write("""
# 机器学习基础

## 什么是机器学习？

机器学习(Machine Learning, ML)是人工智能(AI)的一个分支，它使计算机系统能够自动学习并改进其性能，而无需明确编程。

## 机器学习的类型

### 1. 监督学习
- 使用标记的训练数据
- 包括分类和回归问题
- 常见算法：线性回归、决策树、支持向量机

### 2. 无监督学习
- 使用未标记的数据
- 寻找数据中的隐藏模式
- 常见算法：聚类、降维、关联规则

### 3. 强化学习
- 通过与环境交互学习
- 基于奖励和惩罚机制
- 应用：游戏AI、机器人控制

## 机器学习的应用

- 图像识别和计算机视觉
- 自然语言处理
- 推荐系统
- 预测分析
- 自动驾驶
        """)
    
    print(f"示例文件已创建在: {sample_data_dir}")
    return sample_data_dir


def main():
    """文件处理示例"""
    
    # 创建示例文件
    sample_data_dir = create_sample_files()
    
    # 1. 创建RAG配置
    config = RAGConfig(
        chat_model="qwen3-30b-a3b-2507",
        embedding_model="text-embedding-v2",
        base_url="http://localhost:8000/v1",
        api_key="your-api-key",
        vector_store_path="./example_file_vector_store",
        chunk_size=800,
        chunk_overlap=200,
        top_k=5
    )
    
    # 2. 创建RAG实例
    rag = SimpleRAG(config)
    
    # 3. 处理文本文件
    txt_file = sample_data_dir / "python_guide.txt"
    if txt_file.exists():
        success = rag.add_documents_from_file(str(txt_file))
        print(f"Python指南文件处理{'成功' if success else '失败'}")
    
    # 4. 处理Markdown文件
    md_file = sample_data_dir / "ml_basics.md"
    if md_file.exists():
        success = rag.add_documents_from_file(str(md_file))
        print(f"机器学习基础文件处理{'成功' if success else '失败'}")
    
    # 5. 查询Python相关问题
    print("\n=== Python相关查询 ===")
    response = rag.query("Python有什么特点？")
    print(f"问题: Python有什么特点？")
    print(f"回答: {response.answer}")
    print(f"参考来源: {len(response.sources)}个")
    
    # 6. 查询机器学习相关问题
    print("\n=== 机器学习相关查询 ===")
    response = rag.query("机器学习有哪些类型？")
    print(f"问题: 机器学习有哪些类型？")
    print(f"回答: {response.answer}")
    print(f"参考来源: {len(response.sources)}个")
    
    # 7. 查询跨文档问题
    print("\n=== 跨文档查询 ===")
    response = rag.query("Python在机器学习中的应用")
    print(f"问题: Python在机器学习中的应用")
    print(f"回答: {response.answer}")
    
    # 8. 显示统计信息
    print(f"\n=== 统计信息 ===")
    print(f"知识库文档块数量: {rag.get_document_count()}")
    
    # 9. 显示详细的源文档信息
    if response.sources:
        print(f"\n=== 最后一次查询的源文档 ===")
        for i, source in enumerate(response.sources, 1):
            metadata = source.get('metadata', {})
            print(f"{i}. 来源: {metadata.get('source', '未知')}")
            print(f"   文件名: {metadata.get('filename', '未知')}")
            print(f"   内容预览: {source.get('content', '')[:100]}...")
            print()


if __name__ == "__main__":
    main()