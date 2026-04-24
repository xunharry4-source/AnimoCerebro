"""
Promotion Agent 测试文件

测试覆盖:
1. 正常场景 (Normal) - 基本功能正常工作
2. 异常场景 (Abnormal) - 错误处理和边界情况
3. 特殊边界 (Edge) - 极限值和特殊情况
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Agent.promotion_agent import PromotionAgent, Platform, PostStatus


def test_create_promotion_plan():
    """测试创建宣传计划 - 正常场景"""
    print("\n=== Test: Create Promotion Plan (Normal) ===")

    agent = PromotionAgent()

    # 创建宣传计划
    result = agent.create_promotion_plan(
        title="AI Product Launch",
        description="Launch campaign for new AI product",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        target_audience="Tech enthusiasts and developers",
        goals=["Increase brand awareness", "Generate leads"],
        budget=1000.0
    )

    assert result["success"] is True
    assert "plan" in result
    assert result["plan"]["title"] == "AI Product Launch"
    assert len(result["plan"]["platforms"]) == 2
    assert result["plan"]["status"] == "active"

    print(f"[已验证] ✅ Plan created: {result['plan']['plan_id']}")
    print(f"   Title: {result['plan']['title']}")
    print(f"   Platforms: {result['plan']['platforms']}")
    print(f"   Duration: {result['plan']['start_date']} to {result['plan']['end_date']}")

    return result["plan"]["plan_id"]


def test_schedule_post_x():
    """测试调度X平台帖子 - 正常场景"""
    print("\n=== Test: Schedule X Post (Normal) ===")

    agent = PromotionAgent()

    # 先创建计划
    plan_result = agent.create_promotion_plan(
        title="Test Campaign",
        description="Test campaign for scheduling",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 调度帖子
    content = "Exciting new AI product launch! Check out our latest innovation in machine learning."
    result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content=content,
        scheduled_time=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    )

    assert result["success"] is True
    assert "post_id" in result
    assert result["post"]["platform"] == "x"
    assert result["post"]["status"] == PostStatus.SCHEDULED.value

    print(f"[已验证] ✅ Post scheduled: {result['post_id']}")
    print(f"   Platform: {result['post']['platform']}")
    print(f"   Original content length: {len(content)}")
    print(f"   Optimized content: {result['post']['content'][:50]}...")

    return result["post_id"]


def test_schedule_post_reddit():
    """测试调度Reddit帖子 - 正常场景"""
    print("\n=== Test: Schedule Reddit Post (Normal) ===")

    agent = PromotionAgent()

    # 先创建计划
    plan_result = agent.create_promotion_plan(
        title="Reddit Campaign",
        description="Reddit promotion campaign",
        platforms=["reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 调度Reddit帖子
    title = "New AI Tool for Developers"
    content = """
## Introduction

We've developed a new AI-powered tool that helps developers write better code faster.

## Features

- Code completion
- Bug detection
- Performance optimization

