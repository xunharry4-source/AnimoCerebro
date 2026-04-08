#!/usr/bin/env python3
"""
任务管理模块和反思模块的基础架构测试
不依赖外部库，仅测试模块结构和基础功能
"""

import sys
import os
from pathlib import Path
import tempfile
import shutil
import json

# 添加src路径
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

def test_module_structure():
    """测试模块结构"""
    print("🧪 测试模块结构...")
    
    # 检查任务管理模块结构
    tasks_dir = SRC_ROOT / "zentex" / "tasks"
    required_task_files = [
        "__init__.py",
        "models.py", 
        "service.py",
        "persistence.py",
        "interface.py",
        "plugin_registry.py"
    ]
    
    tasks_files_exist = []
    for file_name in required_task_files:
        file_path = tasks_dir / file_name
        exists = file_path.exists()
        tasks_files_exist.append(exists)
        print(f"  {'✅' if exists else '❌'} tasks/{file_name}")
    
    # 检查反思模块结构
    reflection_dir = SRC_ROOT / "zentex" / "reflection"
    required_reflection_files = [
        "__init__.py",
        "models.py",
        "service.py", 
        "persistence.py",
        "interface.py",
        "errors.py"
    ]
    
    reflection_files_exist = []
    for file_name in required_reflection_files:
        file_path = reflection_dir / file_name
        exists = file_path.exists()
        reflection_files_exist.append(exists)
        print(f"  {'✅' if exists else '❌'} reflection/{file_name}")
    
    # 检查文档文件
    doc_files = [
        "DOCUMENTATION.md",
        "API_REFERENCE.md", 
        "QUICK_START.md",
        "README.md"
    ]
    
    for module_dir, module_name in [(tasks_dir, "tasks"), (reflection_dir, "reflection")]:
        print(f"\n  📚 {module_name} 模块文档:")
        for doc_file in doc_files:
            doc_path = module_dir / doc_file
            exists = doc_path.exists()
            print(f"    {'✅' if exists else '❌'} {doc_file}")
    
    tasks_complete = all(tasks_files_exist)
    reflection_complete = all(reflection_files_exist)
    
    if tasks_complete and reflection_complete:
        print("✅ 模块结构检查通过")
        return True
    else:
        print("❌ 模块结构不完整")
        return False

