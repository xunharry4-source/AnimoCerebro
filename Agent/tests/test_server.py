"""
Test Agent Server - Implements Standard Protocol for Calculator and Data Generator
"""
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from Agent.calculator_agent import calculator_agent
from Agent.data_generator_agent import data_generator_agent

app = FastAPI(title="Zentex Test Agents")

class ExecuteRequest(BaseModel):
    task_id: str
    action: str
    params: Dict[str, Any]

@app.get("/status")
def status():
    return {"status": "online", "uptime": "running"}

@app.post("/handshake")
def handshake():
    return {
        "agent_id": "agent-calculator",
        "version": "1.0.0",
        "capabilities": [
            {"name": "calculate", "description": "Perform math operations"}
        ]
    }

@app.post("/execute")
def execute(request: ExecuteRequest):
    if request.action == "calculate":
        op = request.params.get("operation")
        a = request.params.get("a")
        b = request.params.get("b")
        result = calculator_agent.calculate(op, a, b)
        return {"task_id": request.task_id, "success": True, "result": result}
    raise HTTPException(status_code=400, detail="Unknown action")

# --- Data Generator Agent Instance (Port 9002) ---
app_gen = FastAPI(title="Zentex Data Generator Agent")

@app_gen.get("/status")
def status_gen():
    return {"status": "online", "uptime": "running"}

@app_gen.post("/handshake")
def handshake_gen():
    return {
        "agent_id": "agent-data-generator",
        "version": "1.0.0",
        "capabilities": [
            {"name": "generate_csv", "description": "Generate random CSV data"}
        ]
    }

@app_gen.post("/execute")
def execute_gen(request: ExecuteRequest):
    if request.action == "generate":
        rows = request.params.get("rows", 10)
        filename = request.params.get("filename", "test_output.csv")
        result = data_generator_agent.generate_csv(filename, rows)
        return {"task_id": request.task_id, "success": True, "result": result}
    raise HTTPException(status_code=400, detail="Unknown action")

def run_calc():
    uvicorn.run(app, host="127.0.0.1", port=9001)
        
def run_gen():
    uvicorn.run(app_gen, host="127.0.0.1", port=9002)

if __name__ == "__main__":
    import multiprocessing
    
    p1 = multiprocessing.Process(target=run_calc)
    p2 = multiprocessing.Process(target=run_gen)
    
    print("🚀 Starting Test Agent Servers on :9001 and :9002...")
    p1.start()
    p2.start()
    
    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        p1.terminate()
        p2.terminate()
