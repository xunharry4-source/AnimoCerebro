"""
CLI Tool Data Access Object.

This module provides database operations for CLI tool management,
including tool registration, execution history, and credit scoring.

Responsibilities:
- CRUD operations for cli_tools table
- Execution history tracking (cli_execution_history table)
- Credit score calculation and caching (cli_tool_credit_scores table)
- Performance statistics

Usage:
    db = DatabaseConnection("runtime/data/zentex_core.db")
    dao = CliToolDAO(db)
    
    # Register tool
    dao.register_tool(tool_config)
    
    # Record execution
    dao.record_execution(execution_data)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache

logger = logging.getLogger(__name__)


class CliToolDAO(BaseDAO):
    """Data Access Object for CLI Tool entities."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "cli_tools"
    
    def register_tool(self, tool_data: Dict[str, Any]) -> bool:
        """Register a new CLI tool."""
        try:
            success = self.insert(tool_data)
            if success:
                logger.info(f"CLI tool registered: {tool_data['command_name']}")
            return success
        except Exception as e:
            logger.error(f"Failed to register CLI tool: {e}", exc_info=True)
            return False
    
    def update_tool_status(self, command_name: str, status: str) -> bool:
        """Update tool availability status."""
        success = self.update(command_name, {"status": status})
        if success:
            logger.info(f"CLI tool status updated: {command_name} -> {status}")
        return success
    
    def list_tools(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List CLI tools with optional status filter."""
        if status:
            return self.find_by_condition("status = ?", (status,))
        return self.find_all()
    
    def get_tool_by_command(self, command_name: str) -> Optional[Dict[str, Any]]:
        """Get tool by command name."""
        return self.find_by_id(command_name)


class CliExecutionHistoryDAO(BaseDAO):
    """Data Access Object for CLI Execution History."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "cli_execution_history"
    
    def record_execution(self, execution_data: Dict[str, Any]) -> bool:
        """Record a tool execution."""
        return self.insert(execution_data)
    
    def get_history_by_tool(
        self,
        tool_name: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get execution history for a tool."""
        if status:
            return self.find_by_condition(
                "tool_name = ? AND status = ?",
                (tool_name, status),
                limit=limit,
                offset=offset
            )
        return self.find_by_condition(
            "tool_name = ?",
            (tool_name,),
            limit=limit,
            offset=offset
        )
    
    def get_statistics(self, tool_name: str) -> Dict[str, Any]:
        """Get execution statistics for a tool."""
        row = self.db.execute_query(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(duration_ms) as avg_duration
               FROM cli_execution_history
               WHERE tool_name = ?""",
            (tool_name,)
        )[0]
        
        total = row['total'] or 0
        successful = row['successful'] or 0
        return {
            "total_executions": total,
            "successful": successful,
            "failed": row['failed'] or 0,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_duration_ms": row['avg_duration']
        }


class CliCreditScoreDAO(BaseDAO):
    """Data Access Object for CLI Tool Credit Scores."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "cli_tool_credit_scores"
    
    def update_credit_score(self, tool_name: str, score_data: Dict[str, Any]) -> bool:
        """Update or insert credit score for a tool."""
        score_data['tool_name'] = tool_name
        score_data['calculated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Use INSERT OR REPLACE for upsert
        columns = ', '.join(score_data.keys())
        placeholders = ', '.join(['?' for _ in score_data])
        query = f"INSERT OR REPLACE INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        
        try:
            self.db.execute_update(query, tuple(score_data.values()))
            logger.debug(f"Credit score updated for tool: {tool_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to update credit score: {e}", exc_info=True)
            return False
    
    def get_credit_score(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get credit score for a tool."""
        return self.find_by_id(tool_name)
    
    def calculate_and_update_score(self, tool_name: str, history_dao: CliExecutionHistoryDAO) -> Dict[str, Any]:
        """Calculate credit score based on execution history and save it."""
        stats = history_dao.get_statistics(tool_name)
        
        total = stats['total_executions']
        if total == 0:
            score_data = {
                "total_score": 50.0,
                "success_rate": 0.0,
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "average_response_time_ms": None,
                "error_rate": 0.0,
                "usage_frequency": "low",
                "credit_level": "fair"
            }
        else:
            success_rate = stats['success_rate']
            error_rate = 1 - success_rate
            
            # Usage frequency
            if total > 100:
                usage_freq = "high"
            elif total > 20:
                usage_freq = "medium"
            else:
                usage_freq = "low"
            
            # Calculate score (0-100)
            score_from_success = success_rate * 60
            score_from_usage = {"high": 20, "medium": 15, "low": 10}[usage_freq]
            score_from_response = 20  # Default
            
            total_score = min(max(score_from_success + score_from_usage + score_from_response, 0), 100)
            
            # Credit level
            if total_score >= 85:
                credit_level = "excellent"
            elif total_score >= 70:
                credit_level = "good"
            elif total_score >= 50:
                credit_level = "fair"
            else:
                credit_level = "poor"
            
            score_data = {
                "total_score": round(total_score, 2),
                "success_rate": round(success_rate, 4),
                "total_executions": total,
                "successful_executions": stats['successful'],
                "failed_executions": stats['failed'],
                "average_response_time_ms": stats.get('avg_duration_ms'),
                "error_rate": round(error_rate, 4),
                "usage_frequency": usage_freq,
                "credit_level": credit_level
            }
        
        # Save to database
        self.update_credit_score(tool_name, score_data)
        
        return score_data
