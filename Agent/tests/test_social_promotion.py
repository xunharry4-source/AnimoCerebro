"""
社交媒体宣传 Agent 测试脚本
演示如何使用宣传 Agent 进行自动化发帖
"""
import asyncio
from datetime import datetime, timezone, timedelta
from Agent.social_promotion_agent import social_promotion_agent, PostContent


async def test_promotion_agent():
    """测试宣传 Agent 功能"""
    
    print("=" * 80)
    print("🚀 Social Media Promotion Agent Test")
    print("=" * 80)
    
    # 1. 查看 Agent 信息
    print("\n📋 Agent Information:")
    info = social_promotion_agent.get_info()
    print(f"  Agent ID: {info['agent_id']}")
    print(f"  Name: {info['name']}")
    print(f"  Status: {info['status']}")
    print(f"  Capabilities: {', '.join(info['capabilities'])}")
    
    # 2. 初始化浏览器
    print("\n🌐 Initializing browser...")
    await social_promotion_agent.initialize_browser(headless=False)
    print("✅ Browser initialized")
    
    # 3. 创建宣传计划
    print("\n📝 Creating promotion plan...")
    content_templates = [
        {
            "title": "Check out our new AI project!",
            "content": "We've built an amazing AI agent system. Check it out! #AI #Innovation #Tech",
            "platform": "x"
        },
        {
            "title": "New AI Framework Released",
            "content": "Excited to share our new AI agent framework with advanced cognitive capabilities. Perfect for developers interested in AI and automation. What do you think? #AI #Programming #OpenSource",
            "platform": "reddit",
            "subreddit": "technology"
        }
    ]
    
    plan_result = social_promotion_agent.create_promotion_plan(
        campaign_name="AI Project Launch",
        platforms=["x", "reddit"],
        target_communities=["technology", "programming", "science"],
        content_templates=content_templates,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=7),
        frequency="daily",
        budget=100.0
    )
    
    if plan_result["success"]:
        plan_id = plan_result["plan_id"]
        print(f"✅ Plan created: {plan_id}")
        print(f"   Campaign: {plan_result['plan']['campaign_name']}")
    else:
        print(f"❌ Failed to create plan: {plan_result.get('error')}")
        return
    
    # 4. 分析社区要求
    print("\n🔍 Analyzing community requirements...")
    for community in ["technology", "programming", "science"]:
        req_result = social_promotion_agent.analyze_community_requirements(community)
        if req_result["success"]:
            print(f"\n   r/{community}:")
            print(f"     Max title length: {req_result['requirements']['max_title_length']}")
            print(f"     Max content length: {req_result['requirements']['max_content_length']}")
            print(f"     Required tags: {', '.join(req_result['requirements']['required_tags'])}")
            print(f"     Posting limit: {req_result['requirements']['posting_frequency_limit']}")
            print(f"     Recommendations:")
            for rec in req_result['recommendations'][:3]:
                print(f"       - {rec}")
    
    # 5. 验证内容
    print("\n✓ Validating content for communities...")
    test_content = PostContent(
        title="Amazing AI Project",
        content="Check out this innovative AI framework! #tech #innovation #AI",
        tags=["tech", "innovation", "AI"]
    )
    
    for community in ["technology", "programming"]:
        validation = social_promotion_agent.validate_content_for_community(test_content, community)
        status = "✓ Valid" if validation["valid"] else "✗ Invalid"
        print(f"   r/{community}: {status}")
        if not validation["valid"]:
            for issue in validation["issues"]:
                print(f"      Issue: {issue}")
    
    # 6. 准备发帖内容
    print("\n📤 Preparing posts...")
    
    # X 平台帖子
    x_post = PostContent(
        content="🚀 Excited to share our new AI agent framework! Built with Python and advanced cognitive capabilities. Perfect for automation and intelligent task handling. Check it out! #AI #Python #Innovation #Tech",
        media_files=[]
    )
    
    # Reddit 帖子
    reddit_posts = [
        {
            "title": "Built an AI Agent Framework with Advanced Cognitive Capabilities",
            "content": "Hi everyone! I wanted to share a project I've been working on - an AI agent framework that implements advanced cognitive architectures.\n\nKey features:\n- Multi-agent coordination\n- Memory management and retrieval\n- Task decomposition and planning\n- Plugin-based architecture\n\nWould love to get your feedback! What features would you like to see?\n\n#tech #innovation #AI #Python",
            "subreddit": "technology",
            "flair": "Discussion"
        },
        {
            "title": "Open Source AI Agent System - Looking for Contributors",
            "content": "Hey programmers! I've developed an AI agent system and I'm looking for contributors to help improve it.\n\nThe system includes:\n- Agent orchestration\n- Tool integration\n- Memory systems\n- Learning capabilities\n\nGreat opportunity to learn about AI and contribute to open source. Link in comments!\n\n#code #programming #opensource #AI",
            "subreddit": "programming",
            "flair": "Project"
        }
    ]
    
    # 7. 安排发帖（这里只是示例，实际需要登录后才能执行）
    print("\n📅 Scheduling posts...")
    posts_to_schedule = [
        {
            "platform": "x",
            "content": x_post.content,
            "media_files": x_post.media_files,
            "schedule_time": None  # None 表示立即发布
        }
    ]
    
    for reddit_post in reddit_posts:
        posts_to_schedule.append({
            "platform": "reddit",
            "title": reddit_post["title"],
            "content": reddit_post["content"],
            "subreddit": reddit_post["subreddit"],
            "flair": reddit_post["flair"],
            "schedule_time": None
        })
    
    schedule_result = await social_promotion_agent.schedule_posts(plan_id, posts_to_schedule)
    if schedule_result["success"]:
        print(f"✅ Scheduled {schedule_result['scheduled_count']} posts")
        if schedule_result['failed_count'] > 0:
            print(f"⚠️  {schedule_result['failed_count']} posts failed (need login)")
    else:
        print(f"❌ Failed to schedule posts: {schedule_result.get('error')}")
    
    # 8. 查看宣传结果
    print("\n📊 Promotion Results:")
    results = social_promotion_agent.get_promotion_results(plan_id=plan_id)
    if results["success"]:
        print(f"   Total posts: {results['total_posts']}")
        print(f"   Successful: {results['successful_posts']}")
        print(f"   Failed: {results['failed_posts']}")
        print(f"   Engagement:")
        metrics = results['engagement_metrics']
        print(f"     - Likes: {metrics.get('likes', 0)}")
        print(f"     - Shares/Retweets: {metrics.get('shares', 0)}")
        print(f"     - Comments: {metrics.get('comments', 0)}")
        print(f"     - Upvotes: {metrics.get('upvotes', 0)}")
    
    # 9. 获取计划详情
    print("\n📋 Plan Details:")
    plan_details = social_promotion_agent.get_plan_details(plan_id)
    if plan_details["success"]:
        print(f"   Campaign: {plan_details['plan']['campaign_name']}")
        print(f"   Status: {plan_details['plan']['status']}")
        print(f"   Platforms: {', '.join(plan_details['plan']['platforms'])}")
        print(f"   Target communities: {', '.join(plan_details['plan']['target_communities'])}")
        print(f"   Posts published: {plan_details['published_posts']}")
        print(f"   Posts failed: {plan_details['failed_posts']}")
    
    # 10. 保存数据
    print("\n💾 Saving data...")
    social_promotion_agent.save_data()
    print("✅ Data saved")
    
    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)
    print("\n💡 Next steps:")
    print("1. Login to X: await social_promotion_agent.login_to_x('username', 'password')")
    print("2. Login to Reddit: await social_promotion_agent.login_to_reddit('username', 'password')")
    print("3. Then re-run the schedule_posts to actually post")
    print("4. View results: social_promotion_agent.get_promotion_results()")
    
    # 保持浏览器打开一段时间
    print("\n🔍 Browser will close in 10 seconds...")
    await asyncio.sleep(10)
    
    # 关闭浏览器
    print("\n👋 Closing browser...")
    await social_promotion_agent.close_browser()
    print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(test_promotion_agent())
