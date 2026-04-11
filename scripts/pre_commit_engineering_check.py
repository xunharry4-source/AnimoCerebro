#!/usr/bin/env python3
"""
代码修改前工程规范检查脚本
Pre-modification engineering standards check script

Usage:
    python scripts/pre_commit_engineering_check.py <file_paths...>
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple


class EngineeringStandardsChecker:
    """工程规范自动检查器"""
    
    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self.violations = []
        self.warnings = []
    
    def check_file(self, file_path: str) -> Dict[str, List[str]]:
        """检查单个文件"""
        violations = []
        warnings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return {"violations": [f"无法读取文件: {e}"], "warnings": []}
        
        # 1. 文件用途检查
        if not self._has_file_purpose_comment(content):
            violations.append("缺少文件用途说明 - 需要在文件头部添加说明文件负责什么")
        
        # 2. 职责边界检查
        if not self._has_responsibility_boundary(content):
            violations.append("缺少职责边界说明 - 需要说明文件的主要功能和不负责什么")
        
        # 3. Fail-Closed 行为检查
        silent_fallbacks = self._check_silent_fallbacks(content)
        if silent_fallbacks:
            violations.extend([f"发现静默降级: {fb}" for fb in silent_fallbacks])
        
        # 4. Zentex 特定规则检查
        fake_patterns = self._check_fake_llm_patterns(content)
        if fake_patterns:
            violations.extend([f"发现假LLM输出模式: {fp}" for fp in fake_patterns])
        
        # 5. 测试文件特定检查
        if 'test' in file_path.lower():
            test_issues = self._check_test_standards(content)
            violations.extend(test_issues)
        
        # 6. API 文件特定检查
        if any(keyword in file_path.lower() for keyword in ['api', 'endpoint', 'route']):
            api_issues = self._check_api_standards(content)
            violations.extend(api_issues)
        
        # 7. 文件长度检查 (500行规则)
        length_warning = self._check_file_length(content)
        if length_warning:
            warnings.append(length_warning)
        
        return {
            "violations": violations,
            "warnings": warnings
        }
    
    def _has_file_purpose_comment(self, content: str) -> bool:
        """检查是否有文件用途说明"""
        purpose_patterns = [
            r'""".*文件用途.*"""',
            r'""".*purpose.*"""',
            r'""".*负责.*"""',
            r'""".*功能.*"""',
            r'#.*文件用途',
            r'#.*purpose',
            r'#.*负责',
        ]
        return any(re.search(pattern, content, re.IGNORECASE) for pattern in purpose_patterns)
    
    def _has_responsibility_boundary(self, content: str) -> bool:
        """检查是否有职责边界说明"""
        boundary_patterns = [
            r'职责边界',
            r'responsibility',
            r'不负责',
            r'主要功能',
            r'core.*function',
            r'major.*responsibility',
        ]
        return any(re.search(pattern, content, re.IGNORECASE) for pattern in boundary_patterns)
    
    def _check_silent_fallbacks(self, content: str) -> List[str]:
        """检查静默降级模式"""
        dangerous_patterns = {
            'except Exception:': '裸露的 Exception 捕获',
            'except:': '裸露的 except 语句',
            'return None': '可能返回 None 伪装成功',
            'return {}': '可能返回空字典伪装成功',
            'return ""': '可能返回空字符串伪装成功',
            'pass  #': '可能静默忽略错误',
        }
        
        found = []
        for pattern, description in dangerous_patterns.items():
            if pattern in content:
                # 检查是否在测试文件中（测试文件中可能允许）
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if pattern in line and not self._is_in_test_context(lines, i-1):
                        found.append(f"{description} (第{i}行)")
                        break
        return found
    
    def _check_fake_llm_patterns(self, content: str) -> List[str]:
        """检查假 LLM 输出模式"""
        fake_patterns = {
            'RuleBased': '使用规则链冒充 LLM 输出',
            'static_dict': '使用静态字典冒充认知结果',
            'hardcoded_response': '使用硬编码响应',
            'mock_cognition': '使用模拟认知',
            'fake_completion': '假完成',
        }
        
        found = []
        for pattern, description in fake_patterns.items():
            if pattern in content:
                found.append(description)
        return found
    
    def _check_test_standards(self, content: str) -> List[str]:
        """检查测试特定标准"""
        issues = []
        
        # 检查是否有断言
        if 'def test_' in content and 'assert' not in content:
            issues.append("测试函数缺少断言")
        
        # 检查是否有异常测试
        if 'exception' in content.lower() and 'pytest.raises' not in content:
            issues.append("异常测试建议使用 pytest.raises")
        
        # 检查是否只验证"没报错"
        if 'assert' in content and content.count('assert') == 1:
            lines = content.split('\n')
            for line in lines:
                if 'assert' in line and ('not' in line or 'is' in line):
                    break
            else:
                issues.append("测试可能只验证'没报错'，建议验证具体结果")
        
        return issues
    
    def _check_api_standards(self, content: str) -> List[str]:
        """检查 API 特定标准"""
        issues = []
        
        # 检查返回结构
        if 'return' in content and 'success' not in content:
            issues.append("API 建议返回统一结构包含 success 字段")
        
        # 检查错误处理
        if 'def ' in content and 'try:' not in content:
            issues.append("API 函数建议添加错误处理")
        
        return issues

    def _check_file_length(self, content: str) -> str:
        """检查文件长度是否超过 500 行"""
        lines = content.splitlines()
        line_count = len(lines)
        if line_count > 500:
            return f"文件长度超过 500 行 ({line_count} 行) - 建议考虑将文件拆分为更小的模块"
        return ""
    
    def _is_in_test_context(self, lines: List[str], line_index: int) -> bool:
        """检查是否在测试上下文中"""
        # 简单检查：如果在 test_ 函数内，可能是测试代码
        context_start = max(0, line_index - 10)
        context = lines[context_start:line_index + 1]
        context_text = '\n'.join(context)
        return 'def test_' in context_text
    
    def check_multiple_files(self, file_paths: List[str]) -> Dict[str, Dict[str, List[str]]]:
        """检查多个文件"""
        results = {}
        
        for file_path in file_paths:
            if not Path(file_path).exists():
                results[file_path] = {"violations": [f"文件不存在: {file_path}"], "warnings": []}
                continue
            
            results[file_path] = self.check_file(file_path)
        
        return results


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python pre_commit_engineering_check.py <file_paths...>")
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    checker = EngineeringStandardsChecker(strict_mode=True)
    
    results = checker.check_multiple_files(file_paths)
    
    total_violations = 0
    total_warnings = 0
    
    for file_path, result in results.items():
        violations = result["violations"]
        warnings = result["warnings"]
        
        if violations or warnings:
            print(f"\n📁 {file_path}")
            
            if violations:
                print("  ❌ 违规:")
                for violation in violations:
                    print(f"    - {violation}")
                total_violations += len(violations)
            
            if warnings:
                print("  ⚠️ 警告:")
                for warning in warnings:
                    print(f"    - {warning}")
                total_warnings += len(warnings)
        else:
            print(f"✅ {file_path} - 工程规范检查通过")
    
    print(f"\n📊 总结:")
    print(f"  违规: {total_violations}")
    print(f"  警告: {total_warnings}")
    
    if total_violations > 0:
        print("\n❌ 发现工程规范违规，请修复后重试")
        sys.exit(1)
    else:
        print("\n✅ 所有文件通过工程规范检查")
        sys.exit(0)


if __name__ == "__main__":
    main()
