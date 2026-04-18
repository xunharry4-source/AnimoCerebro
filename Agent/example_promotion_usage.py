"""
Promotion Agent 使用示例

展示如何使用宣传Agent进行自动化社交媒体营销
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Agent.promotion_agent import PromotionAgent


def example_basic_usage():
    """基本使用示例"""
    print("=" * 70)
    print("Example 1: Basic Usage - Create Plan and Schedule Posts")
    print("=" * 70)

    # 创建Agent实例
    agent = PromotionAgent()

    # 1. 创建宣传计划
    plan_result = agent.create_promotion_plan(
        title="AI Product Launch Campaign",
        description="Comprehensive campaign to promote our new AI product",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        target_audience="Developers, tech enthusiasts, and startup founders",
        goals=[
            "Increase brand awareness",
            "Generate 1000+ website visits",
            "Collect 100+ email signups"
        ],
        budget=5000.0
    )

    print(f"\n✅ Plan created: {plan_result['plan']['plan_id']}")
    print(f"   Title: {plan_result['plan']['title']}")
    print(f"   Duration: 30 days")
    print(f"   Platforms: {', '.join(plan_result['plan']['platforms'])}")

    plan_id = plan_result["plan"]["plan_id"]

    # 2. 为X平台调度帖子
    x_posts = [
        "🚀 Excited to announce our new AI-powered code assistant! Boost your productivity with intelligent code completion. #AI #Coding #Productivity",
        "💡 Did you know? Our AI tool can reduce coding time by 40%. Try it today! #DevTools #Innovation",
        "✨ New feature alert: Real-time bug detection and auto-fix suggestions. Game changer for developers! #TechNews"
    ]

    print("\n📝 Scheduling X posts...")
    for i, content in enumerate(x_posts):
        result = agent.schedule_post(
            plan_id=plan_id,
            platform="x",
            content=content,
            scheduled_time=(datetime.now(timezone.utc) + timedelta(hours=i*2)).isoformat()
        )
        print(f"   ✓ Post {i+1} scheduled: {result['post_id']}")

    # 3. 为Reddit调度帖子
    reddit_posts = [
        {
            "subreddit": "programming",
            "title": "We built an AI code assistant that actually understands context",
            "content": """
## Introduction

After 6 months of development, we're excited to share our AI-powered code assistant with the community.

## Key Features

- **Context-aware code completion**: Understands your entire project structure
- **Intelligent bug detection**: Catches issues before they reach production
- **Performance optimization**: Suggests improvements for faster code

## Technical Details

Built with transformer models fine-tuned on millions of code repositories. Supports Python, JavaScript, TypeScript, Go, and Rust.

## Feedback Welcome

We'd love to hear your thoughts and suggestions!
"""
        },
        {
            "subreddit": "startups",
            "title": "From idea to launch: Building an AI dev tool in 6 months",
            "content": """
## The Journey

Started with a simple problem: existing code assistants lack context understanding.

## Challenges Faced

1. Training data quality
2. Model size vs. inference speed
3. User experience design

## Lessons Learned

- Start with a narrow use case
- Get user feedback early and often
- Performance matters more than features

