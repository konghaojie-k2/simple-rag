"""
Session vs 直接请求 - 性能对比测试
"""

import sys
import time
import requests

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8002"

def test_without_session(num_requests=10):
    """不使用session - 每次创建新连接"""
    print(f"\n{'='*60}")
    print(f"测试1: 不使用Session（{num_requests}次请求）")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    for i in range(num_requests):
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print(f"❌ 请求 {i+1} 失败")
    
    elapsed = time.time() - start_time
    avg_time = elapsed / num_requests
    
    print(f"总耗时: {elapsed:.2f}秒")
    print(f"平均耗时: {avg_time:.3f}秒/请求")
    print(f"QPS: {num_requests/elapsed:.2f} 请求/秒")
    
    return elapsed


def test_with_session(num_requests=10):
    """使用session - 复用连接"""
    print(f"\n{'='*60}")
    print(f"测试2: 使用Session（{num_requests}次请求）")
    print(f"{'='*60}")
    
    session = requests.Session()
    
    start_time = time.time()
    
    for i in range(num_requests):
        response = session.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print(f"❌ 请求 {i+1} 失败")
    
    elapsed = time.time() - start_time
    avg_time = elapsed / num_requests
    
    print(f"总耗时: {elapsed:.2f}秒")
    print(f"平均耗时: {avg_time:.3f}秒/请求")
    print(f"QPS: {num_requests/elapsed:.2f} 请求/秒")
    
    session.close()
    return elapsed


def test_session_with_config():
    """展示Session的配置管理优势"""
    print(f"\n{'='*60}")
    print(f"测试3: Session配置管理示例")
    print(f"{'='*60}")
    
    # 创建配置好的session
    session = requests.Session()
    
    # 1. 设置默认headers
    session.headers.update({
        'User-Agent': 'RAG-Test-Client/1.0',
        'Accept-Language': 'zh-CN'
    })
    
    # 2. 设置默认超时
    from functools import partial
    session.request = partial(session.request, timeout=10)
    
    # 3. 配置重试策略
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    print("✅ Session配置完成:")
    print(f"  - 默认User-Agent: {session.headers.get('User-Agent')}")
    print(f"  - 自动重试: 3次")
    print(f"  - 超时设置: 10秒")
    
    # 使用配置好的session
    response = session.get(f"{BASE_URL}/health")
    print(f"\n✅ 请求成功! 状态码: {response.status_code}")
    print(f"  - 实际请求头包含了默认配置")
    
    session.close()


def compare_performance():
    """对比性能"""
    print("\n" + "="*60)
    print("           Session性能对比测试")
    print("="*60)
    
    num_requests = 20
    
    # 测试1: 不用session
    time_without = test_without_session(num_requests)
    
    # 测试2: 用session
    time_with = test_with_session(num_requests)
    
    # 对比结果
    print(f"\n{'='*60}")
    print(f"性能对比总结")
    print(f"{'='*60}")
    
    improvement = ((time_without - time_with) / time_without) * 100
    speedup = time_without / time_with
    
    print(f"不用Session: {time_without:.2f}秒")
    print(f"使用Session: {time_with:.2f}秒")
    print(f"\n性能提升: {improvement:.1f}%")
    print(f"速度倍数: {speedup:.2f}x")
    
    if improvement > 0:
        print(f"\n✅ 使用Session更快!")
    else:
        print(f"\n⚠️ 在少量请求时差异不明显")
    
    # 展示配置管理
    test_session_with_config()


def demonstrate_session_benefits():
    """演示Session的其他好处"""
    print(f"\n{'='*60}")
    print(f"Session的其他好处演示")
    print(f"{'='*60}")
    
    print("\n1️⃣ 连接复用")
    print("   - 避免重复TCP握手")
    print("   - 减少网络延迟")
    print("   - 提高吞吐量")
    
    print("\n2️⃣ 配置管理")
    print("   - 统一headers设置")
    print("   - 统一超时配置")
    print("   - 统一重试策略")
    
    print("\n3️⃣ Cookie管理")
    print("   - 自动保存Cookie")
    print("   - 自动发送Cookie")
    print("   - 适合需要登录的API")
    
    print("\n4️⃣ 认证管理")
    print("   - 统一认证配置")
    print("   - 支持多种认证方式")
    
    print("\n5️⃣ 代理配置")
    print("   - 统一代理设置")
    print("   - 适合企业环境")
    
    print("\n6️⃣ SSL/TLS配置")
    print("   - 自定义证书")
    print("   - 客户端证书")
    
    print("\n7️⃣ 请求钩子")
    print("   - 日志记录")
    print("   - 性能监控")
    print("   - 错误处理")
    
    print("\n8️⃣ 连接池管理")
    print("   - 控制并发数")
    print("   - 资源优化")


def usage_recommendation():
    """使用建议"""
    print(f"\n{'='*60}")
    print(f"使用建议")
    print(f"{'='*60}")
    
    print("\n📌 何时使用Session:")
    print("  ✅ 多次请求同一服务器")
    print("  ✅ 需要统一配置（headers/timeout/auth）")
    print("  ✅ 需要Cookie管理")
    print("  ✅ 需要重试策略")
    print("  ✅ 长时间运行的应用")
    print("  ✅ 高并发场景")
    
    print("\n📌 何时直接用requests:")
    print("  ✅ 单次或少量请求")
    print("  ✅ 简单脚本")
    print("  ✅ 不需要Cookie")
    print("  ✅ 不需要复杂配置")
    
    print("\n💡 最佳实践:")
    print("  1. 应用程序 → 用Session")
    print("  2. 一次性脚本 → 用requests直接调用")
    print("  3. 不确定？ → 用Session，没有坏处")


if __name__ == "__main__":
    # 运行性能对比
    compare_performance()
    
    # 展示其他好处
    demonstrate_session_benefits()
    
    # 使用建议
    usage_recommendation()

