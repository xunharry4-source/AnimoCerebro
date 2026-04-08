#!/usr/bin/env python3
"""
任务管理模块和反思模块的基本功能测试
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import tempfile
import shutil

# 添加src路径
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

def test_task_management_module():
    """测试任务管理模块基本功能"""
    print("🧪 测试任务管理模块...")
    
    try:
        # 导入任务管理模块
        from zentex.tasks import TaskManager
        from zentex.tasks.models import TaskStatus, TaskType, TaskPriority
        
        print("✅ 成功导入任务管理模块")
        
        # 创建临时存储目录
        temp_dir = tempfile.mkdtemp(prefix="task_test_")
        
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
            
            print("✅ 成功创建TaskManager")
            
            # 获取统一接口
            interface = task_manager.get_service_interface()
            print("✅ 成功获取统一接口")
            
            # 测试创建任务
            import asyncio
            async def test_create_task():
                return await interface.create_task({
                    "title": "测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "test_user",
                    "priority": "high",
                    "idempotency_key": "test_task_key"
                })
            
            task_result = asyncio.run(test_create_task())
            
            if task_result["success"]:
                task_id = task_result["task"]["task_id"]
                print(f"✅ 成功创建任务: {task_id}")
                
                # 测试获取任务
                get_result = interface.get_task(task_id)
                if get_result["success"]:
                    print("✅ 成功获取任务信息")
                else:
                    print("❌ 获取任务失败")
                    return False
                
                # 测试更新任务状态
                update_result = interface.update_task_status(task_id, "in_progress", "开始执行")
                if update_result["success"]:
                    print("✅ 成功更新任务状态")
                else:
                    print("❌ 更新任务状态失败")
                    return False
                
                # 测试列出任务
                list_result = interface.list_tasks()
                if list_result["success"] and list_result["count"] > 0:
                    print(f"✅ 成功列出任务，共 {list_result['count']} 个")
                else:
                    print("❌ 列出任务失败")
                    return False
                
                # 测试插件系统
                strategies = task_manager.get_available_decomposition_strategies()
                if strategies:
                    print(f"✅ 成功获取拆解策略: {strategies}")
                else:
                    print("⚠️  未获取到拆解策略")
                
                # 测试统计功能
                stats = interface.get_task_statistics()
                if stats["success"]:
                    print("✅ 成功获取任务统计")
                else:
                    print("❌ 获取任务统计失败")
                    return False
                
            else:
                print(f"❌ 创建任务失败: {task_result.get('error', 'Unknown error')}")
                return False
            
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        print("✅ 任务管理模块测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 任务管理模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reflection_module():
    """测试反思模块基本功能"""
    print("\n🧪 测试反思模块...")
    
    try:
        # 导入反思模块
        from zentex.reflection import ReflectionManager
        from zentex.reflection.models import ReflectionType, ReflectionQuality
        
        print("✅ 成功导入反思模块")
        
        # 创建临时存储目录
        temp_dir = tempfile.mkdtemp(prefix="reflection_test_")
        
        try:
            # 初始化反思管理器
            reflection_manager = ReflectionManager(
                storage_path=temp_dir,
                enable_persistence=True
            )
            
            print("✅ 成功创建ReflectionManager")
            
            # 获取统一接口
            interface = reflection_manager.get_interface()
            print("✅ 成功获取统一接口")
            
            # 测试生成反思
            reflection_result = interface.generate_reflection({
                "subject": "测试决策反思",
                "reflection_type": "decision_reflection",
                "context": {
                    "decision": {
                        "factors": ["性能", "成本", "可维护性"],
                        "risk_level": 0.6
                    },
                    "outcome": {
                        "success": True,
                        "achievement_rate": 0.85
                    },
                    "alternatives": [
                        {"name": "方案A", "pros": ["高性能"], "cons": ["高成本"]},
                        {"name": "方案B", "pros": ["低成本"], "cons": ["性能一般"]}
                    ]
                }
            })
            
            if reflection_result["success"]:
                reflection_id = reflection_result["reflection"]["reflection_id"]
                print(f"✅ 成功生成反思: {reflection_id}")
                
                # 测试获取反思
                get_result = interface.get_reflection(reflection_id)
                if get_result["success"]:
                    reflection = get_result["reflection"]
                    print(f"✅ 成功获取反思，主题: {reflection['subject']}")
                    print(f"   反思类型: {reflection['reflection_type']}")
                    print(f"   反思质量: {reflection['quality']}")
                    print(f"   置信度: {reflection['confidence']:.2f}")
                else:
                    print("❌ 获取反思失败")
                    return False
                
                # 测试列出反思
                list_result = interface.list_reflections()
                if list_result["success"] and list_result["count"] > 0:
                    print(f"✅ 成功列出反思，共 {list_result['count']} 个")
                else:
                    print("❌ 列出反思失败")
                    return False
                
                # 测试搜索反思
                search_result = interface.search_reflections("测试")
                if search_result["success"]:
                    print(f"✅ 成功搜索反思，找到 {search_result['count']} 个")
                else:
                    print("❌ 搜索反思失败")
                    return False
                
                # 测试验证反思
                verify_result = interface.verify_reflection(reflection_id, "test_user")
                if verify_result["success"]:
                    print("✅ 成功验证反思")
                else:
                    print("❌ 验证反思失败")
                    return False
                
                # 测试统计功能
                metrics = interface.get_metrics()
                if metrics["success"]:
                    metrics_data = metrics["metrics"]
                    print(f"✅ 成功获取反思指标，总反思数: {metrics_data['total_reflections']}")
                else:
                    print("❌ 获取反思指标失败")
                    return False
                
            else:
                print(f"❌ 生成反思失败: {reflection_result.get('error', 'Unknown error')}")
                return False
            
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        print("✅ 反思模块测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 反思模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_advanced_features():
    """测试高级功能"""
    print("\n🧪 测试高级功能...")
    
    try:
        # 测试任务管理高级功能
        from zentex.tasks import TaskManager
        
        temp_dir = tempfile.mkdtemp(prefix="advanced_test_")
        
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
            
            # 测试创建使命任务
            import asyncio
            async def test_mission():
                return await task_manager.create_mission(
                    title="测试使命",
                    content="这是一个测试使命，用于验证任务拆解功能",
                    originator_id="test_user",
                    strategy="sequential"
                )
            
            mission_result = asyncio.run(test_mission())
            
            if mission_result:
                mission_id = mission_result.task_id
                print(f"✅ 成功创建使命任务: {mission_id}")
                
                # 查看子任务
                subtasks = task_manager.list_tasks({"parent_task_id": mission_id})
                if isinstance(subtasks, list) and len(subtasks) > 0:
                    print(f"✅ 成功拆解出 {len(subtasks)} 个子任务")
                elif isinstance(subtasks, dict) and subtasks.get("count", 0) > 0:
                    print(f"✅ 成功拆解出 {subtasks['count']} 个子任务")
                else:
                    print("⚠️  未拆解出子任务")
            else:
                print(f"⚠️  创建使命任务失败: {mission_result.get('error')}")
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # 测试反思高级功能
        from zentex.reflection import ReflectionManager
        
        temp_dir2 = tempfile.mkdtemp(prefix="reflection_advanced_test_")
        
        try:
            reflection_manager = ReflectionManager(storage_path=temp_dir2)
            
            # 测试高级反思生成
            decision_reflection = reflection_manager.generate_decision_reflection(
                decision_subject="高级技术选型",
                decision_data={
                    "factors": ["性能", "成本", "可维护性", "团队技能"],
                    "constraints": ["预算限制", "时间压力"]
                },
                outcome_data={
                    "success": True,
                    "performance_improvement": 0.4,
                    "team_satisfaction": 0.8
                },
                alternatives=[
                    {"name": "方案A", "risk": "low", "benefit": "limited"},
                    {"name": "方案B", "risk": "high", "benefit": "significant"}
                ]
            )
            
            if decision_reflection["success"]:
                print("✅ 成功生成高级决策反思")
                
                # 测试模式分析
                patterns = reflection_manager.interface.analyze_reflection_patterns()
                if patterns["success"]:
                    print("✅ 成功分析反思模式")
                else:
                    print("⚠️  分析反思模式失败")
                
                # 测试推荐功能
                recommendations = reflection_manager.interface.get_reflection_recommendations(limit=3)
                if recommendations["success"]:
                    print(f"✅ 成功获取 {recommendations['count']} 个推荐")
                else:
                    print("⚠️  获取推荐失败")
            else:
                print(f"⚠️  生成高级反思失败: {decision_reflection.get('error')}")
        
        finally:
            shutil.rmtree(temp_dir2, ignore_errors=True)
        
        print("✅ 高级功能测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 高级功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """测试模块集成"""
    print("\n🧪 测试模块集成...")
    
    try:
        # 测试两个模块是否可以同时使用
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
            
            print("✅ 成功同时初始化两个模块")
            
            # 测试模块间独立性
            import asyncio
            async def test_task_creation():
                return await task_manager.get_service_interface().create_task({
                    "title": "集成测试任务",
                    "task_type": "cognitive_step",
                    "originator_id": "integration_test",
                    "idempotency_key": "integration_test_key"
                })
            
            task_result = asyncio.run(test_task_creation())
            
            reflection_result = reflection_manager.get_interface().generate_reflection({
                "subject": "集成测试反思",
                "reflection_type": "process_reflection",
                "context": {"test": True}
            })
            
            if task_result["success"] and reflection_result["success"]:
                print("✅ 两个模块可以独立工作")
                
                # 获取各自的统计信息
                task_stats = task_manager.get_service_interface().get_task_statistics()
                reflection_stats = reflection_manager.get_interface().get_metrics()
                
                if task_stats["success"] and reflection_stats["success"]:
                    print("✅ 成功获取两个模块的统计信息")
                    print(f"   任务模块: {task_stats['statistics']['total_tasks']} 个任务")
                    print(f"   反思模块: {reflection_stats['metrics']['total_reflections']} 个反思")
                else:
                    print("❌ 获取统计信息失败")
                    return False
            else:
                print("❌ 模块集成测试失败")
                return False
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        print("✅ 模块集成测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 模块集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试任务管理模块和反思模块...")
    print("=" * 60)
    
    results = []
    
    # 基础功能测试
    results.append(test_task_management_module())
    results.append(test_reflection_module())
    
    # 高级功能测试
    results.append(test_advanced_features())
    
    # 集成测试
    results.append(test_integration())
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    
    test_names = [
        "任务管理模块基础功能",
        "反思模块基础功能", 
        "高级功能测试",
        "模块集成测试"
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
        print("🎉 所有测试都通过了！两个模块功能正常。")
        return True
    else:
        print("⚠️  部分测试失败，请检查相关功能。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