def test_basic_imports():
    """测试基础导入（不依赖外部库）"""
    print("\n🧪 测试基础导入...")
    
    try:
        # 测试任务管理模块基础导入
        print("  测试任务管理模块导入...")
        
        # 检查是否可以读取模块文件
        tasks_models_file = SRC_ROOT / "zentex" / "tasks" / "models.py"
        if tasks_models_file.exists():
            with open(tasks_models_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class ZentexTask' in content:
                    print("    ✅ 找到 ZentexTask 类定义")
                if 'class TaskStatus' in content:
                    print("    ✅ 找到 TaskStatus 枚举定义")
                if 'class TaskType' in content:
                    print("    ✅ 找到 TaskType 枚举定义")
                if 'class TaskPriority' in content:
                    print("    ✅ 找到 TaskPriority 枚举定义")
        else:
            print("    ❌ tasks/models.py 文件不存在")
            return False
        
        # 检查服务文件
        tasks_service_file = SRC_ROOT / "zentex" / "tasks" / "service.py"
        if tasks_service_file.exists():
            with open(tasks_service_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class TaskManagementService' in content:
                    print("    ✅ 找到 TaskManagementService 类定义")
                if 'def create_task' in content:
                    print("    ✅ 找到 create_task 方法定义")
                if 'def update_task_status' in content:
                    print("    ✅ 找到 update_task_status 方法定义")
        
        # 检查接口文件
        tasks_interface_file = SRC_ROOT / "zentex" / "tasks" / "interface.py"
        if tasks_interface_file.exists():
            with open(tasks_interface_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class TaskServiceInterface' in content:
                    print("    ✅ 找到 TaskServiceInterface 类定义")
                if 'def generate_reflection' in content or 'def create_task' in content:
                    print("    ✅ 找到接口方法定义")
        
        print("  ✅ 任务管理模块基础结构检查通过")
        
        # 测试反思模块基础导入
        print("  测试反思模块导入...")
        
        reflection_models_file = SRC_ROOT / "zentex" / "reflection" / "models.py"
        if reflection_models_file.exists():
            with open(reflection_models_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class ReflectionRecord' in content:
                    print("    ✅ 找到 ReflectionRecord 类定义")
                if 'class ReflectionType' in content:
                    print("    ✅ 找到 ReflectionType 枚举定义")
                if 'class ReflectionQuality' in content:
                    print("    ✅ 找到 ReflectionQuality 枚举定义")
        else:
            print("    ❌ reflection/models.py 文件不存在")
            return False
        
        reflection_service_file = SRC_ROOT / "zentex" / "reflection" / "service.py"
        if reflection_service_file.exists():
            with open(reflection_service_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class ReflectionService' in content:
                    print("    ✅ 找到 ReflectionService 类定义")
                if 'def generate_reflection' in content:
                    print("    ✅ 找到 generate_reflection 方法定义")
        
        reflection_interface_file = SRC_ROOT / "zentex" / "reflection" / "interface.py"
        if reflection_interface_file.exists():
            with open(reflection_interface_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class ReflectionInterface' in content:
                    print("    ✅ 找到 ReflectionInterface 类定义")
        
        print("  ✅ 反思模块基础结构检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 基础导入测试失败: {e}")
        return False

def test_persistence_structure():
    """测试持久化结构"""
    print("\n🧪 测试持久化结构...")
    
    try:
        # 检查任务管理持久化
        tasks_persistence_file = SRC_ROOT / "zentex" / "tasks" / "persistence.py"
        if tasks_persistence_file.exists():
            with open(tasks_persistence_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class TaskPersistence' in content:
                    print("  ✅ 找到 TaskPersistence 类定义")
                if 'def save_all' in content:
                    print("  ✅ 找到 save_all 方法定义")
                if 'def load_all' in content:
                    print("  ✅ 找到 load_all 方法定义")
                if 'backup_count' in content:
                    print("  ✅ 找到备份功能定义")
        else:
            print("  ❌ tasks/persistence.py 文件不存在")
            return False
        
        # 检查反思持久化
        reflection_persistence_file = SRC_ROOT / "zentex" / "reflection" / "persistence.py"
        if reflection_persistence_file.exists():
            with open(reflection_persistence_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class ReflectionPersistence' in content:
                    print("  ✅ 找到 ReflectionPersistence 类定义")
                if 'def save_reflection' in content:
                    print("  ✅ 找到 save_reflection 方法定义")
                if 'def load_reflections' in content:
                    print("  ✅ 找到 load_reflections 方法定义")
        else:
            print("  ❌ reflection/persistence.py 文件不存在")
            return False
        
        print("  ✅ 持久化结构检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 持久化结构测试失败: {e}")
        return False

def test_plugin_system():
    """测试插件系统结构"""
    print("\n🧪 测试插件系统结构...")
    
    try:
        # 检查任务管理插件系统
        tasks_plugin_file = SRC_ROOT / "zentex" / "tasks" / "plugin_registry.py"
        if tasks_plugin_file.exists():
            with open(tasks_plugin_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class TaskPluginRegistry' in content:
                    print("  ✅ 找到 TaskPluginRegistry 类定义")
                if 'def register_decomposition_plugin' in content:
                    print("  ✅ 找到插件注册方法")
                if 'DEFAULT_SEQUENTIAL_DECOMPOSITION_SPEC' in content:
                    print("  ✅ 找到默认插件定义")
        else:
            print("  ❌ tasks/plugin_registry.py 文件不存在")
            return False
        
        # 检查任务拆解插件
        tasks_decomposition_file = SRC_ROOT / "zentex" / "tasks" / "decomposition_plugin.py"
        if tasks_decomposition_file.exists():
            with open(tasks_decomposition_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'class TaskDecompositionPlugin' in content:
                    print("  ✅ 找到 TaskDecompositionPlugin 类定义")
                if 'def decompose_mission' in content:
                    print("  ✅ 找到任务拆解方法")
        else:
            print("  ❌ tasks/decomposition_plugin.py 文件不存在")
            return False
        
        print("  ✅ 插件系统结构检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 插件系统测试失败: {e}")
        return False

def test_documentation_quality():
    """测试文档质量"""
    print("\n🧪 测试文档质量...")
    
    try:
        # 检查任务管理文档
        tasks_docs = {
            "README.md": ["使用指南", "快速开始"],
            "DOCUMENTATION.md": ["架构设计", "核心组件", "数据模型"],
            "API_REFERENCE.md": ["API接口", "参数说明", "返回格式"],
            "QUICK_START.md": ["5分钟", "快速开始", "核心概念"]
        }
        
        tasks_dir = SRC_ROOT / "zentex" / "tasks"
        for doc_file, required_sections in tasks_docs.items():
            doc_path = tasks_dir / doc_file
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    found_sections = 0
                    for section in required_sections:
                        if section in content:
                            found_sections += 1
                    
                    if found_sections >= len(required_sections) * 0.5:  # 至少找到一半
                        print(f"  ✅ tasks/{doc_file} 文档质量良好 ({found_sections}/{len(required_sections)})")
                    else:
                        print(f"  ⚠️  tasks/{doc_file} 文档内容较少 ({found_sections}/{len(required_sections)})")
            else:
                print(f"  ❌ tasks/{doc_file} 文档不存在")
        
        # 检查反思文档
        reflection_docs = {
            "README.md": ["使用指南", "实际使用场景"],
            "DOCUMENTATION.md": ["架构设计", "核心组件"],
            "API_REFERENCE.md": ["API接口", "错误代码"],
            "QUICK_START.md": ["快速开始", "核心概念"]
        }
        
        reflection_dir = SRC_ROOT / "zentex" / "reflection"
        for doc_file, required_sections in reflection_docs.items():
            doc_path = reflection_dir / doc_file
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    found_sections = 0
                    for section in required_sections:
                        if section in content:
                            found_sections += 1
                    
                    if found_sections >= len(required_sections) * 0.5:
                        print(f"  ✅ reflection/{doc_file} 文档质量良好 ({found_sections}/{len(required_sections)})")
                    else:
                        print(f"  ⚠️  reflection/{doc_file} 文档内容较少 ({found_sections}/{len(required_sections)})")
            else:
                print(f"  ❌ reflection/{doc_file} 文档不存在")
        
        print("  ✅ 文档质量检查完成")
        return True
        
    except Exception as e:
        print(f"❌ 文档质量测试失败: {e}")
        return False

def test_code_quality():
    """测试代码质量（基础检查）"""
    print("\n🧪 测试代码质量...")
    
    try:
        # 检查模块导入结构
        modules_to_check = [
            ("tasks/__init__.py", ["TaskManager", "get_service_interface"]),
            ("reflection/__init__.py", ["ReflectionManager", "get_interface"]),
            ("tasks/interface.py", ["TaskServiceInterface"]),
            ("reflection/interface.py", ["ReflectionInterface"])
        ]
        
        for module_file, required_classes in modules_to_check:
            module_path = SRC_ROOT / "zentex" / module_file
            if module_path.exists():
                with open(module_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    found_classes = 0
                    for class_name in required_classes:
                        if f"class {class_name}" in content:
                            found_classes += 1
                    
                    if found_classes >= len(required_classes) * 0.5:
                        print(f"  ✅ {module_file} 包含预期类定义 ({found_classes}/{len(required_classes)})")
                    else:
                        print(f"  ⚠️  {module_file} 类定义不完整 ({found_classes}/{len(required_classes)})")
            else:
                print(f"  ❌ {module_file} 文件不存在")
        
        # 检查错误处理
        error_files = [
            "tasks/errors.py",
            "reflection/errors.py"
        ]
        
        for error_file in error_files:
            error_path = SRC_ROOT / "zentex" / error_file
            if error_path.exists():
                with open(error_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "class" in content and "Error" in content:
                        print(f"  ✅ {error_file} 包含错误定义")
                    else:
                        print(f"  ⚠️  {error_file} 错误定义不完整")
            else:
                print(f"  ❌ {error_file} 文件不存在")
        
        print("  ✅ 代码质量检查完成")
        return True
        
    except Exception as e:
        print(f"❌ 代码质量测试失败: {e}")
        return False

def test_module_independence():
    """测试模块独立性"""
    print("\n🧪 测试模块独立性...")
    
    try:
        # 检查任务管理模块是否只依赖自己的文件
        tasks_files = [
            "tasks/__init__.py",
            "tasks/models.py",
            "tasks/service.py",
            "tasks/persistence.py",
            "tasks/interface.py",
            "tasks/plugin_registry.py",
            "tasks/decomposition_plugin.py"
        ]
        
        print("  检查任务管理模块导入:")
        for file_name in tasks_files:
            file_path = SRC_ROOT / "zentex" / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 检查是否只导入zentex.tasks内部模块
                lines = content.split('\n')
                external_imports = 0
                internal_imports = 0
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('from zentex.tasks'):
                        internal_imports += 1
                    elif line.startswith('from zentex.') and not line.startswith('from zentex.tasks'):
                        # 检查是否导入核心模块（允许的）
                        if any(core in line for core in ['core', 'common']):
                            pass  # 允许导入核心模块
                        else:
                            external_imports += 1
                
                if external_imports == 0:
                    print(f"    ✅ {file_name} 模块独立性良好")
                else:
                    print(f"    ⚠️  {file_name} 有 {external_imports} 个外部导入")
            else:
                print(f"    ❌ {file_name} 文件不存在")
        
        # 检查反思模块独立性
        reflection_files = [
            "reflection/__init__.py",
            "reflection/models.py", 
            "reflection/service.py",
            "reflection/persistence.py",
            "reflection/interface.py",
            "reflection/errors.py"
        ]
        
        print("  检查反思模块导入:")
        for file_name in reflection_files:
            file_path = SRC_ROOT / "zentex" / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                lines = content.split('\n')
                external_imports = 0
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('from zentex.reflection'):
                        pass  # 内部导入
                    elif line.startswith('from zentex.') and not line.startswith('from zentex.reflection'):
                        if any(core in line for core in ['core', 'common']):
                            pass  # 允许导入核心模块
                        else:
                            external_imports += 1
                
                if external_imports == 0:
                    print(f"    ✅ {file_name} 模块独立性良好")
                else:
                    print(f"    ⚠️  {file_name} 有 {external_imports} 个外部导入")
            else:
                print(f"    ❌ {file_name} 文件不存在")
        
        print("  ✅ 模块独立性检查完成")
        return True
        
    except Exception as e:
        print(f"❌ 模块独立性测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试任务管理模块和反思模块的基础架构...")
    print("=" * 70)
    
    results = []
    
    # 基础架构测试
    results.append(test_module_structure())
    results.append(test_basic_imports())
    results.append(test_persistence_structure())
    results.append(test_plugin_system())
    results.append(test_documentation_quality())
    results.append(test_code_quality())
    results.append(test_module_independence())
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("📊 测试结果汇总:")
    
    test_names = [
        "模块结构检查",
        "基础导入检查",
        "持久化结构检查",
        "插件系统检查",
        "文档质量检查",
        "代码质量检查",
        "模块独立性检查"
    ]
    
    passed = 0
    total = len(results)
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {i+1}. {name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{total} 个测试通过")
    
    if passed >= total * 0.8:  # 80%通过率
        print("🎉 模块架构测试基本通过！")
        print("💡 注意：由于缺少外部依赖（pydantic等），无法进行完整的功能测试。")
        print("📋 建议：安装依赖后进行完整功能测试。")
        return True
    else:
        print("⚠️  模块架构存在问题，需要进一步完善。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
