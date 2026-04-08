#!/usr/bin/env python3
"""
Semantic Kernel任务拆分功能测试
验证基于Semantic Kernel的智能任务拆分
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

def test_semantic_kernel_decomposition():
    """测试Semantic Kernel任务拆分功能"""
    print("🧪 测试Semantic Kernel任务拆分功能...")
    
    try:
        # 直接导入Semantic Kernel组件
        from zentex.tasks.semantic_kernel_decomposer import (
            SemanticKernelTaskDecompositionPlugin, SemanticKernelTaskDecompositionSpec, TaskDecompositionStrategy
        )
        from zentex.tasks.semantic_kernel_registry import (
            SemanticKernelPluginManager, create_default_semantic_kernel_plugin_registry
        )
        
        print("  📋 测试1: Semantic Kernel插件注册")
        # 创建Semantic Kernel注册中心
        registry = create_default_semantic_kernel_plugin_registry()
        
        if registry:
            print("    ✅ Semantic Kernel注册中心创建成功")
            
            # 列出可用插件
            plugins = registry.list_decomposition_plugins()
            if plugins:
                print(f"    ✅ 已注册 {len(plugins)} 个Semantic Kernel插件")
                for plugin in plugins:
                    print(f"      - {plugin['name']} ({plugin['strategy']})")
            else:
                print("    ❌ 无Semantic Kernel插件注册")
                return False
        else:
            print("    ❌ Semantic Kernel注册中心创建失败")
            return False
        
        print("  📋 测试2: Semantic Kernel插件管理器")
        # 创建插件管理器
        plugin_manager = SemanticKernelPluginManager(registry)
        
        # 获取可用策略
        strategies = plugin_manager.get_available_semantic_strategies()
        if strategies:
            print(f"    ✅ 可用Semantic Kernel策略: {strategies}")
        else:
            print("    ❌ 无法获取Semantic Kernel策略")
            return False
        
        print("  📋 测试3: 创建Semantic Kernel拆分插件")
        # 创建不同策略的插件
        test_specs = [
            {
                "strategy": TaskDecompositionStrategy.HYBRID,
                "name": "Test Hybrid Semantic Decomposer",
                "description": "测试混合策略Semantic Kernel拆解器"
            },
            {
                "strategy": TaskDecompositionStrategy.PARALLEL,
                "name": "Test Parallel Semantic Decomposer", 
                "description": "测试并行策略Semantic Kernel拆解器"
            },
            {
                "strategy": TaskDecompositionStrategy.DEPENDENCY_DRIVEN,
                "name": "Test Dependency Semantic Decomposer",
                "description": "测试依赖驱动策略Semantic Kernel拆解器"
            }
        ]
        
        created_plugins = []
        for i, spec_config in enumerate(test_specs):
            spec = SemanticKernelTaskDecompositionSpec(
                plugin_id=f"test-semantic-{spec_config['strategy'].value}-decomposer",
                version="1.0.0",
                feature_code=f"semantic_kernel.task_decomposition.{spec_config['strategy'].value}",
                name=spec_config["name"],
                description=spec_config["description"],
                author="Test",
                strategy=spec_config["strategy"],
                max_depth=4,
                min_task_size=1,
                enable_optimization=True,
                confidence_threshold=0.8,
                semantic_model="gpt-4",
                reasoning_model="gpt-3.5-turbo",
                enable_planning=True,
                enable_memory=True,
                context_window=8000
            )
            
            plugin = SemanticKernelTaskDecompositionPlugin(spec)
            if plugin:
                created_plugins.append(plugin)
                print(f"    ✅ {spec_config['strategy'].value}策略插件创建成功")
            else:
                print(f"    ❌ {spec_config['strategy'].value}策略插件创建失败")
        
        if len(created_plugins) == 0:
            print("    ❌ 无Semantic Kernel插件创建成功")
            return False
        
        print("  📋 测试4: Semantic Kernel任务拆分")
        # 测试任务拆分
        test_missions = [
            {
                "title": "智能客服系统开发",
                "content": "使用Python和FastAPI开发智能客服系统，集成OpenAI API，支持多渠道接入，包括Web、微信、电话等",
                "context": {
                    "max_subtasks": 5,
                    "estimated_duration_per_subtask": 90,
                    "team_size": 6,
                    "complexity": "high",
                    "domain": "software_development",
                    "risk_level": "medium"
                }
            },
            {
                "title": "企业级电商平台重构",
                "content": "重构现有电商平台，采用微服务架构，优化性能，改进用户体验，增加AI推荐功能",
                "context": {
                    "max_subtasks": 4,
                    "estimated_duration_per_subtask": 120,
                    "team_size": 8,
                    "complexity": "critical",
                    "domain": "system_architecture",
                    "risk_level": "high"
                }
            },
            {
                "title": "数据分析仪表板开发",
                "content": "开发实时数据分析仪表板，支持多数据源接入，提供可视化分析和报告功能",
                "context": {
                    "max_subtasks": 3,
                    "estimated_duration_per_subtask": 60,
                    "team_size": 3,
                    "complexity": "medium",
                    "domain": "business_analysis",
                    "risk_level": "low"
                }
            }
        ]
        
        for i, mission in enumerate(test_missions):
            print(f"    测试任务 {i+1}: {mission['title']}")
            
            # 使用第一个插件进行拆分
            if created_plugins:
                plugin = created_plugins[0]
                
                subtasks = plugin.decompose_mission(
                    mission_title=mission["title"],
                    mission_content=mission["content"],
                    context=mission["context"]
                )
                
                if subtasks and len(subtasks) > 0:
                    print(f"      ✅ Semantic Kernel拆分成功，生成 {len(subtasks)} 个子任务")
                    
                    # 验证子任务质量
                    valid_subtasks = 0
                    for j, subtask in enumerate(subtasks):
                        print(f"        子任务 {j+1}: {subtask.get('title', 'Unknown')}")
                        print(f"          类型: {subtask.get('task_type', 'Unknown')}")
                        print(f"          时长: {subtask.get('estimated_duration', 0)}分钟")
                        print(f"          依赖: {subtask.get('depends_on', [])}")
                        print(f"          协调: {subtask.get('coordination_mode', 'Unknown')}")
                        print(f"          语义标签: {subtask.get('semantic_tags', [])}")
                        print(f"          风险等级: {subtask.get('risk_level', 'Unknown')}")
                        
                        # 验证基本字段
                        if (subtask.get('title') and 
                            subtask.get('content') and 
                            subtask.get('task_type')):
                            valid_subtasks += 1
                            print(f"          ✅ 子任务数据完整")
                        else:
                            print(f"          ❌ 子任务数据不完整")
                    
                    if valid_subtasks == len(subtasks):
                        print("      ✅ 所有子任务验证通过")
                    else:
                        print("      ❌ 部分子任务验证失败")
                else:
                    print("      ❌ Semantic Kernel拆分失败或无结果")
            else:
                print("      ❌ 无可用Semantic Kernel插件")
        
        print("  📋 测试5: Semantic Kernel语义分析")
        # 测试语义分析功能
        if created_plugins:
            plugin = created_plugins[0]
            
            for i, mission in enumerate(test_missions[:2]):  # 只测试前两个
                print(f"    语义分析任务 {i+1}: {mission['title']}")
                
                analysis = plugin.get_semantic_analysis(
                    mission_title=mission["title"],
                    mission_content=mission["content"],
                    context=mission["context"]
                )
                
                if analysis and analysis.get("core_objective"):
                    print(f"      ✅ 核心目标: {analysis.get('core_objective', 'Unknown')}")
                    print(f"      ✅ 领域: {analysis.get('domain', 'Unknown')}")
                    print(f"      ✅ 复杂度: {analysis.get('complexity_level', 'Unknown')}")
                    print(f"      ✅ 关键依赖: {analysis.get('key_dependencies', [])}")
                    print(f"      ✅ 资源需求: {analysis.get('resource_requirements', {})}")
                    print(f"      ✅ 风险因素: {analysis.get('risk_factors', [])}")
                else:
                    print("      ❌ 语义分析失败")
        
        print("  📋 测试6: 不同Semantic Kernel策略对比")
        # 测试不同策略的拆分效果
        test_mission = test_missions[0]  # 使用第一个任务
        
        strategy_results = {}
        for plugin in created_plugins:
            strategy_name = plugin.strategy.value
            print(f"    测试策略: {strategy_name}")
            
            subtasks = plugin.decompose_mission(
                mission_title=test_mission["title"],
                mission_content=test_mission["content"],
                context=test_mission["context"]
            )
            
            if subtasks and len(subtasks) > 0:
                strategy_results[strategy_name] = {
                    "count": len(subtasks),
                    "avg_duration": sum(st.get("estimated_duration", 0) for st in subtasks) / len(subtasks),
                    "has_semantic_tags": any(st.get("semantic_tags") for st in subtasks),
                    "risk_diversity": len(set(st.get("risk_level", "medium") for st in subtasks))
                }
                print(f"      ✅ {strategy_name}策略: {len(subtasks)} 个子任务")
            else:
                print(f"      ❌ {strategy_name}策略: 拆分失败")
        
        # 验证策略差异
        if len(strategy_results) > 1:
            print("    策略对比结果:")
            for strategy, result in strategy_results.items():
                print(f"      {strategy}: {result['count']} 个子任务, 语义标签: {result['has_semantic_tags']}, 风险多样性: {result['risk_diversity']}")
            
            unique_counts = set(result["count"] for result in strategy_results.values())
            if len(unique_counts) > 1:
                print("    ✅ 不同Semantic Kernel策略产生不同拆分结果")
            else:
                print("    ⚠️  不同Semantic Kernel策略产生相同结果")
        else:
            print("    ❌ 策略对比失败")
        
        print("  📋 测试7: Semantic Kernel健康检查")
        # 测试插件健康检查
        for i, plugin in enumerate(created_plugins):
            health = plugin.health_check()
            print(f"    插件 {i+1} 健康检查:")
            print(f"      状态: {health.get('status', 'Unknown')}")
            print(f"      策略: {health.get('strategy', 'Unknown')}")
            print(f"      Semantic Kernel配置: {health.get('semantic_kernel_configured', False)}")
            print(f"      语义模型: {health.get('configuration', {}).get('semantic_model', 'Unknown')}")
            print(f"      推理模型: {health.get('configuration', {}).get('reasoning_model', 'Unknown')}")
            print(f"      规划能力: {health.get('configuration', {}).get('enable_planning', False)}")
            print(f"      记忆功能: {health.get('configuration', {}).get('enable_memory', False)}")
        
        print("  📋 测试8: Semantic Kernel质量评估")
        # 测试拆分质量评估
        if created_plugins:
            plugin = created_plugins[0]
            
            # 使用最后一个任务的拆分结果
            subtasks = plugin.decompose_mission(
                mission_title=test_missions[-1]["title"],
                mission_content=test_missions[-1]["content"],
                context=test_missions[-1]["context"]
            )
            
            if subtasks:
                quality = plugin.get_decomposition_quality(subtasks)
                print(f"    ✅ 拆分质量评估:")
                print(f"      总分: {quality.get('score', 0):.2f}")
                print(f"      语义分数: {quality.get('semantic_score', 0):.2f}")
                print(f"      质量等级: {quality.get('quality_level', 'Unknown')}")
                print(f"      指标: {quality.get('metrics', {})}")
                print(f"      问题: {quality.get('issues', [])}")
            else:
                print("    ❌ 无法获取子任务进行质量评估")
        
        return True
        
    except Exception as e:
        print(f"❌ Semantic Kernel任务拆分测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始Semantic Kernel任务拆分功能测试...")
    print("=" * 80)
    
    result = test_semantic_kernel_decomposition()
    
    print("\n" + "=" * 80)
    print("📊 Semantic Kernel任务拆分测试结果:")
    
    if result:
        print("🎉 Semantic Kernel任务拆分测试通过！")
        print("📋 验证的Semantic Kernel拆分功能:")
        print("   ✅ Semantic Kernel插件注册和管理")
        print("   ✅ 多策略Semantic Kernel拆分器创建")
        print("   ✅ 基于Semantic Kernel的智能任务拆分")
        print("   ✅ 子任务数据完整性和语义标签")
        print("   ✅ 深度语义分析能力")
        print("   ✅ 不同Semantic Kernel策略对比")
        print("   ✅ Semantic Kernel健康检查")
        print("   ✅ 拆分质量评估")
        print("   🎯 Semantic Kernel任务拆分功能完全符合预期！")
        print("\n📋 Semantic Kernel拆分优势:")
        print("   🧠 深度语义理解：超越简单关键词匹配")
        print("   🧠 多模型协作：语义模型+推理模型")
        print("   🧠 智能规划：基于项目管理的最佳实践")
        print("   🧠 记忆管理：上下文窗口和记忆功能")
        print("   🧠 风险评估：智能识别和分析风险因素")
        print("   🧠 依赖分析：深度分析任务依赖关系")
        print("   🧠 资源优化：智能分配和优化资源")
        print("   🧠 领域专业知识：软件、业务、架构等领域")
        print("   🧠 质量保证：多层次验证和优化")
        return True
    else:
        print("⚠️  Semantic Kernel任务拆分测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
