"""
数据生成 Agent
在 testdata 目录下随机生成 CSV 文件
"""
import csv
import random
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone


class DataGeneratorAgent:
    """数据生成 Agent，在 testdata 目录下生成随机 CSV 数据"""
    
    def __init__(self):
        self.agent_id = "agent-data-generator"
        self.name = "Data Generator Agent"
        self.status = "active"
        self.capabilities = ["generate_csv", "generate_random_data"]
        self.created_at = datetime.now(timezone.utc)
        self.testdata_dir = Path(__file__).parent.parent / "testdata"
        
    def generate_random_string(self, length: int = 8) -> str:
        """生成随机字符串"""
        characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return ''.join(random.choice(characters) for _ in range(length))
    
    def generate_random_data(self, num_rows: int = 10) -> List[Dict[str, Any]]:
        """生成随机数据"""
        data = []
        for i in range(num_rows):
            row = {
                "id": i + 1,
                "name": f"Item_{self.generate_random_string(6)}",
                "value": round(random.uniform(1.0, 1000.0), 2),
                "category": random.choice(["A", "B", "C", "D"]),
                "status": random.choice(["active", "inactive", "pending"]),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": random.randint(0, 100),
                "description": f"Random item {i + 1} - {self.generate_random_string(10)}",
                "is_valid": random.choice([True, False]),
                "priority": random.randint(1, 5),
                "tags": ",".join(random.sample(["tag1", "tag2", "tag3", "tag4", "tag5"], 
                                               random.randint(1, 3)))
            }
            data.append(row)
        return data
    
    def generate_csv(self, filename: str = "random_data.csv", num_rows: int = 10) -> Dict[str, Any]:
        """生成 CSV 文件"""
        try:
            # 确保 testdata 目录存在
            self.testdata_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = self.testdata_dir / filename
            
            # 生成随机数据
            data = self.generate_random_data(num_rows)
            
            # 写入 CSV 文件
            if data:
                fieldnames = data[0].keys()
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)
            
            return {
                "success": True,
                "filename": str(filename),
                "filepath": str(filepath),
                "rows_generated": len(data),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"Successfully generated {len(data)} rows in {filename}"
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
            "testdata_directory": str(self.testdata_dir),
            "created_at": self.created_at.isoformat()
        }


# 全局实例
data_generator_agent = DataGeneratorAgent()
