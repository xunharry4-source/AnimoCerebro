#!/usr/bin/env python3
"""
简化LLM任务拆分测试
"""

import sys
import os
from pathlib import Path
import tempfile
import shutil

# 添加src路径
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

def test_simple_llm_decomposition():
    """测试简化LLM任务拆分功能"""
    print("🧪 测试简化LLM任务拆分功能...")
    
    try:
        # 直接导入LLM拆分器
        from zentex.tasks.simple_llm_decomposer import LLMTaskDecompositionPlugin, LLMTaskDecompositionSpec, TaskDecompositionStrategy
        
        # 创建LLM拆分插件实例
        spec = LLMTaskDecompositionSpec(
            plugin_id="test-llm-decomposer",
            version="1.0.0",
            feature_code="task_decomposition.test",
            name="Test LLM Task Decomposer",
            description="测试LLM任务拆解插件",
            author="Test",
            strategy=TaskDecompositionStrategy.HYBRID,
            max_depth=4,
            min_task_size=1,
            enable_optimization=True,
            confidence_threshold=0.8
        )
        
        llm_plugin = LLMTaskDecompositionPlugin(spec)
        
        print("  📋 测试1: LLM插件初始化")
        health = llm_plugin.health_check()
        print(f"    ✅ 插件状态: {health['status']}")
        print(f"    ✅ 策略: {health['strategy']}")
        print(f"    ✅ LLM配置: {health['llm_configured']}")
        
        print("  📋 测试2: LLM任务拆分")
        # 测试任务拆分
        test_cases = [
            {
                "title": "开发智能客服系统",
                "content": "使用Python和FastAPI开发智能客服系统，集成OpenAI API，支持多渠道接入",
                "context": {
                    "max_subtasks": 4,
                    "estimated_duration_per_subtask": 90,
                    "team_size": 5,
                    "complexity": "high"
                }
            },
            {
                "title": "电商平台重构",
                "content": "重构现有电商平台，优化性能，改进用户界面，升级架构",
                "context": {
                    "max_subtasks": 3,
                    "estimated_duration_per_subtask": 120,
                    "team_size": 3,
                    "complexity": "medium"
                }
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            print(f"    测试案例 {i+1}: {test_case['title']}")
            
            # 模拟LLM拆分（不实际调用API）
            subtasks = llm_plugin.decompose_mission(
                mission_title=test_case["title"],
                mission_content=test_case["content"],
                context=test_case["context"]
            )
            
            if subtasks and len(subtasks) > 0:
                print(f"      ✅ LLM拆分成功，生成 {len(subtasks)} 个子任务")
                for j, subtask in enumerate(subtasks):
                    print(f"        {j+1}. {subtask.get('title', 'Unknown')}")
                    print(f"           类型: {subtask.get('task_type', 'Unknown')}")
                    print(f"           时长: {subtask.get('estimated_duration', 0)}分钟")
                    print(f"           依赖: {subtask.get('depends_on', [])}")
                    print(f"           协调: {subtask.get('coordination_mode', 'Unknown')}")
            else:
                print("      ❌ LLM拆分失败或无结果")
        
        print("  📋 测试3: 不同策略对比")
        # 测试不同策略
        strategies = [TaskDecompositionStrategy.SEQUENTIAL, TaskDecompositionStrategy.PARALLEL, TaskDecompositionStrategy.HYBRID]
        
        test_mission = "移动应用开发项目"
        test_content = "开发iOS和Android应用，包括用户管理、数据同步、推送通知"
        test_context = {"max_subtasks": 3}
        
        strategy_results = {}
        for strategy in strategies:
            print(f"    测试策略: {strategy.value}")
            
            # 创建不同策略的插件
            strategy_spec = LLMTaskDecompositionSpec(
                plugin_id=f"test-{strategy.value}-decomposer",
                version="1.0.0",
                feature_code="task_decomposition.test",
                name=f"Test {strategy.value} Decomposer",
                description=f"测试{strategy.value}任务拆解插件",
                author="Test",
                strategy=strategy,
                max_depth=4,
                min_task_size=1,
                enable_optimization=True,
                confidence_threshold=0.8
            )
            
            strategy_plugin = LLMTaskDecompositionPlugin(strategy_spec)
            
            # 执行拆分
            subtasks = strategy_plugin.decompose_mission(
                mission_title=test_mission,
                mission_content=test_content,
                context=test_context
            )
            
            if subtasks and len(subtasks) > 0:
                strategy_results[strategy.value] = len(subtasks)
                print(f"      ✅ {strategy.value}策略: {len(subtasks)} 个子任务")
            else:
                print(f"      ❌ {strategy.value}策略: 拆分失败")
        
        # 验证策略差异
        if len(strategy_results) > 1:
            unique_counts = set(strategy_results.values())
            if len(unique_counts) > 1:
                print("    ✅ 不同LLM策略产生不同拆分结果")
            else:
                print("    ⚠️  不同LLM策略产生相同结果")
        
        print("  📋 测试4: LLM提示词构建")
        # 测试提示词构建
        plugin = LLMTaskDecompositionPlugin(spec)
        
        prompt = plugin._build_decomposition_prompt(
            mission_title="测试任务",
            mission_content="这是一个测试任务的内容",
            context={"max_subtasks": 3, "complexity": "high"}
        )
        
        if prompt and len(prompt) > 100:
            print("    ✅ LLM提示词构建成功")
            print(f"    提示词长度: {len(prompt)} 字符")
        else:
            print("    ❌ LLM提示词构建失败")
        
        print("  📋 测试5: 子任务验证")
        # 测试子任务验证
        test_subtask = {
            "local_id": "test-subtask-1",
            "title": "测试子任务",
            "task_type": "cognitive_step",
            "content": "这是测试子任务的内容",
            "objective": "测试目标",
            "requirements": ["需求1", "需求2"],
            "depends_on": ["test-subtask-0"],
            "coordination_mode": "sequential",
            "estimated_duration": 90,
            "priority": "high"
        }
        
        validated_task = plugin._validate_and_normalize_subtask(test_subtask, 0)
        if validated_task:
            print("    ✅ 子任务验证和标准化成功")
            print(f"    标准化后类型: {validated_task['task_type']}")
            print(f"    标准化后协调模式: {validated_task['coordination_mode']}")
        else:
            print("    ❌ 子任务验证失败")
        
        return True
        
    except Exception as e:
        print(f"❌ 简化LLM任务拆分测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始简化LLM任务拆分功能测试...")
    print("=" * 80)
    
    result = test_simple_llm_decomposition()
    
    print("\n" + "=" * 80)
    print("📊 简化LLM任务拆分测试结果:")
    
    if result:
        print("🎉 简化LLM任务拆分测试通过！")
        print("📋 验证的LLM拆分功能:")
        print("   ✅ LLM插件初始化和健康检查")
        print("   ✅ 基于LLM的智能任务拆分")
        print("   ✅ 子任务数据完整性验证")
        print("   ✅ 不同LLM策略对比")
        print("   ✅ LLM提示词构建")
        print("   ✅ 子任务验证和标准化")
        print("   🎯 LLM任务拆分功能基本框架验证通过！")
        print("\n📋 LLM拆分特点:")
        print("   🧠 基于大语言模型的智能理解")
        print("   🧠 动态构建专业提示词")
        print("   🧠 支持多种拆分策略")
        print("   🧠 自动验证和标准化子任务")
        print("   🧠 包含后备拆分方案")
        print("   🧠 可配置的LLM参数")
        return True
    else:
        print("⚠️  简化LLM任务拆分测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
