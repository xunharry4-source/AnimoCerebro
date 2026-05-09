from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceVerificationRecordsMixin:
    def get_verification_engine_status(self) -> Dict[str, Any]:
        """
        Get verification engine status and configuration.
        
        Returns:
            Dict containing verification engine status
        """
        if not VERIFICATION_AVAILABLE:
            return {
                "available": False,
                "message": "Verification module not installed"
            }
        
        if not self._verification_engine:
            return {
                "available": True,
                "initialized": False,
                "message": "Verification engine not initialized"
            }
        
        # Get registered verifier types
        verifier_types = {}
        if self._verifier_registry:
            verifier_types = {
                k: v.__name__ 
                for k, v in self._verifier_registry.list_verifiers().items()
            }
        
        return {
            "available": True,
            "initialized": True,
            "registered_verifiers": verifier_types,
            "verifier_count": len(verifier_types),
            "message": "Verification engine ready"
        }

    # === Observability Methods (Phase F) ===

    def get_verification_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real verification history from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_verification_completed"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        return [e.payload for e in entries if e.payload]

    def get_dispatch_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real dispatch routing decisions from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_dispatched"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        return [e.payload for e in entries if e.payload]

    def get_supervision_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real supervision/intervention records from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_intervened"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        # Also include other supervision-related events if needed
        return [e.payload for e in entries if e.payload]

    def get_database_status(self) -> Dict[str, Any]:
        """
        Get database layer status and statistics.
        
        Returns:
            Dict containing database status information
        """
        if not DATABASE_AVAILABLE:
            return {
                "available": False,
                "message": "Database module not available"
            }
        
        if not self.use_database:
            return {
                "available": True,
                "enabled": False,
                "message": "Task database layer unavailable"
            }
        
        try:
            # Get task statistics from database
            stats = self._task_dao.get_task_statistics() if self._task_dao else {}
            
            # Get cache info
            cache_info = {
                "size": self._cache.size() if self._cache else 0,
                "max_size": self._cache._max_size if self._cache else 0,
            } if self._cache else {}
            
            return {
                "available": True,
                "enabled": True,
                "db_path": str(self._db.db_path) if self._db else None,
                "statistics": stats,
                "cache": cache_info,
                "daos_initialized": {
                    "task_dao": self._task_dao is not None,
                    "suspended_dao": self._suspended_dao is not None,
                    "audit_dao": self._audit_dao is not None,
                    "intervention_dao": self._intervention_dao is not None,
                    "idempotency_dao": self._idempotency_dao is not None,
                },
                "message": "Database layer operational"
            }
        except Exception as e:
            return {
                "available": True,
                "enabled": True,
                "error": str(e),
                "message": "Database layer error"
            }


