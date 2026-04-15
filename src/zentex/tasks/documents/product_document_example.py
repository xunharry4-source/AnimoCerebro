"""
产品文档和任务生成系统 - 完整示例

演示如何：
1. 创建产品文档
2. 组织项目信息（计划、目标、模块、功能点）
3. 转换为任务列表
4. 生成验证框架
"""

from datetime import datetime, timedelta
from zentex.tasks.product_document import (
    ProductDocument,
    ProjectPlan,
    ProjectObjective,
    FunctionalModule,
    FeaturePoint,
    ValidationMethod,
    ValidationType,
    create_feature_point,
    create_functional_module,
    create_project_objective,
)
from zentex.tasks.task_generator import (
    convert_product_document_to_task_list,
)


def example_create_product_document() -> ProductDocument:
    """
    创建一个示例产品文档，演示完整的项目组织结构
    """
    
    # ========================================================================
    # 1. 创建产品文档
    # ========================================================================
    product_doc = ProductDocument(
        name="Zentex 任务编排系统优化",
        version="1.0.0",
        description="优化任务编排系统的前置条件处理和自动化任务生成",
        scope="涵盖产品文档规范化、任务生成、验证框架三个主要模块",
    )
    
    # ========================================================================
    # 2. 定义项目计划
    # ========================================================================
    now = datetime.now()
    product_doc.project_plan.name = "Zentex 优化项目计划"
    product_doc.project_plan.description = "4周时间完成任务系统优化"
    product_doc.project_plan.start_date = now
    product_doc.project_plan.end_date = now + timedelta(days=28)
    product_doc.project_plan.team_members = ["系统架构师", "后端开发", "测试工程师"]
    
    # 添加里程碑
    product_doc.project_plan.add_milestone("产品文档规范定义", now + timedelta(days=7))
    product_doc.project_plan.add_milestone("任务生成系统完成", now + timedelta(days=14))
    product_doc.project_plan.add_milestone("验证框架集成", now + timedelta(days=21))
    product_doc.project_plan.add_milestone("系统测试发布", now + timedelta(days=28))
    
    # 添加风险
    product_doc.project_plan.add_risk(
        "LLM集成复杂度高",
        "提前进行技术调研，预留充足的开发时间"
    )
    product_doc.project_plan.add_risk(
        "数据库性能问题",
        "优先做性能测试和优化，必要时调整架构"
    )
    
    # ========================================================================
    # 3. 定义项目目标
    # ========================================================================
    
    # 目标1: 提高任务发布效率
    obj1 = create_project_objective(
        name="提高任务发布效率60%",
        description="通过产品文档规范化和自动化任务生成，减少手工任务创建时间",
        success_criteria=[
            "从产品文档生成任务耗时 < 5分钟",
            "任务结构化率 = 100%",
            "自动生成任务准确率 > 95%",
        ],
        priority=1,
    )
    obj1.business_impact = "降低项目管理成本，加快项目交付"
    product_doc.add_objective(obj1)
    
    # 目标2: 规范化项目信息管理
    obj2 = create_project_objective(
        name="建立统一的产品文档规范",
        description="定义产品文档的标准结构和内容要求",
        success_criteria=[
            "产品文档规范文档完成度 = 100%",
            "团队采用率 = 100%",
            "文档维护自动化率 > 80%",
        ],
        priority=2,
    )
    obj2.business_impact = "提高信息质量和一致性，便于知识积累"
    product_doc.add_objective(obj2)
    
    # 目标3: 完善任务验证框架
    obj3 = create_project_objective(
        name="建立完整的任务验证框架",
        description="为每个任务定义清晰的验证方法和成功标准",
        success_criteria=[
            "支持10+种验证方法",
            "验收标准自动化覆盖率 > 90%",
            "验证失败率 < 2%",
        ],
        priority=2,
    )
    obj3.business_impact = "确保任务质量，提高交付物满足度"
    product_doc.add_objective(obj3)
    
    # ========================================================================
    # 4. 定义功能模块和功能点
    # ========================================================================
    
    # ---- 模块1: 产品文档规范 ----
    module1 = create_functional_module(
        name="产品文档规范系统",
        description="定义和实现产品文档的标准格式和验证规则",
        priority="critical",
    )
    module1.risk_level = "low"
    
    # 功能点1.1
    fp1_1 = create_feature_point(
        name="ProductDocument 数据模型",
        description="定义产品文档的核心数据结构",
        requirement="支持项目计划、目标、模块、功能点的完整组织",
        estimated_hours=8,
        complexity="medium",
        validation_type=ValidationType.AUTOMATED_TEST,
        validation_criteria=[
            "所有字段类型正确",
            "序列化/反序列化正确",
            "数据验证完整",
        ],
    )
    module1.add_feature_point(fp1_1)
    
    # 功能点1.2
    fp1_2 = create_feature_point(
        name="文档验证引擎",
        description="验证产品文档的完整性和一致性",
        requirement="检测缺失字段、依赖关系、命名规范等",
        estimated_hours=6,
        complexity="medium",
        validation_type=ValidationType.AUTOMATED_TEST,
        validation_criteria=[
            "能检测所有类型的错误",
            "错误消息清晰",
            "性能 < 100ms",
        ],
    )
    module1.add_feature_point(fp1_2)
    
    # 功能点1.3
    fp1_3 = create_feature_point(
        name="Markdown 文档生成",
        description="将产品文档转换为可读的Markdown格式",
        requirement="支持多层级结构的格式化输出",
        estimated_hours=4,
        complexity="low",
        validation_type=ValidationType.DOCUMENTATION_CHECK,
        validation_criteria=[
            "格式符合Markdown规范",
            "显示效果美观",
            "内容完整性100%",
        ],
    )
    module1.add_feature_point(fp1_3)
    
    obj1.related_modules.append(module1.id)
    obj2.related_modules.append(module1.id)
    product_doc.add_module(module1)
    
    # ---- 模块2: 任务生成系统 ----
    module2 = create_functional_module(
        name="自动任务生成系统",
        description="从产品文档自动生成结构化的任务列表",
        priority="critical",
    )
    module2.risk_level = "medium"
    module2.dependencies.append(module1.id)  # 依赖模块1
    
    # 功能点2.1
    fp2_1 = create_feature_point(
        name="任务模型定义",
        description="定义GeneratedTask和SubTask数据结构",
        requirement="支持所有必要的任务属性和元数据",
        estimated_hours=8,
        complexity="medium",
        validation_type=ValidationType.AUTOMATED_TEST,
        validation_criteria=[
            "数据结构完整",
            "支持序列化/反序列化",
            "关联关系正确",
        ],
    )
    module2.add_feature_point(fp2_1)
    
    # 功能点2.2
    fp2_2 = create_feature_point(
        name="转换器实现",
        description="从ProductDocument转换到GeneratedTask",
        requirement="完整转换所有功能模块和功能点为任务",
        estimated_hours=12,
        complexity="high",
        validation_type=ValidationType.INTEGRATION_TEST,
        validation_criteria=[
            "转换准确率 > 95%",
            "保留所有关键信息",
            "性能 < 500ms",
            "错误处理完善",
        ],
    )
    fp2_2.implementation_notes = "需要处理复杂的依赖关系转换"
    module2.add_feature_point(fp2_2)
    
    # 功能点2.3
    fp2_3 = create_feature_point(
        name="任务列表管理",
        description="提供任务列表的查询和排序功能",
        requirement="支持按优先级、依赖关系排序",
        estimated_hours=6,
        complexity="medium",
        validation_type=ValidationType.AUTOMATED_TEST,
        validation_criteria=[
            "排序算法正确",
            "依赖关系处理正确",
            "查询性能优化",
        ],
    )
    module2.add_feature_point(fp2_3)
    
    # 功能点2.4
    fp2_4 = create_feature_point(
        name="任务报告生成",
        description="生成任务列表的详细Markdown报告",
        requirement="显示任务树、统计信息、验证框架",
        estimated_hours=5,
        complexity="low",
        validation_type=ValidationType.DOCUMENTATION_CHECK,
        validation_criteria=[
            "报告格式正确",
            "信息完整",
            "统计数据准确",
        ],
    )
    module2.add_feature_point(fp2_4)
    
    obj1.related_modules.append(module2.id)
    product_doc.add_module(module2)
    
    # ---- 模块3: 验证框架集成 ----
    module3 = create_functional_module(
        name="验证框架与测试体系",
        description="为所有功能集成完整的验证框架",
        priority="high",
    )
    module3.risk_level = "medium"
    module3.dependencies.append(module2.id)  # 依赖模块2
    
    # 功能点3.1
    fp3_1 = create_feature_point(
        name="单元测试套件",
        description="为所有功能编写单元测试",
        requirement="测试覆盖率 >= 85%",
        estimated_hours=16,
        complexity="medium",
        validation_type=ValidationType.AUTOMATED_TEST,
        validation_criteria=[
            "覆盖率 >= 85%",
            "所有测试通过",
            "测试执行时间 < 10s",
        ],
    )
    module3.add_feature_point(fp3_1)
    
    # 功能点3.2
    fp3_2 = create_feature_point(
        name="集成测试",
        description="端到端的系统集成测试",
        requirement="完整流程测试从产品文档到任务列表",
        estimated_hours=10,
        complexity="high",
        validation_type=ValidationType.INTEGRATION_TEST,
        validation_criteria=[
            "完整流程通过",
            "边界条件处理正确",
            "错误恢复能力强",
        ],
    )
    module3.add_feature_point(fp3_2)
    
    # 功能点3.3
    fp3_3 = create_feature_point(
        name="性能测试",
        description="验证系统性能和可扩展性",
        requirement="支持大型项目（1000+功能点）",
        estimated_hours=8,
        complexity="medium",
        validation_type=ValidationType.PERFORMANCE_TEST,
        validation_criteria=[
            "文档转换 < 1秒",
            "内存占用 < 100MB",
            "支持10,000+功能点",
        ],
    )
    module3.add_feature_point(fp3_3)
    
    # 功能点3.4
    fp3_4 = create_feature_point(
        name="文档和示例",
        description="编写完整的API文档和使用示例",
        requirement="包括快速开始、完整参考、错误处理",
        estimated_hours=6,
        complexity="low",
        validation_type=ValidationType.DOCUMENTATION_CHECK,
        validation_criteria=[
            "文档完整度 = 100%",
            "示例可运行",
            "覆盖所有主要功能",
        ],
    )
    module3.add_feature_point(fp3_4)
    
    obj3.related_modules.append(module3.id)
    product_doc.add_module(module3)
    
    # ========================================================================
    # 验证文档
    # ========================================================================
    is_valid, errors = product_doc.validate_document()
    if not is_valid:
        print("❌ 产品文档验证失败:")
        for error in errors:
            print(f"  - {error}")
        raise ValueError("产品文档验证失败")
    
    print("✅ 产品文档创建成功")
    print(f"   - 项目: {product_doc.name}")
    print(f"   - 目标: {len(product_doc.project_objectives)} 个")
    print(f"   - 模块: {len(product_doc.functional_modules)} 个")
    print(f"   - 功能点: {sum(len(m.feature_points) for m in product_doc.functional_modules)} 个")
    print(f"   - 总工时: {product_doc.project_plan.estimated_total_hours} 小时")
    
    return product_doc


