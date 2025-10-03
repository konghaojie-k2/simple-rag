"""
直接使用RESTful方式访问API（不使用session）
"""

import sys
import requests
import json

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# API基础URL
BASE_URL = "http://localhost:8002"

def query_with_requests():
    """方式1: 使用requests直接调用"""
    print("=" * 60)
    print("方式1: 使用 requests 直接调用")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/api/v1/query",
        json={
            "question": "这个文档的主要内容是什么？",
            "knowledge_base": "default",
            "top_k": 3
        },
        timeout=30  # 设置超时
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 查询成功!")
        print(f"问题: {result['query']}")
        print(f"答案: {result['answer'][:200]}...")
        print(f"来源数量: {len(result['sources'])}")
        return result
    else:
        print(f"❌ 查询失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def query_with_urllib():
    """方式2: 使用urllib（Python标准库）"""
    print("\n" + "=" * 60)
    print("方式2: 使用 urllib (标准库)")
    print("=" * 60)
    
    import urllib.request
    import urllib.error
    
    data = {
        "question": "文档中提到了什么技术？",
        "knowledge_base": "default",
        "top_k": 3
    }
    
    json_data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/query",
        data=json_data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✅ 查询成功!")
            print(f"问题: {result['query']}")
            print(f"答案: {result['answer'][:200]}...")
            return result
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP错误: {e.code}")
        print(f"错误信息: {e.read().decode('utf-8')}")
        return None
    except urllib.error.URLError as e:
        print(f"❌ URL错误: {e.reason}")
        return None


def query_cross_kb():
    """测试跨知识库查询"""
    print("\n" + "=" * 60)
    print("测试: 跨知识库查询 (knowledge_base='all')")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/api/v1/query",
        json={
            "question": "所有文档中有哪些关键信息？",
            "knowledge_base": "all",  # 跨所有知识库
            "top_k": 3
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 跨知识库查询成功!")
        print(f"查询范围: {result['knowledge_base']}")
        print(f"答案: {result['answer'][:200]}...")
        
        # 统计来源知识库
        kb_sources = {}
        for source in result['sources']:
            kb = source.get('knowledge_base', 'unknown')
            kb_sources[kb] = kb_sources.get(kb, 0) + 1
        
        print(f"\n来源知识库分布:")
        for kb, count in kb_sources.items():
            print(f"  - {kb}: {count}个文档")
        
        return result
    else:
        print(f"❌ 查询失败: {response.status_code}")
        return None


def test_health_check():
    """测试健康检查"""
    print("\n" + "=" * 60)
    print("测试: 健康检查")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/health")
    
    if response.status_code == 200:
        health = response.json()
        print(f"✅ 系统状态: {health['status']}")
        
        stats = health['summary']
        print(f"\n系统统计:")
        print(f"  - 知识库: {stats['knowledge_bases_count']}个")
        print(f"  - 文件: {stats['files_count']}个")
        print(f"  - 分块: {stats['chunks_count']}个")
        return health
    else:
        print(f"❌ 健康检查失败")
        return None


def test_chunk_search():
    """测试分块搜索"""
    print("\n" + "=" * 60)
    print("测试: 分块搜索")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/api/v1/chunks/search",
        json={
            "query": "技术",
            "knowledge_base": "default",
            "limit": 3
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 搜索成功!")
        print(f"找到: {result['total']}个相关分块")
        print(f"处理时间: {result['processing_time']:.2f}秒")
        
        for i, chunk in enumerate(result['chunks'][:2], 1):
            print(f"\n  [{i}] {chunk['content'][:100]}...")
        
        return result
    else:
        print(f"❌ 搜索失败")
        return None


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("     直接RESTful API访问测试 (不使用session)")
    print("=" * 60)
    
    try:
        # 1. 健康检查
        test_health_check()
        
        # 2. 使用requests直接调用
        query_with_requests()
        
        # 3. 使用urllib（标准库）
        query_with_urllib()
        
        # 4. 跨知识库查询
        query_cross_kb()
        
        # 5. 分块搜索
        test_chunk_search()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

