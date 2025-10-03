"""
查询API测试脚本
测试不同的查询场景和参数组合
"""

import sys
import os
from pathlib import Path

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from examples.api_client_example import KnowledgeAPIClient
import json
from typing import Dict, Any


def print_section(title: str):
    """打印分隔符"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(result: Dict[str, Any]):
    """格式化打印查询结果"""
    print(f"\n问题: {result.get('query', 'N/A')}")
    print(f"知识库: {result.get('knowledge_base', 'N/A')}")
    print(f"处理时间: {result.get('processing_time', 0):.2f}秒")
    print(f"\n答案:\n{result.get('answer', 'N/A')}")
    
    sources = result.get('sources', [])
    if sources:
        print(f"\n来源文档 ({len(sources)}个):")
        for i, source in enumerate(sources[:3], 1):  # 只显示前3个
            print(f"\n  [{i}] 来源知识库: {source.get('knowledge_base', source.get('metadata', {}).get('knowledge_base', 'unknown'))}")
            content = source.get('content', '')
            print(f"      内容预览: {content[:100]}...")
    else:
        print("\n来源文档: 无")


def test_health_check(client: KnowledgeAPIClient):
    """测试1: 健康检查和系统状态"""
    print_section("测试1: 系统健康检查")
    
    try:
        health = client.health_check()
        print(f"✅ 系统状态: {health.get('status', 'unknown')}")
        
        stats = health.get('summary', {})
        print(f"\n系统统计:")
        print(f"  - 知识库数量: {stats.get('knowledge_bases_count', 0)}")
        print(f"  - 文件数量: {stats.get('files_count', 0)}")
        print(f"  - 分块数量: {stats.get('chunks_count', 0)}")
        
        # 显示知识库详情
        kb_details = health.get('system_stats', {}).get('knowledge_bases', {}).get('details', [])
        if kb_details:
            print(f"\n知识库详情:")
            for kb in kb_details:
                print(f"  - {kb['name']}: {kb['chunk_count']} 个分块, {kb.get('file_count', 0)} 个文件")
        
        return True
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False


def test_query_default_kb(client: KnowledgeAPIClient):
    """测试2: 查询默认知识库"""
    print_section("测试2: 查询默认知识库 (default)")
    
    questions = [
        "这个文档的主要内容是什么？",
        "有哪些关键信息？",
        "文档中提到了什么技术？"
    ]
    
    for i, question in enumerate(questions, 1):
        try:
            print(f"\n--- 查询 {i}/{len(questions)} ---")
            result = client.query_knowledge_base(
                question=question,
                knowledge_base="default",
                top_k=3
            )
            print_result(result)
        except Exception as e:
            print(f"❌ 查询失败: {e}")


def test_query_specific_kb(client: KnowledgeAPIClient):
    """测试3: 查询指定知识库"""
    print_section("测试3: 查询指定知识库")
    
    # 先获取所有知识库
    try:
        kbs = client.list_knowledge_bases()
        print(f"可用的知识库: {[kb['name'] for kb in kbs]}")
        
        if not kbs:
            print("⚠️ 没有可用的知识库")
            return
        
        # 测试第一个非default的知识库（如果存在）
        for kb in kbs:
            if kb['name'] != 'default':
                kb_name = kb['name']
                print(f"\n测试知识库: {kb_name}")
                
                result = client.query_knowledge_base(
                    question="这个知识库有什么内容？",
                    knowledge_base=kb_name,
                    top_k=3
                )
                print_result(result)
                break
        else:
            print("⚠️ 只有default知识库，跳过此测试")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def test_query_all_kbs(client: KnowledgeAPIClient):
    """测试4: 跨所有知识库查询"""
    print_section("测试4: 跨所有知识库查询")
    
    questions = [
        "所有文档中提到了哪些关键技术？",
        "有哪些重要信息？"
    ]
    
    for i, question in enumerate(questions, 1):
        try:
            print(f"\n--- 跨知识库查询 {i}/{len(questions)} ---")
            result = client.query_all_knowledge_bases(
                question=question,
                top_k=3
            )
            print_result(result)
            
            # 统计来源知识库
            sources = result.get('sources', [])
            if sources:
                kb_sources = {}
                for source in sources:
                    kb = source.get('knowledge_base', source.get('metadata', {}).get('knowledge_base', 'unknown'))
                    kb_sources[kb] = kb_sources.get(kb, 0) + 1
                
                print(f"\n来源知识库统计:")
                for kb, count in kb_sources.items():
                    print(f"  - {kb}: {count} 个文档")
                    
        except Exception as e:
            print(f"❌ 查询失败: {e}")


def test_query_with_different_params(client: KnowledgeAPIClient):
    """测试5: 测试不同参数组合"""
    print_section("测试5: 不同参数组合测试")
    
    question = "文档的主要内容是什么？"
    
    test_cases = [
        {"top_k": 1, "desc": "只返回1个结果"},
        {"top_k": 5, "desc": "返回5个结果"},
        {"top_k": 10, "desc": "返回10个结果"},
    ]
    
    for case in test_cases:
        try:
            print(f"\n--- {case['desc']} (top_k={case['top_k']}) ---")
            result = client.query_knowledge_base(
                question=question,
                knowledge_base="default",
                top_k=case['top_k']
            )
            
            print(f"返回的来源数量: {len(result.get('sources', []))}")
            print(f"处理时间: {result.get('processing_time', 0):.2f}秒")
            print(f"答案长度: {len(result.get('answer', ''))} 字符")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")


def test_query_empty_kb(client: KnowledgeAPIClient):
    """测试6: 查询空知识库"""
    print_section("测试6: 查询空知识库")
    
    try:
        # 尝试查询一个不存在的知识库
        result = client.query_knowledge_base(
            question="测试问题",
            knowledge_base="nonexistent_kb",
            top_k=3
        )
        print_result(result)
        
    except Exception as e:
        print(f"✅ 预期的错误处理: {e}")


def test_search_chunks(client: KnowledgeAPIClient):
    """测试7: 分块搜索功能"""
    print_section("测试7: 分块搜索功能")
    
    try:
        result = client.search_chunks(
            query="技术",
            knowledge_base="default",
            limit=5
        )
        
        print(f"查询: 技术")
        print(f"找到: {result.get('total', 0)} 个相关分块")
        print(f"处理时间: {result.get('processing_time', 0):.2f}秒")
        
        chunks = result.get('chunks', [])
        if chunks:
            print(f"\n前3个分块:")
            for i, chunk in enumerate(chunks[:3], 1):
                content = chunk.get('content', '')
                print(f"\n  [{i}] {content[:100]}...")
                print(f"      来源: {chunk.get('metadata', {}).get('source', 'unknown')}")
        
    except Exception as e:
        print(f"❌ 搜索失败: {e}")


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("           查询API功能测试")
    print("=" * 70)
    
    # 创建客户端
    client = KnowledgeAPIClient("http://localhost:8002")
    
    try:
        # 运行测试
        tests = [
            test_health_check,
            test_query_default_kb,
            test_query_specific_kb,
            test_query_all_kbs,
            test_query_with_different_params,
            test_query_empty_kb,
            test_search_chunks,
        ]
        
        passed = 0
        failed = 0
        
        for test_func in tests:
            try:
                result = test_func(client)
                if result is not False:  # None or True都算通过
                    passed += 1
            except Exception as e:
                print(f"\n❌ 测试异常: {test_func.__name__}")
                print(f"   错误: {e}")
                failed += 1
        
        # 总结
        print_section("测试总结")
        print(f"✅ 完成: {passed} 个测试")
        if failed > 0:
            print(f"❌ 失败: {failed} 个测试")
        print(f"\n总计: {passed + failed} 个测试")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

