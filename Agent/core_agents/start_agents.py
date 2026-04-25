#!/usr/bin/env python3
"""
独立 Agent 启动脚本

文件用途:
    从仓库根目录上下文启动基础 Agent，并执行最小冒烟验证。

主要职责:
    - 初始化 Calculator Agent 和 Data Generator Agent。
    - 验证基础计算能力。
    - 生成一份测试 CSV 作为 Agent 写入能力证据。

不负责:
    - 启动浏览器或执行社交平台发帖。
    - 调用 LLM 或网络服务。
    - 伪造上层发帖流程成功。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from Agent.core_agents.calculator_agent import calculator_agent
from Agent.core_agents.data_generator_agent import data_generator_agent


def start_agents():
    """启动所有 Agent"""
    print("=" * 60)
    print("🚀 Starting Independent Agents")
    print("=" * 60)
    
    # 1. 启动 Calculator Agent
    print("\n📊 Calculator Agent:")
    calc_info = calculator_agent.get_info()
    print(f"   ID: {calc_info['agent_id']}")
    print(f"   Name: {calc_info['name']}")
    print(f"   Status: {calc_info['status']}")
    print(f"   Capabilities: {', '.join(calc_info['capabilities'])}")
    
    # 测试计算功能
    print("\n   Testing calculations:")
    test_cases = [
        ("add", 10, 5),
        ("multiply", 6, 7),
        ("divide", 100, 4),
        ("power", 2, 8),
    ]
    
    for op, a, b in test_cases:
        result = calculator_agent.calculate(op, a, b)
        if result["success"]:
            print(f"   ✓ {a} {op} {b} = {result['result']}")
        else:
            print(f"   ✗ {op} failed: {result.get('error')}")
    
    # 2. 启动 Data Generator Agent
    print("\n📁 Data Generator Agent:")
    data_info = data_generator_agent.get_info()
    print(f"   ID: {data_info['agent_id']}")
    print(f"   Name: {data_info['name']}")
    print(f"   Status: {data_info['status']}")
    print(f"   Capabilities: {', '.join(data_info['capabilities'])}")
    print(f"   Testdata Directory: {data_info['testdata_directory']}")
    
    # 生成 CSV 文件
    print("\n   Generating CSV file with 10 random rows...")
    csv_result = data_generator_agent.generate_csv(
        filename="agent_generated_data.csv",
        num_rows=10
    )
    
    if csv_result["success"]:
        print(f"   ✓ CSV generated successfully!")
        print(f"   File: {csv_result['filepath']}")
        print(f"   Rows: {csv_result['rows_generated']}")
    else:
        print(f"   ✗ Failed to generate CSV: {csv_result.get('error')}")
    
    print("\n" + "=" * 60)
    print("✅ All agents started successfully!")
    print("=" * 60)
    
    return {
        "calculator": calc_info,
        "data_generator": data_info,
        "csv_generation": csv_result
    }


if __name__ == "__main__":
    try:
        start_agents()
    except Exception as e:
        print(f"\n❌ Error starting agents: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
