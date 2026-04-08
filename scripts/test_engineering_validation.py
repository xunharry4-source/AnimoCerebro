#!/usr/bin/env python3
"""
测试时工程标准验证脚本
Test-time engineering standards validation

Usage:
    python scripts/test_engineering_validation.py <test_file_paths...>
"""

import sys
import ast
import re
from pathlib import Path
from typing import Dict, List, Set


class TestEngineeringValidator:
    """测试工程标准验证器"""
    
    def __init__(self):
        self.violations = []
        self.warnings = []
    
    def validate_test_file(self, test_file_path: str) -> Dict[str, List[str]]:
        """验证测试文件符合工程标准"""
        violations = []
        warnings = []
        
        try:
            with open(test_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)
        except Exception as e:
            return {"violations": [f"无法解析测试文件: {e}"], "warnings": []}
        
        # 1. 基础测试结构检查
        structure_issues = self._check_test_structure(tree, content)
        violations.extend(structure_issues)
        
        # 2. 测试覆盖检查
        coverage_issues = self._check_test_coverage(tree, content)
        violations.extend(coverage_issues)
        
        # 3. 负向测试检查
        negative_issues = self._check_negative_testing(tree, content)
        violations.extend(negative_issues)
        
        # 4. 测试真实性检查
        reality_issues = self._check_test_reality(tree, content)
        violations.extend(reality_issues)
        
        # 5. 隔离性检查
        isolation_issues = self._check_test_isolation(tree, content)
        violations.extend(isolation_issues)
        
        return {
            "violations": violations,
            "warnings": warnings
        }
    
    def _check_test_structure(self, tree: ast.AST, content: str) -> List[str]:
        """检查测试基础结构"""
        issues = []
        
        test_functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) 
                       and node.name.startswith('test_')]
        
        if not test_functions:
            issues.append("未找到测试函数 (函数名应以 test_ 开头)")
            return issues
        
        # 检查每个测试函数
        for func in test_functions:
            # 检查是否有文档字符串
            if not ast.get_docstring(func):
                issues.append(f"测试函数 {func.name} 缺少文档字符串")
            
            # 检查函数体是否为空
            if not func.body:
                issues.append(f"测试函数 {func.name} 函数体为空")
        
        return issues
    
    def _check_test_coverage(self, tree: ast.AST, content: str) -> List[str]:
        """检查测试覆盖度"""
        issues = []
        
        test_functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) 
                       and node.name.startswith('test_')]
        
        for func in test_functions:
            func_content = self._extract_function_content(content, func)
            
            # 检查是否有断言
            if 'assert' not in func_content:
                issues.append(f"测试函数 {func.name} 缺少断言")
                continue
            
            # 检查断言质量
            assert_count = func_content.count('assert')
            if assert_count == 1:
                # 检查是否只是简单的"不报错"测试
                lines = func_content.split('\n')
                for line in lines:
                    if 'assert' in line:
                        if any(keyword in line.lower() for keyword in ['true', 'not none', 'is not']):
                            pass  # 具体验证，可以
                        else:
                            issues.append(f"测试函数 {func.name} 可能只验证'不报错'，建议验证具体结果")
                        break
        
        return issues
    
    def _check_negative_testing(self, tree: ast.AST, content: str) -> List[str]:
        """检查负向测试"""
        issues = []
        
        # 检查是否有异常测试
        has_exception_test = False
        has_pytest_raises = 'pytest.raises' in content
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                func_content = self._extract_function_content(content, node)
                
                # 检查是否测试异常情况
                exception_keywords = ['exception', 'error', 'invalid', 'fail', 'raise']
                if any(keyword in func_content.lower() for keyword in exception_keywords):
                    has_exception_test = True
                    
                    # 如果测试异常但没有使用 pytest.raises
                    if not has_pytest_raises:
                        issues.append(f"测试函数 {node.name} 测试异常情况但未使用 pytest.raises")
        
        # 检查是否有边界条件测试
        boundary_keywords = ['boundary', 'edge', 'limit', 'max', 'min', 'empty', 'null']
        has_boundary_test = any(keyword in content.lower() for keyword in boundary_keywords)
        
        if not has_boundary_test:
            issues.append("建议添加边界条件测试")
        
        return issues
    
    def _check_test_reality(self, tree: ast.AST, content: str) -> List[str]:
        """检查测试真实性"""
        issues = []
        
        # 检查是否只验证状态码
        if 'status_code' in content and '200' in content:
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'status_code' in line and '200' in line and 'assert' not in line:
                    issues.append(f"第{i}行: 建议验证具体响应内容而非仅状态码")
        
        # 检查是否有假数据测试
        fake_patterns = ['fake', 'mock', 'stub', 'dummy']
        has_fake_data = any(pattern in content.lower() for pattern in fake_patterns)
        
        if has_fake_data:
            # 检查是否明确标注为测试数据
            if 'test_data' not in content and 'fixture' not in content:
                issues.append("使用假数据但未明确标注为测试数据或 fixture")
        
        return issues
    
    def _check_test_isolation(self, tree: ast.AST, content: str) -> List[str]:
        """检查测试隔离性"""
        issues = []
        
        # 检查是否有外部依赖
        dangerous_imports = [
            'requests', 'urllib', 'http', 'database', 'db', 'redis', 'mongo'
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(danger in alias.name.lower() for danger in dangerous_imports):
                        issues.append(f"Testing imports potential external dependency: {alias.name}")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(danger in node.module.lower() for danger in dangerous_imports):
                    issues.append(f"Testing imports potential external dependency: {node.module}")
        
        # 检查是否有文件系统操作
        fs_operations = ['open(', 'write(', 'delete(', 'remove(']
        for operation in fs_operations:
            if operation in content:
                issues.append(f"Testing contains file system operation: {operation}, suggest using temporary files")
        
        return issues
    
    def _extract_function_content(self, full_content: str, func_node: ast.FunctionDef) -> str:
        """提取函数内容"""
        lines = full_content.split('\n')
        start_line = func_node.lineno - 1
        end_line = func_node.end_lineno
        
        return '\n'.join(lines[start_line:end_line])
    
    def validate_test_suite(self, test_file_paths: List[str]) -> Dict[str, Dict[str, List[str]]]:
        """验证整个测试套件"""
        results = {}
        
        for file_path in test_file_paths:
            if not Path(file_path).exists():
                results[file_path] = {"violations": [f"测试文件不存在: {file_path}"], "warnings": []}
                continue
            
            results[file_path] = self.validate_test_file(file_path)
        
        # 检查整体测试覆盖
        coverage_issues = self._check_suite_coverage(test_file_paths)
        if coverage_issues:
            # 添加到第一个文件的违规中
            first_file = list(results.keys())[0]
            results[first_file]["violations"].extend(coverage_issues)
        
        return results
    
    def _check_suite_coverage(self, test_file_paths: List[str]) -> List[str]:
        """检查测试套件整体覆盖"""
        issues = []
        
        all_content = ""
        for file_path in test_file_paths:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    all_content += f.read() + "\n"
            except:
                continue
        
        # 检查测试类型覆盖
        test_types = {
            "unit": "单元测试",
            "integration": "集成测试", 
            "api": "API测试",
            "negative": "负向测试",
            "performance": "性能测试",
        }
        
        found_types = set()
        for test_type, description in test_types.items():
            if test_type in all_content.lower():
                found_types.add(test_type)
        
        missing_types = set(test_types.keys()) - found_types
        if missing_types:
            missing_descriptions = [test_types[t] for t in missing_types]
            issues.append(f"建议添加以下测试类型: {', '.join(missing_descriptions)}")
        
        return issues


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python test_engineering_validation.py <test_file_paths...>")
        sys.exit(1)
    
    test_file_paths = sys.argv[1:]
    validator = TestEngineeringValidator()
    
    results = validator.validate_test_suite(test_file_paths)
    
    total_violations = 0
    total_warnings = 0
    
    for file_path, result in results.items():
        violations = result["violations"]
        warnings = result["warnings"]
        
        if violations or warnings:
            print(f"\n🧪 {file_path}")
            
            if violations:
                print("  ❌ 测试规范违规:")
                for violation in violations:
                    print(f"    - {violation}")
                total_violations += len(violations)
            
            if warnings:
                print("  ⚠️ 测试警告:")
                for warning in warnings:
                    print(f"    - {warning}")
                total_warnings += len(warnings)
        else:
            print(f"✅ {file_path} - 测试工程规范检查通过")
    
    print(f"\n📊 测试验证总结:")
    print(f"  违规: {total_violations}")
    print(f"  警告: {total_warnings}")
    
    if total_violations > 0:
        print("\n❌ 发现测试工程规范违规，请修复后重试")
        print("\n💡 修复建议:")
        print("  1. 为每个测试函数添加文档字符串")
        print("  2. 确保测试有具体的断言验证")
        print("  3. 异常测试使用 pytest.raises")
        print("  4. 添加边界条件和负向测试")
        print("  5. 使用测试隔离和临时数据")
        sys.exit(1)
    else:
        print("\n✅ 所有测试文件通过工程规范检查")
        sys.exit(0)


if __name__ == "__main__":
    main()
