#!/usr/bin/env python3
"""
IDE 集成工程规范检查
IDE integration for engineering standards check

支持 VS Code 和其他编辑器的实时检查
"""

import os
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class EngineeringStandardsHandler(FileSystemEventHandler):
    """文件变更时自动检查工程规范"""
    
    def __init__(self):
        self.last_check = {}
        self.check_interval = 2  # 秒
        
    def on_modified(self, event):
        """文件修改时触发检查"""
        if event.is_directory:
            return
            
        file_path = event.src_path
        if not file_path.endswith('.py'):
            return
            
        # 防止重复检查
        current_time = time.time()
        if file_path in self.last_check:
            if current_time - self.last_check[file_path] < self.check_interval:
                return
        
        self.last_check[file_path] = current_time
        
        # 延迟检查，等待文件写入完成
        time.sleep(0.5)
        self.check_file_standards(file_path)
    
    def check_file_standards(self, file_path: str):
        """检查单个文件的工程规范"""
        try:
            # 导入检查器
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from pre_commit_engineering_check import EngineeringStandardsChecker
            
            checker = EngineeringStandardsChecker(strict_mode=False)  # IDE 模式不严格阻止
            
            result = checker.check_file(file_path)
            violations = result["violations"]
            warnings = result["warnings"]
            
            if violations or warnings:
                self.show_issues_in_ide(file_path, violations, warnings)
            else:
                self.clear_issues_in_ide(file_path)
                
        except Exception as e:
            print(f"⚠️ 检查 {file_path} 时出错: {e}")
    
    def show_issues_in_ide(self, file_path: str, violations: list, warnings: list):
        """在 IDE 中显示问题"""
        # VS Code 输出格式
        if os.getenv('VSCODE_PID'):
            for violation in violations:
                print(f"::error file={file_path},line=1,col=1::{violation}")
            for warning in warnings:
                print(f"::warning file={file_path},line=1,col=1::{warning}")
        else:
            # 通用输出格式
            print(f"\n🔍 {file_path} 工程规范检查:")
            if violations:
                print("  ❌ 违规:")
                for v in violations:
                    print(f"    - {v}")
            if warnings:
                print("  ⚠️ 警告:")
                for w in warnings:
                    print(f"    - {w}")
    
    def clear_issues_in_ide(self, file_path: str):
        """清除 IDE 中的问题显示"""
        if os.getenv('VSCODE_PID'):
            print(f"::info file={file_path},line=1,col=1::工程规范检查通过")


def start_ide_monitoring():
    """启动 IDE 监控模式"""
    print("🚀 启动工程规范实时监控...")
    print("监控当前目录下的 Python 文件变更...")
    print("按 Ctrl+C 停止监控")
    
    event_handler = EngineeringStandardsHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 停止监控")


def check_current_directory():
    """检查当前目录所有 Python 文件"""
    print("🔍 检查当前目录工程规范...")
    
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from pre_commit_engineering_check import EngineeringStandardsChecker
    
    checker = EngineeringStandardsChecker()
    
    python_files = list(Path('.').rglob('*.py'))
    # 排除一些目录
    exclude_dirs = {'__pycache__', '.git', 'node_modules', '.venv', 'venv'}
    python_files = [f for f in python_files if not any(exclude in str(f) for exclude in exclude_dirs)]
    
    total_violations = 0
    total_warnings = 0
    
    for file_path in python_files:
        result = checker.check_file(str(file_path))
        violations = result["violations"]
        warnings = result["warnings"]
        
        if violations or warnings:
            print(f"\n📁 {file_path}")
            if violations:
                print("  ❌ 违规:")
                for v in violations:
                    print(f"    - {v}")
                total_violations += len(violations)
            if warnings:
                print("  ⚠️ 警告:")
                for w in warnings:
                    print(f"    - {w}")
                total_warnings += len(warnings)
    
    print(f"\n📊 总结:")
    print(f"  违规: {total_violations}")
    print(f"  警告: {total_warnings}")
    
    if total_violations == 0:
        print("✅ 所有文件通过工程规范检查")


def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == '--monitor':
        start_ide_monitoring()
    else:
        check_current_directory()


if __name__ == "__main__":
    main()
