"""
任务系统中的产品文档保存与查看示例

展示如何：
1. 创建产品文档
2. 转换为任务列表（自动保存产品文档）
3. 将任务列表保存到JSON
4. 从任务列表查看原始产品文档
"""

from pathlib import Path
from zentex.tasks.product_document import (
    ProductDocument,
    FunctionalModule,
    FeaturePoint,
    ProjectObjective,
    ProjectPlan,
    ValidationSet,
    ValidationMethod,
    ValidationType,
)
from zentex.tasks.task_generator import (
    convert_product_document_to_task_list,
    save_task_list_to_json,
    load_task_list_from_json,
    get_product_document_from_task_list,
    get_task_list_with_product_context,
)
import json


def create_example_product_document() -> ProductDocument:
    """创建示例产品文档"""
    
    # 创建验证方法
    unit_test_method = ValidationMethod(
        method_type=ValidationType.AUTOMATED_TEST,
        description="使用pytest进行单元测试",
        criteria=["代码覆盖率≥80%", "所有测试用例通过"],
        tools=["pytest", "coverage"],
    )
    
    integration_test_method = ValidationMethod(
        method_type=ValidationType.INTEGRATION_TEST,
        description="使用pytest进行集成测试",
        criteria=["API返回正确响应", "数据库事务完整"],
        tools=["pytest", "Docker"],
    )
    
    # 创建验证集
    feature_validation = ValidationSet(
        primary=unit_test_method,
        secondary=[integration_test_method],
    )
    
    module_validation = ValidationSet(
        primary=ValidationMethod(
            method_type=ValidationType.INTEGRATION_TEST,
            description="验证模块之间的集成",
            criteria=["模块间通信正常", "性能指标达到标准"],
            tools=["pytest", "locust"],
        ),
    )
    
    # 创建功能点
    feature_points = [
        FeaturePoint(
            name="用户认证",
            description="实现用户登录认证功能",
            requirement="支持用户名/密码登录",
            validation=feature_validation,
            dependencies=["密码加密库"],
            estimated_hours=16,
            complexity="medium",
            implementation_notes="使用JWT令牌，需要集成OAuth支持",
        ),
        FeaturePoint(
            name="用户信息管理",
            description="管理用户个人信息",
            requirement="支持修改个人资料",
            validation=feature_validation,
            dependencies=["数据库ORM"],
            estimated_hours=12,
            complexity="low",
        ),
        FeaturePoint(
            name="权限控制",
            description="实现基于角色的权限控制",
            requirement="支持RBAC模型",
            validation=feature_validation,
            dependencies=["用户认证"],
            estimated_hours=20,
            complexity="high",
            implementation_notes="需要支持动态权限加载",
        ),
    ]
    
    # 创建用户模块
    user_module = FunctionalModule(
        name="用户管理模块",
        description="负责用户认证、信息管理和权限控制",
        feature_points=feature_points,
        priority="high",
        risk_level="high",
        dependencies=[],
        blockers=[],
        module_validation=module_validation,
    )
    
    # 创建API模块的功能点
    api_features = [
        FeaturePoint(
            name="RESTful API设计",
            description="设计和实现RESTful API",
            requirement="遵循REST规范",
            validation=feature_validation,
            dependencies=["Flask框架"],
            estimated_hours=24,
            complexity="medium",
        ),
        FeaturePoint(
            name="API文档",
            description="使用Swagger生成API文档",
            requirement="完整的API文档",
            validation=ValidationSet(
                primary=ValidationMethod(
                    method_type=ValidationType.DOCUMENTATION_CHECK,
                    description="检查文档完整性",
                    criteria=["所有端点已文档化", "示例请求/响应完整"],
                    tools=["Swagger UI"],
                ),
            ),
            dependencies=["Swagger库"],
            estimated_hours=10,
            complexity="low",
        ),
    ]
    
    api_module = FunctionalModule(
        name="API服务模块",
        description="提供RESTful API服务",
        feature_points=api_features,
        priority="high",
        risk_level="medium",
        dependencies=[user_module.id],  # 依赖用户模块的实际ID
        blockers=[],
    )
    
    # 创建项目目标
    objectives = [
        ProjectObjective(
            name="完成基础框架",
            description="建立完整的Web应用框架",
            related_modules=["user_id", "api_id"],
            success_criteria=["所有模块可正常启动", "基本功能测试通过"],
            business_impact="为后续功能开发奠定基础",
        ),
        ProjectObjective(
            name="提高代码质量",
            description="确保代码质量达到行业标准",
            related_modules=["user_id"],
            success_criteria=["代码覆盖率≥80%", "无严重bugs"],
            business_impact="提升产品稳定性和可维护性",
        ),
    ]
    
    # 创建项目计划
    from datetime import datetime, timedelta
    plan = ProjectPlan(
        name="用户认证系统项目计划",
        description="从需求分析到上线的完整项目计划",
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 6, 30),
        team_members=["张三 (项目经理)", "李四 (后端开发)", "王五 (测试)"],
        estimated_total_hours=200,
    )
    # 添加里程碑
    plan.add_milestone("框架搭建完成", datetime(2024, 4, 15))
    plan.add_milestone("核心功能完成", datetime(2024, 5, 15))
    plan.add_milestone("测试和优化", datetime(2024, 6, 15))
    # 添加风险
    plan.add_risk("第三方依赖可用性", "准备备用方案")
    plan.add_risk("性能优化时间紧张", "优先进行性能测试")
    
    # 创建产品文档
    product_doc = ProductDocument(
        name="用户认证和API管理系统",
        version="1.0.0",
        description="一个完整的用户认证和RESTful API系统",
        project_plan=plan,
    )
    
    # 添加项目目标
    for obj in objectives:
        product_doc.add_objective(obj)
    
    # 添加功能模块
    for module in [user_module, api_module]:
        product_doc.add_module(module)
    
    return product_doc


