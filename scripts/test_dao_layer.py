#!/usr/bin/env python3
"""
Quick test script to verify DAO layer functionality.

This script tests basic CRUD operations for all DAOs to ensure
the database persistence layer is working correctly.

Usage:
    python scripts/test_dao_layer.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ['PYTHONPATH'] = str(project_root) + ':' + os.environ.get('PYTHONPATH', '')

from zentex.common.dao_registry import get_dao_registry
from datetime import datetime, timezone


def test_agent_dao():
    """Test AgentDAO operations."""
    print("\n=== Testing AgentDAO ===")
    
    registry = get_dao_registry()
    dao = registry.get_agent_dao()
    
    # Test registration
    agent_data = {
        "agent_id": "test-agent-001",
        "name": "test-agent",
        "agent_name": "Test Agent",
        "version": "1.0.0",
        "function_description": "A test agent for DAO testing",
        "endpoint": "http://localhost:9001",
        "role_tag": "test",
        "trust_level": "PENDING",
        "status": "OFFLINE",
        "scope": '["test"]',
        "capabilities": '[]'
    }
    
    success = dao.register_agent(agent_data, operator_id="test_script", trace_id="test-001")
    print(f"✓ Register agent: {'PASS' if success else 'FAIL'}")
    
    # Test query
    agent = dao.find_by_id("test-agent-001")
    print(f"✓ Find by ID: {'PASS' if agent else 'FAIL'}")
    
    # Test list
    agents = dao.list_agents()
    print(f"✓ List agents: {'PASS' if len(agents) > 0 else 'FAIL'} (count: {len(agents)})")
    
    # Test update
    success = dao.update_agent(
        "test-agent-001",
        {"status": "ACTIVE", "latency_ms": 50.0},
        operator_id="test_script"
    )
    print(f"✓ Update agent: {'PASS' if success else 'FAIL'}")
    
    # Test audit logs
    logs = dao.get_audit_logs("test-agent-001")
    print(f"✓ Get audit logs: {'PASS' if len(logs) > 0 else 'FAIL'} (count: {len(logs)})")
    
    # Cleanup
    dao.delete_agent("test-agent-001", operator_id="test_script")
    print("✓ Cleanup: PASS")


def test_mcp_dao():
    """Test MCP Server and Tool DAOs."""
    print("\n=== Testing MCP DAOs ===")
    
    registry = get_dao_registry()
    server_dao = registry.get_mcp_server_dao()
    tool_dao = registry.get_mcp_tool_dao()
    
    # Test server registration
    server_data = {
        "server_id": "test-mcp-server",
        "transport_type": "stdio",
        "command": "echo",
        "args": '[]',
        "env": '{}',
        "status": "CONNECTED",
        "tool_count": 0
    }
    
    success = server_dao.register_server(server_data)
    print(f"✓ Register MCP server: {'PASS' if success else 'FAIL'}")
    
    # Test tool addition
    tools = [
        {
            "tool_name": "test_tool_1",
            "description": "Test tool 1",
            "status": "AVAILABLE"
        },
        {
            "tool_name": "test_tool_2",
            "description": "Test tool 2",
            "status": "AVAILABLE"
        }
    ]
    
    count = tool_dao.add_tools("test-mcp-server", tools)
    print(f"✓ Add MCP tools: {'PASS' if count == 2 else 'FAIL'} (added: {count})")
    
    # Test query with tools
    server_with_tools = server_dao.get_server_with_tools("test-mcp-server")
    print(f"✓ Get server with tools: {'PASS' if server_with_tools and len(server_with_tools.get('tools', [])) == 2 else 'FAIL'}")
    
    # Test list servers
    servers = server_dao.list_servers()
    print(f"✓ List MCP servers: {'PASS' if len(servers) > 0 else 'FAIL'} (count: {len(servers)})")
    
    # Cleanup
    server_dao.delete("test-mcp-server")
    print("✓ Cleanup: PASS")


def test_cli_dao():
    """Test CLI Tool and Execution History DAOs."""
    print("\n=== Testing CLI DAOs ===")
    
    registry = get_dao_registry()
    tool_dao = registry.get_cli_tool_dao()
    exec_dao = registry.get_cli_execution_dao()
    credit_dao = registry.get_cli_credit_dao()
    
    # Test tool registration
    tool_data = {
        "command_name": "test_echo",
        "command_executable": "/bin/echo",
        "description": "Test echo command",
        "status": "AVAILABLE",
        "read_only": True
    }
    
    success = tool_dao.register_tool(tool_data)
    print(f"✓ Register CLI tool: {'PASS' if success else 'FAIL'}")
    
    # Test execution recording
    exec_data = {
        "tool_name": "test_echo",
        "trace_id": "test-exec-001",
        "status": "success",
        "exit_code": 0,
        "stdout": "Hello World",
        "stderr": "",
        "duration_ms": 15.5
    }
    
    success = exec_dao.record_execution(exec_data)
    print(f"✓ Record execution: {'PASS' if success else 'FAIL'}")
    
    # Test statistics
    stats = exec_dao.get_statistics("test_echo")
    print(f"✓ Get statistics: {'PASS' if stats['total_executions'] == 1 else 'FAIL'}")
    
    # Test credit score calculation
    score = credit_dao.calculate_and_update_score("test_echo", exec_dao)
    print(f"✓ Calculate credit score: {'PASS' if score['total_score'] > 0 else 'FAIL'} (score: {score['total_score']})")
    
    # Test history query
    history = exec_dao.get_history_by_tool("test_echo")
    print(f"✓ Get execution history: {'PASS' if len(history) > 0 else 'FAIL'} (count: {len(history)})")
    
    # Cleanup
    tool_dao.delete("test_echo")
    print("✓ Cleanup: PASS")


def main():
    """Run all DAO tests."""
    print("=" * 60)
    print("DAO Layer Quick Test")
    print("=" * 60)
    
    try:
        # Initialize registry
        registry = get_dao_registry()
        registry.initialize("runtime/data/zentex_core.db")
        print("\n✓ DAO Registry initialized")
        
        # Run tests
        test_agent_dao()
        test_mcp_dao()
        test_cli_dao()
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
        # Clear caches
        registry.clear_all_caches()
        print("\n✓ Caches cleared")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
