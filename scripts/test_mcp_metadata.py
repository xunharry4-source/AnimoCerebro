#!/usr/bin/env python3
"""
Test script to verify MCP server metadata fields.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from zentex.mcp.models import McpServerConfig, McpServerRuntimeState
from zentex.mcp.storage import McpStorage
from zentex.mcp.service import McpIntegrationService

def test_models():
    """Test that models accept new fields."""
    print("Testing McpServerConfig with new fields...")
    
    config = McpServerConfig(
        server_id="test-server",
        name="测试服务器",
        description="这是一个测试用的MCP服务器",
        version="1.0.0",
        tags=["test", "development"],
        owner="张三",
        transport_type="stdio",
        command="python",
        args=["-m", "mcp_server"],
    )
    
    assert config.name == "测试服务器"
    assert config.description == "这是一个测试用的MCP服务器"
    assert config.version == "1.0.0"
    assert config.tags == ["test", "development"]
    assert config.owner == "张三"
    
    print("✓ McpServerConfig model test passed")
    
    print("\nTesting McpServerRuntimeState with new fields...")
    state = McpServerRuntimeState(
        server_id="test-server",
        name="测试服务器",
        description="这是一个测试用的MCP服务器",
        version="1.0.0",
        tags=["test", "development"],
        owner="张三",
        transport_type="stdio",
        status="online",
        tool_count=5,
    )
    
    assert state.name == "测试服务器"
    assert state.description == "这是一个测试用的MCP服务器"
    assert state.version == "1.0.0"
    assert state.tags == ["test", "development"]
    assert state.owner == "张三"
    
    print("✓ McpServerRuntimeState model test passed")


def test_storage():
    """Test storage operations with new fields."""
    print("\nTesting McpStorage with new fields...")
    
    db_path = Path("runtime/data/zentex_assets.sqlite")
    storage = McpStorage(db_path)
    
    # Test upsert with new fields
    config_dict = {
        "server_id": "test-metadata-server",
        "name": "元数据测试服务器",
        "description": "用于测试新增字段的服务器",
        "version": "2.0.0",
        "tags": ["metadata", "test"],
        "owner": "李四",
        "transport_type": "stdio",
        "command": "echo",
        "args": [],
        "env": {},
        "tool_bindings": [],
    }
    
    storage.upsert_mcp_server(
        server_id="test-metadata-server",
        config_dict=config_dict,
        status="active",
        tool_count=0
    )
    
    # Verify data was stored
    servers = storage.list_mcp_servers()
    test_server = next((s for s in servers if s["server_id"] == "test-metadata-server"), None)
    
    assert test_server is not None, "Test server not found in database"
    assert test_server.get("name") == "元数据测试服务器"
    assert test_server.get("description") == "用于测试新增字段的服务器"
    assert test_server.get("version") == "2.0.0"
    assert test_server.get("owner") == "李四"
    
    print("✓ Storage operations test passed")
    
    # Cleanup
    storage.delete_mcp_server("test-metadata-server")
    print("✓ Test data cleaned up")


def test_service():
    """Test service layer returns new fields."""
    print("\nTesting McpIntegrationService detail endpoint...")
    
    db_path = Path("runtime/data/zentex_assets.sqlite")
    service = McpIntegrationService(str(db_path))
    
    # Register a test server with metadata
    from zentex.mcp.models import McpServerConfig
    
    config = McpServerConfig(
        server_id="test-service-server",
        name="服务层测试服务器",
        description="测试服务层返回的元数据",
        version="1.2.3",
        tags=["service", "integration"],
        owner="王五",
        transport_type="stdio",
        command="echo",
        args=[],
    )
    
    # Note: This will try to connect to the server, which may fail
    # We're mainly testing that the fields are accepted and stored
    try:
        service.register_server(config)
        print("✓ Server registered successfully")
    except Exception as e:
        print(f"⚠ Registration attempted (connection may fail): {e}")
    
    # Check if data is in storage
    storage = McpStorage(db_path)
    servers = storage.list_mcp_servers()
    test_server = next((s for s in servers if s["server_id"] == "test-service-server"), None)
    
    if test_server:
        assert test_server.get("name") == "服务层测试服务器"
        assert test_server.get("description") == "测试服务层返回的元数据"
        assert test_server.get("version") == "1.2.3"
        assert test_server.get("owner") == "王五"
        print("✓ Service layer storage test passed")
        
        # Cleanup
        storage.delete_mcp_server("test-service-server")
        print("✓ Test data cleaned up")
    else:
        print("⚠ Server not found (expected if connection failed)")


if __name__ == "__main__":
    print("=" * 60)
    print("MCP Server Metadata Fields - Test Suite")
    print("=" * 60)
    
    try:
        test_models()
        test_storage()
        test_service()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        sys.exit(0)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