def example_save_and_view():
    """演示保存任务列表和查看产品文档"""
    
    print("=" * 80)
    print("示例：任务系统中保存和查看产品文档")
    print("=" * 80)
    print()
    
    # 1. 创建产品文档
    print("1️⃣  创建产品文档...")
    product_doc = create_example_product_document()
    print(f"   ✓ 产品文档: {product_doc.name} v{product_doc.version}")
    print(f"   ✓ 包含 {len(product_doc.functional_modules)} 个功能模块")
    print()
    
    # 2. 转换为任务列表（自动保存产品文档）
    print("2️⃣  转换产品文档为任务列表...")
    task_list, errors = convert_product_document_to_task_list(product_doc)
    if errors:
        print(f"   ⚠️  警告: {errors}")
    else:
        print(f"   ✓ 成功转换为任务列表")
        print(f"   ✓ 任务列表ID: {task_list.id}")
        print(f"   ✓ 包含 {len(task_list.tasks)} 个任务")
        print(f"   ✓ 产品文档已在任务列表中: {task_list.product_document_data is not None}")
    print()
    
    # 3. 保存任务列表到JSON（包含产品文档）
    print("3️⃣  保存任务列表到JSON文件...")
    output_dir = Path("/tmp/zentex_tasks")
    output_file = output_dir / "task_list_with_document.json"
    success, error = save_task_list_to_json(task_list, output_file)
    if success:
        print(f"   ✓ 任务列表已保存到: {output_file}")
        print(f"   ✓ 文件大小: {output_file.stat().st_size} 字节")
    else:
        print(f"   ✗ 保存失败: {error}")
    print()
    
    # 4. 从JSON加载任务列表
    print("4️⃣  从JSON加载任务列表...")
    loaded_task_list, error = load_task_list_from_json(output_file)
    if error:
        print(f"   ✗ 加载失败: {error}")
    else:
        print(f"   ✓ 任务列表已加载")
        print(f"   ✓ 任务数量: {len(loaded_task_list.tasks)}")
    print()
    
    # 5. 从任务列表查看产品文档
    print("5️⃣  从任务列表查看原始产品文档...")
    product_doc_from_task = get_product_document_from_task_list(loaded_task_list)
    if product_doc_from_task:
        print(f"   ✓ 产品文档数据已恢复")
        print(f"   ✓ 产品名称: {product_doc_from_task.get('name')}")
        print(f"   ✓ 版本: {product_doc_from_task.get('version')}")
        print(f"   ✓ 功能模块: {len(product_doc_from_task.get('functional_modules', []))} 个")
        print()
        
        # 显示模块信息
        print("   📦 功能模块列表:")
        for module in product_doc_from_task.get('functional_modules', []):
            print(f"     - {module.get('name')} (优先级: {module.get('priority')})")
            print(f"       功能点数: {len(module.get('feature_points', []))}")
    else:
        print("   ✗ 无法恢复产品文档数据")
    print()
    
    # 6. 获取包含产品上下文的完整任务列表
    print("6️⃣  获取包含产品上下文的完整任务列表...")
    full_context = get_task_list_with_product_context(loaded_task_list)
    print(f"   ✓ 已生成上下文数据")
    print(f"   ✓ 包含:")
    print(f"     - 任务列表ID: {full_context['task_list_id']}")
    print(f"     - 产品文档ID: {full_context['product_document_id']}")
    print(f"     - 产品名称: {full_context['product_document_name']}")
    print(f"     - 任务总数: {full_context['tasks_summary']['total_tasks']}")
    print(f"     - 子任务总数: {full_context['tasks_summary']['total_subtasks']}")
    print(f"     - 总工时: {full_context['tasks_summary']['total_estimated_hours']} 小时")
    print()
    
    # 7. 保存完整上下文为JSON
    print("7️⃣  保存完整上下文为JSON...")
    context_file = output_dir / "task_list_full_context.json"
    with open(context_file, 'w', encoding='utf-8') as f:
        json.dump(full_context, f, ensure_ascii=False, indent=2)
    print(f"   ✓ 完整上下文已保存到: {context_file}")
    print()
    
    # 8. 任务查看示例
    print("8️⃣  任务查看示例（包含产品文档引用）...")
    print()
    print("   在任务系统中查看任务时，用户可以:")
    print("   ✓ 查看单个任务和子任务")
    print("   ✓ 查看任务关联的原始产品文档")
    print("   ✓ 了解产品文档中的功能模块和功能点")
    print("   ✓ 查看产品文档中的系统架构和计划信息")
    print()
    
    # 显示任务摘要
    print("   📋 任务摘要:")
    stats = loaded_task_list.get_summary_stats()
    print(f"   - 总任务数: {stats['total_tasks']}")
    print(f"   - 总子任务数: {stats['total_subtasks']}")
    print(f"   - 总工时: {stats['total_estimated_hours']} 小时")
    print(f"   - 优先级分布: {stats['priority_distribution']}")
    print()


if __name__ == "__main__":
    example_save_and_view()
