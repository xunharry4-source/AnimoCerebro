"""
Agent Data Access Object for persistent storage.

This module provides database operations for Agent management, including
registration, updates, queries, and audit logging.

Responsibilities:
- CRUD operations for agents table
- Audit log management for agent actions
- Cache management for frequently accessed agents
- JSON serialization/deserialization for complex fields

Architecture:
- Extends BaseDAO for common operations
- Adds agent-specific query methods
- Integrates with LRUCache for performance

Usage:
    db = DatabaseConnection("runtime/data/zentex_core.db")
    cache = LRUCache(max_size=500, ttl_seconds=300)
    dao = AgentDAO(db, cache)
    
    # Register new agent
    dao.register_agent(agent_data)
    
    # Query agents
    agents = dao.list_agents(status="ACTIVE")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache

logger = logging.getLogger(__name__)


class AgentDAO(BaseDAO):
    """
    Data Access Object for Agent entities.
    
    Provides database operations for agent registration, management,
    and audit trail maintenance.
    
    Tables used:
    - agents: Main agent registry
    - agent_audit_log: Audit trail for all agent actions
    """
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        """
        Initialize AgentDAO.
        
        Args:
            db: DatabaseConnection instance
            cache: Optional LRUCache instance
        """
        super().__init__(db, cache)
        self.table_name = "agents"
    
    def register_agent(self, agent_data: Dict[str, Any], operator_id: str = "system", trace_id: str = "") -> bool:
        """
        Register a new agent in the database.
        
        Args:
            agent_data: Agent registration data (must include agent_id)
            operator_id: Who is registering this agent
            trace_id: Trace ID for audit trail
            
        Returns:
            True if registration succeeded
        """
        try:
            # Insert agent record
            success = self.insert(agent_data)
            
            if success:
                # Log audit event
                self._add_audit_log(
                    agent_id=agent_data['agent_id'],
                    action="REGISTER",
                    operator_id=operator_id,
                    details={"endpoint": agent_data.get('endpoint'), "version": agent_data.get('version')},
                    trace_id=trace_id
                )
                logger.info(f"Agent registered: {agent_data['agent_id']}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to register agent: {e}", exc_info=True)
            return False
    
    def update_agent(self, agent_id: str, updates: Dict[str, Any], operator_id: str = "system", trace_id: str = "") -> bool:
        """
        Update an existing agent's information.
        
        Args:
            agent_id: Agent identifier
            updates: Fields to update
            operator_id: Who is making the update
            trace_id: Trace ID for audit trail
            
        Returns:
            True if update succeeded
        """
        try:
            # Update agent record
            success = self.update(agent_id, updates)
            
            if success:
                # Log audit event
                self._add_audit_log(
                    agent_id=agent_id,
                    action="UPDATE",
                    operator_id=operator_id,
                    details={"updated_fields": list(updates.keys())},
                    trace_id=trace_id
                )
                logger.info(f"Agent updated: {agent_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to update agent {agent_id}: {e}", exc_info=True)
            return False
    
    def list_agents(
        self,
        status: Optional[str] = None,
        trust_level: Optional[str] = None,
        role_tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List agents with optional filters.
        
        Args:
            status: Filter by status (e.g., "ACTIVE", "OFFLINE")
            trust_level: Filter by trust level (e.g., "TRUSTED", "PENDING")
            role_tag: Filter by role tag
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of agent dictionaries
        """
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if trust_level:
            conditions.append("trust_level = ?")
            params.append(trust_level)
        
        if role_tag:
            conditions.append("role_tag = ?")
            params.append(role_tag)
        
        if conditions:
            condition_str = " AND ".join(conditions)
            return self.find_by_condition(condition_str, tuple(params), limit, offset)
        else:
            return self.find_all(limit, offset)
    
    def get_agent_by_endpoint(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Find agent by endpoint URL.
        
        Args:
            endpoint: Agent endpoint URL
            
        Returns:
            Agent dictionary or None
        """
        rows = self.db.execute_query(
            "SELECT * FROM agents WHERE endpoint = ? LIMIT 1",
            (endpoint,)
        )
        return self._row_to_dict(rows[0]) if rows else None
    
    def count_by_status(self, status: str) -> int:
        """
        Count agents by status.
        
        Args:
            status: Agent status to count
            
        Returns:
            Number of agents with given status
        """
        cache_key = self._cache_key("count_by_status", lifecycle_status=lifecycle_status)
        
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        count = self.db.execute_scalar(
            "SELECT COUNT(*) FROM agents WHERE status = ?",
            (status,)
        )
        
        self.cache.set(cache_key, count)
        return count
    
    def get_audit_logs(
        self,
        agent_id: str,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get audit logs for an agent.
        
        Args:
            agent_id: Agent identifier
            action: Filter by action type (optional)
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of audit log entries
        """
        if action:
            rows = self.db.execute_query(
                """SELECT * FROM agent_audit_log 
                   WHERE agent_id = ? AND action = ? 
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (agent_id, action, limit, offset)
            )
        else:
            rows = self.db.execute_query(
                """SELECT * FROM agent_audit_log 
                   WHERE agent_id = ? 
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (agent_id, limit, offset)
            )
        
        return [self._row_to_dict(row) for row in rows]
    
    def _add_audit_log(
        self,
        agent_id: str,
        action: str,
        operator_id: str,
        details: Dict[str, Any],
        trace_id: str = ""
    ) -> bool:
        """
        Add an audit log entry for an agent action.
        
        Args:
            agent_id: Agent identifier
            action: Action type (REGISTER, UPDATE, HANDSHAKE, etc.)
            operator_id: Who performed the action
            details: Additional details as dictionary
            trace_id: Trace ID for tracking
            
        Returns:
            True if log entry was added
        """
        try:
            query = """
                INSERT INTO agent_audit_log (agent_id, action, operator_id, details, trace_id)
                VALUES (?, ?, ?, ?, ?)
            """
            self.db.execute_update(
                query,
                (
                    agent_id,
                    action,
                    operator_id,
                    self._serialize_json(details),
                    trace_id
                )
            )
            logger.debug(f"Audit log added: {action} for agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add audit log: {e}", exc_info=True)
            return False
    
    def delete_agent(self, agent_id: str, operator_id: str = "system", trace_id: str = "") -> bool:
        """
        Delete an agent and its audit logs.
        
        Args:
            agent_id: Agent identifier
            operator_id: Who is deleting the agent
            trace_id: Trace ID for audit trail
            
        Returns:
            True if deletion succeeded
        """
        try:
            # Log audit event before deletion
            self._add_audit_log(
                agent_id=agent_id,
                action="UNREGISTER",
                operator_id=operator_id,
                details={"reason": "Agent unregistered"},
                trace_id=trace_id
            )
            
            # Delete agent (audit logs will be cascade deleted)
            success = super().delete(agent_id)
            
            if success:
                logger.info(f"Agent deleted: {agent_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete agent {agent_id}: {e}", exc_info=True)
            return False
