"""
Agent 初始化模块
在项目启动时自动初始化和注册 Agent
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def initialize_agents() -> Dict[str, Any]:
    """
    初始化所有 Agent
    返回 Agent 信息和状态
    """
    agents_info = {}
    
    try:
        # 导入 Agent
        from Agent.calculator_agent import calculator_agent
        from Agent.data_generator_agent import data_generator_agent
        from Agent.promotion_agent import promotion_agent
        
        # 获取 Agent 信息
        calc_info = calculator_agent.get_info()
        data_gen_info = data_generator_agent.get_info()
        promo_info = promotion_agent.get_info()
        
        # 执行数据生成 Agent 的初始化任务（生成 CSV 文件）
        csv_result = data_generator_agent.generate_csv(
            filename="agent_generated_data.csv",
            num_rows=10
        )
        
        agents_info = {
            "calculator": calc_info,
            "data_generator": {
                **data_gen_info,
                "initial_csv_generation": csv_result
            },
            "promotion": promo_info,
            "status": "initialized",
            "message": "All agents initialized successfully"
        }
        
        logger.info("✅ Agents initialized: Calculator Agent, Data Generator Agent, Promotion Agent")
        if csv_result.get("success"):
            logger.info(f"✅ CSV generated: {csv_result.get('filepath')}")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize agents: {e}")
        agents_info = {
            "status": "failed",
            "error": str(e)
        }
    
    return agents_info


def get_agent_status() -> Dict[str, Any]:
    """获取所有 Agent 的状态"""
    try:
        from Agent.calculator_agent import calculator_agent
        from Agent.data_generator_agent import data_generator_agent
        from Agent.promotion_agent import promotion_agent
        
        return {
            "agents": [
                calculator_agent.get_info(),
                data_generator_agent.get_info(),
                promotion_agent.get_info()
            ],
            "total_agents": 3,
            "status": "running"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def test_calculator_agent() -> Dict[str, Any]:
    """测试计算 Agent"""
    try:
        from Agent.calculator_agent import calculator_agent
        
        # 执行一些测试计算
        tests = [
            calculator_agent.calculate("add", 10, 5),
            calculator_agent.calculate("multiply", 6, 7),
            calculator_agent.calculate("divide", 100, 4),
        ]
        
        return {
            "status": "success",
            "test_results": tests
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }
