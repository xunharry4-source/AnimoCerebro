"""
Self-Promotion Agent 使用示例

演示如何使用 Self-Promotion Agent 进行社交媒体推广：
1. 生成周度推广计划
2. 提交人类干预请求
3. 查询审计日志
4. 追踪推广效果
"""

import asyncio
from datetime import datetime, timezone, timedelta


def example_basic_usage():
    """基本使用示例"""
    print("=" * 70)
    print("Self-Promotion Agent - 基本使用示例")
    print("=" * 70)

    from Agent.self_promotion_agent import self_promotion_agent

    # 1. 获取 Agent 信息
    print("\n1️⃣ 获取 Agent 信息...")
    info = self_promotion_agent.get_info()
    print(f"   Agent ID: {info['agent_id']}")
    print(f"   Name: {info['name']}")
    print(f"   Status: {info['status']}")
    print(f"   Capabilities: {', '.join(info['capabilities'])}")
    print(f"   LLM Available: {info['llm_available']}")
    print(f"   Browser Available: {info['browser_available']}")


def example_human_intervention():
    """人类干预请求示例"""
    print("\n" + "=" * 70)
    print("Self-Promotion Agent - 人类干预请求示例")
    print("=" * 70)

    from Agent.self_promotion_agent import self_promotion_agent

    # 2. 提交人类干预请求
    print("\n2️⃣ 提交人类干预请求...")
    result = self_promotion_agent.submit_human_request(
        content="请推广我们的新功能：实时协作编辑功能，支持多人同时编辑文档",
        platform="both",
        priority="high"
    )

    if result["success"]:
        print(f"   ✅ 请求提交成功")
        print(f"   Request ID: {result['request_id']}")
        print(f"   Message: {result['message']}")
    else:
        print(f"   ❌ 请求提交失败: {result.get('error')}")


def example_audit_log():
    """审计日志查询示例"""
    print("\n" + "=" * 70)
    print("Self-Promotion Agent - 审计日志查询示例")
    print("=" * 70)

    from Agent.self_promotion_agent import self_promotion_agent

    # 3. 查询审计日志
    print("\n3️⃣ 查询审计日志...")
    log_result = self_promotion_agent.get_audit_log(limit=5)

    if log_result["success"]:
        print(f"   总日志数: {log_result['total_count']}")
        print(f"\n   最近 5 条日志:")
        for i, log in enumerate(log_result["audit_log"], 1):
            print(f"   {i}. [{log['timestamp']}] {log['action']}")
            print(f"      Trace ID: {log['trace_id'][:20]}...")
    else:
        print(f"   ❌ 查询失败: {log_result.get('error')}")


def example_weekly_plan_generation():
    """周计划生成示例（需要 LLM）"""
    print("\n" + "=" * 70)
    print("Self-Promotion Agent - 周计划生成示例")
    print("=" * 70)

    from Agent.self_promotion_agent import self_promotion_agent, LLM_AVAILABLE

    if not LLM_AVAILABLE:
        print("\n   ⚠️  LLM 服务不可用，跳过此示例")
        print("   提示: 请配置 .env 文件中的 API 密钥以启用 LLM 功能")
        return

    # 4. 生成周计划
    print("\n4️⃣ 生成周度推广计划...")

    project_info = {
        "name": "AnimoCerebro",
        "description": "AI brain for autonomous agents with nine-question cognitive cycle",
        "tech_stack": ["Python", "FastAPI", "React", "TypeScript", "SQLite"],
        "features": [
            "Nine-question cognitive cycle (Q1-Q9)",
            "Autonomous decision making",
            "Plugin system with hot reload",
            "Web console with real-time monitoring",
            "Long-term memory and experience exchange"
        ]
    }

    try:
        result = self_promotion_agent.generate_weekly_plan(
            project_info=project_info,
            target_audience="AI/ML researchers and developers",
            goals=[
                "Increase GitHub stars",
                "Attract contributors",
                "Build community awareness"
            ],
            target_communities=[
                "r/MachineLearning",
                "r/artificial",
                "r/Python",
                "#AI",
                "#MachineLearning"
            ],
            week_start=datetime.now(timezone.utc)
        )

        if result["success"]:
            print(f"   ✅ 周计划生成成功")
            print(f"   Plan ID: {result['plan_id']}")
            print(f"   Title: {result['plan']['title']}")
            print(f"   Days: {len(result['plan']['daily_schedules'])}")

            # 显示第一天的计划
            if result['plan']['daily_schedules']:
                day1 = result['plan']['daily_schedules'][0]
                print(f"\n   第一天计划:")
                print(f"   - Platform: {day1['platform']}")
                print(f"   - Date: {day1['date']}")
                if day1.get('title'):
                    print(f"   - Title: {day1['title'][:50]}...")
                print(f"   - Content Preview: {day1['content'][:80]}...")
        else:
            print(f"   ❌ 计划生成失败: {result.get('error')}")

    except Exception as e:
        print(f"   ❌ 异常: {str(e)}")
        print(f"   提示: 这可能是由于 LLM API 密钥未配置或网络问题")


