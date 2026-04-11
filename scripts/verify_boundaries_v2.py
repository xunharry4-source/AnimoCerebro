import ast
import os
import sys
from pathlib import Path
from typing import List, Set, Tuple

# 定义架构边界
# 模块 A 不允许 直接导入 模块 B 的内部实现
# 必须通过 B.service 或 B.models (如果存在) 进行访问
BOUNDARIES = {
    "web_console": {
        "forbidden": ["zentex.runtime.runtime", "zentex.runtime.engine", "zentex.runtime.session", "zentex.runtime.nine_questions.state", "zentex.runtime.transcript"],
        "allowed": ["zentex.runtime.service", "zentex.runtime.models", "zentex.web_console.contracts", "zentex.web_console.dependencies"],
    },
    "reflection": {
        "forbidden": ["zentex.runtime.runtime", "zentex.runtime.engine"],
        "allowed": ["zentex.runtime.service", "zentex.runtime.models"],
    },
    "memory": {
        "forbidden": ["zentex.runtime.runtime", "zentex.runtime.engine", "zentex.runtime.nine_questions.state"],
        "allowed": ["zentex.runtime.service", "zentex.runtime.models"],
    }
}

def check_file(file_path: Path) -> List[Tuple[int, str]]:
    leaks = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except Exception as e:
        print(f"Skipping {file_path}: {e}")
        return []

    # 确定文件所属的模块
    module_name = None
    for m in BOUNDARIES:
        if f"zentex/{m}" in str(file_path):
            module_name = m
            break
    
    if not module_name:
        return []

    forbidden = BOUNDARIES[module_name]["forbidden"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for f in forbidden:
                    if alias.name.startswith(f):
                        leaks.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for f in forbidden:
                    if node.module.startswith(f):
                        leaks.append((node.lineno, node.module))
    
    return leaks

def main():
    src_root = Path("src/zentex")
    all_leaks = {}
    
    for root, _, files in os.walk(src_root):
        for file in files:
            if file.endswith(".py"):
                path = Path(root) / file
                leaks = check_file(path)
                if leaks:
                    all_leaks[str(path)] = leaks

    if all_leaks:
        print("❌ Architectural Boundary Leaks Detected:")
        for path, leaks in all_leaks.items():
            print(f"\nFile: {path}")
            for line, mod in leaks:
                print(f"  Line {line}: Forbidden import of '{mod}'")
        sys.exit(1)
    else:
        print("✅ No Architectural Boundary Leaks Detected.")
        sys.exit(0)

if __name__ == "__main__":
    main()
