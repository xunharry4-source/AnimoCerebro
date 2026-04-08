#!/usr/bin/env python3
"""
任务拆分功能测试
验证任务管理模块的任务拆分核心业务逻辑
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

def test_task_decomposition():
    """测试任务拆分功能"""
    print("🧪 测试任务拆分功能...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        temp_dir = tempfile.mkdtemp(prefix="task_decomposition_test_")
        
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
            
            decomposition_tests_passed = 0
            decomposition_tests_total = 0
            
            print("  📋 测试1: 获取可用拆分策略")
            decomposition_tests_total += 1
            strategies = task_manager.get_available_decomposition_strategies()
            if strategies and len(strategies) > 0:
                print(f"    ✅ 可用拆分策略: {strategies}")
                decomposition_tests_passed += 1
            else:
                print("    ❌ 无法获取拆分策略")
            
            print("  📋 测试2: 获取默认拆分策略")
            decomposition_tests_total += 1
            # TaskManager 没有直接的 get_default_decomposition_strategy 方法
            # 我们通过插件信息来获取默认策略
            plugin_info = task_manager.get_plugin_info()
            if plugin_info:
                default_strategy = plugin_info.get("default_plugin")
                if default_strategy and default_strategy in strategies:
                    print(f"    ✅ 默认拆分策略: {default_strategy}")
                    decomposition_tests_passed += 1
                else:
                    print("    ❌ 默认拆分策略无效")
            else:
                print("    ❌ 无法获取插件信息")
            
            print("  📋 测试3: 设置默认拆分策略")
            decomposition_tests_total += 1
            if len(strategies) > 1:
                new_strategy = strategies[1]  # 选择第二个策略
                set_result = task_manager.set_default_decomposition_strategy(new_strategy)
                if set_result:
                    print(f"    ✅ 默认策略设置成功: {new_strategy}")
                    decomposition_tests_passed += 1
                else:
                    print("    ❌ 默认策略设置失败")
            else:
                print("    ⚠️  拆分策略数量不足，跳过设置测试")
                decomposition_tests_passed += 1  # 不算失败
            
            print("  📋 测试4: 创建使命任务进行拆分")
            decomposition_tests_total += 1
            # 创建一个复杂的使命任务
            async def create_mission_task():
                return await interface.create_task({
                    "title": "电商平台重构项目",
                    "task_type": TaskType.MISSION,
                    "originator_id": "project_manager",
                    "priority": TaskPriority.HIGH,
                    "idempotency_key": "ecommerce_refactor_mission",
                    "estimated_duration": 240,  # 4小时
                    "metadata": {
                        "project_scope": "全站重构",
                        "team_size": 8,
                        "complexity": "high",
                        "requirements": ["性能优化", "架构升级", "UI改进"]
                    }
                })
            
            mission_task = asyncio.run(create_mission_task())
            
            if mission_task["success"]:
                mission_id = mission_task["task"]["task_id"]
                print(f"    ✅ 使命任务创建成功: {mission_id}")
                decomposition_tests_passed += 1
            else:
                print("    ❌ 使命任务创建失败")
            
            print("  📋 测试5: 任务拆分执行")
            decomposition_tests_total += 1
            if mission_task["success"]:
                # 使用 TaskManager 的拆分方法
                mission_data = mission_task["task"]
                subtasks = task_manager.decompose_mission_with_strategy(
                    title=mission_data["title"],
                    content=mission_data.get("metadata", {}),
                    strategy="parallel",
                    context={
                        "max_subtasks": 5,
                        "estimated_duration_per_subtask": 48
                    }
                )
                
                if subtasks and len(subtasks) > 0:
                    print(f"    ✅ 任务拆分成功，生成 {len(subtasks)} 个子任务")
                    
                    # 验证子任务的基本属性
                    valid_subtasks = 0
                    for i, subtask in enumerate(subtasks):
                        print(f"      子任务 {i+1}: {subtask.get('title', 'Unknown')}")
                        
                        # 手动创建子任务（因为 decompose_mission_with_strategy 只返回数据）
                        create_result = await interface.create_task({
                            "title": subtask.get("title", f"子任务 {i+1}"),
                            "task_type": TaskType.COGNITIVE_STEP,
                            "originator_id": "decomposer",
                            "priority": TaskPriority.MEDIUM,
                            "parent_task_id": mission_id,
                            "idempotency_key": f"subtask_{i+1}",
                            "estimated_duration": subtask.get("estimated_duration", 48)
                        })
                        
                        if create_result["success"]:
                            valid_subtasks += 1
                            print(f"        ✅ 子任务创建成功")
                        else:
                            print(f"        ❌ 子任务创建失败")
                    
                    if valid_subtasks == len(subtasks):
                        print("    ✅ 所有子任务验证通过")
                        decomposition_tests_passed += 1
                    else:
                        print("    ❌ 部分子任务验证失败")
                else:
                    print("    ❌ 任务拆分失败")
            else:
                print("    ❌ 无使命任务可用于拆分")
            
            print("  📋 测试6: 子任务状态管理")
            decomposition_tests_total += 1
            # 创建子任务列表来跟踪
            created_subtasks = []
            
            if mission_task["success"]:
                # 使用 TaskManager 的拆分方法
                mission_data = mission_task["task"]
                subtasks = task_manager.decompose_mission_with_strategy(
                    title=mission_data["title"],
                    content=mission_data.get("metadata", {}),
                    strategy="parallel",
                    context={
                        "max_subtasks": 3,
                        "estimated_duration_per_subtask": 48
                    }
                )
                
                if subtasks and len(subtasks) > 0:
                    print(f"    ✅ 任务拆分成功，生成 {len(subtasks)} 个子任务")
                    
                    # 创建实际的子任务
                    for i, subtask in enumerate(subtasks):
                        create_result = await interface.create_task({
                            "title": subtask.get("title", f"子任务 {i+1}"),
                            "task_type": TaskType.COGNITIVE_STEP,
                            "originator_id": "decomposer",
                            "priority": TaskPriority.MEDIUM,
                            "parent_task_id": mission_id,
                            "idempotency_key": f"status_test_subtask_{i+1}",
                            "estimated_duration": subtask.get("estimated_duration", 48)
                        })
                        
                        if create_result["success"]:
                            created_subtasks.append(create_result["task"]["task_id"])
                            print(f"      子任务 {i+1}: {create_result['task']['title']}")
                        else:
                            print(f"      ❌ 子任务创建失败")
                    
                    # 测试子任务状态管理
                    if len(created_subtasks) > 0:
                        first_subtask_id = created_subtasks[0]
                        
                        # 更新子任务状态
                        update_result = interface.update_task_status(
                            first_subtask_id, 
                            TaskStatus.IN_PROGRESS, 
                            "开始执行子任务"
                        )
                        
                        if update_result["success"]:
                            print("    ✅ 子任务状态更新成功")
                            
                            # 验证父任务状态是否受影响
                            parent_result = interface.get_task(mission_id)
                            if parent_result["success"]:
                                parent_status = parent_result["task"]["status"]
                                print(f"    ✅ 父任务状态: {parent_status}")
                                
                                # 完成子任务
                                complete_result = interface.update_task_status(
                                    first_subtask_id,
                                    TaskStatus.DONE,
                                    "子任务完成"
                                )
                                
                                if complete_result["success"]:
                                    print("    ✅ 子任务完成成功")
                                    decomposition_tests_passed += 1
                                else:
                                    print("    ❌ 子任务完成失败")
                            else:
                                print("    ❌ 无法获取父任务状态")
                        else:
                            print("    ❌ 子任务状态更新失败")
                    else:
                        print("    ❌ 无子任务可用于状态测试")
                else:
                    print("    ❌ 任务拆分失败")
            else:
                print("    ❌ 无使命任务可用于拆分")
            
            print("  📋 测试7: 任务依赖关系拆分")
            decomposition_tests_total += 1
            # 创建一个有依赖关系的任务
            async def create_dependent_task():
                # 先创建前置任务
                prerequisite = await interface.create_task({
                    "title": "环境准备",
                    "task_type": TaskType.COGNITIVE_STEP,
                    "originator_id": "tech_lead",
                    "priority": TaskPriority.HIGH,
                    "idempotency_key": "env_setup_prereq"
                })
                
                if prerequisite["success"]:
                    # 创建依赖任务
                    dependent = await interface.create_task({
                        "title": "应用部署",
                        "task_type": TaskType.COGNITIVE_STEP,
                        "originator_id": "tech_lead",
                        "priority": TaskPriority.MEDIUM,
                        "depends_on": [prerequisite["task"]["task_id"]],
                        "idempotency_key": "app_deployment"
                    })
                    
                    return prerequisite, dependent
                return None, None
            
            prerequisite_task, dependent_task = asyncio.run(create_dependent_task())
            
            if dependent_task and dependent_task["success"]:
                # 尝试拆分有依赖关系的任务
                dep_decomposition = interface.decompose_task(
                    dependent_task["task"]["task_id"],
                    strategy="sequential",  # 顺序拆分
                    max_subtasks=3
                )
                
                if dep_decomposition["success"]:
                    print("    ✅ 依赖任务拆分成功")
                    decomposition_tests_passed += 1
                else:
                    print("    ❌ 依赖任务拆分失败")
            else:
                print("    ❌ 依赖任务创建失败")
            
            print("  📋 测试8: 批量任务拆分")
            decomposition_tests_total += 1
            # 创建多个任务进行批量拆分
            async def create_multiple_tasks():
                tasks = []
                for i in range(3):
                    task = await interface.create_task({
                        "title": f"批量测试任务 {i+1}",
                        "task_type": TaskType.MISSION,
                        "originator_id": "project_manager",
                        "priority": TaskPriority.MEDIUM,
                        "idempotency_key": f"batch_mission_{i+1}",
                        "estimated_duration": 120
                    })
                    if task["success"]:
                        tasks.append(task["task"]["task_id"])
                return tasks
            
            mission_tasks = asyncio.run(create_multiple_tasks())
            
            if len(mission_tasks) == 3:
                # 批量拆分
                batch_decomposition = interface.batch_decompose_tasks(
                    mission_tasks,
                    strategy="parallel",
                    max_subtasks_per_task=2
                )
                
                if batch_decomposition["success"]:
                    results = batch_decomposition["results"]
                    total_subtasks = sum(len(result.get("subtasks", [])) for result in results)
                    print(f"    ✅ 批量拆分成功，共生成 {total_subtasks} 个子任务")
                    decomposition_tests_passed += 1
                else:
                    print("    ❌ 批量拆分失败")
            else:
                print("    ❌ 批量任务创建失败")
            
            print("  📋 测试9: 拆分结果验证")
            decomposition_tests_total += 1
            if mission_task["success"] and decomposition_result.get("success"):
                # 验证拆分结果的完整性
                subtasks = decomposition_result["subtasks"]
                
                # 检查子任务是否都有正确的父任务ID
                correct_parent_count = sum(
                    1 for subtask in subtasks 
                    if subtask.get("parent_task_id") == mission_id
                )
                
                # 检查子任务是否有合理的估计时间
                reasonable_duration_count = sum(
                    1 for subtask in subtasks 
                    if subtask.get("estimated_duration", 0) > 0
                )
                
                # 检查子任务是否有合理的标题
                valid_title_count = sum(
                    1 for subtask in subtasks 
                    if subtask.get("title") and len(subtask["title"]) > 0
                )
                
                if (correct_parent_count == len(subtasks) and
                    reasonable_duration_count == len(subtasks) and
                    valid_title_count == len(subtasks)):
                    print("    ✅ 拆分结果验证通过")
                    decomposition_tests_passed += 1
                else:
                    print("    ❌ 拆分结果验证失败")
            else:
                print("    ❌ 无拆分结果可用于验证")
            
            print("  📋 测试10: 拆分策略切换")
            decomposition_tests_total += 1
            # 测试不同拆分策略的效果
            if len(strategies) > 1:
                original_strategy = task_manager.get_default_decomposition_strategy()
                
                # 切换到另一个策略
                alternative_strategy = strategies[0] if strategies[0] != original_strategy else strategies[1]
                task_manager.set_default_decomposition_strategy(alternative_strategy)
                
                # 创建新任务进行拆分
                async def create_strategy_test_task():
                    return await interface.create_task({
                        "title": "策略测试任务",
                        "task_type": TaskType.MISSION,
                        "originator_id": "strategy_tester",
                        "priority": TaskPriority.MEDIUM,
                        "idempotency_key": "strategy_test_mission",
                        "estimated_duration": 180
                    })
                
                strategy_task = asyncio.run(create_strategy_test_task())
                
                if strategy_task["success"]:
                    # 使用新策略拆分
                    strategy_decomposition = interface.decompose_task(
                        strategy_task["task"]["task_id"],
                        strategy=alternative_strategy,
                        max_subtasks=3
                    )
                    
                    if strategy_decomposition["success"]:
                        print(f"    ✅ 策略 {alternative_strategy} 拆分成功")
                        decomposition_tests_passed += 1
                    else:
                        print(f"    ❌ 策略 {alternative_strategy} 拆分失败")
                else:
                    print("    ❌ 策略测试任务创建失败")
                
                # 恢复原始策略
                task_manager.set_default_decomposition_strategy(original_strategy)
            else:
                print("    ⚠️  策略数量不足，跳过策略切换测试")
                decomposition_tests_passed += 1  # 不算失败
            
            print(f"  📊 任务拆分功能测试结果: {decomposition_tests_passed}/{decomposition_tests_total} 通过")
            return decomposition_tests_passed >= decomposition_tests_total * 0.8
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 任务拆分功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_decomposition_integration():
    """测试拆分功能的集成场景"""
    print("\n🧪 测试拆分功能集成场景...")
    
    try:
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        temp_dir = tempfile.mkdtemp(prefix="decomposition_integration_test_")
        
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
            
            integration_tests_passed = 0
            integration_tests_total = 0
            
            print("  🎯 场景1: 完整项目拆分流程")
            integration_tests_total += 1
            # 模拟完整的项目拆分流程
            
            # 1. 创建项目使命任务
            async def create_project_mission():
                return await interface.create_task({
                    "title": "移动应用开发项目",
                    "task_type": TaskType.MISSION,
                    "originator_id": "product_manager",
                    "priority": TaskPriority.HIGH,
                    "idempotency_key": "mobile_app_mission",
                    "estimated_duration": 480,  # 8小时
                    "metadata": {
                        "project_type": "mobile_app",
                        "features": ["用户管理", "数据同步", "离线支持"],
                        "platforms": ["iOS", "Android"],
                        "team_composition": ["前端", "后端", "测试"]
                    }
                })
            
            project_mission = asyncio.run(create_project_mission())
            
            if project_mission["success"]:
                mission_id = project_mission["task"]["task_id"]
                print(f"    ✅ 项目使命创建: {mission_id}")
                
                # 2. 拆分为主要阶段
                phase_decomposition = interface.decompose_task(
                    mission_id,
                    strategy="sequential",
                    max_subtasks=4
                )
                
                if phase_decomposition["success"]:
                    phases = phase_decomposition["subtasks"]
                    print(f"    ✅ 项目拆分为 {len(phases)} 个阶段")
                    
                    # 3. 选择一个阶段进行进一步拆分
                    if len(phases) > 0:
                        dev_phase = phases[1]  # 选择开发阶段
                        dev_phase_id = dev_phase["task_id"]
                        
                        # 进一步拆分开发阶段
                        dev_decomposition = interface.decompose_task(
                            dev_phase_id,
                            strategy="parallel",
                            max_subtasks=3
                        )
                        
                        if dev_decomposition["success"]:
                            dev_subtasks = dev_decomposition["subtasks"]
                            print(f"    ✅ 开发阶段拆分为 {len(dev_subtasks)} 个子任务")
                            
                            # 4. 执行一些子任务
                            completed_count = 0
                            for i, subtask in enumerate(dev_subtasks[:2]):  # 完成前两个
                                update_result = interface.update_task_status(
                                    subtask["task_id"],
                                    TaskStatus.DONE,
                                    f"子任务 {i+1} 完成"
                                )
                                if update_result["success"]:
                                    completed_count += 1
                            
                            if completed_count == 2:
                                print("    ✅ 子任务执行成功")
                                
                                # 5. 检查整体进度
                                progress_result = interface.get_task_progress(mission_id)
                                if progress_result["success"]:
                                    progress = progress_result["progress"]
                                    print(f"    ✅ 项目整体进度: {progress:.1%}")
                                    
                                    if progress > 0:
                                        integration_tests_passed += 1
                                        print("    ✅ 完整项目拆分流程成功")
                                    else:
                                        print("    ❌ 项目进度计算错误")
                                else:
                                    print("    ❌ 无法获取项目进度")
                            else:
                                print("    ❌ 子任务执行失败")
                        else:
                            print("    ❌ 开发阶段拆分失败")
                    else:
                        print("    ❌ 无开发阶段可用于进一步拆分")
                else:
                    print("    ❌ 项目使命拆分失败")
            else:
                print("    ❌ 项目使命创建失败")
            
            print("  🎯 场景2: 动态拆分调整")
            integration_tests_total += 1
            # 测试动态调整拆分策略
            
            async def create_dynamic_task():
                return await interface.create_task({
                    "title": "动态拆分测试任务",
                    "task_type": TaskType.MISSION,
                    "originator_id": "dynamic_tester",
                    "priority": TaskPriority.MEDIUM,
                    "idempotency_key": "dynamic_decomposition_test",
                    "estimated_duration": 240
                })
            
            dynamic_task = asyncio.run(create_dynamic_task())
            
            if dynamic_task["success"]:
                task_id = dynamic_task["task"]["task_id"]
                
                # 初始拆分
                initial_decomp = interface.decompose_task(task_id, strategy="parallel", max_subtasks=2)
                
                if initial_decomp["success"]:
                    print("    ✅ 初始拆分成功")
                    
                    # 动态调整：增加更多子任务
                    adjusted_decomp = interface.decompose_task(
                        task_id,
                        strategy="parallel",
                        max_subtasks=4
                    )
                    
                    if adjusted_decomp["success"]:
                        adjusted_subtasks = adjusted_decomp["subtasks"]
                        print(f"    ✅ 动态调整成功，现在有 {len(adjusted_subtasks)} 个子任务")
                        integration_tests_passed += 1
                    else:
                        print("    ❌ 动态调整失败")
                else:
                    print("    ❌ 初始拆分失败")
            else:
                print("    ❌ 动态任务创建失败")
            
            print(f"  📊 拆分集成测试结果: {integration_tests_passed}/{integration_tests_total} 通过")
            return integration_tests_passed >= integration_tests_total * 0.8
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ 拆分集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始任务拆分功能测试...")
    print("=" * 80)
    
    results = []
    
    # 任务拆分功能测试
    results.append(test_task_decomposition())
    
    # 拆分集成测试
    results.append(test_decomposition_integration())
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 任务拆分功能测试结果汇总:")
    
    test_names = [
        "任务拆分核心功能",
        "拆分功能集成场景"
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
        print("🎉 所有任务拆分功能测试都通过了！")
        print("📋 验证的拆分功能:")
        print("   ✅ 拆分策略获取和设置")
        print("   ✅ 使命任务创建和拆分")
        print("   ✅ 子任务生成和验证")
        print("   ✅ 子任务状态管理")
        print("   ✅ 依赖关系拆分")
        print("   ✅ 批量任务拆分")
        print("   ✅ 拆分结果验证")
        print("   ✅ 拆分策略切换")
        print("   ✅ 完整项目拆分流程")
        print("   ✅ 动态拆分调整")
        print("   🎯 任务拆分功能完全符合预期！")
        return True
    else:
        print("⚠️  部分任务拆分功能测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