def example_promotion_tracking():
    """推广效果追踪示例"""
    print("\n" + "=" * 70)
    print("Self-Promotion Agent - 推广效果追踪示例")
    print("=" * 70)

    from Agent.self_promotion_agent import self_promotion_agent

    # 5. 追踪推广效果
    print("\n5️⃣ 追踪推广效果...")

    # 注意：需要先有生成的计划才能追踪
    if not self_promotion_agent.weekly_plans:
        print("   ℹ️  暂无推广计划，请先生成周计划")
        return

    # 获取第一个计划的 ID
    plan_id = list(self_promotion_agent.weekly_plans.keys())[0]

    result = self_promotion_agent.track_promotion_results(plan_id)

    if result["success"]:
        stats = result["results"]
        print(f"   计划 ID: {stats['plan_id']}")
        print(f"   总帖子数: {stats['total_posts']}")
        print(f"   已发布: {stats['published']}")
        print(f"   待发布: {stats['pending']}")
        print(f"   失败: {stats['failed']}")
        print(f"   错误率: {stats['error_rate']:.2%}")
        print(f"   人工干预次数: {stats['human_interventions']}")
    else:
        print(f"   ❌ 追踪失败: {result.get('error')}")


async def example_fastapi_server():
    """FastAPI 服务器测试示例"""
    print("\n" + "=" * 70)
    print("Self-Promotion Agent - FastAPI 服务器测试")
    print("=" * 70)

    import httpx

    base_url = "http://127.0.0.1:9004"

    print(f"\n6️⃣ 测试 FastAPI 服务器 ({base_url})...")

    try:
        async with httpx.AsyncClient() as client:
            # 测试 /status 端点
            print("\n   测试 /status 端点...")
            response = await client.get(f"{base_url}/status")
            if response.status_code == 200:
                status = response.json()
                print(f"   ✅ 状态: {status['status']}")
                print(f"   Agent ID: {status['agent_id']}")
            else:
                print(f"   ❌ 状态检查失败: HTTP {response.status_code}")

            # 测试 /handshake 端点
            print("\n   测试 /handshake 端点...")
            response = await client.post(f"{base_url}/handshake")
            if response.status_code == 200:
                handshake = response.json()
                print(f"   ✅ 握手成功")
                print(f"   Version: {handshake['version']}")
                print(f"   Capabilities: {len(handshake['capabilities'])} available")
            else:
                print(f"   ❌ 握手失败: HTTP {response.status_code}")

            # 测试 /execute 端点
            print("\n   测试 /execute 端点 (submit_human_request)...")
            response = await client.post(
                f"{base_url}/execute",
                json={
                    "task_id": "test-task-001",
                    "action": "submit_human_request",
                    "params": {
                        "content": "Test promotion request from API",
                        "platform": "x",
                        "priority": "normal"
                    }
                }
            )
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ 任务执行成功")
                print(f"   Task ID: {result['task_id']}")
                print(f"   Success: {result['success']}")
            else:
                print(f"   ❌ 任务执行失败: HTTP {response.status_code}")

    except httpx.ConnectError:
        print(f"   ❌ 无法连接到服务器")
        print(f"   提示: 请先运行 ./scripts/start_self_promotion_agent.sh 启动服务器")
    except Exception as e:
        print(f"   ❌ 测试失败: {str(e)}")


def main():
    """主函数 - 运行所有示例"""
    print("\n" + "🚀" * 35)
    print("Self-Promotion Agent 使用示例集合")
    print("🚀" * 35)

    # 运行同步示例
    example_basic_usage()
    example_human_intervention()
    example_audit_log()
    example_weekly_plan_generation()
    example_promotion_tracking()

    # 运行异步示例（FastAPI 测试）
    print("\n" + "=" * 70)
    print("提示: FastAPI 服务器测试需要服务器正在运行")
    print("=" * 70)
    choice = input("\n是否运行 FastAPI 服务器测试? (y/n): ").strip().lower()
    if choice == 'y':
        asyncio.run(example_fastapi_server())

    print("\n" + "=" * 70)
    print("✅ 所有示例运行完成")
    print("=" * 70)
    print("\n下一步:")
    print("1. 配置 LLM API 密钥: 在 .env 文件中设置 GEMINI_API_KEY 或其他提供商密钥")
    print("2. 安装 Playwright: pip install playwright && playwright install chromium")
    print("3. 启动服务器: ./scripts/start_self_promotion_agent.sh")
    print("4. 通过 Zentex 注册 Agent: 使用 Web Console 或 API")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
