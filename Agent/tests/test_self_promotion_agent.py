"""
Self-Promotion Agent 单元测试

测试覆盖：
1. 正常场景 - Agent 初始化、信息获取
2. 异常场景 - LLM 不可用时的降级处理
3. 边界场景 - 空输入、无效参数处理
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch


class TestSelfPromotionAgentInit:
    """测试 Agent 初始化"""

    def test_agent_init_normal(self):
        """正常场景：Agent 成功初始化"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        assert agent.agent_id == "agent-self-promotion"
        assert agent.name == "Self-Promotion Agent"
        assert agent.status == "active"
        assert len(agent.capabilities) > 0
        assert "generate_weekly_plan" in agent.capabilities
        assert agent.weekly_plans == {}
        assert agent.posts == {}
        assert agent.human_requests == []
        assert agent.audit_log == []

    def test_agent_get_info(self):
        """正常场景：获取 Agent 信息"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()
        info = agent.get_info()

        assert info["agent_id"] == "agent-self-promotion"
        assert info["name"] == "Self-Promotion Agent"
        assert info["status"] == "active"
        assert "capabilities" in info
        assert "created_at" in info


class TestWeeklyPlanGenerator:
    """测试周计划生成器"""

    def test_generate_plan_abnormal_llm_unavailable(self):
        """异常场景：LLM 不可用时抛出异常（Fail-Closed）"""
        from Agent.self_promotion_agent import WeeklyPlanGenerator

        generator = WeeklyPlanGenerator(llm_service=None)

        with pytest.raises(RuntimeError, match="LLM MANDATORY"):
            generator.generate_weekly_plan(
                project_info={"name": "Test"},
                target_audience="developers",
                goals=["test"],
                target_communities=["r/test"],
                week_start=datetime.now(timezone.utc)
            )

    def test_generate_plan_edge_empty_project_info(self):
        """边界场景：项目信息为空时的处理"""
        from Agent import self_promotion_agent
        from Agent.self_promotion_agent import WeeklyPlanGenerator, LLM_AVAILABLE

        # 如果 LLM 不可用，跳过此测试（符合 Fail-Closed 原则）
        if not LLM_AVAILABLE:
            pytest.skip("LLM service not available, skipping edge case test")

        # Mock LLM service
        mock_llm = Mock()
        mock_llm.generate_json.return_value = {
            "plan_title": "Test Plan",
            "daily_schedules": []
        }

        generator = WeeklyPlanGenerator(llm_service=mock_llm)

        # 应该能处理空的项目信息（虽然结果可能不理想）
        plan = generator.generate_weekly_plan(
            project_info={},
            target_audience="",
            goals=[],
            target_communities=[],
            week_start=datetime.now(timezone.utc)
        )

        assert plan is not None
        assert plan.title == "Test Plan"


class TestContentStrategyEngine:
    """测试内容策略引擎"""

    @pytest.mark.asyncio
    async def test_optimize_for_x_normal(self):
        """正常场景：优化 X 平台内容"""
        from Agent.self_promotion_agent import ContentStrategyEngine

        engine = ContentStrategyEngine(llm_service=None)

        result = await engine.optimize_for_platform(
            content="This is a test post about AI technology",
            platform="x",
            context={"hashtags": ["#AI", "#Tech"]}
        )

        assert result["success"] is True
        assert "content" in result
        assert len(result["content"]) <= 280

    @pytest.mark.asyncio
    async def test_optimize_for_reddit_normal(self):
        """正常场景：优化 Reddit 内容"""
        from Agent.self_promotion_agent import ContentStrategyEngine

        engine = ContentStrategyEngine(llm_service=None)

        result = await engine.optimize_for_platform(
            content={"title": "Test Title", "body": "Test body content"},
            platform="reddit",
            context={}
        )

        assert result["success"] is True
        assert "title" in result
        assert "body" in result

    @pytest.mark.asyncio
    async def test_fix_reddit_error_abnormal_llm_unavailable(self):
        """异常场景：LLM 不可用时的错误修复"""
        from Agent.self_promotion_agent import ContentStrategyEngine

        engine = ContentStrategyEngine(llm_service=None)

        result = await engine.fix_reddit_post_error(
            original_content={"title": "Test", "body": "Content"},
            error_message="Rule violation",
            subreddit_rules=["No self-promotion"]
        )

        assert result["success"] is False
        assert "suggestion" in result
        assert "人工检查" in result["suggestion"]


class TestHumanIntervention:
    """测试人类干预功能"""

    def test_submit_human_request_normal(self):
        """正常场景：提交人类干预请求"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        result = agent.submit_human_request(
            content="Please promote our new feature",
            platform="x",
            priority="high"
        )

        assert result["success"] is True
        assert "request_id" in result
        assert len(agent.human_requests) == 1
        assert agent.human_requests[0]["content"] == "Please promote our new feature"

    def test_submit_human_request_edge_empty_content(self):
        """边界场景：空内容提交"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        result = agent.submit_human_request(
            content="",
            platform="both",
            priority="normal"
        )

        # 应该仍然接受请求（由上层验证）
        assert result["success"] is True


class TestAuditLog:
    """测试审计日志功能"""

    def test_audit_log_recording(self):
        """正常场景：审计日志记录"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        # 触发一个会产生审计日志的操作
        agent.submit_human_request(
            content="Test content",
            platform="x",
            priority="normal"
        )

        # 检查审计日志
        log_result = agent.get_audit_log()

        assert log_result["success"] is True
        assert len(log_result["audit_log"]) > 0
        assert "audit_id" in log_result["audit_log"][0]
        assert "timestamp" in log_result["audit_log"][0]
        assert "action" in log_result["audit_log"][0]

    def test_audit_log_filter(self):
        """正常场景：审计日志过滤"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        # 提交多个请求
        agent.submit_human_request(content="Request 1", platform="x")
        agent.submit_human_request(content="Request 2", platform="reddit")

        # 过滤特定类型的日志
        filtered = agent.get_audit_log(action_filter="human_intervention_request")

        assert filtered["success"] is True
        assert all(log["action"] == "human_intervention_request" for log in filtered["audit_log"])


class TestWeeklyPlanManagement:
    """测试周计划管理"""

    def test_get_weekly_plan_normal(self):
        """正常场景：获取存在的周计划"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        # 先创建一个计划（模拟）
        from Agent.self_promotion_agent import WeeklyPlan, DailySchedule

        plan = WeeklyPlan(
            plan_id="test-plan-123",
            title="Test Plan",
            description="Test Description",
            week_start=datetime.now(timezone.utc),
            week_end=datetime.now(timezone.utc) + timedelta(days=6),
            daily_schedules=[
                DailySchedule(day=1, date="2026-04-20", platform="x", content="Test content")
            ]
        )
        agent.weekly_plans[plan.plan_id] = plan

        # 获取计划
        result = agent.get_weekly_plan("test-plan-123")

        assert result["success"] is True
        assert result["plan"]["plan_id"] == "test-plan-123"
        assert result["plan"]["title"] == "Test Plan"

    def test_get_weekly_plan_abnormal_not_found(self):
        """异常场景：获取不存在的周计划"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        result = agent.get_weekly_plan("non-existent-plan")

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestPromotionTracking:
    """测试推广效果追踪"""

    def test_track_results_normal(self):
        """正常场景：追踪推广效果"""
        from Agent.self_promotion_agent import SelfPromotionAgent, WeeklyPlan, DailySchedule

        agent = SelfPromotionAgent()

        # 创建测试计划
        plan = WeeklyPlan(
            plan_id="track-test-plan",
            title="Tracking Test",
            description="Test tracking",
            week_start=datetime.now(timezone.utc),
            week_end=datetime.now(timezone.utc) + timedelta(days=6),
            daily_schedules=[
                DailySchedule(day=1, date="2026-04-20", platform="x", status="published"),
                DailySchedule(day=2, date="2026-04-21", platform="reddit", status="pending"),
                DailySchedule(day=3, date="2026-04-22", platform="x", status="failed"),
            ]
        )
        agent.weekly_plans[plan.plan_id] = plan

        # 追踪结果
        result = agent.track_promotion_results("track-test-plan")

        assert result["success"] is True
        assert result["results"]["total_posts"] == 3
        assert result["results"]["published"] == 1
        assert result["results"]["pending"] == 1
        assert result["results"]["failed"] == 1
        assert result["results"]["error_rate"] == pytest.approx(1/3)

    def test_track_results_abnormal_plan_not_found(self):
        """异常场景：追踪不存在计划的效果"""
        from Agent.self_promotion_agent import SelfPromotionAgent

        agent = SelfPromotionAgent()

        result = agent.track_promotion_results("non-existent-plan")

        assert result["success"] is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
