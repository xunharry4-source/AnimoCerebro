"""
项目计划文档示例
防止每次项目计划格式不一样
"""

from datetime import datetime, timedelta
from .project_plan_document_plugin import (
    ProjectPlanDocument,
    TaskCategory,
    Milestone,
    RiskItem,
    RiskPriority,
)


def create_example_project_plan() -> ProjectPlanDocument:
    """创建示例项目计划文档"""
    
    plan_doc = ProjectPlanDocument(
        # 第1部分: 基本信息
        part1_project_name="微服务架构升级项目",
        part1_description="将单体应用逐步迁移到微服务架构，提高系统可扩展性和维护性",
        part1_task_category=TaskCategory.PROJECT_REFACTOR.value,
        part1_version="2024-Q2",
        
        # 第2部分: 项目计划
        part2_start_date=datetime(2024, 4, 1),
        part2_end_date=datetime(2024, 7, 31),
        part2_team_members=[
            "张三 - 项目经理",
            "李四 - 技术主管",
            "王五 - 后端开发（3人）",
            "赵六 - 基础设施（2人）",
            "孙七 - QA（2人）",
        ],
        part2_estimated_total_hours=2000,
        part2_resource_requirements=[
            "Docker & Kubernetes 环境",
            "消息队列中间件（RabbitMQ/Kafka）",
            "分布式追踪系统（Jaeger）",
            "监控告警系统（Prometheus/Grafana）",
        ],
        part2_budget="¥500,000",
        part2_external_dependencies=[
            "云供应商支持（AWS/AlibabaCloud）",
            "第三方API服务升级",
        ],
        
        # 第3部分: 整体项目目标
        part3_business_goals=[
            "提高系统吞吐量 3倍以上",
            "提升团队开发效率，支持并行开发",
            "降低部署周期，实现快速迭代",
            "提高故障隔离度，降低故障影响面",
        ],
        part3_technical_goals=[
            "将10个核心模块分离为独立微服务",
            "实现服务间通信的异步化",
            "建立完整的可观测性体系",
            "实现自动化的灰度和蓝绿部署",
        ],
        part3_success_metrics=[
            "单个服务独立部署成功率 ≥ 99%",
            "平均响应时间降低 30%",
            "新功能发布周期从2周缩短到3天",
            "单点故障影响范围缩小到 ≤ 10% 服务",
        ],
        part3_acceptance_criteria=[
            "所有核心模块已微服务化",
            "生产环境无业务功能回归",
            "性能指标达到或超过目标值",
            "完整的运维文档和故障响应流程",
        ],
    )
    
    # 第4部分: 添加里程碑
    milestones = [
        Milestone(
            name="第一阶段：分析与架构设计",
            description="完成架构分析、设计并验证可行性",
            target_date=datetime(2024, 4, 30),
            deliverables=[
                "微服务架构设计文档",
                "技术选型和POC验证报告",
                "数据库分库方案",
                "服务间通信模型定义",
            ],
            success_criteria=[
                "架构设计评审通过",
                "关键技术POC验证成功",
                "团队培训完成，熟悉新技术栈",
            ],
            key_metrics={
                "文档完整性": "100%",
                "评审通过率": "100%",
                "POC验证成功": True,
            },
        ),
        Milestone(
            name="第二阶段：核心服务提取",
            description="提取3个核心服务，建立微服务基础设施",
            target_date=datetime(2024, 5, 31),
            deliverables=[
                "3个微服务的独立部署版本",
                "服务网格基础设施（Istio）",
                "API网关配置",
                "服务间通信测试套件",
            ],
            success_criteria=[
                "核心服务在生产环境成功运行30天无故障",
                "服务通信延迟 ≤ 100ms",
                "自动化部署成功率 ≥ 98%",
            ],
        ),
        Milestone(
            name="第三阶段：功能验证与优化",
            description="验证微服务化功能正确性，优化性能",
            target_date=datetime(2024, 6, 30),
            deliverables=[
                "完整的功能和性能测试报告",
                "性能优化实施方案",
                "监控和告警规则配置",
            ],
            success_criteria=[
                "所有功能回归测试通过",
                "性能指标达到预期",
                "监控覆盖度 ≥ 95%",
            ],
        ),
        Milestone(
            name="第四阶段：灰度发布与推广",
            description="逐步推广到更多模块和用户",
            target_date=datetime(2024, 7, 31),
            deliverables=[
                "灰度发布策略文档",
                "完整的运维手册和故障响应流程",
                "团队和运维人员培训",
            ],
            success_criteria=[
                "灰度用户反馈满意度 ≥ 4.5/5",
                "全量发布无重大故障",
            ],
        ),
    ]
    for ms in milestones:
        plan_doc.add_milestone(ms)
    
    # 第5部分: 添加风险项
    risks = [
        RiskItem(
            title="数据迁移风险",
            description="数据库分片和数据迁移过程中可能出现数据不一致",
            probability="high",
            impact="high",
            priority=RiskPriority.CRITICAL,
            mitigation_strategy="制定详细的数据迁移计划、灾难恢复方案、验证脚本",
            contingency_plan="及时回滚到单体应用，不影响业务",
        ),
        RiskItem(
            title="服务通信网络延迟",
            description="网络分布式调用可能增加系统延迟",
            probability="medium",
            impact="high",
            priority=RiskPriority.HIGH,
            mitigation_strategy="优化网络拓扑、使用消息队列异步化、缓存策略",
            contingency_plan="调整服务部署位置、增加缓存层",
        ),
        RiskItem(
            title="团队技能不足",
            description="微服务架构和新技术栈学习曲线陡峭",
            probability="medium",
            impact="medium",
            priority=RiskPriority.HIGH,
            mitigation_strategy="提前进行技术培训、引入外部顾问、建立最佳实践文档",
            contingency_plan="调整项目进度、增加外包支持",
        ),
        RiskItem(
            title="第三方服务依赖问题",
            description="依赖的外部服务不稳定或接口变更",
            probability="low",
            impact="high",
            priority=RiskPriority.MEDIUM,
            mitigation_strategy="建立降级方案、Mock服务、与供应商沟通升级计划",
            contingency_plan="使用备用服务商、本地实现替代方案",
        ),
    ]
    for risk in risks:
        plan_doc.add_risk(risk)
    
    return plan_doc


if __name__ == "__main__":
    plan = create_example_project_plan()
    
    # 验证文档
    is_valid, errors = plan.validate_document()
    print("=" * 80)
    print("项目计划文档验证结果")
    print("=" * 80)
    if is_valid:
        print("✓ 项目计划文档验证通过\n")
    else:
        print("✗ 验证失败:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    # 生成Markdown报告
    print(plan.generate_markdown_report())
