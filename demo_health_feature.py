#!/usr/bin/env python3
"""
系统健康监控功能演示脚本

此脚本演示如何调用健康监控API并解析返回数据。
可以直接运行查看示例输出。
"""
import sys
import json
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi.testclient import TestClient
from zentex.web_console.app import create_web_console_app


def demo_health_api():
    """演示健康监控API的使用"""
    
    print("=" * 80)
    print("系统健康监控功能演示")
    print("=" * 80)
    print()
    
    # 创建应用
    print("1️⃣  创建Web控制台应用...")
    app = create_web_console_app()
    client = TestClient(app, raise_server_exceptions=False)
    print("   ✅ 应用创建成功")
    print()
    
    # 调用健康API
    print("2️⃣  调用健康监控API: GET /api/web/health/system")
    response = client.get("/api/web/health/system")
    print(f"   状态码: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ 请求失败: {response.text}")
        return
    
    print("   ✅ 请求成功")
    print()
    
    # 解析数据
    data = response.json()
    
    # 显示整体健康状态
    print("3️⃣  整体健康状态")
    print(f"   状态: {data['overall_health']}")
    print(f"   时间: {data['timestamp']}")
    print()
    
    # 显示Token统计
    print("4️⃣  Token使用统计")
    token_usage = data['token_usage']
    print(f"   总请求次数: {token_usage['total_request_count']}")
    print(f"   输入Tokens: {token_usage['total_input_tokens']:,}")
    print(f"   输出Tokens: {token_usage['total_output_tokens']:,}")
    print(f"   总计Tokens: {token_usage['total_tokens']:,}")
    print()
    
    # 显示Provider详情
    if token_usage['providers']:
        print("5️⃣  LLM Provider详情")
        for i, provider in enumerate(token_usage['providers'], 1):
            print(f"   Provider {i}:")
            print(f"     名称: {provider['provider_name']}")
            print(f"     健康状态: {provider['health_status']}")
            print(f"     请求次数: {provider['request_count']}")
            print(f"     Tokens: {provider['total_tokens']:,}")
            if provider.get('api_base'):
                print(f"     API地址: {provider['api_base']}")
        print()
    
    # 显示模块健康状态
    print("6️⃣  功能模块健康状态")
    modules = data['modules']
    if modules:
        for module in modules:
            status_icon = {
                'healthy': '✅',
                'degraded': '⚠️',
                'unhealthy': '❌',
                'unknown': '❓'
            }.get(module['health_status'], '❓')
            
            print(f"   {status_icon} {module['module_name']}")
            print(f"      状态: {module['health_status']}")
            if module.get('status_message'):
                print(f"      说明: {module['status_message']}")
            if module.get('metrics'):
                metrics_str = ", ".join([f"{k}={v}" for k, v in list(module['metrics'].items())[:3]])
                print(f"      指标: {metrics_str}")
    else:
        print("   ℹ️  暂无模块数据（需要配置runtime）")
    print()
    
    # 显示完整JSON（可选）
    print("7️⃣  完整响应数据（格式化JSON）")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    
    print("=" * 80)
    print("演示完成！")
    print("=" * 80)
    print()
    print("💡 提示：")
    print("   - 在浏览器中访问: http://localhost:8000/console/health")
    print("   - 页面会自动每30秒刷新一次")
    print("   - 可以查看所有模块的实时健康状态")
    print()


if __name__ == "__main__":
    try:
        demo_health_api()
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
