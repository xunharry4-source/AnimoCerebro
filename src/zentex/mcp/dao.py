"""
MCP Server and Tool Data Access Objects.

This module provides database operations for MCP server management,
including server registration, tool mapping, and execution records.

Responsibilities:
- CRUD operations for mcp_servers table
- Tool mapping management (mcp_tools table)
- Execution record tracking (mcp_execution_records table)
- Cache management for server states

Usage:
    db = DatabaseConnection("runtime/data/zentex_core.db")
    dao = McpServerDAO(db)
    
    # Register server
    dao.register_server(server_config)
    
    # Add tools
    dao.add_tools(server_id, tools_list)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache

logger = logging.getLogger(__name__)


class McpServerDAO(BaseDAO):
    """Data Access Object for MCP Server entities."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "mcp_servers"
    
    def register_server(self, server_data: Dict[str, Any]) -> bool:
        """Register a new MCP server."""
        try:
            success = self.insert(server_data)
            if success:
                logger.info(f"MCP server registered: {server_data['server_id']}")
            return success
        except Exception as e:
            logger.error(f"Failed to register MCP server: {e}", exc_info=True)
            return False
    
    def update_server_status(self, server_id: str, status: str, error_message: Optional[str] = None) -> bool:
        """Update server connection status."""
        updates = {"status": status}
        if error_message is not None:
            updates["error_message"] = error_message
        
        success = self.update(server_id, updates)
        if success:
            logger.info(f"MCP server status updated: {server_id} -> {status}")
        return success
    
    def list_servers(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List MCP servers with optional status filter."""
        if status:
            return self.find_by_condition("status = ?", (status,))
        return self.find_all()
    
    def get_server_with_tools(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get server details including all its tools."""
        server = self.find_by_id(server_id)
        if not server:
            return None
        
        # Get tools for this server
        tools_dao = McpToolDAO(self.db, self.cache)
        tools = tools_dao.get_tools_by_server(server_id)
        
        server['tools'] = tools
        return server


class McpToolDAO(BaseDAO):
    """Data Access Object for MCP Tool entities."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "mcp_tools"
    
    def add_tools(self, server_id: str, tools: List[Dict[str, Any]]) -> int:
        """Add multiple tools for a server."""
        count = 0
        for tool in tools:
            tool['server_id'] = server_id
            if self.insert(tool):
                count += 1
        
        if count > 0:
            # Update server tool count
            self.db.execute_update(
                "UPDATE mcp_servers SET tool_count = (SELECT COUNT(*) FROM mcp_tools WHERE server_id = ?) WHERE server_id = ?",
                (server_id, server_id)
            )
            logger.info(f"Added {count} tools for MCP server: {server_id}")
        
        return count
    
    def get_tools_by_server(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all tools for a specific server."""
        return self.find_by_condition("server_id = ?", (server_id,), limit=1000)
    
    def update_tool_status(self, server_id: str, tool_name: str, status: str) -> bool:
        """Update tool availability status."""
        rows = self.db.execute_query(
            "SELECT id FROM mcp_tools WHERE server_id = ? AND tool_name = ?",
            (server_id, tool_name)
        )
        
        if not rows:
            return False
        
        tool_id = rows[0]['id']
        return self.update(str(tool_id), {"status": status})


class McpExecutionRecordDAO(BaseDAO):
    """Data Access Object for MCP Execution Records."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "mcp_execution_records"
    
    def add_execution_record(self, record_data: Dict[str, Any]) -> bool:
        """Add a new execution record."""
        return self.insert(record_data)
    
    def get_records_by_server(
        self,
        server_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get execution records for a server."""
        if status:
            return self.find_by_condition(
                "server_id = ? AND status = ?",
                (server_id, status),
                limit=limit
            )
        return self.find_by_condition("server_id = ?", (server_id,), limit=limit)
    
    def get_statistics(self, server_id: str) -> Dict[str, Any]:
        """Get execution statistics for a server."""
        row = self.db.execute_query(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(duration_seconds) as avg_duration
               FROM mcp_execution_records
               WHERE server_id = ?""",
            (server_id,)
        )[0]
        
        total = row['total'] or 0
        completed = row['completed'] or 0
        return {
            "total_executions": total,
            "completed": completed,
            "failed": row['failed'] or 0,
            "success_rate": completed / total if total > 0 else 0.0,
            "avg_duration_seconds": row['avg_duration']
        }