def example_convert_to_task_list():
    """
    演示如何将产品文档转换为任务列表
    """
    print("\n" + "="*70)
    print("产品文档转任务列表演示")
    print("="*70 + "\n")
    
    # 1. 创建产品文档
    product_doc = example_create_product_document()
    
    # 2. 转换为任务列表
    print("\n转换产品文档为任务列表...\n")
    task_list, errors = convert_product_document_to_task_list(product_doc)
    
    if errors:
        print("❌ 转换过程中出现错误:")
        for error in errors:
            print(f"  - {error}")
        return
    
    print("✅ 转换完成!")
    print(f"   - 生成任务数: {len(task_list.tasks)}")
    print(f"   - 总子任务数: {sum(len(t.subtasks) for t in task_list.tasks)}")
    
    # 3. 显示摘要统计
    print("\n摘要统计:")
    stats = task_list.get_summary_stats()
    print(f"  - 总工时: {stats['total_estimated_hours']} 小时")
    print(f"  - 验证方法: {', '.join(stats['verification_methods'])}")
    
    # 4. 生成Markdown报告
    print("\n生成任务列表报告...\n")
    report = task_list.generate_markdown_report()
    print(report)
    
    # 5. 生成产品文档Markdown
    print("\n" + "="*70)
    print("产品文档详情")
    print("="*70 + "\n")
    doc_markdown = product_doc.generate_markdown_document()
    print(doc_markdown)
    
    return task_list


if __name__ == "__main__":
    example_convert_to_task_list()
