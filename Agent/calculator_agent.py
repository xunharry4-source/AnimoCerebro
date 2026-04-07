"""
计算功能 Agent
提供基本的数学计算能力
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class CalculatorAgent:
    """简单的计算 Agent，提供基本数学运算"""
    
    def __init__(self):
        self.agent_id = "agent-calculator"
        self.name = "Calculator Agent"
        self.status = "active"
        self.capabilities = ["add", "subtract", "multiply", "divide", "power"]
        self.created_at = datetime.now(timezone.utc)
        
    def calculate(self, operation: str, a: float, b: float) -> Dict[str, Any]:
        """执行计算操作"""
        try:
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b == 0:
                    return {
                        "success": False,
                        "error": "Division by zero",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                result = a / b
            elif operation == "power":
                result = a ** b
            else:
                return {
                    "success": False,
                    "error": f"Unknown operation: {operation}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            return {
                "success": True,
                "operation": operation,
                "operands": {"a": a, "b": b},
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_info(self) -> Dict[str, Any]:
        """获取 Agent 信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "capabilities": self.capabilities,
            "created_at": self.created_at.isoformat()
        }


# 全局实例
calculator_agent = CalculatorAgent()
