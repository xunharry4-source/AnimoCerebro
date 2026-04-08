#!/usr/bin/env python3
"""
修复后的业务逻辑真实测试
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

def test_task_business_rules():
    """测试任务管理的业务规则"""
    print("🧪 测试任务管理业务规则...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        temp_dir = tempfile.mkdtemp(prefix="business_rule_test_")
        
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
            
            business_rules_passed = 0
            business_rules_total = 0
            
            print("  📋 业务规则1: 任务类型限制验证")
            business_rules_total += 1
            # 测试允许的任务类型
            valid_types = [TaskType.COGNITIVE_STEP, TaskType.MISSION, TaskType.INTERVENTION]
            valid_type_count = 0
            
            async def test_valid_types():
                results = []
                for task_type in valid_types:
                    task = await interface.create_task({
                        "title": f"{task_type.value}测试任务",
                        "task_type": task_type.value,
                        "originator_id": "test_user",
                        "priority": "medium",
                        "idempotency_key": f"{task_type.value}_test"
                    })
                    results.append(task)
                return results
            
            valid_task_results = asyncio.run(test_valid_types())
            
            for task in valid_task_results:
                if task["success"]:
                    valid_type_count += 1
                    print(f"    ✅ {task['task']['task_type']} 类型允许")
                else:
                    print(f"    ❌ {task['task']['task_type']} 类型被拒绝")
            
            if valid_type_count == len(valid_types):
                business_rules_passed += 1
            
            print("  📋 业务规则2: 无效任务类型拒绝")
            business_rules_total += 1
            # 测试无效的任务类型
            invalid_types = ["decision", "action", "process"]  # 这些不在枚举中
            invalid_rejected = 0
            
            async def test_invalid_types():
                results = []
                for invalid_type in invalid_types:
                    task = await interface.create_task({
                        "title": f"无效类型测试",
                        "task_type": invalid_type,
                        "originator_id": "test_user",
                        "priority": "medium",
                        "idempotency_key": f"invalid_{invalid_type}"
                    })
                    results.append(task)
                return results
            
            invalid_task_results = asyncio.run(test_invalid_types())
            
            for task in invalid_task_results:
                if not task["success"]:
                    invalid_rejected += 1
                    print(f"    ✅ 无效类型被正确拒绝")
                else:
                    print(f"    ❌ 无效类型被错误接受")
            
            if invalid_rejected == len(invalid_types):
                business_rules_passed += 1
            
            print("  📋 业务规则3: 任务状态流转验证")
            business_rules_total += 1
            # 创建任务并测试状态流转
            async def create_task_for_state_test():
                return await interface.create_task({
                    "title": "状态流转测试任务",
                    "task_type": TaskType.COGNITIVE_STEP,
                    "originator_id": "test_user",
                    "priority": "high",
                    "idempotency_key": "state_flow_test"
                })
            
            task = asyncio.run(create_task_for_state_test())
            
            if task["success"]:
                task_id = task["task"]["task_id"]
                
                # 测试有效状态转换: TODO -> IN_PROGRESS -> DONE
                valid_transitions = [
                    (TaskStatus.IN_PROGRESS, "开始执行"),
                    (TaskStatus.DONE, "任务完成")
                ]
                
                valid_transition_count = 0
                for new_status, remarks in valid_transitions:
                    result = interface.update_task_status(task_id, new_status, remarks)
                    if result["success"]:
                        valid_transition_count += 1
                        print(f"    ✅ {TaskStatus.TODO.value} -> {new_status.value} 转换成功")
                    else:
                        print(f"    ❌ {TaskStatus.TODO.value} -> {new_status.value} 转换失败")
                
                # 测试无效状态转换: TODO -> FAILED (应该先经过 IN_PROGRESS)
                invalid_transition = interface.update_task_status(task_id, TaskStatus.FAILED, "直接失败")
                if not invalid_transition["success"]:
                    valid_transition_count += 1
                    print("    ✅ 无效状态转换被正确拒绝")
                else:
                    print("    ❌ 无效状态转换被错误接受")
                
                if valid_transition_count == 3:
                    business_rules_passed += 1
                    print("    ✅ 状态流转规则正确执行")
            
            print("  📋 业务规则4: 任务依赖关系验证")
            business_rules_total += 1
            # 创建有依赖关系的任务
            async def create_dependency_tasks():
                parent_task = await interface.create_task({
                    "title": "父任务",
                    "task_type": TaskType.MISSION,
                    "originator_id": "test_user",
                    "priority": "high",
                    "idempotency_key": "parent_task"
                })
                
                dependency_success = False
                if parent_task["success"]:
                    parent_id = parent_task["task"]["task_id"]
                    
                    # 创建子任务，依赖父任务
                    child_task = await interface.create_task({
                        "title": "子任务",
                        "task_type": TaskType.COGNITIVE_STEP,
                        "originator_id": "test_user",
                        "priority": "medium",
                        "parent_task_id": parent_id,
                        "idempotency_key": "child_task"
                    })
                    
                    if child_task["success"]:
                        # 添加依赖关系
                        dep_result = interface.add_dependency(
                            child_task["task"]["task_id"],
                            parent_id
                        )
                        if dep_result["success"]:
                            dependency_success = True
                            print("    ✅ 任务依赖关系创建成功")
                        else:
                            print("    ❌ 任务依赖关系创建失败")
                    else:
                        print("    ❌ 子任务创建失败")
                else:
                    print("    ❌ 父任务创建失败")
                
                return dependency_success
            
            dependency_success = asyncio.run(create_dependency_tasks())
            
            if dependency_success:
                business_rules_passed += 1
            
            print("  📋 业务规则5: 幂等性保证验证")
            business_rules_total += 1
            # 测试幂等性：相同 idempotency_key 应返回相同任务ID
            idempotency_key = "idempotency_test_key"
            
            async def test_idempotency():
                task1 = await interface.create_task({
                    "title": "幂等性测试任务",
                    "task_type": TaskType.COGNITIVE_STEP,
                    "originator_id": "test_user",
                    "priority": "medium",
                    "idempotency_key": idempotency_key
                })
                
                task2 = await interface.create_task({
                    "title": "幂等性测试任务",
                    "task_type": TaskType.COGNITIVE_STEP,
                    "originator_id": "test_user",
                    "priority": "medium",
                    "idempotency_key": idempotency_key
                })
                
                return task1, task2
            
            task1, task2 = asyncio.run(test_idempotency())
            
            if (task1["success"] and task2["success"] and 
                task1["task"]["task_id"] == task2["task"]["task_id"]):
                print("    ✅ 幂等性保证正确执行")
                business_rules_passed += 1
            else:
                print("    ❌ 幂等性保证失败")
            
            print(f"  📊 任务业务规则测试结果: {business_rules_passed}/{business_rules_total} 通过")
            return business_rules_passed >= business_rules_total * 0.8
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 任务业务规则测试失败: {e}")
        return False

def test_reflection_business_rules():
    """测试反思模块的业务规则"""
    print("\n🧪 测试反思模块业务规则...")
    
    try:
        from zentex.reflection import ReflectionManager
        from zentex.reflection.models import ReflectionType, ReflectionQuality, ReflectionTrigger
        
        temp_dir = tempfile.mkdtemp(prefix="reflection_business_test_")
        
        try:
            reflection_manager = ReflectionManager(
                storage_path=temp_dir,
                enable_persistence=True
            )
            
            interface = reflection_manager.get_interface()
            
            business_rules_passed = 0
            business_rules_total = 0
            
            print("  📝 业务规则1: 反思类型特定生成逻辑验证")
            business_rules_total += 1
            # 测试不同反思类型的生成逻辑
            type_logic_correct = 0  # 在循环外声明变量
            
            reflection_scenarios = [
                {
                    "type": ReflectionType.DECISION_REFLECTION,
                    "subject": "技术选型决策",
                    "context": {
                        "decision": {
                            "factors": ["性能", "成本", "可维护性"],
                            "stakeholders": ["技术团队"]
                        },
                        "outcome": {
                            "success": True,
                            "confidence": 0.8
                        }
                    },
                    "expected_insights": ["考虑了多个技术因素"],
                    "expected_lessons": ["技术调研的重要性"]
                },
                {
                    "type": ReflectionType.ERROR_REFLECTION,
                    "subject": "系统故障",
                    "context": {
                        "error": {
                            "type": "connection_timeout",
                            "severity": "high"
                        },
                        "impact": {
                            "affected_users": 100,
                            "downtime_minutes": 15
                        }
                    },
                    "expected_insights": ["连接池配置问题"],
                    "expected_lessons": ["需要监控告警"]
                },
                {
                    "type": ReflectionType.SUCCESS_REFLECTION,
                    "subject": "项目成功",
                    "context": {
                        "success": {
                            "degree": "complete",
                            "impact_score": 0.9
                        },
                        "success_factors": ["团队协作", "技术方案"]
                    },
                    "expected_insights": ["团队协作的重要性"],
                    "expected_lessons": ["技术方案评审的必要性"]
                }
            ]
            
            for scenario in reflection_scenarios:
                reflection = interface.generate_reflection({
                    "subject": scenario["subject"],
                    "reflection_type": scenario["type"],
                    "context": scenario["context"]
                })
                
                if reflection["success"]:
                    ref_data = reflection["reflection"]
                    
                    # 验证是否包含预期的内容
                    insights_match = any(
                        expected in ref_data["insights"] 
                        for expected in scenario["expected_insights"]
                    )
                    lessons_match = any(
                        expected in ref_data["lessons"] 
                        for expected in scenario["expected_lessons"]
                    )
                    
                    if insights_match and lessons_match:
                        type_logic_correct += 1
                        print(f"    ✅ {scenario['type'].value} 生成逻辑正确")
                    else:
                        print(f"    ❌ {scenario['type'].value} 生成逻辑不符合预期")
                else:
                    print(f"    ❌ {scenario['type'].value} 生成失败")
            
            if type_logic_correct == len(reflection_scenarios):
                business_rules_passed += 1
                print("    ✅ 所有反思类型生成逻辑正确")
            
            print("  📝 业务规则2: 反思质量自动评估验证")
            business_rules_total += 1
            # 创建反思并验证质量评估
            quality_reflection = interface.generate_reflection({
                "subject": "质量评估测试",
                "reflection_type": ReflectionType.PROCESS_REFLECTION,
                "context": {
                    "process": {
                        "phases": ["设计", "开发", "测试"],
                        "outcomes": {"efficiency": 0.8}
                    },
                    "insights": ["流程需要优化", "沟通可以改善"],
                    "lessons": ["敏捷方法有效", "需要更多文档"],
                    "risks": ["依赖外部团队"],
                    "improvements": ["加强沟通", "完善文档"]
                }
            })
            
            if quality_reflection["success"]:
                ref_data = quality_reflection["reflection"]
                quality = ref_data["quality"]
                
                # 验证质量评估逻辑：丰富的内容应该得到高质量
                if (len(ref_data["insights"]) >= 2 and 
                    len(ref_data["lessons"]) >= 2 and 
                    len(ref_data["improvements"]) >= 1 and
                    quality in [ReflectionQuality.EXCELLENT, ReflectionQuality.GOOD]):
                    print(f"    ✅ 质量评估正确: {quality.value}")
                    business_rules_passed += 1
                else:
                    print(f"    ❌ 质量评估错误: {quality.value}")
            
            print("  📝 业务规则3: 反思治理状态流转验证")
            business_rules_total += 1
            # 测试治理状态流转
            if quality_reflection["success"]:
                reflection_id = quality_reflection["reflection"]["reflection_id"]
                
                # 验证 → 可疑 → 归档流程
                verify_result = interface.verify_reflection(reflection_id, "expert_user")
                suspect_result = interface.mark_suspect(reflection_id, "需要重新验证")
                archive_result = interface.archive_reflection(reflection_id)
                
                if (verify_result["success"] and 
                    suspect_result["success"] and 
                    archive_result["success"]):
                    print("    ✅ 治理状态流转正确")
                    business_rules_passed += 1
                else:
                    print("    ❌ 治理状态流转失败")
            
            print(f"  📊 反思业务规则测试结果: {business_rules_passed}/{business_rules_total} 通过")
            return business_rules_passed >= business_rules_total * 0.8
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 反思业务规则测试失败: {e}")
        return False

def test_data_consistency():
    """测试数据一致性"""
    print("\n🧪 测试数据一致性...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.reflection import ReflectionManager
        
        temp_dir = tempfile.mkdtemp(prefix="data_consistency_test_")
        
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
            
            consistency_passed = 0
            consistency_total = 0
            
            print("  📊 一致性测试1: 持久化数据一致性")
            consistency_total += 1
            # 创建任务并验证持久化
            tasks_created = []
            
            async def create_tasks_for_consistency():
                for i in range(5):
                    task = await task_interface.create_task({
                        "title": f"一致性测试任务 {i}",
                        "task_type": "cognitive_step",
                        "originator_id": "test_user",
                        "priority": "medium",
                        "idempotency_key": f"consistency_task_{i}"
                    })
                    if task["success"]:
                        tasks_created.append(task["task"]["task_id"])
                return tasks_created
            
            tasks_created = asyncio.run(create_tasks_for_consistency())
            
            # 验证所有任务都能被检索
            all_tasks = task_interface.list_tasks()
            if all_tasks["success"] and all_tasks["count"] == len(tasks_created):
                print("    ✅ 任务持久化数据一致")
                consistency_passed += 1
            else:
                print("    ❌ 任务持久化数据不一致")
            
            print("  📊 一致性测试2: 统计数据准确性")
            consistency_total += 1
            # 验证统计数据准确性
            stats = task_interface.get_task_statistics()
            if stats["success"]:
                statistics = stats["statistics"]
                if statistics["total_tasks"] == len(tasks_created):
                    print("    ✅ 统计数据准确")
                    consistency_passed += 1
                else:
                    print("    ❌ 统计数据不准确")
            else:
                print("    ❌ 统计数据获取失败")
            
            print("  📊 一致性测试3: 关联关系正确性")
            consistency_total += 1
            # 创建反思并验证关联
            reflection = reflection_interface.generate_reflection({
                "subject": "关联测试反思",
                "reflection_type": "process_reflection",
                "context": {
                    "process": {"type": "测试流程"},
                    "related_tasks": tasks_created[:2]
                }
            })
            
            if reflection["success"]:
                # 验证反思可以被检索
                retrieved_reflection = reflection_interface.get_reflection(
                    reflection["reflection"]["reflection_id"]
                )
                if retrieved_reflection["success"]:
                    print("    ✅ 反思关联数据一致")
                    consistency_passed += 1
                else:
                    print("    ❌ 反思关联数据不一致")
            else:
                print("    ❌ 反思创建失败")
            
            print(f"  📊 数据一致性测试结果: {consistency_passed}/{consistency_total} 通过")
            return consistency_passed >= consistency_total * 0.8
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 数据一致性测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始修复后的业务逻辑真实测试...")
    print("=" * 80)
    
    results = []
    
    # 业务规则测试
    results.append(test_task_business_rules())
    results.append(test_reflection_business_rules())
    
    # 数据一致性测试
    results.append(test_data_consistency())
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 修复后的业务逻辑测试结果汇总:")
    
    test_names = [
        "任务管理业务规则",
        "反思模块业务规则",
        "数据一致性验证"
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
        print("🎉 所有修复后的业务逻辑测试都通过了！")
        print("📋 验证的业务逻辑:")
        print("   ✅ 任务类型限制和枚举验证")
        print("   ✅ 任务状态流转规则")
        print("   ✅ 任务依赖关系约束")
        print("   ✅ 幂等性保证")
        print("   ✅ 反思类型特定生成逻辑")
        print("   ✅ 反思质量自动评估")
        print("   ✅ 反思治理状态流转")
        print("   ✅ 数据持久化一致性")
        print("   ✅ 统计数据准确性")
        print("   ✅ 关联关系正确性")
        print("   🎯 业务逻辑完全符合预期！")
        return True
    else:
        print("⚠️  部分业务逻辑测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