Happy to answer any questions!
"""
        }
    ]

    print("\n📝 Scheduling Reddit posts...")
    for i, post_data in enumerate(reddit_posts):
        result = agent.schedule_post(
            plan_id=plan_id,
            platform="reddit",
            content=post_data["content"],
            subreddit=post_data["subreddit"],
            title=post_data["title"],
            scheduled_time=(datetime.now(timezone.utc) + timedelta(hours=i*4+1)).isoformat()
        )
        print(f"   ✓ Reddit post {i+1} scheduled for r/{post_data['subreddit']}")

    # 4. 查看计划状态
    status = agent.get_plan_status(plan_id)
    print(f"\n📊 Plan Status:")
    print(f"   Total posts: {status['statistics']['total_posts']}")
    print(f"   Scheduled: {status['statistics']['scheduled']}")

    # 5. 执行每日计划（模拟发布）
    print("\n🚀 Executing daily plan...")
    daily_result = agent.execute_daily_plan()
    print(f"   Published: {daily_result['successful']}/{daily_result['total_posts']}")

    # 6. 获取宣传结果
    results = agent.get_promotion_results(plan_id=plan_id)
    print(f"\n📈 Promotion Results:")
    print(f"   Total posts: {results['summary']['total_posts']}")
    print(f"   Published: {results['summary']['published']}")
    print(f"   Failed: {results['summary']['failed']}")

    return plan_id


def example_content_optimization():
    """内容优化示例"""
    print("\n" + "=" * 70)
    print("Example 2: Content Optimization")
    print("=" * 70)

    agent = PromotionAgent()

    # 原始内容
    original_content = """
    We are excited to announce the launch of our revolutionary new artificial intelligence powered development tool that will transform the way developers write code and build applications in the modern software development landscape
    """

    print(f"\n📝 Original content ({len(original_content)} chars):")
    print(f"   {original_content[:80]}...")

    # 为X优化
    optimized_x = agent.content_optimizer.optimize_for_x(original_content, category="tech")
    print(f"\n✨ Optimized for X ({len(optimized_x)} chars):")
    print(f"   {optimized_x}")

    # 为Reddit优化
    reddit_title = "New AI Development Tool Launch"
    optimized_reddit = agent.content_optimizer.optimize_for_reddit(
        reddit_title, original_content, "technology"
    )
    print(f"\n✨ Optimized for Reddit:")
    print(f"   Title: {optimized_reddit['title']}")
    print(f"   Body preview: {optimized_reddit['body'][:100]}...")

    # 生成变体
    variations = agent.generate_content_variations(original_content[:100], count=3)
    print(f"\n🔄 Content Variations:")
    for i, var in enumerate(variations["variations"], 1):
        print(f"   Variant {i}: {var}")


def example_community_rules():
    """社区规则管理示例"""
    print("\n" + "=" * 70)
    print("Example 3: Managing Community Rules")
    print("=" * 70)

    agent = PromotionAgent()

    # 添加新的社区规则
    print("\n📋 Adding community rules for r/MachineLearning...")
    result = agent.add_community_rule(
        subreddit="MachineLearning",
        rules={
            "rules": [
                "Must be ML-related content",
                "No commercial promotions without prior approval",
                "Research posts must include paper links"
            ],
            "post_types": ["link", "text"],
            "max_title_length": 200,
            "requires_flair": True,
            "allowed_flairs": ["Research", "Discussion", "Project", "Question"],
            "min_karma": 100,
            "min_account_age_days": 30
        }
    )
    print(f"   ✓ {result['message']}")

    # 验证帖子是否符合规则
    test_title = "Check out our amazing new ML product!"
    test_content = "We made something cool..."

    if "MachineLearning" in agent.community_rules:
        rule = agent.community_rules["MachineLearning"]
        validation = rule.validate_post(test_title, test_content, "text")

        print(f"\n🔍 Validating post against r/MachineLearning rules:")
        print(f"   Valid: {validation['valid']}")
        if not validation["valid"]:
            print(f"   Violations:")
            for v in validation["violations"]:
                print(f"      - {v}")


def example_analytics():
    """数据分析示例"""
    print("\n" + "=" * 70)
    print("Example 4: Analytics and Reporting")
    print("=" * 70)

    agent = PromotionAgent()

    # 创建测试数据
    plan_result = agent.create_promotion_plan(
        title="Analytics Demo",
        description="Demonstration of analytics capabilities",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 模拟发布和指标更新
    for i in range(5):
        platform = "x" if i % 2 == 0 else "reddit"
        result = agent.schedule_post(
            plan_id=plan_id,
            platform=platform,
            content=f"Test post {i+1}",
            subreddit="technology" if platform == "reddit" else None,
            title=f"Test {i+1}" if platform == "reddit" else None
        )
        agent.publish_post(result["post_id"])

        # 模拟不同的互动指标
        agent.update_post_metrics(result["post_id"], {
            "likes": (i + 1) * 10,
            "comments": (i + 1) * 3,
            "shares": (i + 1) * 2,
            "views": (i + 1) * 100
        })

    # 获取详细分析
    results = agent.get_promotion_results(plan_id=plan_id)

    print(f"\n📊 Campaign Analytics:")
    print(f"   Total Posts: {results['summary']['total_posts']}")
    print(f"   Published: {results['summary']['published']}")
    print(f"\n📈 Engagement Metrics:")
    print(f"   Total Likes: {results['summary']['total_metrics']['likes']}")
    print(f"   Total Comments: {results['summary']['total_metrics']['comments']}")
    print(f"   Total Shares: {results['summary']['total_metrics']['shares']}")
    print(f"   Total Views: {results['summary']['total_metrics']['views']}")

    print(f"\n📱 Platform Breakdown:")
    for platform, stats in results["platform_stats"].items():
        print(f"\n   {platform.upper()}:")
        print(f"      Posts: {stats['total']}")
        print(f"      Likes: {stats['metrics']['likes']}")
        print(f"      Comments: {stats['metrics']['comments']}")
        print(f"      Views: {stats['metrics']['views']}")


def main():
    """运行所有示例"""
    print("\n" + "=" * 70)
    print("Promotion Agent - Usage Examples")
    print("=" * 70)

    try:
        # 运行示例
        example_basic_usage()
        example_content_optimization()
        example_community_rules()
        example_analytics()

        print("\n" + "=" * 70)
        print("✅ All examples completed successfully!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
