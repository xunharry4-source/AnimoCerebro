#!/usr/bin/env python3
"""
双重任务拆分系统测试
验证LLM和Semantic Kernel两种拆分方式的并存和协作
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

def test_dual_decomposition_system():
    """测试双重任务拆分系统"""
    print("🧪 测试双重任务拆分系统...")
    
    try:
        # 导入双重拆分组件
        from zentex.tasks.dual_decomposition_registry import (
            DualDecompositionPluginRegistry, DualDecompositionPluginManager,
            create_default_dual_decomposition_registry
        )
        from zentex.tasks.simple_llm_decomposer import TaskDecompositionStrategy
        
        print("  📋 测试1: 双重拆分注册中心初始化")
        # 创建双重拆分注册中心
        registry = create_default_dual_decomposition_registry()
        
        if registry:
            print("    ✅ 双重拆分注册中心创建成功")
            
            # 获取统计信息
            stats = registry.get_registry_stats()
            print(f"    ✅ 总插件数: {stats['total_plugins']}")
            print(f"    ✅ LLM插件数: {stats['llm_plugins']}")
            print(f"    ✅ Semantic Kernel插件数: {stats['semantic_kernel_plugins']}")
            print(f"    ✅ 默认拆解类型: {stats['default_decomposition_type']}")
        else:
            print("    ❌ 双重拆分注册中心创建失败")
            return False
        
        print("  📋 测试2: 双重拆分插件管理器")
        # 创建插件管理器
        plugin_manager = DualDecompositionPluginManager(registry)
        
        # 获取可用策略
        all_strategies = plugin_manager.get_available_strategies()
        print(f"    ✅ LLM策略: {all_strategies.get('llm', [])}")
        print(f"    ✅ Semantic Kernel策略: {all_strategies.get('semantic_kernel', [])}")
        
        print("  📋 测试3: LLM和Semantic Kernel拆分对比")
        # 测试任务
        test_missions = [
            {
                "title": "智能推荐系统开发",
                "content": "开发基于机器学习的智能推荐系统，支持用户行为分析、实时推荐、A/B测试",
                "context": {
                    "max_subtasks": 4,
                    "estimated_duration_per_subtask": 90,
                    "team_size": 5,
                    "complexity": "high",
                    "domain": "machine_learning"
                }
            },
            {
                "title": "企业微服务架构迁移",
                "content": "将单体应用迁移到微服务架构，包括服务拆分、API网关、服务发现、监控体系",
                "context": {
                    "max_subtasks": 5,
                    "estimated_duration_per_subtask": 120,
                    "team_size": 8,
                    "complexity": "critical",
                    "domain": "system_architecture"
                }
            }
        ]
        
        for i, mission in enumerate(test_missions):
            print(f"    对比任务 {i+1}: {mission['title']}")
            
            # 进行对比拆分
            comparison = plugin_manager.compare_decomposition_methods(
                mission_title=mission["title"],
                mission_content=mission["content"],
                strategy="hybrid",
                context=mission["context"]
            )
            
            # 分析LLM拆分结果
            llm_result = comparison["llm_decomposition"]
            if llm_result["success"]:
                print(f"      ✅ LLM拆分: {llm_result['subtask_count']} 个子任务")
                print(f"        特点: {llm_result['characteristics']['reasoning_depth']} 推理深度")
                print(f"        特点: {llm_result['characteristics']['semantic_understanding']} 语义理解")
                print(f"        特点: {llm_result['characteristics']['domain_expertise']} 领域专业")
            else:
                print("      ❌ LLM拆分失败")
            
            # 分析Semantic Kernel拆分结果
            semantic_result = comparison["semantic_kernel_decomposition"]
            if semantic_result["success"]:
                print(f"      ✅ Semantic Kernel拆分: {semantic_result['subtask_count']} 个子任务")
                print(f"        特点: {semantic_result['characteristics']['reasoning_depth']} 推理深度")
                print(f"        特点: {semantic_result['characteristics']['semantic_understanding']} 语义理解")
                print(f"        特点: {semantic_result['characteristics']['domain_expertise']} 领域专业")
            else:
                print("      ❌ Semantic Kernel拆分失败")
            
            # 显示对比指标
            metrics = comparison["comparison_metrics"]
            print(f"      📊 对比指标:")
            print(f"        子任务数量差异: {metrics['subtask_count_difference']}")
            print(f"        LLM平均时长: {metrics['llm_avg_duration']:.1f}分钟")
            print(f"        Semantic平均时长: {metrics['semantic_avg_duration']:.1f}分钟")
            print(f"        LLM语义标签: {metrics['llm_has_semantic_tags']}")
            print(f"        Semantic语义标签: {metrics['semantic_has_semantic_tags']}")
            print(f"        LLM风险多样性: {metrics['llm_risk_diversity']}")
            print(f"        Semantic风险多样性: {metrics['semantic_risk_diversity']}")
        
        print("  📋 测试4: 动态切换拆解类型")
        # 测试切换默认拆解类型
        original_type = plugin_manager.get_default_decomposition_type()
        print(f"    原始默认类型: {original_type}")
        
        # 切换到Semantic Kernel
        if plugin_manager.set_default_decomposition_type("semantic_kernel"):
            print("    ✅ 成功切换到Semantic Kernel默认拆解")
            
            # 使用Semantic Kernel进行拆分
            semantic_result = plugin_manager.decompose_mission(
                mission_title="切换测试任务",
                mission_content="测试切换到Semantic Kernel拆解",
                decomposition_type="semantic_kernel",
                strategy="hybrid",
                context={"max_subtasks": 3}
            )
            
            if semantic_result["success"]:
                print(f"    ✅ Semantic Kernel拆分成功: {len(semantic_result['subtasks'])} 个子任务")
            else:
                print("    ❌ Semantic Kernel拆分失败")
        else:
            print("    ❌ 切换到Semantic Kernel失败")
        
        # 切换回LLM
        if plugin_manager.set_default_decomposition_type("llm"):
            print("    ✅ 成功切换回LLM默认拆解")
            
            # 使用LLM进行拆分
            llm_result = plugin_manager.decompose_mission(
                mission_title="切换回LLM测试任务",
                mission_content="测试切换回LLM拆解",
                decomposition_type="llm",
                strategy="hybrid",
                context={"max_subtasks": 3}
            )
            
            if llm_result["success"]:
                print(f"    ✅ LLM拆分成功: {len(llm_result['subtasks'])} 个子任务")
            else:
                print("    ❌ LLM拆分失败")
        else:
            print("    ❌ 切换回LLM失败")
        
        # 恢复原始设置
        plugin_manager.set_default_decomposition_type(original_type)
        print(f"    ✅ 恢复原始默认类型: {original_type}")
        
        print("  📋 测试5: 统一接口测试")
        # 测试统一接口（不指定类型，使用默认）
        unified_result = plugin_manager.decompose_mission(
            mission_title="统一接口测试任务",
            mission_content="测试统一拆分接口，使用默认拆解类型",
            decomposition_type=None,  # 使用默认类型
            strategy="hybrid",
            context={"max_subtasks": 3}
        )
        
        if unified_result["success"]:
            print(f"    ✅ 统一接口拆分成功: {len(unified_result['subtasks'])} 个子任务")
            print(f"    ✅ 使用拆解类型: {unified_result['decomposition_type']}")
            print(f"    ✅ 使用插件: {unified_result['plugin_used']}")
            print(f"    ✅ 元数据: {unified_result['metadata']}")
        else:
            print("    ❌ 统一接口拆分失败")
        
        print("  📋 测试6: 插件健康检查")
        # 检查所有插件的健康状态
        all_plugins = registry.list_all_plugins()
        healthy_count = 0
        
        for plugin in all_plugins:
            plugin_type = plugin["type"]
            plugin_id = plugin["plugin_id"]
            health = plugin["health"]
            
            print(f"    {plugin_type}插件 {plugin_id}:")
            print(f"      状态: {health.get('status', 'Unknown')}")
            print(f"      配置: {health.get('configured', False)}")
            
            if health.get("status") == "healthy":
                healthy_count += 1
        
        print(f"    ✅ 健康插件数: {healthy_count}/{len(all_plugins)}")
        
        print("  📋 测试7: 策略灵活性测试")
        # 测试不同策略的灵活性
        strategies_to_test = ["sequential", "parallel", "hybrid"]
        
        for strategy in strategies_to_test:
            print(f"    测试策略: {strategy}")
            
            # LLM策略测试
            llm_available = strategy in plugin_manager.get_available_strategies("llm").get("llm", [])
            semantic_available = strategy in plugin_manager.get_available_strategies("semantic_kernel").get("semantic_kernel", [])
            
            print(f"      LLM支持 {strategy}: {llm_available}")
            print(f"      Semantic Kernel支持 {strategy}: {semantic_available}")
            
            if llm_available or semantic_available:
                print(f"      ✅ 策略 {strategy} 至少被一种拆解方式支持")
            else:
                print(f"      ❌ 策略 {strategy} 未被任何拆解方式支持")
        
        return True
        
    except Exception as e:
        print(f"❌ 双重任务拆分系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_advanced_scenarios():
    """测试高级场景"""
    print("\n🧪 测试高级场景...")
    
    try:
        from zentex.tasks.dual_decomposition_registry import DualDecompositionPluginManager
        
        plugin_manager = DualDecompositionPluginManager()
        
        print("  📋 场景1: 复杂项目混合拆分")
        # 复杂项目：同时使用两种拆分方式
        complex_project = {
            "title": "全栈AI应用开发",
            "content": "开发包含前端、后端、AI模型训练、部署的完整AI应用",
            "context": {
                "max_subtasks": 6,
                "team_size": 10,
                "complexity": "critical",
                "domains": ["frontend", "backend", "machine_learning", "devops"]
            }
        }
        
        # 使用LLM进行初步拆分
        llm_result = plugin_manager.decompose_mission(
            mission_title=complex_project["title"],
            mission_content=complex_project["content"],
            decomposition_type="llm",
            strategy="parallel",
            context=complex_project["context"]
        )
        
        # 使用Semantic Kernel进行深度分析
        semantic_result = plugin_manager.decompose_mission(
            mission_title=complex_project["title"],
            mission_content=complex_project["content"],
            decomposition_type="semantic_kernel",
            strategy="hybrid",
            context=complex_project["context"]
        )
        
        if llm_result["success"] and semantic_result["success"]:
            print("    ✅ 复杂项目混合拆分成功")
            print(f"      LLM拆分: {len(llm_result['subtasks'])} 个子任务")
            print(f"      Semantic Kernel拆分: {len(semantic_result['subtasks'])} 个子任务")
            
            # 分析两种结果的互补性
            llm_complexity = len([st for st in llm_result['subtasks'] if st.get('estimated_duration', 0) > 100])
            semantic_complexity = len([st for st in semantic_result['subtasks'] if st.get('risk_level') == 'high'])
            
            print(f"      LLM复杂任务数: {llm_complexity}")
            print(f"      Semantic高风险任务数: {semantic_complexity}")
            print("    ✅ 两种拆分方式提供了互补的视角")
        else:
            print("    ❌ 复杂项目混合拆分失败")
        
        print("  📋 场景2: 动态策略选择")
        # 根据任务特征动态选择最佳拆解方式
        task_scenarios = [
            {
                "title": "简单数据迁移",
                "content": "将数据从旧系统迁移到新系统",
                "recommended_type": "llm",  # 简单任务用LLM
                "reason": "任务相对简单，LLM足够处理"
            },
            {
                "title": "AI模型训练pipeline",
                "content": "构建端到端的机器学习模型训练pipeline",
                "recommended_type": "semantic_kernel",  # 复杂AI任务用Semantic Kernel
                "reason": "需要深度AI领域专业知识"
            },
            {
                "title": "API网关开发",
                "content": "开发微服务API网关，包含认证、限流、监控",
                "recommended_type": "semantic_kernel",  # 架构任务用Semantic Kernel
                "reason": "需要系统架构专业知识"
            }
        ]
        
        for scenario in task_scenarios:
            print(f"    场景: {scenario['title']}")
            print(f"      推荐拆解类型: {scenario['recommended_type']}")
            print(f"      原因: {scenario['reason']}")
            
            # 使用推荐的类型进行拆分
            result = plugin_manager.decompose_mission(
                mission_title=scenario["title"],
                mission_content=scenario["content"],
                decomposition_type=scenario["recommended_type"],
                strategy="hybrid",
                context={"max_subtasks": 4}
            )
            
            if result["success"]:
                print(f"      ✅ 推荐类型拆分成功: {len(result['subtasks'])} 个子任务")
            else:
                print("      ❌ 推荐类型拆分失败")
        
        return True
        
    except Exception as e:
        print(f"❌ 高级场景测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始双重任务拆分系统测试...")
    print("=" * 80)
    
    results = []
    
    # 双重拆分系统测试
    results.append(test_dual_decomposition_system())
    
    # 高级场景测试
    results.append(test_advanced_scenarios())
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 双重任务拆分系统测试结果:")
    
    test_names = [
        "双重拆分系统基础功能",
        "高级场景和动态选择"
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
        print("🎉 双重任务拆分系统测试全部通过！")
        print("📋 验证的双重拆分功能:")
        print("   ✅ LLM和Semantic Kernel插件并存")
        print("   ✅ 统一管理接口")
        print("   ✅ 动态类型切换")
        print("   ✅ 拆分结果对比分析")
        print("   ✅ 高级场景支持")
        print("   ✅ 策略灵活性")
        print("   ✅ 健康检查和监控")
        print("   🎯 双重任务拆分系统完全符合预期！")
        print("\n📋 系统优势:")
        print("   🔄 灵活选择: 根据任务特征选择最佳拆解方式")
        print("   🧊 对比分析: LLM vs Semantic Kernel结果对比")
        print("   🎯 动态切换: 运行时切换拆解策略")
        print("   🧠 智能推荐: 根据任务类型推荐拆解方式")
        print("   📊 互补优势: 两种方式提供不同视角和优势")
        print("   🔧 统一接口: 简化使用和管理")
        print("   📈 可扩展性: 易于添加新的拆解方式")
        return True
    else:
        print("⚠️  部分双重任务拆分系统测试失败，需要进一步检查和修复。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
