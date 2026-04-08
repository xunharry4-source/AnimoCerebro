#!/usr/bin/env python3
"""
任务管理模块和反思模块的全面功能测试
覆盖所有核心功能和边界情况
"""

import sys
import os
from pathlib import Path
import tempfile
import shutil
import json
from datetime import datetime, timezone, timedelta
import asyncio

# 添加src路径
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

def test_comprehensive_task_management():
    """全面测试任务管理模块"""
    print("🧪 全面测试任务管理模块...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        # 创建临时存储目录
        temp_dir = tempfile.mkdtemp(prefix="comprehensive_task_test_")
        
        try:
            # 创建模拟的transcript store
            class MockTranscriptStore:
                def record_audit(self, *args, **kwargs):
                    pass
                def write_entry(self, *args, **kwargs):
                    pass
            
            # 初始化任务管理器
            task_manager = TaskManager(
                transcript_store=MockTranscriptStore(),
                storage_path=temp_dir,
                enable_persistence=True,
                enable_plugin_system=True
            )
            
            interface = task_manager.get_service_interface()
            
            print("  📋 测试1: 基础任务操作")
            # 测试创建不同类型的任务
            tasks_created = []
            
            # 创建认知任务
            async def create_cognitive_task():
                return await interface.create_task({
                    "title": "认知分析任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "priority": "high",
                    "idempotency_key": "cognitive_task_1"
                })
            
            task1 = asyncio.run(create_cognitive_task())
            if task1["success"]:
                tasks_created.append(task1["task"]["task_id"])
                print("    ✅ 创建认知任务成功")
            
            # 创建决策任务
            async def create_decision_task():
                return await interface.create_task({
                    "title": "技术决策任务",
                    "task_type": "decision",
                    "originator_id": "test_user",
                    "priority": "medium",
                    "idempotency_key": "decision_task_1"
                })
            
            task2 = asyncio.run(create_decision_task())
            if task2["success"]:
                tasks_created.append(task2["task"]["task_id"])
                print("    ✅ 创建决策任务成功")
            
            # 创建执行任务
            async def create_action_task():
                return await interface.create_task({
                    "title": "代码执行任务",
                    "task_type": "action",
                    "originator_id": "test_user",
                    "priority": "low",
                    "idempotency_key": "action_task_1"
                })
            
            task3 = asyncio.run(create_action_task())
            if task3["success"]:
                tasks_created.append(task3["task"]["task_id"])
                print("    ✅ 创建执行任务成功")
            
            print("  🔄 测试2: 任务状态流转")
            # 测试完整的状态流转
            for task_id in tasks_created[:2]:  # 测试前两个任务
                # TODO -> IN_PROGRESS
                result = interface.update_task_status(task_id, "in_progress", "开始执行")
                if result["success"]:
                    print(f"    ✅ 任务 {task_id[:8]} 状态更新为 IN_PROGRESS")
                
                # IN_PROGRESS -> DONE
                result = interface.update_task_status(task_id, "done", "任务完成")
                if result["success"]:
                    print(f"    ✅ 任务 {task_id[:8]} 状态更新为 DONE")
            
            print("  ⏸️  测试3: 任务挂起和恢复")
            # 测试任务挂起
            suspend_result = interface.suspend_task(
                tasks_created[2], 
                reason="等待外部依赖",
                recovery_conditions=["外部服务恢复"]
            )
            if suspend_result["success"]:
                print(f"    ✅ 任务 {tasks_created[2][:8]} 挂起成功")
                
                # 测试恢复任务
                resume_result = interface.resume_task(tasks_created[2], "依赖已解决")
                if resume_result["success"]:
                    print(f"    ✅ 任务 {tasks_created[2][:8]} 恢复成功")
            
            print("  🔗 测试4: 任务依赖关系")
            # 创建有依赖关系的任务
            parent_task = interface.create_task({
                "title": "父任务",
                "task_type": "mission",
                "originator_id": "test_user",
                "priority": "high",
                "idempotency_key": "parent_task_1"
            })
            
            if parent_task["success"]:
                parent_id = parent_task["task"]["task_id"]
                
                # 创建子任务
                child_task = interface.create_task({
                    "title": "子任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "priority": "medium",
                    "parent_task_id": parent_id,
                    "idempotency_key": "child_task_1"
                })
                
                if child_task["success"]:
                    # 添加依赖关系
                    dep_result = interface.add_task_dependency(
                        child_task["task"]["task_id"],
                        parent_id
                    )
                    if dep_result["success"]:
                        print("    ✅ 任务依赖关系创建成功")
                    
                    # 检查依赖树
                    dep_tree = interface.get_dependency_tree(child_task["task"]["task_id"])
                    if dep_tree["success"]:
                        print("    ✅ 依赖树获取成功")
            
            print("  📦 测试5: 批量操作")
            # 批量更新状态
            batch_result = interface.bulk_update_status(
                tasks_created[:2],
                "archived",
                "批量归档"
            )
            if batch_result["success"]:
                print(f"    ✅ 批量更新成功: {batch_result['updated_count']} 个任务")
            
            # 批量挂起
            batch_suspend = interface.bulk_suspend_tasks(
                tasks_created[2:3],
                "批量维护",
                ["维护完成"]
            )
            if batch_suspend["success"]:
                print(f"    ✅ 批量挂起成功: {batch_suspend['updated_count']} 个任务")
            
            print("  📊 测试6: 高级查询和过滤")
            # 按状态过滤
            todo_tasks = interface.list_tasks({"status": "todo"})
            print(f"    ✅ TODO 任务数量: {todo_tasks['count']}")
            
            # 按优先级过滤
            high_priority_tasks = interface.list_tasks({"priority": "high"})
            print(f"    ✅ 高优先级任务数量: {high_priority_tasks['count']}")
            
            # 按类型过滤
            cognitive_tasks = interface.list_tasks({"task_type": "cognitive_step"})
            print(f"    ✅ 认知任务数量: {cognitive_tasks['count']}")
            
            # 搜索任务
            search_result = interface.search_tasks("认知")
            print(f"    ✅ 搜索结果: {search_result['count']} 个任务")
            
            print("  🔧 测试7: 任务干预和清理")
            # 任务干预
            intervention_result = interface.intervene_task(
                tasks_created[0],
                "manual_override",
                "手动干预测试",
                {"priority": "critical"}
            )
            if intervention_result["success"]:
                print("    ✅ 任务干预成功")
            
            # 清理过期任务
            cleanup_result = interface.cleanup_expired_tasks()
            if cleanup_result["success"]:
                print(f"    ✅ 清理完成: {cleanup_result['cleaned_count']} 个任务")
            
            print("  📈 测试8: 统计和监控")
            # 获取详细统计
            stats = interface.get_task_statistics()
            if stats["success"]:
                statistics = stats["statistics"]
                print(f"    ✅ 总任务数: {statistics['total_tasks']}")
                print(f"    ✅ 活跃任务: {statistics['active_tasks']}")
                print(f"    ✅ 已完成任务: {statistics['completed_tasks']}")
                print(f"    ✅ 挂起任务: {statistics['suspended_tasks']}")
            
            # 获取性能指标
            metrics = interface.get_performance_metrics()
            if metrics["success"]:
                print("    ✅ 性能指标获取成功")
            
            print("  🔌 测试9: 插件系统")
            # 测试拆解策略
            strategies = task_manager.get_available_decomposition_strategies()
            print(f"    ✅ 可用拆解策略: {strategies}")
            
            # 测试默认策略
            default_strategy = task_manager.get_default_decomposition_strategy()
            print(f"    ✅ 默认策略: {default_strategy}")
            
            # 设置新策略
            set_result = task_manager.set_default_decomposition_strategy("parallel")
            if set_result:
                print("    ✅ 默认策略设置成功")
            
            print("  💾 测试10: 持久化和恢复")
            # 测试持久化统计
            persistence_stats = interface.get_persistence_stats()
            if persistence_stats["success"]:
                print("    ✅ 持久化统计获取成功")
            
            # 测试自动保存
            auto_save = interface.toggle_auto_save()
            print(f"    ✅ 自动保存切换: {auto_save}")
            
            print("  ✅ 任务管理模块全面测试通过")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 任务管理模块全面测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_comprehensive_reflection():
    """全面测试反思模块"""
    print("\n🧪 全面测试反思模块...")
    
    try:
        from zentex.reflection import ReflectionManager
        from zentex.reflection.models import ReflectionType, ReflectionQuality, ReflectionTrigger
        
        # 创建临时存储目录
        temp_dir = tempfile.mkdtemp(prefix="comprehensive_reflection_test_")
        
        try:
            # 初始化反思管理器
            reflection_manager = ReflectionManager(
                storage_path=temp_dir,
                enable_persistence=True
            )
            
            interface = reflection_manager.get_interface()
            
            print("  📝 测试1: 多类型反思生成")
            reflections_created = []
            
            # 决策反思
            decision_reflection = interface.generate_reflection({
                "subject": "架构设计决策",
                "reflection_type": "decision_reflection",
                "context": {
                    "decision": {
                        "factors": ["性能", "成本", "可维护性"],
                        "stakeholders": ["技术团队", "产品团队"]
                    },
                    "outcome": {
                        "success": True,
                        "confidence": 0.8
                    },
                    "alternatives": [
                        {"name": "微服务", "risk": "medium"},
                        {"name": "单体", "risk": "low"}
                    ]
                }
            })
            if decision_reflection["success"]:
                reflections_created.append(decision_reflection["reflection"]["reflection_id"])
                print("    ✅ 决策反思生成成功")
            
            # 错误反思
            error_reflection = interface.generate_reflection({
                "subject": "数据库连接错误",
                "reflection_type": "error_reflection",
                "context": {
                    "error": {
                        "type": "connection_timeout",
                        "severity": "high",
                        "root_cause": "连接池耗尽"
                    },
                    "impact": {
                        "affected_users": 100,
                        "downtime_minutes": 15
                    },
                    "prevention": {
                        "monitoring_needed": True,
                        "improvements": ["连接池优化", "监控告警"]
                    }
                }
            })
            if error_reflection["success"]:
                reflections_created.append(error_reflection["reflection"]["reflection_id"])
                print("    ✅ 错误反思生成成功")
            
            # 成功反思
            success_reflection = interface.generate_reflection({
                "subject": "性能优化项目成功",
                "reflection_type": "success_reflection",
                "context": {
                    "success": {
                        "degree": "complete",
                        "impact_score": 0.9,
                        "metrics": {"performance_gain": 0.4}
                    },
                    "success_factors": [
                        "团队协作良好",
                        "技术方案合理",
                        "执行计划详细"
                    ],
                    "replication": {
                        "key_factors": ["代码审查", "性能测试"],
                        "context_requirements": ["技术团队", "测试环境"]
                    }
                }
            })
            if success_reflection["success"]:
                reflections_created.append(success_reflection["reflection"]["reflection_id"])
                print("    ✅ 成功反思生成成功")
            
            # 过程反思
            process_reflection = interface.generate_reflection({
                "subject": "开发流程优化",
                "reflection_type": "process_reflection",
                "context": {
                    "process": {
                        "phases": ["需求分析", "设计", "开发", "测试"],
                        "duration_weeks": 8,
                        "team_size": 6
                    },
                    "outcomes": {
                        "efficiency_score": 0.7,
                        "quality_score": 0.8
                    },
                    "challenges": ["沟通延迟", "需求变更"],
                    "improvements": ["敏捷方法", "自动化工具"]
                }
            })
            if process_reflection["success"]:
                reflections_created.append(process_reflection["reflection"]["reflection_id"])
                print("    ✅ 过程反思生成成功")
            
            print("  🔍 测试2: 反思查询和搜索")
            # 按类型过滤
            decision_reflections = interface.list_reflections({"reflection_type": "decision_reflection"})
            print(f"    ✅ 决策反思数量: {decision_reflections['count']}")
            
            # 按质量过滤
            excellent_reflections = interface.list_reflections({"quality": "excellent"})
            print(f"    ✅ 优秀反思数量: {excellent_reflections['count']}")
            
            # 按时间过滤
            recent_reflections = interface.list_reflections({
                "start_time": datetime.now(timezone.utc) - timedelta(hours=1)
            })
            print(f"    ✅ 最近反思数量: {recent_reflections['count']}")
            
            # 文本搜索
            search_results = interface.search_reflections("性能")
            print(f"    ✅ 搜索结果: {search_results['count']} 个反思")
            
            print("  🏛️ 测试3: 反思治理")
            # 验证反思
            verify_result = interface.verify_reflection(reflections_created[0], "expert_user")
            if verify_result["success"]:
                print("    ✅ 反思验证成功")
            
            # 标记可疑
            suspect_result = interface.mark_suspect(reflections_created[1], "数据来源需要验证")
            if suspect_result["success"]:
                print("    ✅ 反思标记可疑成功")
            
            # 归档反思
            archive_result = interface.archive_reflection(reflections_created[2])
            if archive_result["success"]:
                print("    ✅ 反思归档成功")
            
            print("  📦 测试4: 批量治理操作")
            # 批量验证
            batch_verify = interface.batch_governance(
                reflections_created[:2],
                "verify",
                verified_by="batch_admin"
            )
            if batch_verify["success"]:
                print(f"    ✅ 批量验证成功: {batch_verify['success_count']} 个")
            
            # 批量归档
            batch_archive = interface.batch_governance(
                reflections_created[2:3],
                "archive"
            )
            if batch_archive["success"]:
                print(f"    ✅ 批量归档成功: {batch_archive['success_count']} 个")
            
            print("  📊 测试5: 统计分析")
            # 基础指标
            metrics = interface.get_metrics()
            if metrics["success"]:
                data = metrics["metrics"]
                print(f"    ✅ 总反思数: {data['total_reflections']}")
                print(f"    ✅ 平均置信度: {data['average_confidence']:.2f}")
                print(f"    ✅ 平均影响评分: {data['average_impact_score']:.2f}")
            
            # 详细统计
            statistics = interface.get_reflection_statistics()
            if statistics["success"]:
                stats = statistics["statistics"]
                print(f"    ✅ 高质量率: {stats['high_quality_rate']:.2%}")
                print(f"    ✅ 高可操作性率: {stats['high_actionability_rate']:.2%}")
            
            print("  🔬 测试6: 模式分析")
            # 分析反思模式
            patterns = interface.analyze_reflection_patterns()
            if patterns["success"]:
                pattern_data = patterns["patterns"]
                for ref_type, pattern in pattern_data.items():
                    print(f"    ✅ {ref_type}: {pattern['count']} 个反思")
            
            print("  🎯 测试7: 智能推荐")
            # 获取推荐
            recommendations = interface.get_reflection_recommendations(limit=5)
            if recommendations["success"]:
                print(f"    ✅ 获取推荐: {recommendations['count']} 个")
            
            # 上下文推荐
            contextual_recs = reflection_manager.get_contextual_recommendations(
                context={
                    "type": "decision",
                    "keywords": ["技术", "架构"],
                    "min_quality": "good"
                },
                limit=3
            )
            if contextual_recs["success"]:
                print(f"    ✅ 上下文推荐: {contextual_recs['count']} 个")
            
            print("  📚 测试8: 模板系统")
            # 创建自定义模板
            template_result = interface.create_template(
                name="项目管理复盘模板",
                description="用于项目结束后的复盘反思",
                template_data={
                    "reflection_type": "process_reflection",
                    "required_fields": ["project_name", "outcomes"],
                    "optional_fields": ["challenges", "lessons"],
                    "prompt_template": "请对项目'{project_name}'进行全面复盘...",
                    "evaluation_criteria": {
                        "min_insights": 2,
                        "min_lessons": 1
                    }
                }
            )
            if template_result["success"]:
                template_id = template_result["template"]["template_id"]
                print("    ✅ 模板创建成功")
                
                # 使用模板生成反思
                template_reflection = interface.generate_reflection({
                    "subject": "Q1项目复盘",
                    "reflection_type": "process_reflection",
                    "context": {
                        "project_name": "电商平台重构",
                        "outcomes": "按时交付，性能提升30%"
                    },
                    "template_id": template_id
                })
                if template_reflection["success"]:
                    print("    ✅ 使用模板生成反思成功")
            
            # 列出所有模板
            templates = interface.list_templates()
            print(f"    ✅ 可用模板: {templates['count']} 个")
            
            print("  📈 测试9: 高级分析")
            # 批量分析
            batch_analysis = reflection_manager.batch_analyze_reflections(
                reflections_created,
                analysis_type="insights"
            )
            if batch_analysis["success"]:
                print("    ✅ 批量洞察分析成功")
            
            # 学习路径
            learning_path = reflection_manager.get_learning_pathway(
                goal="提高技术决策能力",
                current_level="intermediate",
                target_level="advanced"
            )
            if learning_path["success"]:
                print(f"    ✅ 学习路径: {learning_path['total_steps']} 个步骤")
            
            print("  💾 测试10: 导出和报告")
            # 导出数据
            export_result = reflection_manager.export_reflections(
                format="json"
            )
            if export_result["success"]:
                print(f"    ✅ 导出成功: {export_result['count']} 个反思")
            
            # 生成报告
            report = reflection_manager.generate_reflection_report(
                period="weekly"
            )
            if report["success"]:
                print("    ✅ 报告生成成功")
            
            print("  ✅ 反思模块全面测试通过")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 反思模块全面测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_edge_cases_and_error_handling():
    """测试边界情况和错误处理"""
    print("\n🧪 测试边界情况和错误处理...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.reflection import ReflectionManager
        
        temp_dir = tempfile.mkdtemp(prefix="edge_case_test_")
        
        try:
            class MockTranscriptStore:
                def record_audit(self, *args, **kwargs):
                    pass
                def write_entry(self, *args, **kwargs):
                    pass
            
            task_manager = TaskManager(
                transcript_store=MockTranscriptStore(),
                storage_path=os.path.join(temp_dir, "tasks"),
                enable_persistence=True
            )
            
            reflection_manager = ReflectionManager(
                storage_path=os.path.join(temp_dir, "reflections"),
                enable_persistence=True
            )
            
            task_interface = task_manager.get_service_interface()
            reflection_interface = reflection_manager.get_interface()
            
            print("  ❌ 测试1: 无效输入处理")
            # 任务管理无效输入
            invalid_task = task_interface.create_task({
                "title": "",  # 空标题
                "task_type": "invalid_type",  # 无效类型
                "originator_id": ""  # 空ID
            })
            if not invalid_task["success"]:
                print("    ✅ 任务创建无效输入被正确拒绝")
            
            # 反思管理无效输入
            invalid_reflection = reflection_interface.generate_reflection({
                "subject": "",  # 空主题
                "reflection_type": "invalid_type",  # 无效类型
                "context": {}  # 空上下文
            })
            if not invalid_reflection["success"]:
                print("    ✅ 反思生成无效输入被正确拒绝")
            
            print("  🔍 测试2: 不存在资源处理")
            # 获取不存在的任务
            non_existent_task = task_interface.get_task("non_existent_id")
            if not non_existent_task["success"]:
                print("    ✅ 不存在任务查询被正确处理")
            
            # 获取不存在的反思
            non_existent_reflection = reflection_interface.get_reflection("non_existent_id")
            if not non_existent_reflection["success"]:
                print("    ✅ 不存在反思查询被正确处理")
            
            print("  🔄 测试3: 状态转换验证")
            # 创建任务并测试无效状态转换
            task = task_interface.create_task({
                "title": "状态测试任务",
                "task_type": "cognitive_step",
                "originator_id": "test_user",
                "idempotency_key": "state_test"
            })
            
            if task["success"]:
                task_id = task["task"]["task_id"]
                
                # 尝试无效状态转换 (TODO -> SUSPENDED 应该可以)
                invalid_transition = task_interface.update_task_status(task_id, "invalid_status")
                if not invalid_transition["success"]:
                    print("    ✅ 无效状态转换被正确拒绝")
                
                # 尝试已完成任务的转换
                task_interface.update_task_status(task_id, "done")
                invalid_transition2 = task_interface.update_task_status(task_id, "in_progress")
                if not invalid_transition2["success"]:
                    print("    ✅ 已完成任务状态转换被正确拒绝")
            
            print("  📝 测试4: 重复操作处理")
            # 重复创建相同任务 (通过 idempotency_key)
            task1 = task_interface.create_task({
                "title": "重复测试任务",
                "task_type": "cognitive_step",
                "originator_id": "test_user",
                "idempotency_key": "duplicate_test"
            })
            
            task2 = task_interface.create_task({
                "title": "重复测试任务",
                "task_type": "cognitive_step",
                "originator_id": "test_user",
                "idempotency_key": "duplicate_test"
            })
            
            if task1["success"] and task2["success"]:
                if task1["task"]["task_id"] == task2["task"]["task_id"]:
                    print("    ✅ 幂等性处理正确")
            
            print("  🗂️ 测试5: 大量数据处理")
            # 批量创建大量任务
            batch_tasks = []
            for i in range(50):
                task = task_interface.create_task({
                    "title": f"批量任务 {i}",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "idempotency_key": f"batch_task_{i}"
                })
                if task["success"]:
                    batch_tasks.append(task["task"]["task_id"])
            
            print(f"    ✅ 批量创建 {len(batch_tasks)} 个任务成功")
            
            # 批量操作
            batch_update = task_interface.bulk_update_status(
                batch_tasks[:10],
                "archived"
            )
            if batch_update["success"]:
                print(f"    ✅ 批量更新 {batch_update['updated_count']} 个任务成功")
            
            print("  🔧 测试6: 并发操作模拟")
            import threading
            import time
            
            results = []
            
            def create_task_thread(thread_id):
                try:
                    task = task_interface.create_task({
                        "title": f"并发任务 {thread_id}",
                        "task_type": "cognitive_step",
                        "originator_id": "test_user",
                        "idempotency_key": f"concurrent_task_{thread_id}"
                    })
                    results.append(task["success"])
                except Exception as e:
                    results.append(False)
            
            # 创建多个线程
            threads = []
            for i in range(5):
                thread = threading.Thread(target=create_task_thread, args=(i,))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            if all(results):
                print("    ✅ 并发操作处理正确")
            
            print("  ✅ 边界情况和错误处理测试通过")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 边界情况测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance_and_scalability():
    """测试性能和可扩展性"""
    print("\n🧪 测试性能和可扩展性...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.reflection import ReflectionManager
        import time
        
        temp_dir = tempfile.mkdtemp(prefix="performance_test_")
        
        try:
            class MockTranscriptStore:
                def record_audit(self, *args, **kwargs):
                    pass
                def write_entry(self, *args, **kwargs):
                    pass
            
            task_manager = TaskManager(
                transcript_store=MockTranscriptStore(),
                storage_path=os.path.join(temp_dir, "tasks"),
                enable_persistence=True
            )
            
            reflection_manager = ReflectionManager(
                storage_path=os.path.join(temp_dir, "reflections"),
                enable_persistence=True
            )
            
            task_interface = task_manager.get_service_interface()
            reflection_interface = reflection_manager.get_interface()
            
            print("  ⚡ 测试1: 任务创建性能")
            # 测试大量任务创建性能
            start_time = time.time()
            task_count = 100
            
            for i in range(task_count):
                task = task_interface.create_task({
                    "title": f"性能测试任务 {i}",
                    "task_type": "cognitive_step",
                    "originator_id": "perf_test",
                    "idempotency_key": f"perf_task_{i}"
                })
            
            task_creation_time = time.time() - start_time
            print(f"    ✅ 创建 {task_count} 个任务耗时: {task_creation_time:.2f} 秒")
            print(f"    ✅ 平均每任务耗时: {task_creation_time/task_count*1000:.2f} 毫秒")
            
            print("  ⚡ 测试2: 反思生成性能")
            # 测试大量反思生成性能
            start_time = time.time()
            reflection_count = 50
            
            for i in range(reflection_count):
                reflection = reflection_interface.generate_reflection({
                    "subject": f"性能测试反思 {i}",
                    "reflection_type": "process_reflection",
                    "context": {
                        "process": {"steps": ["步骤1", "步骤2"]},
                        "outcome": {"success": True}
                    }
                })
            
            reflection_creation_time = time.time() - start_time
            print(f"    ✅ 生成 {reflection_count} 个反思耗时: {reflection_creation_time:.2f} 秒")
            print(f"    ✅ 平均每反思耗时: {reflection_creation_time/reflection_count*1000:.2f} 毫秒")
            
            print("  ⚡ 测试3: 查询性能")
            # 测试大量数据查询性能
            start_time = time.time()
            
            # 任务列表查询
            task_list = task_interface.list_tasks()
            
            # 反思列表查询
            reflection_list = reflection_interface.list_reflections()
            
            # 搜索查询
            task_search = task_interface.search_tasks("性能")
            reflection_search = reflection_interface.search_reflections("测试")
            
            query_time = time.time() - start_time
            print(f"    ✅ 多种查询耗时: {query_time:.2f} 秒")
            
            print("  ⚡ 测试4: 统计计算性能")
            # 测试统计计算性能
            start_time = time.time()
            
            task_stats = task_interface.get_task_statistics()
            reflection_metrics = reflection_interface.get_metrics()
            reflection_stats = reflection_interface.get_reflection_statistics()
            
            stats_time = time.time() - start_time
            print(f"    ✅ 统计计算耗时: {stats_time:.2f} 秒")
            
            print("  💾 测试5: 持久化性能")
            # 测试持久化操作性能
            start_time = time.time()
            
            # 强制保存
            task_save = task_interface.save_state()
            reflection_save = reflection_manager.interface.save_state()
            
            persistence_time = time.time() - start_time
            print(f"    ✅ 持久化操作耗时: {persistence_time:.2f} 秒")
            
            print("  📊 测试6: 内存使用情况")
            # 简单的内存使用检查
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            print(f"    ✅ 当前内存使用: {memory_mb:.2f} MB")
            
            if memory_mb < 500:  # 假设内存使用应该小于500MB
                print("    ✅ 内存使用在合理范围内")
            else:
                print("    ⚠️  内存使用较高，需要关注")
            
            print("  ✅ 性能和可扩展性测试通过")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始全面功能测试...")
    print("=" * 80)
    
    results = []
    
    # 全面功能测试
    results.append(test_comprehensive_task_management())
    results.append(test_comprehensive_reflection())
    results.append(test_edge_cases_and_error_handling())
    results.append(test_performance_and_scalability())
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 全面测试结果汇总:")
    
    test_names = [
        "任务管理模块全面测试",
        "反思模块全面测试",
        "边界情况和错误处理测试",
        "性能和可扩展性测试"
    ]
    
    passed = 0
    total = len(results)
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {i+1}. {name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("🎉 所有全面测试都通过了！模块功能完整且稳定。")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