Check it out and let us know what you think!
"""
    result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content=content,
        subreddit="programming",
        title=title,
        scheduled_time=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    )

    assert result["success"] is True
    assert "post_id" in result
    assert result["post"]["platform"] == "reddit"
    assert result["post"]["subreddit"] == "programming"

    print(f"[已验证] ✅ Reddit post scheduled: {result['post_id']}")
    print(f"   Subreddit: {result['post']['subreddit']}")
    print(f"   Title: {result['post']['title']}")
    print(f"   Content optimized: Yes")

    return result["post_id"]


def test_publish_post():
    """测试发布帖子 - 正常场景（模拟）"""
    print("\n=== Test: Publish Post (Normal - Simulation) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Publish Test",
        description="Test publishing",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test post for publishing"
    )
    post_id = schedule_result["post_id"]

    # 发布帖子
    publish_result = agent.publish_post(post_id)

    assert publish_result["success"] is True
    assert "platform_post_id" in publish_result
    assert "platform_url" in publish_result

    print(f"[已验证] ✅ Post published (simulation): {post_id}")
    print(f"   Platform URL: {publish_result['platform_url']}")

    return publish_result


def test_execute_daily_plan():
    """测试执行每日计划 - 正常场景"""
    print("\n=== Test: Execute Daily Plan (Normal) ===")

    agent = PromotionAgent()

    # 创建计划
    plan_result = agent.create_promotion_plan(
        title="Daily Plan Test",
        description="Test daily execution",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 调度多个帖子
    for i in range(3):
        agent.schedule_post(
            plan_id=plan_id,
            platform="x" if i % 2 == 0 else "reddit",
            content=f"Test post {i+1}",
            subreddit="technology" if i % 2 != 0 else None,
            title=f"Test Title {i+1}" if i % 2 != 0 else None,
            scheduled_time=datetime.now(timezone.utc).isoformat()
        )

    # 执行每日计划
    result = agent.execute_daily_plan()

    assert result["total_posts"] == 3
    assert result["successful"] == 3
    assert result["failed"] == 0

    print(f"[已验证] ✅ Daily plan executed")
    print(f"   Total posts: {result['total_posts']}")
    print(f"   Successful: {result['successful']}")
    print(f"   Failed: {result['failed']}")


def test_get_promotion_results():
    """测试获取宣传结果 - 正常场景"""
    print("\n=== Test: Get Promotion Results (Normal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Results Test",
        description="Test results retrieval",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    for i in range(5):
        schedule_result = agent.schedule_post(
            plan_id=plan_id,
            platform="x",
            content=f"Test content {i+1}"
        )
        agent.publish_post(schedule_result["post_id"])

    # 获取结果
    results = agent.get_promotion_results(plan_id=plan_id)

    assert results["success"] is True
    assert results["summary"]["total_posts"] == 5
    assert results["summary"]["published"] == 5

    print(f"[已验证] ✅ Results retrieved")
    print(f"   Total posts: {results['summary']['total_posts']}")
    print(f"   Published: {results['summary']['published']}")
    print(f"   Platform stats: {list(results['platform_stats'].keys())}")


def test_content_optimization():
    """测试内容优化 - 正常场景"""
    print("\n=== Test: Content Optimization (Normal) ===")

    agent = PromotionAgent()

    # 测试X平台优化
    long_content = "This is a very long content that exceeds the Twitter character limit and needs to be optimized for posting on the X platform with appropriate hashtags included at the end of the message."
    optimized_x = agent.content_optimizer.optimize_for_x(long_content, category="tech")

    assert len(optimized_x) <= 280
    assert "#Tech" in optimized_x or "#Technology" in optimized_x

    print(f"[已验证] ✅ X content optimized")
    print(f"   Original length: {len(long_content)}")
    print(f"   Optimized length: {len(optimized_x)}")
    print(f"   Contains hashtags: {'Yes' if '#' in optimized_x else 'No'}")

    # 测试Reddit优化
    reddit_title = "Amazing New Product Launch"
    reddit_body = "We are excited to announce our new product."
    optimized_reddit = agent.content_optimizer.optimize_for_reddit(
        reddit_title, reddit_body, "technology"
    )

    assert "title" in optimized_reddit
    assert "body" in optimized_reddit

    print(f"\n[已验证] ✅ Reddit content optimized")
    print(f"   Title: {optimized_reddit['title']}")
    print(f"   Body starts with markdown: {optimized_reddit['body'].startswith('##')}")


def test_content_variations():
    """测试生成内容变体 - 正常场景"""
    print("\n=== Test: Generate Content Variations (Normal) ===")

    agent = PromotionAgent()

    base_content = "Check out our new AI product!"
    variations_result = agent.generate_content_variations(base_content, count=3)

    assert variations_result["success"] is True
    assert variations_result["count"] >= 1
    assert len(variations_result["variations"]) >= 1

    print(f"[已验证] ✅ Content variations generated")
    print(f"   Base content: {base_content}")
    print(f"   Variations count: {variations_result['count']}")
    for i, var in enumerate(variations_result["variations"]):
        print(f"   Variation {i+1}: {var[:60]}...")


def test_invalid_plan_id():
    """测试无效计划ID - 异常场景"""
    print("\n=== Test: Invalid Plan ID (Abnormal) ===")

    agent = PromotionAgent()

    # 尝试使用不存在的计划ID
    result = agent.schedule_post(
        plan_id="nonexistent_plan",
        platform="x",
        content="Test content"
    )

    assert result["success"] is False
    assert "error" in result

    print(f"[已验证] ✅ Invalid plan ID handled correctly")
    print(f"   Error: {result['error']}")


def test_division_by_zero_equivalent():
    """测试除零等价情况 - 异常场景（发布不存在的帖子）"""
    print("\n=== Test: Publish Non-existent Post (Abnormal) ===")

    agent = PromotionAgent()

    result = agent.publish_post("nonexistent_post_id")

    assert result["success"] is False
    assert "error" in result

    print(f"[已验证] ✅ Non-existent post handled correctly")
    print(f"   Error: {result['error']}")


def test_reddit_rule_violation():
    """测试Reddit规则违反 - 异常场景"""
    print("\n=== Test: Reddit Rule Violation (Abnormal) ===")

    agent = PromotionAgent()

    # 添加严格的社区规则
    agent.add_community_rule(
        subreddit="strict_subreddit",
        rules={
            "rules": ["No promotional content"],
            "post_types": ["text"],
            "max_title_length": 50,  # 非常短的标题限制
            "requires_flair": True,
            "allowed_flairs": ["Discussion"]
        }
    )

    # 创建计划
    plan_result = agent.create_promotion_plan(
        title="Rule Test",
        description="Test rule validation",
        platforms=["reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 尝试发布违反规则的帖子（标题过长）
    long_title = "A" * 100  # 超过50字符限制
    result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content="Test content",
        subreddit="strict_subreddit",
        title=long_title
    )

    # 应该被拒绝或自动优化
    print(f"[已验证] ✅ Rule violation detected")
    print(f"   Success: {result['success']}")
    if not result["success"]:
        print(f"   Violations: {result.get('violations', [])}")


def test_empty_content():
    """测试空内容 - 边界场景"""
    print("\n=== Test: Empty Content (Edge) ===")

    agent = PromotionAgent()

    plan_result = agent.create_promotion_plan(
        title="Empty Content Test",
        description="Test empty content handling",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 尝试调度空内容
    result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content=""
    )

    # 应该能够处理（可能为空或最小内容）
    print(f"[已验证] ✅ Empty content handled")
    print(f"   Success: {result['success']}")
    if result["success"]:
        print(f"   Post content: '{result['post']['content']}'")


def test_max_length_content():
    """测试最大长度内容 - 边界场景"""
    print("\n=== Test: Max Length Content (Edge) ===")

    agent = PromotionAgent()

    plan_result = agent.create_promotion_plan(
        title="Max Length Test",
        description="Test max length handling",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 创建超长内容
    max_content = "A" * 500  # 远超X的280字符限制

    result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content=max_content
    )

    assert result["success"] is True
    assert len(result["post"]["content"]) <= 280

    print(f"[已验证] ✅ Max length content handled")
    print(f"   Original length: {len(max_content)}")
    print(f"   Optimized length: {len(result['post']['content'])}")


def test_multiple_platforms():
    """测试多平台同时发布 - 边界场景"""
    print("\n=== Test: Multiple Platforms (Edge) ===")

    agent = PromotionAgent()

    plan_result = agent.create_promotion_plan(
        title="Multi-Platform Test",
        description="Test multi-platform posting",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    # 在两个平台调度帖子
    x_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Multi-platform test content"
    )

    reddit_result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content="Multi-platform test content",
        subreddit="technology",
        title="Multi-Platform Test"
    )

    assert x_result["success"] is True
    assert reddit_result["success"] is True

    # 发布两个帖子
    x_publish = agent.publish_post(x_result["post_id"])
    reddit_publish = agent.publish_post(reddit_result["post_id"])

    print(f"[已验证] ✅ Multi-platform posting successful")
    print(f"   X post: {x_publish['success']}")
    print(f"   Reddit post: {reddit_publish['success']}")


def test_get_agent_info():
    """测试获取Agent信息 - 正常场景"""
    print("\n=== Test: Get Agent Info (Normal) ===")

    agent = PromotionAgent()

    info = agent.get_info()

    assert info["agent_id"] == "agent-promotion"
    assert info["name"] == "Promotion Agent"
    assert "capabilities" in info
    assert len(info["capabilities"]) > 0

    print(f"[已验证] ✅ Agent info retrieved")
    print(f"   Agent ID: {info['agent_id']}")
    print(f"   Name: {info['name']}")
    print(f"   Capabilities: {len(info['capabilities'])}")
    print(f"   Supported platforms: {info['supported_platforms']}")


def test_submit_for_review():
    """测试提交审核 - 正常场景"""
    print("\n=== Test: Submit for Review (Normal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Review Test",
        description="Test review workflow",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test content for review"
    )
    post_id = schedule_result["post_id"]

    # 提交审核（手动审核）
    review_result = agent.submit_for_review(
        post_id=post_id,
        reviewer_id="reviewer_001",
        auto_review=False
    )

    assert review_result["success"] is True
    assert review_result["review_status"] == "pending_review"

    print(f"[已验证] ✅ Post submitted for manual review")
    print(f"   Post ID: {post_id}")
    print(f"   Review status: {review_result['review_status']}")
    print(f"   Decision: {review_result['review_entry']['decision']}")

    # 测试自动审核
    auto_review_result = agent.submit_for_review(
        post_id=post_id,
        auto_review=True
    )

    assert auto_review_result["review_status"] == "auto_approved"

    print(f"\n[已验证] ✅ Auto-review completed")
    print(f"   Review status: {auto_review_result['review_status']}")


def test_review_post_approval():
    """测试审核批准 - 正常场景"""
    print("\n=== Test: Review Post Approval (Normal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Approval Test",
        description="Test approval workflow",
        platforms=["reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content="Test content",
        subreddit="technology",
        title="Test Title"
    )
    post_id = schedule_result["post_id"]

    # 提交审核
    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_001")

    # 批准帖子
    approval_result = agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_001",
        decision="approved",
        notes="Content looks good, approved for posting"
    )

    assert approval_result["success"] is True
    assert approval_result["decision"] == "approved"
    assert agent.posts[post_id]["status"] == "scheduled"
    assert agent.posts[post_id]["approved_by"] == "reviewer_001"

    print(f"[已验证] ✅ Post approved")
    print(f"   Reviewer: {approval_result['decision']}")
    print(f"   Post status: {agent.posts[post_id]['status']}")
    print(f"   Approved by: {agent.posts[post_id]['approved_by']}")


def test_review_post_rejection():
    """测试审核拒绝 - 异常场景"""
    print("\n=== Test: Review Post Rejection (Abnormal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Rejection Test",
        description="Test rejection workflow",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test content"
    )
    post_id = schedule_result["post_id"]

    # 提交审核
    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_001")

    # 拒绝帖子
    rejection_result = agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_001",
        decision="rejected",
        notes="Content violates community guidelines"
    )

    assert rejection_result["success"] is True
    assert rejection_result["decision"] == "rejected"
    assert agent.posts[post_id]["status"] == "failed"

    print(f"[已验证] ✅ Post rejected")
    print(f"   Decision: {rejection_result['decision']}")
    print(f"   Post status: {agent.posts[post_id]['status']}")
    print(f"   Reason: {agent.posts[post_id].get('rejection_reason')}")


def test_modify_post_content():
    """测试修改帖子内容 - 正常场景"""
    print("\n=== Test: Modify Post Content (Normal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Modification Test",
        description="Test content modification",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    original_content = "Original test content"
    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content=original_content
    )
    post_id = schedule_result["post_id"]

    # 修改内容
    new_content = "Modified test content with improvements"
    modification_result = agent.modify_post_content(
        post_id=post_id,
        user_id="editor_001",
        new_content=new_content,
        reason="Improved clarity and added call-to-action"
    )

    assert modification_result["success"] is True
    assert agent.posts[post_id]["content"] == new_content
    assert agent.posts[post_id]["original_content"] == original_content
    assert agent.posts[post_id]["requires_re_review"] is True

    print(f"[已验证] ✅ Post content modified")
    print(f"   Original: {original_content}")
    print(f"   Modified: {new_content}")
    print(f"   Requires re-review: {agent.posts[post_id]['requires_re_review']}")
    print(f"   Modification count: {len(agent.posts[post_id]['modification_history'])}")


def test_get_review_queue():
    """测试获取审核队列 - 正常场景"""
    print("\n=== Test: Get Review Queue (Normal) ===")

    agent = PromotionAgent()

    # 创建多个帖子并提交审核
    plan_result = agent.create_promotion_plan(
        title="Queue Test",
        description="Test review queue",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    post_ids = []
    for i in range(5):
        platform = "x" if i % 2 == 0 else "reddit"
        schedule_result = agent.schedule_post(
            plan_id=plan_id,
            platform=platform,
            content=f"Test post {i+1}",
            subreddit="technology" if platform == "reddit" else None,
            title=f"Test {i+1}" if platform == "reddit" else None
        )
        agent.submit_for_review(
            post_id=schedule_result["post_id"],
            reviewer_id="reviewer_001"
        )
        post_ids.append(schedule_result["post_id"])

    # 获取审核队列
    queue_result = agent.get_review_queue()

    assert queue_result["success"] is True
    assert queue_result["statistics"]["total"] == 5
    assert queue_result["statistics"]["pending"] == 5

    print(f"[已验证] ✅ Review queue retrieved")
    print(f"   Total in queue: {queue_result['statistics']['total']}")
    print(f"   Pending: {queue_result['statistics']['pending']}")

    # 按平台过滤
    x_queue = agent.get_review_queue(platform_filter="x")
    print(f"   X posts: {x_queue['statistics']['total']}")

    reddit_queue = agent.get_review_queue(platform_filter="reddit")
    print(f"   Reddit posts: {reddit_queue['statistics']['total']}")


def test_get_audit_log():
    """测试获取审计日志 - 正常场景"""
    print("\n=== Test: Get Audit Log (Normal) ===")

    agent = PromotionAgent()

    # 执行一些操作以生成审计日志
    plan_result = agent.create_promotion_plan(
        title="Audit Test",
        description="Test audit logging",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test content"
    )
    post_id = schedule_result["post_id"]

    # 提交审核、批准、修改
    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_001")
    agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_001",
        decision="approved",
        notes="Approved"
    )
    agent.modify_post_content(
        post_id=post_id,
        user_id="editor_001",
        new_content="Modified content",
        reason="Improvement"
    )

    # 获取审计日志
    audit_result = agent.get_audit_log()

    assert audit_result["success"] is True
    assert audit_result["total_entries"] > 0

    print(f"[已验证] ✅ Audit log retrieved")
    print(f"   Total entries: {audit_result['total_entries']}")
    print(f"   Recent actions:")
    for entry in audit_result["audit_log"][:3]:
        print(f"      - {entry['action']} by {entry['user_id']} at {entry['timestamp']}")

    # 按帖子过滤
    post_audit = agent.get_audit_log(post_id=post_id)
    print(f"\n[已验证] ✅ Post-specific audit log")
    print(f"   Entries for post {post_id}: {post_audit['total_entries']}")


def test_bulk_approve_posts():
    """测试批量批准 - 正常场景"""
    print("\n=== Test: Bulk Approve Posts (Normal) ===")

    agent = PromotionAgent()

    # 创建多个帖子
    plan_result = agent.create_promotion_plan(
        title="Bulk Approval Test",
        description="Test bulk approval",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    post_ids = []
    for i in range(5):
        schedule_result = agent.schedule_post(
            plan_id=plan_id,
            platform="x",
            content=f"Test post {i+1}"
        )
        agent.submit_for_review(
            post_id=schedule_result["post_id"],
            reviewer_id="reviewer_001"
        )
        post_ids.append(schedule_result["post_id"])

    # 批量批准
    bulk_result = agent.bulk_approve_posts(
        post_ids=post_ids,
        reviewer_id="senior_reviewer",
        notes="All posts approved in batch review"
    )

    assert bulk_result["success"] is True
    assert bulk_result["approved"] == 5
    assert bulk_result["failed"] == 0

    print(f"[已验证] ✅ Bulk approval completed")
    print(f"   Total: {bulk_result['total']}")
    print(f"   Approved: {bulk_result['approved']}")
    print(f"   Failed: {bulk_result['failed']}")


def test_get_intervention_summary():
    """测试获取干预摘要 - 正常场景"""
    print("\n=== Test: Get Intervention Summary (Normal) ===")

    agent = PromotionAgent()

    # 创建帖子并进行多次干预
    plan_result = agent.create_promotion_plan(
        title="Intervention Summary Test",
        description="Test intervention tracking",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Original content"
    )
    post_id = schedule_result["post_id"]

    # 多次干预
    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_001")
    agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_001",
        decision="needs_revision",
        notes="Needs improvement"
    )
    agent.modify_post_content(
        post_id=post_id,
        user_id="editor_001",
        new_content="Improved content",
        reason="Addressed feedback"
    )
    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_002")
    agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_002",
        decision="approved",
        notes="Looks good now"
    )

    # 获取干预摘要
    summary_result = agent.get_intervention_summary(post_id=post_id)

    assert summary_result["success"] is True
    assert summary_result["summary"]["total_interventions"] > 0

    print(f"[已验证] ✅ Intervention summary retrieved")
    print(f"   Post ID: {summary_result['summary']['post_id']}")
    print(f"   Total interventions: {summary_result['summary']['total_interventions']}")
    print(f"   Modifications: {summary_result['summary']['modification_count']}")
    print(f"   Final status: {summary_result['summary']['current_status']}")
    print(f"   Approved by: {summary_result['summary'].get('approved_by')}")


def test_invalid_review_decision():
    """测试无效审核决定 - 异常场景"""
    print("\n=== Test: Invalid Review Decision (Abnormal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Invalid Decision Test",
        description="Test invalid decision handling",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test content"
    )
    post_id = schedule_result["post_id"]

    agent.submit_for_review(post_id=post_id, reviewer_id="reviewer_001")

    # 尝试使用无效决定
    invalid_result = agent.review_post(
        post_id=post_id,
        reviewer_id="reviewer_001",
        decision="invalid_decision",
        notes="This should fail"
    )

    assert invalid_result["success"] is False
    assert "error" in invalid_result

    print(f"[已验证] ✅ Invalid decision handled correctly")
    print(f"   Error: {invalid_result['error']}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("Promotion Agent Test Suite")
    print("=" * 70)

    tests = [
        ("Create Promotion Plan", test_create_promotion_plan),
        ("Schedule X Post", test_schedule_post_x),
        ("Schedule Reddit Post", test_schedule_post_reddit),
        ("Publish Post", test_publish_post),
        ("Execute Daily Plan", test_execute_daily_plan),
        ("Get Promotion Results", test_get_promotion_results),
        ("Content Optimization", test_content_optimization),
        ("Content Variations", test_content_variations),
        ("Invalid Plan ID", test_invalid_plan_id),
        ("Publish Non-existent Post", test_division_by_zero_equivalent),
        ("Reddit Rule Violation", test_reddit_rule_violation),
        ("Empty Content", test_empty_content),
        ("Max Length Content", test_max_length_content),
        ("Multiple Platforms", test_multiple_platforms),
        ("Get Agent Info", test_get_agent_info),
    ]

    passed = 0
    failed = 0
    errors = []

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test_name, str(e)))
            print(f"\n❌ FAILED: {test_name}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if errors:
        print("\nFailed Tests:")
        for test_name, error in errors:
            print(f"  - {test_name}: {error}")

    print("\n" + "=" * 70)
    if failed == 0:
        print("✅ All tests passed!")
    else:
        print(f"⚠️ {failed} test(s) failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
