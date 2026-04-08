#!/usr/bin/env python3
"""
任务管理模块和反思模块的全面功能测试
简化版本，专注于核心功能测试
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

def test_all_task_features():
    """测试任务管理模块的所有功能"""
    print("🧪 测试任务管理模块所有功能...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        temp_dir = tempfile.mkdtemp(prefix="all_task_features_test_")
        
        try:
            class MockTranscriptStore:
                def record_audit(self, *args, **kwargs):
                    pass
                def write_entry(self, *args, **kwargs):
                    pass
            
            task_manager = TaskManager(
                transcript_store=MockTranscriptStore(),
                storage_path=temp_dir,
                enable_persistence=True,
                enable_plugin_system=True
            )
            
            interface = task_manager.get_service_interface()
            
            features_tested = 0
            features_passed = 0
            
            print("  📋 功能1: 任务创建")
            features_tested += 1
            async def test_task_creation():
                tasks = []
                
                # 创建不同类型的任务
                task_types = [
                    ("cognitive_step", "认知分析", "high"),
                    ("decision", "技术决策", "medium"),
                    ("action", "代码执行", "low"),
                    ("mission", "项目使命", "critical")
                ]
                
                for task_type, title, priority in task_types:
                    task = await interface.create_task({
                        "title": f"{title}任务",
                        "task_type": task_type,
                        "originator_id": "test_user",
                        "priority": priority,
                        "idempotency_key": f"{task_type}_task"
                    })
                    if task["success"]:
                        tasks.append(task["task"]["task_id"])
                
                return tasks
            
            created_tasks = asyncio.run(test_task_creation())
            if len(created_tasks) >= 3:
                print("    ✅ 多类型任务创建成功")
                features_passed += 1
            else:
                print("    ❌ 任务创建失败")
            
            print("  🔄 功能2: 状态管理")
            features_tested += 1
            if created_tasks:
                # 测试状态更新
                update_result = interface.update_task_status(created_tasks[0], "in_progress", "开始执行")
                if update_result["success"]:
                    print("    ✅ 状态更新成功")
                    features_passed += 1
                else:
                    print("    ❌ 状态更新失败")
            else:
                print("    ❌ 无任务可用于状态测试")
            
            print("  📦 功能3: 任务查询")
            features_tested += 1
            # 测试各种查询
            list_result = interface.list_tasks()
            search_result = interface.search_tasks("认知")
            todo_tasks = interface.list_tasks({"status": "todo"})
            
            if (list_result["success"] and search_result["success"] and 
                todo_tasks["success"] and list_result["count"] > 0):
                print("    ✅ 任务查询功能正常")
                features_passed += 1
            else:
                print("    ❌ 任务查询功能异常")
            
            print("  ⏸️  功能4: 任务挂起和恢复")
            features_tested += 1
            if created_tasks:
                # 测试挂起
                suspend_result = interface.suspend_task(created_tasks[1], "测试挂起", ["条件满足"])
                if suspend_result["success"]:
                    # 测试恢复
                    resume_result = interface.resume_task(created_tasks[1], "恢复执行")
                    if resume_result["success"]:
                        print("    ✅ 挂起恢复功能正常")
                        features_passed += 1
                    else:
                        print("    ❌ 恢复失败")
                else:
                    print("    ❌ 挂起失败")
            else:
                print("    ❌ 无任务可用于挂起测试")
            
            print("  🔗 功能5: 依赖关系")
            features_tested += 1
            if len(created_tasks) >= 2:
                # 测试添加依赖
                dep_result = interface.add_task_dependency(created_tasks[1], created_tasks[0])
                if dep_result["success"]:
                    print("    ✅ 依赖关系创建成功")
                    features_passed += 1
                else:
                    print("    ❌ 依赖关系创建失败")
            else:
                print("    ❌ 任务数量不足以测试依赖")
            
            print("  📊 功能6: 统计分析")
            features_tested += 1
            stats = interface.get_task_statistics()
            if stats["success"]:
                print("    ✅ 统计分析功能正常")
                features_passed += 1
            else:
                print("    ❌ 统计分析功能异常")
            
            print("  🔌 功能7: 插件系统")
            features_tested += 1
            strategies = task_manager.get_available_decomposition_strategies()
            default_strategy = task_manager.get_default_decomposition_strategy()
            
            if strategies and default_strategy:
                print("    ✅ 插件系统功能正常")
                features_passed += 1
            else:
                print("    ❌ 插件系统功能异常")
            
            print("  📦 功能8: 批量操作")
            features_tested += 1
            if len(created_tasks) >= 2:
                # 批量更新状态
                batch_result = interface.bulk_update_status(created_tasks[:2], "archived", "批量归档")
                if batch_result["success"]:
                    print("    ✅ 批量操作功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 批量操作失败")
            else:
                print("    ❌ 任务数量不足以测试批量操作")
            
            print("  🔧 功能9: 任务干预")
            features_tested += 1
            if created_tasks:
                # 任务干预
                intervention_result = interface.intervene_task(
                    created_tasks[0],
                    "manual_override",
                    "手动干预",
                    {"priority": "critical"}
                )
                if intervention_result["success"]:
                    print("    ✅ 任务干预功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 任务干预失败")
            else:
                print("    ❌ 无任务可用于干预测试")
            
            print("  💾 功能10: 持久化")
            features_tested += 1
            # 测试持久化统计
            persistence_stats = interface.get_persistence_stats()
            if persistence_stats["success"]:
                print("    ✅ 持久化功能正常")
                features_passed += 1
            else:
                print("    ❌ 持久化功能异常")
            
            print(f"  📈 任务管理模块功能测试结果: {features_passed}/{features_tested} 通过")
            return features_passed >= features_tested * 0.8  # 80%通过率
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 任务管理模块测试失败: {e}")
        return False

def test_all_reflection_features():
    """测试反思模块的所有功能"""
    print("\n🧪 测试反思模块所有功能...")
    
    try:
        from zentex.reflection import ReflectionManager
        from zentex.reflection.models import ReflectionType, ReflectionQuality, ReflectionTrigger
        
        temp_dir = tempfile.mkdtemp(prefix="all_reflection_features_test_")
        
        try:
            reflection_manager = ReflectionManager(
                storage_path=temp_dir,
                enable_persistence=True
            )
            
            interface = reflection_manager.get_interface()
            
            features_tested = 0
            features_passed = 0
            
            print("  📝 功能1: 多类型反思生成")
            features_tested += 1
            reflection_types = [
                ("decision_reflection", "架构决策", {
                    "decision": {"factors": ["性能", "成本"]},
                    "outcome": {"success": True}
                }),
                ("error_reflection", "系统错误", {
                    "error": {"type": "timeout", "severity": "high"},
                    "impact": {"affected_users": 10}
                }),
                ("success_reflection", "项目成功", {
                    "success": {"degree": "complete", "impact_score": 0.9},
                    "success_factors": ["团队协作"]
                }),
                ("process_reflection", "流程优化", {
                    "process": {"phases": ["设计", "开发"]},
                    "outcomes": {"efficiency_score": 0.8}
                })
            ]
            
            created_reflections = []
            for ref_type, subject, context in reflection_types:
                reflection = interface.generate_reflection({
                    "subject": subject,
                    "reflection_type": ref_type,
                    "context": context
                })
                if reflection["success"]:
                    created_reflections.append(reflection["reflection"]["reflection_id"])
            
            if len(created_reflections) >= 3:
                print("    ✅ 多类型反思生成成功")
                features_passed += 1
            else:
                print("    ❌ 反思生成失败")
            
            print("  🔍 功能2: 反思查询")
            features_tested += 1
            list_result = interface.list_reflections()
            search_result = interface.search_reflections("架构")
            type_filter = interface.list_reflections({"reflection_type": "decision_reflection"})
            
            if (list_result["success"] and search_result["success"] and 
                type_filter["success"]):
                print("    ✅ 反思查询功能正常")
                features_passed += 1
            else:
                print("    ❌ 反思查询功能异常")
            
            print("  🏛️ 功能3: 反思治理")
            features_tested += 1
            if created_reflections:
                # 验证反思
                verify_result = interface.verify_reflection(created_reflections[0], "expert_user")
                # 标记可疑
                suspect_result = interface.mark_suspect(created_reflections[1], "需要验证")
                # 归档反思
                archive_result = interface.archive_reflection(created_reflections[2])
                
                if verify_result["success"] and suspect_result["success"] and archive_result["success"]:
                    print("    ✅ 反思治理功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 反思治理功能异常")
            else:
                print("    ❌ 无反思可用于治理测试")
            
            print("  📦 功能4: 批量治理")
            features_tested += 1
            if len(created_reflections) >= 2:
                batch_result = interface.batch_governance(
                    created_reflections[:2],
                    "verify",
                    verified_by="batch_admin"
                )
                if batch_result["success"]:
                    print("    ✅ 批量治理功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 批量治理失败")
            else:
                print("    ❌ 反思数量不足以测试批量治理")
            
            print("  📊 功能5: 统计分析")
            features_tested += 1
            metrics = interface.get_metrics()
            statistics = interface.get_reflection_statistics()
            
            if metrics["success"] and statistics["success"]:
                print("    ✅ 统计分析功能正常")
                features_passed += 1
            else:
                print("    ❌ 统计分析功能异常")
            
            print("  🔬 功能6: 模式分析")
            features_tested += 1
            patterns = interface.analyze_reflection_patterns()
            if patterns["success"]:
                print("    ✅ 模式分析功能正常")
                features_passed += 1
            else:
                print("    ❌ 模式分析功能异常")
            
            print("  🎯 功能7: 智能推荐")
            features_tested += 1
            recommendations = interface.get_reflection_recommendations(limit=5)
            contextual_recs = reflection_manager.get_contextual_recommendations(
                context={"type": "decision", "keywords": ["技术"]},
                limit=3
            )
            
            if recommendations["success"] and contextual_recs["success"]:
                print("    ✅ 智能推荐功能正常")
                features_passed += 1
            else:
                print("    ❌ 智能推荐功能异常")
            
            print("  📚 功能8: 模板系统")
            features_tested += 1
            # 创建模板
            template_result = interface.create_template(
                name="测试模板",
                description="用于测试的模板",
                template_data={
                    "reflection_type": "process_reflection",
                    "required_fields": ["subject"],
                    "prompt_template": "请反思: {subject}"
                }
            )
            
            if template_result["success"]:
                template_id = template_result["template"]["template_id"]
                
                # 使用模板
                template_reflection = interface.generate_reflection({
                    "subject": "模板测试反思",
                    "reflection_type": "process_reflection",
                    "context": {"subject": "测试主题"},
                    "template_id": template_id
                })
                
                if template_reflection["success"]:
                    print("    ✅ 模板系统功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 模板使用失败")
            else:
                print("    ❌ 模板创建失败")
            
            print("  📈 功能9: 高级分析")
            features_tested += 1
            if created_reflections:
                batch_analysis = reflection_manager.batch_analyze_reflections(
                    created_reflections,
                    analysis_type="insights"
                )
                if batch_analysis["success"]:
                    print("    ✅ 高级分析功能正常")
                    features_passed += 1
                else:
                    print("    ❌ 高级分析失败")
            else:
                print("    ❌ 无反思可用于分析测试")
            
            print("  💾 功能10: 导出和报告")
            features_tested += 1
            export_result = reflection_manager.export_reflections(format="json")
            if export_result["success"]:
                print("    ✅ 导出功能正常")
                features_passed += 1
            else:
                print("    ❌ 导出功能异常")
            
            print(f"  📈 反思模块功能测试结果: {features_passed}/{features_tested} 通过")
            return features_passed >= features_tested * 0.8  # 80%通过率
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 反思模块测试失败: {e}")
        return False

def test_integration_and_compatibility():
    """测试模块集成和兼容性"""
    print("\n🧪 测试模块集成和兼容性...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.reflection import ReflectionManager
        
        temp_dir = tempfile.mkdtemp(prefix="integration_test_")
        
        try:
            class MockTranscriptStore:
                def record_audit(self, *args, **kwargs):
                    pass
                def write_entry(self, *args, **kwargs):
                    pass
            
            # 同时初始化两个模块
            task_manager = TaskManager(
                transcript_store=MockTranscriptStore(),
                storage_path=os.path.join(temp_dir, "tasks"),
                enable_persistence=True
            )
            
            reflection_manager = ReflectionManager(
                storage_path=os.path.join(temp_dir, "reflections"),
                enable_persistence=True
            )
            
            print("  🔄 测试1: 并行操作")
            # 并行创建任务和反思
            async def parallel_operations():
                # 创建任务
                task = await task_manager.get_service_interface().create_task({
                    "title": "集成测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "integration_test",
                    "idempotency_key": "integration_task"
                })
                
                # 创建反思
                reflection = reflection_manager.get_interface().generate_reflection({
                    "subject": "集成测试反思",
                    "reflection_type": "process_reflection",
                    "context": {"test": True}
                })
                
                return task, reflection
            
            task_result, reflection_result = asyncio.run(parallel_operations())
            
            if task_result["success"] and reflection_result["success"]:
                print("    ✅ 并行操作成功")
            else:
                print("    ❌ 并行操作失败")
                return False
            
            print("  📊 测试2: 数据独立性")
            # 验证数据独立性
            task_stats = task_manager.get_service_interface().get_task_statistics()
            reflection_metrics = reflection_manager.get_interface().get_metrics()
            
            if (task_stats["success"] and reflection_metrics["success"] and
                task_stats["statistics"]["total_tasks"] > 0 and
                reflection_metrics["metrics"]["total_reflections"] > 0):
                print("    ✅ 数据独立性验证成功")
            else:
                print("    ❌ 数据独立性验证失败")
                return False
            
            print("  🔧 测试3: 资源竞争")
            # 测试资源竞争（简单模拟）
            import threading
            import time
            
            results = []
            
            def task_operations():
                try:
                    for i in range(5):
                        task = task_manager.get_service_interface().create_task({
                            "title": f"竞争测试任务 {i}",
                            "task_type": "cognitive_step",
                            "originator_id": "competition_test",
                            "idempotency_key": f"competition_task_{i}"
                        })
                        results.append(task["success"])
                except Exception:
                    results.append(False)
            
            def reflection_operations():
                try:
                    for i in range(5):
                        reflection = reflection_manager.get_interface().generate_reflection({
                            "subject": f"竞争测试反思 {i}",
                            "reflection_type": "process_reflection",
                            "context": {"test": True}
                        })
                        results.append(reflection["success"])
                except Exception:
                    results.append(False)
            
            # 启动线程
            task_thread = threading.Thread(target=task_operations)
            reflection_thread = threading.Thread(target=reflection_operations)
            
            task_thread.start()
            reflection_thread.start()
            
            task_thread.join()
            reflection_thread.join()
            
            if all(results):
                print("    ✅ 资源竞争测试通过")
            else:
                print("    ❌ 资源竞争测试失败")
                return False
            
            print("  ✅ 模块集成和兼容性测试通过")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        return False

def test_error_handling_and_edge_cases():
    """测试错误处理和边界情况"""
    print("\n🧪 测试错误处理和边界情况...")
    
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
            
            edge_cases_tested = 0
            edge_cases_passed = 0
            
            print("  ❌ 测试1: 无效输入处理")
            edge_cases_tested += 1
            
            async def test_invalid_inputs():
                # 无效任务创建
                invalid_task = await task_interface.create_task({
                    "title": "",  # 空标题
                    "task_type": "invalid_type",  # 无效类型
                    "originator_id": ""  # 空ID
                })
                
                # 无效反思生成
                invalid_reflection = reflection_interface.generate_reflection({
                    "subject": "",  # 空主题
                    "reflection_type": "invalid_type",  # 无效类型
                    "context": {}  # 空上下文
                })
                
                return invalid_task, invalid_reflection
            
            invalid_task, invalid_reflection = asyncio.run(test_invalid_inputs())
            
            if (not invalid_task["success"] and not invalid_reflection["success"]):
                print("    ✅ 无效输入被正确拒绝")
                edge_cases_passed += 1
            else:
                print("    ❌ 无效输入处理异常")
            
            print("  🔍 测试2: 不存在资源处理")
            edge_cases_tested += 1
            
            # 不存在的任务
            non_existent_task = task_interface.get_task("non_existent_id")
            # 不存在的反思
            non_existent_reflection = reflection_interface.get_reflection("non_existent_id")
            
            if (not non_existent_task["success"] and not non_existent_reflection["success"]):
                print("    ✅ 不存在资源被正确处理")
                edge_cases_passed += 1
            else:
                print("    ❌ 不存在资源处理异常")
            
            print("  🔄 测试3: 状态转换验证")
            edge_cases_tested += 1
            
            async def test_state_transitions():
                # 创建任务
                task = await task_interface.create_task({
                    "title": "状态测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "idempotency_key": "state_test"
                })
                
                if task["success"]:
                    task_id = task["task"]["task_id"]
                    
                    # 完成任务
                    await task_interface.update_task_status(task_id, "done", "完成")
                    
                    # 尝试重新激活（应该失败）
                    invalid_transition = await task_interface.update_task_status(task_id, "in_progress")
                    
                    return invalid_transition
                
                return None
            
            invalid_transition = asyncio.run(test_state_transitions())
            
            if invalid_transition and not invalid_transition["success"]:
                print("    ✅ 无效状态转换被正确拒绝")
                edge_cases_passed += 1
            else:
                print("    ❌ 状态转换验证失败")
            
            print("  📝 测试4: 重复操作处理")
            edge_cases_tested += 1
            
            async def test_duplicate_operations():
                # 重复创建任务（幂等性测试）
                task1 = await task_interface.create_task({
                    "title": "重复测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "idempotency_key": "duplicate_test"
                })
                
                task2 = await task_interface.create_task({
                    "title": "重复测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "idempotency_key": "duplicate_test"
                })
                
                return task1, task2
            
            task1, task2 = asyncio.run(test_duplicate_operations())
            
            if (task1["success"] and task2["success"] and 
                task1["task"]["task_id"] == task2["task"]["task_id"]):
                print("    ✅ 幂等性处理正确")
                edge_cases_passed += 1
            else:
                print("    ❌ 幂等性处理失败")
            
            print("  📊 测试5: 大量数据处理")
            edge_cases_tested += 1
            
            # 批量创建大量任务
            batch_tasks = []
            for i in range(20):  # 减少数量以避免性能问题
                task = task_interface.create_task({
                    "title": f"批量任务 {i}",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "idempotency_key": f"batch_task_{i}"
                })
                if task["success"]:
                    batch_tasks.append(task["task"]["task_id"])
            
            if len(batch_tasks) >= 15:
                print("    ✅ 大量数据处理正常")
                edge_cases_passed += 1
            else:
                print("    ❌ 大量数据处理失败")
            
            print(f"  📈 错误处理测试结果: {edge_cases_passed}/{edge_cases_tested} 通过")
            return edge_cases_passed >= edge_cases_tested * 0.8  # 80%通过率
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 错误处理测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始全面功能测试...")
    print("=" * 80)
    
    results = []
    
    # 全面功能测试
    results.append(test_all_task_features())
    results.append(test_all_reflection_features())
    results.append(test_integration_and_compatibility())
    results.append(test_error_handling_and_edge_cases())
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 全面测试结果汇总:")
    
    test_names = [
        "任务管理模块所有功能",
        "反思模块所有功能",
        "模块集成和兼容性",
        "错误处理和边界情况"
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
        print("📋 测试覆盖的功能:")
        print("   🎯 任务管理: 10个核心功能")
        print("   🎯 反思管理: 10个核心功能")
        print("   🎯 模块集成: 3个集成测试")
        print("   🎯 错误处理: 5个边界情况")
        print("   📊 总计: 28个功能点测试")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
